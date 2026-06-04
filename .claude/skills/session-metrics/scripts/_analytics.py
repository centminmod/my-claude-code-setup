"""Usage Insights and analytics helpers for session-metrics."""
import html as html_mod
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from _time_of_day import _is_off_peak_local


def _sm():
    """Return the session_metrics module (deferred — fully loaded by call time)."""
    return sys.modules["session_metrics"]


# ---------------------------------------------------------------------------
# Usage Insights thresholds
# ---------------------------------------------------------------------------

_INSIGHT_PARALLEL_PCT_THRESHOLD       = 20.0   # ≥ 20% of cost from multi-session 5h blocks
_INSIGHT_LONG_SESSION_HOURS           = 8      # session spans ≥ 8h wall-clock
_INSIGHT_LONG_SESSION_PCT_THRESHOLD   = 10.0
_INSIGHT_BIG_CONTEXT_TOKENS           = 150_000
_INSIGHT_BIG_CONTEXT_PCT_THRESHOLD    = 10.0
_INSIGHT_BIG_CACHE_MISS_TOKENS        = 100_000
_INSIGHT_BIG_CACHE_MISS_PCT_THRESHOLD = 5.0
_INSIGHT_SUBAGENT_TASK_COUNT          = 3      # ≥ 3 Task tool calls in a session
_INSIGHT_SUBAGENT_PCT_THRESHOLD       = 10.0
_INSIGHT_TOOL_DOMINANCE_MIN_CALLS     = 10     # gate, not %
_INSIGHT_OFF_PEAK_PCT_THRESHOLD       = 60.0   # heavy off-peak only (above ~58% baseline)
_INSIGHT_COST_CONCENTRATION_TOP_N     = 5
_INSIGHT_COST_CONCENTRATION_PCT       = 25.0
_INSIGHT_COST_CONCENTRATION_MIN_TURNS = 10     # avoid trivially-100% case for tiny sessions
_INSIGHT_TRUNCATED_MIN_TURNS          = 5      # ≥ 5 max_tokens turns before the truncation insight fires
_INSIGHT_TRUNCATED_PCT_THRESHOLD      = 5.0    # …and ≥ 5% of cost on those turns
_INSIGHT_THINKING_PCT_THRESHOLD       = 10.0   # cost share from extended-thinking-engaged turns


def _session_task_count(session: dict) -> int:
    """Count `Task` tool invocations across a session's turns. The Task tool
    is Claude Code's subagent-dispatch mechanism — counting spawn calls in
    the main agent's transcript works regardless of `--include-subagents`."""
    n = 0
    for t in session.get("turns", []):
        for name in (t.get("tool_use_names") or []):
            if name == "Task":
                n += 1
    return n


def _turn_total_input(turn: dict) -> int:
    """Total tokens fed into the model on this turn (proxy for context fill)."""
    return (turn.get("input_tokens", 0)
            + turn.get("cache_read_tokens", 0)
            + turn.get("cache_write_tokens", 0))


