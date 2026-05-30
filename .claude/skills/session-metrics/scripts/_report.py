"""Report building and aggregation layer for session-metrics."""
import functools
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from _constants import _CACHE_BREAK_DEFAULT_THRESHOLD


def _sm():
    return sys.modules["session_metrics"]


def _build_compaction_summary(sessions_out: list[dict]) -> tuple[list[dict], dict]:
    """Aggregate per-session compaction events into a flat list + summary.

    Q1 (compaction detection). Reads ``compaction_events`` (a list of
    boundary dicts from ``_extract_compaction_events``) and
    ``starts_with_summary`` off each session dict. Returns
    ``(events, summary)`` where:

      - ``events`` is the flattened boundary list with ``session_id`` stamped
        on each, in session order (renderers / JSON read this directly).
      - ``summary`` is a dict::

          {boundary_count, auto_count, manual_count, unknown_trigger_count,
           total_reclaimed_tokens, total_pre_tokens, total_post_tokens,
           sessions_with_compaction, continuation_session_count}

    ``reclaimed``/``pre``/``post`` sums skip boundaries where the field is
    absent (older Claude Code builds), so totals are lower bounds when any
    boundary lacks token counts. All counts default to 0, so a report with no
    compaction yields an all-zero summary (renderers auto-hide on
    ``boundary_count == 0``).
    """
    events: list[dict] = []
    auto = manual = unknown = 0
    total_reclaimed = total_pre = total_post = 0
    sessions_with = 0
    continuations = 0
    for s in sessions_out:
        boundaries = s.get("compaction_events") or []
        if s.get("starts_with_summary"):
            continuations += 1
        if boundaries:
            sessions_with += 1
        for b in boundaries:
            ev = dict(b)
            ev["session_id"] = s.get("session_id", "")
            events.append(ev)
            trig = b.get("trigger")
            if trig == "auto":
                auto += 1
            elif trig == "manual":
                manual += 1
            else:
                unknown += 1
            if isinstance(b.get("reclaimed_tokens"), int):
                total_reclaimed += b["reclaimed_tokens"]
            if isinstance(b.get("pre_tokens"), int):
                total_pre += b["pre_tokens"]
            if isinstance(b.get("post_tokens"), int):
                total_post += b["post_tokens"]
    summary = {
        "boundary_count":           len(events),
        "auto_count":               auto,
        "manual_count":             manual,
        "unknown_trigger_count":    unknown,
        "total_reclaimed_tokens":   total_reclaimed,
        "total_pre_tokens":         total_pre,
        "total_post_tokens":        total_post,
        "sessions_with_compaction": sessions_with,
        "continuation_session_count": continuations,
    }
    return events, summary


def _compute_subagent_share(report: dict) -> dict:
    """Compute the headline 'subagent share' stat + attribution coverage.

    Returns a dict with the keys consumed by the renderers:

      - ``include_subagents`` — was the loader run with ``--include-subagents``?
      - ``has_attribution``   — at least one subagent turn was attributed
      - ``total_cost``        — totals[cost] (parent + subagent direct cost,
                                  same as the report's headline total)
      - ``attributed_cost``   — sum of ``attributed_subagent_cost`` across
                                  every main turn (lower bound; orphans
                                  are excluded)
      - ``share_pct``         — ``100 * attributed_cost / total_cost`` (0
                                  when total_cost is 0)
      - ``spawn_count``       — sum of len(t['spawned_subagents']) across
                                  main turns
      - ``attributed_count``  — sum of ``attributed_subagent_count`` across
                                  main turns (= rolled-up subagent turns)
      - ``orphan_turns``      — from ``subagent_attribution_summary``
      - ``cycles_detected``   — from ``subagent_attribution_summary``
      - ``nested_levels_seen``— max nesting depth observed (1 = direct
                                  child only; ≥2 = chains)
    """
    sessions = report.get("sessions") or []
    totals   = report.get("totals") or {}
    summary  = report.get("subagent_attribution_summary") or {}
    total_cost  = float(totals.get("cost", 0.0))
    attributed_cost  = 0.0
    attributed_count = 0
    spawn_count      = 0
    subagent_turn_count = 0
    main_turn_count     = 0
    for s in sessions:
        for t in s.get("turns", []) or []:
            if t.get("is_resume_marker"):
                continue
            if t.get("subagent_agent_id"):
                # Subagent turn — count towards the count-basis denominator
                # plus the numerator. Cost is rolled up onto the parent via
                # the attribution pass below.
                subagent_turn_count += 1
                continue
            main_turn_count  += 1
            attributed_cost  += float(t.get("attributed_subagent_cost", 0.0))
            attributed_count += int(t.get("attributed_subagent_count", 0))
            spawn_count      += len(t.get("spawned_subagents") or [])
    share_pct = (100.0 * attributed_cost / total_cost) if total_cost > 0 else 0.0
    total_turn_count = main_turn_count + subagent_turn_count
    turn_share_pct = (
        100.0 * subagent_turn_count / total_turn_count
        if total_turn_count > 0 else 0.0
    )
    return {
        "include_subagents":  bool(report.get("include_subagents", False)),
        "has_attribution":    attributed_count > 0,
        "total_cost":         total_cost,
        "attributed_cost":    attributed_cost,
        "share_pct":          share_pct,
        "spawn_count":        spawn_count,
        "attributed_count":   attributed_count,
        "orphan_turns":       int(summary.get("orphan_subagent_turns", 0)),
        "cycles_detected":    int(summary.get("cycles_detected", 0)),
        "nested_levels_seen": int(summary.get("nested_levels_seen", 0)),
        # Count-basis turn-share — surfaced alongside the cost-basis share
        # in the dashboard KPI strip so both framings are visible. cognitive-
        # claude reports turn-share only; we surface both.
        "subagent_turn_count": subagent_turn_count,
        "main_turn_count":     main_turn_count,
        "total_turn_count":    total_turn_count,
        "turn_share_pct":      turn_share_pct,
    }


def _compute_within_session_split(sessions: list[dict],
                                    min_per_bucket: int = 3) -> list[dict]:
    """Compute per-session median combined-cost on spawning vs non-spawning turns.

    Returns one dict per session with at least ``min_per_bucket`` (default 3)
    spawning turns AND at least ``min_per_bucket`` non-spawning turns. Sessions
    with fewer turns in either bucket are skipped — three is the minimum where
    a median is meaningful.

    "Combined cost" is ``cost_usd + attributed_subagent_cost`` so that a
    spawning turn's cost reflects the work done both by the parent and by
    the subagent rolled up to it. (See section helper text in the renderer
    for the within-session selection-bias caveat.)

    A turn is "spawning" if it issued at least one Agent/Task tool call,
    detected via ``len(spawned_subagents) > 0`` OR ``len(tool_use_ids) > 0``.
    Subagent turns themselves (``subagent_agent_id`` non-empty) and resume
    markers are excluded from both buckets.

    Each output dict has::

        session_id, spawn_n, no_spawn_n,
        median_spawn, median_no_spawn,
        delta            (median_spawn - median_no_spawn, positive = spawning costs more)
        spawn_share_pct  (100 * sum(combined_cost on spawn turns) / session total cost)
    """
    out: list[dict] = []
    for s in sessions:
        spawn_costs: list[float] = []
        no_spawn_costs: list[float] = []
        spawn_total = 0.0
        for t in s.get("turns", []) or []:
            if t.get("subagent_agent_id"):
                continue
            if t.get("is_resume_marker"):
                continue
            combined = (
                float(t.get("cost_usd", 0.0))
                + float(t.get("attributed_subagent_cost", 0.0))
            )
            is_spawning = bool(t.get("spawned_subagents")) or bool(t.get("tool_use_ids"))
            if is_spawning:
                spawn_costs.append(combined)
                spawn_total += combined
            else:
                no_spawn_costs.append(combined)
        if (len(spawn_costs) < min_per_bucket
                or len(no_spawn_costs) < min_per_bucket):
            continue
        median_spawn    = _median(spawn_costs)
        median_no_spawn = _median(no_spawn_costs)
        session_total = float(s.get("subtotal", {}).get("cost", 0.0))
        spawn_share_pct = (100.0 * spawn_total / session_total) if session_total > 0 else 0.0
        out.append({
            "session_id":       s.get("session_id", ""),
            "spawn_n":          len(spawn_costs),
            "no_spawn_n":       len(no_spawn_costs),
            "median_spawn":     median_spawn,
            "median_no_spawn":  median_no_spawn,
            "delta":            median_spawn - median_no_spawn,
            "spawn_share_pct":  spawn_share_pct,
        })
    return out


