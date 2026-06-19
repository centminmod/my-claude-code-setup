"""Data loading, parsing, and analysis layer for session-metrics."""
import bisect
import functools
import hashlib
import json
import math
import os
import pickle
import re
import secrets
import sys
import time
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

from _constants import _CACHE_BREAK_DEFAULT_THRESHOLD


def _sm():
    return sys.modules["session_metrics"]


# C.4: CSV formula-injection hardening. Spreadsheet apps (Excel, LibreOffice,
# Google Sheets) execute a cell as a formula when its first character is one of
# ``= + - @`` or a leading tab/CR/LF. A transcript field that a user controls
# (model id, slug, prompt snippet, tool name) could therefore smuggle a formula
# into a CSV export and run on open. We neutralise such cells with a leading
# apostrophe — the de-facto convention every major spreadsheet honours.
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _csv_safe(cell):
    """Return ``cell`` neutralised against CSV formula injection.

    Only string cells are touched; ints/floats/bools/None pass through so the
    numeric columns are unaffected. A string that *parses as a number* (e.g. a
    negative cost rendered as ``"-0.5"``) is left alone — prefixing it would
    corrupt a legitimately numeric value — so only genuinely textual cells that
    open with an injection character get the apostrophe.
    """
    if not isinstance(cell, str) or not cell:
        return cell
    if cell[0] in _CSV_INJECTION_PREFIXES:
        try:
            float(cell)
        except ValueError:
            return "'" + cell
    return cell


class _SafeCsvWriter:
    """``csv.writer`` proxy that runs every cell through :func:`_csv_safe`.

    Wrapping at the writer-construction point means all current and future
    ``writerow`` call sites are hardened automatically, rather than auditing
    dozens of individual list literals.
    """

    __slots__ = ("_w",)

    def __init__(self, writer):
        self._w = writer

    def writerow(self, row):
        return self._w.writerow([_csv_safe(c) for c in row])

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


@functools.lru_cache(maxsize=128)
def _pricing_for(model: str) -> dict[str, float]:
    """Resolve a model ID to its rate dict.

    Resolution order (silent → tentative → fallback):

      1. Exact key match in ``_PRICING`` (silent, correct).
      2. Regex sweep through ``_PRICING_PATTERNS`` (silent — more-specific
         variants first; non-Anthropic models, plus the Opus 4.0 anchored
         pattern that replaced the old ``claude-opus-4`` prefix entry).
      3. Prefix sweep through ``_PRICING`` keys (silent, dict-insertion
         order — catches date-suffixed variants of known minors, e.g.
         ``claude-opus-4-7-20251214`` landing on the ``claude-opus-4-7``
         entry).
      4. Family fallback regex sweep through ``_PRICING_FAMILY_FALLBACKS``
         (v1.41.2 — tentative rate **and** flag the model into
         ``_UNKNOWN_MODELS_SEEN``). Catches future variants like
         ``claude-opus-4-8`` (→ NEW $5/$25 tier) and ``claude-haiku-4-6``
         (→ Haiku $1/$5 tier) instead of the previous silent 3x overcharge.
      5. ``_DEFAULT_PRICING`` (Sonnet rate, flag as unknown).

    Cached (v1.41.0): ``functools.lru_cache(maxsize=128)`` removes the
    redundant resolution that ``_cost`` and ``_no_cache_cost`` both
    performed per turn. Side effect on ``_UNKNOWN_MODELS_SEEN`` only
    fires the first time a given model name is seen — the set is
    idempotent, so the at-exit warn surface is unchanged. Tests that
    rely on the side effect refreshing per call must call
    ``_pricing_for.cache_clear()`` (see autouse fixture in tests).
    """
    # Non-billable placeholder: dynamic-workflow orchestrator rows carry the
    # ``<synthetic>`` model marker and represent no real inference. Zero-rate
    # them so they neither overcharge nor trip the unknown-model advisory.
    if model == _sm()._SYNTHETIC_MODEL:
        return _sm()._ZERO_PRICING
    if model in _sm()._PRICING:
        return _sm()._PRICING[model]
    # Regex patterns before prefix sweep so specific variants (e.g. glm-5-turbo)
    # aren't swallowed by a shorter prefix (e.g. glm-5).
    for pattern, rates in _sm()._PRICING_PATTERNS:
        if pattern.search(model):
            return rates
    # NB (F5, v1.80.1): a generic "digit-boundary" guard here (refuse a prefix
    # match when the next char is a digit) was evaluated and REJECTED — it
    # regresses the *intentional* Opus-minor prefix design where
    # ``claude-opus-4-9`` is meant to catch ``claude-opus-4-99`` at the NEW tier
    # (see test_pricing_opus_4_99_silent_via_prefix). The bare-prefix-underprice
    # risk for an unguarded dotted minor (e.g. a hypothetical ``glm-5.10``)
    # remains documented policy debt, handled reactively per-model via an
    # explicit ``(?!\d)`` regex in _PRICING_PATTERNS (as glm-5.1 / glm-5.2 are).
    for prefix, rates in _sm()._PRICING.items():
        if model.startswith(prefix):
            return rates
    # Family fallback (v1.41.2): catches future Anthropic variants whose
    # exact / prefix entries don't exist yet. Returns a defensible family
    # rate (NEW-tier Opus / Haiku tier) AND flags the model so the
    # at-exit advisory tells the user to add an explicit entry.
    for pattern, rates in _sm()._PRICING_FAMILY_FALLBACKS:
        if pattern.search(model):
            _sm()._UNKNOWN_MODELS_SEEN.add(model)
            return rates
    _sm()._UNKNOWN_MODELS_SEEN.add(model)
    return _sm()._DEFAULT_PRICING


def _load_pricing_supplement(path: str, unresolved_only: bool = True) -> None:
    """C.6: supplement ``_PRICING`` from a JSON file for unresolved models only.

    A model is "unresolved" when it has no exact key in ``_PRICING`` — that is
    the set that otherwise falls back to family-tier rates. By default we never
    overwrite an existing exact entry (``unresolved_only``), so a stale
    side-file can't replace a rate the table already gets right. The file maps
    ``model-id -> {input, output, cache_read?, cache_write?, cache_write_1h?}``
    in USD per million tokens; missing cache tiers default from the input rate
    using the standard Anthropic ratios. Non-fatal: a missing/unparseable file
    or a malformed entry warns to stderr and the run continues with the
    built-in table.
    """
    sm = _sm()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"[warn] --refresh-pricing: could not load {path!r}: {exc}",
              file=sys.stderr)
        return
    if not isinstance(data, dict):
        print(f"[warn] --refresh-pricing: {path!r} must be a JSON object "
              "mapping model-id -> rate dict; ignoring.", file=sys.stderr)
        return
    applied: list[str] = []
    for model, rates in data.items():
        if not isinstance(rates, dict):
            continue
        if unresolved_only and model in sm._PRICING:
            continue  # never clobber a known-correct exact entry
        try:
            inp = float(rates["input"])
            entry = {
                "input":          inp,
                "output":         float(rates["output"]),
                "cache_read":     float(rates.get("cache_read", inp * 0.1)),
                "cache_write":    float(rates.get("cache_write", inp * 1.25)),
                "cache_write_1h": float(rates.get("cache_write_1h", inp * 2.0)),
            }
        except (KeyError, TypeError, ValueError):
            print(f"[warn] --refresh-pricing: skipping {model!r} "
                  "(needs numeric 'input' and 'output' rates).", file=sys.stderr)
            continue
        # Reject NaN / ±Inf / negative rates. ``float()`` happily accepts
        # "NaN"/"Infinity" (and Python's json.load parses those tokens by
        # default), and a negative is a valid float too — but any of them would
        # silently poison every downstream cost figure (and, because the cache
        # tiers above derive from ``inp``, one bad ``input`` fans out to all five
        # slots). Guard the whole entry, finite-and-non-negative, before it lands.
        if not all(math.isfinite(v) and v >= 0 for v in entry.values()):
            print(f"[warn] --refresh-pricing: skipping {model!r} "
                  "(rates must be finite and non-negative).", file=sys.stderr)
            continue
        sm._PRICING[model] = entry
        sm._UNKNOWN_MODELS_SEEN.discard(model)
        applied.append(model)
    if applied:
        _pricing_for.cache_clear()
        print(f"[refresh-pricing] supplemented {len(applied)} model(s): "
              f"{', '.join(sorted(applied))}", file=sys.stderr)


def _fast_multiplier_for(model: str) -> float:
    """Per-model fast-mode (``usage.speed == "fast"``) cost multiplier.

    Fast mode (research preview) is Opus-only and prices every token category
    at a uniform premium over standard rates (prompt-caching multipliers apply
    on top of the fast base), so multiplying the computed token cost by a single
    per-model factor is exact. Resolution mirrors ``_pricing_for``'s silent
    chain: exact key → prefix sweep (catches ``[1m]`` and date suffixes) →
    default ``1.0`` (never invent a premium for an unmapped model). No regex /
    family-fallback tier is needed — fast mode is bounded to the three Opus
    minors in ``_FAST_MODE_MULTIPLIERS``, whose ids are non-colliding prefixes.
    """
    table = _sm()._FAST_MODE_MULTIPLIERS
    if model in table:
        return table[model]
    for prefix, factor in table.items():
        if model.startswith(prefix):
            return factor
    return 1.0


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------

def _parse_jsonl(path: Path) -> list[dict]:
    entries = []
    skipped = 0
    first_err: str | None = None
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                skipped += 1
                if first_err is None:
                    first_err = f"line {lineno}: {exc}"
                continue
            # Defensive (v1.41.0): Claude Code's writer always emits JSON
            # objects, but a corrupt/truncated/edited JSONL could land an
            # array or scalar here. Downstream (`_extract_turns`) calls
            # ``entry.get("type")`` directly, which would AttributeError
            # on anything non-dict. Drop with the same skip path.
            if not isinstance(parsed, dict):
                skipped += 1
                if first_err is None:
                    first_err = (f"line {lineno}: top-level value is "
                                 f"{type(parsed).__name__}, expected object")
                continue
            entries.append(parsed)
    if skipped:
        suffix = f" (first: {first_err})" if first_err else ""
        print(f"[warn] {path.name}: {skipped} malformed line{'s' if skipped != 1 else ''} skipped{suffix}",
              file=sys.stderr)
    return entries


