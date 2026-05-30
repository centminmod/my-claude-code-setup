"""Text, CSV, and Markdown rendering helpers for session-metrics."""
import csv as csv_mod
import io
import sys
from datetime import datetime, timedelta, timezone

from _dt import _parse_iso_dt


def _sm():
    """Return the session_metrics module (deferred — fully loaded by call time)."""
    return sys.modules["session_metrics"]


COL  = "{:<4} {:<19} {:>11} {:>7} {:>9} {:>9} {:>10} {:>9}"
# Optional suffix columns: Mode (fast mode), Content (per-turn block distribution)
_COL_MODE_SUFFIX    = "  {:<4}"
_COL_CONTENT_SUFFIX = "  {:<15}"
COL_M  = COL + _COL_MODE_SUFFIX  # retained for back-compat


def _text_format(show_mode: bool, show_content: bool) -> str:
    """Assemble the text-row format string with optional trailing columns."""
    fmt = COL
    if show_mode:
        fmt += _COL_MODE_SUFFIX
    if show_content:
        fmt += _COL_CONTENT_SUFFIX
    return fmt


def _text_table_headers(tz_offset_hours: float = 0.0,
                         show_mode: bool = False,
                         show_content: bool = False) -> tuple[str, str, str]:
    """Return (hdr, sep, wide) for the text timeline table in the given tz."""
    time_col = f"Time ({_short_tz_label(tz_offset_hours)})"
    fmt = _text_format(show_mode, show_content)
    args = ["#", time_col, "Input (new)", "Output",
            "CacheRd", "CacheWr", "Total", "Cost $"]
    if show_mode:
        args.append("Mode")
    if show_content:
        args.append("Content")
    hdr = fmt.format(*args)
    return hdr, "-" * len(hdr), "=" * len(hdr)


def _report_has_any(report: dict, predicate) -> bool:
    """Return True if any turn across any session matches ``predicate``."""
    return any(predicate(t) for s in report["sessions"] for t in s["turns"])


def _has_fast(report: dict) -> bool:
    """Return True if any turn in the report used fast mode."""
    return _report_has_any(report, lambda t: t.get("speed") == "fast")


def _has_1h_cache(report: dict) -> bool:
    """Return True if any turn used the 1-hour cache TTL tier."""
    return _report_has_any(report, lambda t: t.get("cache_write_1h_tokens", 0) > 0)


def _has_thinking(report: dict) -> bool:
    """Return True if any turn carried at least one thinking block."""
    return _report_has_any(
        report, lambda t: (t.get("content_blocks") or {}).get("thinking", 0) > 0
    )


def _has_tool_use(report: dict) -> bool:
    """Return True if any turn carried at least one tool_use block."""
    return _report_has_any(
        report, lambda t: (t.get("content_blocks") or {}).get("tool_use", 0) > 0
    )


def _has_content_blocks(report: dict) -> bool:
    """Return True if any turn carried any content block of any type.

    Drives conditional rendering of the Content column so legacy reports
    (or empty fixtures) stay visually unchanged.
    """
    def _any_nonzero(t):
        cb = t.get("content_blocks") or {}
        return any(v > 0 for v in cb.values())
    return _report_has_any(report, _any_nonzero)


def _fmt_generated_at(report: dict) -> str:
    """Format ``report["generated_at"]`` in the report's display tz.

    Falls back to a UTC-suffixed string when the timestamp can't be
    parsed or shifted (preserves the prior bare-except behavior of the
    two markdown/HTML render sites this consolidates).
    """
    raw = report.get("generated_at", "")
    tz_offset = report.get("tz_offset_hours", 0.0)
    fallback = raw[:19].replace("T", " ") + " UTC"
    dt = _parse_iso_dt(raw)
    if dt is None:
        return fallback
    try:
        local = dt.astimezone(timezone(timedelta(hours=tz_offset)))
        return local.strftime("%Y-%m-%d %H:%M:%S") + f" {_short_tz_label(tz_offset)}"
    except (ValueError, OverflowError, OSError):
        return fallback


def _short_tz_label(offset_hours: float) -> str:
    if offset_hours == 0:
        return "UTC"
    sign = "+" if offset_hours > 0 else "-"
    return f"UTC{sign}{abs(offset_hours):g}"