def _compute_instance_subagent_share(project_reports: list[dict],
                                       instance_totals: dict,
                                       include_subagents: bool) -> dict:
    """Instance-scope variant of ``_compute_subagent_share``.

    The instance report deliberately keeps ``sessions = []`` to bound
    JSON/CSV size, so we can't iterate per-turn fields here. Instead we
    sum each project's headline stats. ``subagent_attribution_summary``
    is already aggregated by ``_aggregate_attribution_summary`` so the
    same orphan/cycle counts surface.
    """
    total_cost = float(instance_totals.get("cost", 0.0))
    attributed_cost = 0.0
    attributed_count = 0
    spawn_count = 0
    orphan_turns = 0
    cycles_detected = 0
    nested_levels_seen = 0
    has_attribution = False
    subagent_turn_count = 0
    main_turn_count     = 0
    for pr in project_reports:
        share = _compute_subagent_share(pr)
        attributed_cost  += share["attributed_cost"]
        attributed_count += share["attributed_count"]
        spawn_count      += share["spawn_count"]
        orphan_turns     += share["orphan_turns"]
        cycles_detected  += share["cycles_detected"]
        nested_levels_seen = max(nested_levels_seen, share["nested_levels_seen"])
        has_attribution = has_attribution or share["has_attribution"]
        subagent_turn_count += int(share.get("subagent_turn_count", 0))
        main_turn_count     += int(share.get("main_turn_count", 0))
    share_pct = (100.0 * attributed_cost / total_cost) if total_cost > 0 else 0.0
    total_turn_count = main_turn_count + subagent_turn_count
    turn_share_pct = (
        100.0 * subagent_turn_count / total_turn_count
        if total_turn_count > 0 else 0.0
    )
    return {
        "include_subagents":  include_subagents,
        "has_attribution":    has_attribution,
        "total_cost":         total_cost,
        "attributed_cost":    attributed_cost,
        "share_pct":          share_pct,
        "spawn_count":        spawn_count,
        "attributed_count":   attributed_count,
        "orphan_turns":       orphan_turns,
        "cycles_detected":    cycles_detected,
        "nested_levels_seen": nested_levels_seen,
        "subagent_turn_count": subagent_turn_count,
        "main_turn_count":     main_turn_count,
        "total_turn_count":    total_turn_count,
        "turn_share_pct":      turn_share_pct,
    }


def _compute_window_stats(sessions: list[dict],
                            days_back: int | None,
                            now_epoch: int | None = None) -> dict:
    """Aggregate per-turn metrics across the trailing ``days_back`` window.

    Returns a stat dict with ``total_cost``, ``cache_hit_pct``, ``turns``,
    ``sessions``, ``top_model`` (model id with the highest cost in the
    window — empty string when the window is empty), and the ``label`` /
    ``days`` framing fields. ``days_back=None`` collapses the filter so the
    window covers the entire dataset (the "all time" column).

    Used by the multi-window dashboard ribbon (``_build_window_ribbon_html``)
    introduced for parity with cognitive-claude's ``--verbose`` 7d / 30d /
    90d / all-time ribbon. Cheap on warm parse-cache because it iterates
    already-loaded turn records — no re-parsing.
    """
    if now_epoch is None:
        now_epoch = int(datetime.now(timezone.utc).timestamp())
    cutoff = (now_epoch - days_back * 86400) if days_back else 0
    cost = 0.0
    cache_read = 0
    cache_write = 0
    new_input = 0
    turns = 0
    partial_hit_turns = 0
    total_cache_turns = 0
    session_ids: set[str] = set()
    model_cost: dict[str, float] = {}
    for s in sessions or []:
        sid = s.get("session_id") or ""
        for t in s.get("turns", []) or []:
            if t.get("is_resume_marker"):
                continue
            if days_back is not None:
                ts_iso = t.get("timestamp", "") or ""
                ts_epoch = _sm()._parse_iso_epoch(ts_iso) if ts_iso else 0
                if not ts_epoch or ts_epoch < cutoff:
                    continue
            turns += 1
            session_ids.add(sid)
            tc = float(t.get("cost_usd", 0.0))
            cost += tc
            cr = int(t.get("cache_read_tokens", 0) or 0)
            cw = int(t.get("cache_write_tokens", 0) or 0)
            cache_read  += cr
            cache_write += cw
            new_input   += int(t.get("input_tokens", 0) or 0)
            if cr > 0 or cw > 0:
                total_cache_turns += 1
            if cr > 0 and cw > 0:
                partial_hit_turns += 1
            mdl = t.get("model") or "unknown"
            model_cost[mdl] = model_cost.get(mdl, 0.0) + tc
    total_input = new_input + cache_read + cache_write
    cache_hit_pct = (100.0 * cache_read / total_input) if total_input > 0 else 0.0
    partial_hit_rate = round(100.0 * partial_hit_turns / max(1, total_cache_turns), 1)
    top_model = ""
    if model_cost:
        top_model = max(model_cost.items(), key=lambda kv: kv[1])[0]
    label = f"Last {days_back}d" if days_back else "All time"
    return {
        "label":         label,
        "days":          days_back,
        "total_cost":    cost,
        "cache_hit_pct": cache_hit_pct,
        "partial_hit_rate": partial_hit_rate,
        "partial_hit_turns": partial_hit_turns,
        "total_cache_turns": total_cache_turns,
        "turns":         turns,
        "sessions":      len(session_ids),
        "top_model":     top_model,
    }