def _parse_cache_dir() -> Path:
    """Return the directory for serialized parse-cache blobs.

    Resolution order (v1.41.0):
      1. ``--cache-dir`` CLI flag (sets ``_sm()._CACHE_DIR_OVERRIDE``)
      2. ``CLAUDE_SESSION_METRICS_CACHE_DIR`` env var
      3. Default ``~/.cache/session-metrics/parse``

    Mirrors the ``--projects-dir`` / ``CLAUDE_PROJECTS_DIR`` precedence
    pattern in ``_cli.py:_projects_dir`` so users juggling multiple
    installs can redirect each location independently.
    """
    if _sm()._CACHE_DIR_OVERRIDE is not None:
        return _sm()._CACHE_DIR_OVERRIDE
    env = os.environ.get("CLAUDE_SESSION_METRICS_CACHE_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cache" / "session-metrics" / "parse"


def _parse_cache_key(path: Path, mtime_ns: int, size: int) -> str:
    """Build a stable cache-key filename from path hash, stem, mtime, size, and ver.

    An 8-hex-char SHA1 of the resolved absolute path disambiguates two JSONLs
    that share a UUID stem (e.g. identical filenames in sibling project dirs).
    Using ``mtime_ns`` (nanoseconds since epoch) means a touched JSONL always
    invalidates the cache. ``size`` (``st_size``) is included so an
    atomic-replace tool that preserves ``mtime_ns`` while changing content
    (``cp -p``, ``rsync --inplace``, restore-from-backup) still invalidates
    the blob — without it a stale pickle would be served silently. Bumping
    ``_sm()._SCRIPT_VERSION`` invalidates every existing blob — safe default
    when the parser shape changes.
    """
    try:
        abs_path = str(path.resolve())
    except OSError:
        abs_path = str(path)
    path_hash = hashlib.sha1(abs_path.encode("utf-8")).hexdigest()[:8]
    return (
        f"{path.stem}__{path_hash}__{mtime_ns}__{size}__"
        f"{_sm()._SCRIPT_VERSION}.pkl"
    )


def _cached_parse_jsonl(path: Path, use_cache: bool = True) -> list[dict]:
    """Return parsed entries from ``path``, using a pickle cache on disk.

    Cache format is ``pickle`` protocol 5 (stdlib, no compression). Bench
    measured -67% cold / -18% warm vs the prior gzip+JSON cache because
    pickle skips JSON's UTF-8 encode/decode and gzip's compression cost
    on this workload (~5k+ Python dicts of mixed strings/ints/floats).
    Trade-off: cache files are ~2× larger on disk (no compression).

    Cache invalidation is automatic on (a) JSONL mtime change and
    (b) ``_sm()._SCRIPT_VERSION`` bump. On I/O errors the cache is silently
    skipped — correctness first, speed second. Trust model: single-user-
    local; pickle of the script's own writes is safe.
    """
    if not use_cache:
        return _parse_jsonl(path)
    try:
        st = path.stat()
        mtime_ns = st.st_mtime_ns
        size = st.st_size
    except OSError:
        return _parse_jsonl(path)

    cache_dir = _sm()._parse_cache_dir()
    cache_path = cache_dir / _sm()._parse_cache_key(path, mtime_ns, size)
    try:
        with open(cache_path, "rb") as fh:
            return pickle.load(fh)
    except FileNotFoundError:
        pass
    except (OSError, pickle.UnpicklingError, EOFError):
        # Corrupt or unreadable — fall through to fresh parse.
        pass

    entries = _parse_jsonl(path)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Write atomically so a crash mid-write doesn't leave a corrupt cache.
        # Randomize the tmp suffix with pid + 4 bytes of entropy so two
        # concurrent writers on the same cache_path never collide on the
        # same tmp file (POSIX os.replace is atomic, but two writers racing
        # on the same tmp could interleave bytes prior to replace()).
        tmp = cache_path.with_suffix(
            f"{cache_path.suffix}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        )
        with open(tmp, "wb") as fh:
            pickle.dump(entries, fh, protocol=5)
        tmp.replace(cache_path)
    except OSError:
        # Non-fatal — the parse already succeeded.
        pass
    else:
        # Prune stranded blobs for the same source file (same stem + path_hash)
        # that were left behind by an mtime_ns bump or a _sm()._SCRIPT_VERSION change.
        # Only runs on cache miss (post-successful write) — no latency on warm hits.
        try:
            try:
                _abs = str(path.resolve())
            except OSError:
                _abs = str(path)
            _ph = hashlib.sha1(_abs.encode("utf-8")).hexdigest()[:8]
            _prefix = f"{path.stem}__{_ph}__"
            for _stale in cache_dir.glob(f"{_prefix}*"):
                if _stale.name != cache_path.name:
                    try:  # noqa: SIM105 — keep inline so the on-pass comment stays anchored
                        _stale.unlink()
                    except OSError:
                        pass  # racing writer / file vanished between glob and unlink
        except OSError:
            pass  # non-fatal — the write already succeeded
    return entries


def _prune_cache_global(cache_dir: Path) -> None:
    """Lazy global prune of the parse-cache directory.

    Throttled to at most once per 24 hours via a sentinel file so it runs
    silently on every normal invocation without per-run overhead.

    Deletion criteria for each *.pkl blob:
    1. Orphaned — the UUID stem matches no JSONL under _projects_dir()
       (deleted project, renamed slug, migrated machine).
    2. Inactive session — source JSONL mtime > 60 days (session closed)
       AND blob mtime > 30 days (not recently cold-parsed).
    3. Stale blob — blob mtime > 30 days even when the session is still
       active-ish (JSONL mtime <= 60 days).  One cold re-parse (~0.3 s)
       is cheaper than keeping blobs that warm-cache hits never refresh.

    The 30 d / 60 d split prevents deleting blobs that are being served
    on warm hits daily for an ongoing project: if the JSONL is young,
    we keep the blob even when it hasn't been written in a month.

    All I/O errors are silenced — the prune must never surface to the user
    or interrupt the main parse path.
    """
    sentinel = cache_dir / ".prune_last_run"
    now = time.time()
    _24h = 86_400.0
    _30d = 30 * _24h
    _60d = 60 * _24h

    try:
        if sentinel.exists() and (now - sentinel.stat().st_mtime) < _24h:
            return
        cache_dir.mkdir(parents=True, exist_ok=True)
        sentinel.touch()
    except OSError:
        return

    # Single glob pass — build UUID→path index for all live JSONLs.
    jsonl_by_stem: dict[str, Path] = {}
    try:
        projects_root = _sm()._projects_dir()
        for _j in projects_root.glob("*/*.jsonl"):
            jsonl_by_stem[_j.stem] = _j
        # Subagent transcripts live one level under the SESSION dir, not the
        # slug dir: <slug>/<session-uuid>/subagents/agent-*.jsonl. The old
        # depth-3 glob ("*/subagents/*.jsonl") matched nothing, so every
        # subagent blob was deleted as "orphaned" on each daily prune and
        # cold-parsed again on the next project run. Keep the depth-3 glob
        # for any legacy layout; add the real depth-4 path and the dynamic-
        # workflow tier (<...>/subagents/workflows/<runId>/agent-*.jsonl).
        for _j in projects_root.glob("*/subagents/*.jsonl"):
            jsonl_by_stem[_j.stem] = _j
        for _j in projects_root.glob("*/*/subagents/*.jsonl"):
            jsonl_by_stem[_j.stem] = _j
        for _j in projects_root.glob("*/*/subagents/workflows/*/*.jsonl"):
            jsonl_by_stem[_j.stem] = _j
    except OSError:
        return  # can't scan — skip this cycle

    try:
        blobs = list(cache_dir.glob("*.pkl"))
    except OSError:
        return

    for _blob in blobs:
        try:
            stem = _blob.name.split("__", 1)[0]
            blob_age = now - _blob.stat().st_mtime
            _jsonl = jsonl_by_stem.get(stem)

            if _jsonl is None:
                _blob.unlink()  # orphaned — source JSONL gone
                continue

            if blob_age <= _30d:
                continue  # recently written — keep unconditionally

            try:
                jsonl_age = now - _jsonl.stat().st_mtime
            except OSError:
                _blob.unlink()  # can't stat JSONL — treat as orphaned
                continue

            if jsonl_age > _60d:
                _blob.unlink()  # session inactive for 60+ days
        except OSError:
            pass  # file vanished between glob and unlink — harmless


_CONTENT_LETTERS = (
    ("thinking",            "T"),
    ("tool_use",            "u"),
    ("text",                "x"),
    ("tool_result",         "r"),
    ("image",               "i"),
    ("server_tool_use",     "v"),
    ("advisor_tool_result", "R"),
)


_BLOCK_WINDOW_SEC = 5 * 3600


def _parse_iso_epoch(ts: str) -> int:
    """Parse an ISO-8601 timestamp to UTC epoch seconds; 0 on failure."""
    dt = _sm()._parse_iso_dt(ts)
    if dt is None:
        return 0
    try:
        return int(dt.timestamp())
    except (OSError, OverflowError):
        return 0


# Phase F — fixed bucket edges + stable labels for the multi-session
# session-shape histograms. Edges are bucket *upper boundaries* consumed by
# ``bisect.bisect_right`` (no leading 0), so a value lands in bucket
# ``bisect_right(edges, value)`` and ``counts`` has ``len(edges)+1`` entries.
# Labels are module constants (not recomputed per call) so the rendered bytes
# are stable across runs.
_HIST_DURATION_EDGES = [300, 900, 1800, 3600, 7200, 14400, 28800]
_HIST_DURATION_LABELS = ["0–5m", "5–15m", "15–30m", "30m–1h",
                         "1–2h", "2–4h", "4–8h", "8h+"]
_HIST_TURN_EDGES = [5, 10, 20, 50, 100, 200]
_HIST_TURN_LABELS = ["1–5", "6–10", "11–20", "21–50",
                     "51–100", "101–200", "200+"]
_HIST_COST_EDGES = [0.01, 0.05, 0.10, 0.50, 1.00, 5.00]
_HIST_COST_LABELS = ["<$0.01", "$0.01–0.05", "$0.05–0.10",
                     "$0.10–0.50", "$0.50–$1", "$1–$5", "$5+"]


def _compute_session_shape_histograms(sessions_out: list[dict]) -> dict:
    """Bucketed distributions of per-session duration / turn-count / cost.

    Multi-session only — a single-session report has no distribution to show,
    so ``{}`` is returned for ``len(sessions_out) < 2`` and every renderer
    auto-hides. Counts are pure integer folds (no float-order risk); p50/p90
    reuse the shared ``_percentile`` helper (which sorts internally), so the
    output is deterministic regardless of session iteration order.
    """
    if len(sessions_out) < 2:
        return {}
    durations = [int(s.get("duration_seconds", 0) or 0) for s in sessions_out]
    turns = [int((s.get("subtotal") or {}).get("turns", 0) or 0) for s in sessions_out]
    costs = [float((s.get("subtotal") or {}).get("cost", 0.0) or 0.0) for s in sessions_out]

    def _hist(values: list, edges: list, labels: list[str],
              right: bool = False) -> dict:
        # Bucket placement: ``bisect_left`` gives inclusive-upper ranges
        # ("1–5" holds 1..5, "15–30m" holds up to 30m) which is what the
        # integer turn / duration labels mean; a value exactly on an edge
        # stays in the *lower* labelled bucket. ``bisect_right`` (right=True)
        # is used for cost, whose leading "<$0.01" label is exclusive, so an
        # exact $0.01 belongs in the next bucket. (Float cost values land on
        # an edge essentially never, so the choice only matters for the
        # integer turn histogram where edge-hits are common.)
        place = bisect.bisect_right if right else bisect.bisect_left
        counts = [0] * (len(edges) + 1)
        for v in values:
            counts[place(edges, v)] += 1
        fvals = [float(v) for v in values]
        return {
            "counts": counts,
            "labels": list(labels),
            "p50": _sm()._percentile(fvals, 50),
            "p90": _sm()._percentile(fvals, 90),
            "n": len(values),
        }

    return {
        "duration": _hist(durations, _HIST_DURATION_EDGES, _HIST_DURATION_LABELS),
        "turns":    _hist(turns,     _HIST_TURN_EDGES,     _HIST_TURN_LABELS),
        "cost":     _hist(costs,     _HIST_COST_EDGES,     _HIST_COST_LABELS, right=True),
    }


def _compute_session_activity_by_hour(sessions_out: list[dict],
                                      tz_offset_hours: float) -> list[int]:
    """24-element list of distinct sessions active in each local hour (0–23).

    A session counts once per hour no matter how many turns it had in that
    hour (``session_id`` set per bucket, then cardinality). Resume-marker
    turns are skipped. Output is positional ``list[int]`` of length 24 — no
    dict-key ordering, so it is byte-stable by construction.
    """
    shift = int(round(tz_offset_hours * 3600))
    hour_sessions: list[set] = [set() for _ in range(24)]
    for s in sessions_out:
        sid = s.get("session_id", "")
        for t in s.get("turns", []) or []:
            if t.get("is_resume_marker"):
                continue
            e = _parse_iso_epoch(t.get("timestamp", ""))
            if not e:
                continue
            h = (((e + shift) % 86400) + 86400) % 86400 // 3600
            hour_sessions[h].add(sid)
    return [len(b) for b in hour_sessions]


def _build_session_blocks(
    sessions_raw: list[tuple[str, list[dict], list[int]]],
) -> list[dict]:
    """Group all events into 5-hour blocks anchored at each block's first event.

    A block starts when an event arrives more than 5 hours after the previous
    block's anchor.  Events are the union of filtered user prompts and
    assistant-turn timestamps across every session in the project — this
    matches what Anthropic's rate-limit window sees (users can ``/clear``
    mid-block and the window keeps running).

    Each block records: anchor and last timestamps, elapsed minutes, turn
    count, user-message count, per-bucket token totals, USD cost, model mix,
    and which session IDs touched the block.
    """
    events: list[tuple[int, str, str, dict | None]] = []
    for session_id, raw_turns, user_ts in sessions_raw:
        for u in user_ts:
            events.append((u, "user", session_id, None))
        for t in raw_turns:
            e = _parse_iso_epoch(t.get("timestamp", ""))
            if e:
                events.append((e, "turn", session_id, t))
    events.sort(key=lambda x: x[0])

    blocks: list[dict] = []
    for epoch, kind, sid, turn in events:
        if not blocks or (epoch - blocks[-1]["anchor_epoch"]) >= _BLOCK_WINDOW_SEC:
            blocks.append({
                "anchor_epoch":     epoch,
                "last_epoch":       epoch,
                "turn_count":       0,
                "user_msg_count":   0,
                "input":            0,
                "output":           0,
                "cache_read":       0,
                "cache_write":      0,
                "cost_usd":         0.0,
                "models":           {},
                "sessions_touched": set(),
            })
        b = blocks[-1]
        b["last_epoch"] = epoch
        b["sessions_touched"].add(sid)
        if kind == "user":
            b["user_msg_count"] += 1
        else:
            # user events carry None; assistant turns carry a dict. Guard
            # explicitly rather than with ``assert`` (which ``python -O`` strips,
            # turning a broken invariant into an opaque crash mid-loop) — a
            # malformed pairing now ``continue``s instead (v1.80.1).
            if turn is None:
                continue
            msg   = turn["message"]
            u     = msg["usage"]
            model = msg.get("model", "unknown")
            b["turn_count"]  += 1
            b["input"]       += u.get("input_tokens", 0)
            b["output"]      += u.get("output_tokens", 0)
            b["cache_read"]  += u.get("cache_read_input_tokens", 0)
            # Mirror _cache_write_split: the nested ephemeral split is the
            # primary source and the flat field only a legacy fallback —
            # reading the flat field alone would silently zero this column
            # if transcripts ever stop dual-populating it.
            cwr_5m, cwr_1h = _sm()._cache_write_split(u)
            b["cache_write"] += cwr_5m + cwr_1h
            b["cost_usd"]    += _sm()._cost(u, model)
            b["models"][model] = b["models"].get(model, 0) + 1

    for b in blocks:
        b["sessions_touched"] = sorted(b["sessions_touched"])
        b["elapsed_min"]      = (b["last_epoch"] - b["anchor_epoch"]) / 60.0
        b["anchor_iso"]       = datetime.fromtimestamp(
            b["anchor_epoch"], tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        b["last_iso"]         = datetime.fromtimestamp(
            b["last_epoch"],   tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return blocks


def _build_weekly_rollup(
    sessions_out: list[dict],
    sessions_raw: list[tuple[str, list[dict], list[int]]],
    session_blocks: list[dict],
    now_epoch: int | None = None,
) -> dict:
    """Compare the trailing 7 days against the prior 7 days.

    Uses **deduped** assistant turns from ``sessions_out`` (match the report's
    cost/token totals) and filtered user prompts from ``sessions_raw``.
    Block counts use each block's anchor epoch — a block "belongs" to the
    window its first event lands in.

    Returns ``{"trailing_7d": {...}, "prior_7d": {...}, "has_data": bool,
    "now_epoch": int}``. When ``prior_7d`` has zero turns, callers should
    render deltas as "new period" rather than infinite percentage.
    """
    if now_epoch is None:
        now_epoch = int(datetime.now(tz=UTC).timestamp())
    cutoff7  = now_epoch - 7  * 86400
    cutoff14 = now_epoch - 14 * 86400

    user_ts_all = sorted(ts for _, _, uts in sessions_raw for ts in uts)
    turns_with_epoch: list[tuple[int, dict]] = []
    for s in sessions_out:
        for t in s["turns"]:
            e = _parse_iso_epoch(t.get("timestamp", ""))
            if e:
                turns_with_epoch.append((e, t))

    def bucket(start: int, end: int) -> dict:
        b = {
            "turns": 0, "user_prompts": 0, "cost": 0.0,
            "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
            "blocks": 0, "partial_hit_turns": 0, "total_cache_turns": 0,
        }
        for u in user_ts_all:
            if start <= u < end:
                b["user_prompts"] += 1
        for e, t in turns_with_epoch:
            if start <= e < end:
                b["turns"]       += 1
                b["input"]       += t["input_tokens"]
                b["output"]      += t["output_tokens"]
                cr = t["cache_read_tokens"]
                cw = t["cache_write_tokens"]
                b["cache_read"]  += cr
                b["cache_write"] += cw
                b["cost"]        += t["cost_usd"]
                if cr > 0 or cw > 0:
                    b["total_cache_turns"] += 1
                if cr > 0 and cw > 0:
                    b["partial_hit_turns"] += 1
        for blk in session_blocks:
            if start <= blk["anchor_epoch"] < end:
                b["blocks"] += 1
        total_in = b["input"] + b["cache_read"] + b["cache_write"]
        b["cache_hit_pct"] = 100 * b["cache_read"] / max(1, total_in)
        b["partial_hit_rate"] = round(100.0 * b["partial_hit_turns"] / max(1, b["total_cache_turns"]), 1)
        return b

    trailing = bucket(cutoff7, now_epoch)
    prior    = bucket(cutoff14, cutoff7)
    return {
        "now_epoch":   now_epoch,
        "trailing_7d": trailing,
        "prior_7d":    prior,
        "has_data":    (trailing["turns"] + prior["turns"]) > 0,
    }


def _weekly_block_counts(blocks: list[dict], now_epoch: int | None = None) -> dict:
    """Count blocks active (``last_epoch`` >= cutoff) in trailing windows.

    ``now_epoch`` is the upper bound for the window; defaults to current UTC.
    Returns counts for the trailing 7/14/30 days plus the grand total, which
    answers "am I tracking toward a weekly cap" at a glance.
    """
    if now_epoch is None:
        now_epoch = int(datetime.now(tz=UTC).timestamp())

    def cnt(days: int) -> int:
        cutoff = now_epoch - days * 86400
        return sum(1 for b in blocks if b["last_epoch"] >= cutoff)

    return {
        "trailing_7":  cnt(7),
        "trailing_14": cnt(14),
        "trailing_30": cnt(30),
        "total":       len(blocks),
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Data model — build structured report from raw turns
# ---------------------------------------------------------------------------

def _derive_total_fields(t: dict, name_counts: dict[str, int]) -> dict:
    """Set every derived field on a totals dict from its additive fields.

    Single source of truth shared by `_totals_from_turns`, `_add_totals`,
    and `_aggregate_totals` (instance scope) so the formulas cannot drift
    between scopes — the v1.63.0 instance-parity bug was caused by exactly
    that three-way duplication. Expects the additive fields to be final
    before the call: input/output/cache_read/cache_write, cost,
    no_cache_cost, turns, thinking_turn_count, partial_hit_turns,
    total_cache_turns, and content_blocks. Mutates and returns ``t``.
    """
    t["total"] = t["input"] + t["output"] + t["cache_read"] + t["cache_write"]
    t["total_input"] = t["input"] + t["cache_read"] + t["cache_write"]
    t["cache_savings"] = t["no_cache_cost"] - t["cost"]
    t["cache_hit_pct"] = 100 * t["cache_read"] / max(1, t["total_input"])
    t["partial_hit_rate"] = round(
        100.0 * t["partial_hit_turns"] / max(1, t["total_cache_turns"]), 1)
    n = t["turns"]
    t["thinking_turn_pct"] = 100 * t["thinking_turn_count"] / n if n else 0.0
    cb = t.get("content_blocks") or {}
    t["tool_call_total"] = cb.get("tool_use", 0)
    t["tool_call_avg_per_turn"] = t["tool_call_total"] / n if n else 0.0
    # Stable ordering: count desc, then name asc so ties are deterministic.
    ranked = sorted(name_counts.items(), key=lambda x: (-x[1], x[0]))
    t["tool_names_top3"] = [name for name, _ in ranked[:3]]
    return t


def _totals_from_turns(turn_records: list[dict]) -> dict:
    t = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
         "cache_write_5m": 0, "cache_write_1h": 0, "extra_1h_cost": 0.0,
         "cost": 0.0, "no_cache_cost": 0.0, "turns": 0,
         "synthetic_turns": 0,
         "advisor_call_count": 0, "advisor_cost_usd": 0.0,
         "partial_hit_turns": 0, "total_cache_turns": 0}
    content_block_totals = {"thinking": 0, "tool_use": 0, "text": 0,
                            "tool_result": 0, "image": 0,
                            "server_tool_use": 0, "advisor_tool_result": 0}
    thinking_turn_count = 0
    # C.2: null-vs-zero discipline. ``latency_seconds`` is the one per-turn
    # numeric that is genuinely *unmeasured* (set to None) rather than measured
    # zero — it has no preceding timestamp to diff against on the first turn of
    # a stream. Counting those turns lets a consumer read any latency aggregate
    # as covering (turns − latency_seconds_null) turns, not all turns. (The
    # cache_write_5m/1h and no_cache_cost fields are always populated by
    # _build_turn_record, so they have no null state worth tracking.)
    latency_null = 0
    name_counts: dict[str, int] = {}
    for r in turn_records:
        # Non-billable ``<synthetic>`` orchestrator/resume placeholders carry
        # zero tokens and zero cost. Excluding them from ``turns`` keeps the
        # headline count equal to the per-model table sum (`_model_breakdown`
        # skips them too); they are still surfaced via ``synthetic_turns``.
        if r["model"] == _sm()._SYNTHETIC_MODEL:
            t["synthetic_turns"] += 1
            continue
        t["turns"]        += 1
        if r.get("latency_seconds") is None:
            latency_null += 1
        t["input"]        += r["input_tokens"]
        t["output"]       += r["output_tokens"]
        t["cache_read"]   += r["cache_read_tokens"]
        t["cache_write"]  += r["cache_write_tokens"]
        t["cache_write_5m"] += r.get("cache_write_5m_tokens", 0)
        t["cache_write_1h"] += r.get("cache_write_1h_tokens", 0)
        cr = r["cache_read_tokens"]
        cw = r["cache_write_tokens"]
        if cr > 0 or cw > 0:
            t["total_cache_turns"] += 1
        if cr > 0 and cw > 0:
            t["partial_hit_turns"] += 1
        t["cost"]              += r["cost_usd"]
        t["no_cache_cost"]     += r["no_cache_cost_usd"]
        t["advisor_call_count"] += r.get("advisor_calls", 0)
        t["advisor_cost_usd"]   += r.get("advisor_cost_usd", 0.0)
        # Extra cost paid for opting into the 1h TTL tier (vs pricing those
        # same tokens at the 5m rate). Meaningful only when cache_write_1h > 0.
        tokens_1h = r.get("cache_write_1h_tokens", 0)
        if tokens_1h:
            rates = _pricing_for(r["model"])
            extra = tokens_1h * (rates["cache_write_1h"] - rates["cache_write"]) / 1_000_000
            # Fast mode scales every rate uniformly, so the 1h-vs-5m premium
            # delta scales too — mirror _cost's per-turn multiplier or this KPI
            # under-reports on fast turns (the headline cost stays correct).
            if r.get("speed") == "fast" and not _sm()._FAST_PREMIUM_DISABLED:
                extra *= _fast_multiplier_for(r["model"])
            t["extra_1h_cost"] += extra
        cb = r.get("content_blocks") or {}
        for k in content_block_totals:
            content_block_totals[k] += cb.get(k, 0)
        if cb.get("thinking", 0) > 0:
            thinking_turn_count += 1
        for name in r.get("tool_use_names", []) or []:
            name_counts[name] = name_counts.get(name, 0) + 1
    t["content_blocks"] = content_block_totals
    t["thinking_turn_count"] = thinking_turn_count
    t["null_metric_counts"] = {"latency_seconds": latency_null}
    _derive_total_fields(t, name_counts)
    # Internal field carried so `_add_totals` (P4.4) can fold per-session
    # subtotals into a project-wide total without re-iterating turns. Stripped
    # off the top-level project totals + each session subtotal in
    # `_build_report` after the reduce so it never lands in JSON exports.
    t["_tool_name_counts"] = name_counts
    return t


def _add_totals(a: dict, b: dict) -> dict:
    """Pairwise sum two `_totals_from_turns` outputs into a new total dict.

    Used by `_build_report` (P4.4) to fold per-session subtotals into the
    project-wide total without a second linear pass over every turn record.
    Re-derives the computed fields (`total`, `total_input`, `cache_savings`,
    `cache_hit_pct`, `thinking_turn_pct`, `tool_call_total`,
    `tool_call_avg_per_turn`, `tool_names_top3`) from the merged additive
    state so the output matches running `_totals_from_turns` over the
    concatenation of the two source turn lists. Integer token/count fields
    are exact; derived float fields may differ from a single linear pass by
    at most a floating-point rounding ULP (pairwise sum vs. one accumulator).
    """
    out: dict = {
        "input":               a["input"]               + b["input"],
        "output":              a["output"]              + b["output"],
        "cache_read":          a["cache_read"]          + b["cache_read"],
        "cache_write":         a["cache_write"]         + b["cache_write"],
        "cache_write_5m":      a["cache_write_5m"]      + b["cache_write_5m"],
        "cache_write_1h":      a["cache_write_1h"]      + b["cache_write_1h"],
        "extra_1h_cost":       a["extra_1h_cost"]       + b["extra_1h_cost"],
        "cost":                a["cost"]                + b["cost"],
        "no_cache_cost":       a["no_cache_cost"]       + b["no_cache_cost"],
        "turns":               a["turns"]               + b["turns"],
        "synthetic_turns":     a.get("synthetic_turns", 0) + b.get("synthetic_turns", 0),
        "advisor_call_count":  a["advisor_call_count"]  + b["advisor_call_count"],
        "advisor_cost_usd":    a["advisor_cost_usd"]    + b["advisor_cost_usd"],
        "thinking_turn_count": a["thinking_turn_count"] + b["thinking_turn_count"],
        "partial_hit_turns":   a.get("partial_hit_turns", 0)  + b.get("partial_hit_turns", 0),
        "total_cache_turns":   a.get("total_cache_turns", 0)  + b.get("total_cache_turns", 0),
    }
    cb_a = a.get("content_blocks") or {}
    cb_b = b.get("content_blocks") or {}
    cb: dict[str, int] = {}
    # C.1: sort the merged key set so the folded `content_blocks` dict has a
    # deterministic key order regardless of which session is folded first —
    # a bare `set(...)` union iterates in hash order and would let JSON byte
    # output drift across runs at multi-session scope.
    for k in sorted(set(cb_a) | set(cb_b)):
        cb[k] = int(cb_a.get(k, 0)) + int(cb_b.get(k, 0))
    out["content_blocks"] = cb
    # C.2: fold per-metric null counts with integer addition, sorted keys for a
    # deterministic merged-dict order (same reason as the content_blocks merge).
    nm_a = a.get("null_metric_counts") or {}
    nm_b = b.get("null_metric_counts") or {}
    out["null_metric_counts"] = {
        k: int(nm_a.get(k, 0)) + int(nm_b.get(k, 0))
        for k in sorted(set(nm_a) | set(nm_b))
    }
    nc_a = a.get("_tool_name_counts") or {}
    nc_b = b.get("_tool_name_counts") or {}
    nc: dict[str, int] = dict(nc_a)
    for k, v in nc_b.items():
        nc[k] = nc.get(k, 0) + v
    out["_tool_name_counts"] = nc
    return _derive_total_fields(out, nc)


def _model_breakdown(turn_records: list[dict]) -> dict[str, dict]:
    """Per-model summary keyed by model id.

    Returns ``{model_id: {"turns": int, "cost_usd": float}}``. The richer
    shape (vs. the prior plain ``{model_id: int}``) matches what
    ``_aggregate_models`` already produces at instance scope, so renderers
    and audit-extract see the same shape regardless of mode. Cost-share
    surfaces as a column in the Models table and as ``cost_pct`` in the
    audit baseline (P2.1 — turn share alone hides the long-tail expensive
    model: 22% turns can be 37% cost).
    """
    out: dict[str, dict] = {}
    for r in turn_records:
        # Skip the non-billable ``<synthetic>`` orchestrator/resume placeholder
        # (zero-cost via `_pricing_for`'s zero-rate tier) so it never surfaces
        # as a misleading $0 phantom row. Mirrors the same exclusion in
        # `_build_by_workflow`.
        if r["model"] == _sm()._SYNTHETIC_MODEL:
            continue
        m = out.setdefault(r["model"], {"turns": 0, "cost_usd": 0.0})
        m["turns"] += 1
        m["cost_usd"] += float(r.get("cost_usd", 0.0))
    return out


# ---------------------------------------------------------------------------
# Phase-A aggregators (v1.6.0) — inspired by Anthropic's session-report skill.
# Three new cross-cutting breakdowns the existing renderers did not expose:
#   1. ``cache_breaks``    — single turns above a configurable uncached+cache-
#                             create threshold, with ±2 user-prompt context.
#   2. ``by_skill``        — per-skill/slash-command aggregation (sticky
#                             attribution to the most recent slash-prefixed
#                             user prompt, overridden turn-locally by Skill
#                             tool_use blocks).
#   3. ``by_subagent_type``— per-subagent-type table (spawn count from
#                             Agent/Task tool_use `input.subagent_type` +
#                             actual consumed tokens when --include-subagents
#                             tags each sidechain turn with its resolved
#                             subagent_type).
# These are computed once per report build and attached at both the per-
# session level (session dict) and the report level (aggregated across the
# report's sessions). The instance-mode builder then aggregates across
# projects on top.
# ---------------------------------------------------------------------------


def _detect_cache_breaks(session: dict,
                          threshold: int = _CACHE_BREAK_DEFAULT_THRESHOLD,
                          context_radius: int = 2) -> list[dict]:
    """Flag turns whose uncached+cache-create token spend exceeds ``threshold``.

    "Cache break" = the cached prompt context was evicted or not reused, so
    the model had to re-ingest a large block of uncached tokens. Surfacing
    these lets users trace *which* turn lost the cache (vs. a summary cache-
    hit% which doesn't name events).

    Returns a list of dicts in descending-uncached order, each with:
        session_id, turn_index, timestamp, timestamp_fmt,
        uncached (input + cache_write), total_tokens, cache_break_pct,
        prompt_snippet, slash_command, model,
        context: [{ts, text, slash, here: bool}] — ±2 user prompts around
                 the flagged turn, ordered chronologically.
    """
    turns = session.get("turns") or []
    if not turns:
        return []
    # Build an ordered list of user-prompt records from the turn stream.
    # A "user prompt" here is the non-empty ``prompt_text`` of a turn — i.e.
    # the genuine typed input that triggered this turn (or the first turn
    # of a tool-use chain rooted in that prompt). Adjacent turns sharing
    # the same prompt reference are deduped so the ±2 window scopes to
    # distinct user actions, not tool-loop continuations.
    prompts: list[dict] = []
    last_text: str | None = None
    for t in turns:
        if t.get("is_resume_marker"):
            continue
        txt = (t.get("prompt_text") or "").strip()
        if not txt or txt == last_text:
            continue
        prompts.append({
            "ts":    t.get("timestamp", ""),
            "ts_fmt": t.get("timestamp_fmt", ""),
            "text":   t.get("prompt_snippet") or txt[:240],
            "slash":  t.get("slash_command", ""),
            "turn_index": t.get("index"),
        })
        last_text = txt
    # Precompute prompt turn-indices once for bisect (P4.2). prompts is
    # built by walking turns in chronological order, so this list is
    # monotonically non-decreasing — required for bisect_right. Parser
    # invariant: every prompt has an integer turn_index.
    prompt_indices: list[int] = [p["turn_index"] for p in prompts]
    # Detect flagged turns, attach context window.
    breaks: list[dict] = []
    for t in turns:
        if t.get("is_resume_marker"):
            continue
        uncached = int(t.get("input_tokens", 0)) + int(t.get("cache_write_tokens", 0))
        if uncached <= threshold:
            continue
        t["is_cache_break"] = True   # mutate in-place; used by HTML inline badge
        total = int(t.get("total_tokens", 0))
        pct = (100.0 * uncached / total) if total else 0.0
        # Locate this turn's position in the prompt stream — match by
        # turn_index >= prompt.turn_index. The closest prompt whose
        # turn_index <= flagged turn's index is "this turn's" prompt; its
        # ±context_radius neighbours form the context window.
        ti = t.get("index")
        anchor = bisect.bisect_right(prompt_indices, ti) - 1 if ti is not None else -1
        ctx: list[dict] = []
        if anchor >= 0:
            lo = max(0, anchor - context_radius)
            hi = min(len(prompts), anchor + context_radius + 1)
            for i in range(lo, hi):
                p = prompts[i]
                ctx.append({
                    "ts":    p["ts_fmt"] or p["ts"],
                    "text":  p["text"],
                    "slash": p["slash"],
                    "here":  (i == anchor),
                })
        breaks.append({
            "session_id":     session.get("session_id", ""),
            "turn_index":     t.get("index"),
            "timestamp":      t.get("timestamp", ""),
            "timestamp_fmt":  t.get("timestamp_fmt", ""),
            "uncached":       uncached,
            "total_tokens":   total,
            "cache_break_pct": round(pct, 1),
            "prompt_snippet": t.get("prompt_snippet", ""),
            "slash_command":  t.get("slash_command", ""),
            "model":          t.get("model", ""),
            "context":        ctx,
        })
    breaks.sort(key=lambda b: -b["uncached"])
    return breaks


# ---------------------------------------------------------------------------
# Token-waste classification (v1.8.0)
# ---------------------------------------------------------------------------
# 9-category taxonomy from Jock Reeves "Token Waste Management" (2026).
# Four categories (cache_read, cache_write, reasoning, subagent_overhead)
# were already tracked; this block adds the remaining five plus per-turn
# labelling and cross-session detection helpers.

_TURN_CHARACTER_LABELS: dict[str, str] = {
    "subagent_overhead": "Subagent Dispatch",
    "paste_bomb":        "Paste-Bomb Prompt",
    "reasoning":         "Extended Thinking",
    "cache_read":        "Cache-Heavy",
    "cache_write":       "Cache Payload",
    "file_reread":       "Inefficient File Access",
    "oververbose_edit":  "Verbose Response",
    "retry_error":       "Retry Attempt",
    "dead_end":          "Stuck/Truncated",
    "productive":        "Productive",
}
_RISK_CATEGORIES: frozenset[str] = frozenset(
    {"retry_error", "dead_end", "oververbose_edit", "file_reread", "paste_bomb"}
)
# Paste-bomb threshold (P2.2): a user prompt > 5 000 characters is treated
# as a single waste category regardless of downstream effects (thinking,
# tool fan-out, cache write). Matches the threshold the audit-extract
# detailed scan already uses for its `paste_bombs` finding so the two
# detectors agree on what counts as a paste bomb.
_PASTE_BOMB_CHARS: int = 5_000

# File-reaccess detector regexes (P4.1: hoisted to module scope so they
# compile once at import-time rather than on every `_detect_file_reaccesses`
# call). See the function docstring for usage. The `(?<![\w.])` start-of-arg
# boundary is intentional — keeps `cat .claude/skills/foo.py` from matching
# `/skills/foo.py` mid-string and silently merging same-suffix files across
# projects.
_EXT_GROUP: str = (
    r"py|js|ts|mjs|jsx|tsx|json|yaml|yml|toml|sh|bash|zsh|txt|csv|md|"
    r"html|htm|css|scss|rs|go|rb|php|java|c|cpp|h|sql|xml|cfg|conf|log|"
    r"ini|env|lock"
)
_BASH_PATH_RE: re.Pattern[str] = re.compile(
    r"(?<![\w.])(?:"
    r"\.{1,2}/[\w.\-/]+\.(?:" + _EXT_GROUP + r")(?!\w)"
    r"|/[\w.\-/]+\.(?:" + _EXT_GROUP + r")(?!\w)"
    r"|~/[\w.\-/]+\.(?:py|js|ts|json|yaml|yml|md|sh|txt)(?!\w))"
)
# For Read/Edit/Write, filter out directory paths (no extension = not a file).
_READ_EXT_RE: re.Pattern[str] = re.compile(r"\.(?:" + _EXT_GROUP + r")$")


def _analyze_stop_reasons(turns: list[dict]) -> dict:
    """Aggregate stop_reason distribution across real (non-resume) turns."""
    counts: dict[str, int] = {}
    real = [t for t in turns if not t.get("is_resume_marker")]
    for t in real:
        r = t.get("stop_reason") or "unknown"
        counts[r] = counts.get(r, 0) + 1
    total = max(len(real), 1)
    return {
        "distribution": counts,
        "max_tokens_count": counts.get("max_tokens", 0),
        "max_tokens_pct":   counts.get("max_tokens", 0) / total * 100,
        "end_turn_pct":     counts.get("end_turn",   0) / total * 100,
        "tool_use_pct":     counts.get("tool_use",   0) / total * 100,
    }


def _detect_retry_chains(turns: list[dict], threshold: float = 0.80) -> dict:
    """Detect retry patterns within a single session's turn list.

    Compares consecutive user-prompt turns using SequenceMatcher. Call once
    per session (not on a cross-session flat list) to avoid false positives
    at session boundaries.
    """
    def _tok(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    prompted = [t for t in turns
                if not t.get("is_resume_marker") and (t.get("prompt_text") or "").strip()]
    # Pre-tokenize once: the inner loop would otherwise call _tok on each
    # b_text twice (SequenceMatcher arg + a_toks reassignment after match),
    # turning the O(N²) walk into 2N × re.findall on long sessions.
    pre_toks: list[list[str]] = [_tok(p["prompt_text"]) for p in prompted]

    chains: list[dict] = []
    processed: set[int] = set()

    for i in range(len(prompted) - 1):
        if i in processed:
            continue
        a_text = prompted[i]["prompt_text"]
        a_toks = pre_toks[i]
        chain = [prompted[i]["index"]]
        j = i + 1
        while j < len(prompted):
            b_text = prompted[j]["prompt_text"]
            b_toks = pre_toks[j]
            if a_text == b_text or SequenceMatcher(None, a_toks, b_toks).ratio() >= threshold:
                chain.append(prompted[j]["index"])
                processed.add(j)
                a_toks = b_toks
                a_text = b_text
                j += 1
            else:
                break
        if len(chain) >= 2:
            chain_set = set(chain)
            cost = sum(t.get("cost_usd", 0.0) for t in turns if t.get("index") in chain_set)
            chains.append({"turn_indices": chain, "length": len(chain), "cost_usd": cost})

    total_cost = sum(t.get("cost_usd", 0.0) for t in turns)
    retry_cost = sum(c["cost_usd"] for c in chains)
    return {
        "chains":          chains,
        "chain_count":     len(chains),
        "retry_cost_pct":  retry_cost / total_cost * 100 if total_cost else 0.0,
    }


def _assign_context_segments(turns: list[dict]) -> None:
    """Annotate each turn with ``_ctx_seg`` (int).

    A new segment starts when the model changes between consecutive real turns
    or when a resume marker is encountered. Resume markers themselves get the
    segment ID of the gap (not counted in file-reaccess logic since they are
    skipped there anyway).

    This is used by ``_detect_file_reaccesses`` to distinguish avoidable
    same-context re-reads (risk) from expected cross-context re-reads (e.g.
    a subagent spawned with a fresh context, or a resumed session).
    """
    seg = 0
    prev_model: str | None = None
    for t in turns:
        if t.get("is_resume_marker"):
            seg += 1
            t["_ctx_seg"] = seg
            prev_model = None
            continue
        mdl = t.get("model", "")
        if prev_model is not None and mdl != prev_model:
            seg += 1
        t["_ctx_seg"] = seg
        prev_model = mdl


def _detect_file_reaccesses(turns: list[dict]) -> dict:
    """Identify files accessed 2+ times across the provided turn list.

    For Read/Edit/Write tools, input_preview IS the file path (produced by
    _summarise_tool_input). For Bash, a regex extracts path-like substrings
    with a known-extension allowlist (prevents hidden dirs like ``.claude``
    from being matched as files).

    Uses ``_ctx_seg`` annotations (set by ``_assign_context_segments``) to
    distinguish two re-access kinds:

    - **Same-segment**: the same context reads a file 2+ times → avoidable,
      flagged as risk in ``_turn_to_paths``.
    - **Cross-segment only**: a file accessed in different model-context
      segments (subagent boundary or session resume) → expected, not risk,
      in ``_turn_to_paths_ctx``.

    Callers must strip ``_turn_to_paths`` and ``_turn_to_paths_ctx`` before
    JSON serialisation.
    """
    from collections import defaultdict

    # (path, seg) → list of turn indices that accessed path in that segment
    seg_turns: dict[tuple[str, int], list[int]] = defaultdict(list)
    # path → set of segments that touched it
    path_segs: dict[str, set[int]] = defaultdict(set)

    for t in turns:
        if t.get("is_resume_marker"):
            continue
        idx = t.get("index", -1)
        seg = t.get("_ctx_seg", 0)
        for tool in t.get("tool_use_detail", []):
            name    = tool.get("name", "")
            preview = tool.get("input_preview", "")
            if name in ("Read", "Edit", "MultiEdit", "Write") and preview and _READ_EXT_RE.search(preview):
                seg_turns[(preview, seg)].append(idx)
                path_segs[preview].add(seg)
            elif name == "Bash":
                for path in _BASH_PATH_RE.findall(preview):
                    seg_turns[(path, seg)].append(idx)
                    path_segs[path].add(seg)

    # Classify paths into same-segment re-reads (risk) vs cross-only (expected)
    same_seg_paths: set[str] = set()
    cross_only_paths: set[str] = set()
    for path, segs in path_segs.items():
        # Does any single segment have 2+ accesses?
        has_same_seg = any(len(seg_turns[(path, s)]) >= 2 for s in segs)
        total_accesses = sum(len(seg_turns[(path, s)]) for s in segs)
        if total_accesses < 2:
            continue
        if has_same_seg:
            same_seg_paths.add(path)
        else:
            cross_only_paths.add(path)

    # Build per-turn path lookup dicts.
    # Only RE-reads are flagged (skip the first access in each segment).
    turn_to_paths: dict[int, set[str]] = defaultdict(set)
    for path in same_seg_paths:
        for seg in path_segs[path]:
            # Sort so the chronologically first turn in this segment is skipped
            for idx in sorted(seg_turns[(path, seg)])[1:]:
                turn_to_paths[idx].add(path)

    # For cross-context paths, skip the earliest segment (the original read);
    # flag only the later-segment accesses as informational re-reads.
    turn_to_paths_ctx: dict[int, set[str]] = defaultdict(set)
    for path in cross_only_paths:
        min_seg = min(path_segs[path])
        for seg in path_segs[path]:
            if seg == min_seg:
                continue  # original read; not a re-read
            for idx in seg_turns[(path, seg)]:
                if idx not in turn_to_paths:
                    turn_to_paths_ctx[idx].add(path)

    all_reaccessed = same_seg_paths | cross_only_paths
    # Flatten all turn indices per path for cost/detail purposes
    all_path_turns: dict[str, list[int]] = {
        p: [i for s in path_segs[p] for i in seg_turns[(p, s)]]
        for p in all_reaccessed
    }
    turn_idx_set: dict[str, set[int]] = {p: set(v) for p, v in all_path_turns.items()}

    # Marginal-cost attribution (P1.4): the previous implementation summed
    # the entire turn cost for any turn that touched a re-read path, which
    # over-attributed waste when a turn ran 5+ tool calls but only one of
    # them hit the path. Weight per-turn contribution by
    # ``path_reads_in_turn / total_tool_calls_in_turn`` so a single Bash arg
    # in a 10-tool turn contributes 10% of the turn cost, not 100%.
    turn_cost_by_idx: dict[int, float] = {}
    turn_total_tools_by_idx: dict[int, int] = {}
    for t in turns:
        if t.get("is_resume_marker"):
            continue
        idx = t.get("index", -1)
        turn_cost_by_idx[idx] = float(t.get("cost_usd", 0.0))
        turn_total_tools_by_idx[idx] = len(t.get("tool_use_detail", []))

    path_count_per_turn: dict[tuple[str, int], int] = defaultdict(int)
    for (p, _), idx_list in seg_turns.items():
        for idx in idx_list:
            path_count_per_turn[(p, idx)] += 1

    def _path_cost(p: str) -> float:
        total = 0.0
        for idx in turn_idx_set[p]:
            denom = turn_total_tools_by_idx.get(idx, 0)
            if denom <= 0:
                continue
            total += (
                turn_cost_by_idx.get(idx, 0.0)
                * path_count_per_turn.get((p, idx), 0)
                / denom
            )
        return total

    details = sorted(
        [
            {
                "path":       p,
                "count":      len(all_path_turns[p]),
                "first_turn": min(all_path_turns[p]),
                "cross_ctx":  p in cross_only_paths,
                "cost_usd":   _path_cost(p),
            }
            for p in all_reaccessed
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    return {
        "reaccessed_count":      len(all_reaccessed),
        "details":               details,
        "total_reaccess_cost":   sum(float(d["cost_usd"]) for d in details),
        "_turn_to_paths":        dict(turn_to_paths),      # risk; strip before export
        "_turn_to_paths_ctx":    dict(turn_to_paths_ctx),  # expected; strip before export
    }


def _detect_verbose_edits(turns: list[dict], output_threshold: int = 800) -> dict:
    """Flag Edit turns with output_tokens above threshold.

    The original ratio heuristic (output/input) is not computable from
    turn records (input_preview is summarised). This proxy — high output
    on an Edit turn — catches genuine over-verbosity without needing raw
    tool input. Threshold of 800 is calibrated for Sonnet/Opus; adjust via
    the parameter if model mix shifts.
    """
    verbose = []
    for t in turns:
        if t.get("is_resume_marker"):
            continue
        if "Edit" not in (t.get("tool_use_names") or []):
            continue
        if t.get("output_tokens", 0) > output_threshold:
            verbose.append({
                "turn_index":    t["index"],
                "output_tokens": t["output_tokens"],
                "cost_usd":      t.get("cost_usd", 0.0),
            })
    verbose.sort(key=lambda x: x["output_tokens"], reverse=True)
    return {
        "verbose_count": len(verbose),
        "details":       verbose[:10],
        "total_cost":    sum(v["cost_usd"] for v in verbose),
    }


def _classify_turn(turn: dict, retry_idx: set[int],
                   reaccess_idx: set[int], verbose_idx: set[int]) -> str:
    """Assign a single waste category to a turn (priority waterfall).

    Order: subagent_overhead > paste_bomb > reasoning > cache_read >
           cache_write > file_reread > oververbose_edit > retry_error >
           dead_end > productive

    paste_bomb fires above reasoning so a turn with a >5 KB pasted prompt
    that also triggers thinking surfaces as a paste-bomb (the actionable
    user behaviour) rather than as reasoning (the downstream effect).
    """
    names    = turn.get("tool_use_names") or []
    idx      = turn.get("index", -1)
    cb       = turn.get("content_blocks") or {}
    cr       = int(turn.get("cache_read_tokens", 0))
    cw       = int(turn.get("cache_write_tokens", 0))
    inp      = int(turn.get("input_tokens", 0))
    total_in = inp + cr

    if "Agent" in names or "Task" in names:
        return "subagent_overhead"
    if len(turn.get("prompt_text") or "") > _PASTE_BOMB_CHARS:
        return "paste_bomb"
    if cb.get("thinking", 0) > 0:
        return "reasoning"
    if cr > 100_000 and total_in > 0 and cr / total_in > 0.5:
        return "cache_read"
    if cw > 100_000:
        return "cache_write"
    if idx in reaccess_idx:
        return "file_reread"
    if idx in verbose_idx:
        return "oververbose_edit"
    if idx in retry_idx:
        return "retry_error"
    if turn.get("stop_reason") == "max_tokens":
        return "dead_end"
    return "productive"


def _build_waste_analysis(sessions: list[dict]) -> dict:
    """Orchestrate all waste-detection passes and per-turn classification.

    ``sessions`` must already have ``_attribute_subagent_tokens`` and
    ``_detect_cache_breaks`` applied (both mutate turn dicts in place).

    Modifies turn dicts in place, adding:
        turn_character       str  — technical key
        turn_character_label str  — display label
        turn_risk            bool — True for inherently wasteful categories

    Returns the top-level waste_analysis dict (stripped of internal keys).
    """
    from collections import Counter

    all_turns = [t for s in sessions for t in s.get("turns", [])]

    # Annotate context segments before detection (model-switch = new context)
    _assign_context_segments(all_turns)

    # Retry: per-session to avoid cross-session false matches
    all_chains: list[dict] = []
    for s in sessions:
        r = _detect_retry_chains(s.get("turns", []))
        all_chains.extend(r["chains"])
    total_cost = sum(t.get("cost_usd", 0.0) for t in all_turns)
    retry_cost = sum(c["cost_usd"] for c in all_chains)
    retry_result = {
        "chains":         all_chains,
        "chain_count":    len(all_chains),
        "retry_cost_pct": retry_cost / total_cost * 100 if total_cost else 0.0,
    }

    # File re-access, verbose edits, stop reasons: cross-session is valid
    stop_reasons    = _analyze_stop_reasons(all_turns)
    reaccess_result = _detect_file_reaccesses(all_turns)
    verbose_result  = _detect_verbose_edits(all_turns)

    # Build O(1) lookup sets for classifier
    retry_idx           = {i for c in retry_result["chains"] for i in c["turn_indices"]}
    reaccess_idx        = set(reaccess_result["_turn_to_paths"].keys())
    cross_ctx_reaccess_idx = set(reaccess_result["_turn_to_paths_ctx"].keys())
    verbose_idx         = {v["turn_index"] for v in verbose_result["details"]}

    # Classify and annotate every turn in place
    distribution: Counter = Counter()
    for t in all_turns:
        if t.get("is_resume_marker"):
            t["turn_character"]       = "productive"
            t["turn_character_label"] = _TURN_CHARACTER_LABELS["productive"]
            t["turn_risk"]            = False
            t["reread_cross_ctx"]     = False
            continue
        idx  = t.get("index", -1)
        char = _classify_turn(t, retry_idx, reaccess_idx, verbose_idx)
        # Cross-context re-reads: same classification, but not a risk signal
        if char != "file_reread" and idx in cross_ctx_reaccess_idx:
            char = "file_reread"
        cross_ctx = idx in cross_ctx_reaccess_idx and idx not in reaccess_idx
        t["turn_character"]       = char
        t["turn_character_label"] = _TURN_CHARACTER_LABELS[char]
        t["turn_risk"]            = char in _RISK_CATEGORIES and not cross_ctx
        t["reread_cross_ctx"]     = cross_ctx
        if char == "file_reread":
            paths_map = (reaccess_result["_turn_to_paths_ctx"]
                         if cross_ctx else reaccess_result["_turn_to_paths"])
            t["reaccessed_paths"] = sorted(
                paths_map.get(idx, set())
            )
        distribution[char] += 1

    _STRIP = {"_turn_to_paths", "_turn_to_paths_ctx"}
    reaccess_out = {k: v for k, v in reaccess_result.items() if k not in _STRIP}

    return {
        "stop_reasons":    stop_reasons,
        "retry_chains":    retry_result,
        "file_reaccesses": reaccess_out,
        "verbose_edits":   verbose_result,
        "distribution":    dict(distribution),
    }


def _empty_skill_row(name: str) -> dict:
    return {
        "name":             name,
        "invocations":      0,
        "turns_attributed": 0,
        "input":            0,
        "output":           0,
        "cache_read":       0,
        "cache_write":      0,
        "total_tokens":     0,
        "cost_usd":         0.0,
        "pct_total_cost":   0.0,
        "cache_hit_pct":    0.0,
        "session_count":    0,
        "_sessions":        set(),  # stripped before return
    }


def _accumulate_bucket(row: dict, t: dict) -> None:
    row["input"]        += int(t.get("input_tokens", 0))
    row["output"]       += int(t.get("output_tokens", 0))
    row["cache_read"]   += int(t.get("cache_read_tokens", 0))
    row["cache_write"]  += int(t.get("cache_write_tokens", 0))
    row["total_tokens"] += int(t.get("total_tokens", 0))
    row["cost_usd"]     += float(t.get("cost_usd", 0.0))
    row["turns_attributed"] += 1


def _finalise_skill_rows(rows: dict, total_cost: float) -> list[dict]:
    """Compute derived fields (pct_total_cost, cache_hit_pct) and drop the
    internal ``_sessions`` set; return a list ordered by cost descending."""
    out: list[dict] = []
    for _, row in rows.items():
        row = dict(row)
        row["session_count"] = len(row.pop("_sessions", set()) or set())
        total_input_side = (row["input"] + row["cache_read"] + row["cache_write"]) or 1
        row["cache_hit_pct"] = round(100.0 * row["cache_read"] / total_input_side, 1)
        row["pct_total_cost"] = (
            round(100.0 * row["cost_usd"] / total_cost, 2) if total_cost else 0.0
        )
        out.append(row)
    out.sort(key=lambda r: -r["cost_usd"])
    return out


def _build_by_skill(sessions: list[dict], total_cost: float) -> list[dict]:
    """Aggregate per-turn tokens/cost by the active skill or slash command.

    Attribution model (matches Anthropic's analyze-sessions.mjs approach):
      - A user prompt with a leading slash-command (``/foo``) sets the
        "current skill" to ``foo`` for that prompt and every follow-up
        assistant turn driven by it (tool-use loops count).
      - A new user prompt *without* a slash-command clears the current
        skill (subsequent turns are un-attributed).
      - A ``Skill`` tool_use block inside any turn overrides attribution
        for *that turn only* to the invoked skill name (``input.skill``).
      - Turns without any signal are simply not attributed (they still
        count toward the report's ``totals`` but not any skill row).

    Boundary detection between user prompts: we use ``prompt_text`` —
    each turn carries a snapshot of the user entry that immediately
    preceded its first occurrence (``_preceding_user_content``), which
    in a tool-use chain is either the original prompt (first turn) or
    a ``tool_result`` entry (subsequent turns). Only text-bearing prompts
    contribute a non-empty ``prompt_text``; tool_result-only content
    flattens to "". The boundary heuristic fires when ``prompt_text``
    becomes non-empty and differs from the previous prompt we tracked.
    """
    rows: dict[str, dict] = {}
    for session in sessions:
        sid = session.get("session_id", "")
        current_skill: str | None = None
        last_prompt_text: str = ""
        for t in session.get("turns", []) or []:
            if t.get("is_resume_marker"):
                continue
            prompt_text = (t.get("prompt_text") or "").strip()
            boundary_hit = bool(prompt_text) and prompt_text != last_prompt_text
            boundary_skill = ""
            if boundary_hit:
                last_prompt_text = prompt_text
                raw_slash = t.get("slash_command") or ""
                # Strip the leading "/" so slash commands key-match Skill-tool
                # invocations (e.g. "/session-metrics" slash ↔ "session-metrics"
                # Skill tool-use invocation are merged into one row). This
                # matches Anthropic session-report's convention.
                new_skill = raw_slash.lstrip("/") if raw_slash else ""
                current_skill = new_skill or None
                if new_skill:
                    rows.setdefault(new_skill, _empty_skill_row(new_skill))["invocations"] += 1
                    boundary_skill = new_skill
            # Turn-scope override: Skill tool-use invocation attributes this
            # turn to the invoked skill name regardless of current_skill.
            invoked = t.get("skill_invocations") or []
            if invoked:
                skill_here = invoked[0]
                row = rows.setdefault(skill_here, _empty_skill_row(skill_here))
                _accumulate_bucket(row, t)
                row["_sessions"].add(sid)
                # A slash command answered by a Skill tool_use for the SAME
                # skill on the SAME turn is one user invocation, not two —
                # the boundary branch above already counted it. Subtract the
                # overlap rather than skipping the whole increment so extra
                # Skill calls in the same turn still count individually.
                n_invoked = len(invoked)
                if boundary_skill and boundary_skill == skill_here:
                    n_invoked -= 1
                row["invocations"] += n_invoked
            elif current_skill:
                row = rows.setdefault(current_skill, _empty_skill_row(current_skill))
                _accumulate_bucket(row, t)
                row["_sessions"].add(sid)
    return _finalise_skill_rows(rows, total_cost)


# Skill-name aliases that all attribute back to "session-metrics" for the
# self-cost meta-metric. The user's slash-command name and the marketplace
# plugin namespace both surface in the by_skill aggregation; map them here
# so the meta-metric stays correct regardless of how the skill was invoked.
_SELF_COST_SKILL_NAMES = frozenset({
    "session-metrics",
    "session-metrics:session-metrics",
})


def _summarize_self_cost(by_skill: list[dict]) -> dict:
    """Return the running-total cost of session-metrics' own prior turns.

    The current invocation's tokens are not yet written to the JSONL when
    the script reads it, so this metric is intentionally a "prior turns
    in this session" figure — first-ever invocation correctly reports
    zero. Surfaces as a stderr line, an HTML KPI card, and a top-level
    JSON key so users can audit the cost of their own observability
    tooling alongside their session work.
    """
    out = {
        "turns":          0,
        "input":          0,
        "output":         0,
        "cache_read":     0,
        "cache_write":    0,
        "total_tokens":   0,
        "cost_usd":       0.0,
        "matched_skill_names": [],
        "note": "Running total of prior session-metrics turns in this "
                "session; the current invocation is not yet written to "
                "the JSONL when the script reads it.",
    }
    for row in by_skill or []:
        name = row.get("name") or ""
        if name not in _SELF_COST_SKILL_NAMES:
            continue
        out["turns"]        += int(row.get("turns_attributed", 0) or 0)
        out["input"]        += int(row.get("input", 0) or 0)
        out["output"]       += int(row.get("output", 0) or 0)
        out["cache_read"]   += int(row.get("cache_read", 0) or 0)
        out["cache_write"]  += int(row.get("cache_write", 0) or 0)
        out["total_tokens"] += int(row.get("total_tokens", 0) or 0)
        out["cost_usd"]     += float(row.get("cost_usd", 0.0) or 0.0)
        out["matched_skill_names"].append(name)
    out["cost_usd"] = round(out["cost_usd"], 6)
    return out


# Connective markers that hint a single prompt bundles multiple asks
# ("fix the test AND update the README", "do X; then Y"). Used by
# ``_build_request_units`` to set a conservative ``multi_intent_possible``
# flag — a HINT for the optional LLM grouping pass, never a hard split.
# Deliberately biased toward false negatives (only fires on explicit
# enumeration) so the flag does not cry wolf on ordinary prose.
_MULTI_INTENT_RE = re.compile(
    r"(?:\b(?:also|then|additionally|afterwards?)\b"
    r"|;\s|\n\s*[-*\d]"          # semicolons / bullet or numbered lines
    r"|\band then\b)",
    re.IGNORECASE,
)


def _detect_multi_intent(prompt_text: str) -> bool:
    """Conservative heuristic: does this prompt bundle ≥2 distinct asks?

    Fires only on explicit enumeration (≥2 connective markers in a prompt
    long enough to plausibly hold two asks). The deterministic layer keeps
    the request unit indivisible regardless — this flag only tells the LLM
    pass "consider whether this one prompt was really two tasks".
    """
    text = (prompt_text or "").strip()
    if len(text) < 60:
        return False
    return len(_MULTI_INTENT_RE.findall(text)) >= 2


def _build_request_units(sessions: list[dict]) -> list[dict]:
    """Group turns into deterministic "request units" by prompt anchor.

    A **request unit** = every turn sharing one ``prompt_anchor_index`` —
    i.e. all assistant/tool/subagent work caused by a single user prompt.
    Subagent turns inherit their spawning prompt's anchor
    (``_compute_prompt_anchor_indices``), so a unit's combined cost already
    captures the subagent chain. This is a *per-utterance* carve-up, NOT a
    semantic task: one prompt can bundle several asks and one task can span
    many follow-up prompts. The honest UI label is "per-request breakdown".

    Cost invariant: summing each unit's ``combined_cost_usd`` over a session
    reproduces that session's ``subtotal.cost`` to float precision, because
    every non-resume turn lands in exactly one unit and ``cost_usd`` is summed
    over the whole group (the headline total is itself parent + subagent
    direct cost). Tool histogram and waste signals aggregate over the MAIN
    (non-subagent) turns only — they describe the main-thread work; subagent
    internals are covered by the subagent / workflow tables.

    The grouping key is the compound ``(session_id, anchor_index)`` so project
    and instance scopes keep per-session units distinct (global turn indices
    are unique today, but a unit's identity should not depend on that).
    """
    from collections import Counter

    units: list[dict] = []
    for session in sessions:
        sid = session.get("session_id", "")
        groups: dict[int, list[dict]] = {}
        order: list[int] = []
        for t in session.get("turns", []) or []:
            if t.get("is_resume_marker"):
                continue
            anchor = t.get("prompt_anchor_index", t.get("index"))
            if anchor not in groups:
                groups[anchor] = []
                order.append(anchor)
            groups[anchor].append(t)

        prev_end_epoch = 0
        for anchor in order:
            turns = groups[anchor]
            # The anchor turn is the prompt-bearing main turn (index == anchor);
            # fall back to the earliest turn if the anchor turn was filtered.
            anchor_turn = next(
                (t for t in turns if t.get("index") == anchor), turns[0])

            tool_hist: Counter = Counter()
            risk = cbreaks = 0
            cross_ctx = False
            reread_paths: set[str] = set()
            direct_cost = sub_cost = 0.0
            tokens = inp = out = cread = cwrite = 0
            for t in turns:
                cost = float(t.get("cost_usd", 0.0))
                if t.get("subagent_agent_id"):
                    sub_cost += cost
                else:
                    direct_cost += cost
                    for n in (t.get("tool_use_names") or []):
                        tool_hist[n] += 1
                    if t.get("turn_risk"):
                        risk += 1
                    if t.get("is_cache_break"):
                        cbreaks += 1
                    if t.get("reread_cross_ctx"):
                        cross_ctx = True
                    for p in (t.get("reaccessed_paths") or []):
                        reread_paths.add(p)
                tokens += int(t.get("total_tokens", 0))
                inp    += int(t.get("input_tokens", 0))
                out    += int(t.get("output_tokens", 0))
                cread  += int(t.get("cache_read_tokens", 0))
                cwrite += int(t.get("cache_write_tokens", 0))

            start_ts = anchor_turn.get("timestamp", "")
            end_ts   = turns[-1].get("timestamp", "")
            start_e  = _parse_iso_epoch(start_ts)
            end_e    = _parse_iso_epoch(end_ts)
            wall = (end_e - start_e) if (start_e and end_e and end_e > start_e) else 0
            idle = (
                (start_e - prev_end_epoch)
                if (prev_end_epoch and start_e and start_e > prev_end_epoch)
                else 0
            )
            if end_e:
                prev_end_epoch = end_e

            indices = [idx for t in turns
                       if isinstance((idx := t.get("index")), int)]
            prompt_text = anchor_turn.get("prompt_text") or ""
            units.append({
                "unit_id":           f"{sid}:{anchor}",
                "session_id":        sid,
                "anchor_index":      anchor,
                "prompt_snippet":    anchor_turn.get("prompt_snippet") or "",
                "prompt_text":       prompt_text,
                "slash_command":     (anchor_turn.get("slash_command") or "").strip(),
                "skill_invocations": sorted(
                    {s for t in turns for s in (t.get("skill_invocations") or [])}),
                "spawned_subagents": sorted(
                    {s for t in turns for s in (t.get("spawned_subagents") or [])}),
                "workflow_run_ids":  sorted(
                    {rid for t in turns
                     if (rid := t.get("workflow_run_id"))}),
                "turn_count":        len(turns),
                "first_index":       min(indices) if indices else anchor,
                "last_index":        max(indices) if indices else anchor,
                "start_ts":          start_ts,
                "end_ts":            end_ts,
                "wall_clock_seconds":      wall,
                "idle_gap_before_seconds": idle,
                "cost_usd":           round(direct_cost, 6),
                "subagent_cost_usd":  round(sub_cost, 6),
                "combined_cost_usd":  round(direct_cost + sub_cost, 6),
                "total_tokens":       tokens,
                "input":              inp,
                "output":             out,
                "cache_read":         cread,
                "cache_write":        cwrite,
                "tool_histogram":     dict(tool_hist.most_common()),
                "risk_turn_count":    risk,
                "reread_path_count":  len(reread_paths),
                "reread_cross_ctx":   cross_ctx,
                "cache_break_count":  cbreaks,
                "multi_intent_possible": _detect_multi_intent(prompt_text),
                "is_post_compaction": any(
                    t.get("is_post_compaction") for t in turns),
            })
    return units


# C.5: velocity discipline. A single request unit can carry a wall-clock
# outlier — a long-running agent, or a prompt the user left mid-stream — that
# would dominate any throughput average. Cap each unit's contribution at
# 30 minutes so one outlier can't swamp the cohort. Idle gaps between units
# (lunch breaks) are excluded from active time by construction (we sum capped
# *work* wall-clock, never the idle gap), so no separate idle cap is needed.
_VELOCITY_CYCLE_CAP_S = 1800


def _compute_velocity_stats(units: list[dict]) -> dict:
    """Throughput statistics over the request units' wall-clock.

    The "filtered sample" is the set of units with a measured positive
    ``wall_clock_seconds`` (units with no usable timestamp diff contribute no
    duration and would otherwise drag the mean toward zero). Mean and the p50/
    p90 percentiles are computed over that *same* capped sample so they describe
    one cohort, and the per-active-minute rates use the capped active minutes as
    the denominator. Returns ``{}`` when no unit has a usable duration.
    """
    sample: list[int] = []
    cost = 0.0
    tokens = 0
    for u in units:
        w = int(u.get("wall_clock_seconds", 0))
        if w <= 0:
            continue
        sample.append(min(w, _VELOCITY_CYCLE_CAP_S))
        cost += float(u.get("combined_cost_usd", 0.0))
        tokens += int(u.get("total_tokens", 0))
    if not sample:
        return {}
    active_minutes = sum(sample) / 60.0
    return {
        "unit_count":            len(units),
        "filtered_unit_count":   len(sample),
        "active_minutes":        round(active_minutes, 4),
        "mean_cycle_s":          round(sum(sample) / len(sample), 2),
        "p50_cycle_s":           _sm()._percentile(sample, 50),
        "p90_cycle_s":           _sm()._percentile(sample, 90),
        "cost_per_active_min":   round(cost / active_minutes, 6) if active_minutes else 0.0,
        "tokens_per_active_min": round(tokens / active_minutes, 2) if active_minutes else 0.0,
    }


# Schema version of the grouping.json consumed by ``--render-tasks``. Bumped
# only when the grouping interchange shape changes (the renderer warns on a
# mismatch so a stale grouping file produced against an older export doesn't
# silently render wrong). Independent of _SKILL_VERSION.
_TASKS_GROUPING_SCHEMA_VERSION = "1"

_TASK_VERDICTS = ("worth_it", "mixed", "likely_waste")

# --- Prepare-tasks skeleton (v1.55.0) --------------------------------------
# ``--prepare-tasks`` emits a compact worksheet + a *renderable* candidate
# grouping skeleton so the Tasks-companion model EDITS a pre-clustered file
# instead of authoring grouping.json from scratch (author -> editor). The
# heuristics below are deliberately conservative — a multi-AI design review
# (v1.55.0) confirmed three failure modes the naive version hit:
#   * blank-snippet units (tool-result-only turns) must NOT each seed a task;
#   * skill-preamble boilerplate ("Base directory for this skill: …") makes a
#     terrible seeded title;
#   * pre-filling ``likely_waste`` anchors the model into rubber-stamping it.

# Snippet prefixes that read as injected boilerplate rather than a user's
# intent — a slash-command dispatch injects the skill's SKILL.md preamble as
# the prompt, so the unit snippet starts with this. Unusable as a seed title.
_SKILL_PREAMBLE_PREFIXES = ("Base directory for this skill:",)

# Waste-ratio thresholds for the deterministic verdict SUGGESTION. Biased to
# worth_it/mixed (matching the SKILL.md grouping rule). The script NEVER
# pre-fills ``likely_waste``: above the high threshold it returns "" so the
# model must make that call itself, avoiding a noisy-signal rubber-stamp.
_VERDICT_MIXED_RATIO = 0.15
_VERDICT_FORCE_MODEL_RATIO = 0.5


def _is_continuation_snippet(snippet: str) -> bool:
    """True when a unit's prompt is a collapsed background-agent completion
    (``↳ …``) — a continuation of the work that spawned it, not a new user
    goal (see ``_summarise_task_notification``)."""
    return snippet.lstrip().startswith("↳")


def _is_seedable_title_snippet(snippet: str) -> bool:
    """True when a snippet reads as a user-authored task title (usable as a
    seeded skeleton title). Excludes blank, ``↳`` continuation, and
    skill-preamble boilerplate snippets."""
    s = snippet.strip()
    if not s or s.startswith("↳"):
        return False
    return not any(s.startswith(p) for p in _SKILL_PREAMBLE_PREFIXES)


def _suggest_verdict(members: list[dict]) -> str:
    """Deterministic verdict suggestion for a skeleton cluster.

    Aggregates per-unit waste signals (risk turns, path re-reads, cache
    breaks) over ``members`` and maps the ratio against total turns. Returns
    only ``"worth_it"`` or ``"mixed"``; returns ``""`` (let the model decide)
    when the waste ratio is high enough that ``likely_waste`` is plausible —
    pre-filling that label biases the model into rubber-stamping it.
    """
    turns = sum(int(u.get("turn_count", 0)) for u in members) or 1
    waste = sum(int(u.get("risk_turn_count", 0))
                + int(u.get("reread_path_count", 0))
                + int(u.get("cache_break_count", 0)) for u in members)
    ratio = waste / turns
    if ratio >= _VERDICT_FORCE_MODEL_RATIO:
        return ""
    if ratio >= _VERDICT_MIXED_RATIO:
        return "mixed"
    return "worth_it"


def _cluster_request_units(units: list[dict]) -> list[list[dict]]:
    """Conservative deterministic clustering of request units into candidate
    task groups. High-confidence attachment only:

      * a blank-snippet unit (tool-result-only turn, no user prompt) attaches
        to the current cluster — never seeds its own task;
      * a ``↳ …`` continuation unit attaches to the current cluster;
      * a unit repeating the current cluster's slash command attaches;
      * any other unit (a real, distinct user prompt) starts a NEW cluster.

    The model refines (merge/split) from here — this only removes the
    mechanical, high-error work and prevents spurious one-unit tasks from
    blank / continuation units. Input order is preserved.
    """
    clusters: list[list[dict]] = []
    cur_slash = ""
    for u in units:
        snippet = u.get("prompt_snippet") or ""
        slash = (u.get("slash_command") or "").strip()
        attach = bool(clusters) and (
            not snippet.strip()
            or _is_continuation_snippet(snippet)
            or (bool(slash) and slash == cur_slash)
        )
        if attach:
            clusters[-1].append(u)
        else:
            clusters.append([u])
            cur_slash = slash
    return clusters


def _seed_title(cluster: list[dict]) -> str:
    """Seeded title for a candidate cluster: the first member snippet that
    reads as a user-authored title (non-blank, non-continuation,
    non-preamble), truncated. Falls back to a neutral anchor-range label so a
    cluster of only blank/continuation/preamble units never gets a blank title
    (which would collide with the collapse guardrail)."""
    for u in cluster:
        snip = (u.get("prompt_snippet") or "").strip()
        if _is_seedable_title_snippet(snip):
            return snip[:60]
    first = cluster[0].get("anchor_index", "?")
    last = cluster[-1].get("anchor_index", "?")
    return f"Requests {first}–{last}" if first != last else f"Request {first}"


def _build_tasks_skeleton(report: dict) -> dict:
    """Build a renderable candidate grouping from an export's request_units.

    Deterministic: clusters units (``_cluster_request_units``), seeds a
    non-blank title per cluster, and pre-fills a conservative verdict
    suggestion. Each task is marked ``_auto_title: true`` and carries a
    ``_hint`` with the verdict math; ``_assemble_tasks`` ignores the
    underscore fields for cost/coverage but reads ``_auto_title`` for the
    auto-title collapse guard. A zero-edit skeleton renders a correct,
    non-collapsed Tasks page (graceful degradation).
    """
    units = report.get("request_units") or []
    tasks: list[dict] = []
    for cluster in _cluster_request_units(units):
        verdict = _suggest_verdict(cluster)
        turns = sum(int(u.get("turn_count", 0)) for u in cluster) or 1
        waste = sum(int(u.get("risk_turn_count", 0))
                    + int(u.get("reread_path_count", 0))
                    + int(u.get("cache_break_count", 0)) for u in cluster)
        tasks.append({
            "title":            _seed_title(cluster),
            "verdict":          verdict,
            "rationale":        "",
            "request_unit_ids": [u.get("unit_id") for u in cluster],
            "_auto_title":      True,
            "_hint": {
                "waste_ratio":       round(waste / turns, 2),
                "suggested_verdict": verdict or "likely_waste?",
                "members":           len(cluster),
            },
        })
    sessions = report.get("sessions") or []
    scope = (f"session_{(sessions[0].get('session_id') or '')[:8]}"
             if len(sessions) == 1 else (report.get("mode") or ""))
    return {
        "schema_version": _TASKS_GROUPING_SCHEMA_VERSION,
        "scope_label":    scope,
        "tasks":          tasks,
    }


# Above this many request units a full one-line-per-unit worksheet (~120 chars
# each) would flood --prepare-tasks stdout that the editing model must read back
# -> "Prompt is too long". Past the cap we emit a bounded per-CLUSTER summary
# instead; the written *_grouping.json skeleton stays the authoritative per-unit
# surface the model edits, so no unit is hidden from the grouping. Sized for a
# comfortable read-back (~120 lines ~= 15 KB); the moderate manual case keeps the
# rich per-unit view.
_TASKS_WORKSHEET_UNIT_CAP = 120


def _render_tasks_worksheet(report: dict) -> str:
    """Compact one-line-per-request-unit worksheet for ``--prepare-tasks``
    stdout — gives the editing model every grouping signal without loading
    full ``prompt_text`` (the jq-probe replacement). Each row shows its
    candidate-cluster number so the model sees the proposed grouping inline.

    On a large session (> ``_TASKS_WORKSHEET_UNIT_CAP`` units) a per-unit dump
    would overflow the prompt the model reads back, so it falls back to a
    bounded per-cluster summary (``_render_tasks_cluster_summary``).
    """
    units = report.get("request_units") or []
    clusters = _cluster_request_units(units)
    if len(units) > _TASKS_WORKSHEET_UNIT_CAP:
        return _render_tasks_cluster_summary(units, clusters)
    cl_of: dict = {}
    for i, cl in enumerate(clusters, 1):
        for u in cl:
            cl_of[u.get("unit_id")] = i
    lines = [f"{len(units)} request units -> {len(clusters)} candidate clusters",
             "(cl = candidate cluster; r/rr/cb = risk/reread/cache-break; "
             "[cont]=agent-continuation [blank]=no-prompt unit)", "",
             f"{'unit':>6} {'cl':>3} {'turns':>5} {'cost$':>9} {'tokens':>9} "
             f"{'r/rr/cb':>9} {'idle_s':>7}  snippet  [tools]"]
    for u in units:
        uid = u.get("unit_id") or ""
        short = uid.split(":")[-1]
        snip = (u.get("prompt_snippet") or "").replace("\n", " ")
        tag = (" [cont]" if _is_continuation_snippet(snip)
               else " [blank]" if not snip.strip() else "")
        tools = ",".join(list((u.get("tool_histogram") or {}).keys())[:3])
        risk = (f'{u.get("risk_turn_count", 0)}/'
                f'{u.get("reread_path_count", 0)}/'
                f'{u.get("cache_break_count", 0)}')
        lines.append(
            f"{short:>6} {cl_of.get(uid, '?'):>3} {u.get('turn_count', 0):>5} "
            f"{u.get('combined_cost_usd', 0.0):>9.4f} "
            f"{u.get('total_tokens', 0):>9} {risk:>9} "
            f"{int(u.get('idle_gap_before_seconds', 0)):>7}  "
            f"{snip[:70]}{tag}  [{tools}]")
    return "\n".join(lines)


def _render_tasks_cluster_summary(units: list, clusters: list) -> str:
    """Bounded per-cluster fallback for ``_render_tasks_worksheet`` on a large
    session. One line per candidate cluster (not per unit), itself capped at
    ``_TASKS_WORKSHEET_UNIT_CAP`` clusters with an explicit overflow note, so the
    stdout the model reads back stays a predictable size regardless of session
    length. The full per-unit detail and every ``unit_id`` live in the written
    ``*_grouping.json`` skeleton, which remains the surface the model edits.
    """
    def _span(cl: list) -> str:
        first = (cl[0].get("unit_id") or "").split(":")[-1] or "?"
        last = (cl[-1].get("unit_id") or "").split(":")[-1] or "?"
        return first if first == last else f"{first}..{last}"

    shown = clusters[:_TASKS_WORKSHEET_UNIT_CAP]
    lines = [
        f"{len(units)} request units -> {len(clusters)} candidate clusters "
        f"(LARGE session: per-CLUSTER summary — per-unit detail and every "
        f"unit_id are in the written *_grouping.json skeleton; edit that file, "
        f"do NOT re-probe the export)",
        "(cl = candidate cluster; r/rr/cb = risk/reread/cache-break totals)", "",
        f"{'cl':>3} {'units':>5} {'span':>13} {'turns':>5} {'cost$':>9} "
        f"{'tokens':>9} {'r/rr/cb':>10}  title/snippet",
    ]
    for i, cl in enumerate(shown, 1):
        turns = sum(int(u.get("turn_count", 0)) for u in cl)
        cost = sum(float(u.get("combined_cost_usd", 0.0)) for u in cl)
        toks = sum(int(u.get("total_tokens", 0)) for u in cl)
        risk = sum(int(u.get("risk_turn_count", 0)) for u in cl)
        rr = sum(int(u.get("reread_path_count", 0)) for u in cl)
        cb = sum(int(u.get("cache_break_count", 0)) for u in cl)
        title = _seed_title(cl).replace("\n", " ")
        lines.append(
            f"{i:>3} {len(cl):>5} {_span(cl):>13} {turns:>5} {cost:>9.4f} "
            f"{toks:>9} {f'{risk}/{rr}/{cb}':>10}  {title[:60]}")
    if len(clusters) > len(shown):
        lines.append(
            f"... ({len(clusters) - len(shown)} more clusters omitted for "
            f"length — full grouping is in the written *_grouping.json skeleton)")
    return "\n".join(lines)


def _assemble_tasks(report: dict, grouping: dict) -> dict:
    """Validate a Claude-authored ``grouping`` and resolve it against the
    export's ``request_units``, computing every total FROM THE EXPORT.

    The grouping file only assigns ``request_unit_ids`` to titled tasks and
    labels each with a verdict + rationale — it is never trusted for cost or
    token math (an LLM must not sum money). This function looks each member
    unit up in ``report["request_units"]`` and sums the deterministic figures,
    so a task's cost is always the exact sum of its members.

    Validation (surfaced as ``warnings``, never silently dropped):
      - schema-version mismatch,
      - unknown unit ids (referenced but absent from the export),
      - duplicate unit ids (a unit claimed by more than one task),
      - uncovered units (present in the export but in no task) — collected
        into a synthetic trailing "Ungrouped requests" task so the page's
        totals still reconcile to the report.

    Returns ``{schema_version, tasks, warnings, coverage_pct,
    total_cost_usd, total_turns, unit_count, grouped_unit_count}``.
    """
    units_by_id = {u.get("unit_id"): u for u in (report.get("request_units") or [])}
    all_ids = list(units_by_id)
    warnings: list[str] = []

    gv = str(grouping.get("schema_version") or "")
    if not gv:
        warnings.append(
            f"grouping has no schema_version; expected "
            f"{_TASKS_GROUPING_SCHEMA_VERSION!r} — rendering best-effort")
    elif gv != _TASKS_GROUPING_SCHEMA_VERSION:
        warnings.append(
            f"grouping schema_version {gv!r} != expected "
            f"{_TASKS_GROUPING_SCHEMA_VERSION!r}; rendering best-effort")

    seen: set[str] = set()
    tasks_out: list[dict] = []
    for raw in grouping.get("tasks") or []:
        if not isinstance(raw, dict):
            warnings.append(f"ignoring non-object task entry: {raw!r}")
            continue
        member_ids = list(raw.get("request_unit_ids") or [])
        members: list[dict] = []
        for uid in member_ids:
            if uid not in units_by_id:
                warnings.append(f"task {raw.get('title','?')!r} references "
                                f"unknown request unit {uid!r}")
                continue
            if uid in seen:
                warnings.append(f"request unit {uid!r} assigned to more than "
                                f"one task; counted once")
                continue
            seen.add(uid)
            members.append(units_by_id[uid])
        verdict = raw.get("verdict") or ""
        if verdict and verdict not in _TASK_VERDICTS:
            warnings.append(f"task {raw.get('title','?')!r} has unknown "
                            f"verdict {verdict!r}")
        tasks_out.append(_summarise_task(
            raw.get("title") or "Untitled task", verdict,
            raw.get("rationale") or "", members,
            auto_title=bool(raw.get("_auto_title"))))

    uncovered = [units_by_id[uid] for uid in all_ids if uid not in seen]
    if uncovered:
        tasks_out.append(_summarise_task(
            "Ungrouped requests", "",
            "Requests the grouping did not assign to any task.", uncovered))

    grouped = len(seen)

    # Collapse guardrail: a blank/placeholder-titled task that swallows the bulk
    # of the requests is the degenerate "one big blob" grouping (e.g. an inline
    # heuristic that gave up on semantic segmentation), not a real grouping.
    # Anchor on the title (a well-titled single task covering a focused session
    # is legitimate); coverage is the secondary signal. Exclude the synthetic
    # "Ungrouped requests" task — its high coverage is the already-warned
    # under-assignment case, a different condition.
    if len(all_ids) >= 3:
        for t in tasks_out:
            if t["title"] == "Ungrouped requests":
                continue
            cov = 100.0 * t["member_count"] / len(all_ids)
            if t["title"] in ("", "Untitled task"):
                if cov > 60.0:
                    warnings.append(
                        f"task covers {cov:.0f}% of all requests but has no "
                        f"title — looks like an un-grouped collapse, not a "
                        f"semantic grouping; re-run with one titled task per goal")
            # Auto-title collapse guard (v1.55.0): a prepare-tasks skeleton
            # marks its seeded titles ``_auto_title``. A non-blank seeded title
            # bypasses the blank-title guard above, so an unedited mega-cluster
            # would render silently. Warn when an auto-title task still swallows
            # the bulk of the requests — the model rubber-stamped the skeleton
            # instead of naming (or splitting) the cluster.
            elif t.get("auto_title") and cov > 60.0:
                warnings.append(
                    f"task {t['title']!r} still has its auto-generated "
                    f"skeleton title and covers {cov:.0f}% of all requests — "
                    f"rename it to a real goal or split it; an unedited "
                    f"mega-cluster is not a semantic grouping")

    return {
        "schema_version":     _TASKS_GROUPING_SCHEMA_VERSION,
        "scope_label":        grouping.get("scope_label") or "",
        "tasks":              tasks_out,
        "warnings":           warnings,
        "unit_count":         len(all_ids),
        "grouped_unit_count": grouped,
        "coverage_pct":       round(100.0 * grouped / len(all_ids), 1) if all_ids else 0.0,
        "total_cost_usd":     round(sum(t["cost_usd"] for t in tasks_out), 6),
        "total_turns":        sum(t["turn_count"] for t in tasks_out),
    }


def _summarise_task(title: str, verdict: str, rationale: str,
                    members: list[dict], auto_title: bool = False) -> dict:
    """Roll a task's member request units into deterministic totals.

    ``auto_title`` carries the grouping's ``_auto_title`` flag through to the
    assembled task so the auto-title collapse guard in ``_assemble_tasks`` can
    distinguish a model-named task from an unedited skeleton seed.
    """
    from collections import Counter
    hist: Counter = Counter()
    for u in members:
        hist.update(u.get("tool_histogram") or {})
    return {
        "title":             title,
        "verdict":           verdict,
        "rationale":         rationale,
        "auto_title":        auto_title,
        "member_count":      len(members),
        "turn_count":        sum(int(u.get("turn_count", 0)) for u in members),
        "cost_usd":          round(sum(float(u.get("combined_cost_usd", 0.0))
                                       for u in members), 6),
        "total_tokens":      sum(int(u.get("total_tokens", 0)) for u in members),
        "risk_turn_count":   sum(int(u.get("risk_turn_count", 0)) for u in members),
        "reread_path_count": sum(int(u.get("reread_path_count", 0)) for u in members),
        "wall_clock_seconds": sum(int(u.get("wall_clock_seconds", 0)) for u in members),
        "tool_histogram":    dict(hist.most_common()),
        "members":           members,
    }


# --- Auto-insights digest + companion (Phase G, v1.78.0) -------------------
# The insights pass mirrors the task-breakdown contract: deterministic Python
# owns every number, an LLM writes only prose. ``--prepare-insights`` serialises
# a BOUNDED, TRUNCATED digest of the already-computed export (totals, health,
# behaviour, velocity, top cost drivers, per-request one-liners) to stdout for
# the running agent to read, plus a skeleton ``<stem>_insights.json`` the agent
# fills with prose. ``--render-insights`` validates that prose and renders the
# themed companion, recomputing the headline FACTS from the export — the prose
# is never trusted for math.

_INSIGHTS_SCHEMA_VERSION = "1"
_INSIGHTS_LENSES = ("summary", "effectiveness")
# Hard cap on per-request one-liners in the digest so the prompt stays a
# predictable size regardless of session length (bounded digest + an explicit
# "(showing N of M)" overflow note).
_INSIGHTS_DIGEST_UNIT_CAP = 40
_INSIGHTS_SNIPPET_CAP = 200
# Section-heading stubs seeded into the prepare-insights skeleton, per lens. The
# running agent overwrites the bodies; the headings are a starting frame only.
_INSIGHTS_SECTION_STUBS = {
    "summary": ("What got done", "Key decisions & patterns", "Notable moments"),
    "effectiveness": ("Where time and cost went", "Waste & redundant work",
                      "How to tune the setup"),
}


def _insights_facts(report: dict) -> dict:
    """Curated, deterministic headline numbers for the insights companion.

    Python owns every figure here — the rendered facts panel uses these, never
    the LLM prose, so the page's numbers are always authoritative. Reads only
    already-computed report fields; never re-derives token math. Health /
    behaviour fields populate at single-session scope only (multi-session
    exports have no single ``session_health``); they stay ``None`` otherwise.
    """
    totals = report.get("totals") or {}
    sessions = report.get("sessions") or []
    sess0 = sessions[0] if len(sessions) == 1 else {}
    health = sess0.get("session_health") or {}
    behavior = sess0.get("session_behavior") or {}
    velocity = report.get("velocity") or {}
    return {
        "scope":             report.get("mode") or "",
        "session_count":     len(sessions),
        "total_cost_usd":    round(float(totals.get("cost", 0.0) or 0.0), 6),
        "total_tokens":      int(totals.get("total", 0) or 0),
        "total_turns":       int(totals.get("turns", 0) or 0),
        "cache_hit_pct":     round(float(totals.get("cache_hit_pct", 0.0) or 0.0), 1),
        "cache_savings_usd": round(float(totals.get("cache_savings", 0.0) or 0.0), 6),
        "health_grade":      health.get("grade"),
        "health_score":      health.get("score"),
        "outcome":           health.get("outcome"),
        "archetype":         behavior.get("archetype"),
        "p50_cycle_s":       velocity.get("p50_cycle_s"),
        "p90_cycle_s":       velocity.get("p90_cycle_s"),
    }


def _insights_corpus_units(units: list[dict]) -> list[dict]:
    """Request units fit for the insights corpus: drops no-prompt (tool-result
    only) and ``↳`` agent-continuation units so the prose reflects real
    interactive work, not injected/continuation noise. Order preserved."""
    out: list[dict] = []
    for u in units:
        snip = (u.get("prompt_snippet") or "").strip()
        if not snip or _is_continuation_snippet(snip):
            continue
        out.append(u)
    return out


def _build_insights_digest(report: dict, lens: str = "summary",
                           focus: str = "") -> str:
    """Bounded, truncated plain-text digest of an export for the insights pass.

    Serialises only ALREADY-COMPUTED numbers (totals, session health/behaviour,
    velocity, top cost drivers, per-request one-liners) — the LLM that reads
    this writes prose, it never recomputes math. Per-request lines exclude
    no-prompt and agent-continuation units and are hard-capped at
    ``_INSIGHTS_DIGEST_UNIT_CAP`` with an explicit "(showing N of M)" note, so
    the prompt size is predictable regardless of session length.
    """
    lens = lens if lens in _INSIGHTS_LENSES else "summary"
    f = _insights_facts(report)
    sessions = report.get("sessions") or []
    sess0 = sessions[0] if len(sessions) == 1 else {}
    health = sess0.get("session_health") or {}
    behavior = sess0.get("session_behavior") or {}
    velocity = report.get("velocity") or {}
    units = report.get("request_units") or []

    lines: list[str] = []
    a = lines.append
    a("=== SESSION-METRICS INSIGHTS DIGEST ===")
    a(f"lens: {lens}   (summary = what got done & why; "
      f"effectiveness = waste & how to improve)")
    if focus.strip():
        a(f"focus (prioritise this in your prose): {focus.strip()[:300]}")
    a(f"scope: {f['scope']}   sessions: {f['session_count']}   "
      f"generated: {report.get('generated_at','')}")
    a("")
    a("-- TOTALS (authoritative; do not restate a different figure) --")
    a(f"cost ${f['total_cost_usd']:.4f}   turns {f['total_turns']:,}   "
      f"tokens {f['total_tokens']:,}")
    a(f"cache hit {f['cache_hit_pct']:.1f}%   "
      f"cache savings ${f['cache_savings_usd']:.4f}")

    if health:
        pen = health.get("penalties") or {}
        pen_str = ", ".join(f"{k} {v}" for k, v in sorted(pen.items()) if v) \
            or "none"
        a("")
        a("-- SESSION HEALTH --")
        a(f"grade {health.get('grade')}  score {health.get('score')}  "
          f"outcome {health.get('outcome')} "
          f"({health.get('outcome_confidence')} confidence)")
        sig = health.get("signals") or {}
        a(f"failures {sig.get('failure_signal_count', 0)}  "
          f"retries {sig.get('retry_count', 0)}  "
          f"edit-churn {sig.get('edit_churn_count', 0)}  "
          f"max-consecutive-failures {sig.get('consecutive_failure_max', 0)}")
        cp = sig.get("context_pressure")
        if cp is not None:
            a(f"context pressure {cp:.0%} "
              f"(peak {sig.get('peak_context_tokens', 0):,} / "
              f"window {sig.get('context_window', 0):,})")
        a(f"penalties: {pen_str}")

    if behavior:
        adopt = behavior.get("adoption") or {}
        skills = adopt.get("distinct_skills") or []
        a("")
        a("-- SESSION BEHAVIOUR --")
        a(f"archetype {behavior.get('archetype')}  "
          f"autonomy {behavior.get('autonomy_ratio')}  "
          f"termination {behavior.get('termination')}  "
          f"relationship {behavior.get('relationship')}")
        a(f"plan-mode {'yes' if adopt.get('plan_mode_used') else 'no'}  "
          f"subagents-spawned {adopt.get('subagent_spawn_count', 0)}  "
          f"skills [{', '.join(skills[:8])}]")
        tax = behavior.get("tool_taxonomy") or {}
        if tax:
            top = sorted(tax.items(), key=lambda x: (-x[1], x[0]))[:6]
            a("tool mix: " + ", ".join(f"{k} {v}" for k, v in top))

    if velocity:
        a("")
        a("-- VELOCITY --")
        a(f"per-request cycle p50 {velocity.get('p50_cycle_s', 0):.0f}s / "
          f"p90 {velocity.get('p90_cycle_s', 0):.0f}s  "
          f"(over {velocity.get('filtered_unit_count', 0)} timed requests)")
        a(f"active minutes {velocity.get('active_minutes', 0):.0f}  "
          f"${velocity.get('cost_per_active_min', 0):.4f}/min  "
          f"{int(velocity.get('tokens_per_active_min', 0)):,} tok/min")

    corpus = _insights_corpus_units(units)
    drivers = sorted(corpus, key=lambda u: (
        -float(u.get("combined_cost_usd", 0.0) or 0.0),
        str(u.get("unit_id") or "")))[:10]
    if drivers:
        a("")
        a("-- TOP COST DRIVERS (request units by cost) --")
        for u in drivers:
            snip = (u.get("prompt_snippet") or "").replace("\n", " ")
            risk = (int(u.get("risk_turn_count", 0))
                    + int(u.get("reread_path_count", 0))
                    + int(u.get("cache_break_count", 0)))
            a(f"#{u.get('anchor_index')}  ${float(u.get('combined_cost_usd', 0.0)):.4f}"
              f"  {int(u.get('turn_count', 0))}t  "
              f"risk{risk}  {snip[:120]}")

    a("")
    total_corpus = len(corpus)
    shown = corpus[:_INSIGHTS_DIGEST_UNIT_CAP]
    a(f"-- REQUESTS IN ORDER (showing {len(shown)} of {total_corpus}; "
      f"no-prompt & agent-continuation units excluded) --")
    for u in shown:
        snip = (u.get("prompt_snippet") or "").replace("\n", " ")
        a(f"#{u.get('anchor_index')}  ${float(u.get('combined_cost_usd', 0.0)):.4f}"
          f"  {int(u.get('turn_count', 0))}t  {snip[:_INSIGHTS_SNIPPET_CAP]}")
    if total_corpus > len(shown):
        a(f"... ({total_corpus - len(shown)} more requests omitted for length)")

    a("")
    a("-- WHAT TO WRITE --")
    if lens == "effectiveness":
        a("Write the effectiveness lens: where the cost/time actually went, "
          "redundant or wasted work (lean on risk/retry/churn signals above), "
          "and concrete, evidence-tied recommendations to tune CLAUDE.md / "
          "settings / workflow. Put each recommendation in `recommendations` "
          "with a one-line `evidence` tied to a number above.")
    else:
        a("Write the summary lens: what got done, the key decisions and "
          "patterns, and notable moments. Keep it factual and tied to the "
          "requests above; do not invent work that is not in the digest.")
    a("Rules: Python owns every number — quote figures from this digest "
      "verbatim, never recompute. Fill the insights JSON skeleton "
      "(headline + sections[].body, optional recommendations) and render with "
      "--render-insights.")
    return "\n".join(lines)


def _build_insights_skeleton(report: dict, lens: str = "summary",
                             focus: str = "") -> dict:
    """Renderable candidate insights JSON for ``--prepare-insights``.

    A zero-edit skeleton renders a correct companion (facts panel + a "prose
    not yet written" note) — graceful degradation, so the running agent EDITS
    rather than authors from scratch. Section bodies are left empty for the
    agent to fill; headings are lens-appropriate stubs.
    """
    lens = lens if lens in _INSIGHTS_LENSES else "summary"
    sessions = report.get("sessions") or []
    scope = (f"session_{(sessions[0].get('session_id') or '')[:8]}"
             if len(sessions) == 1 else (report.get("mode") or ""))
    return {
        "schema_version": _INSIGHTS_SCHEMA_VERSION,
        "lens":           lens,
        "scope_label":    scope,
        "focus":          focus.strip(),
        "headline":       "",
        "sections":       [{"heading": h, "body": ""}
                           for h in _INSIGHTS_SECTION_STUBS[lens]],
        "recommendations": [],
    }


def _assemble_insights(report: dict, insights: dict) -> dict:
    """Validate an LLM-authored ``insights`` object and pair it with the
    deterministic FACTS recomputed from the export.

    The prose (headline / sections / recommendations) is taken from the
    grouping file; every NUMBER comes from :func:`_insights_facts` (the export),
    never from the prose — an LLM must not own figures. Validation issues are
    surfaced as ``warnings`` rather than silently dropped.

    Returns ``{schema_version, lens, scope_label, focus, headline, sections,
    recommendations, facts, warnings}``.
    """
    warnings: list[str] = []
    gv = str(insights.get("schema_version") or "")
    if not gv:
        warnings.append(
            f"insights has no schema_version; expected "
            f"{_INSIGHTS_SCHEMA_VERSION!r} — rendering best-effort")
    elif gv != _INSIGHTS_SCHEMA_VERSION:
        warnings.append(
            f"insights schema_version {gv!r} != expected "
            f"{_INSIGHTS_SCHEMA_VERSION!r}; rendering best-effort")

    lens = insights.get("lens") or "summary"
    if lens not in _INSIGHTS_LENSES:
        warnings.append(f"unknown lens {lens!r}; treating as 'summary'")
        lens = "summary"

    headline = str(insights.get("headline") or "").strip()
    if not headline:
        warnings.append("insights has no headline")

    sections_out: list[dict] = []
    for raw in insights.get("sections") or []:
        if not isinstance(raw, dict):
            warnings.append(f"ignoring non-object section entry: {raw!r}")
            continue
        heading = str(raw.get("heading") or "").strip()
        body = str(raw.get("body") or "").strip()
        if not heading and not body:
            continue
        sections_out.append({"heading": heading, "body": body})
    if not any(s["body"] for s in sections_out):
        warnings.append("no section has a body — prose not written yet")

    recs_out: list[dict] = []
    for raw in insights.get("recommendations") or []:
        if isinstance(raw, str):
            recs_out.append({"text": raw.strip(), "evidence": ""})
        elif isinstance(raw, dict):
            text = str(raw.get("text") or "").strip()
            if text:
                recs_out.append(
                    {"text": text,
                     "evidence": str(raw.get("evidence") or "").strip()})
        else:
            warnings.append(f"ignoring non-text recommendation: {raw!r}")

    return {
        "schema_version":  _INSIGHTS_SCHEMA_VERSION,
        "lens":            lens,
        "scope_label":     str(insights.get("scope_label") or ""),
        "focus":           str(insights.get("focus") or "").strip(),
        "headline":        headline,
        "sections":        sections_out,
        "recommendations": recs_out,
        "facts":           _insights_facts(report),
        "warnings":        warnings,
    }


def _empty_subagent_row(name: str) -> dict:
    return {
        "name":             name,
        "spawn_count":      0,   # Agent/Task tool_use in main turns
        "turns_attributed": 0,   # subagent turns (only when --include-subagents)
        "input":            0,
        "output":           0,
        "cache_read":       0,
        "cache_write":      0,
        "total_tokens":     0,
        "cost_usd":         0.0,
        "pct_total_cost":   0.0,
        "cache_hit_pct":    0.0,
        "avg_tokens_per_call": 0.0,
        # v1.26.0: per-invocation fixed-cost signals. Aggregated across
        # invocations of this subagent type (one invocation = all turns
        # sharing a ``subagent_agent_id``).
        "invocation_count":         0,    # distinct subagent_agent_id values seen
        "first_turn_share_pct":     0.0,  # median(first_turn.cost / invocation total)
        "sp_amortisation_pct":      0.0,  # % of invocations whose turn ≥2 had cache_read
        "_sessions":        set(),
    }


def _finalise_subagent_rows(rows: dict, total_cost: float) -> list[dict]:
    out: list[dict] = []
    for _, row in rows.items():
        row = dict(row)
        row["session_count"] = len(row.pop("_sessions", set()) or set())
        total_input_side = (row["input"] + row["cache_read"] + row["cache_write"]) or 1
        row["cache_hit_pct"] = round(100.0 * row["cache_read"] / total_input_side, 1)
        row["pct_total_cost"] = (
            round(100.0 * row["cost_usd"] / total_cost, 2) if total_cost else 0.0
        )
        calls_for_avg = row["spawn_count"] or row["turns_attributed"] or 1
        row["avg_tokens_per_call"] = round(row["total_tokens"] / calls_for_avg, 1)
        out.append(row)
    out.sort(key=lambda r: -(r["total_tokens"] or r["spawn_count"]))
    return out


def _build_by_subagent_type(sessions: list[dict], total_cost: float) -> list[dict]:
    """Aggregate spawns + consumed tokens per subagent_type.

    Two data sources per row:
      - ``spawn_count`` from **main** turns' ``spawned_subagents`` list
        (populated when the assistant emitted an ``Agent``/``Task`` tool_use
        with ``input.subagent_type``). Always available.
      - ``input``/``output``/``cache_*``/``cost_usd`` from **subagent**
        turns (turns with ``subagent_type`` set via ``_load_session``
        tagging). Only populated when the user ran with
        ``--include-subagents``; without it the token columns are all zero.

    The row ``name`` is the resolved subagent type string. Rows for spawn
    events whose type wasn't observed among the loaded subagent files still
    appear (with zero tokens) so users see the spawn signal even when the
    subagent JSONL wasn't loaded.

    v1.58.0: dynamic-workflow agent turns (those tagged with a
    ``workflow_run_id``) are **excluded** here — they are accounted
    exclusively in the ``by_workflow`` table. The two tables therefore
    decompose the merged turn set without overlap, so a user summing
    "subagent share + workflow share" never double-counts the same agent
    work. (Headline totals are unaffected either way: each turn is still
    counted once in the merged entries.)
    """
    rows: dict[str, dict] = {}
    # v1.26.0: per-invocation grouping for fixed-cost signals. Each
    # ``subagent_agent_id`` is one invocation; we collect its turns
    # (in transcript order) so we can compute first-turn-share and
    # cache-read amortisation downstream.
    invocations: dict[str, dict] = {}
    for session in sessions:
        sid = session.get("session_id", "")
        for t in session.get("turns", []) or []:
            if t.get("is_resume_marker"):
                continue
            # v1.58.0: workflow-agent turns belong to by_workflow only.
            # Skipping the whole turn keeps the spawn-count, token, and
            # per-invocation paths all out of the subagent-type table —
            # see _turn_parser.py Workflow branch for the intent.
            if t.get("workflow_run_id"):
                continue
            # Spawn-count contribution from main turns.
            for st in (t.get("spawned_subagents") or []):
                row = rows.setdefault(st, _empty_subagent_row(st))
                row["spawn_count"] += 1
                row["_sessions"].add(sid)
            # Token contribution from subagent-tagged turns.
            stype = t.get("subagent_type") or ""
            agent_id = t.get("subagent_agent_id") or ""
            if stype:
                row = rows.setdefault(stype, _empty_subagent_row(stype))
                _accumulate_bucket(row, t)
                row["_sessions"].add(sid)
            if agent_id:
                inv = invocations.setdefault(
                    agent_id, {"type": stype, "turns": []})
                inv["turns"].append(t)
                # Belt-and-braces: a subagent turn might have empty stype
                # if tagging was incomplete; later overwrites win.
                if stype and not inv["type"]:
                    inv["type"] = stype
    # Roll per-invocation metrics up to the type-level rows.
    type_invocations: dict[str, list[dict]] = {}
    for inv in invocations.values():
        stype = inv["type"]
        if not stype:
            continue
        turns_sorted = sorted(inv["turns"], key=lambda x: x.get("index", 0))
        if not turns_sorted:
            continue
        first_cost = float(turns_sorted[0].get("cost_usd", 0.0))
        total_inv_cost = sum(float(t.get("cost_usd", 0.0)) for t in turns_sorted)
        first_share = (first_cost / total_inv_cost) if total_inv_cost > 0 else 0.0
        # SP amortisation: any turn beyond the first read from cache.
        # Single-turn invocations cannot amortise (denominator-only).
        sp_amortised = any(
            int(t.get("cache_read_tokens", 0)) > 0 for t in turns_sorted[1:]
        )
        type_invocations.setdefault(stype, []).append({
            "first_share":   first_share,
            "sp_amortised":  sp_amortised,
            "turn_count":    len(turns_sorted),
        })
    for stype, inv_list in type_invocations.items():
        row = rows.get(stype)
        if not row or not inv_list:
            continue
        shares_sorted = sorted(i["first_share"] for i in inv_list)
        n = len(shares_sorted)
        if n % 2 == 1:
            median_share = shares_sorted[n // 2]
        else:
            median_share = 0.5 * (shares_sorted[n // 2 - 1] + shares_sorted[n // 2])
        amort_count = sum(1 for i in inv_list if i["sp_amortised"])
        row["invocation_count"]     = n
        row["first_turn_share_pct"] = round(100.0 * median_share, 1)
        row["sp_amortisation_pct"]  = round(100.0 * amort_count / n, 1)
    return _finalise_subagent_rows(rows, total_cost)


def _empty_workflow_row(run_id: str) -> dict:
    return {
        "run_id":           run_id,
        "workflow_name":    run_id,   # overwritten from journal when present
        "status":           "",
        "agents":           0,        # distinct on-disk agentIds (transcripts)
        "agent_count":      0,        # journal-reported agentCount (may differ)
        "tool_calls":       0,        # journal totalToolCalls
        "turns_attributed": 0,        # workflow-tagged turns counted
        "input":            0,
        "output":           0,
        "cache_read":       0,
        "cache_write":      0,
        "total_tokens":     0,
        "cost_usd":         0.0,
        "duration_ms":      0,
        "default_model":    "",
        "models":           {},       # model → turn count, from transcripts
        "pct_total_cost":   0.0,
        "cache_hit_pct":    0.0,
        "phases":           [],       # journal phase list (display only)
        "agent_details":    [],       # journal per-agent entries (companion)
        "_sessions":        set(),
        "_agent_ids":       set(),
    }


def _build_by_workflow(sessions: list[dict], total_cost: float,
                       journals_by_session: dict) -> list[dict]:
    """Aggregate dynamic-workflow token/cost per ``runId``.

    Cost and tokens are summed from the merged workflow-agent transcripts
    (turns tagged with ``workflow_run_id`` by ``_load_session``) using the
    same per-model pricing as every other turn — so the figure is exact,
    including the cache-read-heavy component that the journal's own
    ``totalTokens`` omits. The ``wf_<runId>.json`` journals
    (``journals_by_session[session_id][run_id]``) supply only display
    metadata: workflow name, run status, phase structure, tool-call count,
    wall-clock duration, and the per-agent label/preview list used by the
    companion deep-dive. Returns ``[]`` when no workflow ran.
    """
    rows: dict[str, dict] = {}
    # Per-agent exact token/cost from transcripts, keyed (run_id, agentId).
    # Merged into the journal's per-agent entries so the companion deep-dive
    # shows real cost rather than the journal's cache-read-excluding figure.
    per_agent: dict[tuple[str, str], dict] = {}
    for session in sessions:
        sid = session.get("session_id", "")
        for t in session.get("turns", []) or []:
            if t.get("is_resume_marker"):
                continue
            run_id = t.get("workflow_run_id") or ""
            if not run_id:
                continue
            row = rows.setdefault(run_id, _empty_workflow_row(run_id))
            _accumulate_bucket(row, t)          # input/output/cache/cost/turns
            row["_sessions"].add(sid)
            aid = t.get("subagent_agent_id") or ""
            if aid:
                row["_agent_ids"].add(aid)
                pa = per_agent.setdefault((run_id, aid),
                                          {"tokens": 0, "cost": 0.0})
                pa["tokens"] += int(t.get("total_tokens", 0))
                pa["cost"]   += float(t.get("cost_usd", 0.0))
            mdl = t.get("model") or ""
            if mdl and mdl != _sm()._SYNTHETIC_MODEL:
                row["models"][mdl] = row["models"].get(mdl, 0) + 1
    # Enrich with journal metadata (name/status/phases/tool-calls/duration)
    # and graft exact per-agent transcript cost onto each agent entry.
    for run_meta in (journals_by_session or {}).values():
        for run_id, summary in (run_meta or {}).items():
            row = rows.get(run_id)
            if not row:
                # Journal present but no transcripts loaded (pruned
                # transcripts, run still in flight, or runId mismatch). Data
                # is still correct — no transcripts means no cost to report —
                # but warn so a suppressed run is discoverable, not silent.
                print(f"[warn] workflow run {run_id!r}: journal found but no "
                      f"agent transcripts loaded — run omitted from by_workflow",
                      file=sys.stderr)
                continue
            row["workflow_name"] = summary.get("workflow_name") or run_id
            row["status"]        = summary.get("status") or ""
            row["agent_count"]   = int(summary.get("agent_count") or 0)
            row["tool_calls"]    = int(summary.get("total_tool_calls") or 0)
            row["duration_ms"]   = int(summary.get("duration_ms") or 0)
            row["default_model"] = summary.get("default_model") or ""
            row["phases"]        = summary.get("phases") or []
            agents_out = []
            for a in summary.get("agents") or []:
                a = dict(a)
                pa = per_agent.get((run_id, a.get("agentId") or ""))
                a["transcript_tokens"] = int(pa["tokens"]) if pa else 0
                a["transcript_cost"]   = round(float(pa["cost"]), 6) if pa else 0.0
                agents_out.append(a)
            row["agent_details"] = agents_out
    out: list[dict] = []
    for row in rows.values():
        row = dict(row)
        row["session_count"] = len(row.pop("_sessions", set()) or set())
        row["agents"] = len(row.pop("_agent_ids", set()) or set())
        total_input_side = (row["input"] + row["cache_read"] + row["cache_write"]) or 1
        row["cache_hit_pct"] = round(100.0 * row["cache_read"] / total_input_side, 1)
        row["pct_total_cost"] = (
            round(100.0 * row["cost_usd"] / total_cost, 2) if total_cost else 0.0
        )
        out.append(row)
    out.sort(key=lambda r: -r["cost_usd"])
    return out


# ---------------------------------------------------------------------------
# v1.26.0: subagent share + within-session split + attribution coverage
# ---------------------------------------------------------------------------
#
# These helpers all derive from data the parser already records on each turn
# (``attributed_subagent_*`` fields, ``cost_usd``, ``tool_use_ids``,
# ``spawned_subagents``, ``subagent_agent_id``) plus ``subagent_attribution_summary``
# already attached to the report. No new per-turn fields, no parser changes,
# no ``_sm()._SCRIPT_VERSION`` bump.

# ---------------------------------------------------------------------------
# Evidence-pack export — sha256-pinned JSON sidecar for reproducibility.
# ---------------------------------------------------------------------------

def _write_evidence_pack(json_path,
                          provenance_extra: dict | None = None,
                          share_safe: bool = False):
    """Write reproducibility sidecars next to a session-metrics JSON export.

    Two files are emitted:
      - ``<json>.sha256``      one-line GNU coreutils format
                                ``<hex64>  <basename>``
      - ``<json>.provenance.json``  small JSON with skill version, host
                                     platform, generation timestamp,
                                     source JSON path + size.

    Returns ``(sha256_path, provenance_path)``. Sourced from cognitive-
    claude's ``cost-audit.py --evidence`` framing — lets a third party
    verify a published report wasn't massaged after the fact.
    """
    from pathlib import Path
    import datetime as _dt
    import platform as _plat
    json_path = Path(json_path)
    payload = json_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    sha_path = json_path.with_suffix(json_path.suffix + ".sha256")
    sha_path.write_text(f"{digest}  {json_path.name}\n", encoding="utf-8")
    prov = {
        "json_file":      json_path.name,
        "sha256":         digest,
        "size_bytes":     len(payload),
        "generated_at":   _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "skill_version":  sys.modules["session_metrics"]._SKILL_VERSION,
        "script_version": sys.modules["session_metrics"]._SCRIPT_VERSION,
        "platform":       _plat.platform(),
        "python_version": _plat.python_version(),
    }
    if provenance_extra:
        prov.update(provenance_extra)
    prov_path = json_path.with_suffix(json_path.suffix + ".provenance.json")
    prov_path.write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")
    if share_safe:
        sha_path.chmod(0o600)
        prov_path.chmod(0o600)
    return sha_path, prov_path


# ---------------------------------------------------------------------------
# Output dispatch
# ---------------------------------------------------------------------------

