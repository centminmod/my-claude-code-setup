"""Compare primitives for session-metrics.

Split out from ``session-metrics.py`` to keep per-file size manageable
as the compare feature grows (planned: pairing, rendering, insights
card, count-tokens API mode — see ``~/.claude/plans/`` for the full
design).

Scope boundary:

- **This module** — compare-specific helpers: model-family slug,
  turn pairing, per-project family inventory, CLI-arg resolver.
- **``session-metrics.py``** — everything else: pricing, JSONL
  parsing, session loading, existing report rendering, CLI entry.

Runtime coupling is one-way: a small set of helpers is looked up
from ``sys.modules["session_metrics"]`` via :func:`_main` when
needed. Callers (the CLI and tests) must ensure ``session-metrics.py``
has been imported first under that module name.
"""
from __future__ import annotations

import csv as csv_mod
import hashlib
import io
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Runtime coupling helper
# ---------------------------------------------------------------------------

_MAIN_MODULE_NAME = "session_metrics"


def _main():
    """Return the loaded ``session-metrics`` module.

    Raises :class:`RuntimeError` if it hasn't been loaded yet. Tests
    and the CLI entrypoint both load the main module under the name
    ``session_metrics`` before calling any compare helper that needs
    it (``_find_jsonl_files``, ``_load_session``, ``_SESSION_RE``,
    ``_projects_dir``).
    """
    mod = sys.modules.get(_MAIN_MODULE_NAME)
    if mod is None:
        raise RuntimeError(
            f"{_MAIN_MODULE_NAME!r} must be loaded before compare helpers "
            "that depend on it are called"
        )
    return mod


# ---------------------------------------------------------------------------
# Model-family slug (fine-grained; distinct from coarse _model_family)
# ---------------------------------------------------------------------------

_CONTEXT_TIER_SUFFIX_RE = re.compile(r"\[[^\]]*\]$")


def _strip_context_tier_suffix(model_id: str) -> str:
    """Strip a trailing bracketed context-tier tag like ``[1m]``.

    Claude Code tags the 1M-context Opus 4.7 variant as
    ``claude-opus-4-7[1m]`` in ``message.model``. For compare-mode
    family matching we treat this as the same family as the non-[1m]
    baseline — pricing is identical (prefix fallback already handles
    it) and the tokenizer is the same.
    """
    return _CONTEXT_TIER_SUFFIX_RE.sub("", model_id or "")


def _model_family_slug(model_id: str) -> str:
    """Fine-grained family slug from a model id — e.g. ``opus-4-7``.

    Distinct from ``session_metrics._model_family()`` (which returns
    the coarse ``"Opus"`` / ``"Sonnet"`` / ``"Haiku"`` bucket used by
    the dashboard card). This finer-grained slug is what the
    compare-mode ``last-<family>`` / ``all-<family>`` resolver keys
    off of, and what sessions get grouped by for Mode 2 (project-
    aggregate) compare.

    - Strips the ``[1m]`` (or similar bracketed) context-tier suffix.
    - Strips the leading ``claude-`` namespace.
    - Strips trailing date stamps like ``-20251001`` seen on some
      haiku ids — so ``claude-haiku-4-5`` and
      ``claude-haiku-4-5-20251001`` return the same slug.
    - Returns ``""`` for unknown / empty / non-Claude model ids so
      callers can detect and refuse gracefully (BYOK / proxy guard).
    """
    if not model_id:
        return ""
    m = _strip_context_tier_suffix(model_id).lower()
    if not m.startswith("claude-"):
        return ""
    m = m[len("claude-"):]
    # Trim a trailing ``-YYYYMMDD`` date stamp if present.
    m = re.sub(r"-\d{8}$", "", m)
    return m


# ---------------------------------------------------------------------------
# Turn pairing
# ---------------------------------------------------------------------------

# Fingerprint length: hash the first N characters of a user prompt to
# pair turns across two sessions that ran the same prompts. Chosen
# long enough to avoid collisions in practice (even short prompts
# differ in their first 200 chars) but short enough that trailing
# whitespace / minor edits don't cause mismatches.
_FINGERPRINT_PREFIX_LEN = 200


def _user_prompt_fingerprint_text(preceding_user_content: object) -> str:
    """Extract plain text from a ``_preceding_user_content`` value.

    Returns the concatenated ``text`` of every text block, whitespace-
    collapsed and stripped. Non-text blocks (tool_result, image) are
    ignored — they don't represent a user-written prompt. Returns
    ``""`` for empty / missing / pure-tool-result entries, which the
    fingerprint pairing should skip.
    """
    if preceding_user_content is None:
        return ""
    if isinstance(preceding_user_content, str):
        return " ".join(preceding_user_content.split())
    if isinstance(preceding_user_content, list):
        parts: list[str] = []
        for block in preceding_user_content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text") or ""
                if text:
                    parts.append(text)
        joined = " ".join(parts)
        return " ".join(joined.split())
    return ""


def _user_prompt_fingerprint(text: str) -> str:
    """Stable sha1 hash of the first ``_FINGERPRINT_PREFIX_LEN`` chars
    of a user prompt.

    The text is whitespace-collapsed upstream by
    :func:`_user_prompt_fingerprint_text`, so CR/LF drift and
    leading/trailing whitespace don't change the hash. The prefix
    is taken after normalization so different line-endings don't
    shift chars in and out of the hashed window.
    """
    head = (text or "")[:_FINGERPRINT_PREFIX_LEN]
    return hashlib.sha1(head.encode("utf-8")).hexdigest()


def _pair_turns(
    a_turns: list[dict],
    b_turns: list[dict],
    mode: str = "fingerprint",
) -> dict:
    """Pair turns from session A with turns from session B.

    Input turns are raw entries as returned by
    ``session_metrics._extract_turns()`` — they carry
    ``_preceding_user_content`` for fingerprint pairing. Subagent /
    sidechain entries are filtered out upstream by ``_load_session``
    when ``include_subagents=False``.

    Strategies:

    - ``mode="ordinal"``: pairs turn ``i`` of A with turn ``i`` of B.
      Emits whichever tail is longer as unmatched. Simplest possible
      pairing; assumes the user ran the same prompt sequence in both
      sessions.

    - ``mode="fingerprint"`` (default): hashes the first
      ``_FINGERPRINT_PREFIX_LEN`` chars of each turn's preceding user
      prompt and pairs on hash equality. Tolerant of minor drift,
      skipped turns, or extra turns on one side. Within each side,
      duplicate fingerprints (same prompt asked twice) are paired by
      ordinal within-hash position so the second occurrence on A
      pairs with the second occurrence on B.

    Returns a dict::

        {
            "mode":        "ordinal" | "fingerprint",
            "paired":      [(a_turn, b_turn), ...],
            "unmatched_a": [a_turn, ...],
            "unmatched_b": [b_turn, ...],
            "warnings":    [str, ...],   # human-readable advisories
        }
    """
    if mode not in ("ordinal", "fingerprint"):
        raise ValueError(f"unknown pairing mode: {mode!r}")

    warnings: list[str] = []

    if mode == "ordinal":
        n = min(len(a_turns), len(b_turns))
        paired = list(zip(a_turns[:n], b_turns[:n]))
        tail_a = list(a_turns[n:])
        tail_b = list(b_turns[n:])
        if tail_a or tail_b:
            warnings.append(
                f"ordinal pairing: lengths differ "
                f"(a={len(a_turns)}, b={len(b_turns)}); "
                f"{len(tail_a) + len(tail_b)} turn(s) left unmatched"
            )
        return {
            "mode":        "ordinal",
            "paired":      paired,
            "unmatched_a": tail_a,
            "unmatched_b": tail_b,
            "warnings":    warnings,
        }

    # Fingerprint mode.
    a_by_fp: dict[str, list[dict]] = {}
    b_by_fp: dict[str, list[dict]] = {}
    a_empty: list[dict] = []
    b_empty: list[dict] = []
    for t in a_turns:
        text = _user_prompt_fingerprint_text(t.get("_preceding_user_content"))
        if not text:
            a_empty.append(t)
            continue
        a_by_fp.setdefault(_user_prompt_fingerprint(text), []).append(t)
    for t in b_turns:
        text = _user_prompt_fingerprint_text(t.get("_preceding_user_content"))
        if not text:
            b_empty.append(t)
            continue
        b_by_fp.setdefault(_user_prompt_fingerprint(text), []).append(t)

    paired: list[tuple[dict, dict]] = []
    unmatched_a: list[dict] = list(a_empty)
    unmatched_b: list[dict] = list(b_empty)
    for fp, a_list in a_by_fp.items():
        b_list = b_by_fp.get(fp, [])
        k = min(len(a_list), len(b_list))
        for i in range(k):
            paired.append((a_list[i], b_list[i]))
        unmatched_a.extend(a_list[k:])
        unmatched_b.extend(b_list[k:])
    # B-side fingerprints with no A counterpart.
    for fp, b_list in b_by_fp.items():
        if fp not in a_by_fp:
            unmatched_b.extend(b_list)

    if not paired and (a_turns or b_turns):
        warnings.append(
            "fingerprint pairing matched 0 turns — did both sessions run "
            "the same prompt suite?"
        )
    if unmatched_a or unmatched_b:
        warnings.append(
            f"fingerprint pairing: {len(unmatched_a)} turn(s) on side A and "
            f"{len(unmatched_b)} on side B had no partner"
        )
    return {
        "mode":        "fingerprint",
        "paired":      paired,
        "unmatched_a": unmatched_a,
        "unmatched_b": unmatched_b,
        "warnings":    warnings,
    }


# ---------------------------------------------------------------------------
# Project-level inventory and arg resolver
# ---------------------------------------------------------------------------