def _model_family(model_id: str) -> str:
    """Coarse family bucket from a model id like `claude-opus-4-7`."""
    m = (model_id or "").lower()
    if "opus" in m:
        return "Opus"
    if "sonnet" in m:
        return "Sonnet"
    if "haiku" in m:
        return "Haiku"
    return "Other"


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. `values` is assumed unsorted; sorted internally."""
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(pct / 100.0 * (len(s) - 1)))))
    return s[k]


def _fmt_long_duration(seconds: float) -> str:
    """Compact human duration for insight prose: `42m`, `3.2h`, `1d 4h`.

    Distinct from the existing ``_fmt_duration(int)`` helper used by the
    per-session burn-rate card (which formats short, exact intervals like
    ``45m12s``). Insight strings prefer rounder numbers and multi-day
    coverage at the cost of second-level precision.
    """
    s = max(0, int(seconds))
    if s < 3600:
        return f"{s // 60}m"
    h = s / 3600.0
    if h < 24:
        return f"{h:.1f}h"
    days = int(h // 24)
    rem  = int(h - days * 24)
    return f"{days}d {rem}h" if rem else f"{days}d"


# ---------------------------------------------------------------------------
# Compare-insight state marker + multi-family detection (Phase 7)
# ---------------------------------------------------------------------------

def _compare_state_marker_path(slug: str) -> Path:
    """File whose presence means the user has run ``--compare`` at least
    once for this project.

    Lives under the project's JSONL directory (not the session-metrics
    cache) so uninstalling session-metrics doesn't lose the marker, and
    so deleting a project's session dir cleans up the marker alongside
    everything else.
    """
    return _sm()._projects_dir() / slug / ".session-metrics-compare-used"


def _touch_compare_state_marker(slug: str) -> None:
    """Drop the opt-in marker before running ``--compare``.

    Best-effort: a filesystem failure here shouldn't abort the compare
    run. Callers wrap the call in a try/except that swallows ``OSError``.
    The marker content is an ISO-8601 timestamp so later tooling could
    show "first compare run on date X" — not used yet, but cheap to
    record.
    """
    marker = _compare_state_marker_path(slug)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8",
    )


def _has_compare_state_marker(slug: str) -> bool:
    """True iff :func:`_touch_compare_state_marker` has been called
    for this project (i.e., the user opted into compare-aware insights)."""
    return _compare_state_marker_path(slug).is_file()


def _scan_project_family_mix(slug: str) -> list[str]:
    """Return the sorted set of fine-grained model family slugs
    (``"opus-4-6"`` etc.) observed across every session in the project.

    Pulled via the compare module's ``_project_family_inventory`` so
    the family slug matches compare-mode conventions (1M-context suffix
    stripped). Called only by ``_compute_model_compare_insight`` — the
    main-report insight bank doesn't re-scan the disk for the other
    cards because the report already has all the data it needs.
    """
    try:
        smc = sys.modules.get("session_metrics_compare")
        if smc is None:
            # Lazy-load. The helper is in a sibling file; import here so
            # regular single-session reports don't pay for it.
            here = Path(__file__).resolve().parent
            spec = importlib.util.spec_from_file_location(
                "session_metrics_compare",
                here / "session_metrics_compare.py",
            )
            if spec is None or spec.loader is None:
                return []
            smc = importlib.util.module_from_spec(spec)
            # Ensure session_metrics is resolvable by the compare module.
            # By call time the monolith is fully loaded under "session_metrics"
            # (test runner) or "__main__" (direct script execution).
            _sm_mod = sys.modules.get("session_metrics") or sys.modules.get("__main__")
            if _sm_mod is not None:
                sys.modules.setdefault("session_metrics", _sm_mod)
            sys.modules["session_metrics_compare"] = smc
            spec.loader.exec_module(smc)
        inventory = smc._project_family_inventory(slug, use_cache=True)
    except (OSError, AttributeError, ImportError):
        return []
    return sorted(f for f in inventory.keys() if f)


def _version_suffix_of_family(family: str) -> tuple[int, ...]:
    """Parse trailing integer-dash segments out of a family slug.

    ``opus-4-7`` → ``(4, 7)``; ``sonnet-4-5-haiku`` → ``(4, 5)``.
    Used to order families for the "newer / older" insight copy. Returns
    ``()`` when no trailing ints are present — families compared as
    equal in that case fall back to alphabetical ordering in the caller.
    """
    parts = family.split("-")
    nums: list[int] = []
    # Walk from the right and collect integers until we hit a non-int.
    for part in reversed(parts):
        if part.isdigit():
            nums.append(int(part))
        else:
            break
    return tuple(reversed(nums))


def _order_family_pair(families: list[str]) -> tuple[str, str] | None:
    """Pick a deterministic (older, newer) pair from a family list.

    - If exactly two families, orders by version suffix (higher =
      newer), falling back to alphabetical.
    - If more than two, picks the two most distinct by version: the
      lowest-version family as "older" and the highest as "newer". Ties
      fall back to alphabetical.
    - Returns ``None`` when fewer than two families are present.
    """
    distinct = [f for f in dict.fromkeys(families) if f]
    if len(distinct) < 2:
        return None
    keyed = sorted(distinct, key=lambda f: (_version_suffix_of_family(f), f))
    return (keyed[0], keyed[-1])


def _compute_model_compare_insight(report: dict) -> dict | None:
    """Build the Phase-7 model-compare insight card for a report.

    Fires with a soft hint when:
    - the user has NOT yet run ``--compare`` in this project, AND
    - at least two distinct model families appear in the project's
      sessions (not just this report's sessions — we scan the project
      dir so the hint still shows on a single-session report that only
      used one family, as long as the *project* has two).

    Fires with a stronger card ("run '--compare' for an attribution-
    grade benchmark") once the marker exists — the hint shape is the
    same, but the copy acknowledges the user has already engaged.

    Returns ``None`` (caller suppresses the card) when:
    - fewer than two families are present in the project, or
    - ``--no-model-compare-insight`` was passed (caller handles this;
      the builder itself doesn't read CLI flags), or
    - the project slug can't be determined.
    """
    slug = report.get("slug") or ""
    if not slug:
        return None
    families = _scan_project_family_mix(slug)
    pair = _order_family_pair(families)
    if not pair:
        return None
    older, newer = pair
    already_used = _has_compare_state_marker(slug)
    n_families = len([f for f in families if f])
    if already_used:
        headline = f"{n_families} model families &mdash; run a fresh compare"
        body = (
            f" &mdash; <code>{html_mod.escape(older)}</code> and "
            f"<code>{html_mod.escape(newer)}</code> both appear in this "
            f"project. Re-run <code>session-metrics --compare last-"
            f"{html_mod.escape(older)} last-{html_mod.escape(newer)}</code> "
            f"to refresh attribution numbers with your latest sessions."
        )
    else:
        headline = f"{n_families} model families detected"
        body = (
            f" in this project's sessions &mdash; "
            f"<code>{html_mod.escape(older)}</code> and "
            f"<code>{html_mod.escape(newer)}</code>. "
            f"Run <code>session-metrics --compare-prep</code> to set up a "
            f"controlled comparison that isolates tokenizer / output-length "
            f"effects from workload shift."
        )
    return {
        "id":        "model_compare",
        "headline":  headline,
        "body":      body,
        "value":     float(n_families),
        "threshold": 2.0,
        "shown":     True,
        "always_on": True,
    }


def _compute_usage_insights(report: dict) -> list[dict]:
    """Compute the Usage Insights candidate list. See module-level
    `_INSIGHT_*` constants for thresholds. Each entry:
        {id, headline, body, value, threshold, shown, always_on}
    Returns `[]` if total cost is zero (avoids percentage division by zero).
    """
    totals     = report.get("totals", {}) or {}
    total_cost = float(totals.get("cost", 0.0) or 0.0)
    if total_cost <= 0:
        return []

    sessions       = report.get("sessions", []) or []
    blocks         = report.get("session_blocks", []) or []
    tz_off         = float(report.get("tz_offset_hours", 0.0) or 0.0)
    all_turns      = [t for s in sessions for t in s.get("turns", [])]
    total_turns    = len(all_turns)
    candidates: list[dict] = []

    # 1. Parallel sessions — cost from 5h blocks where multiple sessions touched the window.
    parallel_cost = sum(b.get("cost_usd", 0.0) for b in blocks
                        if len(b.get("sessions_touched") or []) > 1)
    parallel_pct  = 100.0 * parallel_cost / total_cost
    candidates.append({
        "id":        "parallel_sessions",
        "headline":  f"{parallel_pct:.0f}%",
        "body":      f" of cost came from 5-hour windows where you ran more than one session in parallel — concurrent sessions share the same rate-limit window.",
        "value":     parallel_pct,
        "threshold": _INSIGHT_PARALLEL_PCT_THRESHOLD,
        "shown":     parallel_pct >= _INSIGHT_PARALLEL_PCT_THRESHOLD,
        "always_on": False,
    })

    # 2. Long sessions — cost share from sessions ≥ 8h wall-clock.
    long_cutoff = _INSIGHT_LONG_SESSION_HOURS * 3600
    long_cost   = sum(s.get("subtotal", {}).get("cost", 0.0)
                      for s in sessions
                      if s.get("duration_seconds", 0) >= long_cutoff)
    long_pct    = 100.0 * long_cost / total_cost
    candidates.append({
        "id":        "long_sessions",
        "headline":  f"{long_pct:.0f}%",
        "body":      f" of cost came from sessions active for {_INSIGHT_LONG_SESSION_HOURS}+ hours — long-lived sessions accumulate context cost over time.",
        "value":     long_pct,
        "threshold": _INSIGHT_LONG_SESSION_PCT_THRESHOLD,
        "shown":     long_pct >= _INSIGHT_LONG_SESSION_PCT_THRESHOLD,
        "always_on": False,
    })

    # 3. Big-context turns — cost share of turns where total input ≥ 150k.
    big_ctx_cost = sum(t.get("cost_usd", 0.0) for t in all_turns
                       if _turn_total_input(t) >= _INSIGHT_BIG_CONTEXT_TOKENS)
    big_ctx_pct  = 100.0 * big_ctx_cost / total_cost
    candidates.append({
        "id":        "big_context_turns",
        "headline":  f"{big_ctx_pct:.0f}%",
        "body":      f" of cost was spent on turns with ≥{_INSIGHT_BIG_CONTEXT_TOKENS // 1000}k context filled — `/compact` mid-task or `/clear` between tasks keeps the running input down.",
        "value":     big_ctx_pct,
        "threshold": _INSIGHT_BIG_CONTEXT_PCT_THRESHOLD,
        "shown":     big_ctx_pct >= _INSIGHT_BIG_CONTEXT_PCT_THRESHOLD,
        "always_on": False,
    })

    # 4. Big cache misses — cost share of turns sending ≥ 100k uncached input.
    miss_cost = sum(t.get("cost_usd", 0.0) for t in all_turns
                    if (t.get("input_tokens", 0) + t.get("cache_write_tokens", 0))
                       >= _INSIGHT_BIG_CACHE_MISS_TOKENS)
    miss_pct  = 100.0 * miss_cost / total_cost
    candidates.append({
        "id":        "big_cache_misses",
        "headline":  f"{miss_pct:.0f}%",
        "body":      f" of cost came from turns with ≥{_INSIGHT_BIG_CACHE_MISS_TOKENS // 1000}k tokens of uncached input — typically a cold-start after a session went idle, or a large new prompt that wasn't cached.",
        "value":     miss_pct,
        "threshold": _INSIGHT_BIG_CACHE_MISS_PCT_THRESHOLD,
        "shown":     miss_pct >= _INSIGHT_BIG_CACHE_MISS_PCT_THRESHOLD,
        "always_on": False,
    })

    # 5. Subagent-heavy sessions — cost share from sessions with ≥ 3 Task calls.
    subagent_cost = sum(s.get("subtotal", {}).get("cost", 0.0)
                        for s in sessions
                        if _session_task_count(s) >= _INSIGHT_SUBAGENT_TASK_COUNT)
    subagent_pct  = 100.0 * subagent_cost / total_cost
    candidates.append({
        "id":        "subagent_heavy",
        "headline":  f"{subagent_pct:.0f}%",
        "body":      f" of cost came from sessions that ran {_INSIGHT_SUBAGENT_TASK_COUNT}+ subagent dispatches (Task tool) — each subagent runs its own request loop.",
        "value":     subagent_pct,
        "threshold": _INSIGHT_SUBAGENT_PCT_THRESHOLD,
        "shown":     subagent_pct >= _INSIGHT_SUBAGENT_PCT_THRESHOLD,
        "always_on": False,
    })

    # 6. Tool dominance — top-3 tool names' share of all tool calls.
    name_counts: dict[str, int] = {}
    for t in all_turns:
        for name in (t.get("tool_use_names") or []):
            name_counts[name] = name_counts.get(name, 0) + 1
    total_tool_calls = sum(name_counts.values())
    if total_tool_calls >= _INSIGHT_TOOL_DOMINANCE_MIN_CALLS:
        ranked = sorted(name_counts.items(), key=lambda x: (-x[1], x[0]))
        top3   = ranked[:3]
        top3_share = 100.0 * sum(c for _, c in top3) / total_tool_calls
        names_str  = ", ".join(html_mod.escape(n) for n, _ in top3)
        candidates.append({
            "id":        "top3_tools",
            "headline":  f"{top3_share:.0f}%",
            "body":      f" of all tool calls were {names_str} — your top-3 tools dominate this {total_tool_calls:,}-call workload.",
            "value":     top3_share,
            "threshold": 0.0,
            "shown":     True,
            "always_on": False,
        })
    else:
        candidates.append({
            "id":        "top3_tools",
            "headline":  "0%",
            "body":      " (insufficient tool-call volume).",
            "value":     0.0,
            "threshold": 0.0,
            "shown":     False,
            "always_on": False,
        })

    # 7. Off-peak share — cost share with timestamps outside 09:00–18:00 local weekday.
    _parse_iso_epoch = _sm()._parse_iso_epoch
    off_peak_cost = sum(t.get("cost_usd", 0.0) for t in all_turns
                        if _is_off_peak_local(_parse_iso_epoch(t.get("timestamp", "")), tz_off))
    off_peak_pct  = 100.0 * off_peak_cost / total_cost
    candidates.append({
        "id":        "off_peak_share",
        "headline":  f"{off_peak_pct:.0f}%",
        "body":      f" of cost happened outside business hours (before 09:00, after 18:00, or on weekends in your local timezone) — heads-up that long-running subagents while you're AFK still bill.",
        "value":     off_peak_pct,
        "threshold": _INSIGHT_OFF_PEAK_PCT_THRESHOLD,
        "shown":     off_peak_pct >= _INSIGHT_OFF_PEAK_PCT_THRESHOLD,
        "always_on": False,
    })

    # 8. Cost concentration — top-N turns' cost share (gated on total turns ≥ 10).
    if total_turns >= _INSIGHT_COST_CONCENTRATION_MIN_TURNS:
        sorted_costs = sorted((t.get("cost_usd", 0.0) for t in all_turns), reverse=True)
        topn_share   = 100.0 * sum(sorted_costs[:_INSIGHT_COST_CONCENTRATION_TOP_N]) / total_cost
        candidates.append({
            "id":        "cost_concentration",
            "headline":  f"{topn_share:.0f}%",
            "body":      f" of cost was driven by just the top {_INSIGHT_COST_CONCENTRATION_TOP_N} most-expensive turns out of {total_turns:,} total — a few large turns dominate the bill.",
            "value":     topn_share,
            "threshold": _INSIGHT_COST_CONCENTRATION_PCT,
            "shown":     topn_share >= _INSIGHT_COST_CONCENTRATION_PCT,
            "always_on": False,
        })
    else:
        candidates.append({
            "id":        "cost_concentration",
            "headline":  "0%",
            "body":      " (too few turns to call concentration meaningful).",
            "value":     0.0,
            "threshold": _INSIGHT_COST_CONCENTRATION_PCT,
            "shown":     False,
            "always_on": False,
        })

    # 9. Model mix — cost share by family, shown iff ≥ 2 families seen.
    family_cost: dict[str, float] = {}
    for t in all_turns:
        fam = _model_family(t.get("model", ""))
        family_cost[fam] = family_cost.get(fam, 0) + t.get("cost_usd", 0.0)
    families_used = [f for f, c in family_cost.items() if c > 0]
    if len(families_used) >= 2:
        ranked_fams = sorted(family_cost.items(), key=lambda x: -x[1])
        parts       = [f"{html_mod.escape(f)} {100.0 * c / total_cost:.0f}%"
                       for f, c in ranked_fams if c > 0]
        candidates.append({
            "id":        "model_mix",
            "headline":  f"{len(families_used)} families",
            "body":      f" — cost split: {' · '.join(parts)}.",
            "value":     float(len(families_used)),
            "threshold": 2.0,
            "shown":     True,
            "always_on": True,
        })
    else:
        candidates.append({
            "id":        "model_mix",
            "headline":  "1 family",
            "body":      " (single-model project).",
            "value":     1.0,
            "threshold": 2.0,
            "shown":     False,
            "always_on": True,
        })

    # 10. Session pacing — turn-count distribution + duration extremes (≥ 2 sessions).
    if len(sessions) >= 2:
        durations = [s.get("duration_seconds", 0) for s in sessions if s.get("duration_seconds", 0) > 0]
        turn_counts = [len(s.get("turns", [])) for s in sessions]
        median_dur  = _percentile(durations, 50) if durations else 0
        longest_dur = max(durations) if durations else 0
        tc_min  = min(turn_counts) if turn_counts else 0
        tc_max  = max(turn_counts) if turn_counts else 0
        tc_avg  = (sum(turn_counts) / len(turn_counts)) if turn_counts else 0
        tc_p95  = _percentile([float(x) for x in turn_counts], 95) if turn_counts else 0
        candidates.append({
            "id":        "session_pacing",
            "headline":  f"{len(sessions)} sessions",
            "body":      (f" — median duration {_fmt_long_duration(median_dur)}, longest {_fmt_long_duration(longest_dur)};"
                          f" turns/session min {tc_min:,} · avg {tc_avg:.0f} · p95 {int(tc_p95):,} · max {tc_max:,}."),
            "value":     float(len(sessions)),
            "threshold": 2.0,
            "shown":     True,
            "always_on": True,
        })
    else:
        candidates.append({
            "id":        "session_pacing",
            "headline":  "1 session",
            "body":      " (no distribution to summarise).",
            "value":     1.0,
            "threshold": 2.0,
            "shown":     False,
            "always_on": True,
        })

    # 11. Truncated responses — cost share + count of turns that hit the output
    # token limit (stop_reason == "max_tokens"). Gated on a minimum count so a
    # single truncated turn in a tiny session doesn't fire. Neutral framing: a
    # truncated turn isn't necessarily wasted, but frequent limit-hits mean
    # follow-ups that re-send context.
    trunc_turns = [t for t in all_turns if t.get("stop_reason") == "max_tokens"]
    trunc_n     = len(trunc_turns)
    trunc_cost  = sum(t.get("cost_usd", 0.0) for t in trunc_turns)
    trunc_pct   = 100.0 * trunc_cost / total_cost
    candidates.append({
        "id":        "truncated_responses",
        "headline":  f"{trunc_pct:.0f}%",
        "body":      (f" of cost came from {trunc_n:,} turn{'s' if trunc_n != 1 else ''} that hit the "
                      f"output-token limit (stop_reason=max_tokens) — incomplete replies often need a "
                      f"follow-up that re-sends context; a higher max-output-tokens setting can cut the round-trips."),
        "value":     trunc_pct,
        "threshold": _INSIGHT_TRUNCATED_PCT_THRESHOLD,
        "shown":     trunc_n >= _INSIGHT_TRUNCATED_MIN_TURNS and trunc_pct >= _INSIGHT_TRUNCATED_PCT_THRESHOLD,
        "always_on": False,
    })

    # 12. Extended-thinking engagement — cost share of turns that carried a
    # thinking block. Behavioural signal ("how much spend involved extended
    # thinking"), NOT a thinking-token cost: thinking tokens are billed inside
    # output_tokens and are not separately measurable from the transcript.
    thinking_cost = sum(t.get("cost_usd", 0.0) for t in all_turns
                        if (t.get("content_blocks") or {}).get("thinking", 0) > 0)
    thinking_pct  = 100.0 * thinking_cost / total_cost
    candidates.append({
        "id":        "thinking_engagement",
        "headline":  f"{thinking_pct:.0f}%",
        "body":      (" of cost came from turns that engaged extended thinking — reasoning trades extra "
                      "output tokens (billed at the output rate) for deeper analysis."),
        "value":     thinking_pct,
        "threshold": _INSIGHT_THINKING_PCT_THRESHOLD,
        "shown":     thinking_pct >= _INSIGHT_THINKING_PCT_THRESHOLD,
        "always_on": False,
    })

    # 13. Model compare hint — fires when the project has ≥2 distinct
    # model families. Gated behind a state marker so the card escalates
    # from "hint you can run a benchmark" to "re-run for fresh numbers"
    # once the user actually tries --compare. Suppressed CLI-side via
    # --no-model-compare-insight.
    if not report.get("_suppress_model_compare_insight"):
        mc = _compute_model_compare_insight(report)
        if mc is not None:
            candidates.append(mc)

    return candidates
