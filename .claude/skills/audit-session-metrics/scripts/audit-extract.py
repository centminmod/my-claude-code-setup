#!/usr/bin/env python3
"""Pre-compute audit triggers and metrics from a session-metrics JSON export.

The audit-session-metrics skill calls this script once with the export path
and consumes the digest from stdout. That replaces multiple Bash exploration
roundtrips during a Haiku audit turn.

Usage:
    python3 audit-extract.py <path-to-session-metrics.json> [--mode quick|detailed]

Output: a single JSON object on stdout containing baseline metrics, fired
triggers (with suggested severity + estimated impact where computable),
top-3 expensive turns (with cross-finding correlation flags), and — in
detailed mode — pre-computed scans (file re-reads, paste-bombs, wrong-model
turns, verbose responses, weekly rollup deltas, subagent orphans).

The digest schema is consumed by the audit-session-metrics playbook's
markdown render step. Bumping the digest shape is a coordinated change
across this script, references/quick-audit.md, references/detailed-audit.md,
and the test fixtures.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from typing import Any

# Per-model input rates ($/M tokens) — used for cache_break impact and idle-gap
# rebuild cost estimates. Substring-matched (first hit wins; order matters,
# longest-most-specific first). Kept embedded rather than reading
# references/pricing.md to keep this script standalone.
#
# Default fallback is the Sonnet rate ($3/M), matching session-metrics.py's
# _DEFAULT_PRICING. Cache-break impact previously hard-coded the Opus 4.7 rate
# ($5/M) for every turn, overstating cost by 67% on Sonnet turns and 400% on
# Haiku turns.
#
# Non-Anthropic models (glm-*, deepseek/*, openai/*, qwen, kimi, minimax, …)
# are intentionally ABSENT from this table and fall through to the $3 default.
# This is DORMANT, not a mispricing: the only two consumers of this rate are
# `cache_break` impact and `idle_gap_cache_decay` (see the three call sites of
# `_input_rate_for_model`), and BOTH require prompt-cache activity (cache writes
# / breaks). Those third-party models have no prompt caching (cache columns are
# $0 in session-metrics' _PRICING), so neither finding ever fires for them and
# the $3 default is never actually multiplied against their tokens. Documented
# in tests/test_pricing.py:test_audit_extract_pricing_parity_forward (non-Anthropic
# explicitly out of scope).
# NOTE: the bare "claude-opus-4" prefix entry was removed (matches the
# removal in session-metrics.py:_PRICING done in v1.41.2). Without that entry,
# any future Opus 4 minor (e.g. claude-opus-4-2) substring-falls through to
# the bare "claude-opus" needle below at the NEW $5/M tier — conservative
# undercharge rather than the prior 3x overcharge ($15/M OLD tier). The
# `(?!\d)` boundary added to `_input_rate_for_model` in v1.45.1 ensures the
# TWO-digit minors (claude-opus-4-10..19) ALSO fall through to $5 instead of
# substring-hitting the `claude-opus-4-1` needle (which would 3x-overcharge
# them). Real
# Opus 4.0 IDs (claude-opus-4 / claude-opus-4-YYYYMMDD) are an inherent
# audit-vs-main asymmetry: main script's anchored regex prices them at $15;
# audit-extract now prices them at $5. Audit impact estimates are
# approximate by design; the under-direction is the safer drift mode.
_INPUT_RATE_PER_M_BY_MODEL: tuple[tuple[str, float], ...] = (
    ("claude-opus-4-9", 5.00),
    ("claude-opus-4-8", 5.00),
    ("claude-opus-4-7", 5.00),
    ("claude-opus-4-6", 5.00),
    ("claude-opus-4-5", 5.00),
    ("claude-opus-4-1", 15.00),
    ("claude-3-opus", 15.00),
    ("claude-haiku-4-9", 1.00),
    ("claude-haiku-4-8", 1.00),
    ("claude-haiku-4-7", 1.00),
    ("claude-haiku-4-6", 1.00),
    ("claude-haiku-4-5", 1.00),
    ("claude-3-5-haiku", 0.80),
    ("claude-fable-5", 10.00),
    ("claude-3-7-sonnet", 3.00),
    ("claude-3-5-sonnet", 3.00),
    ("claude-sonnet-4-9", 3.00),
    ("claude-sonnet-4-8", 3.00),
    ("claude-sonnet", 3.00),
    ("claude-haiku", 1.00),
    ("claude-opus", 5.00),
    # Bare-major future keys (claude-opus-5 / claude-sonnet-5 / claude-haiku-5)
    # are intentionally NOT listed: the bare family needles above already resolve
    # them to the correct tier, and a major-only needle here would trip the
    # `test_audit_extract_no_undocumented_loose_prefixes` drift guard.
    #
    # DATE-EFFECTIVE PRICING NOT MODELLED HERE (v1.84.0): the main script prices
    # claude-sonnet-5 at its introductory $2/M through 2026-08-31 and $3/M from
    # 2026-09-01 (see session-metrics.py:_PRICING_SCHEDULES / _pricing_for_at).
    # This standalone table is time-blind and always uses the standard $3/M, so
    # cache-break / idle-gap ESTIMATES for intro-window Sonnet 5 turns can run up
    # to ~50% high. This is the same "approximate by design" under-direction the
    # Opus 4.0 asymmetry note above already accepts; the main report's per-turn
    # cost figures remain exact.
)
_DEFAULT_INPUT_RATE_PER_M = 3.00


def _input_rate_for_model(model: str | None) -> float:
    """Look up $/M input rate for a model id. Substring-matched against the
    table above, falling back to Sonnet rate for unknown / missing model.
    Synthetic markers like ``<synthetic>`` also fall through to the default.

    The ``(?!\\d)`` boundary (v1.45.1) stops a needle from matching when it is
    immediately followed by another digit, so the ``claude-opus-4-1`` ($15 OLD
    tier) needle no longer substring-swallows the two-digit minors
    ``claude-opus-4-10``..``-19`` (NEW $5 tier) and over-charge them 3x. It
    mirrors the ``(?!\\d)`` negative-lookahead session-metrics.py uses in its
    ``_PRICING_PATTERNS``. Real Anthropic ids always carry a non-digit (`-`,
    `[`, or end-of-string) after a needle, so the bare family needles
    (``claude-opus`` etc.) keep matching their versioned ids unchanged."""
    if not model:
        return _DEFAULT_INPUT_RATE_PER_M
    for needle, rate in _INPUT_RATE_PER_M_BY_MODEL:
        if re.search(re.escape(needle) + r"(?!\d)", model):
            return rate
    return _DEFAULT_INPUT_RATE_PER_M

# Cache TTL boundary in seconds. A gap longer than this expires the 5-minute
# ephemeral cache; the next turn pays full uncached input on whatever it
# would have hit. Independent of the HTML --idle-gap-minutes UI threshold.
CACHE_TTL_5M_SECONDS = 300

DIGEST_SCHEMA_VERSION = "1.3"

# Session archetype enum — emitted as a top-level digest field. The classifier
# is intentionally biased toward `unknown` at low confidence (lesson learned
# from v1.29.0's `"other"`-row padding antipattern). Severity overrides
# conditional on archetype come in v1.31.0; v1.30.0 ships *detect-only*.
SESSION_ARCHETYPES = (
    "agent_workflow",    # subagent_share_pct >= 30
    "short_test",        # turns <= 5
    "long_debug",        # turns > 30 AND (cache_breaks OR cache_hit_pct < 70)
    "code_writing",      # turns > 5 AND Edit+Write >= 25% of tool calls
    "exploratory_chat",  # turns > 5 AND tool_call_total / turns < 1.0
    "unknown",           # default — no clear pattern
)

# Metrics that are only meaningful within a single session. Suppressed when
# scope is "project" or "instance" (where turns span many sessions or are
# absent entirely, making intra-session gap detection and per-session turn
# counts meaningless).
SESSION_ONLY_METRICS: frozenset[str] = frozenset({
    "idle_gap_cache_decay",    # intra-session idle gap detection
    "session_warmup_overhead", # first-turn warmup relative to session length
})


def session_filename_parts(path: str) -> tuple[str, str]:
    """Return (id8, ts_str) parsed from a session-metrics export filename.

    Recognises:
      session_<id8>_<YYYYMMDD>T<HHMMSS>Z.json   (current)
      session_<id8>_<YYYYMMDD_HHMMSS>.json      (legacy)
    Falls back to splitting the stem on '_'."""
    name = os.path.basename(path)
    m = re.match(r"^session_([0-9a-f]{8})_(\d{8}T\d{6}Z)\.json$", name)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^session_([0-9a-f]{8})_(\d{8}_\d{6})\.json$", name)
    if m:
        return m.group(1), m.group(2)
    stem = os.path.splitext(name)[0]
    parts = stem.split("_")
    if len(parts) >= 3:
        return parts[1], "_".join(parts[2:])
    return "unknown", "unknown"


def project_filename_parts(path: str) -> tuple[str, str]:
    """Return ("project", ts_str) from project_<YYYYMMDD>T<HHMMSS>Z.json."""
    name = os.path.basename(path)
    m = re.match(r"^project_(\d{8}T\d{6}Z)\.json$", name)
    if m:
        return "project", m.group(1)
    return "project", "unknown"


def instance_filename_parts(path: str) -> tuple[str, str]:
    """Return ("instance", ts_str) from instance/<datedir>/index.json.

    The parent directory is named YYYYMMDDTHHMMSSZ (session-metrics
    v1.67.0+) or YYYY-MM-DD-HHMMSS (earlier); both remain on disk."""
    parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
    m = re.match(r"^(\d{4}-\d{2}-\d{2}-\d{6}|\d{8}T\d{6}Z)$", parent)
    if m:
        return "instance", m.group(1)
    return "instance", "unknown"


def detect_scope(data: dict, path: str) -> str:
    """Return scope string: "session" | "project" | "instance".

    Reads data["mode"] first (authoritative); falls back to filename pattern."""
    mode = data.get("mode", "")
    if mode in ("session", "project", "instance"):
        return mode
    name = os.path.basename(path)
    if name.startswith("project_"):
        return "project"
    if name == "index.json":
        return "instance"
    return "session"


def flatten_turns(data: dict) -> list[dict]:
    return [t for s in data.get("sessions", []) for t in s.get("turns", [])]


def _first_user_turn(data: dict) -> dict | None:
    """Return the first non-synthetic, non-resume-marker turn across all
    sessions, or None if no such turn exists. Used to anchor the
    first_turn_cost_share metric so resumed/synthetic-fronted exports do
    not mis-attribute the warmup cost."""
    for s in data.get("sessions", []):
        for t in s.get("turns", []):
            if t.get("is_resume_marker"):
                continue
            model = (t.get("model") or "")
            if model.startswith("<synthetic>"):
                continue
            return t
    return None


def _models_with_shares(data: dict) -> dict[str, dict]:
    """Normalise the export's ``models`` field and attach turn/cost shares.

    session-metrics v1.34.0+ emits ``{name: {turns, cost_usd}}``. Older exports
    used ``{name: int}`` (turn count only). Accept both. Returned shape:
    ``{name: {turns, turns_pct, cost_usd, cost_pct}}`` so the audit playbook
    can render either share without extra arithmetic. ``cost_pct`` is null
    when the export pre-dates v1.34.0 (no per-model cost), so the playbook
    can fall back to ``turns_pct``.
    """
    raw = data.get("models") or {}
    if not raw:
        return {}
    parsed: dict[str, dict] = {}
    has_cost = False
    for name, val in raw.items():
        if isinstance(val, dict):
            t = int(val.get("turns", 0) or 0)
            c = float(val.get("cost_usd", 0.0) or 0.0)
            if c > 0:
                has_cost = True
            parsed[name] = {"turns": t, "cost_usd": c}
        else:
            parsed[name] = {"turns": int(val or 0), "cost_usd": 0.0}
    total_turns = sum(m["turns"] for m in parsed.values()) or 1
    total_cost  = sum(m["cost_usd"] for m in parsed.values())
    out: dict[str, dict] = {}
    for name, m in parsed.items():
        cost_pct: float | None
        if has_cost and total_cost > 0:
            cost_pct = round(100.0 * m["cost_usd"] / total_cost, 1)
        else:
            cost_pct = None
        out[name] = {
            "turns":     m["turns"],
            "turns_pct": round(100.0 * m["turns"] / total_turns, 1),
            "cost_usd":  round(m["cost_usd"], 4),
            "cost_pct":  cost_pct,
        }
    return out


def compute_baseline(data: dict) -> dict:
    totals = data.get("totals", {})
    output = totals.get("output", 0)
    uncached_input = totals.get("total_input", 0) - totals.get("cache_read", 0)
    ratio = int(round(uncached_input / output)) if output else 0
    cost = totals.get("cost", 0) or 0
    first = _first_user_turn(data)
    first_cost = (first.get("cost_usd", 0) or 0) if first else 0
    first_share_pct = round(_safe_div_pct(first_cost, cost), 1) if cost > 0 else 0.0
    return {
        "total_cost_usd": round(totals.get("cost", 0), 2),
        "turns": totals.get("turns", 0),
        "models": _models_with_shares(data),
        "input_output_ratio": ratio,
        "cache_hit_pct": round(totals.get("cache_hit_pct", 0), 1),
        "cache_savings_usd": round(totals.get("cache_savings", 0), 2),
        "no_cache_cost_usd": round(totals.get("no_cache_cost", 0), 2),
        "first_turn_cost_usd": round(first_cost, 4),
        "first_turn_cost_share_pct": first_share_pct,
    }


def _safe_div_pct(num: float, denom: float) -> float:
    return (num / denom) * 100 if denom else 0.0


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _detect_idle_gap_cache_decay(turns: list[dict]) -> list[dict]:
    """Find turns where a >5m gap from the prior turn was followed by a
    cache rebuild (cache_creation_input_tokens > 50% of billable input).
    Returns rebuild events sorted by descending cost."""
    events: list[dict] = []
    prev_ts: datetime | None = None
    for t in turns:
        if t.get("is_resume_marker"):
            prev_ts = None
            continue
        cur_ts = _parse_iso(t.get("timestamp", ""))
        if prev_ts and cur_ts:
            gap_s = (cur_ts - prev_ts).total_seconds()
            if gap_s >= CACHE_TTL_5M_SECONDS:
                cw = t.get("cache_write_tokens", 0) or 0
                ip = t.get("input_tokens", 0) or 0
                cr = t.get("cache_read_tokens", 0) or 0
                billable = cw + ip + cr
                if billable > 0 and (cw / billable) > 0.5:
                    rate = _input_rate_for_model(t.get("model"))
                    rebuild_cost = round(cw * rate / 1_000_000, 4)
                    events.append({
                        "turn_index": t.get("index"),
                        "gap_minutes": round(gap_s / 60, 1),
                        "cache_write_tokens": cw,
                        "rebuild_cost_usd": rebuild_cost,
                    })
        if cur_ts:
            prev_ts = cur_ts
    events.sort(key=lambda e: e["rebuild_cost_usd"], reverse=True)
    return events


def evaluate_triggers(data: dict, turns: list[dict]) -> list[dict]:
    """Evaluate every metric in the audit enum. Return only fired triggers
    with evidence + suggested severity (downgrade_reason populated when
    the data is milder than the trigger threshold suggests) + estimated
    impact in USD where it can be computed honestly."""
    fired: list[dict] = []
    totals = data.get("totals", {})
    cache_breaks = data.get("cache_breaks", []) or []
    cost = totals.get("cost", 0) or 0.0

    # cache_break — any cache_breaks entry
    if cache_breaks:
        n = len(cache_breaks)
        total_uncached = sum(cb.get("uncached", 0) for cb in cache_breaks)
        impact_raw = 0.0
        for cb in cache_breaks:
            cb_rate = _input_rate_for_model(cb.get("model"))
            impact_raw += (cb.get("uncached", 0) or 0) * cb_rate / 1_000_000
        impact = round(impact_raw, 2)
        break_pct = (n / max(totals.get("turns", 1), 1)) * 100
        suggested = "medium"
        downgrade_reason = None
        if break_pct < 2 and n <= 2:
            suggested = "low"
            downgrade_reason = (
                f"{n} break(s) in {totals.get('turns', 0)} turns ({break_pct:.1f}%) — "
                "below typical concern threshold"
            )
        models_in_breaks = sorted({
            cb.get("model") for cb in cache_breaks if cb.get("model")
        })
        if len(models_in_breaks) == 1:
            m = models_in_breaks[0]
            impact_basis = (
                f"{total_uncached:,} uncached tokens × "
                f"${_input_rate_for_model(m):.2f}/M ({m} input rate)"
            )
        elif models_in_breaks:
            impact_basis = (
                f"{total_uncached:,} uncached tokens × per-break input rate "
                f"(mixed models: {', '.join(models_in_breaks)})"
            )
        else:
            impact_basis = (
                f"{total_uncached:,} uncached tokens × "
                f"${_DEFAULT_INPUT_RATE_PER_M:.2f}/M (default fallback rate)"
            )
        fired.append({
            "metric": "cache_break",
            "default_severity": "medium",
            "suggested_severity": suggested,
            "downgrade_reason": downgrade_reason,
            "evidence": {
                "turn_index": cache_breaks[0].get("turn_index"),
                "uncached_tokens": cache_breaks[0].get("uncached"),
                "count": n,
            },
            "estimated_impact_usd": impact,
            "impact_basis": impact_basis,
        })

    # top_turn_share — top single turn > 30% of cost
    if turns and cost > 0:
        top = max(turns, key=lambda t: t.get("cost_usd", 0) or 0)
        top_cost = top.get("cost_usd", 0) or 0
        top_pct = _safe_div_pct(top_cost, cost)
        if top_pct > 30:
            fired.append({
                "metric": "top_turn_share",
                "default_severity": "high",
                "suggested_severity": "high",
                "downgrade_reason": None,
                "evidence": {
                    "turn_index": top.get("index"),
                    "cost_usd": round(top_cost, 4),
                    "pct_of_total": round(top_pct, 1),
                    "slash_command": top.get("slash_command") or None,
                    "prompt_excerpt": (top.get("prompt_text") or "")[:80] or None,
                },
                "estimated_impact_usd": None,
                "impact_basis": "n/a — already-realised cost, not a recoverable saving",
            })

    # input_output_ratio_uncached — ratio > 50:1 AND cache hit < 60%
    output = totals.get("output", 0)
    uncached_input = totals.get("total_input", 0) - totals.get("cache_read", 0)
    ratio = (uncached_input / output) if output else 0
    cache_hit = totals.get("cache_hit_pct", 0) or 0
    if ratio > 50 and cache_hit < 60:
        fired.append({
            "metric": "input_output_ratio_uncached",
            "default_severity": "high",
            "suggested_severity": "high",
            "downgrade_reason": None,
            "evidence": {
                "ratio": int(round(ratio)),
                "cache_hit_pct": round(cache_hit, 1),
                "total_input": totals.get("total_input", 0),
                "output": output,
            },
            "estimated_impact_usd": None,
            "impact_basis": (
                "savings depend on whether the bloat is reusable across turns; "
                "skill cannot estimate without re-running with prompt caching applied"
            ),
        })

    # subagent_share — subagent_share_stats.share_pct > 50
    sub = data.get("subagent_share_stats", {}) or {}
    sub_share = sub.get("share_pct", 0) or 0
    if sub_share > 50:
        fired.append({
            "metric": "subagent_share",
            "default_severity": "medium",
            "suggested_severity": "medium",
            "downgrade_reason": None,
            "evidence": {
                "share_pct": round(sub_share, 1),
                "total_cost_usd": round(sub.get("total_cost", 0), 2),
                "attributed_cost_usd": round(sub.get("attributed_cost", 0), 2),
            },
            "estimated_impact_usd": round(sub.get("attributed_cost", 0), 2),
            "impact_basis": "subagent_share_stats.attributed_cost (already realised)",
        })

    # cache_ttl_1h_unused — extra_1h_cost > 0 AND cache_read < 50% of cache_write_1h
    extra_1h = totals.get("extra_1h_cost", 0) or 0
    cache_write_1h = totals.get("cache_write_1h", 0) or 0
    cache_read = totals.get("cache_read", 0) or 0
    if extra_1h > 0 and cache_write_1h > 0 and cache_read < (0.5 * cache_write_1h):
        fired.append({
            "metric": "cache_ttl_1h_unused",
            "default_severity": "medium",
            "suggested_severity": "medium",
            "downgrade_reason": None,
            "evidence": {
                "extra_1h_cost_usd": round(extra_1h, 2),
                "cache_write_1h": cache_write_1h,
                "cache_read": cache_read,
            },
            "estimated_impact_usd": round(extra_1h, 2),
            "impact_basis": "totals.extra_1h_cost (1h-tier surcharge over 5m baseline)",
        })

    # session_warmup_overhead — first turn > 20% of cost. Length-agnostic
    # since v1.35.0 (was previously gated on len(turns) <= 15, which silenced
    # mid-length sessions where the first turn still dominated). For long
    # sessions where the first-turn share is notable but not dominant, the
    # severity downgrades to low — the absolute warmup cost is the same but
    # the user has more turns to amortise it across.
    if turns and cost > 0:
        first = turns[0]
        first_cost = first.get("cost_usd", 0) or 0
        first_pct = _safe_div_pct(first_cost, cost)
        if first_pct > 20:
            n_turns = len(turns)
            suggested = "medium"
            downgrade_reason: str | None = None
            if n_turns > 30 and first_pct < 30:
                suggested = "low"
                downgrade_reason = (
                    f"long session ({n_turns} turns) — first-turn share "
                    f"is high ({round(first_pct, 1)}%) but warmup is "
                    "small relative to overall work; informational only"
                )
            fired.append({
                "metric": "session_warmup_overhead",
                "default_severity": "medium",
                "suggested_severity": suggested,
                "downgrade_reason": downgrade_reason,
                "evidence": {
                    "first_turn_cost_usd": round(first_cost, 2),
                    "total_cost_usd": round(cost, 2),
                    "pct_of_total": round(first_pct, 1),
                    "total_turns": n_turns,
                },
                "estimated_impact_usd": None,
                "impact_basis": "n/a — first-turn warmup share, no direct savings figure",
            })

    # tool_result_bloat — turn with cache_write > 50K right after Bash/Read/WebFetch
    bloat: list[dict] = []
    for i in range(len(turns) - 1):
        prior = turns[i]
        nxt = turns[i + 1]
        prior_tools = prior.get("tool_use_names", []) or []
        match = next((t for t in ("Bash", "Read", "WebFetch") if t in prior_tools), None)
        cw = nxt.get("cache_write_tokens", 0) or 0
        if match and cw > 50_000:
            bloat.append({
                "turn_index": nxt.get("index"),
                "prior_turn_index": prior.get("index"),
                "prior_tool": match,
                "cache_write_tokens": cw,
            })
    if bloat:
        bloat.sort(key=lambda b: b["cache_write_tokens"], reverse=True)
        fired.append({
            "metric": "tool_result_bloat",
            "default_severity": "medium",
            "suggested_severity": "medium",
            "downgrade_reason": None,
            "evidence": {
                "turn_index": bloat[0]["turn_index"],
                "prior_turn_index": bloat[0]["prior_turn_index"],
                "prior_tool": bloat[0]["prior_tool"],
                "cache_write_tokens": bloat[0]["cache_write_tokens"],
                "examples": bloat[:3],
            },
            "estimated_impact_usd": None,
            "impact_basis": "savings depend on cache reuse across subsequent turns",
        })

    # heavy_reader_tools — Read or WebFetch in tool_names_top3
    top3 = totals.get("tool_names_top3", []) or []
    if any(t in top3 for t in ("Read", "WebFetch")):
        fired.append({
            "metric": "heavy_reader_tools",
            "default_severity": "low",
            "suggested_severity": "low",
            "downgrade_reason": None,
            "evidence": {
                "tool_names_top3": top3,
                "tool_call_total": totals.get("tool_call_total", 0),
            },
            "estimated_impact_usd": None,
            "impact_basis": "n/a — informational",
        })

    # cache_savings_low — cache_savings < 10% of cost
    cache_savings = totals.get("cache_savings", 0) or 0
    cache_save_pct = _safe_div_pct(cache_savings, cost)
    if cost > 0 and cache_save_pct < 10:
        fired.append({
            "metric": "cache_savings_low",
            "default_severity": "low",
            "suggested_severity": "low",
            "downgrade_reason": None,
            "evidence": {
                "cache_savings_usd": round(cache_savings, 2),
                "cost_usd": round(cost, 2),
                "pct": round(cache_save_pct, 1),
            },
            "estimated_impact_usd": None,
            "impact_basis": "potential savings depend on user's prompt-reuse pattern",
        })

    # thinking_engagement_high — thinking_turn_pct > 30
    thinking_pct = totals.get("thinking_turn_pct", 0) or 0
    if thinking_pct > 30:
        fired.append({
            "metric": "thinking_engagement_high",
            "default_severity": "low",
            "suggested_severity": "low",
            "downgrade_reason": None,
            "evidence": {
                "thinking_turn_pct": round(thinking_pct, 1),
                "thinking_turn_count": totals.get("thinking_turn_count", 0),
                "total_turns": totals.get("turns", 0),
            },
            "estimated_impact_usd": None,
            "impact_basis": "thinking tokens billed at output rate; savings depend on user's tolerance for shallower reasoning",
        })

    # truncated_outputs — any turn with stop_reason="max_tokens"
    truncated = [t for t in turns if t.get("stop_reason") == "max_tokens"]
    if truncated:
        fired.append({
            "metric": "truncated_outputs",
            "default_severity": "low",
            "suggested_severity": "low",
            "downgrade_reason": None,
            "evidence": {
                "truncated_count": len(truncated),
                "turn_indices": [t.get("index") for t in truncated[:5]],
            },
            "estimated_impact_usd": None,
            "impact_basis": "n/a — quality issue, not a cost issue",
        })

    # idle_gap_cache_decay — long idle gap (>5m, cache TTL boundary) followed
    # by a cache rebuild. Aggregates the top-3 most-expensive rebuilds into
    # one finding; severity scales by total rebuild cost.
    decays = _detect_idle_gap_cache_decay(turns)
    if decays:
        total_rebuild_cost = round(sum(d["rebuild_cost_usd"] for d in decays), 2)
        top = decays[0]
        if total_rebuild_cost >= 1.0:
            severity = "high"
        elif total_rebuild_cost >= 0.30:
            severity = "medium"
        else:
            severity = "low"
        fired.append({
            "metric": "idle_gap_cache_decay",
            "default_severity": "medium",
            "suggested_severity": severity,
            "downgrade_reason": None,
            "evidence": {
                "events": len(decays),
                "total_rebuild_cost_usd": total_rebuild_cost,
                "worst_turn_index": top["turn_index"],
                "worst_gap_minutes": top["gap_minutes"],
                "worst_rebuild_cost_usd": top["rebuild_cost_usd"],
                "examples": decays[:3],
            },
            "estimated_impact_usd": total_rebuild_cost,
            "impact_basis": (
                "sum(cache_creation_tokens after >5m gap) × $5/M (Opus input rate); "
                "5m is the ephemeral cache TTL boundary, independent of the HTML "
                "--idle-gap-minutes UI threshold"
            ),
        })

    # advisor_share — advisor_cost_usd > 5% of cost
    advisor_cost = totals.get("advisor_cost_usd", 0) or 0
    advisor_pct = _safe_div_pct(advisor_cost, cost)
    if totals.get("advisor_call_count", 0) > 0 and advisor_pct >= 5:
        # Resolve the model from the first advisor turn
        advisor_model = None
        for t in turns:
            if (t.get("advisor_calls") or 0) > 0:
                advisor_model = t.get("advisor_model")
                break
        fired.append({
            "metric": "advisor_share",
            "default_severity": "low",
            "suggested_severity": "low",
            "downgrade_reason": None,
            "evidence": {
                "advisor_call_count": totals.get("advisor_call_count", 0),
                "advisor_cost_usd": round(advisor_cost, 2),
                "pct_of_total": round(advisor_pct, 1),
                "advisor_model": advisor_model,
            },
            "estimated_impact_usd": round(advisor_cost, 2),
            "impact_basis": "totals.advisor_cost_usd (already realised)",
        })

    return fired


def evaluate_positive_triggers(data: dict) -> list[dict]:
    """Evaluate positive (celebratory) triggers. These are first-class
    structural findings that prevent Haiku from padding the audit with
    'other'-row filler when no waste pattern fires. Two triggers ship in
    schema 1.1: cache_savings_high and cache_health_excellent."""
    fired: list[dict] = []
    totals = data.get("totals", {})
    cost = totals.get("cost") or 0.0
    cache_savings = totals.get("cache_savings") or 0
    cache_hit = totals.get("cache_hit_pct") or 0
    cache_breaks = data.get("cache_breaks", []) or []

    # cache_savings_high — savings > 3× cost OR > $5 absolute
    if cost > 0 and (cache_savings > 3 * cost or cache_savings > 5):
        ratio = round(cache_savings / cost, 1) if cost else None
        fired.append({
            "metric": "cache_savings_high",
            "default_severity": "positive",
            "suggested_severity": "positive",
            "evidence": {
                "cache_savings_usd": round(cache_savings, 2),
                "cost_usd": round(cost, 2),
                "ratio_savings_to_cost": ratio,
            },
            "estimated_savings_usd": round(cache_savings, 2),
            "impact_basis": "totals.cache_savings (already realised)",
        })

    # cache_health_excellent — hit_ratio > 90% AND no cache_break events
    if cache_hit > 90 and not cache_breaks:
        fired.append({
            "metric": "cache_health_excellent",
            "default_severity": "positive",
            "suggested_severity": "positive",
            "evidence": {
                "cache_hit_pct": round(cache_hit, 1),
                "cache_break_count": 0,
            },
            "estimated_savings_usd": None,
            "impact_basis": "n/a — informational; hit ratio >90% with zero cache breaks indicates well-cached prompts",
        })

    return fired


def _aggregate_tool_counts(turns: list[dict]) -> Counter[str]:
    """Aggregate per-tool invocation counts across all turns. Used by the
    archetype classifier to compute Edit/Write share and Read share."""
    counts: Counter[str] = Counter()
    for t in turns:
        for d in t.get("tool_use_detail", []) or []:
            name = d.get("name")
            if name:
                counts[name] += 1
    return counts


def classify_session_archetype(data: dict, turns: list[dict]) -> tuple[str, dict]:
    """Detect-only classifier (v1.30.0). Returns (archetype, signals).

    Priority order (first match wins):
      1. agent_workflow   — subagent_share_pct >= 30
      2. short_test       — 0 < turns <= 5
      3. long_debug       — turns > 30 AND (cache_break_pct > 2% OR cache_hit_pct < 70).
                            The 2% threshold mirrors the cache_break trigger's
                            downgrade rule — a single break in 200 turns is
                            below typical concern, so it should not pin the
                            session as "debug".
      4. code_writing     — turns > 5 AND (Edit + Write) >= 25% of tool calls
      5. exploratory_chat — turns > 5 AND tool_call_total / turns < 1.0
      6. unknown          — default; no clear pattern (do NOT force-label)

    The classifier is intentionally biased toward `unknown` at low confidence
    — same lesson as v1.29.0's forbidden `"other"` enum: forcing labels to
    appear thorough is the antipattern. Severity overrides conditional on
    archetype come in v1.31.0; v1.30.0 is detect-only.

    Signals are emitted alongside the label so future overrides + debugging
    can see what the classifier saw.
    """
    totals = data.get("totals", {}) or {}
    sub = data.get("subagent_share_stats", {}) or {}
    cache_breaks = data.get("cache_breaks", []) or []

    n_turns = totals.get("turns", 0) or 0
    sub_share = sub.get("share_pct", 0) or 0
    cache_hit = totals.get("cache_hit_pct", 0) or 0
    thinking_pct = totals.get("thinking_turn_pct", 0) or 0
    tool_call_total = totals.get("tool_call_total", 0) or 0

    tool_counts = _aggregate_tool_counts(turns)
    edit_write = tool_counts.get("Edit", 0) + tool_counts.get("Write", 0)
    read_count = tool_counts.get("Read", 0)
    bash_count = tool_counts.get("Bash", 0)
    edit_write_pct = (edit_write / tool_call_total * 100) if tool_call_total else 0.0
    read_pct = (read_count / tool_call_total * 100) if tool_call_total else 0.0
    bash_pct = (bash_count / tool_call_total * 100) if tool_call_total else 0.0
    tools_per_turn = (tool_call_total / n_turns) if n_turns else 0.0

    signals = {
        "turns": n_turns,
        "subagent_share_pct": round(sub_share, 1),
        "cache_hit_pct": round(cache_hit, 1),
        "cache_break_count": len(cache_breaks),
        "thinking_turn_pct": round(thinking_pct, 1),
        "tool_call_total": tool_call_total,
        "edit_write_pct_of_tools": round(edit_write_pct, 1),
        "read_pct_of_tools": round(read_pct, 1),
        "bash_pct_of_tools": round(bash_pct, 1),
        "tools_per_turn": round(tools_per_turn, 2),
    }

    # Priority chain — first match wins. Document the order in the docstring
    # rather than rely on Haiku to reverse-engineer it.
    cache_break_pct = (len(cache_breaks) / n_turns * 100) if n_turns else 0.0
    signals["cache_break_pct"] = round(cache_break_pct, 2)

    if sub_share >= 30:
        return "agent_workflow", signals
    if 0 < n_turns <= 5:
        return "short_test", signals
    if n_turns > 30 and (cache_break_pct > 2 or cache_hit < 70):
        return "long_debug", signals
    if n_turns > 5 and edit_write_pct >= 25:
        return "code_writing", signals
    if n_turns > 5 and tool_call_total > 0 and tools_per_turn < 1.0:
        return "exploratory_chat", signals
    return "unknown", signals


def top_expensive_turns(turns: list[dict], cache_breaks: list[dict]) -> list[dict]:
    """Return the 3 most expensive turns with hypothesis + cross-finding flags."""
    cb_indices = {cb.get("turn_index") for cb in cache_breaks}
    top = sorted(turns, key=lambda t: t.get("cost_usd", 0) or 0, reverse=True)[:3]
    out = []
    for t in top:
        idx = t.get("index")
        cost = t.get("cost_usd", 0) or 0
        slash = t.get("slash_command") or ""
        prompt = t.get("prompt_text") or ""
        if slash:
            label = slash[:80]
        elif prompt:
            label = prompt[:80].replace("\n", " ")
        else:
            label = "(no prompt text — tool-result follow-up)"

        cw = t.get("cache_write_tokens", 0) or 0
        cr = t.get("cache_read_tokens", 0) or 0
        out_tok = t.get("output_tokens", 0) or 0
        attr_sub = t.get("attributed_subagent_cost", 0) or 0
        tool_names = t.get("tool_use_names", []) or []
        model = (t.get("model") or "").lower()

        if "Read" in tool_names and cw > 50_000:
            hypothesis = f"large file Read baked into cache ({cw // 1000}K cw)"
        elif len(prompt) > 5000:
            hypothesis = f"paste-bomb prompt (~{len(prompt) // 1024} KB)"
        elif "opus" in model and 0 < cost < 0.05:
            hypothesis = "Opus on a trivial-looking task"
        elif attr_sub > cost > 0:
            hypothesis = "expensive subagent spawned from a small prompt"
        elif cw > max(cr, 100_000):
            hypothesis = f"cache-write heavy ({cw // 1000}K cw)"
        elif cr > 500_000 and cr > out_tok * 100:
            hypothesis = f"cache-read heavy ({cr // 1000}K cr)"
        else:
            hypothesis = "output-heavy"

        out.append({
            "turn_index": idx,
            "cost_usd": round(cost, 4),
            "label": label,
            "hypothesis": hypothesis,
            "is_cache_break": idx in cb_indices,
            "drivers": {
                "input_tokens": t.get("input_tokens", 0) or 0,
                "output_tokens": out_tok,
                "cache_read_tokens": cr,
                "cache_write_tokens": cw,
                "attributed_subagent_cost_usd": round(attr_sub, 4) if attr_sub else 0,
            },
        })
    return out


def detailed_candidates(data: dict, turns: list[dict]) -> dict:
    """Pre-compute scans that detailed mode needs but quick mode skips."""
    # File re-reads (>2 reads of same path).
    # The session-metrics export schema stores the path as `input_preview`
    # (a string), not a structured `input.file_path` dict — for Read/Edit/Write
    # tools, _summarise_tool_input emits the raw path. Reading `input.file_path`
    # silently always returned None, so file_re_reads was always [].
    read_counts: Counter[str] = Counter()
    read_indices: dict[str, list[int]] = {}
    for t in turns:
        for d in t.get("tool_use_detail", []) or []:
            if d.get("name") == "Read":
                fp = d.get("input_preview")
                if isinstance(fp, str) and fp:
                    read_counts[fp] += 1
                    read_indices.setdefault(fp, []).append(t.get("index"))
    re_reads = sorted(
        ({"file_path": p, "read_count": c, "turn_indices": read_indices[p][:5]}
         for p, c in read_counts.items() if c > 2),
        key=lambda r: r["read_count"], reverse=True,
    )

    # Paste bombs: prompt_text > 5000 chars
    paste_bombs = []
    for t in turns:
        pt = t.get("prompt_text") or ""
        if len(pt) > 5000:
            paste_bombs.append({
                "turn_index": t.get("index"),
                "chars": len(pt),
                "excerpt": pt[:80].replace("\n", " "),
            })

    # Wrong-model turns: Opus on trivial work
    wrong_model = []
    for t in turns:
        model = (t.get("model") or "").lower()
        c = t.get("cost_usd", 0) or 0
        if "opus" in model and 0 < c < 0.05:
            wrong_model.append({
                "turn_index": t.get("index"),
                "cost_usd": round(c, 4),
                "prompt_excerpt": (t.get("prompt_text") or "")[:80].replace("\n", " "),
            })

    # Subagent dominant parents
    sub_dominant = []
    for t in turns:
        parent = t.get("cost_usd", 0) or 0
        sub = t.get("attributed_subagent_cost", 0) or 0
        if parent > 0 and sub > 5 * parent:
            sub_dominant.append({
                "turn_index": t.get("index"),
                "parent_cost_usd": round(parent, 4),
                "subagent_cost_usd": round(sub, 2),
                "ratio": round(sub / parent, 1),
            })

    # Verbose response: output_tokens / (input_tokens + cache_read_tokens) > 5
    # Use total billable input as denominator so cache-heavy sessions don't
    # inflate the ratio artificially (uncached `input_tokens` alone is
    # misleading once cache hit > 50%).
    verbose_count = 0
    sampled = 0
    samples = []
    for t in turns:
        ip = (t.get("input_tokens", 0) or 0) + (t.get("cache_read_tokens", 0) or 0)
        op = t.get("output_tokens", 0) or 0
        if ip > 0:
            sampled += 1
            ratio = op / ip
            if ratio > 5:
                verbose_count += 1
                if len(samples) < 3:
                    samples.append({"turn_index": t.get("index"), "ratio": round(ratio, 2)})
    verbose_pct = round(verbose_count / sampled * 100, 1) if sampled >= 10 else None

    # Weekly rollup deltas — only meaningful with two weeks of data.
    weekly = data.get("weekly_rollup") or {}
    weekly_summary = None
    if weekly.get("has_data"):
        trail = weekly.get("trailing_7d", {}) or {}
        prior = weekly.get("prior_7d", {}) or {}
        prior_cost = prior.get("cost", 0) or 0
        trail_cost = trail.get("cost", 0) or 0
        # Suppress entirely when prior_7d has no usage — first-week-of-data
        # case where any "delta" is meaningless.
        if prior_cost > 0:
            cost_delta_pct = round((trail_cost - prior_cost) / prior_cost * 100, 1)
            cache_delta = round(trail.get("cache_hit_pct", 0) - prior.get("cache_hit_pct", 0), 1)
            weekly_summary = {
                "trailing_7d_cost_usd": round(trail_cost, 2),
                "prior_7d_cost_usd": round(prior_cost, 2),
                "cost_delta_pct": cost_delta_pct,
                "trailing_7d_cache_hit_pct": round(trail.get("cache_hit_pct", 0), 1),
                "prior_7d_cache_hit_pct": round(prior.get("cache_hit_pct", 0), 1),
                "cache_hit_delta_pp": cache_delta,
            }

    # Subagent attribution orphans
    sub_summary = data.get("subagent_attribution_summary") or {}
    orphan_summary = None
    if sub_summary.get("orphan_subagent_turns", 0) > 0:
        orphan_summary = {
            "orphan_turns": sub_summary["orphan_subagent_turns"],
            "attributed_turns": sub_summary.get("attributed_turns", 0),
            "nested_levels_seen": sub_summary.get("nested_levels_seen", 0),
            "cycles_detected": sub_summary.get("cycles_detected", 0),
        }

    return {
        "file_re_reads": re_reads[:10],
        "paste_bombs": paste_bombs[:5],
        "wrong_model_turns": wrong_model[:5],
        "subagent_dominant_parents": sub_dominant[:5],
        "verbose_response": {
            "pct_of_turns": verbose_pct,
            "total_turns_sampled": sampled,
            "samples": samples,
        },
        "weekly_rollup": weekly_summary,
        "subagent_orphan": orphan_summary,
    }


def _weekly_rollup_summary(data: dict) -> dict | None:
    """Extract cost + cache-hit weekly trend from data["weekly_rollup"].

    Shared by project and instance baselines."""
    weekly = data.get("weekly_rollup") or {}
    if not weekly.get("has_data"):
        return None
    trail = weekly.get("trailing_7d", {}) or {}
    prior = weekly.get("prior_7d", {}) or {}
    prior_cost = prior.get("cost", 0) or 0
    trail_cost = trail.get("cost", 0) or 0
    if prior_cost <= 0:
        return None
    return {
        "trailing_7d_cost_usd": round(trail_cost, 2),
        "prior_7d_cost_usd": round(prior_cost, 2),
        "cost_delta_pct": round((trail_cost - prior_cost) / prior_cost * 100, 1),
        "trailing_7d_cache_hit_pct": round(trail.get("cache_hit_pct", 0), 1),
        "prior_7d_cache_hit_pct": round(prior.get("cache_hit_pct", 0), 1),
        "cache_hit_delta_pp": round(
            trail.get("cache_hit_pct", 0) - prior.get("cache_hit_pct", 0), 1
        ),
    }


def compute_project_baseline(data: dict) -> dict:
    """Baseline metrics for a project-scope JSON export."""
    totals = data.get("totals", {})
    sessions = data.get("sessions", [])
    n = len(sessions)
    cost = totals.get("cost", 0) or 0
    output = totals.get("output", 0)
    uncached_input = totals.get("total_input", 0) - totals.get("cache_read", 0)
    ratio = int(round(uncached_input / output)) if output else 0
    return {
        "total_cost_usd": round(cost, 2),
        "sessions_count": n,
        "cost_per_session_avg_usd": round(cost / n, 2) if n else 0,
        "turns": totals.get("turns", 0),
        "models": _models_with_shares(data),
        "input_output_ratio": ratio,
        "cache_hit_pct": round(totals.get("cache_hit_pct", 0), 1),
        "cache_savings_usd": round(totals.get("cache_savings", 0), 2),
        "no_cache_cost_usd": round(totals.get("no_cache_cost", 0), 2),
        "weekly_rollup": _weekly_rollup_summary(data),
    }


def compute_instance_baseline(data: dict) -> dict:
    """Baseline metrics for an instance-scope (all-projects) JSON export."""
    totals = data.get("totals", {})
    cost = totals.get("cost") or 0
    output = totals.get("output") or 0
    uncached_input = (totals.get("total_input") or 0) - (totals.get("cache_read") or 0)
    ratio = int(round(uncached_input / output)) if output else 0
    return {
        "total_cost_usd": round(cost, 2),
        "projects_count": data.get("project_count", len(data.get("projects", []))),
        "sessions_count": data.get("session_count", 0),
        "turns": totals.get("turns") or 0,
        "models": _models_with_shares(data),
        "input_output_ratio": ratio,
        "cache_hit_pct": round(totals.get("cache_hit_pct") or 0, 1),
        "cache_savings_usd": round(totals.get("cache_savings") or 0, 2),
        "no_cache_cost_usd": round(totals.get("no_cache_cost") or 0, 2),
        "weekly_rollup": _weekly_rollup_summary(data),
    }


def compute_project_session_analysis(data: dict) -> dict:
    """Per-session breakdown for a project-scope audit.

    Surfaces the four metrics the user cares about: top expensive sessions,
    sessions with below-average cache health, sessions that had cache breaks,
    and the weekly cost trend.
    """
    sessions = data.get("sessions", [])
    total_cost = (data.get("totals", {}) or {}).get("cost", 0) or 0
    overall_cache_hit = (data.get("totals", {}) or {}).get("cache_hit_pct", 0) or 0

    # Top 5 most expensive sessions
    by_cost = sorted(
        sessions,
        key=lambda s: (s.get("subtotal") or {}).get("cost", 0),
        reverse=True,
    )
    top_sessions = []
    for s in by_cost[:5]:
        sub = s.get("subtotal") or {}
        sc = sub.get("cost", 0) or 0
        top_sessions.append({
            "session_id_short": (s.get("session_id") or "")[:8],
            "first_ts": s.get("first_ts"),
            "cost_usd": round(sc, 4),
            "cost_share_pct": round(sc / total_cost * 100, 1) if total_cost else 0,
            "turns": sub.get("turns", 0),
            "cache_hit_pct": round(sub.get("cache_hit_pct", 0), 1),
        })

    # Sessions with poor cache health (below 80% AND cost > $0.01)
    POOR_CACHE_THRESHOLD = 80.0
    poor_cache = []
    for s in sessions:
        sub = s.get("subtotal") or {}
        hit = sub.get("cache_hit_pct", 0) or 0
        sc = sub.get("cost", 0) or 0
        if hit < POOR_CACHE_THRESHOLD and sc > 0.01:
            poor_cache.append({
                "session_id_short": (s.get("session_id") or "")[:8],
                "first_ts": s.get("first_ts"),
                "cache_hit_pct": round(hit, 1),
                "cost_usd": round(sc, 4),
                "gap_from_avg_pp": round(hit - overall_cache_hit, 1),
            })
    poor_cache.sort(key=lambda x: x["cache_hit_pct"])

    # Sessions that had cache break events
    sessions_with_breaks = []
    for s in sessions:
        breaks = s.get("cache_breaks") or []
        if breaks:
            sub = s.get("subtotal") or {}
            sessions_with_breaks.append({
                "session_id_short": (s.get("session_id") or "")[:8],
                "first_ts": s.get("first_ts"),
                "break_count": len(breaks),
                "cost_usd": round((sub.get("cost", 0) or 0), 4),
            })
    sessions_with_breaks.sort(key=lambda x: x["break_count"], reverse=True)

    return {
        "top_expensive_sessions": top_sessions,
        "poor_cache_health_sessions": poor_cache[:10],
        "sessions_with_cache_breaks": sessions_with_breaks[:10],
        "project_cache_hit_avg_pct": round(overall_cache_hit, 1),
        "poor_cache_threshold_pct": POOR_CACHE_THRESHOLD,
    }


def compute_instance_project_analysis(data: dict) -> dict:
    """Per-project breakdown for an instance-scope (all-projects) audit."""
    projects = data.get("projects", [])
    total_cost = (data.get("totals", {}) or {}).get("cost", 0) or 0

    # Top 5 most expensive projects
    by_cost = sorted(
        projects,
        key=lambda p: p.get("cost_usd", 0) or 0,
        reverse=True,
    )
    top_projects = []
    for p in by_cost[:5]:
        pc = p.get("cost_usd", 0) or 0
        top_projects.append({
            "slug": p.get("slug", ""),
            "cost_usd": round(pc, 2),
            "cost_share_pct": round(pc / total_cost * 100, 1) if total_cost else 0,
            "session_count": p.get("session_count", 0),
            "turn_count": p.get("turn_count", 0),
        })

    # Projects with poor average cache health
    POOR_CACHE_THRESHOLD = 80.0
    overall_cache_hit = (data.get("totals", {}) or {}).get("cache_hit_pct", 0) or 0
    poor_cache = []
    for p in projects:
        p_sessions = p.get("sessions") or []
        if not p_sessions:
            continue
        hits = [
            (s.get("subtotal") or {}).get("cache_hit_pct", 0) or 0
            for s in p_sessions
        ]
        avg_hit = sum(hits) / len(hits) if hits else 0
        pc = p.get("cost_usd", 0) or 0
        if avg_hit < POOR_CACHE_THRESHOLD and pc > 0.10:
            poor_cache.append({
                "slug": p.get("slug", ""),
                "avg_cache_hit_pct": round(avg_hit, 1),
                "cost_usd": round(pc, 2),
                "gap_from_avg_pp": round(avg_hit - overall_cache_hit, 1),
            })
    poor_cache.sort(key=lambda x: x["avg_cache_hit_pct"])

    return {
        "top_expensive_projects": top_projects,
        "poor_cache_health_projects": poor_cache[:5],
        "instance_cache_hit_avg_pct": round(overall_cache_hit, 1),
        "poor_cache_threshold_pct": POOR_CACHE_THRESHOLD,
        "total_projects": len(projects),
        "total_sessions": data.get("session_count", 0),
    }


def build_digest(data: dict, json_path: str, mode: str) -> dict:
    scope = detect_scope(data, json_path)

    if scope == "project":
        id8, ts = project_filename_parts(json_path)
        turns = flatten_turns(data)
        cache_breaks = data.get("cache_breaks", []) or []
        fired = [
            t for t in evaluate_triggers(data, turns)
            if t["metric"] not in SESSION_ONLY_METRICS
        ]
        digest: dict[str, Any] = {
            "digest_schema_version": DIGEST_SCHEMA_VERSION,
            "scope": scope,
            "session_id_short": id8,
            "ts_str": ts,
            "input_json": os.path.abspath(json_path),
            "mode_hint": mode,
            "session_archetype": "n/a",
            "archetype_signals": {"scope": "project", "sessions_count": len(data.get("sessions", []))},
            "baseline": compute_project_baseline(data),
            "fired_triggers": fired,
            "positive_triggers": evaluate_positive_triggers(data),
            "top_expensive_turns": top_expensive_turns(turns, cache_breaks),
            "project_analysis": compute_project_session_analysis(data),
        }
        return digest

    if scope == "instance":
        id8, ts = instance_filename_parts(json_path)
        digest = {
            "digest_schema_version": DIGEST_SCHEMA_VERSION,
            "scope": scope,
            "session_id_short": id8,
            "ts_str": ts,
            "input_json": os.path.abspath(json_path),
            "mode_hint": mode,
            "session_archetype": "n/a",
            "archetype_signals": {
                "scope": "instance",
                "projects_count": len(data.get("projects", [])),
            },
            "baseline": compute_instance_baseline(data),
            "fired_triggers": [],
            "positive_triggers": evaluate_positive_triggers(data),
            "top_expensive_turns": [],
            "instance_analysis": compute_instance_project_analysis(data),
        }
        return digest

    # session scope (existing path)
    turns = flatten_turns(data)
    cache_breaks = data.get("cache_breaks", []) or []
    id8, ts = session_filename_parts(json_path)
    archetype, archetype_signals = classify_session_archetype(data, turns)
    digest = {
        "digest_schema_version": DIGEST_SCHEMA_VERSION,
        "scope": scope,
        "session_id_short": id8,
        "ts_str": ts,
        "input_json": os.path.abspath(json_path),
        "mode_hint": mode,
        "session_archetype": archetype,
        "archetype_signals": archetype_signals,
        "baseline": compute_baseline(data),
        "fired_triggers": evaluate_triggers(data, turns),
        "positive_triggers": evaluate_positive_triggers(data),
        "top_expensive_turns": top_expensive_turns(turns, cache_breaks),
    }
    if mode == "detailed":
        digest["detailed_candidates"] = detailed_candidates(data, turns)
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-compute audit triggers + metrics from a session-metrics JSON export.")
    parser.add_argument("json_path", help="Path to a session-metrics JSON export.")
    parser.add_argument(
        "--mode", choices=["quick", "detailed"], default="quick",
        help="Audit mode the digest is being built for. Detailed mode adds re-read / "
             "paste-bomb / wrong-model / weekly-delta / orphan scans.",
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.json_path):
        print(json.dumps({"error": f"file not found: {args.json_path}"}), file=sys.stderr)
        return 2

    with open(args.json_path, encoding="utf-8") as f:
        data = json.load(f)

    digest = build_digest(data, args.json_path, args.mode)
    json.dump(digest, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