def _fmt_epoch_local(epoch: int, offset_hours: float = 0.0,
                     fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format an integer epoch in the given UTC offset."""
    offset_sec = int(offset_hours * 3600)
    return datetime.fromtimestamp(
        epoch + offset_sec, tz=timezone.utc,
    ).strftime(fmt)


def _fmt_cwr_row(t: dict) -> str:
    """Per-turn CacheWr cell. Appends `*` when the turn used 1h-tier cache."""
    n = t["cache_write_tokens"]
    if t.get("cache_write_ttl") in ("1h", "mix"):
        return f"{n:>8,}*"
    return f"{n:>9,}"


def _fmt_cwr_subtotal(s: dict) -> str:
    """Subtotal/total CacheWr cell. `*` when any 1h tokens are in the sum."""
    n = s.get("cache_write", 0)
    if s.get("cache_write_1h", 0) > 0:
        return f"{n:>8,}*"
    return f"{n:>9,}"


def _row_text(t: dict, show_mode: bool = False,
              show_content: bool = False) -> str:
    fmt = _text_format(show_mode, show_content)
    args = [
        t["index"], t["timestamp_fmt"],
        f"{t['input_tokens']:>7,}", f"{t['output_tokens']:>7,}",
        f"{t['cache_read_tokens']:>9,}", _fmt_cwr_row(t),
        f"{t['total_tokens']:>10,}",
        f"${t['cost_usd']:>8.4f}",
    ]
    if show_mode:
        spd = t.get("speed", "")
        args.append("fast" if spd == "fast" else "std")
    if show_content:
        args.append(_sm()._fmt_content_cell(t.get("content_blocks") or {}))
    return fmt.format(*args)


def _subtotal_text(label: str, s: dict, show_mode: bool = False,
                   show_content: bool = False) -> str:
    fmt = _text_format(show_mode, show_content)
    args = [
        label, "",
        f"{s['input']:>7,}", f"{s['output']:>7,}",
        f"{s['cache_read']:>9,}", _fmt_cwr_subtotal(s),
        f"{s['total']:>10,}",
        f"${s['cost']:>8.4f}",
    ]
    if show_mode:
        args.append("")
    if show_content:
        args.append("")
    return fmt.format(*args)


def _text_legend(tz_label: str, show_mode: bool, show_ttl: bool,
                 show_content: bool = False) -> str:
    """Build the column legend emitted above the timeline table."""
    rows = [
        ("#",       "deduplicated turn index"),
        ("Time",    f"turn start, local tz ({tz_label})"),
    ]
    if show_mode:
        rows.append(("Mode",  "fast / standard (only shown when fast mode was used)"))
    rows.extend([
        ("Input",   "net new input tokens (uncached)"),
        ("Output",  "generated tokens (includes thinking + tool_use block tokens)"),
        ("CacheRd", "tokens read from cache (cheap)"),
    ])
    if show_ttl:
        rows.append(("CacheWr", "tokens written to cache; `*` = includes 1h-tier (see footer)"))
    else:
        rows.append(("CacheWr", "tokens written to cache (one-time)"))
    rows.extend([
        ("Total",   "sum of the four billable token buckets"),
        ("Cost $",  "estimated USD for this turn"),
    ])
    if show_content:
        rows.append((
            "Content",
            "content blocks per turn: T thinking, u tool_use, x text, "
            "r tool_result, i image, v server_tool_use, R advisor_tool_result (zeros omitted)",
        ))
    w = max(len(k) for k, _ in rows)
    lines = ["Columns:"] + [f"  {k:<{w}}  {v}" for k, v in rows]
    return "\n".join(lines)


def render_text(report: dict, quiet: bool = False) -> str:
    """Render the plain-text report to a string.

    When ``quiet`` is set, the per-turn timeline (and, in project mode, the
    whole per-session loop) is suppressed — only the legend, scope header,
    grand-total subtotal, and footer are emitted. This keeps stdout
    O(1) in turn/session count so large project/session exports don't
    overflow the harness output cap (the useful ``[export]`` path lines,
    printed separately by the dispatcher, stay visible). Used by
    ``--quiet`` / export runs where the per-turn detail lives in the
    written HTML/JSON anyway.
    """
    if report.get("mode") == "compare":
        return sys.modules["session_metrics_compare"].render_compare_text(report)
    if report.get("mode") == "instance":
        return _sm()._render_instance_text(report)
    out = io.StringIO()

    def p(*args, **kw):
        print(*args, **kw, file=out)

    sessions = report["sessions"]

    m = _has_fast(report)
    has_1h = _has_1h_cache(report)
    has_content = _has_content_blocks(report)
    tz_offset = report.get("tz_offset_hours", 0.0)
    tz_label = report.get("tz_label", "UTC")
    hdr, sep, wide = _text_table_headers(tz_offset, show_mode=m,
                                          show_content=has_content)

    p(_text_legend(tz_label, show_mode=m, show_ttl=has_1h,
                    show_content=has_content))
    p()

    if report["mode"] == "project":
        p(f"Project: {report['slug']}")
        p(f"Sessions with data: {len(sessions)}")
        if quiet:
            p("  (per-session and per-turn detail suppressed by --quiet; "
              "see the HTML/JSON export)")
        p()
        if not quiet:
            for i, s in enumerate(sessions, 1):
                p(wide)
                _adv_n = s["subtotal"].get("advisor_call_count", 0)
                _adv_tag = ""
                if _adv_n > 0:
                    _adv_c = s["subtotal"].get("advisor_cost_usd", 0.0)
                    _adv_m = s.get("advisor_configured_model") or ""
                    _adv_label = f" · {_adv_m}" if _adv_m else ""
                    _adv_tag = f"  [advisor: {_adv_n} call{'s' if _adv_n != 1 else ''}{_adv_label} · +${_adv_c:.4f}]"
                p(f"  Session {s['session_id'][:8]}…  {s['first_ts']} → {s['last_ts']}  ({len(s['turns'])} turns){_adv_tag}")
                p(wide)
                p(hdr)
                for t in s["turns"]:
                    p(_row_text(t, m, has_content))
                p(sep)
                p(_subtotal_text(f"S{i:02}", s["subtotal"], m, has_content))
                p()
        p(wide)
        p(f"  PROJECT TOTAL — {len(sessions)} session{'s' if len(sessions) != 1 else ''}, {report['totals']['turns']} turns")
        p(wide)
        p(hdr)
        p(sep)
        p(_subtotal_text("TOT", report["totals"], m, has_content))
    else:
        s = sessions[0]
        p(hdr)
        if not quiet:
            for t in s["turns"]:
                p(_row_text(t, m, has_content))
        p(sep)
        p(_subtotal_text("TOT", s["subtotal"], m, has_content))

    p(_sm()._footer_text(report["totals"], report["models"], report.get("time_of_day"),
                    tz_label=report.get("tz_label", "UTC"),
                    session_blocks=report.get("session_blocks"),
                    block_summary=report.get("block_summary")))
    return out.getvalue()
def render_csv(report: dict) -> str:
    """Render turn-level CSV with an appended time-of-day summary section.

    The first section contains one row per assistant turn (unchanged).
    A blank separator row is followed by a ``USER ACTIVITY BY TIME OF DAY``
    summary with per-session and project-wide counts bucketed at UTC.
    """
    if report.get("mode") == "compare":
        return sys.modules["session_metrics_compare"].render_compare_csv(report)
    if report.get("mode") == "instance":
        return _sm()._render_instance_csv(report)
    out = io.StringIO()
    w = csv_mod.writer(out)
    w.writerow([f"# Session Metrics skill v{report.get('skill_version', '?')}",
                report.get("generated_at", ""), report.get("mode", "")])
    w.writerow(["session_id", "turn", "timestamp", "model", "speed",
                "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
                "cache_write_5m_tokens", "cache_write_1h_tokens", "cache_write_ttl",
                "total_tokens", "cost_usd", "no_cache_cost_usd",
                "thinking_blocks", "tool_use_blocks", "text_blocks",
                "tool_result_blocks", "image_blocks",
                # Phase-B (v1.7.0) attribution columns. Always emitted so
                # column count is stable across reports; values are 0 on
                # turns that didn't spawn a subagent (the common case).
                "attributed_subagent_tokens", "attributed_subagent_cost",
                "attributed_subagent_count",
                "stop_reason", "is_cache_break",
                "turn_character", "turn_character_label", "turn_risk"])
    for s in report["sessions"]:
        for t in s["turns"]:
            cb = t.get("content_blocks") or {}
            w.writerow([
                s["session_id"], t["index"], t["timestamp"], t["model"],
                t.get("speed", ""),
                t["input_tokens"], t["output_tokens"],
                t["cache_read_tokens"], t["cache_write_tokens"],
                t.get("cache_write_5m_tokens", 0),
                t.get("cache_write_1h_tokens", 0),
                t.get("cache_write_ttl", ""),
                t["total_tokens"],
                f"{t['cost_usd']:.6f}", f"{t['no_cache_cost_usd']:.6f}",
                cb.get("thinking", 0), cb.get("tool_use", 0),
                cb.get("text", 0), cb.get("tool_result", 0),
                cb.get("image", 0),
                t.get("attributed_subagent_tokens", 0),
                f"{float(t.get('attributed_subagent_cost', 0.0)):.6f}",
                t.get("attributed_subagent_count", 0),
                t.get("stop_reason", ""),
                t.get("is_cache_break", False),
                t.get("turn_character", ""),
                t.get("turn_character_label", ""),
                t.get("turn_risk", False),
            ])

    # Time-of-day summary section
    tz_label = report.get("tz_label", "UTC")
    w.writerow([])
    w.writerow([f"# USER ACTIVITY BY TIME OF DAY ({tz_label})"])
    w.writerow(["scope", "id", "night_0_6", "morning_6_12",
                "afternoon_12_18", "evening_18_24", "total"])
    for s in report["sessions"]:
        tod = s.get("time_of_day", {})
        b = tod.get("buckets", {})
        w.writerow(["session", s["session_id"],
                     b.get("night", 0), b.get("morning", 0),
                     b.get("afternoon", 0), b.get("evening", 0),
                     tod.get("message_count", 0)])
    tod = report.get("time_of_day", {})
    b = tod.get("buckets", {})
    w.writerow(["project", report["slug"],
                 b.get("night", 0), b.get("morning", 0),
                 b.get("afternoon", 0), b.get("evening", 0),
                 tod.get("message_count", 0)])

    # Hour-of-day section (project-wide)
    hod = tod.get("hour_of_day")
    if hod and hod.get("total", 0) > 0:
        w.writerow([])
        w.writerow([f"# HOUR OF DAY ({tz_label})"])
        w.writerow(["hour"] + [f"{h:02d}" for h in range(24)] + ["total"])
        w.writerow(["prompts"] + list(hod["hours"]) + [hod["total"]])

    # Weekday x hour matrix (project-wide)
    wh = tod.get("weekday_hour")
    if wh and wh.get("total", 0) > 0:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        w.writerow([])
        w.writerow([f"# WEEKDAY x HOUR ({tz_label})"])
        w.writerow(["weekday"] + [f"{h:02d}" for h in range(24)] + ["row_total"])
        for i, d in enumerate(days):
            w.writerow([d] + list(wh["matrix"][i]) + [wh["row_totals"][i]])
        w.writerow(["col_total"] + list(wh["col_totals"]) + [wh["total"]])

    # 5-hour session blocks
    blocks  = report.get("session_blocks") or []
    summary = report.get("block_summary") or {}
    if blocks:
        w.writerow([])
        w.writerow(["# 5-HOUR SESSION BLOCKS"])
        w.writerow(["trailing_7", "trailing_14", "trailing_30", "total"])
        w.writerow([summary.get("trailing_7", 0), summary.get("trailing_14", 0),
                    summary.get("trailing_30", 0), summary.get("total", len(blocks))])
        w.writerow([])
        w.writerow(["anchor_utc", "last_utc", "elapsed_min", "turns",
                    "user_prompts", "input", "output", "cache_read",
                    "cache_write", "cost_usd", "sessions_touched"])
        for b in blocks:
            w.writerow([
                b["anchor_iso"], b["last_iso"], f"{b['elapsed_min']:.1f}",
                b["turn_count"], b["user_msg_count"],
                b["input"], b["output"], b["cache_read"], b["cache_write"],
                f"{b['cost_usd']:.6f}", len(b["sessions_touched"]),
            ])

    # Phase-A (v1.6.0): skill/subagent/cache-break sections.
    by_skill = report.get("by_skill") or []
    if by_skill:
        w.writerow([])
        w.writerow(["# SKILLS / SLASH COMMANDS"])
        w.writerow(["name", "invocations", "turns", "input", "output",
                    "cache_read", "cache_write", "total_tokens",
                    "cost_usd", "cache_hit_pct", "pct_total_cost"])
        for r in by_skill:
            w.writerow([
                r.get("name", ""), r.get("invocations", 0),
                r.get("turns_attributed", 0), r.get("input", 0),
                r.get("output", 0), r.get("cache_read", 0),
                r.get("cache_write", 0), r.get("total_tokens", 0),
                f"{float(r.get('cost_usd', 0.0)):.6f}",
                f"{float(r.get('cache_hit_pct', 0.0)):.1f}",
                f"{float(r.get('pct_total_cost', 0.0)):.2f}",
            ])

    by_subagent = report.get("by_subagent_type") or []
    if by_subagent:
        w.writerow([])
        w.writerow(["# SUBAGENT TYPES"])
        w.writerow(["name", "spawn_count", "turns", "input", "output",
                    "cache_read", "cache_write", "total_tokens",
                    "avg_tokens_per_call", "cost_usd",
                    "cache_hit_pct", "pct_total_cost",
                    # v1.26.0: per-invocation warm-up signals.
                    "invocation_count", "first_turn_share_pct",
                    "sp_amortisation_pct"])
        for r in by_subagent:
            w.writerow([
                r.get("name", ""), r.get("spawn_count", 0),
                r.get("turns_attributed", 0), r.get("input", 0),
                r.get("output", 0), r.get("cache_read", 0),
                r.get("cache_write", 0), r.get("total_tokens", 0),
                f"{float(r.get('avg_tokens_per_call', 0.0)):.1f}",
                f"{float(r.get('cost_usd', 0.0)):.6f}",
                f"{float(r.get('cache_hit_pct', 0.0)):.1f}",
                f"{float(r.get('pct_total_cost', 0.0)):.2f}",
                int(r.get("invocation_count", 0)),
                f"{float(r.get('first_turn_share_pct', 0.0)):.1f}",
                f"{float(r.get('sp_amortisation_pct', 0.0)):.1f}",
            ])

    by_workflow = report.get("by_workflow") or []
    if by_workflow:
        w.writerow([])
        w.writerow(["# DYNAMIC WORKFLOWS"])
        w.writerow(["run_id", "workflow_name", "status", "agents",
                    "agent_count_journal", "tool_calls", "turns",
                    "input", "output", "cache_read", "cache_write",
                    "total_tokens", "cost_usd", "cache_hit_pct",
                    "pct_total_cost", "default_model", "duration_ms"])
        for r in by_workflow:
            w.writerow([
                r.get("run_id", ""), r.get("workflow_name", ""),
                r.get("status", ""), r.get("agents", 0),
                r.get("agent_count", 0), r.get("tool_calls", 0),
                r.get("turns_attributed", 0), r.get("input", 0),
                r.get("output", 0), r.get("cache_read", 0),
                r.get("cache_write", 0), r.get("total_tokens", 0),
                f"{float(r.get('cost_usd', 0.0)):.6f}",
                f"{float(r.get('cache_hit_pct', 0.0)):.1f}",
                f"{float(r.get('pct_total_cost', 0.0)):.2f}",
                r.get("default_model", ""), r.get("duration_ms", 0),
            ])

    cache_breaks = report.get("cache_breaks") or []
    if cache_breaks:
        w.writerow([])
        threshold = int(report.get("cache_break_threshold",
                                     _sm()._CACHE_BREAK_DEFAULT_THRESHOLD))
        w.writerow([f"# CACHE BREAKS (> {threshold:,} uncached)"])
        w.writerow(["session_id", "turn_index", "timestamp", "uncached",
                    "total_tokens", "cache_break_pct", "slash_command",
                    "project", "prompt_snippet"])
        for cb in cache_breaks:
            w.writerow([
                cb.get("session_id", ""), cb.get("turn_index", ""),
                cb.get("timestamp", ""), cb.get("uncached", 0),
                cb.get("total_tokens", 0),
                f"{float(cb.get('cache_break_pct', 0.0)):.1f}",
                cb.get("slash_command", ""),
                cb.get("project", ""),
                (cb.get("prompt_snippet") or "")[:240],
            ])

    wa = report.get("waste_analysis")
    if wa:
        dist = wa.get("distribution") or {}
        if dist:
            w.writerow([])
            w.writerow(["# TURN CHARACTER ANALYSIS"])
            w.writerow(["turn_character", "turn_character_label", "count"])
            for char, count in sorted(dist.items(), key=lambda x: -x[1]):
                w.writerow([char, _sm()._TURN_CHARACTER_LABELS.get(char, char), count])
        retry = wa.get("retry_chains") or {}
        if retry.get("chain_count", 0) > 0:
            w.writerow([])
            w.writerow([f"# RETRY CHAINS ({retry['chain_count']} chains, "
                        f"{retry.get('retry_cost_pct', 0):.1f}% of session cost)"])
            w.writerow(["chain_length", "turn_indices", "cost_usd"])
            for c in retry.get("chains") or []:
                w.writerow([c["length"],
                            ";".join(str(i) for i in c["turn_indices"]),
                            f"{c['cost_usd']:.6f}"])
        reaccess = wa.get("file_reaccesses") or {}
        if reaccess.get("reaccessed_count", 0) > 0:
            w.writerow([])
            w.writerow([f"# FILE RE-ACCESSES ({reaccess['reaccessed_count']} files)"])
            w.writerow(["path", "access_count", "first_turn", "cost_usd"])
            for d in reaccess.get("details") or []:
                w.writerow([d["path"], d["count"], d["first_turn"],
                            f"{d['cost_usd']:.6f}"])

    return out.getvalue()


def render_md(report: dict) -> str:
    """Render the full report as GitHub-flavored Markdown.

    Includes summary cards, user activity by time of day (UTC), model pricing
    table, and per-session turn-level tables with subtotals.
    """
    if report.get("mode") == "compare":
        return sys.modules["session_metrics_compare"].render_compare_md(report)
    if report.get("mode") == "instance":
        return _sm()._render_instance_md(report)
    out = io.StringIO()

    def p(*args, **kw):
        print(*args, **kw, file=out)

    slug = report["slug"]
    totals = report["totals"]
    mode = report["mode"]
    tz_offset = report.get("tz_offset_hours", 0.0)
    generated = _fmt_generated_at(report)
    skill_version = report.get("skill_version", "?")

    p(f"# Session Metrics — {slug}")
    p()
    p(f"Generated: {generated}  |  Mode: {mode}  |  Skill: v{skill_version}")
    p()

    # Summary cards
    p("## Summary")
    p()
    p(f"| Metric | Value |")
    p(f"|--------|-------|")
    p(f"| Sessions | {len(report['sessions'])} |")
    p(f"| Total turns | {totals['turns']:,} |")
    # Wall clock + mean turn latency. ``Wall clock`` is the sum of per-session
    # first→last assistant-turn intervals; for benchmark / headless ``claude
    # -p`` runs this approximates the orchestrator's perceived wall-clock.
    # ``Mean turn latency`` is the average ``latency_seconds`` across every
    # assistant turn that had a parseable predecessor — drops resume markers
    # and any turn whose predecessor timestamp couldn't be parsed.
    _wall_total = sum(int(s.get("wall_clock_seconds", 0) or s.get("duration_seconds", 0)) for s in report["sessions"])
    _turn_lats = [t["latency_seconds"] for s in report["sessions"]
                   for t in s["turns"] if t.get("latency_seconds") is not None]
    if _wall_total > 0:
        p(f"| Wall clock | {_fmt_duration(_wall_total)} |")
    if _turn_lats:
        _mean_lat = sum(_turn_lats) / len(_turn_lats)
        p(f"| Mean turn latency | {_mean_lat:.2f}s ({len(_turn_lats)} turns) |")
    p(f"| Total cost | ${totals['cost']:.4f} |")
    _share_line = _build_subagent_share_md(_sm()._compute_subagent_share(report))
    if _share_line:
        p(_share_line)
    p(f"| Cache savings | ${totals['cache_savings']:.4f} |")
    p(f"| Cache hit ratio | {totals['cache_hit_pct']:.1f}% |")
    p(f"| Total input tokens | {totals['total_input']:,} |")
    p(f"| Input tokens (new) | {totals['input']:,} |")
    p(f"| Output tokens | {totals['output']:,} |")
    p(f"| Cache read tokens | {totals['cache_read']:,} |")
    p(f"| Cache write tokens | {totals['cache_write']:,} |")
    _cs = report.get("compaction_summary") or {}
    if int(_cs.get("boundary_count", 0) or 0) > 0:
        _split = []
        if _cs.get("auto_count"):
            _split.append(f"{_cs['auto_count']} auto")
        if _cs.get("manual_count"):
            _split.append(f"{_cs['manual_count']} manual")
        _split_str = f" ({', '.join(_split)})" if _split else ""
        p(f"| Context compactions | {_cs['boundary_count']}{_split_str} · "
          f"{int(_cs.get('total_reclaimed_tokens', 0) or 0):,} tokens reclaimed |")
    if totals.get("cache_write_1h", 0) > 0:
        pct_1h = 100 * totals["cache_write_1h"] / max(1, totals["cache_write"])
        p(f"| Cache TTL mix (1h share of writes) | {pct_1h:.1f}% |")
        p(f"| Extra cost paid for 1h cache tier | ${totals.get('extra_1h_cost', 0.0):.4f} |")
    if totals.get("thinking_turn_count", 0) > 0:
        cb = totals.get("content_blocks") or {}
        p(
            f"| Extended thinking turns | "
            f"{totals['thinking_turn_count']} of {totals['turns']} "
            f"({totals.get('thinking_turn_pct', 0.0):.1f}%, "
            f"{cb.get('thinking', 0)} blocks) |"
        )
    if totals.get("tool_call_total", 0) > 0:
        top3 = totals.get("tool_names_top3") or []
        top3_str = ", ".join(top3) if top3 else "none"
        p(
            f"| Tool calls | {totals['tool_call_total']} total, "
            f"{totals.get('tool_call_avg_per_turn', 0.0):.1f}/turn "
            f"(top: {top3_str}) |"
        )
    if totals.get("advisor_call_count", 0) > 0:
        _adv_n = totals["advisor_call_count"]
        _adv_c = totals.get("advisor_cost_usd", 0.0)
        p(f"| Advisor calls | {_adv_n} call{'s' if _adv_n != 1 else ''} · +${_adv_c:.4f} |")
    p()

    # Usage Insights — derived from `_compute_usage_insights`. Renders only
    # when at least one insight crossed its threshold; otherwise the
    # section is omitted entirely so the existing layout flow is preserved.
    md_insights = _build_usage_insights_md(report.get("usage_insights", []) or [])
    if md_insights:
        p(md_insights)

    md_waste = _build_waste_analysis_md(report.get("waste_analysis") or {})
    if md_waste:
        p(md_waste)

    # Time-of-day section
    tod = report.get("time_of_day", {})
    tz_label = report.get("tz_label", "UTC")
    if tod.get("message_count", 0) > 0:
        b = tod["buckets"]
        p(f"## User Activity by Time of Day ({tz_label})")
        p()
        p("| Period | Hours | Messages |")
        p("|--------|------:|---------:|")
        p(f"| Night | 0\u20136 | {b.get('night', 0):,} |")
        p(f"| Morning | 6\u201312 | {b.get('morning', 0):,} |")
        p(f"| Afternoon | 12\u201318 | {b.get('afternoon', 0):,} |")
        p(f"| Evening | 18\u201324 | {b.get('evening', 0):,} |")
        p(f"| **Total** | | **{tod['message_count']:,}** |")
        p()

        hod = tod.get("hour_of_day")
        if hod and hod.get("total", 0) > 0:
            hours = hod["hours"]
            p(f"### Hour of day ({tz_label})")
            p()
            p("| Hour | Prompts |")
            p("|-----:|--------:|")
            for h in range(24):
                p(f"| {h:02d}:00 | {hours[h]:,} |")
            p()

        wh = tod.get("weekday_hour")
        if wh and wh.get("total", 0) > 0:
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            p(f"### Weekday x hour ({tz_label})")
            p()
            header = "| Day | " + " | ".join(f"{h:02d}" for h in range(24)) + " | Total |"
            sep = "|-----|" + "|".join(["---:"] * 24) + "|------:|"
            p(header)
            p(sep)
            for i, d in enumerate(days):
                row = wh["matrix"][i]
                cells = " | ".join(str(c) if c else "" for c in row)
                p(f"| {d} | {cells} | **{wh['row_totals'][i]:,}** |")
            p()

    blocks  = report.get("session_blocks", [])
    summary = report.get("block_summary", {})
    if blocks:
        p(f"## 5-hour session blocks ({tz_label})")
        p()
        p(f"- Trailing 7 days: **{summary.get('trailing_7', 0)}** blocks")
        p(f"- Trailing 14 days: **{summary.get('trailing_14', 0)}** blocks")
        p(f"- Trailing 30 days: **{summary.get('trailing_30', 0)}** blocks")
        p(f"- All time: **{summary.get('total', len(blocks))}** blocks")
        p()
        p(f"| Anchor ({tz_label}) | Duration | Turns | Prompts | Cost | Sessions |")
        p("|-------------|---------:|------:|--------:|-----:|---------:|")
        for b in reversed(blocks[-12:]):
            anchor_local = _fmt_epoch_local(b["anchor_epoch"], tz_offset, "%Y-%m-%d %H:%M")
            p(f"| {anchor_local} | {b['elapsed_min']:.0f}m "
              f"| {b['turn_count']:,} | {b['user_msg_count']:,} "
              f"| ${b['cost_usd']:.3f} | {len(b['sessions_touched'])} |")
        p()

    if report["models"]:
        p("## Models")
        p()
        p("| Model | Turns | Turn % | Cost $ | Cost % | $/M in | $/M out | $/M rd | $/M wr |")
        p("|-------|------:|------:|------:|------:|------:|------:|------:|------:|")
        _t_total = sum(int(i.get("turns", 0)) for i in report["models"].values()) or 1
        _c_total = sum(float(i.get("cost_usd", 0.0)) for i in report["models"].values()) or 0.0
        for m, info in sorted(report["models"].items(),
                              key=lambda x: -float(x[1].get("cost_usd", 0.0))):
            r = _sm()._pricing_for(m)
            cnt = int(info.get("turns", 0))
            cost = float(info.get("cost_usd", 0.0))
            t_pct = 100.0 * cnt / _t_total
            c_pct = (100.0 * cost / _c_total) if _c_total else 0.0
            p(f"| `{m}` | {cnt:,} | {t_pct:.1f}% | ${cost:.4f} | {c_pct:.1f}% "
              f"| ${r['input']:.2f} | ${r['output']:.2f} | ${r['cache_read']:.2f} | ${r['cache_write']:.2f} |")
        p()

    # Phase-A (v1.6.0) sections: skill / subagent / cache-break tables.
    by_skill_rows = report.get("by_skill") or []
    if by_skill_rows:
        p("## Skills & slash commands")
        p()
        p("| Name | Invocations | Turns | Input | Output | % cached | Cost $ | % of total |")
        p("|------|------------:|------:|------:|------:|--------:|------:|-----------:|")
        for r in by_skill_rows:
            p(f"| `{r.get('name', '')}` | {int(r.get('invocations', 0)):,} "
              f"| {int(r.get('turns_attributed', 0)):,} "
              f"| {int(r.get('input', 0)):,} "
              f"| {int(r.get('output', 0)):,} "
              f"| {float(r.get('cache_hit_pct', 0.0)):.1f}% "
              f"| ${float(r.get('cost_usd', 0.0)):.4f} "
              f"| {float(r.get('pct_total_cost', 0.0)):.2f}% |")
        p()

    by_subagent_rows = report.get("by_subagent_type") or []
    if by_subagent_rows:
        p("## Subagent types")
        p()
        # v1.26.0: extra warm-up columns visible only when per-invocation
        # data was actually observed (i.e. ``--include-subagents`` was on
        # AND the loader saw subagent JSONL turns).
        _show_warm = bool(report.get("include_subagents")) and any(
            int(r.get("invocation_count", 0)) > 0 for r in by_subagent_rows
        )
        if _show_warm:
            p("| Subagent | Spawns | Turns | Input | Output | % cached "
              "| Avg/call | Cost $ | % of total | First-turn % | SP amortised % |")
            p("|----------|-------:|------:|------:|------:|--------:|"
              "--------:|------:|-----------:|-------------:|---------------:|")
        else:
            p("| Subagent | Spawns | Turns | Input | Output | % cached | Avg/call | Cost $ | % of total |")
            p("|----------|-------:|------:|------:|------:|--------:|--------:|------:|-----------:|")
        for r in by_subagent_rows:
            base = (
                f"| `{r.get('name', '')}` | {int(r.get('spawn_count', 0)):,} "
                f"| {int(r.get('turns_attributed', 0)):,} "
                f"| {int(r.get('input', 0)):,} "
                f"| {int(r.get('output', 0)):,} "
                f"| {float(r.get('cache_hit_pct', 0.0)):.1f}% "
                f"| {float(r.get('avg_tokens_per_call', 0.0)):,.0f} "
                f"| ${float(r.get('cost_usd', 0.0)):.4f} "
                f"| {float(r.get('pct_total_cost', 0.0)):.2f}% "
            )
            if _show_warm:
                inv_n = int(r.get("invocation_count", 0))
                if inv_n > 0:
                    base += (
                        f"| {float(r.get('first_turn_share_pct', 0.0)):.1f}% "
                        f"| {float(r.get('sp_amortisation_pct', 0.0)):.1f}% |"
                    )
                else:
                    base += "| — | — |"
            else:
                base += "|"
            p(base)
        p()

    # Dynamic workflows (Workflow tool) — runId-keyed cost table. Cost/tokens
    # exact from agent transcripts; name/status/duration from the run journal.
    by_workflow_rows = report.get("by_workflow") or []
    if by_workflow_rows:
        p("## Dynamic workflows")
        p()
        p("| Workflow | Status | Agents | Tool calls | Total tokens "
          "| % cached | Cost $ | % of total | Model | Duration |")
        p("|----------|--------|-------:|-----------:|-------------:"
          "|---------:|------:|-----------:|-------|---------:|")
        for r in by_workflow_rows:
            mdls = r.get("models") or {}
            top = max(mdls, key=lambda k: mdls[k]) if mdls else "—"
            mdl_lbl = top if len(mdls) <= 1 else f"{top} +{len(mdls) - 1}"
            dur_s = int(r.get("duration_ms", 0)) // 1000
            dur = (f"{dur_s // 60}m {dur_s % 60}s" if dur_s >= 60
                   else (f"{dur_s}s" if dur_s else "—"))
            p(
                f"| `{r.get('workflow_name', '') or r.get('run_id', '')}` "
                f"| {r.get('status', '') or '—'} "
                f"| {int(r.get('agents', 0)):,} "
                f"| {int(r.get('tool_calls', 0)):,} "
                f"| {int(r.get('total_tokens', 0)):,} "
                f"| {float(r.get('cache_hit_pct', 0.0)):.1f}% "
                f"| ${float(r.get('cost_usd', 0.0)):.4f} "
                f"| {float(r.get('pct_total_cost', 0.0)):.2f}% "
                f"| {mdl_lbl} | {dur} |"
            )
        p()

    # Per-request breakdown — deterministic task-grouping foundation. One row
    # per user prompt + all the work it drove (follow-up turns + subagents).
    # Honest framing: per-request, NOT semantic tasks (the task-breakdown skill
    # groups these into labelled tasks on a separate companion page).
    request_units = report.get("request_units") or []
    if len(request_units) > 1:
        _ru_total = float((report.get("totals") or {}).get("cost", 0.0) or 0.0)
        _ru_rows = sorted(request_units,
                          key=lambda u: -float(u.get("combined_cost_usd", 0.0)))
        _ru_limit = 50
        p("## Per-request breakdown")
        p()
        p("_One row per user prompt and all the work it drove (follow-up turns "
          "+ attributed subagents). Per-request, **not** semantic tasks — the "
          "`task-breakdown` skill groups these into labelled tasks._")
        p()
        p("| Turn | Request | Turns | Cost $ | % total | Tokens | Tools "
          "| Risk | Re-reads | Idle (s) |")
        p("|-----:|---------|------:|-------:|--------:|-------:|-------"
          "|-----:|---------:|---------:|")
        for u in _ru_rows[:_ru_limit]:
            tools = list(u.get("tool_histogram") or {})
            tools_str = ", ".join(tools[:3]) + (f" +{len(tools) - 3}"
                                                if len(tools) > 3 else "")
            snippet = (u.get("prompt_snippet") or "").replace("|", "\\|")
            if u.get("slash_command"):
                snippet = f"{u['slash_command']} · {snippet}"
            if u.get("multi_intent_possible"):
                snippet += " _(multi-ask?)_"
            comb = float(u.get("combined_cost_usd", 0.0))
            pct = (100.0 * comb / _ru_total) if _ru_total else 0.0
            p(f"| #{u.get('anchor_index')} | {snippet} "
              f"| {int(u.get('turn_count', 0)):,} "
              f"| ${comb:.4f} "
              f"| {pct:.1f}% "
              f"| {int(u.get('total_tokens', 0)):,} "
              f"| {tools_str or '—'} "
              f"| {int(u.get('risk_turn_count', 0))} "
              f"| {int(u.get('reread_path_count', 0))} "
              f"| {int(u.get('idle_gap_before_seconds', 0))} |")
        if len(_ru_rows) > _ru_limit:
            p()
            p(f"_Showing top {_ru_limit} of {len(_ru_rows)} requests by cost._")
        p()

    # Within-session spawning split — descriptive contrast that holds
    # task / model / context constant. Only renders for sessions with
    # ≥3 spawning AND ≥3 non-spawning turns (median needs a floor).
    _ws_split = _sm()._compute_within_session_split(report.get("sessions") or [])
    _ws_split_md = _build_within_session_split_md(_ws_split)
    if _ws_split_md:
        p(_ws_split_md)

    cache_breaks_rows = report.get("cache_breaks") or []
    if cache_breaks_rows:
        threshold = int(report.get("cache_break_threshold",
                                     _sm()._CACHE_BREAK_DEFAULT_THRESHOLD))
        p(f"## Cache breaks (> {threshold:,} uncached)")
        p()
        p(f"{len(cache_breaks_rows)} event{'s' if len(cache_breaks_rows) != 1 else ''} "
          f"— single turns where `input + cache_creation` exceeded the threshold. "
          f"Each row names *which* turn lost the cache.")
        p()
        p("| Uncached | % | When | Session | Prompt |")
        p("|---------:|--:|------|---------|--------|")
        for cb in cache_breaks_rows[:25]:
            sid8 = (cb.get("session_id") or "")[:8]
            snippet = (cb.get("prompt_snippet") or "").replace("|", "\\|")[:120]
            p(f"| {int(cb.get('uncached', 0)):,} "
              f"| {float(cb.get('cache_break_pct', 0.0)):.0f}% "
              f"| {cb.get('timestamp_fmt') or cb.get('timestamp', '')} "
              f"| `{sid8}` "
              f"| {snippet} |")
        if len(cache_breaks_rows) > 25:
            p()
            p(f"_Showing top 25 of {len(cache_breaks_rows)} — raw list available in JSON export._")
        p()

    # Q1: context-compaction events. Each boundary reset the working context;
    # reclaimed = preTokens-postTokens. Auto-hides when none recorded.
    compaction_rows = report.get("compaction_events") or []
    if compaction_rows:
        p(f"## Context compactions")
        p()
        p(f"{len(compaction_rows)} compaction boundar"
          f"{'y' if len(compaction_rows) == 1 else 'ies'} — points where the "
          f"working context was summarised and reset. The turn after each "
          f"rebuilds context (expect a cache-write spike).")
        p()
        p("| When | Session | Trigger | Pre → Post | Reclaimed | Duration |")
        p("|------|---------|---------|-----------|----------:|---------:|")
        for ev in compaction_rows[:50]:
            sid8 = (ev.get("session_id") or "")[:8]
            pre = ev.get("pre_tokens")
            post = ev.get("post_tokens")
            recl = ev.get("reclaimed_tokens")
            dur = ev.get("duration_ms")
            pre_post = (f"{pre:,} → {post:,}"
                        if isinstance(pre, int) and isinstance(post, int) else "—")
            recl_s = f"{recl:,}" if isinstance(recl, int) else "—"
            dur_s = f"{dur / 1000:.1f}s" if isinstance(dur, int) else "—"
            p(f"| {ev.get('timestamp') or ''} "
              f"| `{sid8}` "
              f"| {ev.get('trigger') or '—'} "
              f"| {pre_post} "
              f"| {recl_s} "
              f"| {dur_s} |")
        if len(compaction_rows) > 50:
            p()
            p(f"_Showing first 50 of {len(compaction_rows)} — raw list available in JSON export._")
        p()

    has_1h_cache = _has_1h_cache(report)
    has_content  = _has_content_blocks(report)
    p("## Column legend")
    p()
    p("- **#** — deduplicated turn index")
    p(f"- **Time** — turn start, local tz ({tz_label})")
    p("- **Input (new)** — net new input tokens (uncached)")
    p("- **Output** — generated tokens (includes thinking + tool_use block tokens)")
    p("- **CacheRd** — tokens read from cache (cheap)")
    if has_1h_cache:
        p("- **CacheWr** — tokens written to cache; `*` suffix marks turns that used the 1-hour TTL tier")
    else:
        p("- **CacheWr** — tokens written to cache (one-time)")
    p("- **Total** — sum of the four billable token buckets")
    p("- **Cost $** — estimated USD for this turn")
    if has_content:
        p("- **Content** — per-turn content blocks: `T` thinking, `u` tool_use, "
          "`x` text, `r` tool_result, `i` image, `v` server_tool_use, "
          "`R` advisor_tool_result (zero counts omitted)")
    p()

    for i, s in enumerate(report["sessions"], 1):
        if mode == "project":
            st = s["subtotal"]
            p(f"## Session {i}: `{s['session_id'][:8]}…`")
            p()
            p(f"{s['first_ts']} → {s['last_ts']} &nbsp;·&nbsp; {len(s['turns'])} turns &nbsp;·&nbsp; **${st['cost']:.4f}**")
            p()

        if has_content:
            p(f"| # | Time ({tz_label}) | Input (new) | Output | CacheRd | CacheWr | Total | Cost $ | Content |")
            p("|--:|-----------|------------:|------:|--------:|--------:|------:|-------:|:--------|")
        else:
            p(f"| # | Time ({tz_label}) | Input (new) | Output | CacheRd | CacheWr | Total | Cost $ |")
            p("|--:|-----------|------------:|------:|--------:|--------:|------:|-------:|")
        for t in s["turns"]:
            ttl = t.get("cache_write_ttl", "")
            cwr_cell = f"{t['cache_write_tokens']:,}" + ("*" if ttl in ("1h", "mix") else "")
            row = (f"| {t['index']} | {t['timestamp_fmt']} "
                   f"| {t['input_tokens']:,} | {t['output_tokens']:,} "
                   f"| {t['cache_read_tokens']:,} | {cwr_cell} "
                   f"| {t['total_tokens']:,} | ${t['cost_usd']:.4f} |")
            if has_content:
                row += f" {_sm()._fmt_content_cell(t.get('content_blocks') or {})} |"
            p(row)
        st = s["subtotal"]
        st_cwr_cell = f"{st['cache_write']:,}" + ("*" if st.get("cache_write_1h", 0) > 0 else "")
        trow = (f"| **TOT** | | **{st['input']:,}** | **{st['output']:,}** "
                f"| **{st['cache_read']:,}** | **{st_cwr_cell}** "
                f"| **{st['total']:,}** | **${st['cost']:.4f}** |")
        if has_content:
            trow += " |"
        p(trow)
        if st.get("cache_write_1h", 0) > 0:
            p()
            p(f"_`*` = cache write includes the 1-hour TTL tier "
              f"(5m: {st.get('cache_write_5m', 0):,}, 1h: {st['cache_write_1h']:,} tokens)._")
        p()

    return out.getvalue()


def _fmt_duration(sec: int) -> str:
    """Format ``sec`` as a compact duration (``1h23m``, ``45m12s``, ``7s``)."""
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m{sec % 60:02d}s"
    hours, rem = divmod(sec, 3600)
    return f"{hours}h{rem // 60:02d}m"


def _build_subagent_share_md(stats: dict) -> str:
    """Single line for the MD ``## Summary`` table.

    Returns an empty string when the line should be omitted (i.e. when
    ``include_subagents`` is False AND there are no spawns to disclose).
    The HTML headline always renders for visibility; MD is a tabular
    summary so we suppress the row in the no-data case to avoid
    misleading readers with a 0% line they can't act on.
    """
    if not stats.get("include_subagents"):
        # Show a one-liner only when spawns were detected so user knows
        # the data is incomplete; otherwise stay quiet.
        if int(stats.get("spawn_count", 0)) == 0:
            return ""
        return ("| Subagent share of cost | attribution disabled "
                "(re-run with `--include-subagents`) |")
    if not stats.get("has_attribution"):
        return "| Subagent share of cost | 0% — no subagent activity |"
    pct = float(stats.get("share_pct", 0.0))
    cost = float(stats.get("attributed_cost", 0.0))
    total = float(stats.get("total_cost", 0.0))
    spawns = int(stats.get("spawn_count", 0))
    orphans = int(stats.get("orphan_turns", 0))
    lb = (f" — lower bound, {orphans} orphan turn"
          f"{'s' if orphans != 1 else ''} excluded") if orphans else ""
    return (
        f"| Subagent share of cost | "
        f"{pct:.1f}% (${cost:.4f} of ${total:.4f}, "
        f"{spawns} spawn{'s' if spawns != 1 else ''}{lb}) |"
    )


def _build_within_session_split_md(rows: list[dict]) -> str:
    """Markdown rendering of the within-session split table.

    Returns "" when no session qualifies. Helper text mirrors the HTML
    section: descriptive correlation only, NOT a counterfactual.
    """
    if not rows:
        return ""
    out: list[str] = []
    out.append("## Within-session spawning split")
    out.append("")
    out.append("Per session, median *combined* turn cost (parent direct + "
               "attributed subagent) on spawning vs. non-spawning turns. "
               "Descriptive correlation — users delegate the hardest "
               "sub-tasks, so this is **not** a counterfactual estimate "
               "of what the same work would have cost in the main context.")
    out.append("")
    out.append("| Session | Spawn turns | No-spawn turns | "
               "Median (spawn) | Median (no spawn) | Δ | Spawn-turn cost share |")
    out.append("|---------|------------:|---------------:|"
               "---------------:|------------------:|---:|----------------------:|")
    for r in rows:
        sid = (r.get("session_id") or "")[:8]
        ms  = float(r.get("median_spawn", 0.0))
        mns = float(r.get("median_no_spawn", 0.0))
        delta = float(r.get("delta", 0.0))
        sign = "+" if delta >= 0 else ""
        out.append(
            f"| `{sid}…` | {int(r.get('spawn_n', 0)):,} "
            f"| {int(r.get('no_spawn_n', 0)):,} "
            f"| ${ms:.4f} | ${mns:.4f} "
            f"| {sign}${delta:.4f} "
            f"| {float(r.get('spawn_share_pct', 0.0)):.1f}% |"
        )
    out.append("")
    return "\n".join(out)


def _build_workflow_companion_md(report: dict) -> str:
    """Standalone Markdown deep-dive for a report's dynamic workflows.

    The Markdown sibling of ``_build_workflow_companion_html``: one section per
    run with a phase → agent timeline. Per-agent token/cost are exact (summed
    from agent transcripts); labels, phases, tool-calls and previews come from
    the run journal. Returns "" when the report has no workflows.
    """
    rows = report.get("by_workflow") or []
    if not rows:
        return ""

    def _dur(ms: int) -> str:
        s = int(ms) // 1000
        if s <= 0:
            return "—"
        if s < 60:
            return f"{s}s"
        m, sec = divmod(s, 60)
        if m < 60:
            return f"{m}m {sec}s"
        h, m = divmod(m, 60)
        return f"{h}h {m}m"

    def _cell(text) -> str:
        return str(text or "").replace("|", "\\|").replace("\n", " ").strip()

    scope = report.get("slug") or report.get("mode") or ""
    gen = report.get("generated_at", "") or ""
    ver = str(report.get("skill_version", "") or "")
    tot_runs = len(rows)
    tot_agents = sum(int(r.get("agents", 0)) for r in rows)
    tot_cost = sum(float(r.get("cost_usd", 0.0)) for r in rows)
    tot_tokens = sum(int(r.get("total_tokens", 0)) for r in rows)

    out: list[str] = [
        f"# Dynamic workflows — {scope}",
        "",
        f"_Generated {gen} · skill v{ver}_",
        "",
        "Per-agent token/cost are exact (summed from agent transcripts); labels, "
        "phases, tool-calls and previews come from the run journal.",
        "",
        f"**{tot_runs:,}** run{'s' if tot_runs != 1 else ''} · "
        f"**{tot_agents:,}** agents · **${tot_cost:.4f}** · "
        f"**{tot_tokens:,}** tokens",
        "",
    ]
    for r in rows:
        name = r.get("workflow_name") or r.get("run_id") or ""
        out.append(f"## {name}")
        out.append("")
        meta_bits = [
            f"status **{r.get('status') or '—'}**",
            f"{int(r.get('agents', 0)):,} agents",
            f"${float(r.get('cost_usd', 0.0)):.4f}",
            f"{int(r.get('total_tokens', 0)):,} tokens",
            _dur(int(r.get("duration_ms", 0))),
        ]
        if r.get("project"):
            meta_bits.insert(0, f"project `{_cell(r.get('project'))}`")
        out.append(" · ".join(meta_bits))
        out.append("")

        agents = r.get("agent_details") or []
        by_phase: dict = {}
        for a in agents:
            by_phase.setdefault(int(a.get("phaseIndex") or 0), []).append(a)
        phase_titles = {i + 1: (p.get("title") or "")
                        for i, p in enumerate(r.get("phases") or [])}
        for pidx in sorted(by_phase):
            ptitle = phase_titles.get(pidx, "")
            head = f"Phase {pidx}" + (f": {ptitle}" if ptitle else "")
            out.append(f"### {head}")
            out.append("")
            out.append("| Agent | Model | Tokens | Cost $ | Tools | Duration | State |")
            out.append("|-------|-------|-------:|-------:|------:|---------:|-------|")
            ranked = sorted(by_phase[pidx],
                            key=lambda x: -float(x.get("transcript_cost") or 0.0))
            for a in ranked:
                out.append(
                    f"| `{_cell(a.get('label') or a.get('agentId'))}` "
                    f"| {_cell(a.get('model'))} "
                    f"| {int(a.get('transcript_tokens', 0)):,} "
                    f"| ${float(a.get('transcript_cost', 0.0)):.4f} "
                    f"| {int(a.get('toolCalls', 0)):,} "
                    f"| {_dur(int(a.get('durationMs', 0)))} "
                    f"| {_cell(a.get('state'))} |"
                )
            previews = [(a.get("label") or a.get("agentId") or "",
                         (a.get("resultPreview") or "")[:200])
                        for a in ranked if a.get("resultPreview")]
            if previews:
                out.append("")
                for lbl, pv in previews:
                    out.append(f"- `{_cell(lbl)}` — {_cell(pv)}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


_TASK_VERDICT_MD = {
    "worth_it": "✅ Worth it", "mixed": "🟡 Mixed", "likely_waste": "🔴 Likely waste",
}


def _build_tasks_companion_md(report: dict, tasks_data: dict) -> str:
    """Standalone Markdown "Tasks" companion — the Markdown sibling of
    :func:`_html_sections._build_tasks_companion_html`.

    One section per Claude-grouped task with a verdict, rationale and a member
    request-unit table. All figures come from ``tasks_data`` (summed from the
    export's request units). Returns "" when there are no tasks.
    """
    tasks = tasks_data.get("tasks") or []
    if not tasks:
        return ""

    def _cell(text) -> str:
        return str(text or "").replace("|", "\\|").replace("\n", " ").strip()

    scope = (tasks_data.get("scope_label")
             or report.get("slug") or report.get("mode") or "")
    gen = report.get("generated_at", "") or ""
    ver = str(report.get("skill_version", "") or "")
    out: list[str] = [
        f"# Tasks — {scope}",
        "",
        f"_Generated {gen} · skill v{ver}_",
        "",
        "Semantic tasks grouped by Claude from the deterministic per-request "
        "breakdown. Every figure is summed from the export's request units — "
        "the grouping only assigns requests to tasks and labels each.",
        "",
        f"**{len(tasks):,}** task{'s' if len(tasks) != 1 else ''} · "
        f"**{int(tasks_data.get('total_turns', 0)):,}** turns · "
        f"**${float(tasks_data.get('total_cost_usd', 0.0)):.4f}** · "
        f"**{tasks_data.get('coverage_pct', 0.0):.0f}%** of requests grouped",
        "",
    ]
    for t in tasks:
        out.append(f"## {t.get('title') or 'Untitled task'}")
        out.append("")
        verdict = _TASK_VERDICT_MD.get(t.get("verdict") or "", "")
        meta = [m for m in [
            verdict,
            f"{int(t.get('member_count', 0)):,} requests",
            f"{int(t.get('turn_count', 0)):,} turns",
            f"${float(t.get('cost_usd', 0.0)):.4f}",
            f"{int(t.get('total_tokens', 0)):,} tokens",
            (f"⚠ {int(t.get('risk_turn_count', 0))} risky turns"
             if int(t.get("risk_turn_count", 0)) else ""),
        ] if m]
        out.append(" · ".join(meta))
        out.append("")
        if t.get("rationale"):
            out.append(f"> {_cell(t.get('rationale'))}")
            out.append("")
        out.append("| Req | Prompt | Turns | Cost $ | Tokens | Tools | Risk |")
        out.append("|----:|--------|------:|-------:|-------:|-------|-----:|")
        for u in t.get("members") or []:
            tools = list(u.get("tool_histogram") or {})
            tools_str = ", ".join(tools[:3]) + (f" +{len(tools) - 3}"
                                                if len(tools) > 3 else "")
            out.append(
                f"| #{u.get('anchor_index')} "
                f"| {_cell((u.get('prompt_snippet') or '')[:120])} "
                f"| {int(u.get('turn_count', 0)):,} "
                f"| ${float(u.get('combined_cost_usd', 0.0)):.4f} "
                f"| {int(u.get('total_tokens', 0)):,} "
                f"| {tools_str or '—'} "
                f"| {int(u.get('risk_turn_count', 0)) or '—'} |")
        out.append("")
    warnings = tasks_data.get("warnings") or []
    if warnings:
        out.append("## Grouping notes")
        out.append("")
        for w in warnings[:20]:
            out.append(f"- {_cell(w)}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _build_usage_insights_md(insights: list[dict]) -> str:
    """Render the Usage Insights as a flat Markdown bullet list.
    Returns `""` if no insights are shown."""
    shown = [i for i in (insights or []) if i.get("shown")]
    if not shown:
        return ""
    threshold_bearing = [i for i in shown if not i.get("always_on")]
    top = max(threshold_bearing, key=lambda i: i.get("value", 0)) if threshold_bearing else shown[0]
    ordered = [top] + [i for i in shown if i is not top]
    lines = ["## Usage Insights", ""]
    for i in ordered:
        lines.append(f"- **{i.get('headline', '')}**{i.get('body', '')}")
    lines.append("")
    return "\n".join(lines)


def _build_waste_analysis_md(wa: dict) -> str:
    """Render the waste analysis summary as a Markdown section.
    Returns ``""`` when there is nothing to show."""
    if not wa:
        return ""
    dist  = wa.get("distribution") or {}
    total = max(sum(dist.values()), 1)
    if total == 0:
        return ""

    _ORDER = [
        "productive", "cache_read", "cache_write", "reasoning",
        "subagent_overhead", "retry_error", "file_reread",
        "oververbose_edit", "dead_end",
    ]
    lines = ["## Turn Character & Efficiency Signals", ""]
    for cat in _ORDER:
        n = dist.get(cat, 0)
        if n == 0:
            continue
        pct = n / total * 100
        lbl = _sm()._TURN_CHARACTER_LABELS.get(cat, cat)
        risk_marker = " ⚠" if cat in _sm()._RISK_CATEGORIES else ""
        lines.append(f"- **{lbl}{risk_marker}**: {n:,} turns ({pct:.1f}%)")

    retry = wa.get("retry_chains") or {}
    if retry.get("chain_count", 0) > 0:
        lines.append("")
        lines.append(f"**Retry chains:** {retry['chain_count']} detected, "
                     f"{float(retry.get('retry_cost_pct', 0.0)):.1f}% of session cost")

    reaccess = wa.get("file_reaccesses") or {}
    if reaccess.get("reaccessed_count", 0) > 0:
        lines.append(f"**File re-accesses:** {reaccess['reaccessed_count']} files read 2+ times")

    verbose = wa.get("verbose_edits") or {}
    if verbose.get("verbose_count", 0) > 0:
        lines.append(f"**Verbose edits:** {verbose['verbose_count']} Edit turns with output > 800 tokens")

    sr = wa.get("stop_reasons") or {}
    mt_count = int(sr.get("max_tokens_count", 0))
    if mt_count > 0:
        mt_pct = float(sr.get("max_tokens_pct", 0.0))
        lines.append(f"**Truncated responses (max_tokens):** {mt_count} turns ({mt_pct:.1f}%)")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Theme layer — 4 themes (Beacon / Console / Lattice / Pulse) bundled in
# every HTML export, with a top-right picker. Ported from
# examples/claude-design-html-templates/variants-v1/{dashboard,detail}.html
# and layered over the existing class names (.cards/.card/.timeline-table/
# .turn-drawer/.prompts-table/.usage-insights/...) so the rewrite preserves
# every data contract the test suite asserts on while still producing the
# preview's visual output under each theme.
#
# Three helpers:
#   _theme_css()                 — full <style>...</style> block (base + 4 themes)
#   _theme_picker_markup()       — 4-button switcher for top-right
#   _theme_bootstrap_head_js()   — pre-paint hash/localStorage read (in <head>)
#   _theme_bootstrap_body_js()   — click handler + nav-forward (end of <body>)
# ---------------------------------------------------------------------------