def _median(values: list[float]) -> float:
    """Plain median for small lists (no numpy dependency).

    Used by the within-session split: outlier-resistant compared to mean,
    which matters because a single $0.20 turn distorts a session of
    $0.001-cost turns.
    """
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return 0.5 * (s[n // 2 - 1] + s[n // 2])


# ---------------------------------------------------------------------------
# Phase-B (v1.7.0): subagent → parent-prompt token attribution
# ---------------------------------------------------------------------------
#
# Roll subagent token usage onto the user prompt that spawned the subagent
# chain so the Prompts table reflects the *true* cost of an action ("a
# cheap-looking prompt that spawned a $1.20 Explore"). Implementation
# mirrors Anthropic's session-report 3-stage linkage but adapts to our
# post-load architecture:
#
#   Stage 1: ``tool_use.id → prompt_anchor_index`` (parent-side spawn)
#   Stage 2: ``agentId → prompt_anchor_index`` (via ``toolUseResult.agentId``)
#   Stage 3: roll subagent turns' tokens onto the resolved root prompt
#
# Key correction over Anthropic's reference: we use ``prompt_anchor_index``
# (the most recent turn whose ``prompt_text`` is non-empty) instead of the
# turn the spawn happens in. This avoids attribution landing on a turn
# that's invisible in the Prompts table (which filters on prompt_text).
# Nested chains resolve via iterative walk (no timestamp-sort dependency)
# with a cycle guard.


def _compute_prompt_anchor_indices(turn_records: list[dict]) -> None:
    """Forward pass: stamp ``prompt_anchor_index`` on every turn.

    The anchor is the index of the most recent turn (this one or earlier
    in chronological order) with non-empty ``prompt_text``. Subagent turns
    don't carry their own ``prompt_text`` and don't anchor for main-session
    rollup — they keep the most recent main-turn anchor that was seen.

    Mutates ``turn_records`` in place.
    """
    last_main_anchor: int | None = None
    for t in turn_records:
        # Subagent turns inherit the prior main-turn anchor (their own
        # ``prompt_text`` is "" by construction since the subagent JSONL
        # doesn't contain user prompts in the same shape).
        if t.get("subagent_agent_id"):
            t["prompt_anchor_index"] = (
                last_main_anchor if last_main_anchor is not None else t["index"]
            )
            continue
        if (t.get("prompt_text") or "").strip():
            last_main_anchor = t["index"]
        t["prompt_anchor_index"] = (
            last_main_anchor if last_main_anchor is not None else t["index"]
        )


def _attribute_subagent_tokens(turn_records: list[dict],
                               runid_to_tooluse: dict | None = None) -> dict:
    """Roll subagent token usage onto the user prompt that spawned them.

    Modifies the matching turn record in-place: increments
    ``attributed_subagent_tokens``, ``attributed_subagent_cost`` and
    ``attributed_subagent_count`` on the *root* main-turn for every
    subagent turn whose chain resolves back to a known parent.

    The new fields are purely additive: ``cost_usd`` and ``total_tokens``
    on every turn are unchanged, so ``_totals_from_turns`` and existing
    aggregators see the same values they did pre-attribution. Display
    layers read ``attributed_subagent_*`` separately.

    Algorithm (no timestamp-sort dependency, with cycle guard):

    Pass 1 — ``tool_use_id → prompt_anchor_index``:
        Walk *all* turns (main + subagent). For each turn with
        ``tool_use_ids``, every id maps to that turn's
        ``prompt_anchor_index`` — i.e., the user prompt this spawn
        belongs to. Subagent turns also contribute (nested case): their
        anchor is the parent-subagent's resolved root, populated by
        ``_compute_prompt_anchor_indices`` to the most recent main
        prompt.

    Pass 2 — ``agent_id → anchor_index``:
        Walk *all* turns. For every ``(tuid, agent_id)`` in
        ``agent_links``, look up the spawn's ``prompt_anchor_index``
        from pass 1 and record it under ``agent_id``.

    Pass 3 — roll up subagent tokens:
        For every turn whose ``subagent_agent_id`` is non-empty, look
        up ``agent_id_anchor[subagent_agent_id]`` to find the root
        main-turn index. If found, accumulate; if not, increment the
        orphan counter.

    Returns a summary dict with totals useful for sanity checks.
    """
    summary = {
        "attributed_turns":       0,
        "orphan_subagent_turns":  0,
        "nested_levels_seen":     0,
        "cycles_detected":        0,
    }
    if not turn_records:
        return summary

    # ``index`` may not equal list position (global_idx is reset across
    # sessions in _build_report). Build a position map so anchor lookup
    # is O(1) regardless.
    index_to_pos = {t["index"]: i for i, t in enumerate(turn_records)}

    # Pass 1: tool_use_id -> prompt_anchor_index.
    tool_use_to_anchor: dict[str, int] = {}
    for t in turn_records:
        if t.get("is_resume_marker"):
            continue
        anchor = t.get("prompt_anchor_index", t["index"])
        for tuid in (t.get("tool_use_ids") or []):
            if isinstance(tuid, str) and tuid:
                tool_use_to_anchor[tuid] = anchor

    # Pass 2: agent_id -> anchor_index.
    agent_id_to_anchor: dict[str, int] = {}
    for t in turn_records:
        for pair in (t.get("agent_links") or []):
            if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
                continue
            tuid, aid = pair[0], pair[1]
            if not (isinstance(tuid, str) and isinstance(aid, str) and tuid and aid):
                continue
            anchor = tool_use_to_anchor.get(tuid)
            if anchor is not None:
                agent_id_to_anchor[aid] = anchor

    # Pass 2b: runId -> anchor, for dynamic-workflow agents. They carry no
    # main-thread ``(tool_use_id, agentId)`` link (parentUuid is null), so the
    # agentId map above never resolves them. Instead we bridge through the
    # Workflow tool_result's ``runId`` -> its spawning ``tool_use_id`` (captured
    # in ``runid_to_tooluse``) -> the prompt anchor from Pass 1.
    runid_to_anchor: dict[str, int] = {}
    for rid, tuid in (runid_to_tooluse or {}).items():
        anchor = tool_use_to_anchor.get(tuid) if tuid else None
        if anchor is not None:
            runid_to_anchor[rid] = anchor

    # Pass 3: roll up subagent tokens onto root main turn.
    attributed_indices: set[int] = set()
    for t in turn_records:
        aid = t.get("subagent_agent_id") or ""
        if not aid:
            continue
        anchor = agent_id_to_anchor.get(aid)
        if anchor is None:
            # Dynamic-workflow agent: fall back to the run's spawning prompt.
            wf_run = t.get("workflow_run_id") or ""
            anchor = runid_to_anchor.get(wf_run) if wf_run else None
        if anchor is None:
            summary["orphan_subagent_turns"] += 1
            continue
        # Iterative resolve with cycle guard. The anchor from pass 1 is
        # already the prompt-anchor index of the spawning turn; if that
        # spawning turn was itself a subagent turn, we step up via its
        # own ``subagent_agent_id`` until we land on a main turn.
        visited: set[str] = {aid}
        depth = 1
        while True:
            pos = index_to_pos.get(anchor)
            if pos is None:
                break
            anchor_turn = turn_records[pos]
            parent_aid = anchor_turn.get("subagent_agent_id") or ""
            if not parent_aid:
                break  # reached a main-session turn — root found
            if parent_aid in visited:
                summary["cycles_detected"] += 1
                break
            visited.add(parent_aid)
            next_anchor = agent_id_to_anchor.get(parent_aid)
            if next_anchor is None:
                break  # orphan in chain — roll onto current anchor anyway
            anchor = next_anchor
            depth += 1
        # Accumulate onto the resolved root (or the deepest known anchor
        # if the chain orphans partway). The anchor is a main turn iff
        # we broke on the no-parent-aid branch above.
        pos = index_to_pos.get(anchor)
        if pos is None:
            summary["orphan_subagent_turns"] += 1
            continue
        target = turn_records[pos]
        target["attributed_subagent_tokens"] += int(t.get("total_tokens", 0))
        target["attributed_subagent_cost"]   += float(t.get("cost_usd", 0.0))
        target["attributed_subagent_count"]  += 1
        attributed_indices.add(target["index"])
        if depth > summary["nested_levels_seen"]:
            summary["nested_levels_seen"] = depth

    summary["attributed_turns"] = len(attributed_indices)
    return summary


def _build_report(
    mode: str,
    slug: str,
    sessions_raw: list[tuple[str, list[dict], list[int]]],
    tz_offset_hours: float = 0.0,
    tz_label: str = "UTC",
    peak: dict | None = None,
    suppress_model_compare_insight: bool = False,
    cache_break_threshold: int = _CACHE_BREAK_DEFAULT_THRESHOLD,
    subagent_attribution: bool = True,
    sort_prompts_by: str | None = None,
    include_subagents: bool = False,
    compaction_events_by_session: dict | None = None,
    workflow_journals_by_session: dict | None = None,
) -> dict:
    """Build a structured report dict from raw session data.

    Args:
        mode: ``"session"`` for single-session or ``"project"`` for all sessions.
        slug: Project slug derived from the working directory path.
        sessions_raw: List of ``(session_id, assistant_turns, user_epoch_secs)``
            triples in chronological order (oldest first).  ``assistant_turns``
            are raw JSONL entries for assistant messages; ``user_epoch_secs``
            are sorted UTC epoch-seconds for non-meta user entries.

    Returns:
        Report dict containing ``sessions`` (list), ``totals``, ``models``,
        and ``time_of_day`` (project-wide).  Each session entry also has its
        own ``time_of_day`` for per-session breakdowns.
    """
    sessions_out = []
    global_idx = 1
    attribution_summary = {
        "attributed_turns":      0,
        "orphan_subagent_turns": 0,
        "nested_levels_seen":    0,
        "cycles_detected":       0,
    }

    for session_id, raw_turns, user_ts in sessions_raw:
        turn_records = [_sm()._build_turn_record(global_idx + i, t, tz_offset_hours)
                        for i, t in enumerate(raw_turns)]
        global_idx += len(turn_records)
        # Phase-B (v1.7.0): subagent → parent-prompt attribution. Anchor
        # computation must precede attribution; both modify turn records
        # in place. Always-on by default; ``--no-subagent-attribution``
        # suppresses Pass 3's accumulation while still computing anchors
        # so other features (sort tie-breaks) keep working.
        _compute_prompt_anchor_indices(turn_records)
        if subagent_attribution:
            # runId → spawning tool_use_id for this session's workflows, so
            # workflow-agent turns (which orphan on the agentId path) can
            # roll up onto the prompt that launched the run.
            _wf_runs = (workflow_journals_by_session or {}).get(session_id, {})
            runid_to_tooluse = {
                rid: meta.get("spawn_tool_use_id")
                for rid, meta in (_wf_runs or {}).items()
                if isinstance(meta, dict) and meta.get("spawn_tool_use_id")
            }
            session_summary = _attribute_subagent_tokens(
                turn_records, runid_to_tooluse)
            for k, v in session_summary.items():
                if k == "nested_levels_seen":
                    attribution_summary[k] = max(attribution_summary[k], v)
                else:
                    attribution_summary[k] += v
        resumes = _build_resumes(turn_records)
        # Stamp `is_terminal_exit_marker` onto the last-turn marker (if any) so
        # the timeline divider can distinguish "user came back" from "user's
        # most recent /exit with no subsequent work in this JSONL". The
        # dashboard card already splits these in its sublabel; the timeline
        # needs the same distinction to stay internally consistent.
        for r in resumes:
            if r["terminal"]:
                idx = r["turn_index"]
                for t in turn_records:
                    if t["index"] == idx:
                        t["is_terminal_exit_marker"] = True
                        break
        # Raw epoch span — used by usage-insights (long_sessions, session_pacing).
        # Computed here while raw_turns is still in scope; the formatted
        # display strings would be brittle to re-parse for arithmetic.
        first_epoch = _sm()._parse_iso_epoch(raw_turns[0].get("timestamp", "")) if raw_turns else 0
        last_epoch  = _sm()._parse_iso_epoch(raw_turns[-1].get("timestamp", "")) if raw_turns else 0
        duration_seconds = (last_epoch - first_epoch) if (first_epoch and last_epoch and last_epoch > first_epoch) else 0
        # Wall-clock seconds (first user prompt → last assistant turn). Picks
        # up the initial pre-first-response wait that ``duration_seconds``
        # excludes — relevant for benchmark / headless ``claude -p`` runs
        # where prompt #1 lands at session start. Falls back to
        # ``duration_seconds`` when ``user_ts`` is empty (e.g. resumed
        # session whose first user entry was filtered out).
        first_user_epoch = user_ts[0] if user_ts else 0
        wall_clock_seconds = (
            (last_epoch - first_user_epoch)
            if (first_user_epoch and last_epoch and last_epoch > first_user_epoch)
            else duration_seconds
        )
        # advisorModel is stamped on every assistant JSONL entry when advisor
        # is configured for the session — read it once from the first match.
        advisor_configured_model: str | None = next(
            (t.get("advisorModel") for t in raw_turns if t.get("advisorModel")),
            None,
        )
        session_dict = {
            "session_id":              session_id,
            "first_ts":                _sm()._fmt_ts(raw_turns[0].get("timestamp", ""), tz_offset_hours) if raw_turns else "",
            "last_ts":                 _sm()._fmt_ts(raw_turns[-1].get("timestamp", ""), tz_offset_hours) if raw_turns else "",
            "duration_seconds":        duration_seconds,
            "wall_clock_seconds":      wall_clock_seconds,
            "turns":                   turn_records,
            "subtotal":                _sm()._totals_from_turns(turn_records),
            "models":                  _sm()._model_breakdown(turn_records),
            "time_of_day":             _sm()._build_time_of_day(user_ts, offset_hours=tz_offset_hours),
            "resumes":                 resumes,
            "advisor_configured_model": advisor_configured_model,
        }
        # Per-session phase-A aggregators: cache-breaks are intrinsically
        # session-scoped (a turn either breaks the cache in this session's
        # context or it doesn't). by_skill / by_subagent_type are computed
        # at both per-session and report scopes so either drilldown has a
        # self-consistent table when displayed in isolation.
        session_dict["cache_breaks"] = _sm()._detect_cache_breaks(
            session_dict, threshold=cache_break_threshold,
        )
        session_dict["by_skill"] = _sm()._build_by_skill(
            [session_dict], session_dict["subtotal"]["cost"],
        )
        session_dict["by_subagent_type"] = _sm()._build_by_subagent_type(
            [session_dict], session_dict["subtotal"]["cost"],
        )
        # Compaction events (Q1): threaded in via the caller's sink dict,
        # keyed by session_id. Default to empty so renderers can always
        # read the keys regardless of whether the caller supplied a sink.
        _comp = (compaction_events_by_session or {}).get(session_id) or {}
        session_dict["compaction_events"] = _comp.get("boundaries", []) or []
        session_dict["starts_with_summary"] = bool(_comp.get("starts_with_summary", False))
        # Q1c: correlate each boundary to the first not-yet-claimed real turn
        # that follows it (timestamp walk), so the HTML timeline can render a
        # "Context compacted" divider before that turn. Sourcing from the
        # canonical, deduped, subagent-excluded ``compaction_events`` (above) —
        # NOT a per-file stamp — means the rendered divider count can never
        # exceed ``compaction_summary["boundary_count"]`` even though boundaries
        # replay across sibling JSONLs. Both lists are timestamp-sorted, so this
        # is a single two-pointer pass; each boundary claims a distinct turn, so
        # back-to-back compactions don't collapse onto one row. A boundary with
        # no following turn (compaction at session end) stays unmapped → no
        # divider, but is still counted in the KPI card (divider_count ≤ N).
        _boundaries = sorted(
            session_dict["compaction_events"], key=lambda b: b.get("timestamp", ""),
        )
        _claimable = [t for t in turn_records if not t.get("is_resume_marker")]
        _ti = 0
        for _b in _boundaries:
            _bts = _b.get("timestamp", "")
            while _ti < len(_claimable) and _claimable[_ti].get("timestamp", "") <= _bts:
                _ti += 1
            if _ti < len(_claimable):
                _t = _claimable[_ti]
                _t["is_post_compaction"] = True
                _t["compaction_trigger"] = _b.get("trigger", "")
                _t["compaction_reclaimed_tokens"] = _b.get("reclaimed_tokens")
                _ti += 1
        # Q1c item 2: a session that opens on a compaction summary continues a
        # prior conversation whose boundary lives in a predecessor file. Mark
        # its first real turn so the timeline can show a "Continued from prior
        # conversation" pill (visually distinct from the in-session divider).
        if session_dict["starts_with_summary"]:
            for _t in turn_records:
                if not _t.get("is_resume_marker"):
                    _t["is_continued_from_prior"] = True
                    break
        sessions_out.append(session_dict)

    all_turns = [t for s in sessions_out for t in s["turns"]]
    all_user_ts = sorted(ts for _, _, uts in sessions_raw for ts in uts)
    blocks = _sm()._build_session_blocks(sessions_raw)
    # P4.4: fold per-session subtotals into the project-wide total via
    # `_sm()._add_totals` instead of re-iterating every turn through
    # `_sm()._totals_from_turns(all_turns)`. Each subtotal already carries the
    # additive state (and `_tool_name_counts`) needed to reconstruct an
    # identical total. Strip the internal `_tool_name_counts` from the
    # project total + each session subtotal before any renderer / JSON
    # exporter sees them.
    if sessions_out:
        totals = functools.reduce(
            _sm()._add_totals, (s["subtotal"] for s in sessions_out)
        )
    else:
        totals = _sm()._totals_from_turns([])
    totals.pop("_tool_name_counts", None)
    for s in sessions_out:
        s["subtotal"].pop("_tool_name_counts", None)
    report = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "skill_version":   _sm()._SKILL_VERSION,
        "mode":            mode,
        "slug":            slug,
        "tz_offset_hours": tz_offset_hours,
        "tz_label":        tz_label,
        "sessions":        sessions_out,
        "totals":          totals,
        "models":          _sm()._model_breakdown(all_turns),
        "time_of_day":     _sm()._build_time_of_day(all_user_ts, offset_hours=tz_offset_hours),
        "session_blocks":  blocks,
        "block_summary":   _sm()._weekly_block_counts(blocks),
        "weekly_rollup":   _sm()._build_weekly_rollup(sessions_out, sessions_raw, blocks),
        "peak":            peak,
        "resumes":         [r for s in sessions_out for r in s["resumes"]],
        # Phase-A cross-cutting tables (v1.6.0). All three are always
        # attached; renderers auto-hide when the list/dict is empty.
        "cache_breaks":        [cb for s in sessions_out for cb in s.get("cache_breaks", [])],
        # Q1: context-compaction events flattened across sessions + summary.
        # Renderers auto-hide when ``compaction_summary["boundary_count"]`` is 0.
        **dict(zip(
            ("compaction_events", "compaction_summary"),
            _build_compaction_summary(sessions_out),
        )),
        "by_skill":            _sm()._build_by_skill(sessions_out, totals.get("cost", 0.0)),
        "by_subagent_type":    _sm()._build_by_subagent_type(sessions_out, totals.get("cost", 0.0)),
        # Dynamic-workflow (Workflow tool) cost table — runId-keyed, cost from
        # transcripts, display metadata from the wf_<runId>.json journals.
        # Empty list when no workflows ran; renderers auto-hide.
        "by_workflow":         _sm()._build_by_workflow(
            sessions_out, totals.get("cost", 0.0),
            workflow_journals_by_session or {}),
        "cache_break_threshold": cache_break_threshold,
        # Phase-B (v1.7.0): subagent → parent-prompt attribution summary.
        # Renderers read ``attributed_subagent_*`` directly off turn
        # records; this top-level dict surfaces orphan/cycle counts +
        # nested-depth observed for footer + JSON consumers.
        "subagent_attribution_summary": attribution_summary,
        # User-requested prompt sort mode (or None = renderer default).
        # HTML/MD default to ``"total"`` (parent + attributed subagent
        # cost — bubbles up cheap-prompt-spawning-expensive-subagent
        # turns); CSV/JSON default to ``"self"`` (parent only) so
        # script consumers parsing the prior output ordering remain
        # stable. Value is preserved on the report dict so renderers
        # can do their own per-format defaulting.
        "sort_prompts_by": sort_prompts_by,
        # Whether the loader was invoked with --include-subagents.
        # Renderers read this to decide whether the Subagent-types table's
        # zero token columns mean "no spawns happened" vs "spawn-count
        # only · token data not loaded".
        "include_subagents": include_subagents,
        # CLI opt-out for the Phase 7 model-compare insight card. Keyed
        # with an underscore so downstream JSON exports don't leak the
        # flag into user-facing schema; `_compute_usage_insights` reads
        # it before returning the list.
        "_suppress_model_compare_insight": suppress_model_compare_insight,
    }
    # Self-cost meta-metric (v1.27.0): how much has session-metrics itself
    # cost in this session's JSONL? Always computed; renderers / dispatcher
    # honour --no-self-cost by stripping the field before display.
    report["self_cost"] = _sm()._summarize_self_cost(report["by_skill"])
    # Sort global cache_breaks by uncached desc to keep "worst-first" order.
    report["cache_breaks"].sort(key=lambda b: -int(b.get("uncached", 0)))
    # v1.26.0: precompute the headline subagent share + within-session
    # split. Stashing here means all renderers (HTML / MD / JSON / CSV)
    # read consistent values, and the JSON export carries them out of
    # the box without per-renderer wiring.
    report["subagent_share_stats"] = _compute_subagent_share(report)
    report["subagent_within_session_split"] = _compute_within_session_split(sessions_out)
    # Multi-window comparison ribbon (cognitive-claude inspired). Project-
    # scope only — single-session reports cover one window by definition,
    # so a 7/30/90 ribbon would be confusing. Cheap to compute on already-
    # parsed turn data.
    if mode == "project":
        report["window_stats"] = [
            _compute_window_stats(sessions_out, d) for d in (7, 30, 90, None)
        ]
    report["usage_insights"] = _sm()._compute_usage_insights(report)
    # v1.8.0: token-waste classification — runs after attribution + cache-break
    # detection (both mutate turn dicts in place); annotates turns with
    # turn_character / turn_character_label / turn_risk and attaches
    # the top-level waste_analysis summary dict.
    report["waste_analysis"] = _sm()._build_waste_analysis(sessions_out)
    # Per-request breakdown (deterministic task-grouping foundation): group
    # turns by (session_id, prompt_anchor_index) into "request units". Runs
    # last — after attribution + cache-break + waste passes have stamped
    # every turn — so each unit can aggregate cost, tokens, tool mix and
    # waste signals. Honest framing: per-utterance, NOT semantic tasks.
    report["request_units"] = _sm()._build_request_units(sessions_out)
    # Drop the internal flag after use so the report dict stays clean
    # for downstream renderers / JSON export.
    report.pop("_suppress_model_compare_insight", None)
    return report


def _build_resumes(turn_records: list[dict]) -> list[dict]:
    """Extract resume markers from per-session turn records.

    A resume marker is a turn flagged ``is_resume_marker=True`` by
    `_extract_turns` (synthetic no-op preceded by a `/exit` local-command
    replay in the last ~10 user entries). For each marker we compute the
    wall-clock gap to the previous assistant turn in the same session —
    the practical "away" time between the user's prior work and the
    resumed work. When the marker is the first turn in the session
    (prior-session context not observable from this file), gap is null.
    When the marker is the last turn in the session (user exited and did
    not return), ``terminal`` is True — render as an exit marker rather
    than a resume divider.

    Returns a list ordered by ``turn_index``; each entry is a dict with
    ``timestamp``, ``timestamp_fmt``, ``turn_index``, ``gap_seconds``,
    ``terminal``.
    """
    markers: list[dict] = []
    for i, t in enumerate(turn_records):
        if not t.get("is_resume_marker"):
            continue
        gap: float | None = None
        if i > 0:
            prev_dt = _sm()._parse_iso_dt(turn_records[i-1].get("timestamp", ""))
            cur_dt  = _sm()._parse_iso_dt(t.get("timestamp", ""))
            if prev_dt and cur_dt:
                try:
                    gap = (cur_dt - prev_dt).total_seconds()
                except (ValueError, AttributeError, TypeError, OSError):
                    gap = None
        terminal = (i == len(turn_records) - 1)
        markers.append({
            "timestamp":     t.get("timestamp", ""),
            "timestamp_fmt": t.get("timestamp_fmt", ""),
            "turn_index":    t.get("index"),
            "gap_seconds":   gap,
            "terminal":      terminal,
        })
    return markers

def _project_summary_from_report(project_report: dict) -> dict:
    """Condense a full ``_build_report(mode="project", ...)`` result into the
    lightweight summary that goes into ``instance_report["projects"]``.

    Per-turn records are dropped — they live inside the per-project
    drilldown HTML (rendered separately) so that the instance index stays
    small and the JSON/CSV exports are tractable.
    """
    slug = project_report["slug"]
    sessions = project_report["sessions"]
    totals = project_report["totals"]
    first_epoch = 0
    last_epoch = 0
    first_ts_fmt = ""
    last_ts_fmt = ""
    if sessions:
        first = sessions[0]
        last = sessions[-1]
        first_ts_fmt = first.get("first_ts", "")
        last_ts_fmt = last.get("last_ts", "")
        if first.get("turns"):
            first_epoch = _sm()._parse_iso_epoch(first["turns"][0].get("timestamp", ""))
        if last.get("turns"):
            last_epoch = _sm()._parse_iso_epoch(last["turns"][-1].get("timestamp", ""))
    session_summaries = []
    for s in sessions:
        session_summaries.append({
            "session_id":       s["session_id"],
            "first_ts":         s.get("first_ts", ""),
            "last_ts":          s.get("last_ts", ""),
            "duration_seconds": s.get("duration_seconds", 0),
            "turn_count":       len(s.get("turns", [])),
            "subtotal":         s.get("subtotal", {}),
            "models":           s.get("models", {}),
        })
    duration_seconds = 0
    if first_epoch and last_epoch and last_epoch > first_epoch:
        duration_seconds = last_epoch - first_epoch
    return {
        "slug":             slug,
        "friendly_path":    _sm()._slug_to_friendly_path(slug),
        "session_count":    len(sessions),
        "turn_count":       totals.get("turns", 0),
        "first_ts":         first_ts_fmt,
        "last_ts":          last_ts_fmt,
        "first_epoch":      first_epoch,
        "last_epoch":       last_epoch,
        "duration_seconds": duration_seconds,
        "totals":           totals,
        "models":           project_report.get("models", {}),
        "cost_usd":         float(totals.get("cost", 0.0)),
        "sessions":         session_summaries,
        "waste_dist":       (project_report.get("waste_analysis") or {}).get("distribution") or {},
    }


def _build_instance_daily(project_reports: list[dict],
                          tz_offset_hours: float,
                          top_n: int = 10) -> tuple[list[dict], list[str]]:
    """Aggregate per-turn cost into daily buckets, attributed by project.

    Returns ``(daily, top_slugs)`` where ``daily`` is a list of
    ``{date, cost, tokens, input, output, cache_read, cache_write,
    by_project: {slug: cost_usd}}`` dicts sorted oldest-first, and
    ``top_slugs`` is the slug list that the instance chart stacks
    (all other projects are rolled into an "other" series by the renderer).

    The four per-token subcategories (``input`` / ``output`` / ``cache_read``
    / ``cache_write``) are tracked separately so the instance daily-cost
    chart can feed a real stacked-bar breakdown to the chart renderer,
    rather than flatlining those four series at 0 (the pre-v1.14.1 bug).
    """
    buckets: dict[str, dict] = {}
    project_cost: dict[str, float] = {}
    shift = timedelta(hours=tz_offset_hours)
    for pr in project_reports:
        slug = pr["slug"]
        for s in pr["sessions"]:
            for t in s.get("turns", []):
                ts = t.get("timestamp", "")
                dt = _sm()._parse_iso_dt(ts)
                if not dt:
                    continue
                local = (dt + shift).date().isoformat()
                cost = float(t.get("cost_usd", 0.0))
                tokens = int(t.get("total_tokens", 0))
                b = buckets.setdefault(local, {
                    "date": local, "cost": 0.0, "tokens": 0,
                    "input": 0, "output": 0,
                    "cache_read": 0, "cache_write": 0,
                    "by_project": {},
                })
                b["cost"] += cost
                b["tokens"] += tokens
                b["input"]       += int(t.get("input_tokens", 0) or 0)
                b["output"]      += int(t.get("output_tokens", 0) or 0)
                b["cache_read"]  += int(t.get("cache_read_tokens", 0) or 0)
                b["cache_write"] += int(t.get("cache_write_tokens", 0) or 0)
                b["by_project"][slug] = b["by_project"].get(slug, 0.0) + cost
                project_cost[slug] = project_cost.get(slug, 0.0) + cost
    daily = sorted(buckets.values(), key=lambda x: x["date"])
    top_slugs = [s for s, _ in sorted(project_cost.items(),
                                       key=lambda kv: kv[1], reverse=True)[:top_n]]
    return daily, top_slugs


def _aggregate_totals(project_reports: list[dict]) -> dict:
    """Sum per-project ``totals`` dicts into one instance-wide total."""
    keys = ["input", "output", "cache_read", "cache_write",
            "cache_write_5m", "cache_write_1h", "extra_1h_cost",
            "cost", "no_cache_cost", "turns",
            "advisor_call_count", "advisor_cost_usd"]
    out: dict = {k: 0 for k in keys}
    out["cost"] = 0.0
    out["no_cache_cost"] = 0.0
    out["extra_1h_cost"] = 0.0
    out["advisor_cost_usd"] = 0.0
    content_blocks = {"thinking": 0, "tool_use": 0, "text": 0,
                      "tool_result": 0, "image": 0}
    thinking_turn_count = 0
    name_counts: dict[str, int] = {}
    for pr in project_reports:
        t = pr.get("totals", {})
        for k in keys:
            out[k] = out.get(k, 0) + t.get(k, 0)
        cb = t.get("content_blocks") or {}
        for k, v in cb.items():
            content_blocks[k] = content_blocks.get(k, 0) + int(v or 0)
        thinking_turn_count += t.get("thinking_turn_count", 0)
        tun = t.get("tool_use_names") or {}
        for name, n in tun.items():
            name_counts[name] = name_counts.get(name, 0) + n
    if any(v for v in content_blocks.values()):
        out["content_blocks"] = content_blocks
    if thinking_turn_count:
        out["thinking_turn_count"] = thinking_turn_count
    if name_counts:
        out["tool_use_names"] = name_counts
    return out


def _aggregate_models(project_reports: list[dict]) -> dict:
    """Build a per-model breakdown across every project in the instance.

    Per-project ``models`` dicts produced by ``_build_report`` are simple
    ``{name: turn_count}`` maps (matches what the project-mode renderer
    expects). For the instance dashboard we want richer per-model stats
    (tokens + cost) so we walk each project's already-built turn records
    and accumulate the breakdown here. Pricing rates are attached via
    ``_pricing_for`` so the HTML models table can render rate columns
    without needing to re-run cost math.
    """
    merged: dict[str, dict] = {}
    for pr in project_reports:
        for s in pr.get("sessions", []):
            for t in s.get("turns", []):
                name = t.get("model", "unknown")
                m = merged.setdefault(name, {
                    "turns":              0,
                    "input_tokens":       0,
                    "output_tokens":      0,
                    "cache_read_tokens":  0,
                    "cache_write_tokens": 0,
                    "cache_write_5m_tokens": 0,
                    "cache_write_1h_tokens": 0,
                    "cost_usd":           0.0,
                })
                m["turns"]              += 1
                m["input_tokens"]       += int(t.get("input_tokens", 0))
                m["output_tokens"]      += int(t.get("output_tokens", 0))
                m["cache_read_tokens"]  += int(t.get("cache_read_tokens", 0))
                m["cache_write_tokens"] += int(t.get("cache_write_tokens", 0))
                m["cache_write_5m_tokens"] += int(t.get("cache_write_5m_tokens", 0))
                m["cache_write_1h_tokens"] += int(t.get("cache_write_1h_tokens", 0))
                m["cost_usd"]           += float(t.get("cost_usd", 0.0))
    return merged


def _merge_bucket_rows(project_reports: list[dict], key: str,
                        total_cost: float) -> list[dict]:
    """Merge per-project ``by_skill`` / ``by_subagent_type`` lists into a
    single instance-level list. Token counters and ``spawn_count`` /
    ``invocations`` / ``turns_attributed`` sum; ``session_count`` and the
    derived pct/cache-hit fields are recomputed from the sums.
    """
    merged: dict[str, dict] = {}
    session_accumulator: dict[str, set] = {}
    for pr in project_reports:
        for row in pr.get(key, []) or []:
            name = row.get("name", "")
            if not name:
                continue
            m = merged.setdefault(name, {
                "name": name,
                "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
                "total_tokens": 0, "cost_usd": 0.0,
                "turns_attributed": 0,
            })
            # Sum numeric counters generically.
            for field in ("input", "output", "cache_read", "cache_write",
                           "total_tokens", "turns_attributed", "invocations",
                           "spawn_count"):
                if field in row:
                    m[field] = m.get(field, 0) + int(row.get(field, 0) or 0)
            m["cost_usd"] = float(m.get("cost_usd", 0.0)) + float(row.get("cost_usd", 0.0))
            # Sessions are recomputed from summed session_count (best-effort
            # — we treat each project's session_count as independent because
            # project slugs partition session IDs).
            session_accumulator.setdefault(name, set())
            # Proxy: each project contributes at most session_count rows.
            sc = int(row.get("session_count", 0) or 0)
            if sc:
                # synth placeholder so len() matches total (deduped within
                # a project; across projects the union over namespaces is
                # the sum since slugs are disjoint).
                for i in range(sc):
                    session_accumulator[name].add(f"{pr.get('slug', '?')}::{i}")
    out: list[dict] = []
    for name, m in merged.items():
        m["session_count"] = len(session_accumulator.get(name, set()))
        total_input_side = (m["input"] + m["cache_read"] + m["cache_write"]) or 1
        m["cache_hit_pct"] = round(100.0 * m["cache_read"] / total_input_side, 1)
        m["pct_total_cost"] = (
            round(100.0 * m["cost_usd"] / total_cost, 2) if total_cost else 0.0
        )
        if "spawn_count" in m or key == "by_subagent_type":
            calls_for_avg = m.get("spawn_count", 0) or m.get("turns_attributed", 0) or 1
            m["avg_tokens_per_call"] = round(m.get("total_tokens", 0) / calls_for_avg, 1)
        out.append(m)
    out.sort(key=lambda r: -(r.get("cost_usd", 0.0) or r.get("total_tokens", 0) or r.get("spawn_count", 0)))
    return out


def _aggregate_attribution_summary(project_reports: list[dict]) -> dict:
    """Sum per-project Phase-B attribution summaries (counts add; nested
    depth maxes). Stable shape across modes so renderers don't branch."""
    out = {
        "attributed_turns":      0,
        "orphan_subagent_turns": 0,
        "nested_levels_seen":    0,
        "cycles_detected":       0,
    }
    for pr in project_reports:
        s = pr.get("subagent_attribution_summary") or {}
        for k in out:
            v = int(s.get(k, 0) or 0)
            if k == "nested_levels_seen":
                out[k] = max(out[k], v)
            else:
                out[k] += v
    return out


def _build_instance_report(
        project_reports: list[dict],
        all_sessions_raw: list[tuple[str, list[dict], list[int]]],
        tz_offset_hours: float,
        tz_label: str,
        projects_dir: Path,
        peak: dict | None = None,
        cache_break_threshold: int = _CACHE_BREAK_DEFAULT_THRESHOLD) -> dict:
    """Assemble the instance-wide report from per-project reports.

    Strategy: reuse ``_build_report(mode="project")`` for each project (done
    by the caller) to get full turn records, then flatten everything into a
    single virtual "project" to feed ``_build_time_of_day``,
    ``_build_weekly_rollup``, ``_build_session_blocks`` — they already work
    on lists of sessions, so we get identical rendering behaviour for free.
    Finally we strip per-turn payloads from the top-level ``projects`` list
    to keep the in-memory / JSON / CSV output bounded.

    ``all_sessions_raw`` is the concatenation of the ``sessions_raw`` tuples
    loaded per-project — shape ``(session_id, raw_turns, user_ts)``, same
    as what ``_build_report`` consumes. We need the raw JSONL entries (not
    the post-processed turn records) because ``_build_session_blocks``
    reaches into each raw turn's ``message.usage`` for token tallies.
    """
    # Collect per-project summaries (no turns)
    projects: list[dict] = []
    for pr in project_reports:
        projects.append(_project_summary_from_report(pr))
    # Sort by cost descending (matches plan: highest-spend first)
    projects.sort(key=lambda p: p["cost_usd"], reverse=True)

    # Flatten post-processed sessions for _build_weekly_rollup (it reads
    # per-session summary data, not raw entries, so the ``sessions`` lists
    # already produced by _build_report are the right input here).
    all_sessions_out = []
    for pr in project_reports:
        for s in pr["sessions"]:
            all_sessions_out.append(s)

    # Collect user-prompt timestamps across all projects so the instance
    # time_of_day / hour-of-day / punchcard charts reflect actual user
    # activity, not just assistant turns.
    all_user_ts: list[int] = sorted(
        ts for _, _, uts in all_sessions_raw for ts in uts
    )

    blocks = _sm()._build_session_blocks(all_sessions_raw)
    totals = _aggregate_totals(project_reports)
    models = _aggregate_models(project_reports)
    # Re-price models with a rates key if missing, using _pricing_for
    for model, info in models.items():
        if "rates" not in info:
            info["rates"] = _sm()._pricing_for(model)

    daily, top_slugs = _build_instance_daily(project_reports,
                                              tz_offset_hours=tz_offset_hours)

    total_cost_for_pct = float(totals.get("cost", 0.0))
    # Aggregated phase-A tables across projects.
    inst_by_skill = _merge_bucket_rows(project_reports, "by_skill",
                                         total_cost_for_pct)
    inst_by_subagent = _merge_bucket_rows(project_reports, "by_subagent_type",
                                            total_cost_for_pct)
    # Dynamic-workflow rows are keyed by globally-unique ``runId`` (each
    # workflow run lives in exactly one session/project), so instance-scope
    # merge is a concatenation — no cross-project key collisions. We keep the
    # rich per-row metadata (phases, agent_details, status) the generic
    # name-keyed merger would drop, and just re-base ``pct_total_cost`` on the
    # instance total + tag each row with its project for the drilldown.
    inst_by_workflow: list[dict] = []
    for pr in project_reports:
        pr_slug = pr.get("slug", "")
        for row in pr.get("by_workflow", []) or []:
            tagged = dict(row)
            tagged["project"] = pr_slug
            tagged["pct_total_cost"] = (
                round(100.0 * float(tagged.get("cost_usd", 0.0)) / total_cost_for_pct, 2)
                if total_cost_for_pct else 0.0
            )
            inst_by_workflow.append(tagged)
    inst_by_workflow.sort(key=lambda r: -float(r.get("cost_usd", 0.0)))
    inst_cache_breaks: list[dict] = []
    for pr in project_reports:
        pr_slug = pr.get("slug", "")
        for cb in pr.get("cache_breaks", []) or []:
            tagged = dict(cb)
            tagged["project"] = pr_slug
            inst_cache_breaks.append(tagged)
    inst_cache_breaks.sort(key=lambda b: -int(b.get("uncached", 0)))

    # Q1: roll up per-project compaction events + summaries to instance scope.
    # Each project report already carries both (from _build_report); we tag
    # events with their project and sum the summary counters.
    inst_compaction_events: list[dict] = []
    inst_compaction_summary = {
        "boundary_count": 0, "auto_count": 0, "manual_count": 0,
        "unknown_trigger_count": 0, "total_reclaimed_tokens": 0,
        "total_pre_tokens": 0, "total_post_tokens": 0,
        "sessions_with_compaction": 0, "continuation_session_count": 0,
    }
    for pr in project_reports:
        pr_slug = pr.get("slug", "")
        for ev in pr.get("compaction_events", []) or []:
            tagged = dict(ev)
            tagged["project"] = pr_slug
            inst_compaction_events.append(tagged)
        cs = pr.get("compaction_summary") or {}
        for k in inst_compaction_summary:
            inst_compaction_summary[k] += int(cs.get(k, 0) or 0)

    report = {
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "skill_version":    _sm()._SKILL_VERSION,
        "mode":             "instance",
        "slug":             "all-projects",
        "projects_dir":     str(projects_dir),
        "tz_offset_hours":  tz_offset_hours,
        "tz_label":         tz_label,
        "projects":         projects,
        "project_count":    len(projects),
        "session_count":    sum(p["session_count"] for p in projects),
        "totals":           totals,
        "models":           models,
        "time_of_day":      _sm()._build_time_of_day(all_user_ts,
                                                offset_hours=tz_offset_hours),
        "session_blocks":   blocks,
        "block_summary":    _sm()._weekly_block_counts(blocks),
        "weekly_rollup":    _sm()._build_weekly_rollup(all_sessions_out,
                                                  all_sessions_raw,
                                                  blocks),
        "peak":             peak,
        "daily":            daily,
        "top_project_slugs": top_slugs,
        "cache_breaks":        inst_cache_breaks,
        "compaction_events":   inst_compaction_events,
        "compaction_summary":  inst_compaction_summary,
        "by_skill":            inst_by_skill,
        "by_subagent_type":    inst_by_subagent,
        "by_workflow":         inst_by_workflow,
        "cache_break_threshold": cache_break_threshold,
        # Phase-B (v1.7.0): instance-wide attribution summary — sum
        # per-project counts; max nested depth observed across all
        # projects. Each project's per-turn ``attributed_subagent_*``
        # already lives on the per-project sessions/turns and renders
        # via the project drilldown — no instance-level aggregation
        # needed beyond the summary footer.
        "subagent_attribution_summary": _aggregate_attribution_summary(project_reports),
        # v1.26.0: precomputed instance-level subagent share + within-
        # session split. ``sessions`` is intentionally an empty list at
        # this scope (per-turn payloads are stripped to keep JSON/CSV
        # exports bounded), so the renderers can't recompute these on
        # demand. They're rolled up here once and cached on the report.
        "subagent_share_stats": _compute_instance_subagent_share(
            project_reports, totals,
            include_subagents=any(pr.get("include_subagents") for pr in project_reports),
        ),
        "subagent_within_session_split": _compute_within_session_split(all_sessions_out),
        # Multi-window comparison ribbon at instance scope. Reads the
        # flattened ``all_sessions_out`` (preserved above for the
        # within-session split) so we don't lose access to per-turn
        # timestamps when ``sessions`` is later set to ``[]``.
        "window_stats": [
            _compute_window_stats(all_sessions_out, d) for d in (7, 30, 90, None)
        ],
        # Placeholders so the existing renderers don't KeyError if they
        # reach into the report looking for these.
        "sessions":         [],
        "resumes":          [],
        "usage_insights":   [],
        # ``include_subagents`` propagated up so the by_subagent_type
        # and headline renderers know whether to show "attribution
        # disabled" framing in instance scope.
        "include_subagents": any(pr.get("include_subagents") for pr in project_reports),
    }
    return report