def _dominant_model_family(turns: list[dict]) -> str:
    """Most frequent ``_model_family_slug`` across a session's turns.

    Ties broken by first-seen order (Python 3.7+ dict insertion order).
    Returns ``""`` if ``turns`` is empty or no turn has a known family.
    """
    counts: dict[str, int] = {}
    for t in turns:
        model = (t.get("message") or {}).get("model") or t.get("model") or ""
        slug = _model_family_slug(model)
        if slug:
            counts[slug] = counts.get(slug, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _project_family_inventory(
    slug: str,
    include_subagents: bool = False,
    use_cache: bool = True,
) -> dict[str, list[tuple[Path, int]]]:
    """Scan every session in a project and group by dominant family.

    Returns:
        ``{family_slug: [(path, user_turn_count), ...], ...}`` where
        the inner lists are sorted most-recent-first (matching the
        order of ``session_metrics._find_jsonl_files``). Sessions
        whose dominant model doesn't resolve to a known family are
        bucketed under ``""``.
    """
    m = _main()
    inventory: dict[str, list[tuple[Path, int]]] = {}
    for path in m._find_jsonl_files(slug, include_subagents=include_subagents):
        try:
            _sid, turns, user_ts = m._load_session(
                path, include_subagents=include_subagents, use_cache=use_cache,
            )
        except OSError:
            continue
        family = _dominant_model_family(turns)
        inventory.setdefault(family, []).append((path, len(user_ts)))
    return inventory


class CompareArgError(ValueError):
    """Raised by :func:`_resolve_compare_arg` when an arg can't be
    resolved to one or more session paths.

    Carries a user-facing message; the CLI catches this and prints
    ``[error] <msg>`` then exits. Tests assert the message text.
    """


def _resolve_compare_arg(
    arg: str,
    slug: str,
    *,
    include_subagents: bool = False,
    min_turns: int = 5,
    use_cache: bool = True,
) -> tuple[str, list[Path]]:
    """Resolve a ``--compare`` arg to one or more session JSONL paths.

    Accepts four forms:

    - **Path**: absolute or relative ``.jsonl`` path. Returned as
      ``("single", [path])`` if the file exists.
    - **Session UUID**: a value matching
      ``session_metrics._SESSION_RE``. Looked up under the current
      project's slug dir (and as a fallback, any project dir under
      ``CLAUDE_PROJECTS_DIR``).
    - **``last-<family>``**: the most-recent session in the current
      project whose dominant model family slug matches ``<family>``.
      Skips sessions with fewer than ``min_turns`` user prompts.
      Returns ``("single", [path])``.
    - **``all-<family>``**: every session in the current project
      whose dominant model family slug matches ``<family>``. No
      min-turn filter (aggregates observational data; short sessions
      still contribute). Returns ``("aggregate", [path, ...])``.

    Raises :class:`CompareArgError` on any failure with a message
    that tells the user *what* went wrong and, where possible,
    *what alternatives are present* (e.g. listing the families
    actually seen in the project for typo'd ``last-X`` tokens).
    """
    if not arg:
        raise CompareArgError("compare arg is empty")

    m = _main()

    # Form 1: path. Must contain a path separator OR end in .jsonl
    # to avoid mis-matching bare family slugs that happen to exist
    # as cwd-relative paths.
    if "/" in arg or arg.endswith(".jsonl"):
        p = Path(arg).expanduser()
        if p.exists() and p.is_file():
            resolved = p.resolve()
            # Regression guard for H5: reject paths outside the projects
            # directory. Main-script single-session lookup already enforces
            # this via _ensure_within_projects; compare's explicit-path form
            # must apply the same guard to prevent symlink/traversal escapes
            # (e.g. ``/etc/passwd.jsonl`` or ``../../escape.jsonl``).
            root = m._projects_dir().resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise CompareArgError(
                    f"refusing to read outside {root}: {resolved}"
                ) from exc
            return ("single", [resolved])
        raise CompareArgError(f"path does not exist: {arg}")

    # Forms 2 & 3: magic tokens. Checked BEFORE session-UUID because
    # ``_SESSION_RE`` is permissive (any ``[A-Za-z0-9._-]{1,64}``) and
    # would accept ``last-opus-4-7`` / ``all-opus-4-7`` as "UUIDs",
    # masking the magic-token path.
    if arg.startswith("last-") or arg.startswith("all-"):
        kind, _, family = arg.partition("-")
        family = family.strip()
        if not family:
            raise CompareArgError(
                f"magic token {arg!r} is missing a family slug "
                f"(expected e.g. 'last-opus-4-7')"
            )
        inventory = _project_family_inventory(
            slug, include_subagents=include_subagents, use_cache=use_cache,
        )
        # Fuzzy family match: allow short forms like ``4-7`` when only
        # one family in the project carries that suffix.
        matched = _match_family_key(family, list(inventory.keys()))
        if matched is None:
            present = sorted(f for f in inventory if f)
            if not present:
                raise CompareArgError(
                    f"no sessions with a recognized Claude model family "
                    f"in project {slug!r}"
                )
            raise CompareArgError(
                f"no sessions found for family {family!r} in project "
                f"{slug!r}. Families present: {', '.join(present)}"
            )
        sessions = inventory[matched]
        if kind == "last":
            eligible = [(p, n) for p, n in sessions if n >= min_turns]
            if not eligible:
                raise CompareArgError(
                    f"no session of family {matched!r} in project "
                    f"{slug!r} has >={min_turns} user prompt(s) "
                    f"(found {len(sessions)} with fewer turns - "
                    f"override with --compare-min-turns)"
                )
            # _find_jsonl_files returns newest-first, preserved by
            # _project_family_inventory; eligible[0] is newest.
            return ("single", [eligible[0][0]])
        # kind == "all"
        return ("aggregate", [p for p, _n in sessions])

    # Form 4: bare session UUID. ``_SESSION_RE`` accepts any
    # ``[A-Za-z0-9._-]{1,64}`` so this branch runs only after the
    # magic-token prefixes have been ruled out above.
    if m._SESSION_RE.match(arg):
        candidate = m._projects_dir() / slug / f"{arg}.jsonl"
        if candidate.exists():
            return ("single", [candidate.resolve()])
        # Fallback: search across all project dirs.
        for p in m._projects_dir().rglob(f"{arg}.jsonl"):
            return ("single", [p.resolve()])
        raise CompareArgError(f"session id not found: {arg}")

    raise CompareArgError(
        f"could not interpret compare arg {arg!r}. Expected a path, "
        f"session UUID, or 'last-<family>' / 'all-<family>' token"
    )


def _match_family_key(query: str, candidates: list[str]) -> str | None:
    """Match a family query string against present-family slugs.

    Tries, in order:

    1. Exact match (``opus-4-7`` → ``opus-4-7``).
    2. Candidates that **end with** ``-<query>`` when exactly one
       such candidate exists (``4-7`` → ``opus-4-7`` iff there's no
       other ``*4-7`` present like ``sonnet-4-7``).

    Returns the matched key or ``None``. ``None`` signals the caller
    to produce a friendly error listing candidates.
    """
    real = [c for c in candidates if c]
    if query in real:
        return query
    suffix_matches = [
        c for c in real if c == query or c.endswith("-" + query)
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    return None


# ---------------------------------------------------------------------------
# Compare-report builder (Mode 1 — controlled session pair)
# ---------------------------------------------------------------------------

# Threshold for the cache-read-share-of-input drift advisory. When two
# sessions differ by more than this many percentage points, the header
# flags it — cache warmth confounds tokenizer-ratio interpretation.
_CACHE_SHARE_DRIFT_PP = 10.0


def _context_tier_from_model_id(model_id: str) -> str:
    """Extract a bracketed context-tier tag from a model id.

    ``claude-opus-4-7[1m]`` → ``"1m"``; bare ``claude-opus-4-7`` → ``""``.
    The lowercased inner token is returned so advisory text can say
    "1m vs default" without caring about source-case drift.
    """
    if not model_id:
        return ""
    m = _CONTEXT_TIER_SUFFIX_RE.search(model_id)
    if not m:
        return ""
    return m.group(0).strip("[]").lower()


def _dominant_model_id(turns: list[dict]) -> str:
    """Most-frequent raw ``message.model`` string across a session's turns.

    Returns the full model id including any ``[1m]`` suffix — distinct
    from :func:`_model_family_slug`, which strips that suffix. Used by
    the compare report so the header can display the exact model id the
    user ran, not a normalized slug.
    """
    counts: dict[str, int] = {}
    for t in turns:
        model = (t.get("message") or {}).get("model") or t.get("model") or ""
        if model:
            counts[model] = counts.get(model, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    """Return ``numerator/denominator`` or ``None`` if denominator is 0.

    Ratio math is everywhere in the compare report (b/a for tokens, cost,
    chars-per-token). Zero-input turns are possible (tool-result-only
    exchanges), so every division path funnels through this guard.
    """
    if not denominator:
        return None
    return numerator / denominator


def _mcnemar_midp(b: int, c: int) -> float | None:
    """Two-sided mid-p McNemar test on paired binary outcomes.

    Given the discordant-pair counts ``b`` (A-pass, B-fail) and ``c``
    (A-fail, B-pass), returns the two-sided mid-p value under the null
    hypothesis that A and B have equal pass rates. Concordant pairs
    (both pass, both fail) carry no information about the delta and
    are not inputs to the test.

    Mid-p is used instead of the exact binomial tail because the exact
    test is conservative at small n (our IFEval suite is N=9–10). For
    ``b + c == 0`` (no discordant pairs), returns ``None`` — there is
    no evidence for or against a difference.

    Stdlib-only: uses ``math.comb`` for exact binomial PMF under p=0.5.
    """
    n = b + c
    if n == 0:
        return None
    k = min(b, c)
    # P(X <= k) under Binomial(n, 0.5)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    # mid-p: subtract half of the point mass at k
    point_k = math.comb(n, k) / (2 ** n)
    midp_one_sided = tail - 0.5 * point_k
    # two-sided: double, capped at 1.0
    return min(1.0, 2.0 * midp_one_sided)


def _wilson_ci(successes: int, n: int,
               z: float = 1.959963984540054) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion.

    Closed-form 95% CI (default ``z`` is the exact two-sided 0.975
    quantile of the standard normal). Returns ``(lo, hi)`` both in
    [0, 1], or ``None`` when ``n == 0``. Wilson is preferred over the
    naive Wald interval because it stays inside [0, 1] and has better
    coverage at small n and at boundary proportions (0 or 1) — both
    common in our N=9–10 IFEval suite.
    """
    if n <= 0:
        return None
    p_hat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p_hat + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def _compute_ratios(a_rec: dict, b_rec: dict) -> dict:
    """Per-turn b/a ratios for the four headline columns.

    Returns a dict with ``input_tokens``, ``output_tokens``,
    ``total_tokens``, ``cost_usd`` — each a float or ``None`` when the
    A-side denominator is zero. Used to heatmap the turn table and to
    feed the p50/p95 histogram in later HTML work.
    """
    return {
        "input_tokens":  _safe_ratio(b_rec["input_tokens"], a_rec["input_tokens"]),
        "output_tokens": _safe_ratio(b_rec["output_tokens"], a_rec["output_tokens"]),
        "total_tokens":  _safe_ratio(b_rec["total_tokens"], a_rec["total_tokens"]),
        "cost_usd":      _safe_ratio(b_rec["cost_usd"], a_rec["cost_usd"]),
    }


def _cache_read_share_pct(totals: dict) -> float:
    """Cache reads as a percentage of total input-side tokens.

    ``total_input`` is already computed by ``_totals_from_turns`` as the
    sum of uncached input + cache reads + cache writes. Returns 0 when
    a session has no input at all (degenerate but possible for
    single-turn no-cache transcripts).
    """
    total_input = totals.get("total_input", 0) or 0
    if not total_input:
        return 0.0
    return 100.0 * (totals.get("cache_read", 0) or 0) / total_input


def _build_side_info(
    session_id: str,
    raw_turns: list[dict],
    user_ts: list[int],
    turn_records: list[dict],
    tz_offset_hours: float,
    *,
    effort: str | None = None,
) -> dict:
    """Compact per-side summary consumed by every compare renderer.

    Carries both the raw model id (with any ``[1m]`` suffix, used for
    the header banner) and the stripped family slug (used for
    model-agnostic report copy).

    ``effort`` records the ``claude -p --effort <level>`` value the
    side was captured with. Preserved verbatim (``"low"`` / ``"medium"``
    / ``"high"`` / ``"xhigh"`` / ``"max"``) and ``None`` when the caller
    didn't pin a level — renderers must surface it only when truthy so
    Mode 2 and arbitrary-JSONL inputs that never went through the
    compare-run orchestrator stay unannotated.
    """
    m = _main()
    dominant = _dominant_model_id(raw_turns)
    totals = m._totals_from_turns(turn_records)
    first_ts = raw_turns[0].get("timestamp", "") if raw_turns else ""
    last_ts = raw_turns[-1].get("timestamp", "") if raw_turns else ""
    return {
        "session_id":        session_id,
        "session_ids":       [session_id],   # Mode 2 will carry a list
        "dominant_model_id": dominant,
        "model_family":      _model_family_slug(dominant),
        "context_tier":      _context_tier_from_model_id(dominant),
        "effort":            effort or None,
        "turn_count":        len(turn_records),
        "user_prompt_count": len(user_ts),
        "first_ts":          first_ts,
        "last_ts":           last_ts,
        "first_ts_fmt":      m._fmt_ts(first_ts, tz_offset_hours) if first_ts else "",
        "last_ts_fmt":       m._fmt_ts(last_ts, tz_offset_hours) if last_ts else "",
        "totals":            totals,
        "cache_read_share_of_input": _cache_read_share_pct(totals),
    }


def _build_aggregate_side_info(
    sessions: list[tuple[str, list[dict], list[int], list[dict]]],
    tz_offset_hours: float,
    *,
    effort: str | None = None,
) -> dict:
    """Aggregate multiple sessions into a single compare side.

    ``sessions`` is a list of ``(session_id, raw_turns, user_timestamps,
    turn_records)`` tuples — one per session rolled into this side. The
    returned dict carries the same keys as :func:`_build_side_info` plus:

    - ``session_count``: number of sessions aggregated.
    - ``session_ids``: the full list.
    - ``avg_input_tokens_per_prompt``, ``avg_output_tokens_per_turn``: the
      aggregate-only averages listed in the Phase 3 plan.
    - ``tool_calls_per_turn`` and ``thinking_turn_pct``: mirrored out of
      ``totals`` to the top level so the observational report can pull
      them without digging into the totals sub-dict.

    Mode 1 side_info is retained separately — flattening both shapes
    into one entry point would make Mode 1 callers carry degenerate
    single-session fields they don't use.

    ``effort`` mirrors :func:`_build_side_info` — pinned reasoning
    level annotated onto the side if known, ``None`` otherwise. Mode 2
    aggregates are rarely captured via the orchestrator so this stays
    ``None`` by default; callers who do know the level (e.g. tests)
    can still pass it through.
    """
    m = _main()

    session_ids = [sid for sid, _r, _u, _rec in sessions]
    flat_raw = [t for _sid, raw, _u, _rec in sessions for t in raw]
    flat_records = [r for _sid, _raw, _u, recs in sessions for r in recs]
    flat_user_ts = [ts for _sid, _raw, uts, _rec in sessions for ts in uts]

    totals = m._totals_from_turns(flat_records)
    dominant = _dominant_model_id(flat_raw)

    all_timestamps = [t.get("timestamp", "") for t in flat_raw if t.get("timestamp")]
    first_ts = min(all_timestamps) if all_timestamps else ""
    last_ts = max(all_timestamps) if all_timestamps else ""

    n_turns = len(flat_records)
    n_prompts = len(flat_user_ts)

    return {
        "session_id":        session_ids[0] if len(session_ids) == 1 else "",
        "session_ids":       session_ids,
        "session_count":     len(session_ids),
        "dominant_model_id": dominant,
        "model_family":      _model_family_slug(dominant),
        "context_tier":      _context_tier_from_model_id(dominant),
        "effort":            effort or None,
        "turn_count":        n_turns,
        "user_prompt_count": n_prompts,
        "first_ts":          first_ts,
        "last_ts":           last_ts,
        "first_ts_fmt":      m._fmt_ts(first_ts, tz_offset_hours) if first_ts else "",
        "last_ts_fmt":       m._fmt_ts(last_ts, tz_offset_hours) if last_ts else "",
        "totals":            totals,
        "cache_read_share_of_input":   _cache_read_share_pct(totals),
        "avg_input_tokens_per_prompt": (
            totals["input"] / n_prompts if n_prompts else 0.0
        ),
        "avg_output_tokens_per_turn":  (
            totals["output"] / n_turns if n_turns else 0.0
        ),
        "tool_calls_per_turn":         totals.get("tool_call_avg_per_turn", 0.0),
        "thinking_turn_pct":           totals.get("thinking_turn_pct", 0.0),
    }


def _build_advisories(
    side_a: dict,
    side_b: dict,
    pairing: dict,
) -> list[dict]:
    """Header-banner advisories surfaced on top of the compare report.

    Kinds:

    - ``context-tier-mismatch``: one side is ``[1m]`` and the other
      isn't. Any tokenizer ratio conflates tokenizer + window-tier.
    - ``cache-share-drift``: cache-read share differs by more than
      :data:`_CACHE_SHARE_DRIFT_PP` percentage points. Cache warmth
      was different; read the cache column with skepticism.
    - ``model-family-collision``: same family on both sides. Degenerate
      compare — probably an A/B replay of one model. Still renders.
    - ``no-fingerprint-matches``: fingerprint pairing produced 0 pairs.
      Likely the two sessions didn't run the same prompts.
    - ``empty-side``: one side has no turns.

    Each advisory is ``{"kind": str, "severity": "warn"|"info",
    "message": str}``. Renderers treat ``warn`` prominently; ``info``
    is a footnote.
    """
    advisories: list[dict] = []

    if side_a["context_tier"] != side_b["context_tier"]:
        a_tier = side_a["context_tier"] or "default"
        b_tier = side_b["context_tier"] or "default"
        advisories.append({
            "kind":     "context-tier-mismatch",
            "severity": "warn",
            "message": (
                f"context-tier mismatch: side A is {a_tier!r}, side B is "
                f"{b_tier!r} — any ratio conflates tokenizer + context-window"
            ),
        })

    a_share = side_a["cache_read_share_of_input"]
    b_share = side_b["cache_read_share_of_input"]
    if abs(a_share - b_share) > _CACHE_SHARE_DRIFT_PP:
        advisories.append({
            "kind":     "cache-share-drift",
            "severity": "warn",
            "message": (
                f"cache-read share differs by "
                f"{abs(a_share - b_share):.1f} pp (A={a_share:.1f}%, "
                f"B={b_share:.1f}%); cache warmth can skew the cache column"
            ),
        })

    if (
        side_a["model_family"]
        and side_a["model_family"] == side_b["model_family"]
        and side_a["dominant_model_id"] == side_b["dominant_model_id"]
    ):
        advisories.append({
            "kind":     "model-family-collision",
            "severity": "info",
            "message": (
                f"both sides use {side_a['dominant_model_id']!r}; ratios will "
                f"reflect run-to-run variance rather than model deltas"
            ),
        })

    if pairing["mode"] == "fingerprint" and not pairing["paired"]:
        advisories.append({
            "kind":     "no-fingerprint-matches",
            "severity": "warn",
            "message": (
                "fingerprint pairing matched 0 turns; the two sessions likely "
                "did not run the same prompts (try --pair-by ordinal)"
            ),
        })

    if side_a["turn_count"] == 0 or side_b["turn_count"] == 0:
        advisories.append({
            "kind":     "empty-side",
            "severity": "warn",
            "message": "one or both sessions have no assistant turns with usage",
        })

    return advisories


def _build_compare_summary(
    side_a: dict,
    side_b: dict,
    paired: list[dict],
    unmatched_a: list[dict],
    unmatched_b: list[dict],
) -> dict:
    """Aggregate ratios used by every compare renderer's summary strip.

    Ratios are side-total based (b/a), not mean-of-per-turn-ratios.
    Mean-of-ratios is skewed by low-input turns; side-total is the
    bottom-line number users care about (total cost delta).

    Instruction-pass rates are computed over the subset of paired turns that
    actually carry a predicate (``instruction_pass_a is not None``) so the
    denominator reflects "suite turns evaluated", not "all paired turns".
    """
    a_t = side_a["totals"]
    b_t = side_b["totals"]

    # IFEval aggregate: only count turns where a predicate ran.
    evaluated = [p for p in paired if p.get("instruction_pass_a") is not None]
    if evaluated:
        pass_a = sum(1 for p in evaluated if p["instruction_pass_a"])
        pass_b = sum(1 for p in evaluated if p["instruction_pass_b"])
        rate_a = pass_a / len(evaluated)
        rate_b = pass_b / len(evaluated)
        pass_delta_pp = 100.0 * (rate_b - rate_a)
        # Paired-samples statistics. The pairing structure (same prompt
        # evaluated by both models) makes McNemar the correct test —
        # simple two-proportion tests would ignore the pairing and
        # inflate the apparent variance.
        mcnemar_b = sum(
            1 for p in evaluated
            if p["instruction_pass_a"] and not p["instruction_pass_b"]
        )
        mcnemar_c = sum(
            1 for p in evaluated
            if not p["instruction_pass_a"] and p["instruction_pass_b"]
        )
        mcnemar_p = _mcnemar_midp(mcnemar_b, mcnemar_c)
        rate_a_ci = _wilson_ci(pass_a, len(evaluated))
        rate_b_ci = _wilson_ci(pass_b, len(evaluated))
    else:
        pass_a = pass_b = 0
        rate_a = rate_b = None
        pass_delta_pp = None
        mcnemar_b = mcnemar_c = 0
        mcnemar_p = None
        rate_a_ci = rate_b_ci = None

    # Small-N warning: below N=20 the suite has no power to resolve
    # a 10-pp shift at conventional alpha. Surface this so users don't
    # over-interpret single-prompt flips.
    _LOW_N_THRESHOLD = 20
    n_eval = len(evaluated)
    low_sample_size = 0 < n_eval < _LOW_N_THRESHOLD
    if low_sample_size:
        sample_size_note = (
            f"IFEval N={n_eval} < {_LOW_N_THRESHOLD}: a single-prompt flip "
            "(~{:.0f} pp at N={}) is within statistical noise. Treat "
            "pass-rate deltas as directional, not conclusive.".format(
                100.0 / n_eval, n_eval
            )
        )
    else:
        sample_size_note = None

    return {
        "paired_count":             len(paired),
        "unmatched_a_count":        len(unmatched_a),
        "unmatched_b_count":        len(unmatched_b),
        "input_tokens_ratio":       _safe_ratio(b_t["input"], a_t["input"]),
        "output_tokens_ratio":      _safe_ratio(b_t["output"], a_t["output"]),
        "total_tokens_ratio":       _safe_ratio(b_t["total"], a_t["total"]),
        "cost_ratio":               _safe_ratio(b_t["cost"], a_t["cost"]),
        "cache_read_share_delta_pp": (
            side_b["cache_read_share_of_input"]
            - side_a["cache_read_share_of_input"]
        ),
        "instruction_evaluated":   len(evaluated),
        "instruction_pass_a":      pass_a,
        "instruction_pass_b":      pass_b,
        "instruction_pass_rate_a": rate_a,
        "instruction_pass_rate_b": rate_b,
        "instruction_pass_delta_pp": pass_delta_pp,
        # New in v1.13.0: paired-samples statistics (additive — existing
        # consumers of the three *_rate_*/delta fields above are unaffected).
        "instruction_mcnemar_b":      mcnemar_b,
        "instruction_mcnemar_c":      mcnemar_c,
        "instruction_mcnemar_pvalue": mcnemar_p,
        "instruction_pass_rate_a_ci": rate_a_ci,
        "instruction_pass_rate_b_ci": rate_b_ci,
        "low_sample_size":            low_sample_size,
        "sample_size_note":           sample_size_note,
    }


class SuiteVersionMismatchError(ValueError):
    """Raised when compared sessions carry different compare-suite versions.

    Silent averaging across suite versions is the bug this guards against —
    a v2 prompt set and a v1 prompt set will generally produce different
    ratios for reasons unrelated to the model under test. The caller can
    opt in with ``--allow-suite-mismatch``.
    """


def _resolve_suite_versions(
    side_a_turns: list[dict],
    side_b_turns: list[dict],
    *,
    allow_mismatch: bool,
) -> tuple[set[int], set[int], list[dict]]:
    """Check sentinel-version agreement and emit advisories.

    Returns ``(versions_a, versions_b, advisories)``. Raises
    :class:`SuiteVersionMismatchError` when the two sides disagree and
    ``allow_mismatch`` is False.
    """
    va = _detect_suite_versions(side_a_turns)
    vb = _detect_suite_versions(side_b_turns)
    advisories: list[dict] = []

    if not va and not vb:
        # Neither side ran the canonical suite — not a mismatch, just
        # a non-suite comparison. Upstream still supports this for
        # ad-hoc paired sessions; the IFEval column simply stays blank.
        return va, vb, advisories

    if len(va) > 1 or len(vb) > 1:
        # A single session carrying multiple suite versions is almost
        # always a copy-paste error (user mixed prompts from different
        # suites). Flag as a warning regardless of allow_mismatch.
        advisories.append({
            "kind":     "suite-version-intrasession-mix",
            "severity": "warn",
            "message": (
                f"a session mixes multiple suite versions (A={sorted(va)}, "
                f"B={sorted(vb)}); IFEval results may be inconsistent"
            ),
        })

    if va and vb and va != vb:
        msg = (
            f"compare-suite versions differ between sides: A={sorted(va)}, "
            f"B={sorted(vb)} — re-run both sides under the same suite, or "
            f"pass --allow-suite-mismatch to proceed anyway"
        )
        if not allow_mismatch:
            raise SuiteVersionMismatchError(msg)
        advisories.append({
            "kind":     "suite-version-mismatch",
            "severity": "warn",
            "message":  msg,
        })

    return va, vb, advisories


def _build_compare_report(
    side_a_session_id: str,
    side_a_turns: list[dict],
    side_a_user_ts: list[int],
    side_b_session_id: str,
    side_b_turns: list[dict],
    side_b_user_ts: list[int],
    *,
    slug: str,
    pair_by: str = "fingerprint",
    tz_offset_hours: float = 0.0,
    tz_label: str = "UTC",
    prompt_suite: dict | None = None,
    allow_suite_mismatch: bool = False,
    effort_a: str | None = None,
    effort_b: str | None = None,
) -> dict:
    """Build a Mode-1 (controlled, session-pair) compare report.

    Returns a report dict whose ``mode`` is ``"compare"`` — the main
    renderer branches (``render_text`` etc.) delegate to the compare
    renderers in this module when they see this. Per-turn records are
    built via the main module's :func:`_build_turn_record` so column
    semantics match single-session reports.

    ``prompt_suite`` lets callers (chiefly tests) inject a predicate
    registry; production calls pass ``None`` to load the packaged suite
    from disk. A missing suite dir silently yields an empty dict — the
    compare still runs, the IFEval column stays blank.
    """
    m = _main()

    if prompt_suite is None:
        try:
            prompt_suite = _load_prompt_suite()
        except PromptSuiteError:
            # A malformed local suite shouldn't sink the compare — log
            # nothing, skip IFEval, let the user see a blank pass column.
            prompt_suite = {}

    suite_advisories: list[dict] = []
    _va, _vb, suite_advisories = _resolve_suite_versions(
        side_a_turns, side_b_turns, allow_mismatch=allow_suite_mismatch,
    )

    a_turn_records = [m._build_turn_record(i + 1, t, tz_offset_hours)
                      for i, t in enumerate(side_a_turns)]
    b_turn_records = [m._build_turn_record(i + 1, t, tz_offset_hours)
                      for i, t in enumerate(side_b_turns)]

    pairing = _pair_turns(side_a_turns, side_b_turns, mode=pair_by)

    # Map raw-turn identity to the per-side turn record so pairing output
    # (which references raw turns) can be translated back to records.
    # id() is safe here because the raw turn dicts have well-defined
    # lifetimes within this call.
    a_rec_by_raw = {id(t): r for t, r in zip(side_a_turns, a_turn_records)}
    b_rec_by_raw = {id(t): r for t, r in zip(side_b_turns, b_turn_records)}

    paired: list[dict] = []
    # P2.5: accumulate (prompt_name, "ExcType: msg") for predicates that RAISE
    # during evaluation (vs genuinely returning False). _run_predicate swallows
    # the exception to a False "fail"; this list lets us emit a [warn] after the
    # loop so a broken suite predicate isn't an invisible 0%-pass anomaly.
    predicate_errors: list[tuple[str, str]] = []
    for a_raw, b_raw in pairing["paired"]:
        a_rec = a_rec_by_raw[id(a_raw)]
        b_rec = b_rec_by_raw[id(b_raw)]
        fp_text = _user_prompt_fingerprint_text(
            a_raw.get("_preceding_user_content"))

        # IFEval wiring: look up each side's sentinel and run the suite
        # predicate against the assistant's text output. Both sides
        # ideally agree on the prompt (fingerprint pairing guarantees
        # identical user text, so sentinels match); ordinal pairing can
        # produce mismatches, which we handle by only evaluating when
        # both sentinels agree.
        a_sentinel = _primary_sentinel(
            _user_prompt_fingerprint_text(a_raw.get("_preceding_user_content")))
        b_sentinel = _primary_sentinel(
            _user_prompt_fingerprint_text(b_raw.get("_preceding_user_content")))

        suite_prompt_name: str | None = None
        instruction_pass_a: bool | None = None
        instruction_pass_b: bool | None = None
        if a_sentinel and b_sentinel and a_sentinel[1] == b_sentinel[1]:
            suite_prompt_name = a_sentinel[1]
            prompt_entry = prompt_suite.get(suite_prompt_name)
            if prompt_entry is not None:
                check_fn = prompt_entry.get("check")
                instruction_pass_a = _run_predicate(
                    check_fn, _assistant_text(a_raw),
                    prompt_name=suite_prompt_name, errors=predicate_errors)
                instruction_pass_b = _run_predicate(
                    check_fn, _assistant_text(b_raw),
                    prompt_name=suite_prompt_name, errors=predicate_errors)

        paired.append({
            "a":                   a_rec,
            "b":                   b_rec,
            "fingerprint":         _user_prompt_fingerprint(fp_text) if fp_text else None,
            "ratios":              _compute_ratios(a_rec, b_rec),
            "suite_prompt_name":   suite_prompt_name,
            "instruction_pass_a":  instruction_pass_a,
            "instruction_pass_b":  instruction_pass_b,
        })
    unmatched_a_recs = [a_rec_by_raw[id(t)] for t in pairing["unmatched_a"]]
    unmatched_b_recs = [b_rec_by_raw[id(t)] for t in pairing["unmatched_b"]]

    side_a_info = _build_side_info(
        side_a_session_id, side_a_turns, side_a_user_ts,
        a_turn_records, tz_offset_hours,
        effort=effort_a,
    )
    side_b_info = _build_side_info(
        side_b_session_id, side_b_turns, side_b_user_ts,
        b_turn_records, tz_offset_hours,
        effort=effort_b,
    )
    # P2.5: surface predicates that raised (scored as False fails) once, de-duped
    # by (prompt, error) so one broken check doesn't spam per turn. Mirrors the
    # unknown-model / fast-mode stderr advisories — a 0%-pass anomaly is now
    # attributable to a broken suite predicate instead of looking like a model fail.
    if predicate_errors:
        seen_pe = sorted(set(predicate_errors))
        details = "; ".join(f"{name} ({err})" for name, err in seen_pe)
        print(f"[warn] {len(seen_pe)} IFEval predicate(s) raised during evaluation and "
              f"were scored as failures (not genuine fails): {details}. "
              f"Check the suite file.", file=sys.stderr)
    advisories = _build_advisories(side_a_info, side_b_info, pairing)
    advisories.extend(suite_advisories)
    summary = _build_compare_summary(
        side_a_info, side_b_info, paired, unmatched_a_recs, unmatched_b_recs,
    )
    return {
        "mode":            "compare",
        "compare_mode":    "controlled",
        "slug":            slug,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "tz_offset_hours": tz_offset_hours,
        "tz_label":        tz_label,
        "pair_by":         pair_by,
        "side_a":          side_a_info,
        "side_b":          side_b_info,
        "paired":          paired,
        "unmatched_a":     unmatched_a_recs,
        "unmatched_b":     unmatched_b_recs,
        "warnings":        pairing["warnings"],
        "advisories":      advisories,
        "summary":         summary,
    }


def _build_aggregate_advisories(side_a: dict, side_b: dict) -> list[dict]:
    """Mode-2-specific advisories.

    Observational reports need every Mode-1 warning *except* the two
    that assume paired turns (``no-fingerprint-matches`` is pairing-
    specific) and always carry the banner that reminds users this is a
    drift summary — the ratios conflate tokenizer shift with prompt-
    distribution shift between the two families.
    """
    advisories: list[dict] = [{
        "kind":     "observational-not-controlled",
        "severity": "warn",
        "message": (
            "observational compare — ratios reflect aggregate usage across "
            "differing prompt distributions. For attribution (tokenizer vs "
            "prompt mix), run the controlled suite via "
            "'session-metrics --compare-prep'"
        ),
    }]

    if side_a["context_tier"] != side_b["context_tier"]:
        a_tier = side_a["context_tier"] or "default"
        b_tier = side_b["context_tier"] or "default"
        advisories.append({
            "kind":     "context-tier-mismatch",
            "severity": "warn",
            "message": (
                f"context-tier mismatch: side A is {a_tier!r}, side B is "
                f"{b_tier!r} — any ratio conflates tokenizer + context-window"
            ),
        })

    a_share = side_a["cache_read_share_of_input"]
    b_share = side_b["cache_read_share_of_input"]
    if abs(a_share - b_share) > _CACHE_SHARE_DRIFT_PP:
        advisories.append({
            "kind":     "cache-share-drift",
            "severity": "warn",
            "message": (
                f"cache-read share differs by "
                f"{abs(a_share - b_share):.1f} pp (A={a_share:.1f}%, "
                f"B={b_share:.1f}%); cache warmth can skew the cache column"
            ),
        })

    if (
        side_a["model_family"]
        and side_a["model_family"] == side_b["model_family"]
    ):
        advisories.append({
            "kind":     "model-family-collision",
            "severity": "info",
            "message": (
                f"both sides are family {side_a['model_family']!r}; this is "
                f"an A/B within one model, not a cross-model compare"
            ),
        })

    if side_a["turn_count"] == 0 or side_b["turn_count"] == 0:
        advisories.append({
            "kind":     "empty-side",
            "severity": "warn",
            "message": (
                "one side has no assistant turns with usage — "
                f"A={side_a['turn_count']}, B={side_b['turn_count']}"
            ),
        })

    return advisories


def _build_aggregate_summary(side_a: dict, side_b: dict) -> dict:
    """Side-total ratios for the observational report's summary strip.

    Identical keys to :func:`_build_compare_summary` so renderers can
    share the ratio-printing codepath, but without the paired/unmatched
    counters (no pairing happens in Mode 2). The ``avg_*_ratio`` keys
    surface the aggregate-only averages that only Mode 2 can populate.
    """
    a_t = side_a["totals"]
    b_t = side_b["totals"]
    return {
        "input_tokens_ratio":  _safe_ratio(b_t["input"], a_t["input"]),
        "output_tokens_ratio": _safe_ratio(b_t["output"], a_t["output"]),
        "total_tokens_ratio":  _safe_ratio(b_t["total"], a_t["total"]),
        "cost_ratio":          _safe_ratio(b_t["cost"], a_t["cost"]),
        "cache_read_share_delta_pp": (
            side_b["cache_read_share_of_input"]
            - side_a["cache_read_share_of_input"]
        ),
        "avg_input_per_prompt_ratio": _safe_ratio(
            side_b["avg_input_tokens_per_prompt"],
            side_a["avg_input_tokens_per_prompt"],
        ),
        "avg_output_per_turn_ratio": _safe_ratio(
            side_b["avg_output_tokens_per_turn"],
            side_a["avg_output_tokens_per_turn"],
        ),
        "tool_calls_per_turn_ratio": _safe_ratio(
            side_b["tool_calls_per_turn"],
            side_a["tool_calls_per_turn"],
        ),
    }


def _build_compare_aggregate_report(
    side_a_sessions: list[tuple[str, list[dict], list[int]]],
    side_b_sessions: list[tuple[str, list[dict], list[int]]],
    *,
    slug: str,
    tz_offset_hours: float = 0.0,
    tz_label: str = "UTC",
    effort_a: str | None = None,
    effort_b: str | None = None,
) -> dict:
    """Build a Mode-2 (observational, project-aggregate) compare report.

    ``side_a_sessions`` / ``side_b_sessions`` carry
    ``(session_id, raw_turns, user_timestamps)`` tuples per session.
    Per-turn records are built via the main module's
    :func:`_build_turn_record` — column semantics match single-session
    and controlled-compare reports.

    The returned dict has ``mode="compare"``, ``compare_mode=
    "observational"``, no ``paired``/``unmatched`` fields (pairing
    isn't meaningful when prompts differ across sessions), and the
    same header/summary/advisory/totals shape Mode 1 uses — so
    renderers can reuse most of the Mode 1 helpers.

    ``effort_a`` / ``effort_b`` annotate each side with the pinned
    reasoning level when known (threaded through from compare-run);
    ``None`` (the default) leaves the side unannotated, which is the
    common case for Mode 2 aggregates captured outside the orchestrator.
    """
    m = _main()

    def _per_side(sessions, effort):
        prepared = []
        for sid, raw_turns, user_ts in sessions:
            records = [m._build_turn_record(i + 1, t, tz_offset_hours)
                       for i, t in enumerate(raw_turns)]
            prepared.append((sid, raw_turns, user_ts, records))
        return _build_aggregate_side_info(
            prepared, tz_offset_hours, effort=effort,
        )

    side_a_info = _per_side(side_a_sessions, effort_a)
    side_b_info = _per_side(side_b_sessions, effort_b)
    advisories = _build_aggregate_advisories(side_a_info, side_b_info)
    summary = _build_aggregate_summary(side_a_info, side_b_info)
    return {
        "mode":            "compare",
        "compare_mode":    "observational",
        "slug":            slug,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "tz_offset_hours": tz_offset_hours,
        "tz_label":        tz_label,
        "side_a":          side_a_info,
        "side_b":          side_b_info,
        "warnings":        [],
        "advisories":      advisories,
        "summary":         summary,
    }


# ---------------------------------------------------------------------------
# Prompt suite (Phase 4) — sentinel detection + predicate loader
# ---------------------------------------------------------------------------

# Version of the canonical prompt suite shipped with this release. Bump when
# prompt bodies or predicates change in a way that would skew ratios across
# older vs newer captures — the suite-version-mismatch refusal keys off this
# integer so old captures don't get silently averaged against new ones.
_SUITE_VERSION = 1

# Directory the prompt files live in. Resolved relative to this script so the
# suite loads correctly whether the skill is running from the dev repo, the
# plugin cache, or a project-local copy.
_PROMPT_SUITE_DIR = (
    Path(__file__).resolve().parent.parent
    / "references" / "model-compare" / "prompts"
)

# User-supplied extra prompts directory. Files here are merged on top of the
# packaged suite automatically — no CLI flags required. Supports "lite" format
# (plain text, no frontmatter needed). Only applies when suite_dir is None
# (i.e. not overridden by --compare-prompts).
_EXTRAS_DIR = Path.home() / ".session-metrics" / "prompts"

# Sentinel regex: matches ``[session-metrics:compare-suite:v<N>:prompt=<name>]``
# anywhere in a user prompt. Plain brackets (not HTML comments) because HTML
# comments get mangled in some Claude-Code paste paths; the bracket form
# survives CR/LF normalization and markdown quoting round-trips.
_SENTINEL_RE = re.compile(
    r"\[session-metrics:compare-suite:v(\d+):prompt=([a-z0-9_]+)\]"
)


def _extract_sentinels(text: str) -> list[tuple[int, str]]:
    """All ``(version, prompt_name)`` sentinels in a user prompt.

    Returns every match so we can detect the rare case of multiple sentinels
    pasted into one prompt (malformed capture — caller refuses). Returns an
    empty list for non-suite prompts, which the predicate-eval path skips.
    """
    return [(int(v), name) for v, name in _SENTINEL_RE.findall(text or "")]


def _primary_sentinel(text: str) -> tuple[int, str] | None:
    """First sentinel in the text, or None.

    Used when the caller only needs to know which suite prompt (if any) a
    turn belongs to — multi-sentinel anomalies are surfaced separately by
    :func:`_extract_sentinels`.
    """
    hits = _extract_sentinels(text)
    return hits[0] if hits else None


def _parse_simple_yaml(text: str) -> dict:
    """Minimal ``key: value`` YAML parser for prompt-file frontmatter.

    Only supports flat ``key: value`` lines (no nesting, no lists, no
    multi-line strings). Values are stripped of wrapping single / double
    quotes. Comment lines starting with ``#`` are ignored.

    Staying stdlib-only is a hard constraint for this skill, so we don't
    import PyYAML — and the frontmatter schema is under our control, which
    keeps this parser honest.
    """
    out: dict = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if ":" not in s:
            continue
        key, _, value = s.partition(":")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        out[key] = value
    return out


# Fenced predicate block: four-backtick fence prefixed by ``python``. Chose a
# 4-tick fence because prompts themselves routinely contain 3-tick Python /
# diff / CSV snippets — a 3-tick predicate fence would collide with those.
_PREDICATE_MARKER = "<!-- PREDICATE -->"
_PREDICATE_FENCE_RE = re.compile(
    r"````python\s*\n(.*?)\n````",
    flags=re.DOTALL,
)


class PromptSuiteError(ValueError):
    """Raised when a prompt file is malformed or the suite can't load."""


def _parse_prompt_file(path: Path) -> dict:
    """Parse one prompt file into ``{name, metadata, body, check}``.

    Two formats are accepted:

    **Full format** (packaged suite + power-user custom prompts):

    - YAML-like frontmatter between ``---`` fences at the top.
    - Prompt body (what the user pastes into Claude Code).
    - A ``<!-- PREDICATE -->`` HTML-comment marker.
    - A 4-backtick ``python`` fenced block defining ``check(text) -> bool``.

    **Lite format** (user extras in ``~/.session-metrics/prompts/``):

    - Plain text prompt body only — no frontmatter, no predicate required.
    - ``name`` is derived from the filename stem (numeric prefix stripped).
    - A ``user-suite`` sentinel is auto-injected so the body carries a
      fingerprint without triggering the compare-suite version checker.
    - ``check`` is always ``None`` (ratio/token data only; no IFEval column).

    ``check`` may be ``None`` (prompt intentionally has no IFEval predicate
    — see ``05_tool_heavy_task.md``). The returned dict carries the body
    *without* the predicate section so ``--compare-prep`` can paste the
    body directly. Predicates are executed once at load time in an
    isolated namespace so each prompt's ``check`` doesn't pollute the next.
    """
    raw = path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, flags=re.DOTALL)
    if not fm_match:
        # A file that starts with '---' but doesn't match the full fence pattern
        # is a malformed full-format file (missing closing fence, etc.).
        if raw.lstrip().startswith("---"):
            raise PromptSuiteError(
                f"{path.name}: malformed YAML frontmatter (expected opening '---' "
                f"fence followed by fields and a closing '---' fence)"
            )
        # Lite format: plain text prompt — derive name from filename, inject sentinel.
        name = re.sub(r"^[0-9_]+", "", path.stem)
        name = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
        if not name:
            raise PromptSuiteError(
                f"{path.name}: cannot derive a prompt name from the filename stem"
            )
        sentinel = f"[session-metrics:user-suite:v1:prompt={name}]"
        body = f"{sentinel}\n\n{raw.strip()}"
        return {
            "name":     name,
            "metadata": {"description": f"user prompt: {name}"},
            "body":     body,
            "check":    None,
            "path":     path,
        }
    fm_text, rest = fm_match.groups()
    metadata = _parse_simple_yaml(fm_text)
    name = metadata.get("name") or path.stem.lstrip("0123456789_")
    if not name:
        raise PromptSuiteError(f"{path.name}: frontmatter missing 'name' field")

    if _PREDICATE_MARKER in rest:
        body, _, pred_block = rest.partition(_PREDICATE_MARKER)
    else:
        body, pred_block = rest, ""

    check_fn = None
    if pred_block:
        mm = _PREDICATE_FENCE_RE.search(pred_block)
        if mm:
            src = mm.group(1)
            ns: dict = {}
            try:
                exec(src, ns)   # trusted skill-shipped code — no sandbox
            except Exception as exc:  # noqa: BLE001
                raise PromptSuiteError(
                    f"{path.name}: predicate failed to exec — {exc!r}"
                ) from exc
            candidate = ns.get("check")
            if candidate is not None and not callable(candidate):
                raise PromptSuiteError(
                    f"{path.name}: 'check' must be callable or None"
                )
            check_fn = candidate

    return {
        "name":     name,
        "metadata": metadata,
        "body":     body.strip("\n"),
        "check":    check_fn,
        "path":     path,
    }


def _load_prompt_suite(
    suite_dir: Path | None = None,
) -> dict[str, dict]:
    """Return ``{prompt_name: parsed_dict}`` for every ``.md`` in the suite dir.

    Falls back to the packaged suite dir when ``suite_dir`` is None. Files are
    sorted by filename so numeric prefixes (``01_``, ``02_``) control the
    canonical order the suite emits in ``--compare-prep`` output.

    When ``suite_dir`` is ``None`` (default), also auto-merges any ``.md`` files
    found in ``_EXTRAS_DIR`` (``~/.session-metrics/prompts/``). Extras support
    the lite format (plain text, no frontmatter). This merge is skipped when an
    explicit ``suite_dir`` override is provided, so ``--compare-prompts DIR``
    behaviour is unchanged.
    """
    d = suite_dir if suite_dir is not None else _PROMPT_SUITE_DIR
    if not d.exists() or not d.is_dir():
        return {}
    suite: dict[str, dict] = {}
    for path in sorted(d.glob("*.md")):
        parsed = _parse_prompt_file(path)
        if parsed["name"] in suite:
            raise PromptSuiteError(
                f"duplicate prompt name {parsed['name']!r} in {d}"
            )
        suite[parsed["name"]] = parsed

    # Auto-merge user extras only when using the packaged default suite.
    # Callers passing an explicit suite_dir get exactly what they asked for.
    if suite_dir is None and _EXTRAS_DIR.exists() and _EXTRAS_DIR.is_dir():
        for path in sorted(_EXTRAS_DIR.glob("*.md")):
            parsed = _parse_prompt_file(path)
            if parsed["name"] in suite:
                raise PromptSuiteError(
                    f"user prompt name {parsed['name']!r} in {_EXTRAS_DIR} "
                    f"collides with a built-in prompt name. "
                    f"Rename the file (e.g. my_{parsed['name']}.md) to fix this."
                )
            parsed["metadata"]["user_prompt"] = True
            suite[parsed["name"]] = parsed

    return suite


def _run_compare_list_prompts(suite: dict[str, dict]) -> None:
    """Print the active prompt suite to stdout and exit.

    Shows which prompts will run on the next ``--compare-run``, their source
    (built-in vs user), predicate status, and total inference-call count.
    """
    builtin = [(n, e) for n, e in suite.items() if not e["metadata"].get("user_prompt")]
    user    = [(n, e) for n, e in suite.items() if e["metadata"].get("user_prompt")]
    total   = len(suite)

    if user:
        header = (
            f"Suite: {len(builtin)} built-in + {len(user)} user "
            f"= {total} prompt(s) × 2 models = {2 * total} calls"
        )
    else:
        header = f"Suite: {total} built-in prompt(s) × 2 models = {2 * total} calls"
    print(header)
    print()

    col_w = max((len(n) for n in suite), default=20) + 2
    for name, entry in suite.items():
        is_user   = entry["metadata"].get("user_prompt", False)
        marker    = "+" if is_user else "·"
        has_pred  = "yes" if entry.get("check") is not None else "no "
        desc      = entry["metadata"].get("description", "")
        src       = str(entry["path"].parent) if is_user else "(built-in)"
        print(f"  {marker} {name:<{col_w}} predicate: {has_pred}   {src}")
        if desc and not desc.startswith("user prompt:"):
            print(f"    {desc}")

    print()
    print("· = built-in   + = your prompts  (from ~/.session-metrics/prompts/)")


def _assistant_text(raw_turn: dict) -> str:
    """Concatenate the assistant's text-block content for one turn.

    Content blocks that aren't ``text`` (``thinking``, ``tool_use``) are
    skipped — IFEval predicates are structural checks on the model's
    natural-language output, not its internal reasoning or tool calls.
    """
    msg = raw_turn.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            t = block.get("text") or ""
            if t:
                parts.append(t)
    return "".join(parts).strip()


def _detect_suite_versions(raw_turns: list[dict]) -> set[int]:
    """All sentinel versions found across a session's user prompts."""
    versions: set[int] = set()
    for t in raw_turns:
        text = _user_prompt_fingerprint_text(t.get("_preceding_user_content"))
        for v, _name in _extract_sentinels(text):
            versions.add(v)
    return versions


def _run_predicate(check_fn, text: str, *, prompt_name: str | None = None,
                   errors: list | None = None) -> bool | None:
    """Evaluate a predicate safely — any exception collapses to ``False``.

    Returns ``None`` when ``check_fn`` is ``None`` (prompt has no predicate,
    e.g. the tool-heavy task). A predicate that raises is treated as a
    fail, not a crash, so one broken check doesn't sink a whole compare run.

    When ``errors`` is supplied, a predicate that *raises* also records
    ``(prompt_name, "<ExcType>: <msg>")`` into it. That lets the caller surface
    a [warn] distinguishing a genuine fail (predicate returned False) from a
    broken suite predicate (predicate raised) — otherwise a typo'd or import-
    broken check silently scores 0% across every model with no diagnostic.
    """
    if check_fn is None:
        return None
    try:
        return bool(check_fn(text))
    except Exception as exc:  # noqa: BLE001
        if errors is not None:
            errors.append((prompt_name or "<unknown>", f"{type(exc).__name__}: {exc}"))
        return False


# ---------------------------------------------------------------------------
# Compare renderers (text / md / json / csv)
# ---------------------------------------------------------------------------

def _fmt_ratio(value: float | None, precision: int = 2) -> str:
    """Format a b/a ratio like ``1.32×`` — or ``n/a`` when undefined."""
    if value is None:
        return "n/a"
    return f"{value:.{precision}f}×"


def _fmt_delta_pp(value: float, precision: int = 1) -> str:
    """Format a percentage-point delta with sign — e.g. ``+4.2 pp``."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{precision}f} pp"


def _fmt_pass(value: bool | None) -> str:
    """Format an IFEval pass/fail cell — ``✓``, ``✗``, or em-dash."""
    if value is None:
        return "—"
    return "✓" if value else "✗"


def _fmt_cost_delta(side_a: dict, side_b: dict) -> str:
    """Render the cost delta as an absolute-dollar string.

    Always shows side B minus side A (so a positive value means B cost
    more). Used by both the text and Markdown summary strips.
    """
    a_cost = side_a["totals"].get("cost", 0.0) or 0.0
    b_cost = side_b["totals"].get("cost", 0.0) or 0.0
    delta = b_cost - a_cost
    sign = "+" if delta >= 0 else ""
    return f"{sign}${delta:.4f}"


def _side_label(side: dict, fallback: str) -> str:
    """Short human-readable label for a compare side.

    Prefers the session-id prefix; falls back to the model family when
    the id is empty (Mode-2 aggregates will exercise this later).
    """
    sid = side.get("session_id") or ""
    if sid:
        return f"{sid[:8]}…"
    family = side.get("model_family") or ""
    return family or fallback


def _fmt_effort_suffix(side: dict) -> str:
    """Return ``" effort=<level>"`` when the side has a pinned reasoning
    level, or an empty string otherwise.

    Renderers concatenate this at the end of the model banner so the
    output is self-descriptive for compare-run captures while staying
    silent on Mode 2 / arbitrary-JSONL inputs that never ran through
    the orchestrator (effort is ``None`` there).
    """
    effort = side.get("effort") or ""
    return f" effort={effort}" if effort else ""


def _any_effort(report: dict) -> bool:
    """True when either side of the compare report carries a pinned
    reasoning effort. Renderers use this to decide whether to emit an
    Effort column / row — avoids rendering an empty cell on every
    legacy / Mode 2 report that will never set the field.
    """
    return bool(
        (report.get("side_a") or {}).get("effort")
        or (report.get("side_b") or {}).get("effort")
    )


def render_compare_text(report: dict) -> str:
    """Render the compare report as plain-text for stdout.

    Dispatches on ``compare_mode``: observational (Mode 2) and
    controlled (Mode 1) share the summary-line vocabulary but differ
    on per-turn table vs aggregate cards.
    """
    if report.get("compare_mode") == "observational":
        return _render_aggregate_text(report)
    return _render_controlled_text(report)


def _render_controlled_text(report: dict) -> str:
    """Render the Mode-1 compare report as plain-text for stdout."""
    out = io.StringIO()

    def p(*args, **kw):
        print(*args, **kw, file=out)

    a = report["side_a"]
    b = report["side_b"]
    s = report["summary"]
    tz_label = report.get("tz_label", "UTC")

    p("=" * 82)
    p(f"COMPARE (controlled)  slug={report['slug']}  pair-by={report['pair_by']}  tz={tz_label}")
    p("=" * 82)
    p(f"  A  {_side_label(a, 'a'):<14} model={a['dominant_model_id'] or '?':<28} "
      f"turns={a['turn_count']:<4} cost=${a['totals']['cost']:.4f}"
      f"{_fmt_effort_suffix(a)}")
    p(f"  B  {_side_label(b, 'b'):<14} model={b['dominant_model_id'] or '?':<28} "
      f"turns={b['turn_count']:<4} cost=${b['totals']['cost']:.4f}"
      f"{_fmt_effort_suffix(b)}")
    p()

    if report["advisories"]:
        p("ADVISORIES")
        for adv in report["advisories"]:
            tag = "[WARN]" if adv["severity"] == "warn" else "[info]"
            p(f"  {tag} {adv['message']}")
        p()

    if report["warnings"]:
        p("PAIRING WARNINGS")
        for w in report["warnings"]:
            p(f"  - {w}")
        p()

    p("SUMMARY (B vs A)")
    p(f"  input-token ratio   : {_fmt_ratio(s['input_tokens_ratio'])}")
    p(f"  output-token ratio  : {_fmt_ratio(s['output_tokens_ratio'])}")
    p(f"  total-token ratio   : {_fmt_ratio(s['total_tokens_ratio'])}")
    p(f"  cost ratio          : {_fmt_ratio(s['cost_ratio'])}  "
      f"(abs delta {_fmt_cost_delta(a, b)})")
    p(f"  cache-read share Δ  : {_fmt_delta_pp(s['cache_read_share_delta_pp'])}")
    p(f"  paired turns        : {s['paired_count']} "
      f"(unmatched A={s['unmatched_a_count']}, B={s['unmatched_b_count']})")
    if s.get("instruction_evaluated"):
        p(f"  IFEval pass         : "
          f"A {s['instruction_pass_a']}/{s['instruction_evaluated']} "
          f"({(s['instruction_pass_rate_a'] or 0) * 100:.0f}%), "
          f"B {s['instruction_pass_b']}/{s['instruction_evaluated']} "
          f"({(s['instruction_pass_rate_b'] or 0) * 100:.0f}%), "
          f"Δ {_fmt_delta_pp(s['instruction_pass_delta_pp'] or 0)}")
        ci_a = s.get("instruction_pass_rate_a_ci")
        ci_b = s.get("instruction_pass_rate_b_ci")
        if ci_a and ci_b:
            p(f"  IFEval 95% CI       : "
              f"A [{ci_a[0] * 100:.0f}–{ci_a[1] * 100:.0f}%], "
              f"B [{ci_b[0] * 100:.0f}–{ci_b[1] * 100:.0f}%] (Wilson)")
        pval = s.get("instruction_mcnemar_pvalue")
        if pval is not None:
            p(f"  IFEval McNemar      : "
              f"p={pval:.3f} "
              f"(b={s['instruction_mcnemar_b']} A✓B✗, "
              f"c={s['instruction_mcnemar_c']} A✗B✓, "
              f"mid-p two-sided)")
        if s.get("low_sample_size") and s.get("sample_size_note"):
            p(f"  [!] {s['sample_size_note']}")
    p()

    if report["paired"]:
        has_instruction = any(
            row.get("instruction_pass_a") is not None
            or row.get("instruction_pass_b") is not None
            for row in report["paired"]
        )
        p("PAIRED TURNS (A → B)")
        extras = "  A✓  B✓  prompt" if has_instruction else ""
        hdr = (f"  {'#':>3}  {'A input':>8} {'B input':>8} {'Δin':>6}   "
               f"{'A out':>7} {'B out':>7} {'Δout':>6}   "
               f"{'A cost':>9} {'B cost':>9} {'Δcost':>6}{extras}")
        p(hdr)
        p("  " + "-" * (len(hdr) - 2))
        for i, row in enumerate(report["paired"], 1):
            ar, br, r = row["a"], row["b"], row["ratios"]
            extra_cols = ""
            if has_instruction:
                extra_cols = (
                    f"  {_fmt_pass(row.get('instruction_pass_a'))}  "
                    f"{_fmt_pass(row.get('instruction_pass_b'))}  "
                    f"{row.get('suite_prompt_name') or '—'}"
                )
            p(f"  {i:>3}  "
              f"{ar['input_tokens']:>8} {br['input_tokens']:>8} {_fmt_ratio(r['input_tokens']):>6}   "
              f"{ar['output_tokens']:>7} {br['output_tokens']:>7} {_fmt_ratio(r['output_tokens']):>6}   "
              f"${ar['cost_usd']:>8.4f} ${br['cost_usd']:>8.4f} {_fmt_ratio(r['cost_usd']):>6}"
              f"{extra_cols}")
        p()

    if report["unmatched_a"] or report["unmatched_b"]:
        p("UNMATCHED")
        p(f"  A-only turns: {len(report['unmatched_a'])}")
        p(f"  B-only turns: {len(report['unmatched_b'])}")
        p()

    p("NOTE  compare mode is a tokenizer/behaviour study, not a quality score.")
    p("      cost deltas with identical pricing are tokenizer-driven.")
    return out.getvalue()


def render_compare_md(report: dict) -> str:
    """Render the compare report as GitHub-flavored Markdown.

    Observational (Mode 2) swaps the per-turn table for aggregate cards;
    otherwise renderer shape is identical.
    """
    if report.get("compare_mode") == "observational":
        return _render_aggregate_md(report)
    return _render_controlled_md(report)


def _render_controlled_md(report: dict) -> str:
    """Render the Mode-1 compare report as GitHub-flavored Markdown."""
    out = io.StringIO()

    def p(*args, **kw):
        print(*args, **kw, file=out)

    a = report["side_a"]
    b = report["side_b"]
    s = report["summary"]

    p(f"# Model Compare — {report['slug']}")
    p()
    p(f"- Mode: **{report['compare_mode']}**")
    p(f"- Pair-by: `{report['pair_by']}`")
    p(f"- Generated: {report['generated_at']}")
    p()
    p("## Sides")
    p()
    has_effort = _any_effort(report)
    if has_effort:
        p("| Side | Session | Model | Effort | Turns | Cost |")
        p("|------|---------|-------|--------|------:|-----:|")
    else:
        p("| Side | Session | Model | Turns | Cost |")
        p("|------|---------|-------|------:|-----:|")
    for tag, side in (("A", a), ("B", b)):
        if has_effort:
            effort_cell = f"`{side.get('effort')}`" if side.get("effort") else "—"
            p(f"| {tag} | `{_side_label(side, tag.lower())}` | "
              f"`{side['dominant_model_id'] or '?'}` | "
              f"{effort_cell} | "
              f"{side['turn_count']} | ${side['totals']['cost']:.4f} |")
        else:
            p(f"| {tag} | `{_side_label(side, tag.lower())}` | "
              f"`{side['dominant_model_id'] or '?'}` | "
              f"{side['turn_count']} | ${side['totals']['cost']:.4f} |")
    p()

    if report["advisories"]:
        p("## Advisories")
        p()
        for adv in report["advisories"]:
            tag = "⚠️" if adv["severity"] == "warn" else "ℹ️"
            p(f"- {tag} {adv['message']}")
        p()

    if report["warnings"]:
        p("## Pairing warnings")
        p()
        for w in report["warnings"]:
            p(f"- {w}")
        p()

    p("## Summary (B vs A)")
    p()
    p("| Metric | Value |")
    p("|--------|------:|")
    p(f"| Input-token ratio | {_fmt_ratio(s['input_tokens_ratio'])} |")
    p(f"| Output-token ratio | {_fmt_ratio(s['output_tokens_ratio'])} |")
    p(f"| Total-token ratio | {_fmt_ratio(s['total_tokens_ratio'])} |")
    p(f"| Cost ratio | {_fmt_ratio(s['cost_ratio'])} |")
    p(f"| Cost Δ (absolute) | {_fmt_cost_delta(a, b)} |")
    p(f"| Cache-read share Δ | {_fmt_delta_pp(s['cache_read_share_delta_pp'])} |")
    p(f"| Paired turns | {s['paired_count']} "
      f"(unmatched A={s['unmatched_a_count']}, B={s['unmatched_b_count']}) |")
    if s.get("instruction_evaluated"):
        p(f"| IFEval pass (A) | "
          f"{s['instruction_pass_a']}/{s['instruction_evaluated']} "
          f"({(s['instruction_pass_rate_a'] or 0) * 100:.0f}%) |")
        p(f"| IFEval pass (B) | "
          f"{s['instruction_pass_b']}/{s['instruction_evaluated']} "
          f"({(s['instruction_pass_rate_b'] or 0) * 100:.0f}%) |")
        p(f"| IFEval Δ | {_fmt_delta_pp(s['instruction_pass_delta_pp'] or 0)} |")
        ci_a = s.get("instruction_pass_rate_a_ci")
        ci_b = s.get("instruction_pass_rate_b_ci")
        if ci_a and ci_b:
            p(f"| IFEval 95% CI (A) | "
              f"[{ci_a[0] * 100:.0f}–{ci_a[1] * 100:.0f}%] (Wilson) |")
            p(f"| IFEval 95% CI (B) | "
              f"[{ci_b[0] * 100:.0f}–{ci_b[1] * 100:.0f}%] (Wilson) |")
        pval = s.get("instruction_mcnemar_pvalue")
        if pval is not None:
            p(f"| IFEval McNemar p | "
              f"p={pval:.3f} "
              f"(b={s['instruction_mcnemar_b']}, "
              f"c={s['instruction_mcnemar_c']}, mid-p) |")
    if s.get("low_sample_size") and s.get("sample_size_note"):
        p()
        p(f"> **Low sample size.** {s['sample_size_note']}")
    p()

    if report["paired"]:
        has_instruction = any(
            row.get("instruction_pass_a") is not None
            or row.get("instruction_pass_b") is not None
            for row in report["paired"]
        )
        p("## Paired turns")
        p()
        if has_instruction:
            p("| # | A input | B input | Δ input | A output | B output | Δ output | "
              "A cost | B cost | Δ cost | A✓ | B✓ | Prompt |")
            p("|--:|--------:|--------:|--------:|---------:|---------:|---------:|"
              "-------:|-------:|-------:|:--:|:--:|:-------|")
        else:
            p("| # | A input | B input | Δ input | A output | B output | Δ output | "
              "A cost | B cost | Δ cost |")
            p("|--:|--------:|--------:|--------:|---------:|---------:|---------:|"
              "-------:|-------:|-------:|")
        for i, row in enumerate(report["paired"], 1):
            ar, br, r = row["a"], row["b"], row["ratios"]
            tail = ""
            if has_instruction:
                tail = (
                    f" {_fmt_pass(row.get('instruction_pass_a'))} | "
                    f"{_fmt_pass(row.get('instruction_pass_b'))} | "
                    f"{row.get('suite_prompt_name') or '—'} |"
                )
            p(f"| {i} | {ar['input_tokens']} | {br['input_tokens']} | "
              f"{_fmt_ratio(r['input_tokens'])} | "
              f"{ar['output_tokens']} | {br['output_tokens']} | "
              f"{_fmt_ratio(r['output_tokens'])} | "
              f"${ar['cost_usd']:.4f} | ${br['cost_usd']:.4f} | "
              f"{_fmt_ratio(r['cost_usd'])} |{tail}")
        p()

    return out.getvalue()


def render_compare_json(report: dict) -> str:
    """Dump the compare report as indented JSON.

    No transforms needed — the compare report is already JSON-safe
    (no raw epoch-seconds lists; timestamps are ISO-8601 strings).
    Shape differs between Mode 1 (paired/unmatched) and Mode 2
    (aggregate) — consumers should branch on ``compare_mode``.
    """
    return json.dumps(report, indent=2)


def render_compare_csv(report: dict) -> str:
    """Render the compare report as CSV.

    Dispatches on ``compare_mode`` — Mode 1 emits a paired-turn table
    plus summary/ratios blocks; Mode 2 emits a single-row per-side
    aggregate table plus the same summary/ratios blocks.
    """
    if report.get("compare_mode") == "observational":
        return _render_aggregate_csv(report)
    return _render_controlled_csv(report)


def _render_controlled_csv(report: dict) -> str:
    """Render the Mode-1 compare report as CSV.

    Layout:

    - Header row + one row per paired turn with A/B columns and ratios.
    - Blank row, then a ``# SUMMARY`` section with side-level totals.
    - Blank row, then a ``# ADVISORIES`` section (empty if none).
    - Blank row, then a ``# UNMATCHED`` section noting counts per side.
    """
    out = io.StringIO()
    w = csv_mod.writer(out)
    w.writerow([
        "pair_index", "fingerprint", "suite_prompt_name",
        "a_model", "a_input_tokens", "a_output_tokens",
        "a_cache_read_tokens", "a_cache_write_tokens",
        "a_total_tokens", "a_cost_usd", "a_instruction_pass",
        "b_model", "b_input_tokens", "b_output_tokens",
        "b_cache_read_tokens", "b_cache_write_tokens",
        "b_total_tokens", "b_cost_usd", "b_instruction_pass",
        "input_ratio", "output_ratio", "total_ratio", "cost_ratio",
    ])

    def _pass_cell(v):
        if v is None:
            return ""
        return "True" if v else "False"

    for i, row in enumerate(report["paired"], 1):
        ar, br, r = row["a"], row["b"], row["ratios"]
        w.writerow([
            i, row.get("fingerprint") or "", row.get("suite_prompt_name") or "",
            ar["model"], ar["input_tokens"], ar["output_tokens"],
            ar["cache_read_tokens"], ar["cache_write_tokens"],
            ar["total_tokens"], f"{ar['cost_usd']:.6f}",
            _pass_cell(row.get("instruction_pass_a")),
            br["model"], br["input_tokens"], br["output_tokens"],
            br["cache_read_tokens"], br["cache_write_tokens"],
            br["total_tokens"], f"{br['cost_usd']:.6f}",
            _pass_cell(row.get("instruction_pass_b")),
            "" if r["input_tokens"]  is None else f"{r['input_tokens']:.4f}",
            "" if r["output_tokens"] is None else f"{r['output_tokens']:.4f}",
            "" if r["total_tokens"]  is None else f"{r['total_tokens']:.4f}",
            "" if r["cost_usd"]      is None else f"{r['cost_usd']:.4f}",
        ])

    s = report["summary"]
    a = report["side_a"]
    b = report["side_b"]
    w.writerow([])
    w.writerow(["# SUMMARY"])
    w.writerow(["side", "session_id", "model_family", "context_tier", "effort",
                "turn_count", "input", "output", "cache_read", "cache_write",
                "total_tokens", "cost_usd", "cache_read_share_pct"])
    for tag, side in (("A", a), ("B", b)):
        t = side["totals"]
        w.writerow([
            tag, side["session_id"], side["model_family"], side["context_tier"],
            side.get("effort") or "",
            side["turn_count"], t["input"], t["output"],
            t["cache_read"], t["cache_write"], t["total"],
            f"{t['cost']:.6f}", f"{side['cache_read_share_of_input']:.2f}",
        ])
    w.writerow([])
    w.writerow(["# RATIOS (B vs A)"])
    w.writerow(["metric", "value"])
    w.writerow(["input_tokens_ratio",
                "" if s["input_tokens_ratio"]  is None else f"{s['input_tokens_ratio']:.4f}"])
    w.writerow(["output_tokens_ratio",
                "" if s["output_tokens_ratio"] is None else f"{s['output_tokens_ratio']:.4f}"])
    w.writerow(["total_tokens_ratio",
                "" if s["total_tokens_ratio"]  is None else f"{s['total_tokens_ratio']:.4f}"])
    w.writerow(["cost_ratio",
                "" if s["cost_ratio"]          is None else f"{s['cost_ratio']:.4f}"])
    w.writerow(["cache_read_share_delta_pp",   f"{s['cache_read_share_delta_pp']:.4f}"])
    w.writerow(["paired_count",                s["paired_count"]])
    w.writerow(["unmatched_a_count",           s["unmatched_a_count"]])
    w.writerow(["unmatched_b_count",           s["unmatched_b_count"]])
    # IFEval aggregates — blank when no predicates ran.
    w.writerow(["instruction_evaluated",       s.get("instruction_evaluated", 0)])
    w.writerow(["instruction_pass_a",          s.get("instruction_pass_a", 0)])
    w.writerow(["instruction_pass_b",          s.get("instruction_pass_b", 0)])
    rate_a = s.get("instruction_pass_rate_a")
    rate_b = s.get("instruction_pass_rate_b")
    w.writerow(["instruction_pass_rate_a",
                "" if rate_a is None else f"{rate_a:.4f}"])
    w.writerow(["instruction_pass_rate_b",
                "" if rate_b is None else f"{rate_b:.4f}"])
    delta_pp = s.get("instruction_pass_delta_pp")
    w.writerow(["instruction_pass_delta_pp",
                "" if delta_pp is None else f"{delta_pp:.4f}"])
    # Paired-samples statistics (v1.13.0+). Empty cells when no predicates ran.
    w.writerow(["instruction_mcnemar_b", s.get("instruction_mcnemar_b", 0)])
    w.writerow(["instruction_mcnemar_c", s.get("instruction_mcnemar_c", 0)])
    pval = s.get("instruction_mcnemar_pvalue")
    w.writerow(["instruction_mcnemar_pvalue",
                "" if pval is None else f"{pval:.4f}"])
    ci_a = s.get("instruction_pass_rate_a_ci")
    ci_b = s.get("instruction_pass_rate_b_ci")
    w.writerow(["instruction_pass_rate_a_ci_lo",
                "" if ci_a is None else f"{ci_a[0]:.4f}"])
    w.writerow(["instruction_pass_rate_a_ci_hi",
                "" if ci_a is None else f"{ci_a[1]:.4f}"])
    w.writerow(["instruction_pass_rate_b_ci_lo",
                "" if ci_b is None else f"{ci_b[0]:.4f}"])
    w.writerow(["instruction_pass_rate_b_ci_hi",
                "" if ci_b is None else f"{ci_b[1]:.4f}"])
    w.writerow(["low_sample_size",
                "1" if s.get("low_sample_size") else "0"])
    note = s.get("sample_size_note")
    w.writerow(["sample_size_note", note or ""])

    if report["advisories"]:
        w.writerow([])
        w.writerow(["# ADVISORIES"])
        w.writerow(["kind", "severity", "message"])
        for adv in report["advisories"]:
            w.writerow([adv["kind"], adv["severity"], adv["message"]])

    return out.getvalue()


# ---------------------------------------------------------------------------
# Aggregate (Mode 2) renderer bodies
# ---------------------------------------------------------------------------

def _aggregate_side_label(side: dict) -> str:
    """Short label for a Mode-2 side — family + session count when aggregated."""
    family = side.get("model_family") or "?"
    n = side.get("session_count", 1)
    if n > 1:
        return f"{family} ({n} sessions)"
    return family


def _render_aggregate_text(report: dict) -> str:
    """Mode-2 plain-text renderer — aggregate cards, no per-turn table."""
    out = io.StringIO()

    def p(*args, **kw):
        print(*args, **kw, file=out)

    a = report["side_a"]
    b = report["side_b"]
    s = report["summary"]
    tz_label = report.get("tz_label", "UTC")

    p("=" * 82)
    p(f"COMPARE (observational)  slug={report['slug']}  tz={tz_label}")
    p("=" * 82)
    p(f"  A  {_aggregate_side_label(a):<28} model={a['dominant_model_id'] or '?':<28} "
      f"turns={a['turn_count']:<4} cost=${a['totals']['cost']:.4f}"
      f"{_fmt_effort_suffix(a)}")
    p(f"  B  {_aggregate_side_label(b):<28} model={b['dominant_model_id'] or '?':<28} "
      f"turns={b['turn_count']:<4} cost=${b['totals']['cost']:.4f}"
      f"{_fmt_effort_suffix(b)}")
    p()

    if report["advisories"]:
        p("ADVISORIES")
        for adv in report["advisories"]:
            tag = "[WARN]" if adv["severity"] == "warn" else "[info]"
            p(f"  {tag} {adv['message']}")
        p()

    p("SUMMARY (B vs A, aggregate)")
    p(f"  input-token ratio          : {_fmt_ratio(s['input_tokens_ratio'])}")
    p(f"  output-token ratio         : {_fmt_ratio(s['output_tokens_ratio'])}")
    p(f"  total-token ratio          : {_fmt_ratio(s['total_tokens_ratio'])}")
    p(f"  cost ratio                 : {_fmt_ratio(s['cost_ratio'])}  "
      f"(abs delta {_fmt_cost_delta(a, b)})")
    p(f"  avg input / user prompt    : {_fmt_ratio(s['avg_input_per_prompt_ratio'])}")
    p(f"  avg output / turn          : {_fmt_ratio(s['avg_output_per_turn_ratio'])}")
    p(f"  tool-calls / turn          : {_fmt_ratio(s['tool_calls_per_turn_ratio'])}")
    p(f"  cache-read share Δ         : {_fmt_delta_pp(s['cache_read_share_delta_pp'])}")
    p()

    p("AGGREGATE DETAIL")
    hdr = (f"  {'side':<5} {'sessions':>8} {'turns':>6} {'prompts':>8} "
           f"{'input':>10} {'output':>9} {'cost':>10} {'cache%':>7} "
           f"{'tool/t':>7} {'think%':>7}")
    p(hdr)
    p("  " + "-" * (len(hdr) - 2))
    for tag, side in (("A", a), ("B", b)):
        t = side["totals"]
        p(f"  {tag:<5} {side['session_count']:>8} {side['turn_count']:>6} "
          f"{side['user_prompt_count']:>8} {t['input']:>10} {t['output']:>9} "
          f"${t['cost']:>9.4f} {side['cache_read_share_of_input']:>6.1f}% "
          f"{side['tool_calls_per_turn']:>7.2f} {side['thinking_turn_pct']:>6.1f}%")
    p()

    p("NOTE  observational compare is a drift summary, NOT a controlled benchmark.")
    p("      Prompt distributions differ between sides; ratios conflate tokenizer")
    p("      shift with workload shift. Run 'session-metrics --compare-prep' for a")
    p("      controlled suite that isolates tokenizer effects.")
    return out.getvalue()


def _render_aggregate_md(report: dict) -> str:
    """Mode-2 Markdown renderer — aggregate cards, no per-turn table."""
    out = io.StringIO()

    def p(*args, **kw):
        print(*args, **kw, file=out)

    a = report["side_a"]
    b = report["side_b"]
    s = report["summary"]

    p(f"# Model Compare — {report['slug']}")
    p()
    p(f"- Mode: **{report['compare_mode']}**")
    p(f"- Generated: {report['generated_at']}")
    p()
    p("> **Observational, not controlled.** Ratios below conflate tokenizer")
    p("> shift with prompt-distribution shift between the two families. Run")
    p("> `session-metrics --compare-prep` for an attribution-grade benchmark.")
    p()
    p("## Sides")
    p()
    has_effort = _any_effort(report)
    if has_effort:
        p("| Side | Family | Sessions | Model | Effort | Turns | Prompts | Cost |")
        p("|------|--------|---------:|-------|--------|------:|--------:|-----:|")
    else:
        p("| Side | Family | Sessions | Model | Turns | Prompts | Cost |")
        p("|------|--------|---------:|-------|------:|--------:|-----:|")
    for tag, side in (("A", a), ("B", b)):
        if has_effort:
            effort_cell = f"`{side.get('effort')}`" if side.get("effort") else "—"
            p(f"| {tag} | `{side['model_family'] or '?'}` | "
              f"{side['session_count']} | "
              f"`{side['dominant_model_id'] or '?'}` | "
              f"{effort_cell} | "
              f"{side['turn_count']} | {side['user_prompt_count']} | "
              f"${side['totals']['cost']:.4f} |")
        else:
            p(f"| {tag} | `{side['model_family'] or '?'}` | "
              f"{side['session_count']} | "
              f"`{side['dominant_model_id'] or '?'}` | "
              f"{side['turn_count']} | {side['user_prompt_count']} | "
              f"${side['totals']['cost']:.4f} |")
    p()

    if report["advisories"]:
        p("## Advisories")
        p()
        for adv in report["advisories"]:
            tag = "⚠️" if adv["severity"] == "warn" else "ℹ️"
            p(f"- {tag} {adv['message']}")
        p()

    p("## Summary (B vs A, aggregate)")
    p()
    p("| Metric | Value |")
    p("|--------|------:|")
    p(f"| Input-token ratio | {_fmt_ratio(s['input_tokens_ratio'])} |")
    p(f"| Output-token ratio | {_fmt_ratio(s['output_tokens_ratio'])} |")
    p(f"| Total-token ratio | {_fmt_ratio(s['total_tokens_ratio'])} |")
    p(f"| Cost ratio | {_fmt_ratio(s['cost_ratio'])} |")
    p(f"| Cost Δ (absolute) | {_fmt_cost_delta(a, b)} |")
    p(f"| Avg input / user prompt | {_fmt_ratio(s['avg_input_per_prompt_ratio'])} |")
    p(f"| Avg output / turn | {_fmt_ratio(s['avg_output_per_turn_ratio'])} |")
    p(f"| Tool-calls / turn | {_fmt_ratio(s['tool_calls_per_turn_ratio'])} |")
    p(f"| Cache-read share Δ | {_fmt_delta_pp(s['cache_read_share_delta_pp'])} |")
    p()

    p("## Aggregate detail")
    p()
    p("| Side | Sessions | Turns | Prompts | Input | Output | Cache read | "
      "Cost | Cache % | Tool/turn | Think-turn % |")
    p("|------|---------:|------:|--------:|------:|-------:|-----------:|"
      "-----:|--------:|----------:|-------------:|")
    for tag, side in (("A", a), ("B", b)):
        t = side["totals"]
        p(f"| {tag} | {side['session_count']} | {side['turn_count']} | "
          f"{side['user_prompt_count']} | {t['input']} | {t['output']} | "
          f"{t['cache_read']} | ${t['cost']:.4f} | "
          f"{side['cache_read_share_of_input']:.1f}% | "
          f"{side['tool_calls_per_turn']:.2f} | "
          f"{side['thinking_turn_pct']:.1f}% |")
    p()

    return out.getvalue()


def _render_aggregate_csv(report: dict) -> str:
    """Mode-2 CSV renderer — two aggregate rows + summary + advisories."""
    out = io.StringIO()
    w = csv_mod.writer(out)

    w.writerow([
        "side", "model_family", "dominant_model_id", "context_tier", "effort",
        "session_count", "turn_count", "user_prompt_count",
        "input_tokens", "output_tokens", "cache_read_tokens",
        "cache_write_tokens", "total_tokens", "cost_usd",
        "cache_read_share_pct", "avg_input_per_prompt",
        "avg_output_per_turn", "tool_calls_per_turn", "thinking_turn_pct",
    ])
    for tag, side in (("A", report["side_a"]), ("B", report["side_b"])):
        t = side["totals"]
        w.writerow([
            tag, side["model_family"], side["dominant_model_id"],
            side["context_tier"], side.get("effort") or "",
            side["session_count"], side["turn_count"],
            side["user_prompt_count"], t["input"], t["output"], t["cache_read"],
            t["cache_write"], t["total"], f"{t['cost']:.6f}",
            f"{side['cache_read_share_of_input']:.2f}",
            f"{side['avg_input_tokens_per_prompt']:.2f}",
            f"{side['avg_output_tokens_per_turn']:.2f}",
            f"{side['tool_calls_per_turn']:.4f}",
            f"{side['thinking_turn_pct']:.2f}",
        ])

    s = report["summary"]
    w.writerow([])
    w.writerow(["# RATIOS (B vs A)"])
    w.writerow(["metric", "value"])
    for key in (
        "input_tokens_ratio", "output_tokens_ratio", "total_tokens_ratio",
        "cost_ratio", "avg_input_per_prompt_ratio", "avg_output_per_turn_ratio",
        "tool_calls_per_turn_ratio",
    ):
        val = s[key]
        w.writerow([key, "" if val is None else f"{val:.4f}"])
    w.writerow(["cache_read_share_delta_pp", f"{s['cache_read_share_delta_pp']:.4f}"])

    if report["advisories"]:
        w.writerow([])
        w.writerow(["# ADVISORIES"])
        w.writerow(["kind", "severity", "message"])
        for adv in report["advisories"]:
            w.writerow([adv["kind"], adv["severity"], adv["message"]])

    return out.getvalue()


# ---------------------------------------------------------------------------
# HTML renderer — variant="compare" (Phase 6)
# ---------------------------------------------------------------------------
#
# Deliberately emits one self-contained HTML file (no dashboard/detail
# split): the compare report is already concise, and every section
# (summary strip, advisories, per-turn table, quality-vs-cost card) is
# interdependent. Splitting would fragment the story users came for.
#
# The renderer imports ``html`` lazily inside the function so the main
# module's pricing/cost path isn't forced to pull it just for the
# compare codepath.


def _html_escape(s: object) -> str:
    """Small wrapper so the module stays import-cheap — defers to
    ``html.escape`` at call time. Accepts any object (stringifies)
    because report fields include numeric tokens that end up inside
    tooltips."""
    import html as _h
    return _h.escape("" if s is None else str(s))


def _fmt_ratio_html(value: float | None, precision: int = 2) -> str:
    """Ratio as ``"1.23×"`` or ``"—"``. Shared by every summary card."""
    if value is None:
        return "&mdash;"
    return f"{value:.{precision}f}&times;"


def _ratio_tint_class(value: float | None) -> str:
    """CSS class for a heatmap cell based on a ratio vs 1.0.

    Keeps thresholds modest — tokenizer deltas on real workloads cluster
    between 1.0 and 1.5×. Symmetric negative band surfaces the (rare)
    B-side-wins case without drowning out the common direction.
    """
    if value is None:
        return "ratio-na"
    if value >= 1.45:
        return "ratio-hot"
    if value >= 1.20:
        return "ratio-warm"
    if value >= 1.05:
        return "ratio-mild"
    if value <= 0.85:
        return "ratio-cool"
    if value <= 0.95:
        return "ratio-coolish"
    return "ratio-neutral"


def _advisory_banners_html(advisories: list[dict]) -> str:
    """Top-of-page banners for every advisory on the report.

    Severity ``warn`` gets the amber rule; ``info`` the blue muted strip.
    Each banner renders as a ``<div class="advisory {severity}">``.
    """
    if not advisories:
        return ""
    rows = []
    for adv in advisories:
        sev = adv.get("severity", "info")
        icon = "&#9888;" if sev == "warn" else "&#8505;"  # ⚠ / ℹ
        msg = _html_escape(adv.get("message", ""))
        kind = _html_escape(adv.get("kind", ""))
        rows.append(
            f'  <div class="advisory {sev}" data-kind="{kind}">'
            f'<span class="advisory-icon">{icon}</span>'
            f'<span class="advisory-msg">{msg}</span>'
            f'</div>'
        )
    return '<div class="advisories">\n' + "\n".join(rows) + "\n</div>"


def _summary_card(label: str, value: str, sub: str = "",
                  accent: str = "") -> str:
    """One KPI card — identical visual shape to the main dashboard
    cards, but built locally so compare output doesn't depend on the
    main module's renderer being imported."""
    cls = f"card {accent}".strip()
    sub_html = f'<div class="sub">{_html_escape(sub)}</div>' if sub else ""
    return (f'  <div class="{cls}"><div class="val">{value}</div>'
            f'<div class="lbl">{_html_escape(label)}</div>{sub_html}</div>')


def _reproducibility_stamp(report: dict, side_a: dict, side_b: dict) -> str:
    """Fine-print footer line showing exactly which inputs produced the
    report. Present on every variant — ``--compare`` output is meant to
    be shared, and the stamp lets readers verify claims without the
    original JSONLs."""
    parts = [
        f"Generated {_html_escape(report.get('generated_at', ''))}",
        f"slug {_html_escape(report.get('slug', ''))}",
        f"A {_html_escape(side_a.get('dominant_model_id') or '?')}",
        f"B {_html_escape(side_b.get('dominant_model_id') or '?')}",
    ]
    pair_by = report.get("pair_by")
    if pair_by:
        parts.append(f"pair-by {_html_escape(pair_by)}")
    return " &middot; ".join(parts)


def _paired_prompt_label(row: dict, *, redact: bool) -> str:
    """Short label for the per-turn table's `Prompt` column.

    If a suite sentinel matched, show the suite prompt name (canonical,
    safe to share). Otherwise show either the fingerprint-derived hash
    (a peek at pairing, harmless) or a redaction marker when
    ``--redact-user-prompts`` is set on the CLI.
    """
    name = row.get("suite_prompt_name")
    if name:
        return f'<span class="prompt-suite">{_html_escape(name)}</span>'
    fp = row.get("fingerprint") or ""
    if redact:
        return '<span class="prompt-redacted">[redacted]</span>'
    if fp:
        return f'<span class="prompt-fp" title="Fingerprint">{_html_escape(fp[:8])}&hellip;</span>'
    return '<span class="muted">&mdash;</span>'


def _render_histogram_card(paired: list[dict]) -> str:
    """Tiny inline histogram of per-turn input-token ratios.

    Bins ratios into 6 buckets covering the observed range. Pure HTML +
    CSS (no charting library) because compare HTML is meant to be a
    shareable single file; dragging in Highcharts just for this would
    bloat the output for one card.
    """
    ratios = [
        p["ratios"]["input_tokens"] for p in paired
        if p.get("ratios") and p["ratios"].get("input_tokens") is not None
    ]
    if not ratios:
        return ""
    bins = [
        ("< 0.90", lambda r: r < 0.90),
        ("0.90-1.00", lambda r: 0.90 <= r < 1.00),
        ("1.00-1.10", lambda r: 1.00 <= r < 1.10),
        ("1.10-1.25", lambda r: 1.10 <= r < 1.25),
        ("1.25-1.45", lambda r: 1.25 <= r < 1.45),
        (">= 1.45", lambda r: r >= 1.45),
    ]
    counts = [sum(1 for r in ratios if pred(r)) for _label, pred in bins]
    max_count = max(counts) or 1
    ratios_sorted = sorted(ratios)
    mean = sum(ratios) / len(ratios)
    p50 = ratios_sorted[len(ratios_sorted) // 2]
    p95_idx = max(0, int(round(0.95 * (len(ratios_sorted) - 1))))
    p95 = ratios_sorted[p95_idx]
    bar_rows = []
    for (label, _pred), count in zip(bins, counts):
        pct = 100.0 * count / max_count
        bar_rows.append(
            f'      <div class="hist-row">'
            f'<div class="hist-label">{_html_escape(label)}</div>'
            f'<div class="hist-bar-wrap">'
            f'<div class="hist-bar" style="width:{pct:.1f}%"></div>'
            f'<div class="hist-count">{count}</div>'
            f'</div></div>'
        )
    return (
        '<section class="compare-card histogram">\n'
        '  <h2>Per-turn input-token ratio distribution</h2>\n'
        f'  <p class="meta-small">mean {mean:.2f}&times; &middot; p50 '
        f'{p50:.2f}&times; &middot; p95 {p95:.2f}&times; &middot; '
        f'n={len(ratios)}</p>\n'
        '  <div class="hist">\n'
        + "\n".join(bar_rows)
        + '\n  </div>\n'
        '</section>'
    )


def _render_quality_vs_cost_card(summary: dict) -> str:
    """Explicit juxtaposition of cost delta and quality delta.

    Without this card, readers see a red "+30% cost" number and draw the
    wrong conclusion. IFEval delta (when evaluated) prevents the naive
    "more expensive == worse" read by showing the trade-off directly.
    """
    cost = summary.get("cost_ratio")
    ifeval = summary.get("instruction_pass_delta_pp")
    evaluated = summary.get("instruction_evaluated") or 0
    if cost is None and not evaluated:
        return ""
    cost_txt = _fmt_ratio_html(cost) if cost is not None else "&mdash;"
    if evaluated:
        sign = "+" if (ifeval or 0) >= 0 else ""
        ifeval_txt = f"{sign}{ifeval:.1f} pp"
        if ifeval and ifeval > 0 and cost and cost > 1.05:
            verdict = ("higher cost bought higher instruction compliance "
                       "&mdash; read as a quality/cost trade-off")
        elif ifeval and ifeval < 0 and cost and cost > 1.05:
            verdict = ("higher cost with lower compliance &mdash; weak "
                       "pair on this suite")
        elif cost and cost <= 1.05 and ifeval and ifeval > 0:
            verdict = "quality up with no meaningful cost hit"
        else:
            verdict = "cost roughly flat; quality delta shown at right"
    else:
        ifeval_txt = "no suite predicates evaluated"
        verdict = ("no IFEval measurement; cost delta alone doesn't tell "
                   "you whether quality changed")
    return (
        '<section class="compare-card qvsc">\n'
        '  <h2>Quality vs cost</h2>\n'
        '  <div class="qvsc-row">\n'
        f'    <div class="qvsc-cell"><div class="val">{cost_txt}</div>'
        f'<div class="lbl">cost ratio (B vs A)</div></div>\n'
        f'    <div class="qvsc-cell"><div class="val">{ifeval_txt}</div>'
        f'<div class="lbl">IFEval &Delta; (B minus A)</div></div>\n'
        '  </div>\n'
        f'  <p class="qvsc-verdict">{_html_escape(verdict)}</p>\n'
        '</section>'
    )


def _render_compare_html_controlled(
    report: dict,
    *,
    redact_user_prompts: bool = False,
) -> str:
    """Mode-1 compare HTML renderer.

    Produces one self-contained dark-themed page. Sections:
    advisories → sides bar → KPI summary strip → quality-vs-cost card →
    (when evaluated) IFEval summary → per-turn table with heatmap tint
    → histogram card → unmatched turns → methodology footer.
    """
    a = report["side_a"]
    b = report["side_b"]
    s = report["summary"]
    slug = report.get("slug", "")
    pair_by = report.get("pair_by", "?")
    tz_label = report.get("tz_label", "UTC")

    advisories_html = _advisory_banners_html(report.get("advisories", []) or [])

    def _effort_html(side: dict) -> str:
        effort = side.get("effort") or ""
        return f' &middot; effort <code>{_html_escape(effort)}</code>' if effort else ""

    sides_html = (
        '<section class="sides">\n'
        f'  <div class="side-card side-a">\n'
        f'    <div class="side-tag">A</div>\n'
        f'    <div class="side-model">{_html_escape(a.get("dominant_model_id") or "?")}</div>\n'
        f'    <div class="side-meta">'
        f'<code>{_html_escape((a.get("session_id") or "")[:16])}&hellip;</code>'
        f' &middot; {a.get("turn_count", 0)} turns'
        f' &middot; ${a.get("totals", {}).get("cost", 0):.4f}'
        f'{_effort_html(a)}'
        f'</div>\n'
        f'  </div>\n'
        f'  <div class="side-card side-b">\n'
        f'    <div class="side-tag">B</div>\n'
        f'    <div class="side-model">{_html_escape(b.get("dominant_model_id") or "?")}</div>\n'
        f'    <div class="side-meta">'
        f'<code>{_html_escape((b.get("session_id") or "")[:16])}&hellip;</code>'
        f' &middot; {b.get("turn_count", 0)} turns'
        f' &middot; ${b.get("totals", {}).get("cost", 0):.4f}'
        f'{_effort_html(b)}'
        f'</div>\n'
        f'  </div>\n'
        '</section>'
    )

    cost_delta_abs = b.get("totals", {}).get("cost", 0) - a.get("totals", {}).get("cost", 0)
    cost_delta_sign = "+" if cost_delta_abs >= 0 else "&minus;"
    cost_delta_txt = f"{cost_delta_sign}${abs(cost_delta_abs):.4f}"

    cards = [
        _summary_card("Input tokens ratio",
                      _fmt_ratio_html(s.get("input_tokens_ratio")),
                      "B vs A, side totals"),
        _summary_card("Output tokens ratio",
                      _fmt_ratio_html(s.get("output_tokens_ratio"))),
        _summary_card("Total tokens ratio",
                      _fmt_ratio_html(s.get("total_tokens_ratio"))),
        _summary_card("Cost ratio",
                      _fmt_ratio_html(s.get("cost_ratio")),
                      cost_delta_txt,
                      accent="amber"),
        _summary_card("Paired turns",
                      str(s.get("paired_count", 0)),
                      f"unmatched A={s.get('unmatched_a_count', 0)}, "
                      f"B={s.get('unmatched_b_count', 0)}"),
        _summary_card("Cache-read share &Delta;",
                      _fmt_delta_pp(s.get("cache_read_share_delta_pp", 0)),
                      accent="green" if (s.get("cache_read_share_delta_pp") or 0) >= 0 else ""),
    ]
    if s.get("instruction_evaluated"):
        rate_a = (s.get("instruction_pass_rate_a") or 0) * 100
        rate_b = (s.get("instruction_pass_rate_b") or 0) * 100
        delta_pp = s.get("instruction_pass_delta_pp") or 0
        delta_accent = "green" if delta_pp >= 0 else "amber"
        sub_parts = [f"A {rate_a:.0f}%", _fmt_delta_pp(delta_pp)]
        ci_b = s.get("instruction_pass_rate_b_ci")
        if ci_b:
            sub_parts.append(
                f"95% CI [{ci_b[0] * 100:.0f}&ndash;{ci_b[1] * 100:.0f}%]"
            )
        pval = s.get("instruction_mcnemar_pvalue")
        if pval is not None:
            sub_parts.append(f"McNemar p={pval:.3f}")
        cards.append(_summary_card(
            "IFEval pass rate (B)",
            f"{rate_b:.0f}%",
            " &middot; ".join(sub_parts),
            accent=delta_accent,
        ))
    cards_html = '<div class="cards">\n' + "\n".join(cards) + '\n</div>'

    # Small-N banner — placed above the cards so the number isn't
    # over-interpreted. Additive: existing DOM selectors keep working.
    if s.get("low_sample_size") and s.get("sample_size_note"):
        cards_html = (
            '<div class="ifeval-banner" role="note" '
            'style="padding:.6em .8em;margin:0 0 .6em;border-radius:4px;'
            'background:#fff8e1;border-left:3px solid #f59e0b;'
            'color:#92400e;font-size:.9em;">'
            f'<strong>Low sample size:</strong> '
            f'{_html_escape(s["sample_size_note"])}'
            '</div>\n'
        ) + cards_html

    qvsc_html = _render_quality_vs_cost_card(s)
    hist_html = _render_histogram_card(report.get("paired", []) or [])

    # ---- Per-turn table ----------------------------------------------------
    paired = report.get("paired", []) or []
    has_instruction = any(
        row.get("instruction_pass_a") is not None
        or row.get("instruction_pass_b") is not None
        for row in paired
    )

    def _pass_cell(v):
        if v is True:
            return '<td class="pass pass-ok">&#10003;</td>'
        if v is False:
            return '<td class="pass pass-fail">&#10007;</td>'
        return '<td class="pass muted">&mdash;</td>'

    def _ratio_cell(v, precision=2):
        cls = _ratio_tint_class(v)
        if v is None:
            return f'<td class="num {cls}">&mdash;</td>'
        return f'<td class="num {cls}">{v:.{precision}f}&times;</td>'

    table_rows = []
    for i, row in enumerate(paired, 1):
        ar = row.get("a", {})
        br = row.get("b", {})
        r = row.get("ratios", {}) or {}
        prompt_html = _paired_prompt_label(row, redact=redact_user_prompts)
        cells = [
            f'<td class="idx">{i}</td>',
            f'<td class="num">{ar.get("input_tokens", 0):,}</td>',
            f'<td class="num">{br.get("input_tokens", 0):,}</td>',
            _ratio_cell(r.get("input_tokens")),
            f'<td class="num">{ar.get("output_tokens", 0):,}</td>',
            f'<td class="num">{br.get("output_tokens", 0):,}</td>',
            _ratio_cell(r.get("output_tokens")),
            f'<td class="num cost">${ar.get("cost_usd", 0):.4f}</td>',
            f'<td class="num cost">${br.get("cost_usd", 0):.4f}</td>',
            _ratio_cell(r.get("cost_usd")),
        ]
        if has_instruction:
            cells.append(_pass_cell(row.get("instruction_pass_a")))
            cells.append(_pass_cell(row.get("instruction_pass_b")))
            cells.append(f'<td class="prompt">{prompt_html}</td>')
        else:
            cells.append(f'<td class="prompt">{prompt_html}</td>')
        table_rows.append("    <tr>" + "".join(cells) + "</tr>")

    headers_base = [
        ("#", "idx"),
        ("A input", "num"), ("B input", "num"), ("&Delta; input", "num"),
        ("A output", "num"), ("B output", "num"), ("&Delta; output", "num"),
        ("A cost", "num"), ("B cost", "num"), ("&Delta; cost", "num"),
    ]
    if has_instruction:
        headers = headers_base + [("A&#10003;", "pass"), ("B&#10003;", "pass"),
                                  ("Prompt", "prompt")]
    else:
        headers = headers_base + [("Prompt", "prompt")]
    thead = "".join(f'<th class="{cls}">{name}</th>' for name, cls in headers)

    if paired:
        table_html = (
            '<section class="compare-card">\n'
            '  <h2>Paired turns</h2>\n'
            '  <table class="compare-table">\n'
            f'    <thead><tr>{thead}</tr></thead>\n'
            '    <tbody>\n'
            + "\n".join(table_rows)
            + '\n    </tbody>\n  </table>\n</section>'
        )
    else:
        table_html = (
            '<section class="compare-card empty">\n'
            '  <h2>Paired turns</h2>\n'
            '  <p class="meta">No paired turns &mdash; see advisories.</p>\n'
            '</section>'
        )

    unmatched_a = len(report.get("unmatched_a", []) or [])
    unmatched_b = len(report.get("unmatched_b", []) or [])
    unmatched_html = ""
    if unmatched_a or unmatched_b:
        unmatched_html = (
            '<section class="compare-card unmatched">\n'
            '  <h2>Unmatched turns</h2>\n'
            f'  <p>A-only turns: <strong>{unmatched_a}</strong></p>\n'
            f'  <p>B-only turns: <strong>{unmatched_b}</strong></p>\n'
            '  <p class="meta-small">These turns ran on one side but found '
            'no counterpart on the other &mdash; typically a prompt appeared '
            'only once in the paste sequence.</p>\n'
            '</section>'
        )

    stamp = _reproducibility_stamp(report, a, b)
    methodology = (
        '<section class="compare-card methodology">\n'
        '  <h2>Methodology</h2>\n'
        '  <p>Compare mode is a tokenizer / behaviour study, not a quality '
        'score. When pricing is identical (e.g. between '
        '<code>claude-opus-4-6</code> and <code>claude-opus-4-7</code>), '
        'cost ratio equals tokenizer + output-length ratio. IFEval is a '
        'strict per-prompt predicate &mdash; near-misses fail by design.</p>\n'
        '  <p class="meta-small">Full methodology and caveats: '
        '<code>references/model-compare.md</code> in the skill tree.</p>\n'
        '</section>'
    )

    return _compare_html_shell(
        title=f"Compare &mdash; {_html_escape(slug)}",
        subheading=(f'mode <strong>controlled</strong> &middot; '
                    f'pair-by <strong>{_html_escape(pair_by)}</strong> '
                    f'&middot; tz <strong>{_html_escape(tz_label)}</strong>'),
        body="\n".join(filter(None, [
            advisories_html,
            sides_html,
            cards_html,
            qvsc_html,
            hist_html,
            table_html,
            unmatched_html,
            methodology,
        ])),
        stamp=stamp,
    )


def _render_compare_html_aggregate(
    report: dict,
    *,
    redact_user_prompts: bool = False,  # noqa: ARG001 — unused, API parity
) -> str:
    """Mode-2 compare HTML renderer.

    Same visual shell as Mode 1, but replaces the per-turn table with
    aggregate side cards and the observational-not-controlled banner
    always fires from the advisories list so users don't mistake this
    for attribution-grade output.
    """
    a = report["side_a"]
    b = report["side_b"]
    s = report["summary"]
    slug = report.get("slug", "")
    tz_label = report.get("tz_label", "UTC")

    advisories_html = _advisory_banners_html(report.get("advisories", []) or [])

    def _side_block(tag: str, side: dict, cls: str) -> str:
        t = side.get("totals", {})
        effort = side.get("effort") or ""
        effort_html = (
            f' &middot; effort <code>{_html_escape(effort)}</code>' if effort else ""
        )
        return (
            f'  <div class="side-card {cls}">\n'
            f'    <div class="side-tag">{tag}</div>\n'
            f'    <div class="side-model">'
            f'{_html_escape(side.get("dominant_model_id") or "?")}</div>\n'
            f'    <div class="side-meta">'
            f'family <code>{_html_escape(side.get("model_family") or "?")}</code>'
            f' &middot; {side.get("session_count", 1)} session(s)'
            f' &middot; {side.get("turn_count", 0)} turns'
            f' &middot; ${t.get("cost", 0):.4f}'
            f'{effort_html}'
            f'</div>\n'
            f'  </div>'
        )
    sides_html = (
        '<section class="sides">\n'
        + _side_block("A", a, "side-a") + "\n"
        + _side_block("B", b, "side-b") + "\n"
        + '</section>'
    )

    cost_delta_abs = b.get("totals", {}).get("cost", 0) - a.get("totals", {}).get("cost", 0)
    cost_delta_sign = "+" if cost_delta_abs >= 0 else "&minus;"
    cost_delta_txt = f"{cost_delta_sign}${abs(cost_delta_abs):.4f}"

    cards = [
        _summary_card("Input tokens ratio",
                      _fmt_ratio_html(s.get("input_tokens_ratio")),
                      "B vs A, side totals"),
        _summary_card("Output tokens ratio",
                      _fmt_ratio_html(s.get("output_tokens_ratio"))),
        _summary_card("Total tokens ratio",
                      _fmt_ratio_html(s.get("total_tokens_ratio"))),
        _summary_card("Cost ratio",
                      _fmt_ratio_html(s.get("cost_ratio")),
                      cost_delta_txt,
                      accent="amber"),
        _summary_card("Avg input / prompt",
                      _fmt_ratio_html(s.get("avg_input_per_prompt_ratio"))),
        _summary_card("Avg output / turn",
                      _fmt_ratio_html(s.get("avg_output_per_turn_ratio"))),
        _summary_card("Tool calls / turn",
                      _fmt_ratio_html(s.get("tool_calls_per_turn_ratio"))),
        _summary_card("Cache-read share &Delta;",
                      _fmt_delta_pp(s.get("cache_read_share_delta_pp", 0))),
    ]
    cards_html = '<div class="cards">\n' + "\n".join(cards) + '\n</div>'

    # Aggregate detail table — one row per side.
    def _detail_row(tag, side):
        t = side.get("totals", {})
        return (
            '    <tr>'
            f'<td class="idx">{tag}</td>'
            f'<td class="num">{side.get("session_count", 1)}</td>'
            f'<td class="num">{side.get("turn_count", 0):,}</td>'
            f'<td class="num">{side.get("user_prompt_count", 0):,}</td>'
            f'<td class="num">{t.get("input", 0):,}</td>'
            f'<td class="num">{t.get("output", 0):,}</td>'
            f'<td class="num">{t.get("cache_read", 0):,}</td>'
            f'<td class="num cost">${t.get("cost", 0):.4f}</td>'
            f'<td class="num">{side.get("cache_read_share_of_input", 0):.1f}%</td>'
            f'<td class="num">{side.get("tool_calls_per_turn", 0):.2f}</td>'
            f'<td class="num">{side.get("thinking_turn_pct", 0):.1f}%</td>'
            '</tr>'
        )
    detail_html = (
        '<section class="compare-card">\n'
        '  <h2>Aggregate detail</h2>\n'
        '  <table class="compare-table">\n'
        '    <thead><tr>'
        '<th class="idx">Side</th><th class="num">Sessions</th>'
        '<th class="num">Turns</th><th class="num">Prompts</th>'
        '<th class="num">Input</th><th class="num">Output</th>'
        '<th class="num">Cache read</th><th class="num">Cost</th>'
        '<th class="num">Cache %</th><th class="num">Tool/turn</th>'
        '<th class="num">Think-turn %</th>'
        '</tr></thead>\n'
        '    <tbody>\n'
        + _detail_row("A", a) + "\n"
        + _detail_row("B", b) + "\n"
        + '    </tbody>\n  </table>\n</section>'
    )

    stamp = _reproducibility_stamp(report, a, b)
    methodology = (
        '<section class="compare-card methodology">\n'
        '  <h2>Methodology</h2>\n'
        '  <p><strong>Observational, not controlled.</strong> These ratios '
        'compare aggregate behaviour across sessions with different prompt '
        'distributions. They conflate tokenizer shift, workload shift, and '
        'cache warmth. For attribution run '
        '<code>session-metrics --compare-prep</code> and capture two fresh '
        'sessions running the canonical suite.</p>\n'
        '  <p class="meta-small">Full methodology: '
        '<code>references/model-compare.md</code>.</p>\n'
        '</section>'
    )

    return _compare_html_shell(
        title=f"Compare &mdash; {_html_escape(slug)}",
        subheading=(f'mode <strong>observational</strong> &middot; '
                    f'tz <strong>{_html_escape(tz_label)}</strong>'),
        body="\n".join(filter(None, [
            advisories_html,
            sides_html,
            cards_html,
            detail_html,
            methodology,
        ])),
        stamp=stamp,
    )


def _compare_html_shell(*, title: str, subheading: str, body: str,
                        stamp: str) -> str:
    """Outer HTML document scaffolding shared by Mode 1 and Mode 2.

    CSS is inlined — compare HTML is meant to be a single self-contained
    file users can share via attachment or static hosting without a
    separate stylesheet fetch. Palette mirrors the main dashboard so the
    two outputs feel related when opened side by side.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Session Metrics &mdash; {title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #0d1117; color: #e6edf3; font-size: 13px; padding: 24px;
         line-height: 1.5; }}
  h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 4px; color: #f0f6fc; }}
  h2 {{ font-size: 14px; font-weight: 600; color: #f0f6fc; margin: 0 0 10px; }}
  .subhead {{ color: #8b949e; font-size: 12px; margin-bottom: 20px; }}
  .subhead strong {{ color: #c9d1d9; font-weight: 600; }}
  .advisories {{ display: flex; flex-direction: column; gap: 6px;
                 margin-bottom: 20px; }}
  .advisory {{ padding: 9px 14px; border-radius: 6px; font-size: 12px;
               display: flex; gap: 10px; align-items: flex-start;
               border: 1px solid transparent; }}
  .advisory.warn {{ background: #2e1f0d; border-color: #9c7a2f;
                    color: #f7c773; }}
  .advisory.info {{ background: #0d2237; border-color: #1f4e79;
                    color: #79c0ff; }}
  .advisory-icon {{ flex: 0 0 auto; font-weight: 700; }}
  .advisory-msg {{ flex: 1 1 auto; color: #c9d1d9; }}
  .sides {{ display: flex; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }}
  .side-card {{ flex: 1 1 300px; background: #161b22; border: 1px solid #30363d;
                border-radius: 8px; padding: 14px 18px; position: relative; }}
  .side-card.side-a {{ border-left: 3px solid #58a6ff; }}
  .side-card.side-b {{ border-left: 3px solid #d29922; }}
  .side-tag {{ position: absolute; top: 10px; right: 12px;
               font-size: 11px; color: #8b949e; font-weight: 600; }}
  .side-model {{ font-size: 14px; color: #f0f6fc; font-weight: 600;
                 font-family: "SF Mono", Menlo, Consolas, monospace; }}
  .side-meta {{ font-size: 11px; color: #8b949e; margin-top: 4px; }}
  .side-meta code {{ color: #a5d6ff; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
           padding: 12px 16px; min-width: 150px; flex: 1 1 150px; }}
  .card .val {{ font-size: 22px; font-weight: 700; color: #58a6ff;
                font-variant-numeric: tabular-nums; }}
  .card .lbl {{ font-size: 11px; color: #8b949e; margin-top: 2px; }}
  .card .sub {{ font-size: 10px; color: #6e7681; margin-top: 2px;
                font-variant-numeric: tabular-nums; }}
  .card.green .val {{ color: #3fb950; }}
  .card.amber .val {{ color: #d29922; }}
  section.compare-card {{ background: #161b22; border: 1px solid #30363d;
                           border-radius: 8px; padding: 16px 20px;
                           margin-bottom: 18px; }}
  section.compare-card.qvsc .qvsc-row {{ display: flex; gap: 18px;
                                          margin: 10px 0; }}
  section.compare-card.qvsc .qvsc-cell {{ flex: 1 1 160px;
                           background: #0d1117; border: 1px solid #30363d;
                           border-radius: 6px; padding: 12px 14px; }}
  section.compare-card.qvsc .qvsc-cell .val {{ font-size: 20px;
                           font-weight: 700; color: #f0f6fc;
                           font-variant-numeric: tabular-nums; }}
  section.compare-card.qvsc .qvsc-cell .lbl {{ font-size: 11px;
                           color: #8b949e; margin-top: 2px; }}
  .qvsc-verdict {{ color: #c9d1d9; font-size: 12px; font-style: italic;
                   margin-top: 6px; }}
  section.compare-card.histogram .hist {{ display: flex;
                           flex-direction: column; gap: 4px; margin-top: 6px; }}
  .hist-row {{ display: flex; gap: 10px; align-items: center; }}
  .hist-label {{ flex: 0 0 80px; font-size: 11px; color: #8b949e;
                 font-variant-numeric: tabular-nums; text-align: right; }}
  .hist-bar-wrap {{ flex: 1 1 auto; display: flex; align-items: center;
                    gap: 8px; }}
  .hist-bar {{ height: 14px; background: linear-gradient(to right,
                           #1f6feb 0%, #58a6ff 100%);
                           border-radius: 3px; min-width: 2px; }}
  .hist-count {{ font-size: 11px; color: #c9d1d9;
                 font-variant-numeric: tabular-nums; }}
  .meta-small {{ font-size: 11px; color: #8b949e; margin: 4px 0; }}
  table.compare-table {{ width: 100%; border-collapse: collapse;
                          font-size: 12px; }}
  table.compare-table th {{ background: #0d1117; color: #8b949e;
                             font-weight: 500; text-align: left;
                             padding: 6px 10px;
                             border-bottom: 1px solid #30363d;
                             white-space: nowrap; }}
  table.compare-table th.num, table.compare-table td.num {{ text-align: right;
                           font-variant-numeric: tabular-nums; }}
  table.compare-table th.pass, table.compare-table td.pass {{
                           text-align: center; width: 42px; }}
  table.compare-table td {{ padding: 4px 10px;
                             border-bottom: 1px solid #21262d;
                             vertical-align: middle; }}
  table.compare-table tr:hover td {{ background: #1c2128; }}
  td.cost {{ color: #c9d1d9; white-space: nowrap; }}
  td.idx {{ color: #6e7681; text-align: right; width: 36px; }}
  td.prompt {{ color: #8b949e; font-size: 11px; }}
  td.prompt .prompt-suite {{ color: #a5d6ff;
                             font-family: "SF Mono", Menlo, Consolas, monospace; }}
  td.prompt .prompt-fp {{ color: #6e7681;
                          font-family: "SF Mono", Menlo, Consolas, monospace; }}
  td.prompt .prompt-redacted {{ color: #6e7681; font-style: italic; }}
  .pass-ok {{ color: #3fb950; font-weight: 700; }}
  .pass-fail {{ color: #f85149; font-weight: 700; }}
  .muted {{ color: #484f58; }}
  .ratio-hot {{ background: rgba(248, 81, 73, 0.18); color: #ff7b72; }}
  .ratio-warm {{ background: rgba(210, 153, 34, 0.18); color: #e3b341; }}
  .ratio-mild {{ background: rgba(210, 153, 34, 0.08); color: #d29922; }}
  .ratio-neutral {{ color: #8b949e; }}
  .ratio-coolish {{ color: #3fb950; }}
  .ratio-cool {{ background: rgba(63, 185, 80, 0.18); color: #3fb950; }}
  .ratio-na {{ color: #484f58; }}
  .stamp {{ margin-top: 22px; padding: 10px 0; font-size: 10px;
            color: #484f58; border-top: 1px solid #21262d;
            font-family: "SF Mono", Menlo, Consolas, monospace; }}
  code {{ font-family: "SF Mono", Menlo, Consolas, monospace;
          color: #a5d6ff; background: #0d1117; padding: 0 4px;
          border-radius: 3px; border: 1px solid #30363d; font-size: 11px; }}
</style>
</head>
<body>
<h1>Session Metrics &mdash; {title}</h1>
<p class="subhead">{subheading}</p>
{body}
<p class="stamp">{stamp}</p>
</body>
</html>
"""


def render_compare_html(report: dict, *,
                        redact_user_prompts: bool = False) -> str:
    """Entry point for compare HTML rendering.

    Dispatches on ``compare_mode``; both branches return a single
    self-contained HTML document. ``redact_user_prompts`` masks freeform
    prompt fingerprints in the per-turn table (Mode 1 only) for
    shareable output &mdash; sentinel-tagged suite prompts are canonical
    and stay visible.
    """
    if report.get("compare_mode") == "observational":
        return _render_compare_html_aggregate(
            report, redact_user_prompts=redact_user_prompts,
        )
    return _render_compare_html_controlled(
        report, redact_user_prompts=redact_user_prompts,
    )


# ---------------------------------------------------------------------------
# Driver — CLI dispatch entrypoint
# ---------------------------------------------------------------------------

def _check_compare_scope(
    scope: str,
    a_kind: str,
    b_kind: str,
) -> str:
    """Reconcile ``--compare-scope`` against the resolver's per-arg kind.

    Returns the effective compare_mode slug:

    - ``"controlled"`` — both args are single sessions (Mode 1).
    - ``"observational"`` — at least one arg is an aggregate; the report
      rolls up every session in each side's family without per-turn
      pairing.

    Raises :class:`CompareArgError` when the requested scope is
    incompatible with what the args resolved to. Scope ``"auto"``
    picks observational iff either side is an aggregate; ``"session"``
    forces controlled (refuses aggregates); ``"project"`` forces
    observational (accepts single sessions as degenerate 1-session
    aggregates so the user can pin Mode 2 unambiguously even when
    passing two UUIDs or paths).
    """
    has_aggregate = a_kind == "aggregate" or b_kind == "aggregate"

    if scope == "session":
        if has_aggregate:
            raise CompareArgError(
                "--compare-scope=session requires two single sessions, but an "
                "arg resolved to a project aggregate ('all-<family>')"
            )
        return "controlled"

    if scope == "project":
        return "observational"

    # scope == "auto"
    if has_aggregate:
        return "observational"
    return "controlled"


def _load_sessions(
    paths: list[Path],
    include_subagents: bool,
    use_cache: bool,
) -> list[tuple[str, list[dict], list[int]]]:
    """Load every JSONL in ``paths`` via the main module's ``_load_session``.

    Small helper so ``_run_compare`` can materialize a side's worth of
    sessions in one call — aggregate sides (``all-<family>``) have N
    paths; single sides have 1.
    """
    m = _main()
    out: list[tuple[str, list[dict], list[int]]] = []
    for p in paths:
        sid, turns, user_ts = m._load_session(
            p, include_subagents, use_cache=use_cache,
        )
        out.append((sid, turns, user_ts))
    return out


def _confirm_aggregate_or_exit(
    side_a_sessions: list[tuple[str, list[dict], list[int]]],
    side_b_sessions: list[tuple[str, list[dict], list[int]]],
    assume_yes: bool,
) -> None:
    """Show an aggregate-scope preview and ask for y/N unless ``assume_yes``.

    Prints session counts + total-turn counts per side to stderr so the
    dashboard output on stdout stays clean, then reads one line from
    stdin. Any response that doesn't start with ``y`` (case-insensitive)
    exits 0 with a message. Non-TTY stdin (e.g. piped input) and
    ``--yes`` both skip the prompt — piped invocations never block.

    Called only when ``compare_mode == "observational"``; the
    controlled path has no confirmation gate because a session pair
    is a small, predictable scope.
    """
    def _count(sessions):
        turns = sum(len(t) for _sid, t, _u in sessions)
        prompts = sum(len(u) for _sid, _t, u in sessions)
        return len(sessions), turns, prompts

    a_n, a_turns, a_prompts = _count(side_a_sessions)
    b_n, b_turns, b_prompts = _count(side_b_sessions)

    print("Mode 2 (observational) aggregate preview:", file=sys.stderr)
    print(f"  A: {a_n} session(s), {a_turns} turn(s), {a_prompts} user prompt(s)",
          file=sys.stderr)
    print(f"  B: {b_n} session(s), {b_turns} turn(s), {b_prompts} user prompt(s)",
          file=sys.stderr)

    if assume_yes:
        print("(--yes given; proceeding)", file=sys.stderr)
        return
    if not sys.stdin.isatty():
        # Non-interactive invocation — require explicit --yes to proceed.
        print("[error] aggregate compare requires --yes when stdin is not a TTY "
              "(prevents accidental large rollups in scripts)", file=sys.stderr)
        sys.exit(1)
    try:
        answer = input("Proceed? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n(aborted)", file=sys.stderr)
        sys.exit(0)
    if not answer.startswith("y"):
        print("(aborted)", file=sys.stderr)
        sys.exit(0)


def _run_compare(
    arg_a: str,
    arg_b: str,
    *,
    slug: str,
    pair_by: str = "fingerprint",
    compare_scope: str = "auto",
    min_turns: int = 5,
    formats: list[str] | None = None,
    tz_offset: float = 0.0,
    tz_label: str = "UTC",
    include_subagents: bool = False,
    use_cache: bool = True,
    single_page: bool = False,
    chart_lib: str = "highcharts",
    assume_yes: bool = False,
    prompt_suite_dir: Path | None = None,
    allow_suite_mismatch: bool = False,
    redact_user_prompts: bool = False,
    share_safe: bool = False,
    effort_a: str | None = None,
    effort_b: str | None = None,
) -> dict | None:
    """Entrypoint the CLI calls after argument parsing.

    Resolves both ``--compare`` args to JSONL paths, enforces scope
    against what the args resolved to, builds either a Mode-1
    (controlled, session pair) or Mode-2 (observational, project
    aggregate) report, then hands off to the main module's
    ``_dispatch`` for format output.

    ``assume_yes`` skips the Mode-2 aggregate confirmation gate. Mode 1
    never prompts.

    Returns the compare report dict (same object passed to
    ``_dispatch``) so callers can feed downstream artefact generators
    — e.g. ``_emit_compare_run_extras`` which renders per-session
    dashboards and the companion analysis.md. Existing CLI callers
    that discard the return value are unaffected. ``None`` is returned
    on early-exit arg-error paths that terminate with ``sys.exit``;
    normal code paths always return a dict.
    """
    m = _main()
    formats = formats or []

    try:
        a_kind, a_paths = _resolve_compare_arg(
            arg_a, slug,
            include_subagents=include_subagents,
            min_turns=min_turns,
            use_cache=use_cache,
        )
        b_kind, b_paths = _resolve_compare_arg(
            arg_b, slug,
            include_subagents=include_subagents,
            min_turns=min_turns,
            use_cache=use_cache,
        )
        compare_mode = _check_compare_scope(compare_scope, a_kind, b_kind)
    except CompareArgError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        side_a_sessions = _load_sessions(a_paths, include_subagents, use_cache)
        side_b_sessions = _load_sessions(b_paths, include_subagents, use_cache)
    except OSError as exc:
        print(f"[error] failed to load compare session: {exc}", file=sys.stderr)
        sys.exit(1)

    if compare_mode == "observational":
        _confirm_aggregate_or_exit(
            side_a_sessions, side_b_sessions, assume_yes=assume_yes,
        )

        a_preview = f"{len(side_a_sessions)} session(s)"
        b_preview = f"{len(side_b_sessions)} session(s)"
        print(f"Compare : A={a_preview}  B={b_preview}", file=sys.stderr)
        print(f"Slug    : {slug}", file=sys.stderr)
        print(f"Scope   : observational", file=sys.stderr)
        print(f"TZ      : {tz_label}", file=sys.stderr)
        print(file=sys.stderr)

        if not side_a_sessions or not side_b_sessions:
            print("[info] one or both sides have no sessions; compare report "
                  "will be empty", file=sys.stderr)

        report = _build_compare_aggregate_report(
            side_a_sessions, side_b_sessions,
            slug=slug,
            tz_offset_hours=tz_offset,
            tz_label=tz_label,
            effort_a=effort_a,
            effort_b=effort_b,
        )
        m._dispatch(report, formats, single_page=single_page,
                    chart_lib=chart_lib,
                    redact_user_prompts=redact_user_prompts,
                    share_safe=share_safe)
        return report

    # compare_mode == "controlled" — Mode 1
    a_sid, a_turns, a_user_ts = side_a_sessions[0]
    b_sid, b_turns, b_user_ts = side_b_sessions[0]
    a_path = a_paths[0]
    b_path = b_paths[0]

    print(f"Compare : A={a_path.name}  B={b_path.name}", file=sys.stderr)
    print(f"Slug    : {slug}", file=sys.stderr)
    print(f"Pair-by : {pair_by}", file=sys.stderr)
    print(f"TZ      : {tz_label}", file=sys.stderr)
    print(file=sys.stderr)

    if not a_turns or not b_turns:
        print("[info] one or both sessions have no assistant turns with "
              "usage data; compare report will be empty", file=sys.stderr)

    # Load suite predicates once per invocation. A user-supplied
    # ``--compare-prompts DIR`` overrides the packaged suite; the
    # builder accepts the pre-loaded dict so tests can inject too.
    try:
        prompt_suite = _load_prompt_suite(prompt_suite_dir)
    except PromptSuiteError as exc:
        print(f"[error] prompt suite: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        report = _build_compare_report(
            a_sid, a_turns, a_user_ts,
            b_sid, b_turns, b_user_ts,
            slug=slug,
            pair_by=pair_by,
            tz_offset_hours=tz_offset,
            tz_label=tz_label,
            prompt_suite=prompt_suite,
            allow_suite_mismatch=allow_suite_mismatch,
            effort_a=effort_a,
            effort_b=effort_b,
        )
    except SuiteVersionMismatchError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    m._dispatch(report, formats, single_page=single_page,
                chart_lib=chart_lib,
                redact_user_prompts=redact_user_prompts,
                share_safe=share_safe)
    return report


# ---------------------------------------------------------------------------
# Capture protocol helper — ``--compare-prep`` (Phase 4)
# ---------------------------------------------------------------------------

def _compare_prep_protocol(model_a: str, model_b: str) -> str:
    """Capture-protocol header for ``--compare-prep`` output.

    Explains the model-switch dance, the prep steps that minimise
    confounds, and the `/model` verification step. Kept as a single
    string so it emits as one coherent block before the prompt list.
    """
    return (
        f"=== Compare capture protocol ({model_a} vs {model_b}) ===\n"
        f"\n"
        f"PREP — minimise confounds:\n"
        f"  - Run in a fresh, empty scratch directory (no large CLAUDE.md,\n"
        f"    no pre-existing project memory).\n"
        f"  - Ensure the same tool set is enabled in both sessions\n"
        f"    (Bash, Read, Write, etc.) — mismatches skew the tool-call ratio.\n"
        f"  - Do not resume sessions; start fresh each time.\n"
        f"\n"
        f"CAPTURE:\n"
        f"  1. Start a fresh Claude Code session.\n"
        f"  2. Run:     /model {model_a}\n"
        f"     Verify:  /model          (expect: {model_a!r})\n"
        f"  3. Paste each of the {_SUITE_VERSION_PROMPT_COUNT} prompts below in order;\n"
        f"     let each complete before pasting the next.\n"
        f"  4. Exit. Start a NEW fresh session.\n"
        f"  5. Run:     /model {model_b}\n"
        f"     Verify:  /model          (expect: {model_b!r})\n"
        f"  6. Paste the same prompts in the same order.\n"
        f"  7. Exit. Then run:\n"
        f"        session-metrics --compare last-<family-A> last-<family-B> --output md\n"
        f"\n"
        f"Suite version: v{_SUITE_VERSION}\n"
    )


# Number of prompts shipped in the canonical suite. Read once at module load
# from the suite dir so the protocol block stays honest when prompts are
# added or removed. Falls back to 10 (the Phase 4 design count) if the dir
# is missing — users without the packaged suite still get a sensible header.
def _count_suite_prompts() -> int:
    try:
        return len(_load_prompt_suite())
    except Exception:  # noqa: BLE001
        return 10


_SUITE_VERSION_PROMPT_COUNT = _count_suite_prompts()


def _run_compare_prep(
    models: list[str] | None,
    *,
    suite_dir: Path | None = None,
    out=None,
) -> None:
    """Emit the compare capture protocol + prompt suite to stdout.

    ``models`` may be empty (use defaults), have one entry (override A,
    keep default B), or two entries (override both). Prints the protocol,
    then each prompt's body wrapped with a ``>>> PROMPT n of N`` header so
    users can see progress while pasting into Claude Code.

    ``out`` defaults to ``sys.stdout``; tests pass a ``StringIO`` to
    capture output without spawning a subprocess.
    """
    if out is None:
        out = sys.stdout
    models = list(models) if models else []
    # Defaults match what Claude Code actually ships: both Opus 4.6 and
    # 4.7 route to their 1M-context tier (``[1m]``) unless the user picks
    # the 200k variant explicitly. Comparing ``[1m]`` vs ``[1m]`` therefore
    # reflects real-world usage, not a laboratory baseline.
    if len(models) == 0:
        model_a, model_b = "claude-opus-4-6[1m]", "claude-opus-4-7[1m]"
    elif len(models) == 1:
        model_a, model_b = models[0], "claude-opus-4-7[1m]"
    elif len(models) == 2:
        model_a, model_b = models[0], models[1]
    else:
        print(
            "[error] --compare-prep takes at most two model IDs",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        suite = _load_prompt_suite(suite_dir)
    except PromptSuiteError as exc:
        print(f"[error] prompt suite: {exc}", file=sys.stderr)
        sys.exit(1)
    if not suite:
        print("[error] prompt suite is empty or missing (expected under "
              f"{suite_dir or _PROMPT_SUITE_DIR})", file=sys.stderr)
        sys.exit(1)

    out.write(_compare_prep_protocol(model_a, model_b))
    out.write("\n")
    out.write(f"=== PROMPT SUITE (v{_SUITE_VERSION}, {len(suite)} prompts) ===\n")
    out.write("\n")

    # Preserve filename order (numeric prefixes on disk drive the canonical
    # sequence; _load_prompt_suite returns them sorted by stem).
    for i, (name, entry) in enumerate(suite.items(), 1):
        desc = entry["metadata"].get("description", "")
        out.write(f">>> PROMPT {i} of {len(suite)}: {name} <<<\n")
        if desc:
            out.write(f"({desc})\n")
        out.write("\n")
        out.write(entry["body"])
        out.write("\n\n")


# ---------------------------------------------------------------------------
# Phase 8 — count_tokens API mode
# ---------------------------------------------------------------------------
#
# Inference-free tokenizer comparison: hit POST /v1/messages/count_tokens for
# every prompt × model pair and compare input-token counts. Complements
# ``--compare`` (which needs two real sessions) with a shortcut that only
# needs an API key. Outputs are input-only by design — no inference runs,
# so output length and total cost cannot be measured this way.

_COUNT_TOKENS_URL = "https://api.anthropic.com/v1/messages/count_tokens"
_ANTHROPIC_API_VERSION = "2023-06-01"


class CountTokensError(Exception):
    """Raised by :func:`_count_tokens_request` for any non-success path.

    Carries the HTTP status / network error / malformed-body detail
    so the caller can decide between probe fallback (first-call 4xx on
    model A) and a hard error (repeated failure or transport error).
    """


def _count_tokens_request(
    model: str,
    prompt: str,
    *,
    api_key: str,
    url: str = _COUNT_TOKENS_URL,
    timeout: float = 30.0,
    urlopen=None,
) -> int:
    """POST /v1/messages/count_tokens for one ``(model, prompt)`` pair.

    Returns the server-reported ``input_tokens`` integer. Raises
    :class:`CountTokensError` on any non-2xx status, network error, or
    malformed response body — preserving enough detail for the probe
    fallback in :func:`_run_count_tokens_only` to distinguish
    model-unavailable from infra errors.

    ``urlopen`` override exists so tests inject a mock without global
    monkey-patching; defaults to ``urllib.request.urlopen``.
    """
    import urllib.error  # stdlib-only; lazy-imported so non-API-mode
    import urllib.request  # invocations don't pay the import cost.

    if urlopen is None:
        urlopen = urllib.request.urlopen
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body_bytes,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            response_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            detail = ""
        raise CountTokensError(
            f"HTTP {exc.code} calling count_tokens for model={model!r}: "
            f"{detail[:400]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise CountTokensError(
            f"network error calling count_tokens for model={model!r}: "
            f"{exc.reason}"
        ) from exc
    if status >= 400:
        raise CountTokensError(
            f"HTTP {status} calling count_tokens for model={model!r}"
        )
    try:
        data = json.loads(response_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CountTokensError(
            f"malformed count_tokens response for model={model!r}: {exc}"
        ) from exc
    tokens = data.get("input_tokens")
    if not isinstance(tokens, int):
        raise CountTokensError(
            f"missing 'input_tokens' in count_tokens response for "
            f"model={model!r}: got keys {sorted(data.keys())}"
        )
    return tokens


def _confirm_count_tokens_or_exit(
    models: list[str],
    prompt_count: int,
    *,
    assume_yes: bool,
    stdin=None,
) -> None:
    """Gate count-tokens mode behind explicit confirmation.

    Prints the total API-call count and waits for ``y`` unless
    ``assume_yes``. Non-TTY stdin without ``--yes`` is refused so
    scripted invocations don't silently burn rate-limit quota.

    ``stdin`` injection exists for tests; None means ``sys.stdin``.
    """
    if stdin is None:
        stdin = sys.stdin
    total_calls = len(models) * prompt_count
    print(
        f"About to call count_tokens: {prompt_count} prompt(s) × "
        f"{len(models)} model(s) = {total_calls} API call(s).",
        file=sys.stderr,
    )
    print(
        "count_tokens requests don't incur per-token charges, but each call "
        "counts against the account's request rate limit.",
        file=sys.stderr,
    )
    if assume_yes:
        print("(--yes given; proceeding)", file=sys.stderr)
        return
    if not getattr(stdin, "isatty", lambda: False)():
        print(
            "[error] --count-tokens-only requires --yes when stdin is not a "
            "TTY (prevents accidental rate-limit burn in scripts)",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        answer = input("Proceed? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n(aborted)", file=sys.stderr)
        sys.exit(0)
    if not answer.startswith("y"):
        print("(aborted)", file=sys.stderr)
        sys.exit(0)


def _render_count_tokens_text(
    results: list[dict],
    models: list[str],
    *,
    out,
    fallback_from: str | None = None,
) -> None:
    """Render the tokens-only comparison to ``out``.

    One row per prompt, one column per effective model, plus a ratio
    column (B/A) when exactly two models resolved. Footer carries the
    ratio summary (mean / p50 / p95) and the input-only disclaimer so
    the user doesn't misread this as a full cost comparison.

    ``fallback_from`` is set when the probe rejected the first model
    and counting collapsed to a single model — surfaced in the footer
    so the empty column isn't mysterious.
    """
    if not results:
        out.write("(no prompts in suite — nothing to count)\n")
        return

    is_pair = len(models) == 2

    prompt_col = max(
        max(len(r["name"]) for r in results),
        len("Prompt"),
    )
    col_width = 22

    header = f"{'Prompt':<{prompt_col}}"
    for m in models:
        header += "  " + f"{m:>{col_width}}"
    if is_pair:
        header += "  " + f"{'Ratio B/A':>12}"
    out.write(header + "\n")
    out.write("-" * len(header) + "\n")

    ratios: list[float] = []
    for r in results:
        row = f"{r['name']:<{prompt_col}}"
        for m in models:
            val = r["tokens_by_model"].get(m)
            cell = str(val) if val is not None else "—"
            row += "  " + f"{cell:>{col_width}}"
        if is_pair:
            a = r["tokens_by_model"].get(models[0])
            b = r["tokens_by_model"].get(models[1])
            if a is not None and b is not None and a > 0:
                ratio = b / a
                ratios.append(ratio)
                row += "  " + f"{ratio:>11.2f}×"
            else:
                row += "  " + f"{'—':>12}"
        out.write(row + "\n")

    out.write("\n")
    if is_pair and ratios:
        n = len(ratios)
        rsorted = sorted(ratios)
        mean = sum(rsorted) / n
        p50 = rsorted[n // 2]
        # For short suites (<20 prompts) fall back to max as the p95
        # proxy — the true 95th percentile on 10 samples is ill-defined.
        p95 = rsorted[-1] if n < 20 else rsorted[int(round(n * 0.95)) - 1]
        out.write(
            f"Ratio summary (B/A): mean={mean:.2f}×  p50={p50:.2f}×  "
            f"p95={p95:.2f}×\n"
        )
    elif fallback_from is not None:
        out.write(
            f"[info] counted against {models[0]!r} only — {fallback_from!r} "
            "was rejected by the API. Ratios not computable from this mode; "
            "run --compare against two actual sessions for a full comparison.\n"
        )

    out.write("\n")
    out.write(
        "NOTE: count_tokens measures INPUT tokens only. No inference runs, "
        "so output length and total cost cannot be compared this way. "
        "For a full cost comparison, run --compare against two actual "
        "Claude Code sessions.\n"
    )


def _run_count_tokens_only(
    models: list[str] | None,
    *,
    suite_dir: Path | None = None,
    assume_yes: bool = False,
    api_key: str | None = None,
    urlopen=None,
    stdin=None,
    out=None,
) -> None:
    """Entrypoint for ``--count-tokens-only``.

    Calls ``POST /v1/messages/count_tokens`` for every prompt in the
    canonical suite against each of the (up to two) models in
    ``models``. Prints a tokens-only table to ``out`` (stdout).

    Probe fallback: attempts the first model with the first prompt.
    If that call fails, the mode collapses to counting the second
    model only and emits a friendly explanation pointing at
    ``--compare`` as the alternative. This handles the common case
    of a deprecated baseline (``claude-opus-4-6``) no longer being
    accessible via the API even though the reference suite names it.

    Requires ``ANTHROPIC_API_KEY`` env var unless ``api_key`` is
    injected (tests). Missing key → clear error, exit 1.

    ``urlopen`` / ``stdin`` / ``out`` / ``api_key`` are test seams —
    production callers leave them ``None``.
    """
    import os

    if out is None:
        out = sys.stdout
    if api_key is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "[error] --count-tokens-only requires ANTHROPIC_API_KEY env var "
            "(the /v1/messages/count_tokens endpoint needs an API key). Set "
            "it and re-run, or use --compare against two real sessions for a "
            "cost-aware comparison.",
            file=sys.stderr,
        )
        sys.exit(1)

    models = list(models) if models else []
    if len(models) == 0:
        models = ["claude-opus-4-6", "claude-opus-4-7"]
    elif len(models) == 1:
        print(
            f"[info] only one model provided ({models[0]}); ratios will not "
            "be computed.",
            file=sys.stderr,
        )
    elif len(models) > 2:
        print(
            "[error] --compare-models takes at most two model IDs",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        suite = _load_prompt_suite(suite_dir)
    except PromptSuiteError as exc:
        print(f"[error] prompt suite: {exc}", file=sys.stderr)
        sys.exit(1)
    if not suite:
        print(
            "[error] prompt suite is empty or missing (expected under "
            f"{suite_dir or _PROMPT_SUITE_DIR})",
            file=sys.stderr,
        )
        sys.exit(1)

    _confirm_count_tokens_or_exit(
        models, len(suite), assume_yes=assume_yes, stdin=stdin,
    )

    effective_models = list(models)
    fallback_from: str | None = None

    # Probe model A with the first prompt. If it fails, fall back to
    # counting B only (assuming we had a pair — single-model invocations
    # skip probing since there's nothing to fall back to).
    if len(effective_models) == 2:
        first_name = next(iter(suite))
        first_body = suite[first_name]["body"]
        try:
            _count_tokens_request(
                effective_models[0], first_body,
                api_key=api_key, urlopen=urlopen,
            )
        except CountTokensError as exc:
            print(
                f"[info] model {effective_models[0]!r} is not accessible to "
                f"this API key (probe failed: {exc}).",
                file=sys.stderr,
            )
            print(
                f"[info] falling back to counting tokens against "
                f"{effective_models[1]!r} only. For a full baseline "
                "comparison, run --compare against two actual sessions.",
                file=sys.stderr,
            )
            fallback_from = effective_models[0]
            effective_models = [effective_models[1]]

    results: list[dict] = []
    for name, entry in suite.items():
        tokens_by_model: dict[str, int] = {}
        for m in effective_models:
            try:
                tokens_by_model[m] = _count_tokens_request(
                    m, entry["body"], api_key=api_key, urlopen=urlopen,
                )
            except CountTokensError as exc:
                print(
                    f"[warn] count_tokens failed for prompt={name!r} "
                    f"model={m!r}: {exc}",
                    file=sys.stderr,
                )
        results.append({
            "name": name,
            "tokens_by_model": tokens_by_model,
        })

    _render_count_tokens_text(
        results, effective_models, out=out, fallback_from=fallback_from,
    )


# ---------------------------------------------------------------------------
# Phase 10 — Automated headless capture (``--compare-run``)
# ---------------------------------------------------------------------------
#
# One-command alternative to the manual capture protocol in
# ``references/model-compare.md``. Spawns two ``claude -p`` (headless)
# sessions — one per model — feeds each the canonical prompt suite, then
# hands the resulting JSONL pair off to the existing :func:`_run_compare`
# renderer. Designed for subscription-plan users who want zero variance
# between sides: same prompts, same order, same tool set, same working
# directory, no human-in-the-loop typos.
#
# Why not run this from inside an interactive Claude Code session? The
# headless docs are explicit that user-invoked skills aren't available
# under ``-p``. So the orchestrator runs from a plain shell, spawns
# ``claude -p`` sub-processes itself, and reads the JSONLs Claude Code
# writes to ``~/.claude/projects/<slug>/`` as a side effect.

_DEFAULT_COMPARE_RUN_ALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep"
_DEFAULT_COMPARE_RUN_PERMISSION_MODE = "bypassPermissions"
_DEFAULT_COMPARE_RUN_TIMEOUT_SEC = 900.0  # 15 min / prompt; tool-heavy #5 is slowest

# Valid ``claude -p --effort`` values. Kept in sync with Claude Code's own
# enum — mismatches would cause a cryptic subprocess error mid-capture. Opus
# 4.6 defaults to ``high`` and Opus 4.7 defaults to ``xhigh`` when the flag
# is omitted; passing ``None`` here (the default) preserves that per-model
# behaviour so A/B runs across model versions stay apples-to-apples by
# default. Override per-side via ``--compare-run-effort`` when pinning both
# sides to a common level matters more than matching each model's default.
_COMPARE_RUN_EFFORT_LEVELS = frozenset({"low", "medium", "high", "xhigh", "max"})

# Prompt-steering variants applied symmetrically to both sides of a
# ``--compare-run`` so the A/B stays clean. Each variant supplies a ``prefix``
# (prepended to the prompt body) and a ``suffix`` (appended); ``--compare-run-
# prompt-steering-position`` selects which one(s) to actually wrap with. The
# wrapper is opt-in — when ``steering_variant`` is None, the behaviour is
# byte-identical to the pre-flag pipeline.
#
# Phrasings are pulled from Anthropic's prompting best-practices guide where
# a canonical sentence exists for the steer, and Anthropic-style approximations
# elsewhere. Source:
# https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
#
# Caveat on the thinking-word variants: that doc notes Claude Opus 4.5 is
# particularly sensitive to the word "think" and its variants when extended
# thinking is *disabled* — which means the ``think-step-by-step`` and
# ``ultrathink`` deltas measured by the benchmark will be larger when
# adaptive thinking is on (the default for 4.6/4.7) than when it is off.
# When interpreting the benchmark, treat thinking-related variants as
# conditional on the model's thinking configuration.
_PROMPT_STEERING_VARIANTS: dict[str, dict[str, str]] = {
    "concise": {
        # Verbatim from Anthropic's "Response length and verbosity" section.
        "prefix": (
            "Provide concise, focused responses. Skip non-essential context, "
            "and keep examples minimal."
        ),
        "suffix": "Keep your response as short as possible.",
    },
    "think-step-by-step": {
        # Verbatim from Anthropic's "Calibrating effort and thinking depth"
        # section — the recommended targeted-guidance phrasing when raising
        # the effort parameter isn't an option.
        "prefix": (
            "This task involves multi-step reasoning. Think carefully "
            "through the problem before responding."
        ),
        "suffix": "Show your reasoning step by step.",
    },
    "ultrathink": {
        # Anthropic's guide doesn't use the literal "ultrathink" phrase
        # (that is a Claude Code CLI magic word, not a docs-recommended
        # steer). The closest canonical formulation in the guide is
        # "think harder / think thoroughly", combined here so the variant
        # tests both an escalation phrase and an extended-reasoning cue.
        "prefix": (
            "Think harder and more thoroughly about this problem. Use "
            "extended reasoning before responding."
        ),
        "suffix": "Take time to reason carefully before answering.",
    },
    "no-tools": {
        # No direct canonical phrasing in Anthropic's guide for prompt-level
        # tool suppression — the guide focuses on encouraging appropriate
        # tool USE rather than blanket suppression. Phrasing here is a
        # neutral Anthropic-style instruction; if you find this variant
        # under-triggers, the next thing to try is adding "even if you
        # think a tool would help" to make the override more decisive.
        "prefix": (
            "Do not invoke any tools. Answer from your own knowledge and "
            "reasoning only."
        ),
        "suffix": "Do not invoke any tools to produce this answer.",
    },
}

_PROMPT_STEERING_POSITIONS = frozenset({"prefix", "append", "both"})


def _apply_steering(
    body: str,
    variant: str | None,
    position: str = "prefix",
) -> str:
    """Wrap a prompt body with steering text per the selected variant/position.

    Returns the body unchanged when ``variant`` is None or empty — that
    pre-flag-equivalent path keeps the no-flag baseline byte-identical so
    JSONL fingerprints don't drift for users who never opt in. Raises
    ``KeyError`` for unknown variants and ``ValueError`` for unknown
    positions; both are pre-flight conditions the CLI dispatcher validates
    before any subprocess fires.
    """
    if not variant:
        return body
    v = _PROMPT_STEERING_VARIANTS[variant]
    if position == "prefix":
        return f"{v['prefix']}\n\n{body}"
    if position == "append":
        return f"{body}\n\n{v['suffix']}"
    if position == "both":
        return f"{v['prefix']}\n\n{body}\n\n{v['suffix']}"
    raise ValueError(f"unknown steering position: {position!r}")


class CompareRunError(RuntimeError):
    """Raised when the ``--compare-run`` orchestrator can't continue.

    Covers three failure classes: ``claude`` binary not on PATH, a
    non-zero exit from a ``claude -p`` subprocess, or a JSON parse
    failure on the subprocess stdout. The caller catches and prints
    to stderr with exit 1 — partial JSONLs from the prior prompts are
    left in place so the user can inspect or resume.
    """


def _claude_headless_call(
    prompt: str,
    *,
    model: str,
    session_id: str,
    is_first_turn: bool,
    cwd: Path,
    allowed_tools: str,
    permission_mode: str | None,
    max_budget_usd: float | None,
    timeout: float,
    subprocess_run,
    effort: str | None = None,
) -> dict:
    """Shell out to ``claude -p`` for one prompt and return the parsed JSON result.

    First-turn invocations pass ``--session-id <uuid>`` to seed the JSONL
    filename deterministically; continuation turns pass ``--resume <uuid>``
    so all turns append to the same file. ``--output-format json`` gives us
    ``{session_id, result, usage, total_cost_usd, ...}`` on stdout for
    cost telemetry and success confirmation.

    ``effort`` — when non-None, threaded as ``--effort <level>`` so the
    subprocess pins reasoning effort (low/medium/high/xhigh/max). Leave as
    ``None`` to let Claude Code apply its per-model default (opus-4-6 →
    high, opus-4-7 → xhigh), which keeps cross-version A/B runs faithful
    to how each model actually ships by default.

    Raises :class:`CompareRunError` on FileNotFoundError (claude not on
    PATH), non-zero returncode, or stdout that doesn't parse as JSON.

    ``subprocess_run`` injection is a test seam; production callers pass
    ``subprocess.run``.
    """
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json"]
    if is_first_turn:
        cmd += ["--session-id", session_id]
    else:
        cmd += ["--resume", session_id]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", str(max_budget_usd)]
    if effort:
        cmd += ["--effort", effort]
    try:
        result = subprocess_run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CompareRunError(
            "'claude' binary not found on PATH — install Claude Code first "
            "or run from a shell where the CLI is reachable."
        ) from exc
    if result.returncode != 0:
        raise CompareRunError(
            f"claude -p failed for model={model!r} "
            f"(returncode={result.returncode}). "
            f"stderr[:400]={(result.stderr or '')[:400]!r}"
        )
    try:
        return json.loads(result.stdout or "")
    except json.JSONDecodeError as exc:
        raise CompareRunError(
            f"claude -p returned non-JSON output for model={model!r}: {exc}. "
            f"stdout[:200]={(result.stdout or '')[:200]!r}"
        ) from exc


def _run_compare_side(
    model: str,
    session_id: str,
    suite: dict,
    *,
    cwd: Path,
    allowed_tools: str,
    permission_mode: str | None,
    max_budget_usd: float | None,
    timeout: float,
    subprocess_run,
    progress_out,
    effort: str | None = None,
    steering_variant: str | None = None,
    steering_position: str = "prefix",
) -> list[dict]:
    """Feed the full prompt suite into one model via ``claude -p``.

    Loops ``suite`` in iteration order (which matches filename order on
    disk). First iteration uses ``--session-id``; later iterations use
    ``--resume`` against the same UUID so every turn lands in a single
    JSONL at ``~/.claude/projects/<slug-of-cwd>/<session_id>.jsonl``.

    ``steering_variant`` / ``steering_position`` — when ``steering_variant``
    is non-None, every prompt body is wrapped via :func:`_apply_steering`
    before reaching the subprocess. Both sides get the same wrapper so the
    A/B comparison stays clean. The compare-suite sentinel sits inside the
    body and survives the wrap; pairing logic is unaffected.

    Returns the list of per-prompt JSON results from stdout (for
    diagnostics / rollup). Raises :class:`CompareRunError` on the
    first failure — the partial JSONL is left on disk for inspection.
    """
    results: list[dict] = []
    prompts = list(suite.items())
    total = len(prompts)
    for i, (name, entry) in enumerate(prompts, 1):
        progress_out.write(
            f"  [{model}] prompt {i}/{total}: {name}\n"
        )
        progress_out.flush()
        steered_body = _apply_steering(
            entry["body"], steering_variant, steering_position,
        )
        out_json = _claude_headless_call(
            steered_body,
            model=model,
            session_id=session_id,
            is_first_turn=(i == 1),
            cwd=cwd,
            allowed_tools=allowed_tools,
            permission_mode=permission_mode,
            max_budget_usd=max_budget_usd,
            timeout=timeout,
            subprocess_run=subprocess_run,
            effort=effort,
        )
        results.append({"name": name, "response": out_json})
    return results


def _confirm_compare_run_or_exit(
    model_a: str,
    model_b: str,
    prompt_count: int,
    *,
    scratch_dir: Path,
    assume_yes: bool,
    stdin=None,
    effort_a: str | None = None,
    effort_b: str | None = None,
    steering_variant: str | None = None,
    steering_position: str = "prefix",
) -> None:
    """Confirmation gate before firing 2 × N headless inference calls.

    Mirrors :func:`_confirm_count_tokens_or_exit` — ``--yes`` bypass,
    non-TTY stdin without ``--yes`` is a hard refusal, interactive prompt
    defaults to no. Unlike count-tokens mode, each call here runs full
    inference and burns real subscription quota, so the message
    emphasises that rather than rate-limit requests. ``effort_a`` /
    ``effort_b`` surface on the model line only when set — silent fallback
    to Claude Code's per-model defaults preserves the existing output
    shape for the no-flag case. ``steering_variant`` surfaces on its own
    line under the same conditional so the no-flag baseline banner is
    unchanged.
    """
    if stdin is None:
        stdin = sys.stdin
    total_calls = 2 * prompt_count
    print(
        f"About to run --compare-run: {prompt_count} prompts × 2 models = "
        f"{total_calls} headless Claude Code invocations.",
        file=sys.stderr,
    )
    suffix_a = f" (effort={effort_a})" if effort_a else ""
    suffix_b = f" (effort={effort_b})" if effort_b else ""
    print(
        f"  Side A: {model_a}{suffix_a}   Side B: {model_b}{suffix_b}",
        file=sys.stderr,
    )
    if steering_variant:
        print(
            f"  Steering: {steering_variant} ({steering_position}) — "
            f"applied symmetrically to both sides; IFEval pass rates may "
            f"differ from unsteered baseline.",
            file=sys.stderr,
        )
    print(
        f"  Scratch dir: {scratch_dir}",
        file=sys.stderr,
    )
    print(
        "Each call runs full inference and counts against your subscription "
        "quota / rate limit.",
        file=sys.stderr,
    )
    if assume_yes:
        print("(--yes given; proceeding)", file=sys.stderr)
        return
    if not getattr(stdin, "isatty", lambda: False)():
        print(
            "[error] --compare-run requires --yes when stdin is not a TTY "
            "(prevents surprise quota burn in scripts).",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        answer = input("Proceed? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n(aborted)", file=sys.stderr)
        sys.exit(0)
    if not answer.startswith("y"):
        print("(aborted)", file=sys.stderr)
        sys.exit(0)


def _run_compare_run(
    model_a: str,
    model_b: str,
    *,
    scratch_dir: Path | None = None,
    suite_dir: Path | None = None,
    assume_yes: bool = False,
    allowed_tools: str = _DEFAULT_COMPARE_RUN_ALLOWED_TOOLS,
    permission_mode: str | None = _DEFAULT_COMPARE_RUN_PERMISSION_MODE,
    max_budget_usd: float | None = None,
    per_call_timeout: float = _DEFAULT_COMPARE_RUN_TIMEOUT_SEC,
    formats: list[str] | None = None,
    single_page: bool = False,
    chart_lib: str = "highcharts",
    redact_user_prompts: bool = False,
    share_safe: bool = False,
    tz_offset: float = 0.0,
    tz_label: str = "UTC",
    use_cache: bool = True,
    include_subagents: bool = False,
    pair_by: str = "fingerprint",
    min_turns: int = 5,
    allow_suite_mismatch: bool = False,
    subprocess_run=None,
    uuid_factory=None,
    stdin=None,
    progress_out=None,
    tempfile_mkdtemp=None,
    auto_resume: bool = True,
    compare_run_extras: bool = True,
    effort_a: str | None = None,
    effort_b: str | None = None,
    steering_variant: str | None = None,
    steering_position: str = "prefix",
) -> dict:
    """Orchestrator for ``--compare-run``: capture both sides, then compare.

    End-to-end flow:

    1. Resolve or create a scratch directory. Every ``claude -p``
       subprocess runs with this as cwd, which determines the project
       slug Claude Code writes to.
    2. Load the canonical prompt suite and gate on user confirmation
       (``--yes`` bypass; non-TTY refusal without it).
    3. For each side, mint a fresh UUID and pump the 10 prompts
       through ``claude -p --session-id <uuid>`` (first) then
       ``claude -p --resume <uuid>`` (remaining). Each side's turns
       land in a single JSONL under
       ``~/.claude/projects/<slug>/<uuid>.jsonl``.
    4. Hand the two UUIDs off to :func:`_run_compare` — the same
       renderer the manual Workflow A uses. User sees the same HTML /
       Markdown / JSON report at the end either way.

    All the I/O-ish surfaces (subprocess, uuid, tempfile, stdin,
    progress output) are injected so tests can exercise the whole
    orchestrator without spawning real processes. Returns a small
    diagnostic dict (used by tests; the CLI caller ignores it).
    """
    import subprocess as _subprocess  # stdlib-only; lazy-loaded
    import tempfile as _tempfile
    import uuid as _uuid

    if subprocess_run is None:
        subprocess_run = _subprocess.run
    if uuid_factory is None:
        uuid_factory = lambda: str(_uuid.uuid4())  # noqa: E731
    if tempfile_mkdtemp is None:
        tempfile_mkdtemp = lambda: Path(  # noqa: E731
            _tempfile.mkdtemp(prefix="sm-compare-run-")
        )
    if progress_out is None:
        progress_out = sys.stderr
    formats = formats or []

    # Effort levels: validate before we burn any subprocess calls. Empty
    # string is a no-op so the CLI dispatcher can normalise ``""`` → ``None``
    # without a branch, mirroring the permission-mode opt-out convention.
    for label, level in (("A", effort_a), ("B", effort_b)):
        if level in (None, ""):
            continue
        if level not in _COMPARE_RUN_EFFORT_LEVELS:
            print(
                f"[error] --compare-run-effort side {label}: {level!r} is "
                f"not a valid effort level. Expected one of: "
                f"{', '.join(sorted(_COMPARE_RUN_EFFORT_LEVELS))}.",
                file=sys.stderr,
            )
            sys.exit(1)
    effort_a = effort_a or None
    effort_b = effort_b or None

    # Steering: validate variant + position before any subprocess fires. Empty
    # string normalises to None so the CLI can stay branch-free, mirroring the
    # effort-level pattern above.
    if steering_variant in (None, ""):
        steering_variant = None
    elif steering_variant not in _PROMPT_STEERING_VARIANTS:
        print(
            f"[error] --compare-run-prompt-steering: {steering_variant!r} is "
            f"not a known variant. Expected one of: "
            f"{', '.join(sorted(_PROMPT_STEERING_VARIANTS))}.",
            file=sys.stderr,
        )
        sys.exit(1)
    if steering_position not in _PROMPT_STEERING_POSITIONS:
        print(
            f"[error] --compare-run-prompt-steering-position: "
            f"{steering_position!r} is not valid. Expected one of: "
            f"{', '.join(sorted(_PROMPT_STEERING_POSITIONS))}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 1: scratch dir. Resolve symlinks (``/tmp`` → ``/private/tmp`` on
    # macOS) so the slug we compute later matches what Claude Code derives
    # from its own cwd when the subprocess runs — otherwise the JSONLs land
    # in one project dir and we look for them in another.
    if scratch_dir is None:
        scratch_dir = Path(tempfile_mkdtemp()).resolve()
    else:
        scratch_dir = Path(scratch_dir).expanduser().resolve()
        scratch_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: prompt suite + confirmation gate
    try:
        suite = _load_prompt_suite(suite_dir)
    except PromptSuiteError as exc:
        print(f"[error] prompt suite: {exc}", file=sys.stderr)
        sys.exit(1)
    if not suite:
        print(
            "[error] prompt suite is empty or missing (expected under "
            f"{suite_dir or _PROMPT_SUITE_DIR})",
            file=sys.stderr,
        )
        sys.exit(1)

    _confirm_compare_run_or_exit(
        model_a, model_b, len(suite),
        scratch_dir=scratch_dir, assume_yes=assume_yes, stdin=stdin,
        effort_a=effort_a, effort_b=effort_b,
        steering_variant=steering_variant,
        steering_position=steering_position,
    )

    # Step 3: capture side A then side B
    side_uuids: dict[str, str] = {}
    for side_label, model, side_effort in (
        ("A", model_a, effort_a), ("B", model_b, effort_b),
    ):
        session_id = uuid_factory()
        side_uuids[side_label] = session_id
        effort_suffix = f"  effort={side_effort}" if side_effort else ""
        print(
            f"\n=== Side {side_label}: {model}  session_id={session_id}"
            f"{effort_suffix} ===",
            file=progress_out,
        )
        try:
            _run_compare_side(
                model, session_id, suite,
                cwd=scratch_dir,
                allowed_tools=allowed_tools,
                permission_mode=permission_mode,
                max_budget_usd=max_budget_usd,
                timeout=per_call_timeout,
                subprocess_run=subprocess_run,
                progress_out=progress_out,
                effort=side_effort,
                steering_variant=steering_variant,
                steering_position=steering_position,
            )
        except CompareRunError as exc:
            print(f"[error] side {side_label} ({model}): {exc}", file=sys.stderr)
            print(
                f"[info] partial JSONL (if any) remains at "
                f"~/.claude/projects/<slug>/{session_id}.jsonl — inspect or "
                f"re-run once the cause is fixed. scratch_dir={scratch_dir}",
                file=sys.stderr,
            )
            sys.exit(1)

    # Step 4: hand off to the existing compare renderer
    m = _main()
    if hasattr(m, "_cwd_to_slug"):
        slug = m._cwd_to_slug(str(scratch_dir))
    else:
        # Fall back: compute slug the same way the main module does.
        slug = str(scratch_dir).replace("/", "-")

    print(
        f"\n=== Capture complete. Rendering compare report "
        f"(A={side_uuids['A']}, B={side_uuids['B']}) ===",
        file=progress_out,
    )
    extras_paths: dict | None = None
    if auto_resume:
        compare_report = _run_compare(
            side_uuids["A"], side_uuids["B"],
            slug=slug,
            pair_by=pair_by,
            compare_scope="session",
            min_turns=min_turns,
            formats=formats,
            tz_offset=tz_offset,
            tz_label=tz_label,
            include_subagents=include_subagents,
            use_cache=use_cache,
            single_page=single_page,
            chart_lib=chart_lib,
            assume_yes=True,
            prompt_suite_dir=suite_dir,
            allow_suite_mismatch=allow_suite_mismatch,
            redact_user_prompts=redact_user_prompts,
            share_safe=share_safe,
            effort_a=effort_a,
            effort_b=effort_b,
        )
        # Extras: per-session dashboards + analysis.md scaffold. Gated on
        # (1) compare_run_extras (--no-compare-run-extras opts out),
        # (2) formats (no user-requested file outputs → stay text-only),
        # (3) compare_report is not None (defensive; _run_compare may
        # short-circuit on the no-overlap path before building a report).
        if compare_run_extras and formats and compare_report is not None:
            try:
                extras_paths = _emit_compare_run_extras(
                    compare_report,
                    side_uuids["A"],
                    side_uuids["B"],
                    slug,
                    formats=formats,
                    single_page=single_page,
                    chart_lib=chart_lib,
                    tz_offset=tz_offset,
                    tz_label=tz_label,
                    include_subagents=include_subagents,
                    use_cache=use_cache,
                    progress_out=progress_out,
                    share_safe=share_safe,
                )
            except Exception as exc:  # noqa: BLE001
                # Never fail the whole compare-run because extras emission
                # hiccupped — the primary compare report already landed.
                print(
                    f"[warn] compare-run extras emission failed: {exc}",
                    file=sys.stderr,
                )

    result = {
        "scratch_dir": str(scratch_dir),
        "slug": slug,
        "side_a_session_id": side_uuids["A"],
        "side_b_session_id": side_uuids["B"],
        "suite_prompt_count": len(suite),
    }
    if extras_paths is not None:
        result["extras"] = extras_paths
    return result


# ---------------------------------------------------------------------------
# --compare-run extras (Phase 8): per-session dashboards + analysis.md
# ---------------------------------------------------------------------------
#
# After every ``compare-run``, users were running the same three follow-up
# steps by hand: find the two captured JSONLs, render each side's dashboard
# through the single-session entrypoint, and draft a Substack-style analysis
# article over the numbers. The deterministic 80% of that workflow lives
# here; the prose 20% stays as ``{{TODO}}`` placeholders the user can fill
# in a follow-up turn.
#
# The extras are opt-in at the CLI level only via ``--no-compare-run-extras``
# — when ``compare-run`` is invoked with ``--output`` and without that flag,
# the 5 companion artefacts land alongside the compare report automatically.


def _decision_framework_verdict(
    cost_ratio: float | None,
    ifeval_delta_pp: float | None,
) -> dict:
    """Map (cost_ratio, IFEval Δ pp) to a decision-framework verdict.

    Mirror of the table in
    ``references/model-compare.md:421-429``. Threshold drift between
    this table and the docs is a bug — if you bump thresholds here,
    bump the doc row and vice versa. ``analysis.md`` re-prints the
    doc table alongside the verdict row so readers can audit the
    match.

    Returns ``{"bucket": <slug>, "verdict": <sentence>,
    "explanation": <short reason>}``. ``bucket`` is stable for
    diffing tests / tooling. ``no-ratio`` covers the edge case
    where side A had zero cost (division-by-zero); ``no-ifeval``
    covers observational compares and aborted suite runs where no
    predicates fired.
    """
    if cost_ratio is None:
        return {
            "bucket": "no-ratio",
            "verdict": "cannot auto-classify",
            "explanation": (
                "side A has no billable cost so no ratio is defined; "
                "inspect the raw totals manually"
            ),
        }

    if ifeval_delta_pp is None:
        # Cost-only verdicts still reveal the cheapest-of-the-two
        # rows (≤1.05× "Switch") and the most-expensive row (≥1.45×
        # "Stay"). Anything in between is a workload-dependent
        # judgment that needs IFEval data to resolve.
        if cost_ratio <= 1.05:
            return {
                "bucket": "no-ifeval-cheap",
                "verdict": "switch — minimal cost impact",
                "explanation": (
                    "cost ratio ≤1.05× means the newer model is "
                    "essentially free to adopt regardless of quality "
                    "delta; no IFEval data needed"
                ),
            }
        if cost_ratio >= 1.45:
            return {
                "bucket": "no-ifeval-expensive",
                "verdict": "stay, or use selectively",
                "explanation": (
                    "cost ratio ≥1.45× means the newer model is a "
                    "material spend increase; without IFEval data "
                    "there is no case for a blanket switch"
                ),
            }
        return {
            "bucket": "no-ifeval",
            "verdict": "cannot auto-classify",
            "explanation": (
                "this compare has no IFEval predicate results "
                "(observational or non-suite capture); the 1.05×–1.45× "
                "cost band is workload-dependent and needs a quality "
                "signal to resolve"
            ),
        }

    # Controlled compare with IFEval data — map against the full 5-row
    # table. Each predicate is written as a strict boundary that matches
    # the doc wording ("+5 pp or more", "±2 pp", "+10 pp or more").
    if cost_ratio <= 1.05:
        return {
            "bucket": "cheap",
            "verdict": "switch — minimal cost impact",
            "explanation": (
                f"cost ratio {cost_ratio:.2f}× is within noise; quality "
                f"delta ({ifeval_delta_pp:+.1f} pp) is not load-bearing"
            ),
        }
    if 1.05 < cost_ratio <= 1.20:
        if ifeval_delta_pp >= 5.0:
            return {
                "bucket": "mid-quality-win",
                "verdict": "switch if quality matters",
                "explanation": (
                    f"cost ratio {cost_ratio:.2f}× is a moderate premium "
                    f"offset by a +{ifeval_delta_pp:.1f} pp quality lift "
                    f"— worth it when the workload rewards compliance"
                ),
            }
        if abs(ifeval_delta_pp) <= 2.0:
            return {
                "bucket": "mid-flat",
                "verdict": "workload-dependent — test with your own content",
                "explanation": (
                    f"cost ratio {cost_ratio:.2f}× with a flat quality "
                    f"delta ({ifeval_delta_pp:+.1f} pp) is suite-agnostic; "
                    f"the canonical suite doesn't resolve this band"
                ),
            }
        # Between ±2 and +5 pp — the doc table doesn't list this cell
        # explicitly. Fall through to workload-dependent with a
        # gap-acknowledgement explanation.
        return {
            "bucket": "mid-gap",
            "verdict": "workload-dependent",
            "explanation": (
                f"cost ratio {cost_ratio:.2f}× with quality delta "
                f"{ifeval_delta_pp:+.1f} pp falls between the table's "
                f"±2 pp row and +5 pp row; lean on workload evidence"
            ),
        }
    if 1.20 < cost_ratio <= 1.45:
        if ifeval_delta_pp >= 10.0:
            return {
                "bucket": "expensive-big-quality",
                "verdict": "trade-off call — model your spend at the new ratio",
                "explanation": (
                    f"cost ratio {cost_ratio:.2f}× is a substantial "
                    f"premium, but +{ifeval_delta_pp:.1f} pp IFEval "
                    f"gain is large enough to rationalise on "
                    f"quality-sensitive workloads"
                ),
            }
        return {
            "bucket": "expensive-gap",
            "verdict": "workload-dependent — quality lift doesn't clearly pay for the cost",
            "explanation": (
                f"cost ratio {cost_ratio:.2f}× with quality delta "
                f"{ifeval_delta_pp:+.1f} pp sits below the +10 pp "
                f"threshold the doc table flags as a trade-off call"
            ),
        }
    # cost_ratio > 1.45
    return {
        "bucket": "very-expensive",
        "verdict": "stay, or use the newer model selectively",
        "explanation": (
            f"cost ratio {cost_ratio:.2f}× is prohibitive for a blanket "
            f"switch regardless of quality delta ({ifeval_delta_pp:+.1f} "
            f"pp); prefer selective use (e.g. code review only)"
        ),
    }


def _analysis_link(href: str | None, label: str) -> str:
    """Render an analysis.md link cell — em-dash when href is missing."""
    if not href:
        return f"_{label} not available_"
    return f"[{label}]({href})"


def _analysis_fmt_ratio_cell(value: float | None, precision: int = 2) -> str:
    """Ratio cell — defers to the existing formatter, just a shorter alias."""
    return _fmt_ratio(value, precision=precision)


def _analysis_fmt_pp_cell(value: float | None, precision: int = 1) -> str:
    """Percentage-point delta cell that tolerates None."""
    if value is None:
        return "n/a"
    return _fmt_delta_pp(value, precision=precision)


def _analysis_fmt_cost_delta_abs(a_cost: float, b_cost: float) -> str:
    """Absolute cost delta in USD (B − A) with sign."""
    delta = b_cost - a_cost
    sign = "+" if delta >= 0 else ""
    return f"{sign}${delta:.4f}"


def _analysis_first_turn_cache_write(session_report: dict) -> int:
    """First turn's cache-write tokens (system-prompt encoding proxy)."""
    sessions = session_report.get("sessions") or []
    if not sessions:
        return 0
    turns = sessions[0].get("turns") or []
    if not turns:
        return 0
    return int(turns[0].get("cache_write_tokens", 0) or 0)


def _render_compare_analysis_md(
    compare_report: dict,
    session_a_report: dict,
    session_b_report: dict,
    links: dict,
) -> str:
    """Render the Substack-style compare analysis Markdown scaffold.

    The ~80% deterministic part is generated here from the compare
    report + per-session reports; the prose ~20% stays as
    ``{{TODO}}`` placeholders the author fills in a follow-up turn.

    ``links`` carries relative hrefs to the compare HTML, per-session
    dashboards/detail pages, and per-session JSONs that live in the
    same ``exports/session-metrics/`` directory. Missing keys fall
    through to a polite "not available" cell so an ``--output md``
    run (no HTML emitted) still produces a valid article.

    Section layout (13 sections):

    1. Title + subtitle with ``{{TODO}}`` hooks
    2. TL;DR auto headline ratios + decision verdict
    3. Methodology — models, sessions, suite version, prompt list
    4. The numbers — per-session totals side-by-side + per-prompt table
    5. Where does the cost come from? — cache-write / cache-read /
       output / user-prompt-input decomposition
    6. Extended thinking usage — counts per side + ``{{TODO}}``
    7. Advisories — auto bullet list
    8. Should I switch? — embedded decision table + bolded row
    9. Caveats — boilerplate port of five items from
       ``model-compare.md``
    10. Reproduce it yourself — the ``compare-run`` command + manual
        fallback note
    11. Links — relative hrefs to the 6 artefacts + upstream repo
    12. Footer — run timestamp + skill-version pointer
    """
    out = io.StringIO()

    def p(*args, **kw):
        print(*args, **kw, file=out)

    a = compare_report.get("side_a") or {}
    b = compare_report.get("side_b") or {}
    s = compare_report.get("summary") or {}
    paired = compare_report.get("paired") or []
    advisories = compare_report.get("advisories") or []

    a_model = a.get("dominant_model_id") or "side-A model"
    b_model = b.get("dominant_model_id") or "side-B model"
    a_family = a.get("model_family") or a_model
    b_family = b.get("model_family") or b_model
    a_totals = a.get("totals") or {}
    b_totals = b.get("totals") or {}

    a_session_totals = session_a_report.get("totals") or a_totals
    b_session_totals = session_b_report.get("totals") or b_totals

    cost_ratio = s.get("cost_ratio")
    ifeval_delta = s.get("instruction_pass_delta_pp")
    input_ratio = s.get("input_tokens_ratio")
    output_ratio = s.get("output_tokens_ratio")
    total_ratio = s.get("total_tokens_ratio")

    verdict = _decision_framework_verdict(cost_ratio, ifeval_delta)

    # ---- 1. Title + subtitle ---------------------------------------------
    p(f"# {{{{TODO: one-line hook — e.g. \"I ran {b_family} against "
      f"{a_family} on {len(paired)} prompts. It cost "
      f"{_analysis_fmt_ratio_cell(cost_ratio)} more for "
      f"{_analysis_fmt_pp_cell(ifeval_delta)} of IFEval compliance.\"}}}}")
    p()
    p(f"_{{{{TODO: one-sentence framing — e.g. \"The ratio held across "
      f"{len(paired)} canonical prompts. Here's where the cost came "
      f"from and when it's worth paying.\"}}}}_")
    p()

    # ---- 2. TL;DR --------------------------------------------------------
    p("## TL;DR")
    p()
    p(f"- **Cost ratio ({b_family} ÷ {a_family}):** "
      f"{_analysis_fmt_ratio_cell(cost_ratio)}  "
      f"(Δ absolute: {_analysis_fmt_cost_delta_abs(a_totals.get('cost', 0.0) or 0.0, b_totals.get('cost', 0.0) or 0.0)})")
    p(f"- **Input-token ratio:** {_analysis_fmt_ratio_cell(input_ratio)}")
    p(f"- **Output-token ratio:** {_analysis_fmt_ratio_cell(output_ratio)}")
    p(f"- **Total-token ratio:** {_analysis_fmt_ratio_cell(total_ratio)}")
    if s.get("instruction_evaluated"):
        rate_a = s.get("instruction_pass_rate_a") or 0
        rate_b = s.get("instruction_pass_rate_b") or 0
        p(f"- **IFEval pass rate:** "
          f"A {rate_a * 100:.0f}% "
          f"({s.get('instruction_pass_a', 0)}/{s['instruction_evaluated']}), "
          f"B {rate_b * 100:.0f}% "
          f"({s.get('instruction_pass_b', 0)}/{s['instruction_evaluated']}) — "
          f"Δ {_analysis_fmt_pp_cell(ifeval_delta)}")
    else:
        p("- **IFEval pass rate:** not evaluated (no suite predicates fired)")
    p(f"- **Decision-framework verdict:** **{verdict['verdict']}** — "
      f"{verdict['explanation']}")
    p()
    p(f"{{{{TODO: 2–3 sentences of framing — the headline "
      f"ratio in plain English, the workload-specific "
      f"caveat, and why a reader should read past the TL;DR.}}}}")
    p()

    # ---- 3. Methodology --------------------------------------------------
    p("## Methodology")
    p()
    a_sid = a.get("session_id") or ""
    b_sid = b.get("session_id") or ""
    a_effort = a.get("effort") or ""
    b_effort = b.get("effort") or ""
    a_effort_tail = f" — effort `{a_effort}`" if a_effort else ""
    b_effort_tail = f" — effort `{b_effort}`" if b_effort else ""
    p(f"- **Side A:** `{a_model}` — session `{a_sid}`{a_effort_tail}")
    p(f"- **Side B:** `{b_model}` — session `{b_sid}`{b_effort_tail}")
    p(f"- **Pair-by:** `{compare_report.get('pair_by', 'fingerprint')}`")
    p(f"- **Compare mode:** `{compare_report.get('compare_mode', 'controlled')}`")
    p(f"- **Slug:** `{compare_report.get('slug', '')}`")
    a_first = a.get("first_ts_fmt") or a.get("first_ts") or ""
    a_last = a.get("last_ts_fmt") or a.get("last_ts") or ""
    b_first = b.get("first_ts_fmt") or b.get("first_ts") or ""
    b_last = b.get("last_ts_fmt") or b.get("last_ts") or ""
    p(f"- **Side A window:** {a_first} → {a_last}")
    p(f"- **Side B window:** {b_first} → {b_last}")
    p(f"- **Paired turns:** {s.get('paired_count', len(paired))} "
      f"(unmatched A={s.get('unmatched_a_count', 0)}, "
      f"B={s.get('unmatched_b_count', 0)})")
    if paired:
        p()
        p("**Prompts exercised** (in pairing order):")
        p()
        for i, row in enumerate(paired, 1):
            name = row.get("suite_prompt_name") or "_non-suite prompt_"
            p(f"{i}. `{name}`")
    p()

    # ---- 4. The numbers --------------------------------------------------
    p("## The numbers")
    p()
    p(f"### Per-session totals")
    p()
    p("| Metric | Side A | Side B | Ratio (B ÷ A) |")
    p("|--------|-------:|-------:|--------------:|")
    p(f"| Input tokens (net new) | "
      f"{a_session_totals.get('input', a_totals.get('input', 0)):,} | "
      f"{b_session_totals.get('input', b_totals.get('input', 0)):,} | "
      f"{_analysis_fmt_ratio_cell(input_ratio)} |")
    p(f"| Output tokens | "
      f"{a_session_totals.get('output', a_totals.get('output', 0)):,} | "
      f"{b_session_totals.get('output', b_totals.get('output', 0)):,} | "
      f"{_analysis_fmt_ratio_cell(output_ratio)} |")
    p(f"| Cache reads | "
      f"{a_session_totals.get('cache_read', a_totals.get('cache_read', 0)):,} | "
      f"{b_session_totals.get('cache_read', b_totals.get('cache_read', 0)):,} | "
      f"{_analysis_fmt_ratio_cell(_safe_ratio(b_session_totals.get('cache_read', b_totals.get('cache_read', 0)), a_session_totals.get('cache_read', a_totals.get('cache_read', 0))))} |")
    p(f"| Cache writes | "
      f"{a_session_totals.get('cache_write', a_totals.get('cache_write', 0)):,} | "
      f"{b_session_totals.get('cache_write', b_totals.get('cache_write', 0)):,} | "
      f"{_analysis_fmt_ratio_cell(_safe_ratio(b_session_totals.get('cache_write', b_totals.get('cache_write', 0)), a_session_totals.get('cache_write', a_totals.get('cache_write', 0))))} |")
    p(f"| Total billable tokens | "
      f"{a_session_totals.get('total', a_totals.get('total', 0)):,} | "
      f"{b_session_totals.get('total', b_totals.get('total', 0)):,} | "
      f"{_analysis_fmt_ratio_cell(total_ratio)} |")
    p(f"| Cost (USD) | "
      f"${a_session_totals.get('cost', a_totals.get('cost', 0.0)):.4f} | "
      f"${b_session_totals.get('cost', b_totals.get('cost', 0.0)):.4f} | "
      f"{_analysis_fmt_ratio_cell(cost_ratio)} |")
    thinking_a = a_session_totals.get("thinking_turn_count", 0)
    thinking_b = b_session_totals.get("thinking_turn_count", 0)
    p(f"| Turns with thinking blocks | {thinking_a} | {thinking_b} | — |")
    tool_a = a_session_totals.get("tool_call_total", 0)
    tool_b = b_session_totals.get("tool_call_total", 0)
    p(f"| Tool-call total | {tool_a} | {tool_b} | — |")
    p()

    if paired:
        has_instruction = any(
            row.get("instruction_pass_a") is not None
            or row.get("instruction_pass_b") is not None
            for row in paired
        )
        p("### Per-prompt breakdown")
        p()
        if has_instruction:
            p("| # | Prompt | A in | B in | Δ in | A out | B out | Δ out | "
              "A cost | B cost | Δ cost | A✓ | B✓ |")
            p("|--:|--------|-----:|-----:|-----:|------:|------:|------:|"
              "-------:|-------:|-------:|:--:|:--:|")
        else:
            p("| # | Prompt | A in | B in | Δ in | A out | B out | Δ out | "
              "A cost | B cost | Δ cost |")
            p("|--:|--------|-----:|-----:|-----:|------:|------:|------:|"
              "-------:|-------:|-------:|")
        for i, row in enumerate(paired, 1):
            ar = row.get("a") or {}
            br = row.get("b") or {}
            r = row.get("ratios") or {}
            name = row.get("suite_prompt_name") or "—"
            tail = ""
            if has_instruction:
                tail = (
                    f" {_fmt_pass(row.get('instruction_pass_a'))} | "
                    f"{_fmt_pass(row.get('instruction_pass_b'))} |"
                )
            p(f"| {i} | `{name}` | "
              f"{ar.get('input_tokens', 0):,} | "
              f"{br.get('input_tokens', 0):,} | "
              f"{_analysis_fmt_ratio_cell(r.get('input_tokens'))} | "
              f"{ar.get('output_tokens', 0):,} | "
              f"{br.get('output_tokens', 0):,} | "
              f"{_analysis_fmt_ratio_cell(r.get('output_tokens'))} | "
              f"${ar.get('cost_usd', 0.0):.4f} | "
              f"${br.get('cost_usd', 0.0):.4f} | "
              f"{_analysis_fmt_ratio_cell(r.get('cost_usd'))} |{tail}")
        p()

    # ---- 5. Where does the cost come from? -------------------------------
    p("## Where does the cost come from?")
    p()
    p(f"{{{{TODO: prose — explain which token bucket drove the "
      f"cost delta. The decomposition table below shows the raw "
      f"split; the prose connects it to the workload.}}}}")
    p()
    a_first_cw = _analysis_first_turn_cache_write(session_a_report)
    b_first_cw = _analysis_first_turn_cache_write(session_b_report)
    a_cache_read = a_session_totals.get("cache_read",
                                        a_totals.get("cache_read", 0))
    b_cache_read = b_session_totals.get("cache_read",
                                        b_totals.get("cache_read", 0))
    a_output = a_session_totals.get("output", a_totals.get("output", 0))
    b_output = b_session_totals.get("output", b_totals.get("output", 0))
    a_input = a_session_totals.get("input", a_totals.get("input", 0))
    b_input = b_session_totals.get("input", b_totals.get("input", 0))
    p("| Component | Side A | Side B | Ratio (B ÷ A) |")
    p("|-----------|-------:|-------:|--------------:|")
    p(f"| First-turn cache write (system-prompt encoding) | "
      f"{a_first_cw:,} | {b_first_cw:,} | "
      f"{_analysis_fmt_ratio_cell(_safe_ratio(b_first_cw, a_first_cw))} |")
    p(f"| Cumulative cache reads | "
      f"{a_cache_read:,} | {b_cache_read:,} | "
      f"{_analysis_fmt_ratio_cell(_safe_ratio(b_cache_read, a_cache_read))} |")
    p(f"| Output tokens | "
      f"{a_output:,} | {b_output:,} | "
      f"{_analysis_fmt_ratio_cell(_safe_ratio(b_output, a_output))} |")
    p(f"| User-prompt input (uncached) | "
      f"{a_input:,} | {b_input:,} | "
      f"{_analysis_fmt_ratio_cell(_safe_ratio(b_input, a_input))} |")
    p()

    # ---- 6. Extended thinking usage -------------------------------------
    p("## Extended thinking usage")
    p()
    a_turns = a.get("turn_count", 0) or 0
    b_turns = b.get("turn_count", 0) or 0
    p(f"- Side A: {thinking_a} of {a_turns} turn(s) carried at least one "
      f"`thinking` block.")
    p(f"- Side B: {thinking_b} of {b_turns} turn(s) carried at least one "
      f"`thinking` block.")
    p()
    p(f"{{{{TODO: interpretation — extended thinking is billed at the "
      f"output rate. Did one side use it more than the other? Was the "
      f"compliance delta (if any) visible specifically on the thinking "
      f"turns?}}}}")
    p()

    # ---- 7. Advisories ---------------------------------------------------
    if advisories:
        p("## Advisories raised by the compare report")
        p()
        for adv in advisories:
            tag = "⚠️" if adv.get("severity") == "warn" else "ℹ️"
            p(f"- {tag} **{adv.get('kind', 'advisory')}:** "
              f"{adv.get('message', '')}")
        p()

    # ---- 8. Should I switch? --------------------------------------------
    p("## Should I switch?")
    p()
    p("The canonical decision framework from "
      "`references/model-compare.md`:")
    p()
    p("| Cost ratio | IFEval Δ | Recommendation |")
    p("|------------|----------|----------------|")
    rows = [
        ("cheap",
         "≤ 1.05×", "any", "Switch. Minimal cost impact."),
        ("mid-quality-win",
         "1.05–1.20×", "+5 pp or more", "Switch if quality matters."),
        ("mid-flat",
         "1.05–1.20×", "±2 pp",
         "Suite-agnostic — depends on workload. Test with your own content."),
        ("expensive-big-quality",
         "1.20–1.45×", "+10 pp or more",
         "Trade-off call. Model your spend at the new ratio."),
        ("very-expensive",
         "≥ 1.45×", "any",
         "Stay, or use the newer model selectively (e.g. code review only)."),
    ]
    for bucket, cost_col, if_col, rec in rows:
        bold_open = "**" if bucket == verdict["bucket"] else ""
        bold_close = "**" if bucket == verdict["bucket"] else ""
        p(f"| {bold_open}{cost_col}{bold_close} | "
          f"{bold_open}{if_col}{bold_close} | "
          f"{bold_open}{rec}{bold_close} |")
    p()
    p(f"_Matched bucket:_ `{verdict['bucket']}` — {verdict['explanation']}")
    p()
    p(f"{{{{TODO: workload-specific interpretation — is your actual "
      f"workload closer to the suite's content shape, or skewed? "
      f"Does the decision row above hold once you factor in the "
      f"content mix you actually run?}}}}")
    p()

    # ---- 9. Caveats ------------------------------------------------------
    p("## Methodology caveats")
    p()
    p("- **Single-run variance.** Each prompt runs once per side. "
      "One-off captures can swing ±10% on tokenizer ratios. "
      "Multi-trial support is on the roadmap.")
    p("- **Cache warmth.** Running side B immediately after side A "
      "means B's CLAUDE.md cache is in a different state than A's "
      "was on its first turn. The report's `cache-share-drift` "
      "advisory fires when the two sides' cache-read share differs "
      "by >10 pp — read the cache column skeptically when it does.")
    p("- **Context-tier confound.** Claude Code's default Opus 4.7 "
      "arrives tagged `claude-opus-4-7[1m]`. When one side runs on "
      "the default tier and the other on `[1m]`, ratios conflate "
      "tokenizer + window tier + cache-hit-rate.")
    p("- **System-prompt drift.** Claude Code's system prompt "
      "evolves over time. Captures weeks or months apart can drift "
      "for that reason alone.")
    p("- **Prompt-suite representativeness.** The canonical 10 "
      "prompts cover the content shapes the upstream tokenizer "
      "article measured. Your real workload may be skewed — add "
      "prompts to the suite and re-run if so.")
    p()

    # ---- 10. Reproduce it yourself --------------------------------------
    p("## Reproduce it yourself")
    p()
    p("From any project root:")
    p()
    p("```bash")
    p(f"session-metrics --compare-run {a_family} {b_family} \\")
    p("    --output html")
    p("```")
    p()
    p("That spawns two `claude -p` subprocesses, feeds each side the "
      "canonical 10-prompt suite, and emits the compare HTML plus "
      "the per-session dashboards and this analysis scaffold. Pass "
      "`--no-compare-run-extras` to skip the per-session dashboards "
      "and this file (the minimal pre-v1.7.0 output).")
    p()
    p("If `claude -p` isn't available on your machine "
      "(e.g. a CI container without the CLI), fall back to "
      "`session-metrics --compare-prep` to print the manual capture "
      "protocol, then re-run `session-metrics --compare <A> <B>` "
      "against the resulting JSONLs. An API-only smoke test is "
      "`session-metrics --count-tokens-only --compare-models <A> <B>` "
      "— it measures input tokens but not output or cost.")
    p()

    # ---- 11. Links -------------------------------------------------------
    p("## Links")
    p()
    p(f"- {_analysis_link(links.get('compare_html'), 'Compare report (HTML)')}")
    p(f"- {_analysis_link(links.get('side_a_dashboard'), 'Side A dashboard')}  ·  "
      f"{_analysis_link(links.get('side_a_detail'), 'detail')}  ·  "
      f"{_analysis_link(links.get('side_a_json'), 'JSON')}")
    p(f"- {_analysis_link(links.get('side_b_dashboard'), 'Side B dashboard')}  ·  "
      f"{_analysis_link(links.get('side_b_detail'), 'detail')}  ·  "
      f"{_analysis_link(links.get('side_b_json'), 'JSON')}")
    p("- [session-metrics skill](https://github.com/centminmod/claude-plugins)")
    p()

    # ---- 12. Footer ------------------------------------------------------
    p(f"_Generated by session-metrics · "
      f"{compare_report.get('generated_at', '')} · "
      f"see marketplace listing for plugin version._")

    return out.getvalue()


def _emit_compare_run_extras(
    compare_report: dict,
    side_a_uuid: str,
    side_b_uuid: str,
    slug: str,
    *,
    formats: list[str],
    single_page: bool,
    chart_lib: str,
    tz_offset: float,
    tz_label: str,
    include_subagents: bool,
    use_cache: bool,
    progress_out=None,
    share_safe: bool = False,
) -> dict:
    """Emit the 5 per-session + analysis.md companion artefacts.

    Fires from ``_run_compare_run`` only when
    ``auto_resume and compare_run_extras and formats`` — i.e. the
    user is already opting into file output via ``--output`` and has
    not flipped the opt-out flag.

    Design choices encoded here:

    - **Shared timestamp.** All 5 (or more) written files share the
      single ``export_ts`` computed at the top of this function so
      the analysis.md's relative hrefs resolve to the sibling files
      regardless of how long the renders take in wall-clock time.
    - **Inline render loop.** We bypass the main module's
      ``_dispatch()`` because (a) it computes its own
      ``datetime.now()`` for the HTML 2-page split, losing the
      shared timestamp, and (b) it always prints ``render_text`` to
      stdout — for the per-session extras we don't want to dump
      side-A's timeline and then side-B's timeline over the user's
      terminal (they already saw the compare text output).
    - **Format fidelity.** Per-side renders honour the caller's
      requested formats (html / json / md / csv) — including the
      dashboard+detail split when ``single_page`` is False and
      ``html`` is requested. Analysis.md is always emitted
      regardless of format set, because it's the companion article,
      not a primary render.
    - **Defensive empty-side handling.** If a side's JSONL is
      missing (rare — only happens if Claude Code wrote to an
      unexpected path), that side's per-session exports are
      skipped with a warning and the analysis.md still renders
      using the side-info from the compare report.

    Returns a diagnostic dict of written paths keyed by
    ``{"side_a": {fmt: path}, "side_b": {fmt: path},
    "analysis_md": path}`` — used by tests.
    """
    m = _main()
    if progress_out is None:
        progress_out = sys.stderr

    export_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    projects_dir = m._projects_dir()
    side_a_jsonl = projects_dir / slug / f"{side_a_uuid}.jsonl"
    side_b_jsonl = projects_dir / slug / f"{side_b_uuid}.jsonl"

    diagnostic: dict = {"side_a": {}, "side_b": {}, "analysis_md": None}
    session_reports: dict[str, dict] = {}

    for side_label, uuid, jsonl_path in (
        ("A", side_a_uuid, side_a_jsonl),
        ("B", side_b_uuid, side_b_jsonl),
    ):
        side_key = f"side_{side_label.lower()}"
        if not jsonl_path.exists():
            print(
                f"[warn] compare-run extras: side {side_label} JSONL not "
                f"found at {jsonl_path}; skipping per-session exports for "
                f"this side",
                file=progress_out,
            )
            continue
        try:
            session_id, turns, user_ts = m._load_session(
                jsonl_path, include_subagents, use_cache=use_cache,
            )
        except OSError as exc:
            print(
                f"[warn] compare-run extras: failed to load side "
                f"{side_label} JSONL ({exc}); skipping per-session exports",
                file=progress_out,
            )
            continue
        if not turns:
            print(
                f"[warn] compare-run extras: side {side_label} has no "
                f"assistant turns with usage data; skipping per-session "
                f"exports for this side",
                file=progress_out,
            )
            continue

        report = m._build_report(
            "session", slug, [(session_id, turns, user_ts)],
            tz_offset_hours=tz_offset, tz_label=tz_label, peak=None,
            # Suppress the model-compare insight card on per-session
            # dashboards emitted from compare-run — the compare report
            # itself is the authoritative signal; duplicating the
            # advisory on each side is noise.
            suppress_model_compare_insight=True,
        )
        session_reports[side_key] = report

        for fmt in formats:
            if fmt == "text":
                continue
            if fmt == "html" and not single_page:
                sid8 = session_id[:8]
                dash_name = f"session_{sid8}_{export_ts}_dashboard.html"
                det_name = f"session_{sid8}_{export_ts}_detail.html"
                dash = m.render_html(report, variant="dashboard",
                                     nav_sibling=det_name,
                                     chart_lib=chart_lib)
                det = m.render_html(report, variant="detail",
                                    nav_sibling=dash_name,
                                    chart_lib=chart_lib)
                out_dir = m._export_dir()
                out_dir.mkdir(parents=True, exist_ok=True)
                dash_path = out_dir / dash_name
                det_path = out_dir / det_name
                dash_path.write_text(dash, encoding="utf-8")
                det_path.write_text(det, encoding="utf-8")
                if share_safe:
                    dash_path.chmod(0o600)
                    det_path.chmod(0o600)
                diagnostic[side_key]["html_dashboard"] = dash_path
                diagnostic[side_key]["html_detail"] = det_path
                print(
                    f"[export] side {side_label} HTML (dashboard) → "
                    f"{dash_path}",
                    file=progress_out,
                )
                print(
                    f"[export] side {side_label} HTML (detail)    → "
                    f"{det_path}",
                    file=progress_out,
                )
                continue
            if fmt == "html":
                content = m.render_html(report, variant="single",
                                        chart_lib=chart_lib)
            else:
                content = m._RENDERERS[fmt](report)
            path = m._write_output(fmt, content, report,
                                   explicit_ts=export_ts,
                                   share_safe=share_safe)
            diagnostic[side_key][fmt] = path
            print(
                f"[export] side {side_label} {fmt.upper():4} → {path}",
                file=progress_out,
            )

    # Build the links dict for the analysis.md — relative-only hrefs so
    # the Markdown resolves regardless of where the user opens it
    # from, as long as all files stay in ``exports/session-metrics/``.
    def _rel(p):
        return p.name if p is not None else None

    a_export = diagnostic["side_a"]
    b_export = diagnostic["side_b"]
    a_sid8 = (compare_report.get("side_a") or {}).get("session_id", "a")[:8]
    b_sid8 = (compare_report.get("side_b") or {}).get("session_id", "b")[:8]
    compare_html_name = (
        f"compare_{a_sid8}_vs_{b_sid8}_{export_ts}.html"
    )
    compare_html_path = m._export_dir() / compare_html_name

    links = {
        "compare_html": (
            compare_html_name if compare_html_path.exists() else None
        ),
        "side_a_dashboard": _rel(a_export.get("html_dashboard")),
        "side_a_detail": _rel(a_export.get("html_detail")),
        "side_a_json": _rel(a_export.get("json")),
        "side_b_dashboard": _rel(b_export.get("html_dashboard")),
        "side_b_detail": _rel(b_export.get("html_detail")),
        "side_b_json": _rel(b_export.get("json")),
    }
    # Single-page HTML extras land under the "html" key rather than
    # the split keys — fall back so the link section still renders
    # something useful when the user passed --single-page.
    if links["side_a_dashboard"] is None:
        links["side_a_dashboard"] = _rel(a_export.get("html"))
    if links["side_b_dashboard"] is None:
        links["side_b_dashboard"] = _rel(b_export.get("html"))

    # Fall back to an empty session report dict when a side is
    # missing — the analysis renderer defers to the compare report's
    # ``side_a["totals"]`` / ``side_b["totals"]`` for the numbers.
    content = _render_compare_analysis_md(
        compare_report,
        session_reports.get("side_a", {}),
        session_reports.get("side_b", {}),
        links,
    )
    analysis_path = m._write_output(
        "md", content, compare_report,
        suffix="_analysis", explicit_ts=export_ts,
        share_safe=share_safe,
    )
    diagnostic["analysis_md"] = analysis_path
    print(
        f"[export] compare-run analysis → {analysis_path}",
        file=progress_out,
    )

    return diagnostic
