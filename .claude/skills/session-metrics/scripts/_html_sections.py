"""HTML section builders and render_html for session-metrics."""
import html as html_mod
import json
import re
import sys
from datetime import datetime, timezone


def _sm():
    """Return the session_metrics module (deferred — fully loaded by call time)."""
    return sys.modules["session_metrics"]


def _fmt_content_cell(cb: dict) -> str:
    """Format the per-turn Content cell. Zeros are omitted.

    Example: ``{thinking: 3, tool_use: 2, text: 1}`` → ``"T3 u2 x1"``.
    Returns ``"-"`` when every count is zero so empty rows stay visible.
    """
    if not cb:
        return "-"
    parts: list[str] = []
    for key, letter in _sm()._CONTENT_LETTERS:
        n = cb.get(key, 0)
        if n:
            parts.append(f"{letter}{n}")
    return " ".join(parts) if parts else "-"


def _fmt_content_title(cb: dict) -> str:
    """Human-readable tooltip text for the per-turn Content cell."""
    if not cb:
        return ""
    parts = [f"{cb.get(key, 0)} {key}"
             for key, _ in _sm()._CONTENT_LETTERS if cb.get(key, 0) > 0]
    return ", ".join(parts)


def _footer_text(totals: dict, models: dict[str, dict],
                 time_of_day: dict | None = None,
                 tz_label: str = "UTC",
                 session_blocks: list[dict] | None = None,
                 block_summary: dict | None = None) -> str:
    """Build the text footer with cache stats, model breakdown, and time-of-day.

    Args:
        totals: Aggregated token/cost totals dict.
        models: ``{model_id: {"turns", "cost_usd"}}`` mapping.
        time_of_day: Optional ``time_of_day`` report section.  When provided,
            a UTC-bucketed user activity summary is appended.
    """
    # C.3: surface negative savings rather than hiding the sign. When cache
    # writes outweigh read savings the "savings" is actually a net cost; never
    # clamp it to zero — a misleadingly cheerful $0.0000 would bury a real
    # signal that caching cost the user money on this run.
    _sav = totals["cache_savings"]
    if _sav >= 0:
        _sav_line = f"Cache savings vs no-cache baseline : ${_sav:.4f}"
    else:
        _sav_line = f"Cache cost vs no-cache baseline (writes > reads): +${abs(_sav):.4f}"
    lines = [
        "",
        _sav_line,
        f"Cache hit ratio (read / total input): {totals['cache_hit_pct']:.1f}%",
    ]
    if totals.get("total_cache_turns", 0) > 0:
        lines.append(
            f"Partial hit rate (read+write turns) : {totals['partial_hit_rate']:.1f}%  "
            f"[{totals['partial_hit_turns']:,} of {totals['total_cache_turns']:,} cache turns]"
        )
    if totals.get("cache_write_1h", 0) > 0:
        lines.append(
            f"Extra cost paid for 1h cache tier  : ${totals.get('extra_1h_cost', 0.0):.4f}"
        )
        pct_1h = 100 * totals["cache_write_1h"] / max(1, totals["cache_write"])
        lines.append(
            f"Cache TTL mix (1h share of writes) : {pct_1h:.1f}%  "
            f"[* in CacheWr column = includes 1h-tier cache write]"
        )
    if totals.get("thinking_turn_count", 0) > 0:
        lines.append(
            f"Extended thinking turns            : "
            f"{totals['thinking_turn_count']} of {totals.get('turns', 0)} "
            f"({totals.get('thinking_turn_pct', 0.0):.1f}%, "
            f"{(totals.get('content_blocks') or {}).get('thinking', 0)} blocks)"
        )
    if totals.get("tool_call_total", 0) > 0:
        top3 = totals.get("tool_names_top3") or []
        top3_str = ", ".join(top3) if top3 else "none"
        lines.append(
            f"Tool calls                         : "
            f"{totals['tool_call_total']} total, "
            f"{totals.get('tool_call_avg_per_turn', 0.0):.1f}/turn  "
            f"(top: {top3_str})"
        )
    if totals.get("advisor_call_count", 0) > 0:
        _adv_n = totals["advisor_call_count"]
        _adv_c = totals.get("advisor_cost_usd", 0.0)
        lines.append(
            f"Advisor calls                      : "
            f"{_adv_n} call{'s' if _adv_n != 1 else ''}  +${_adv_c:.4f}"
        )
    if models:
        lines.append("")
        lines.append("Models used:")
        total_turns = sum(int(i.get("turns", 0)) for i in models.values()) or 1
        total_cost  = sum(float(i.get("cost_usd", 0.0)) for i in models.values()) or 0.0
        for m, info in sorted(models.items(),
                              key=lambda x: -float(x[1].get("cost_usd", 0.0))):
            r = _sm()._pricing_for(m)
            cnt = int(info.get("turns", 0))
            cost = float(info.get("cost_usd", 0.0))
            t_pct = 100.0 * cnt / total_turns
            c_pct = (100.0 * cost / total_cost) if total_cost else 0.0
            lines.append(
                f"  {m:<40}  {cnt:>3} turns ({t_pct:>4.1f}%)  "
                f"${cost:.4f} ({c_pct:>4.1f}%)  "
                f"(${r['input']:.2f}/${r['output']:.2f}/${r['cache_read']:.2f}/${r['cache_write']:.2f} per 1M in/out/rd/wr)"
            )
    if time_of_day and time_of_day.get("message_count", 0) > 0:
        b = time_of_day["buckets"]
        lines.append("")
        lines.append(f"User prompts by time of day ({tz_label}):")
        lines.append(f"  Night (0\u20136):      {b.get('night', 0):>5,}")
        lines.append(f"  Morning (6\u201312):   {b.get('morning', 0):>5,}")
        lines.append(f"  Afternoon (12\u201318):{b.get('afternoon', 0):>5,}")
        lines.append(f"  Evening (18\u201324):  {b.get('evening', 0):>5,}")

        hod = time_of_day.get("hour_of_day")
        if hod and hod.get("total", 0) > 0:
            hours = hod["hours"]
            mx = max(hours) or 1
            lines.append("")
            lines.append(f"Hour-of-day ({tz_label}) — each \u2588 \u2248 {mx/20:.1f} prompts:")
            for h in range(24):
                bar = "\u2588" * int(hours[h] / mx * 20)
                lines.append(f"  {h:02d}:00  {hours[h]:>4,}  {bar}")

        wh = time_of_day.get("weekday_hour")
        if wh and wh.get("total", 0) > 0:
            row_totals = wh["row_totals"]
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            lines.append("")
            lines.append(f"Weekday totals ({tz_label}):")
            for i, d in enumerate(days):
                lines.append(f"  {d}:  {row_totals[i]:>5,}")

    if session_blocks:
        lines.append("")
        s7  = block_summary.get("trailing_7",  0) if block_summary else 0
        s14 = block_summary.get("trailing_14", 0) if block_summary else 0
        tot = block_summary.get("total", len(session_blocks)) if block_summary else len(session_blocks)
        lines.append(f"5-hour session blocks ({tot} total; "
                     f"{s7} in last 7d, {s14} in last 14d):")
        recent = session_blocks[-8:]
        for b in recent:
            anchor = b["anchor_iso"][:16].replace("T", " ")
            dur    = b["elapsed_min"]
            lines.append(
                f"  {anchor}Z  "
                f"dur={dur:>5.0f}m  "
                f"turns={b['turn_count']:>3}  "
                f"prompts={b['user_msg_count']:>3}  "
                f"${b['cost_usd']:>7.3f}"
            )
        if len(session_blocks) > len(recent):
            lines.append(f"  ... ({len(session_blocks) - len(recent)} earlier blocks omitted)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _session_duration_stats(session: dict) -> dict | None:
    """Per-session wall-clock + burn rate derived from turn timestamps.

    Returns None when fewer than 2 turns have usable timestamps. Burn rate
    metrics are clamped so a single-turn session doesn't divide by zero.
    """
    turns = session.get("turns", [])
    epochs = [_sm()._parse_iso_epoch(t.get("timestamp", "")) for t in turns]
    epochs = [e for e in epochs if e]
    if len(epochs) < 2:
        return None
    first, last = min(epochs), max(epochs)
    wall_sec    = last - first
    wall_min    = wall_sec / 60.0
    st          = session["subtotal"]
    minutes     = max(1e-6, wall_min)
    return {
        "first_epoch":  first,
        "last_epoch":   last,
        "wall_sec":     wall_sec,
        "wall_min":     wall_min,
        "tokens_per_min": st["total"] / minutes,
        "cost_per_min":   st["cost"]  / minutes,
        "turns":        st["turns"],
    }


def _build_session_duration_html(sessions: list[dict], tz_label: str,
                                  tz_offset_hours: float) -> str:
    """Build a per-session duration + burn-rate card.

    Shows the most-recent 10 sessions (newest first) with wall-clock time,
    turn count, total cost, tokens/min, and cost/min. Answers "how much
    am I spending per active minute" for a given session.
    """
    rows_data = []
    for s in sessions:
        stats = _session_duration_stats(s)
        if not stats:
            continue
        rows_data.append((s, stats))
    if not rows_data:
        return ""
    offset_sec = int(tz_offset_hours * 3600)

    def fmt_local(epoch: int) -> str:
        return datetime.fromtimestamp(
            epoch + offset_sec, tz=timezone.utc,
        ).strftime("%Y-%m-%d %H:%M")

    rows_data.sort(key=lambda x: x[1]["last_epoch"], reverse=True)
    rows_data = rows_data[:10]
    rows_html = []
    for s, st in rows_data:
        sid = s["session_id"][:8]
        rows_html.append(
            f'<tr><td class="mono">{sid}\u2026</td>'
            f'<td class="mono">{fmt_local(st["first_epoch"])}</td>'
            f'<td class="num mono">{_sm()._fmt_duration(st["wall_sec"])}</td>'
            f'<td class="num">{st["turns"]:,}</td>'
            f'<td class="num"><strong>${s["subtotal"]["cost"]:.3f}</strong></td>'
            f'<td class="num muted">{st["tokens_per_min"]:,.0f}</td>'
            f'<td class="num muted">${st["cost_per_min"]:.3f}</td></tr>'
        )
    return (
        f'<section class="section" id="session-duration-section">\n'
        f'  <div class="section-title"><h2>Session duration</h2>'
        f'<span class="hint">top 10 by wall time ({tz_label})</span></div>\n'
        f'  <div class="rollup" id="session-duration">\n'
        f'  <table>\n'
        f'    <thead><tr>\n'
        f'      <th>Session</th><th>First turn ({tz_label})</th>'
        f'<th class="num">Wall</th><th class="num">Turns</th>'
        f'<th class="num">Cost</th><th class="num">tok/min</th><th class="num">$/min</th>\n'
        f'    </tr></thead>\n'
        f'    <tbody>{"".join(rows_html)}</tbody>\n'
        f'  </table>\n  </div>\n</section>'
    )


def _fmt_delta_pct(cur: float, prev: float) -> tuple[str, str]:
    """Format the relative delta of ``cur`` vs ``prev`` as ``("+12.3%", color)``.

    When ``prev`` is zero, returns ``("new", "#8b949e")`` — don't render
    infinite percentages. Positive deltas are red for cost/turns (caller
    picks the color-flip); this helper just returns a magenta/green by sign.
    """
    if prev <= 0:
        return ("new" if cur > 0 else "\u2013", "#8b949e")
    delta = (cur - prev) / prev * 100.0
    sign = "+" if delta > 0 else ""
    color = "#f47067" if delta > 0 else "#58a6ff" if delta < 0 else "#8b949e"
    return (f"{sign}{delta:.1f}%", color)


def _build_weekly_rollup_html(rollup: dict) -> str:
    """Render a trailing-7d vs prior-7d comparison card.

    Returns empty string when there's no data (skips the section cleanly
    on brand-new projects).
    """
    if not rollup or not rollup.get("has_data"):
        return ""
    cur  = rollup["trailing_7d"]
    prev = rollup["prior_7d"]

    rows = []
    metrics = [
        ("Cost (USD)",       f"${cur['cost']:.2f}",          f"${prev['cost']:.2f}",          cur["cost"],          prev["cost"]),
        ("Assistant turns",  f"{cur['turns']:,}",            f"{prev['turns']:,}",            cur["turns"],         prev["turns"]),
        ("User prompts",     f"{cur['user_prompts']:,}",     f"{prev['user_prompts']:,}",     cur["user_prompts"],  prev["user_prompts"]),
        ("5h blocks",        f"{cur['blocks']:,}",           f"{prev['blocks']:,}",           cur["blocks"],        prev["blocks"]),
        ("Cache hit ratio",  f"{cur['cache_hit_pct']:.1f}%", f"{prev['cache_hit_pct']:.1f}%", cur["cache_hit_pct"], prev["cache_hit_pct"]),
        ("Partial hit rate", f"{cur.get('partial_hit_rate', 0.0):.1f}%", f"{prev.get('partial_hit_rate', 0.0):.1f}%", cur.get("partial_hit_rate", 0.0), prev.get("partial_hit_rate", 0.0)),
    ]
    for label, cur_s, prev_s, cur_v, prev_v in metrics:
        delta, color = _fmt_delta_pct(cur_v, prev_v)
        rows.append(
            f'<tr><td>{label}</td>'
            f'<td class="num"><strong>{cur_s}</strong></td>'
            f'<td class="num muted">{prev_s}</td>'
            f'<td class="num" style="color:{color}">{delta}</td></tr>'
        )

    return (
        '<section class="section" id="weekly-rollup-section">\n'
        '  <div class="section-title"><h2>Weekly rollup</h2>'
        '<span class="hint">trailing 7d vs prior 7d</span></div>\n'
        '  <div class="rollup" id="weekly-rollup">\n'
        '  <table>\n'
        '    <thead><tr>'
        '<th>Metric</th><th class="num">Last 7d</th>'
        '<th class="num">Prior 7d</th><th class="num">\u0394</th>'
        '</tr></thead>\n'
        f'    <tbody>{"".join(rows)}</tbody>\n'
        '  </table>\n  </div>\n</section>'
    )


def _build_session_blocks_html(
    blocks: list[dict], summary: dict, tz_label: str = "UTC",
    tz_offset_hours: float = 0.0,
) -> str:
    """Render 5-hour session blocks as a summary card + recent-blocks list.

    Includes a weekly-count card (trailing 7/14/30d) as the primary
    rate-limit-debugging signal, then the newest 12 blocks with duration,
    turn count, prompt count, cost, and session-count.
    """
    if not blocks:
        return ""
    offset_sec = int(tz_offset_hours * 3600)

    def fmt_local(epoch: int) -> str:
        return datetime.fromtimestamp(
            epoch + offset_sec, tz=timezone.utc,
        ).strftime("%Y-%m-%d %H:%M")

    s7  = summary.get("trailing_7",  0)
    s14 = summary.get("trailing_14", 0)
    s30 = summary.get("trailing_30", 0)
    tot = summary.get("total", len(blocks))
    recent = list(reversed(blocks[-12:]))

    # Determine max cost for the block-row bars (preview .block-row pattern)
    max_cost = max((b["cost_usd"] for b in recent), default=0.0) or 1.0
    block_rows = "".join(
        f'<div class="block-row">'
        f'<span class="label">{fmt_local(b["anchor_epoch"])}</span>'
        f'<div class="bar"><div class="bar-fill" '
        f'style="width:{min(100, int(b["cost_usd"] / max_cost * 100))}%"></div></div>'
        f'<span class="num mono">${b["cost_usd"]:.3f}</span>'
        f'<span class="num mono">{b["turn_count"]:,} turns</span>'
        f'</div>'
        for b in recent
    )

    # Kpi-style stat cards for the trailing-window counts
    stat_card = lambda label, value: (
        f'<div class="kpi cat-time" style="min-height:auto;padding:12px 16px;min-width:140px">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-val">{value}</div></div>'
    )

    return (
        '<section class="section" id="session-blocks-section">\n'
        '  <div class="section-title"><h2>5-hour session blocks</h2>'
        f'<span class="hint">recent blocks · {tz_label}</span></div>\n'
        '  <div id="session-blocks" class="blocks">\n'
        '  <div class="grid kpi-grid" '
        'style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin-bottom:16px">\n'
        f'    {stat_card("Last 7 days", s7)}\n'
        f'    {stat_card("Last 14 days", s14)}\n'
        f'    {stat_card("Last 30 days", s30)}\n'
        f'    {stat_card("All time", tot)}\n'
        '  </div>\n'
        f'  {block_rows}\n'
        '  </div>\n</section>'
    )


def _build_tod_epoch_blob(tod: dict) -> str:
    """Serialize ``time_of_day.epoch_secs`` once as a shared JSON blob.

    The hour-of-day, punchcard, and day-part heatmap sections all rebucket
    the same epoch-seconds array client-side. Embedding it three times
    (one ``var TS=[...]`` per section) tripled the largest data payload in
    the page, so the array is emitted once here and each section reads it
    via ``JSON.parse``. Callers must place this blob BEFORE the first of
    those sections in document order — their IIFEs run at parse time.

    Returns "" when there are no user timestamps, matching the three
    sections' own empty-state behaviour (no sections ⇒ no blob needed;
    the array is plain integers, so no HTML escaping is required).
    """
    epoch_secs = tod.get("epoch_secs", [])
    if not epoch_secs:
        return ""
    return ('<script type="application/json" id="tod-epoch-secs">'
            + json.dumps(epoch_secs, separators=(",", ":"))
            + "</script>")


# Shared JS snippet reading the blob emitted by ``_build_tod_epoch_blob``.
_TOD_EPOCH_READ_JS = (
    "JSON.parse(document.getElementById('tod-epoch-secs').textContent)"
)


def _build_hour_of_day_html(tod: dict, tz_label: str = "UTC",
                            default_offset_hours: float = 0.0,
                            peak: dict | None = None) -> str:
    """Build a 24-hour bar chart of user prompts, self-contained HTML + CSS + JS.

    Client-side JS rebuckets to any offset chosen from the tz dropdown. When
    ``peak`` is supplied (see ``_build_peak``), overlays a translucent band
    behind the bars in the peak-hours range, and reshifts the band when the
    user changes display tz.
    """
    epoch_secs = tod.get("epoch_secs", [])
    if not epoch_secs:
        return ""
    tz_options = _tz_dropdown_options(default_offset_hours, tz_label)

    peak_json = "null"
    peak_legend = ""
    if peak:
        peak_json = json.dumps({
            "start":   peak["start"],
            "end":     peak["end"],
            "tz_off":  peak["tz_offset_hours"],
            "tz_label": peak["tz_label"],
        }, separators=(",", ":"))
        peak_legend = (
            f'<span style="color:#8b949e;font-size:11px;display:inline-flex;'
            f'align-items:center;gap:6px">'
            f'<span style="display:inline-block;width:10px;height:10px;'
            f'background:rgba(239,197,75,0.25);border:1px solid rgba(239,197,75,0.6);'
            f'border-radius:2px"></span>'
            f'Peak ({peak["start"]:02d}\u2013{peak["end"]:02d} {peak["tz_label"]}, {peak["note"]})'
            f'</span>'
        )

    return f"""\
<section class="section" id="hod-section">
  <div class="section-title"><h2>Hour of day</h2>
    <span class="hint">user messages</span></div>
  <div id="hod-chart" class="chart-card">
  <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;flex-wrap:wrap">
    <select id="hod-tz" class="tod-tz" style="background:var(--bg);color:var(--fg);
            border:1px solid var(--border);border-radius:6px;padding:6px 10px;
            font-family:'JetBrains Mono',monospace;font-size:11px;cursor:pointer">{tz_options}</select>
    <span class="mono muted" style="font-size:11px">Peak:
      <strong id="hod-peak" class="mono" style="opacity:1">-</strong></span>
    {peak_legend}
  </div>
  <div id="hod-wrap" style="position:relative;height:160px;
       border-bottom:1px solid var(--border-dim);padding-bottom:2px">
    <div id="hod-peak-band1" style="position:absolute;top:0;bottom:0;
         background:rgba(239,197,75,0.12);border-left:1px dashed rgba(239,197,75,0.35);
         border-right:1px dashed rgba(239,197,75,0.35);display:none;pointer-events:none"></div>
    <div id="hod-peak-band2" style="position:absolute;top:0;bottom:0;
         background:rgba(239,197,75,0.12);border-left:1px dashed rgba(239,197,75,0.35);
         border-right:1px dashed rgba(239,197,75,0.35);display:none;pointer-events:none"></div>
    <div id="hod-bars" style="position:relative;display:flex;align-items:flex-end;
         gap:2px;height:100%"></div>
  </div>
  <div class="mono muted" style="display:flex;gap:2px;margin-top:6px;font-size:10px">
    {"".join(f'<div style="flex:1;text-align:center">{h:02d}</div>' for h in range(24))}
  </div>
  </div>
</section>
<script>
(function(){{
  var TS={_TOD_EPOCH_READ_JS};
  var PEAK={peak_json};
  var bars=document.getElementById('hod-bars');
  var bs=[];
  for(var i=0;i<24;i++){{
    var b=document.createElement('div');
    b.style.cssText='flex:1;background:var(--accent);border-radius:2px 2px 0 0;'+
      'min-height:1px;transition:height 0.25s ease;position:relative;opacity:.9';
    b.title=(i<10?'0':'')+i+':00';
    bars.appendChild(b);bs.push(b);
  }}
  function bandPct(startHour,endHour){{
    return {{left:(startHour/24*100)+'%',width:((endHour-startHour)/24*100)+'%'}};
  }}
  function positionPeak(displayOff){{
    var b1=document.getElementById('hod-peak-band1');
    var b2=document.getElementById('hod-peak-band2');
    if(!PEAK){{b1.style.display='none';b2.style.display='none';return;}}
    var shift=displayOff-PEAK.tz_off;
    var s=((PEAK.start+shift)%24+24)%24;
    var e=((PEAK.end  +shift)%24+24)%24;
    if(e===0)e=24;
    if(s<e){{
      var p=bandPct(s,e);
      b1.style.left=p.left;b1.style.width=p.width;b1.style.display='block';
      b2.style.display='none';
    }}else{{
      // wraps midnight: split into [s,24) + [0,e)
      var p1=bandPct(s,24),p2=bandPct(0,e);
      b1.style.left=p1.left;b1.style.width=p1.width;b1.style.display='block';
      b2.style.left=p2.left;b2.style.width=p2.width;b2.style.display='block';
    }}
  }}
  function render(off){{
    var c=new Array(24);for(var i=0;i<24;i++)c[i]=0;
    var s=off*3600;
    for(var j=0;j<TS.length;j++){{
      var h=(((TS[j]+s)%86400)+86400)%86400/3600|0;
      c[h]++;
    }}
    var mx=Math.max.apply(null,c)||1;
    var peak=0,peakH=0;
    for(var k=0;k<24;k++){{
      bs[k].style.height=(c[k]/mx*100)+'%';
      bs[k].title=(k<10?'0':'')+k+':00  '+c[k].toLocaleString()+' prompts';
      if(c[k]>peak){{peak=c[k];peakH=k;}}
    }}
    document.getElementById('hod-peak').textContent=
      peak?((peakH<10?'0':'')+peakH+':00 ('+peak.toLocaleString()+')'):'-';
    positionPeak(off);
  }}
  var sel=document.getElementById('hod-tz');
  sel.addEventListener('change',function(){{render(+this.value);}});
  render(+sel.value);
}})();
</script>"""


def _build_punchcard_html(tod: dict, tz_label: str = "UTC",
                          default_offset_hours: float = 0.0) -> str:
    """Build a 7x24 weekday-by-hour punchcard, GitHub-style dots.

    Rows: Mon..Sun.  Columns: 00..23 in the selected tz.  Dot radius scales
    with the cell count; empty cells render as faint dots.
    """
    epoch_secs = tod.get("epoch_secs", [])
    if not epoch_secs:
        return ""
    tz_options = _tz_dropdown_options(default_offset_hours, tz_label)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cells = []
    for r in range(7):
        row = [f'<div class="punch-day">{days[r]}</div>']
        for h in range(24):
            row.append(f'<div class="punch-cell" data-r="{r}" data-h="{h}">'
                       f'<div class="punch-dot"></div></div>')
        cells.append('<div class="punch-row">' + "".join(row) + "</div>")
    hour_header = ('<div class="punch-row punch-head">'
                   '<div class="punch-day"></div>'
                   + "".join(f'<div class="punch-hour">{h:02d}</div>' for h in range(24))
                   + '</div>')
    return f"""\
<section class="section">
  <div class="section-title"><h2>Weekday \u00d7 hour</h2>
    <span class="hint">punchcard of user messages</span></div>
  <div id="punchcard" class="punch">
    <div class="punch-head-row">
      <select id="pc-tz" class="tz-select">{tz_options}</select>
      <span class="muted">Busiest: <strong id="pc-busy" class="mono">-</strong></span>
    </div>
    <div class="punch-grid">
      {hour_header}
      {"".join(cells)}
    </div>
  </div>
</section>
<script>
(function(){{
  var TS={_TOD_EPOCH_READ_JS};
  var cells=document.querySelectorAll('#punchcard .punch-cell');
  function render(off){{
    var m=[];for(var r=0;r<7;r++){{m.push(new Array(24));for(var k=0;k<24;k++)m[r][k]=0;}}
    var s=off*3600,mx=0,busyR=0,busyH=0;
    for(var i=0;i<TS.length;i++){{
      var t=TS[i]+s;
      var days=Math.floor(t/86400);
      var w=((days+3)%7+7)%7;
      var h=((t%86400)+86400)%86400/3600|0;
      m[w][h]++;
      if(m[w][h]>mx){{mx=m[w][h];busyR=w;busyH=h;}}
    }}
    mx=mx||1;
    var accent=getComputedStyle(document.body).getPropertyValue('--accent').trim()||'#A58BFF';
    var dim=getComputedStyle(document.body).getPropertyValue('--border').trim()||'#30363d';
    cells.forEach(function(el){{
      var r=+el.dataset.r,h=+el.dataset.h,v=m[r][h];
      var dot=el.firstChild;
      if(v===0){{
        dot.style.width='2px';dot.style.height='2px';dot.style.background=dim;
      }}else{{
        var sz=Math.max(4,Math.min(14,4+v/mx*10));
        dot.style.width=sz+'px';dot.style.height=sz+'px';dot.style.background=accent;
        el.title=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][r]+' '+(h<10?'0':'')+h+':00 \u2014 '+v;
      }}
    }});
    var DAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    document.getElementById('pc-busy').textContent=
      mx>1||(mx===1&&TS.length)?(DAYS[busyR]+' '+(busyH<10?'0':'')+busyH+':00 ('+mx+')'):'-';
  }}
  var sel=document.getElementById('pc-tz');
  sel.addEventListener('change',function(){{render(+this.value);}});
  render(+sel.value);
}})();
</script>"""


def _tz_dropdown_options(default_offset_hours: float, tz_label: str) -> str:
    """Build the <option> list for the tz dropdown used by hod/punchcard/heatmap.

    The resolved display tz (from CLI/env/auto-detect) is always present as
    the selected option and always first.  A small fixed set of common zones
    is appended below; duplicates are skipped.
    """
    def fmt(off: float) -> str:
        sign = "+" if off >= 0 else "\u2212"
        return f"UTC{sign}{abs(off):g}"
    items = [(default_offset_hours, f"{tz_label} ({fmt(default_offset_hours)})", True)]
    commons = [(0.0, "UTC"), (-8.0, "PT"), (-5.0, "ET"),
               (1.0, "CET"), (5.5, "IST"), (10.0, "AEST")]
    seen = {round(default_offset_hours, 2)}
    for off, label in commons:
        key = round(off, 2)
        if key in seen:
            continue
        seen.add(key)
        items.append((off, f"{label} ({fmt(off)})", False))
    return "".join(
        f'<option value="{off:g}"{" selected" if sel else ""}>{lbl}</option>'
        for off, lbl, sel in items
    )


def _build_tod_heatmap_html(tod: dict, tz_label: str = "UTC",
                            default_offset_hours: float = 0.0) -> str:
    """Build the Time-of-Day heatmap as self-contained HTML + CSS + JS.

    Renders a horizontal bar chart with four period rows (Night, Morning,
    Afternoon, Evening), a timezone dropdown pre-selected to the report's
    resolved display tz, and client-side re-bucketing via JavaScript.

    No Highcharts dependency — uses pure HTML/CSS bars with JS-driven width
    updates.  The epoch-seconds array is read from the shared blob emitted
    by ``_build_tod_epoch_blob`` (one copy serves all three time-of-day
    sections); bucketing uses ``(((epoch + off) % 86400) + 86400) % 86400``
    (the standard double-modulo idiom) to guarantee non-negative results
    even when JS's sign-preserving ``%`` encounters negative operands.

    Args:
        tod: Report's ``time_of_day`` dict containing ``epoch_secs`` and
            ``buckets``.

    Returns:
        HTML string for embedding in the full report page.  Returns an empty
        string if no user timestamps are available.
    """
    epoch_secs = tod.get("epoch_secs", [])
    if not epoch_secs:
        return ""
    tz_options = _tz_dropdown_options(default_offset_hours, tz_label)

    return f"""\
<section class="section">
  <div class="section-title"><h2>User messages by time of day</h2>
    <span class="hint">day-part distribution</span></div>
  <div id="tod-container" class="tod">
    <div class="tod-head">
      <select id="tod-tz" class="tod-tz">{tz_options}</select>
      <span class="muted">Total: <strong id="tod-total" class="tod-total mono">0</strong></span>
    </div>
    <div class="tod-rows">
      <div class="tod-row">
        <span class="tod-label">Morning (6\u201312)</span>
        <div class="tod-track"><div id="tod-bar-morning" class="tod-fill"></div></div>
        <span id="tod-cnt-morning" class="tod-cnt mono">0</span>
      </div>
      <div class="tod-row">
        <span class="tod-label">Afternoon (12\u201318)</span>
        <div class="tod-track"><div id="tod-bar-afternoon" class="tod-fill"></div></div>
        <span id="tod-cnt-afternoon" class="tod-cnt mono">0</span>
      </div>
      <div class="tod-row">
        <span class="tod-label">Evening (18\u201324)</span>
        <div class="tod-track"><div id="tod-bar-evening" class="tod-fill"></div></div>
        <span id="tod-cnt-evening" class="tod-cnt mono">0</span>
      </div>
      <div class="tod-row">
        <span class="tod-label">Night (0\u20136)</span>
        <div class="tod-track"><div id="tod-bar-night" class="tod-fill"></div></div>
        <span id="tod-cnt-night" class="tod-cnt mono">0</span>
      </div>
    </div>
  </div>
</section>
<script>
(function(){{
  var TS={_TOD_EPOCH_READ_JS};
  var KEYS=['night','morning','afternoon','evening'];

  function bucket(off){{
    var c=[0,0,0,0],s=off*3600;
    for(var i=0;i<TS.length;i++){{
      var h=(((TS[i]+s)%86400)+86400)%86400/3600|0;
      c[h<6?0:h<12?1:h<18?2:3]++;
    }}
    return c;
  }}

  function render(off){{
    var c=bucket(off);
    var mx=Math.max(1,Math.max.apply(null,c));
    var total=0;
    for(var i=0;i<4;i++){{
      var pct=c[i]/mx*100;
      document.getElementById('tod-bar-'+KEYS[i]).style.width=pct+'%';
      document.getElementById('tod-cnt-'+KEYS[i]).textContent=c[i].toLocaleString();
      total+=c[i];
    }}
    document.getElementById('tod-total').textContent=total.toLocaleString();
  }}

  var sel=document.getElementById('tod-tz');
  sel.addEventListener('change',function(){{render(+this.value);}});
  render(+sel.value);
}})();
</script>"""


def _fmt_cost(v: float) -> str:
    return f"${float(v or 0.0):.4f}"


def _build_by_skill_html(rows: list[dict],
                          heading: str = "Skills &amp; slash commands",
                          hint: str = "aggregated across this report scope · "
                                      "sticky attribution to slash-prefixed prompts") -> str:
    """Render the ``by_skill`` aggregation as a sortable section. Returns "" when empty."""
    if not rows:
        return ""
    body_rows: list[str] = []
    for r in rows:
        name = html_mod.escape(r.get("name") or "")
        body_rows.append(
            f'<tr>'
            f'<td><code>{name}</code></td>'
            f'<td class="num">{int(r.get("invocations", 0)):,}</td>'
            f'<td class="num">{int(r.get("turns_attributed", 0)):,}</td>'
            f'<td class="num">{int(r.get("input", 0)):,}</td>'
            f'<td class="num">{float(r.get("cache_hit_pct", 0.0)):.1f}%</td>'
            f'<td class="num">{int(r.get("output", 0)):,}</td>'
            f'<td class="num">{int(r.get("total_tokens", 0)):,}</td>'
            f'<td class="cost">{_fmt_cost(r.get("cost_usd", 0.0))}</td>'
            f'<td class="num">{float(r.get("pct_total_cost", 0.0)):.2f}%</td>'
            f'</tr>'
        )
    return (
        f'<section class="section">\n'
        f'<div class="section-title"><h2>{heading}</h2>'
        f'<span class="hint">{html_mod.escape(hint)}</span></div>\n'
        f'<table class="models-table">\n'
        f'<thead><tr>'
        f'<th>Name</th>'
        f'<th class="num">Invocations</th>'
        f'<th class="num">Turns</th>'
        f'<th class="num">Input</th>'
        f'<th class="num">% cached</th>'
        f'<th class="num">Output</th>'
        f'<th class="num">Total</th>'
        f'<th class="num">Cost $</th>'
        f'<th class="num">% of total</th>'
        f'</tr></thead>\n'
        f'<tbody>{"".join(body_rows)}</tbody>\n'
        f'</table>\n'
        f'</section>'
    )


def _fmt_secs_short(secs: float) -> str:
    """Compact human duration: ``42s`` / ``7m`` / ``2h 5m``. ``0`` → em-dash."""
    s = int(secs or 0)
    if s <= 0:
        return "&mdash;"
    if s < 90:
        return f"{s}s"
    m = s // 60
    if m < 120:
        return f"{m}m"
    h, mm = divmod(m, 60)
    return f"{h}h {mm}m" if mm else f"{h}h"


def _build_request_units_html(units: list[dict],
                              total_cost: float = 0.0,
                              limit: int = 50) -> str:
    """Render the deterministic per-request breakdown. Returns "" when ≤1 unit.

    Each row is one **request unit** — a user prompt plus all the work it
    drove (follow-up tool turns + attributed subagents). This is a
    per-utterance carve-up, NOT semantic tasks (the heading says so); the
    optional ``task-breakdown`` skill groups these into labelled tasks on a
    separate companion page. Rows link to the anchor turn's drawer, mirroring
    the Prompts table. Sorted by combined cost; capped at ``limit`` with a
    "+N more" note so a long session stays scannable.
    """
    if not units or len(units) <= 1:
        return ""
    rows = sorted(units, key=lambda u: -float(u.get("combined_cost_usd", 0.0)))
    shown = rows[:limit]
    body_rows: list[str] = []
    for u in shown:
        sid8 = (u.get("session_id") or "")[:8]
        key = f'{sid8}-{u.get("anchor_index")}'
        key_esc = html_mod.escape(key)
        snippet = html_mod.escape(u.get("prompt_snippet") or "") or "&mdash;"
        badges = ""
        if u.get("slash_command"):
            badges += (f' <span class="prompts-slash">'
                       f'{html_mod.escape(u["slash_command"])}</span>')
        if u.get("multi_intent_possible"):
            badges += (' <span class="ru-badge" title="This single prompt may '
                       'bundle more than one ask — the deterministic unit keeps '
                       'them together; the task-breakdown skill can split it.">'
                       'multi-ask?</span>')
        if float(u.get("subagent_cost_usd", 0.0)) > 0:
            badges += (f' <span class="prompts-subagent" title="Includes '
                       f'${u["subagent_cost_usd"]:.4f} of attributed subagent '
                       f'work in this request’s combined cost.">+subagent</span>')
        tools = list(u.get("tool_histogram") or {})
        if tools:
            tools_str = ", ".join(html_mod.escape(n) for n in tools[:3])
            if len(tools) > 3:
                tools_str += f" +{len(tools) - 3}"
        else:
            tools_str = "&mdash;"
        risk = int(u.get("risk_turn_count", 0))
        reread = int(u.get("reread_path_count", 0))
        cbreaks = int(u.get("cache_break_count", 0))
        waste_bits: list[str] = []
        if risk:
            waste_bits.append(f'<span class="ru-risk" title="{risk} turn(s) '
                              f'flagged potentially wasteful (retry / dead-end / '
                              f're-read / verbose edit)">&#9888; {risk}</span>')
        if reread:
            waste_bits.append(f'<span class="muted" title="{reread} file path(s) '
                              f're-read within this request">&#8635;{reread}</span>')
        if cbreaks:
            waste_bits.append(f'<span class="muted" title="{cbreaks} cache-break '
                              f'turn(s) in this request">&#10005;{cbreaks}</span>')
        waste_str = " ".join(waste_bits) if waste_bits else "&mdash;"
        pct = (100.0 * float(u.get("combined_cost_usd", 0.0)) / total_cost
               if total_cost else 0.0)
        body_rows.append(
            f'<tr data-turn="{key_esc}" tabindex="0">'
            f'<td class="num"><a class="prompt-turn-link" '
            f'href="#turn-{key_esc}">#{u.get("anchor_index")}</a></td>'
            f'<td><div class="prompt-text truncate">{snippet}{badges}</div></td>'
            f'<td class="num">{int(u.get("turn_count", 0)):,}</td>'
            f'<td class="cost">{_fmt_cost(u.get("combined_cost_usd", 0.0))}</td>'
            f'<td class="num">{pct:.1f}%</td>'
            f'<td class="num">{int(u.get("total_tokens", 0)):,}</td>'
            f'<td class="tools">{tools_str}</td>'
            f'<td class="num">{waste_str}</td>'
            f'<td class="num">{_fmt_secs_short(u.get("idle_gap_before_seconds", 0))}</td>'
            f'</tr>'
        )
    more = ""
    if len(rows) > limit:
        more = (f'<span class="hint">&middot; showing top {limit} of '
                f'{len(rows)} requests by cost</span>')
    return (
        f'<section class="section">\n'
        f'<div class="section-title"><h2>Per-request breakdown</h2>'
        f'<span class="hint">one row per user prompt &amp; all the work it drove '
        f'(follow-up turns + subagents) &middot; <strong>per-request, not '
        f'semantic tasks</strong> &middot; click a row to open the turn drawer'
        f'</span>{more}</div>\n'
        f'<table class="models-table">\n'
        f'<thead><tr>'
        f'<th>Turn</th><th>Request</th>'
        f'<th class="num">Turns</th>'
        f'<th class="num">Cost $</th>'
        f'<th class="num">% of total</th>'
        f'<th class="num">Tokens</th>'
        f'<th>Tools</th>'
        f'<th class="num" title="Potentially-wasteful signals in this request: '
        f'&#9888; risky turns, &#8635; file re-reads, &#10005; cache breaks">'
        f'Waste</th>'
        f'<th class="num" title="Idle wall-clock gap before this request '
        f'started">Idle</th>'
        f'</tr></thead>\n'
        f'<tbody>{"".join(body_rows)}</tbody>\n'
        f'</table>\n'
        f'</section>'
    )


def _build_by_subagent_type_html(rows: list[dict],
                                   heading: str = "Subagent types",
                                   subagents_included: bool = True) -> str:
    """Render ``by_subagent_type`` as a sortable section. Returns "" when empty.

    When the loader was invoked without ``--include-subagents``, token
    columns show only the *spawn-turn* contribution (zero for most rows).
    A footer note is rendered so users know to enable the flag for
    accurate per-type cost when relevant.
    """
    if not rows:
        return ""
    # v1.26.0: only render the warm-up columns when the loader actually
    # observed per-invocation data. With ``--no-include-subagents`` every
    # row's ``invocation_count`` is 0 and the columns would be a wall of
    # zeros; hiding them keeps the table readable.
    show_warmup = subagents_included and any(
        int(r.get("invocation_count", 0)) > 0 for r in rows
    )
    body_rows: list[str] = []
    for r in rows:
        name = html_mod.escape(r.get("name") or "")
        warmup_cells = ""
        if show_warmup:
            inv_n = int(r.get("invocation_count", 0))
            if inv_n > 0:
                warmup_cells = (
                    f'<td class="num" title="Median first-turn cost / total '
                    f'invocation cost across {inv_n} invocation'
                    f'{"s" if inv_n != 1 else ""} of this type. '
                    f'High = short-lived agents pay setup tax without amortising.">'
                    f'{float(r.get("first_turn_share_pct", 0.0)):.1f}%</td>'
                    f'<td class="num" title="Fraction of invocations where '
                    f'turn ≥2 read from cache (system-prompt cache write paid '
                    f'back at least once).">'
                    f'{float(r.get("sp_amortisation_pct", 0.0)):.1f}%</td>'
                )
            else:
                warmup_cells = (
                    '<td class="num muted">&ndash;</td>'
                    '<td class="num muted">&ndash;</td>'
                )
        body_rows.append(
            f'<tr>'
            f'<td><code>{name}</code></td>'
            f'<td class="num">{int(r.get("spawn_count", 0)):,}</td>'
            f'<td class="num">{int(r.get("turns_attributed", 0)):,}</td>'
            f'<td class="num">{int(r.get("input", 0)):,}</td>'
            f'<td class="num">{float(r.get("cache_hit_pct", 0.0)):.1f}%</td>'
            f'<td class="num">{int(r.get("output", 0)):,}</td>'
            f'<td class="num">{int(r.get("total_tokens", 0)):,}</td>'
            f'<td class="num">{float(r.get("avg_tokens_per_call", 0.0)):,.0f}</td>'
            f'<td class="cost">{_fmt_cost(r.get("cost_usd", 0.0))}</td>'
            f'<td class="num">{float(r.get("pct_total_cost", 0.0)):.2f}%</td>'
            f'{warmup_cells}'
            f'</tr>'
        )
    hint = ("aggregated across this report scope"
            if subagents_included else
            "spawn-count only · pass --include-subagents for full cost rollup")
    warmup_headers = (
        '<th class="num" title="Median fraction of an invocation\'s cost spent '
        'on its first turn (system-prompt warm-up).">First-turn %</th>'
        '<th class="num" title="Fraction of invocations whose turn ≥2 read '
        'from cache (system-prompt cache write paid back).">SP amortised %</th>'
    ) if show_warmup else ""
    return (
        f'<section class="section">\n'
        f'<div class="section-title"><h2>{heading}</h2>'
        f'<span class="hint">{html_mod.escape(hint)}</span></div>\n'
        f'<table class="models-table">\n'
        f'<thead><tr>'
        f'<th>Subagent type</th>'
        f'<th class="num">Spawns</th>'
        f'<th class="num">Turns</th>'
        f'<th class="num">Input</th>'
        f'<th class="num">% cached</th>'
        f'<th class="num">Output</th>'
        f'<th class="num">Total</th>'
        f'<th class="num">Avg / call</th>'
        f'<th class="num">Cost $</th>'
        f'<th class="num">% of total</th>'
        f'{warmup_headers}'
        f'</tr></thead>\n'
        f'<tbody>{"".join(body_rows)}</tbody>\n'
        f'</table>\n'
        f'</section>'
    )


def _fmt_workflow_duration(ms: int) -> str:
    """Human-readable wall-clock from a millisecond count (e.g. 1702105 →
    ``28m 22s``). Returns ``&ndash;`` for non-positive input."""
    s = int(ms) // 1000
    if s <= 0:
        return "&ndash;"
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m {sec}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def _workflow_model_label(models: dict) -> str:
    """Collapse a ``{model: turn_count}`` map to a single display label:
    the sole model, or ``"<dominant> +N"`` when more than one ran."""
    if not models:
        return "&ndash;"
    items = sorted(models.items(), key=lambda kv: -kv[1])
    top = items[0][0]
    if len(items) == 1:
        return html_mod.escape(top)
    return f'{html_mod.escape(top)} <span class="muted">+{len(items) - 1}</span>'


def _workflow_companion_css() -> str:
    """Companion-only CSS layered on top of :func:`_theme_css`.

    Every colour is a ``var(--…)`` token defined identically across all four
    ``body.theme-*`` blocks (``--surface``/``--border``/``--accent``/
    ``--fg-dim``/``--surface-deep``/``--border-dim``), so the deep-dive page
    themes automatically when the switcher toggles the body class — no
    per-theme override blocks. Generic ``th``/``td`` colours come from
    :func:`_theme_css` element rules; this only adds layout + the run
    accordion + summary chips.
    """
    return """<style>
.wf-summary-cards{margin:0 0 4px}
.wf-intro{font-size:12px;opacity:.7;margin:0 0 20px}
.wf-run{border:1px solid var(--border);border-radius:12px;margin:12px 0;background:var(--surface);overflow:hidden}
.wf-run>summary{cursor:pointer;list-style:none;padding:13px 18px;display:flex;align-items:center;flex-wrap:wrap;gap:10px;font-size:13px}
.wf-run>summary::-webkit-details-marker{display:none}
.wf-run>summary::before{content:"\\25B8";color:var(--accent);font-size:11px;transition:transform .15s ease;flex:none}
.wf-run[open]>summary::before{transform:rotate(90deg)}
.wf-run>summary strong{font-family:'Inter Tight','Inter',sans-serif;font-weight:600;font-size:14px}
.wf-chips{display:flex;flex-wrap:wrap;gap:6px;margin-left:auto}
.wf-chip{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.04em;padding:2px 9px;border-radius:999px;background:var(--surface-deep);border:1px solid var(--border);color:var(--fg-dim);white-space:nowrap}
.wf-chip.cost{color:var(--accent)}
.wf-chip.ok{color:#3fb950;border-color:rgba(63,185,80,.4)}
.wf-chip.amber{color:#d29922;border-color:rgba(210,153,34,.4)}
.wf-chip.warn{color:#f85149;border-color:rgba(248,81,73,.4)}
.wf-body{padding:0 18px 16px}
.wf-phase{margin-top:16px}
.wf-phase>h3{margin:0 0 6px;font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);opacity:.9}
table.wf-table{width:100%;border-collapse:collapse;font-family:'JetBrains Mono',monospace;font-size:12px}
table.wf-table th,table.wf-table td{padding:6px 10px;text-align:left;vertical-align:top}
table.wf-table th.num,table.wf-table td.num,table.wf-table td.cost{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.wf-table td.cost{color:var(--accent)}
table.wf-table code{background:var(--surface-deep);border:1px solid var(--border-dim);padding:1px 6px;border-radius:5px;font-size:11px}
table.wf-table tr.preview td{padding-top:0;padding-bottom:11px;font-size:11px;line-height:1.5}
.wf-empty{opacity:.55;font-size:12px;font-style:italic;padding:2px 0 6px}
table.wf-table tr.req-row{cursor:pointer}
table.wf-table tr.req-row:focus{outline:1px solid var(--accent);outline-offset:-1px}
table.wf-table tr.req-row:hover>td{background:var(--surface-deep)}
.req-caret{display:inline-block;color:var(--accent);font-size:9px;margin-right:6px;transition:transform .15s ease}
table.wf-table tr.req-row.open .req-caret{transform:rotate(90deg)}
table.wf-table tr.req-turns>td{padding:0 10px 10px 24px;background:var(--surface)}
table.turn-subtable{width:100%;border-collapse:collapse;font-family:'JetBrains Mono',monospace;font-size:11px;border-left:2px solid var(--border)}
table.turn-subtable th,table.turn-subtable td{padding:4px 8px;text-align:left;vertical-align:top;color:var(--fg-dim)}
table.turn-subtable th.num,table.turn-subtable td.num,table.turn-subtable td.cost{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.turn-subtable td.cost{color:var(--accent)}
.sub-tag{font-size:9px;letter-spacing:.04em;padding:1px 5px;border-radius:999px;background:var(--surface-deep);border:1px solid var(--border-dim);color:var(--fg-dim);margin-left:5px}
.turn-risk{color:#d29922;margin-left:5px}
</style>"""


def _build_workflow_companion_html(report: dict,
                                   nav_sibling: str | None = None) -> str:
    """Standalone, theme-aware deep-dive page for a report's dynamic workflows.

    Reuses the main report's full page shell (:func:`_theme_css`, the
    Beacon/Console/Lattice/Pulse switcher, and the head/body bootstrap JS) so
    the companion matches the dashboard/detail pages and the picked theme
    persists across navigation via ``localStorage['sm_theme']``. One
    collapsible ``<details class="wf-run">`` per run (native accordion — no
    custom JS) with a phase → agent timeline. Per-agent token/cost are exact
    (grafted from transcripts in ``_build_by_workflow``); labels, previews,
    phases and tool-calls come from the run journal. Returns "" when the
    report has no workflows.
    """
    rows = report.get("by_workflow", []) or []
    if not rows:
        return ""
    blocks: list[str] = []
    for r in rows:
        name = html_mod.escape(r.get("workflow_name") or r.get("run_id") or "")
        status = html_mod.escape(r.get("status") or "")
        status_cls = "ok" if status == "completed" else ""
        proj = html_mod.escape(r.get("project") or "")
        proj_bit = f'<span class="muted">{proj}</span>' if proj else ""
        chips = (
            '<span class="wf-chips">'
            f'<span class="wf-chip">{int(r.get("agents", 0)):,} agents</span>'
            f'<span class="wf-chip cost">{_fmt_cost(r.get("cost_usd", 0.0))}</span>'
            f'<span class="wf-chip">{int(r.get("total_tokens", 0)):,} tok</span>'
            f'<span class="wf-chip">{_fmt_workflow_duration(int(r.get("duration_ms", 0)))}</span>'
            f'<span class="wf-chip {status_cls}">{status or "&ndash;"}</span>'
            '</span>'
        )
        summary = f'<summary><strong>{name}</strong>{proj_bit}{chips}</summary>'
        # Group agents by phase for the timeline.
        agents = r.get("agent_details") or []
        by_phase: dict = {}
        for a in agents:
            by_phase.setdefault(int(a.get("phaseIndex") or 0), []).append(a)
        phase_titles = {i + 1: (p.get("title") or "")
                        for i, p in enumerate(r.get("phases") or [])}
        phase_html: list[str] = []
        for pidx in sorted(by_phase):
            ptitle = html_mod.escape(phase_titles.get(pidx, f"Phase {pidx}"))
            head = f"Phase {pidx}" + (f": {ptitle}" if ptitle else "")
            agent_rows = []
            for a in sorted(by_phase[pidx],
                            key=lambda x: -float(x.get("transcript_cost") or 0.0)):
                label = html_mod.escape(a.get("label") or a.get("agentId") or "")
                model = html_mod.escape(a.get("model") or "")
                state = html_mod.escape(a.get("state") or "")
                preview = html_mod.escape((a.get("resultPreview") or "")[:300])
                preview_row = (
                    f'<tr class="preview"><td colspan="7"><span class="muted">{preview}</span></td></tr>'
                    if preview else ""
                )
                agent_rows.append(
                    f'<tr>'
                    f'<td><code>{label}</code></td>'
                    f'<td>{model}</td>'
                    f'<td class="num">{int(a.get("transcript_tokens", 0)):,}</td>'
                    f'<td class="cost">{_fmt_cost(a.get("transcript_cost", 0.0))}</td>'
                    f'<td class="num">{int(a.get("toolCalls", 0)):,}</td>'
                    f'<td class="num">{_fmt_workflow_duration(int(a.get("durationMs", 0)))}</td>'
                    f'<td class="muted">{state}</td>'
                    f'</tr>{preview_row}'
                )
            body = ("".join(agent_rows)
                    or '<tr><td colspan="7" class="wf-empty">No agent transcripts.</td></tr>')
            phase_html.append(
                f'<div class="wf-phase"><h3>{head}</h3>'
                f'<table class="wf-table"><thead><tr>'
                f'<th>Agent</th><th>Model</th><th class="num">Tokens</th>'
                f'<th class="num">Cost $</th><th class="num">Tools</th>'
                f'<th class="num">Duration</th><th>State</th>'
                f'</tr></thead><tbody>{body}</tbody></table></div>'
            )
        blocks.append(
            f'<details class="wf-run">{summary}'
            f'<div class="wf-body">{"".join(phase_html)}</div></details>'
        )

    # Summary strip across all runs.
    tot_runs = len(rows)
    tot_agents = sum(int(r.get("agents", 0)) for r in rows)
    tot_cost = sum(float(r.get("cost_usd", 0.0)) for r in rows)
    tot_tokens = sum(int(r.get("total_tokens", 0)) for r in rows)
    cards = (
        '<div class="cards wf-summary-cards">'
        f'<div class="card"><div class="val">{tot_runs:,}</div><div class="lbl">Workflow runs</div></div>'
        f'<div class="card"><div class="val">{tot_agents:,}</div><div class="lbl">Agents</div></div>'
        f'<div class="card amber"><div class="val">{_fmt_cost(tot_cost)}</div><div class="lbl">Workflow cost</div></div>'
        f'<div class="card"><div class="val">{tot_tokens:,}</div><div class="lbl">Tokens</div></div>'
        '</div>'
    )

    # Back-link: history.back() is robust to which page linked in (dashboard
    # or detail, each carrying its own timestamp) — no filename coupling. Not
    # tagged ``data-sm-nav``: theme persists via localStorage, and the
    # onclick must win over any href rewrite.
    back = ('<a class="navlink" href="#" '
            'onclick="if(history.length>1){history.back();return false}">'
            '&larr; Back</a>')
    if nav_sibling:
        # Real href so the link works when the page is opened directly
        # (fresh tab, history.length <= 1); the onclick still prefers
        # history.back() so in-flow navigation returns to whichever page
        # (dashboard or detail) linked in. Not data-sm-nav: the onclick
        # must win over any href rewrite.
        back = (f'<a class="navlink" href="{html_mod.escape(nav_sibling)}" '
                'onclick="if(history.length>1){history.back();return false}">'
                '&larr; Back</a>')
    gen = html_mod.escape(report.get("generated_at", "") or "")
    ver = html_mod.escape(str(report.get("skill_version", "") or ""))
    scope = html_mod.escape(report.get("slug", "") or report.get("mode", "") or "")
    run_word = "run" if tot_runs == 1 else "runs"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="session-metrics {ver}">
<title>Dynamic workflows — {scope}</title>
{_theme_css()}
{_overlay_css()}
{_workflow_companion_css()}
{_theme_bootstrap_head_js()}
</head>
<body class="theme-console">
<div class="shell">
<header class="topbar">
<div class="brand"><span class="dot"></span><span>session-metrics</span></div>
<nav class="nav">{back}{_theme_picker_markup()}</nav>
</header>
<header class="page-header">
<h1>Dynamic workflows</h1>
<p class="meta">{scope} &nbsp;·&nbsp; Generated {gen} &nbsp;·&nbsp; skill v{ver}</p>
</header>
{cards}
<p class="wf-intro">Per-agent token/cost are exact (summed from agent
transcripts); labels, phases, tool-calls and previews come from the run
journal.</p>
<section class="section">
<div class="section-title"><h2>Workflow runs</h2>
<span class="hint">{tot_runs:,} {run_word}</span></div>
{"".join(blocks)}
</section>
<footer class="foot"><span class="muted">session-metrics · {gen}</span></footer>
</div>
{_overlay_js()}
{_theme_bootstrap_body_js()}
</body>
</html>"""


_TASK_VERDICT_META = {
    "worth_it":     ("ok",    "Worth it"),
    "mixed":        ("amber", "Mixed"),
    "likely_waste": ("warn",  "Likely waste"),
}


def _task_turn_detail_row(req_key: str, turns: list[dict]) -> str:
    """Hidden detail row holding a compact per-turn sub-table for one request
    unit — the Tasks-page turn drilldown revealed when its request row is
    clicked. Mirrors the columns of the details report's Timeline row. Every
    figure is read straight from the turn dict (no re-summing), consistent with
    the skill's "export owns the numbers" rule. Subagent turns (which inherit
    their spawner's anchor, so they land in this unit) are badged so the row
    count reconciles with the request's ``turn_count`` chip."""
    rows: list[str] = []
    for t in turns:
        tools = t.get("tool_use_names") or []
        tools_str = (", ".join(html_mod.escape(n) for n in tools[:3])
                     + (f" +{len(tools) - 3}" if len(tools) > 3 else "")) or "&mdash;"
        si = t.get("skill_invocations") or []
        sc = t.get("slash_command") or ""
        skill_label = si[0] if si else (sc.lstrip("/") if sc else "")
        skill_badge = (f'<span class="sub-tag">{html_mod.escape(skill_label)}</span>'
                       if skill_label else "")
        sub_badge = ('<span class="sub-tag" title="subagent turn">sub</span>'
                     if t.get("subagent_agent_id") else "")
        risk_badge = ('<span class="turn-risk" title="Potentially wasteful turn">'
                      '&#9888;</span>' if t.get("turn_risk") else "")
        rows.append(
            f'<tr>'
            f'<td class="num">{t.get("index", "")}</td>'
            f'<td>{html_mod.escape(t.get("timestamp_fmt", ""))}</td>'
            f'<td>{html_mod.escape(t.get("model", ""))}{skill_badge}{sub_badge}</td>'
            f'<td class="num">{int(t.get("input_tokens", 0)):,}</td>'
            f'<td class="num">{int(t.get("output_tokens", 0)):,}</td>'
            f'<td class="num">{int(t.get("cache_read_tokens", 0)):,}</td>'
            f'<td class="num">{int(t.get("total_tokens", 0)):,}</td>'
            f'<td class="cost">{_fmt_cost(t.get("cost_usd", 0.0))}</td>'
            f'<td>{tools_str}{risk_badge}</td>'
            f'</tr>'
        )
    head = (
        '<thead><tr>'
        '<th class="num">#</th><th>Time</th><th>Model</th>'
        '<th class="num">In</th><th class="num">Out</th>'
        '<th class="num">Cache rd</th><th class="num">Tokens</th>'
        '<th class="num">Cost $</th><th>Tools</th>'
        '</tr></thead>'
    )
    return (
        f'<tr class="req-turns" data-req="{html_mod.escape(req_key)}" hidden>'
        f'<td colspan="7">'
        f'<table class="turn-subtable">{head}<tbody>{"".join(rows)}</tbody></table>'
        f'</td></tr>'
    )


def _build_tasks_companion_html(report: dict, tasks_data: dict,
                                nav_sibling: str | None = None) -> str:
    """Standalone, theme-aware "Tasks" companion page (the 4th export page).

    Renders the Claude-authored task grouping produced by the
    ``task-breakdown`` skill: one collapsible ``<details class="wf-run">``
    accordion per semantic task (reusing the workflow-companion shell + CSS),
    with a verdict pill and member request-unit timeline. All cost/turn
    figures come from :func:`_data._assemble_tasks` (summed from the export's
    request units), never from the grouping file. Returns "" when there are
    no tasks.
    """
    tasks = tasks_data.get("tasks") or []
    if not tasks:
        return ""
    # Map each request unit's (session_id, anchor) to its constituent turns so a
    # request row can drill down to per-turn detail. Mirrors the grouping key in
    # _build_request_units. Empty at instance scope (no per-turn records are
    # retained) → the per-request table renders without turn expansion.
    turns_by_unit: dict[tuple, list[dict]] = {}
    for s in report.get("sessions") or []:
        sid = s.get("session_id", "")
        for tn in s.get("turns") or []:
            if tn.get("is_resume_marker"):
                continue
            anchor = tn.get("prompt_anchor_index", tn.get("index"))
            turns_by_unit.setdefault((sid, anchor), []).append(tn)
    blocks: list[str] = []
    for t in tasks:
        title = html_mod.escape(t.get("title") or "")
        vcls, vlabel = _TASK_VERDICT_META.get(
            t.get("verdict") or "", ("", ""))
        verdict_chip = (f'<span class="wf-chip {vcls}">{vlabel}</span>'
                        if vlabel else "")
        wall = _fmt_secs_short(t.get("wall_clock_seconds", 0))
        risk = int(t.get("risk_turn_count", 0))
        risk_chip = (f'<span class="wf-chip warn">&#9888; {risk} risky</span>'
                     if risk else "")
        chips = (
            '<span class="wf-chips">'
            f'{verdict_chip}'
            f'<span class="wf-chip">{int(t.get("member_count", 0)):,} requests</span>'
            f'<span class="wf-chip">{int(t.get("turn_count", 0)):,} turns</span>'
            f'<span class="wf-chip cost">{_fmt_cost(t.get("cost_usd", 0.0))}</span>'
            f'<span class="wf-chip">{int(t.get("total_tokens", 0)):,} tok</span>'
            f'<span class="wf-chip">{wall}</span>'
            f'{risk_chip}'
            '</span>'
        )
        summary = f'<summary><strong>{title}</strong>{chips}</summary>'
        rationale = html_mod.escape(t.get("rationale") or "")
        rationale_html = (f'<p class="wf-intro">{rationale}</p>'
                          if rationale else "")
        member_rows: list[str] = []
        for u in t.get("members") or []:
            snippet = html_mod.escape((u.get("prompt_snippet") or "")[:200]) or "&mdash;"
            tools = list(u.get("tool_histogram") or {})
            tools_str = (", ".join(html_mod.escape(n) for n in tools[:3])
                         + (f" +{len(tools) - 3}" if len(tools) > 3 else "")
                         ) or "&mdash;"
            ur = int(u.get("risk_turn_count", 0))
            u_turns = turns_by_unit.get(
                (u.get("session_id"), u.get("anchor_index")), [])
            req_key = f'{(u.get("session_id") or "")[:8]}-{u.get("anchor_index")}'
            if u_turns:
                caret = '<span class="req-caret">&#9656;</span>'
                req_attrs = (f' class="req-row" role="button" tabindex="0" '
                             f'data-req="{html_mod.escape(req_key)}"')
            else:
                caret = ""
                req_attrs = ""
            member_rows.append(
                f'<tr{req_attrs}>'
                f'<td>{caret}<code>#{u.get("anchor_index")}</code></td>'
                f'<td>{snippet}</td>'
                f'<td class="num">{int(u.get("turn_count", 0)):,}</td>'
                f'<td class="cost">{_fmt_cost(u.get("combined_cost_usd", 0.0))}</td>'
                f'<td class="num">{int(u.get("total_tokens", 0)):,}</td>'
                f'<td>{tools_str}</td>'
                f'<td class="num">{("&#9888; " + str(ur)) if ur else "&mdash;"}</td>'
                f'</tr>'
            )
            if u_turns:
                member_rows.append(_task_turn_detail_row(req_key, u_turns))
        body = ("".join(member_rows)
                or '<tr><td colspan="7" class="wf-empty">No requests.</td></tr>')
        table = (
            f'<div class="wf-phase">'
            f'<table class="wf-table"><thead><tr>'
            f'<th>Req</th><th>Prompt</th><th class="num">Turns</th>'
            f'<th class="num">Cost $</th><th class="num">Tokens</th>'
            f'<th>Tools</th><th class="num">Risk</th>'
            f'</tr></thead><tbody>{body}</tbody></table></div>'
        )
        blocks.append(
            f'<details class="wf-run">{summary}'
            f'<div class="wf-body">{rationale_html}{table}</div></details>'
        )

    tot_tasks = len(tasks)
    cards = (
        '<div class="cards wf-summary-cards">'
        f'<div class="card"><div class="val">{tot_tasks:,}</div>'
        f'<div class="lbl">Tasks</div></div>'
        f'<div class="card"><div class="val">{int(tasks_data.get("total_turns", 0)):,}</div>'
        f'<div class="lbl">Turns</div></div>'
        f'<div class="card amber"><div class="val">'
        f'{_fmt_cost(tasks_data.get("total_cost_usd", 0.0))}</div>'
        f'<div class="lbl">Total cost</div></div>'
        f'<div class="card"><div class="val">{tasks_data.get("coverage_pct", 0.0):.0f}%</div>'
        f'<div class="lbl">Requests grouped</div></div>'
        '</div>'
    )
    warnings = tasks_data.get("warnings") or []
    warn_html = ""
    if warnings:
        items = "".join(f'<li>{html_mod.escape(w)}</li>' for w in warnings[:20])
        warn_html = (f'<section class="section"><div class="section-title">'
                     f'<h2>Grouping notes</h2></div>'
                     f'<ul class="muted">{items}</ul></section>')

    back = ('<a class="navlink" href="#" '
            'onclick="if(history.length>1){history.back();return false}">'
            '&larr; Back</a>')
    if nav_sibling:
        # Real href so the link works when the page is opened directly
        # (fresh tab, history.length <= 1); the onclick still prefers
        # history.back() so in-flow navigation returns to whichever page
        # (dashboard or detail) linked in. Not data-sm-nav: the onclick
        # must win over any href rewrite.
        back = (f'<a class="navlink" href="{html_mod.escape(nav_sibling)}" '
                'onclick="if(history.length>1){history.back();return false}">'
                '&larr; Back</a>')
    gen = html_mod.escape(report.get("generated_at", "") or "")
    ver = html_mod.escape(str(report.get("skill_version", "") or ""))
    scope = html_mod.escape(tasks_data.get("scope_label")
                            or report.get("slug", "")
                            or report.get("mode", "") or "")
    task_word = "task" if tot_tasks == 1 else "tasks"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="session-metrics {ver}">
<title>Tasks — {scope}</title>
{_theme_css()}
{_overlay_css()}
{_workflow_companion_css()}
{_theme_bootstrap_head_js()}
</head>
<body class="theme-console">
<div class="shell">
<header class="topbar">
<div class="brand"><span class="dot"></span><span>session-metrics</span></div>
<nav class="nav">{back}{_theme_picker_markup()}</nav>
</header>
<header class="page-header">
<h1>Tasks</h1>
<p class="meta">{scope} &nbsp;·&nbsp; Generated {gen} &nbsp;·&nbsp; skill v{ver}</p>
</header>
{cards}
<p class="wf-intro">Semantic tasks grouped by Claude from the deterministic
per-request breakdown. Every cost / turn figure is summed from the export's
request units — the grouping only assigns requests to tasks and labels each
with a verdict. Click a task to see its requests.</p>
<section class="section">
<div class="section-title"><h2>Tasks</h2>
<span class="hint">{tot_tasks:,} {task_word}</span></div>
{"".join(blocks)}
</section>
{warn_html}
<footer class="foot"><span class="muted">session-metrics · {gen}</span></footer>
</div>
<script>
(function(){{
  function toggle(row){{
    var key=row.getAttribute('data-req');if(!key)return;
    var sel='tr.req-turns[data-req="'+(window.CSS&&CSS.escape?CSS.escape(key):key)+'"]';
    var det=row.parentNode.querySelector(sel);if(!det)return;
    if(det.hasAttribute('hidden')){{det.removeAttribute('hidden');row.classList.add('open');}}
    else{{det.setAttribute('hidden','');row.classList.remove('open');}}
  }}
  document.addEventListener('click',function(e){{
    var row=e.target.closest&&e.target.closest('tr.req-row');if(row)toggle(row);
  }});
  document.addEventListener('keydown',function(e){{
    if(e.key!=='Enter'&&e.key!==' ')return;
    var row=e.target.closest&&e.target.closest('tr.req-row');
    if(row){{e.preventDefault();toggle(row);}}
  }});
}})();
</script>
{_overlay_js()}
{_theme_bootstrap_body_js()}
</body>
</html>"""


def _md_inline_spans(escaped: str) -> str:
    """Apply the safe inline Markdown subset (``**bold**`` → <strong>,
    `` `code` `` → <code>) to ALREADY-ESCAPED text. The ``**`` / `` ` `` markers
    are not HTML-special, so running this after :func:`html.escape` cannot inject
    markup — callers MUST escape first."""
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", out)


def _md_inline_to_html(text: str) -> str:
    """Render a tiny, SAFE Markdown subset to HTML for LLM-authored prose.

    Escaping runs FIRST, so no markup in ``text`` can inject HTML. Supports
    ``**bold**``, `` `code` ``, single-newline ``<br>``, and blank-line-separated
    paragraphs. Returns "" for empty input."""
    esc = html_mod.escape(text or "").strip()
    if not esc:
        return ""
    esc = _md_inline_spans(esc)
    paras = [p.strip() for p in re.split(r"\n\s*\n", esc) if p.strip()]
    return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paras)


_INSIGHTS_LENS_LABEL = {
    "summary": "Summary lens — what got done",
    "effectiveness": "Effectiveness lens — waste & how to improve",
}


def _build_insights_companion_html(report: dict, insights_data: dict,
                                   nav_sibling: str | None = None) -> str:
    """Standalone, theme-aware "Insights" companion page (auto-insights).

    Renders the LLM-authored prose (headline + sections + recommendations)
    produced by the insights pass over a deterministic digest. The FACTS strip
    is recomputed by :func:`_data._assemble_insights` from the export — the
    prose is never trusted for numbers. Reuses the workflow-companion shell +
    CSS. Returns the page even with empty prose (the facts strip + a
    "prose not yet written" note), so a zero-edit skeleton still renders.
    """
    facts = insights_data.get("facts") or {}
    lens = insights_data.get("lens") or "summary"
    headline = insights_data.get("headline") or ""
    sections = insights_data.get("sections") or []
    recs = insights_data.get("recommendations") or []
    focus = insights_data.get("focus") or ""

    def _fact_card(val: str, lbl: str, cls: str = "") -> str:
        return (f'<div class="card {cls}"><div class="val">{val}</div>'
                f'<div class="lbl">{html_mod.escape(lbl)}</div></div>')

    cards = ['<div class="cards wf-summary-cards">']
    cards.append(_fact_card(_fmt_cost(facts.get("total_cost_usd", 0.0)),
                            "Total cost", "amber"))
    cards.append(_fact_card(f'{int(facts.get("total_turns", 0)):,}', "Turns"))
    cards.append(_fact_card(f'{int(facts.get("total_tokens", 0)):,}', "Tokens"))
    cards.append(_fact_card(f'{float(facts.get("cache_hit_pct", 0.0)):.0f}%',
                            "Cache hit"))
    if facts.get("health_grade"):
        cards.append(_fact_card(html_mod.escape(str(facts.get("health_grade"))),
                                "Health grade"))
    if facts.get("outcome"):
        cards.append(_fact_card(html_mod.escape(str(facts.get("outcome"))),
                                "Outcome"))
    if facts.get("archetype"):
        cards.append(_fact_card(html_mod.escape(str(facts.get("archetype"))),
                                "Archetype"))
    cards.append("</div>")
    cards_html = "".join(cards)

    lens_label = _INSIGHTS_LENS_LABEL.get(lens, lens)
    headline_html = (f'<p class="wf-intro insights-headline">'
                     f'{_md_inline_spans(html_mod.escape(headline))}</p>'
                     if headline else
                     '<p class="wf-intro muted">No headline yet — run the '
                     'insights pass to write the prose.</p>')
    focus_html = (f'<p class="wf-intro muted">Focus: '
                  f'{html_mod.escape(focus)}</p>' if focus else "")

    sec_blocks: list[str] = []
    for s in sections:
        heading = html_mod.escape(s.get("heading") or "")
        body = _md_inline_to_html(s.get("body") or "")
        if not heading and not body:
            continue
        body_html = body or '<p class="muted">(not written yet)</p>'
        sec_blocks.append(
            f'<section class="section"><div class="section-title">'
            f'<h2>{heading}</h2></div>'
            f'<div class="health-panel">{body_html}</div></section>')
    sections_html = "".join(sec_blocks)

    rec_html = ""
    if recs:
        items = []
        for r in recs:
            text = _md_inline_to_html(r.get("text") or "")
            ev = html_mod.escape(r.get("evidence") or "")
            ev_html = f'<div class="lbl">{ev}</div>' if ev else ""
            if text:
                items.append(f'<li>{text}{ev_html}</li>')
        if items:
            rec_html = (
                f'<section class="section"><div class="section-title">'
                f'<h2>Recommendations</h2></div>'
                f'<ul class="rec-list health-panel">{"".join(items)}</ul>'
                f'</section>')

    warnings = insights_data.get("warnings") or []
    warn_html = ""
    if warnings:
        items = "".join(f'<li>{html_mod.escape(w)}</li>' for w in warnings[:20])
        warn_html = (f'<section class="section"><div class="section-title">'
                     f'<h2>Notes</h2></div>'
                     f'<ul class="muted">{items}</ul></section>')

    back = ('<a class="navlink" href="#" '
            'onclick="if(history.length>1){history.back();return false}">'
            '&larr; Back</a>')
    if nav_sibling:
        back = (f'<a class="navlink" href="{html_mod.escape(nav_sibling)}" '
                'onclick="if(history.length>1){history.back();return false}">'
                '&larr; Back</a>')
    gen = html_mod.escape(report.get("generated_at", "") or "")
    ver = html_mod.escape(str(report.get("skill_version", "") or ""))
    scope = html_mod.escape(insights_data.get("scope_label")
                            or report.get("slug", "")
                            or report.get("mode", "") or "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="session-metrics {ver}">
<title>Insights — {scope}</title>
{_theme_css()}
{_overlay_css()}
{_workflow_companion_css()}
<style>
.insights-headline{{font-size:1.1em;font-weight:600;color:var(--fg)}}
.rec-list{{margin:0;padding-left:1.2em}}
.rec-list li{{margin:0 0 .6em}}
.rec-list .lbl{{margin-top:.15em;font-size:.85em;color:var(--fg-dim)}}
.health-panel p{{margin:0 0 .6em}}
.health-panel p:last-child{{margin-bottom:0}}
</style>
{_theme_bootstrap_head_js()}
</head>
<body class="theme-console">
<div class="shell">
<header class="topbar">
<div class="brand"><span class="dot"></span><span>session-metrics</span></div>
<nav class="nav">{back}{_theme_picker_markup()}</nav>
</header>
<header class="page-header">
<h1>Insights</h1>
<p class="meta">{html_mod.escape(lens_label)} &nbsp;·&nbsp; {scope}
 &nbsp;·&nbsp; Generated {gen} &nbsp;·&nbsp; skill v{ver}</p>
</header>
{cards_html}
{headline_html}
{focus_html}
<p class="wf-intro muted">Prose written by Claude over a deterministic digest.
The numbers above are recomputed from the export — the prose never owns a
figure.</p>
{sections_html}
{rec_html}
{warn_html}
<footer class="foot"><span class="muted">session-metrics · {gen}</span></footer>
</div>
{_overlay_js()}
{_theme_bootstrap_body_js()}
</body>
</html>"""


def _build_tasks_placeholder_html(report: dict, dashboard_href: str) -> str:
    """Minimal stand-in written at export time at the Tasks-companion path.

    ``--task-companion-nav`` makes the dashboard/detail nav point at
    ``<stem>_tasks.html`` before that page exists (it is generated later by
    the task-breakdown flow). This placeholder keeps the button from 404ing
    when the flow is skipped — e.g. the 2-40 request-unit gate fails — and
    is overwritten by ``--render-tasks`` when the real page lands.
    """
    ver = html_mod.escape(str(report.get("skill_version", "") or ""))
    gen = html_mod.escape(report.get("generated_at", "") or "")
    back = (f'<a class="navlink" href="{html_mod.escape(dashboard_href)}" '
            'onclick="if(history.length>1){history.back();return false}">'
            '&larr; Back</a>')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="session-metrics {ver}">
<title>Tasks — pending</title>
{_theme_css()}
{_overlay_css()}
{_theme_bootstrap_head_js()}
</head>
<body class="theme-console">
<div class="shell">
<header class="topbar">
<div class="brand"><span class="dot"></span><span>session-metrics</span></div>
<nav class="nav">{back}{_theme_picker_markup()}</nav>
</header>
<header class="page-header">
<h1>Tasks companion not generated yet</h1>
<p class="meta">Generated {gen} &nbsp;·&nbsp; skill v{ver}</p>
</header>
<section class="section">
<p class="muted">This file is a placeholder written at export time so the
Tasks nav button always resolves. The actual Tasks page is produced by the
task-breakdown flow after the export (<code>--prepare-tasks</code> &rarr;
edit the grouping &rarr; <code>--render-tasks</code>) and overwrites this
file. If you keep seeing this page, the grouping step was skipped — most
commonly because the session had fewer than 2 or more than 40 request
units.</p>
</section>
<footer class="foot"><span class="muted">session-metrics · {gen}</span></footer>
</div>
{_overlay_js()}
{_theme_bootstrap_body_js()}
</body>
</html>"""


def _manifest_file_label(name: str, stem: str) -> str:
    """Short link label for a run file: suffix when present, else extension.

    Non-HTML companions keep their extension so e.g. ``_tasks.html`` and
    ``_tasks.md`` don't both render as "tasks".
    """
    rest = name[len(stem):]
    if rest.startswith("_"):
        suffix, ext = rest.lstrip("_").split(".", 1)
        label = suffix.replace("_", " ")
        return label if ext == "html" else f"{label} ({ext})"
    return rest.lstrip(".")


def _build_export_manifest_html(inv: dict) -> str:
    """Render the export-root ``index.html`` from a ``_scan_export_runs``
    inventory: a "latest run per scope" strip, then every run newest-first
    with per-file links. Audit sidecars list next to their session run.
    All hrefs are relative so the directory stays portable.
    """
    runs = inv.get("runs") or []
    audits = inv.get("audits") or {}
    other = int(inv.get("other") or 0)
    ver = html_mod.escape(str(sys.modules["session_metrics"]._SKILL_VERSION))

    def _pretty_ts(ts: str) -> str:
        digits = "".join(ch for ch in ts if ch.isdigit())
        if len(digits) >= 14:
            return (f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]} "
                    f"{digits[8:10]}:{digits[10:12]}:{digits[12:14]} UTC")
        return ts

    def _run_href(r: dict) -> str | None:
        if r["dir"] is not None:
            idx = r["dir"] / "index.html"
            return f"instance/{r['dir'].name}/index.html" if idx.is_file() \
                else f"instance/{r['dir'].name}"
        for cand in (f"{r['stem']}_dashboard.html", f"{r['stem']}.html"):
            if any(f.name == cand for f in r["files"]):
                return cand
        return r["files"][0].name if r["files"] else None

    latest: dict[str, dict] = {}
    for r in runs:   # newest-first
        latest.setdefault(r["scope"], r)
    cards = []
    for scope in ("session", "project", "instance", "compare"):
        r = latest.get(scope)
        if not r:
            continue
        href = _run_href(r)
        label = html_mod.escape(r["key"] if scope != "instance" else "instance")
        val = (f'<a href="{html_mod.escape(href)}">{label}</a>'
               if href else label)
        cards.append(f'<div class="card"><div class="val">{val}</div>'
                     f'<div class="lbl">Latest {scope} · '
                     f'{_pretty_ts(r["ts"])}</div></div>')
    latest_html = (f'<div class="cards">{"".join(cards)}</div>'
                   if cards else "")

    body_rows = []
    for r in runs:
        if r["dir"] is not None:
            href = _run_href(r)
            files_html = (f'<a href="{html_mod.escape(href)}">bundle</a>'
                          if href else "&mdash;")
        else:
            links = []
            for f in sorted(r["files"], key=lambda p: p.name):
                lbl = _manifest_file_label(f.name, r["stem"]) or f.name
                links.append(f'<a href="{html_mod.escape(f.name)}">'
                             f'{html_mod.escape(lbl)}</a>')
            for a in sorted(audits.get(r["stem"], []), key=lambda p: p.name):
                links.append(f'<a href="{html_mod.escape(a.name)}" '
                             f'class="muted">audit ({a.suffix.lstrip(".")})</a>')
            files_html = " &middot; ".join(links) or "&mdash;"
        body_rows.append(
            f'<tr><td>{html_mod.escape(r["scope"])}</td>'
            f'<td>{html_mod.escape(r["key"])}</td>'
            f'<td>{_pretty_ts(r["ts"])}</td>'
            f'<td>{files_html}</td>'
            f'<td class="num">{r["bytes"] / 1e6:.1f} MB</td></tr>')
    other_html = (f'<p class="muted">{other} file(s) in this directory are '
                  f'not part of a recognised run and are not listed.</p>'
                  if other else "")
    run_word = "run" if len(runs) == 1 else "runs"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="session-metrics {ver}">
<title>session-metrics exports</title>
{_theme_css()}
{_theme_bootstrap_head_js()}
<style>
.manifest td, .manifest th {{ padding: 6px 10px; text-align: left; }}
.manifest td.num {{ text-align: right; }}
.manifest tr:nth-child(even) {{ background: rgba(127,127,127,.06); }}
</style>
</head>
<body class="theme-console">
<div class="shell">
<header class="topbar">
<div class="brand"><span class="dot"></span><span>session-metrics</span></div>
<nav class="nav">{_theme_picker_markup()}</nav>
</header>
<header class="page-header">
<h1>Exports</h1>
<p class="meta">{len(runs):,} {run_word} &nbsp;·&nbsp; refreshed after every
export &nbsp;·&nbsp; skill v{ver}</p>
</header>
{latest_html}
<section class="section">
<div class="section-title"><h2>All runs</h2>
<span class="hint">newest first</span></div>
<table class="manifest">
<thead><tr><th>Scope</th><th>Run</th><th>When</th><th>Files</th>
<th>Size</th></tr></thead>
<tbody>{"".join(body_rows)}</tbody>
</table>
</section>
{other_html}
<footer class="foot"><span class="muted">session-metrics exports index</span></footer>
</div>
{_theme_bootstrap_body_js()}
</body>
</html>"""


def _build_by_workflow_html(rows: list[dict],
                            heading: str = "Dynamic workflows",
                            companion_href: str | None = None,
                            show_project: bool = False) -> str:
    """Render ``by_workflow`` as a sortable cost table. Returns "" when empty.

    Mirrors :func:`_build_by_subagent_type_html` (same ``models-table``
    class, so theming/sorting are shared) but keyed on the Workflow tool's
    ``runId``. Cost/tokens are exact (summed from the workflow-agent
    transcripts); name/status/tool-calls/duration come from the run journal.
    ``show_project`` adds a Project column for the instance dashboard.
    """
    if not rows:
        return ""
    body_rows: list[str] = []
    for r in rows:
        name = html_mod.escape(r.get("workflow_name") or r.get("run_id") or "")
        status = html_mod.escape(r.get("status") or "")
        status_cls = "ok" if status == "completed" else "muted"
        proj_cell = (f'<td><code>{html_mod.escape(r.get("project") or "")}</code></td>'
                     if show_project else "")
        body_rows.append(
            f'<tr>'
            f'{proj_cell}'
            f'<td><code>{name}</code></td>'
            f'<td class="{status_cls}">{status or "&ndash;"}</td>'
            f'<td class="num" title="Distinct agent transcripts merged from '
            f'disk for this run.">{int(r.get("agents", 0)):,}</td>'
            f'<td class="num">{int(r.get("tool_calls", 0)):,}</td>'
            f'<td class="num">{int(r.get("total_tokens", 0)):,}</td>'
            f'<td class="num">{float(r.get("cache_hit_pct", 0.0)):.1f}%</td>'
            f'<td class="cost">{_fmt_cost(r.get("cost_usd", 0.0))}</td>'
            f'<td class="num">{float(r.get("pct_total_cost", 0.0)):.2f}%</td>'
            f'<td>{_workflow_model_label(r.get("models") or {})}</td>'
            f'<td class="num">{_fmt_workflow_duration(int(r.get("duration_ms", 0)))}</td>'
            f'</tr>'
        )
    link = (f' &middot; <a href="{html_mod.escape(companion_href)}">'
            f'full breakdown &rarr;</a>') if companion_href else ""
    proj_hdr = '<th>Project</th>' if show_project else ""
    return (
        f'<section class="section">\n'
        f'<div class="section-title"><h2>{html_mod.escape(heading)}</h2>'
        f'<span class="hint">cost from workflow-agent transcripts'
        f'{link}</span></div>\n'
        f'<table class="models-table">\n'
        f'<thead><tr>'
        f'{proj_hdr}'
        f'<th>Workflow</th>'
        f'<th>Status</th>'
        f'<th class="num" title="Distinct agent transcripts on disk.">Agents</th>'
        f'<th class="num">Tool calls</th>'
        f'<th class="num">Total tokens</th>'
        f'<th class="num">% cached</th>'
        f'<th class="num">Cost $</th>'
        f'<th class="num">% of total</th>'
        f'<th>Model</th>'
        f'<th class="num">Duration</th>'
        f'</tr></thead>\n'
        f'<tbody>{"".join(body_rows)}</tbody>\n'
        f'</table>\n'
        f'</section>'
    )


def _build_subagent_share_card_html(stats: dict) -> str:
    """One-line headline 'Subagent share of cost' KPI card.

    Branches on ``include_subagents`` so users running without the flag
    see "attribution disabled" rather than a deceptive 0% reading.
    Returns the bare ``<div class="kpi">…</div>`` for inclusion in
    ``kpi-grid`` blocks. Always returns a card — the headline framing
    deserves to be visible even when the answer is "we didn't measure".
    """
    # v1.26.0: structure mirrors the other KPI cards — bold headline
    # value (matches Total Cost / Cache Hit Ratio rhythm) plus a small
    # ``.kpi-sub`` line for the supporting numbers, plus a tooltip that
    # carries the full prose explanation. Avoids the multi-line wall of
    # text the previous all-in-``kpi-val`` rendering produced on real
    # sessions where the lower-bound disclosure was non-trivial.
    if not stats.get("include_subagents"):
        return (
            '<div class="kpi" title="Run with --include-subagents to roll up '
            'child subagent JSONL costs onto the parent prompt that spawned them.">'
            '<div class="kpi-label">Subagent share of cost</div>'
            '<div class="kpi-val">&mdash;</div>'
            '<div class="kpi-sub">attribution disabled '
            '&middot; pass <code>--include-subagents</code></div></div>'
        )
    if not stats.get("has_attribution"):
        spawns = int(stats.get("spawn_count", 0) or 0)
        if spawns:
            plural = "" if spawns == 1 else "s"
            return (
                '<div class="kpi" title="Subagents were spawned, but no child '
                'subagent turns were attributed inside this report. Their '
                'transcripts may belong to a prior resumed or compacted session.">'
                '<div class="kpi-label">Subagent share of cost</div>'
                '<div class="kpi-val">0%</div>'
                f'<div class="kpi-sub">{spawns} subagent{plural} spawned '
                '&middot; no attributed child turns</div></div>'
            )
        return (
            '<div class="kpi" title="No subagent turns were attributed to '
            'parent prompts in this report.">'
            '<div class="kpi-label">Subagent share of cost</div>'
            '<div class="kpi-val">0%</div>'
            '<div class="kpi-sub">no subagent activity</div></div>'
        )
    pct = float(stats.get("share_pct", 0.0))
    cost = float(stats.get("attributed_cost", 0.0))
    total = float(stats.get("total_cost", 0.0))
    spawns = int(stats.get("spawn_count", 0))
    orphans = int(stats.get("orphan_turns", 0))
    sub_main = (
        f'${cost:.4f} of ${total:.4f} '
        f'&middot; {spawns} spawn{"s" if spawns != 1 else ""}'
    )
    lower_bound_line = (
        f'<div class="kpi-sub">lower bound &mdash; {orphans} orphan turn'
        f'{"s" if orphans != 1 else ""} excluded</div>'
    ) if orphans else ""
    title = (
        "Cost rolled up from child subagent JSONLs onto the parent "
        "prompts that spawned them."
    )
    if orphans:
        title += (
            f" Lower bound — {orphans} orphan turn"
            f"{'s' if orphans != 1 else ''} excluded because their parent "
            "linkage couldn't be resolved."
        )
    return (
        f'<div class="kpi" title="{html_mod.escape(title)}">'
        f'<div class="kpi-label">Subagent share of cost</div>'
        f'<div class="kpi-val">{pct:.1f}%</div>'
        f'<div class="kpi-sub">{sub_main}</div>'
        f'{lower_bound_line}'
        f'</div>'
    )


def _build_subagent_turn_share_card_html(stats: dict) -> str:
    """Count-basis 'Subagent share of turns' KPI card.

    Pairs with the cost-basis card so users see both framings: cognitive-
    claude-style turn ratio (sub-agent turns / total turns) plus the
    session-metrics-native cost roll-up. Returns '' when no subagent
    turns are present so the card auto-hides on subagent-free reports.
    """
    sa_turns = int(stats.get("subagent_turn_count", 0) or 0)
    if sa_turns <= 0:
        return ""
    total_turns = int(stats.get("total_turn_count", 0) or 0)
    main_turns  = int(stats.get("main_turn_count", 0) or 0)
    pct = float(stats.get("turn_share_pct", 0.0) or 0.0)
    title = (
        "Share of total assistant turns that ran inside a sub-agent. "
        "cognitive-claude-style count-basis framing — pairs with the "
        "cost-basis 'Subagent share of cost' card."
    )
    return (
        f'<div class="kpi" title="{html_mod.escape(title)}">'
        f'<div class="kpi-label">Subagent share of turns</div>'
        f'<div class="kpi-val">{pct:.1f}%</div>'
        f'<div class="kpi-sub">{sa_turns:,} of {total_turns:,} turns '
        f'&middot; main {main_turns:,}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Session-health card + section (v1.72.0)
# ---------------------------------------------------------------------------

_GRADE_COLORS = {
    "A": "#1a7f37", "B": "#3fb950", "C": "#d29922", "D": "#e3742f", "F": "#cf222e",
}
_OUTCOME_STYLE = {
    "completed":   ("Completed",   "#1a7f37"),
    "abandoned":   ("Abandoned",   "#d29922"),
    "errored":     ("Errored",     "#cf222e"),
    "unknown":     ("Unknown",     "#6e7781"),
    "in_progress": ("In progress", "#0969da"),
    "automated":   ("Automated",   "#6e7781"),
}
_PENALTY_LABELS = {
    "failures":             "Tool failures",
    "retries":              "Repeated identical calls",
    "churn":                "File edit churn",
    "streak":               "Consecutive-failure streak",
    "compactions":          "Context compactions",
    "mid_task_compactions": "Mid-task compactions",
    "context_pressure":     "Context pressure (>90%)",
    "outcome":              "Outcome penalty",
}


def _outcome_badge_html(outcome: str) -> str:
    label, color = _OUTCOME_STYLE.get(outcome, (outcome.replace("_", " ").title(), "#6e7781"))
    return (f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
            f'background:{color};color:#fff;font-weight:600;font-size:13px">{label}</span>')


def _build_session_health_card_html(health: dict) -> str:
    """Compact KPI card: grade + score + outcome, for the dashboard grid."""
    if not health:
        return ""
    grade = health.get("grade")
    score = health.get("score")
    outcome = health.get("outcome", "unknown")
    o_label = _OUTCOME_STYLE.get(outcome, (outcome.replace("_", " ").title(),))[0]
    if grade:
        g_color = _GRADE_COLORS.get(grade, "#6e7781")
        val = (f'<span style="color:{g_color}">{grade}</span> '
               f'<span style="font-size:18px;color:var(--muted,#888)">{score}/100</span>')
    else:
        val = '<span style="font-size:18px;color:var(--muted,#888)">not scored</span>'
    return (
        '<div class="kpi cat-save" title="Penalty-based 0–100 session-health '
        'score with an A–F grade. See the Session Health section for the '
        'per-signal breakdown.">'
        '<div class="kpi-label">Session health</div>'
        f'<div class="kpi-val">{val}</div>'
        f'<div class="kpi-sub">{o_label}</div></div>'
    )


def _build_session_health_html(health: dict) -> str:
    """Full Session Health section: grade, outcome, penalty breakdown, signals.

    Returns "" when no health object is present. Renders for automated /
    unscored sessions too — the outcome + signals are still informative even
    when the numeric score is suppressed.
    """
    if not health:
        return ""
    sig = health.get("signals") or {}
    outcome = health.get("outcome", "unknown")
    grade = health.get("grade")
    score = health.get("score")
    confidence = health.get("outcome_confidence", "")
    basis = health.get("basis") or []

    if grade:
        g_color = _GRADE_COLORS.get(grade, "#6e7781")
        grade_block = (
            f'<span style="display:inline-block;min-width:48px;text-align:center;'
            f'padding:8px 14px;border-radius:10px;background:{g_color};color:#fff;'
            f'font-size:30px;font-weight:700;line-height:1">{grade}</span>'
            f'<span style="font-size:22px;margin-left:12px">{score}<span '
            f'style="color:var(--fg-dim,#888);font-size:15px">/100</span></span>'
        )
    else:
        reason = "automated session" if outcome == "automated" else (
            "live session" if outcome == "in_progress" else "insufficient data")
        grade_block = (
            f'<span style="font-size:18px;color:var(--fg-dim,#888)">Not scored '
            f'&middot; {reason}</span>'
        )

    pen = health.get("penalties") or {}
    pen_rows = "".join(
        f'<tr><td>{_PENALTY_LABELS.get(k, k)}</td>'
        f'<td style="text-align:right;color:#cf222e">&minus;{v}</td></tr>'
        for k, v in pen.items() if v
    )
    if pen_rows:
        pen_table = (
            '<table class="mini-table" style="margin-top:8px"><thead><tr>'
            '<th>Penalty</th><th style="text-align:right">Points</th></tr></thead>'
            f'<tbody>{pen_rows}</tbody></table>'
        )
    elif grade:
        pen_table = ('<p style="color:#1a7f37;margin-top:8px">No penalties &mdash; '
                     'clean session.</p>')
    else:
        pen_table = ""

    # Signals one-liners.
    def _n(key):
        return int(sig.get(key, 0) or 0)
    cp = sig.get("context_pressure")
    cp_str = (f'{cp * 100:.0f}% of {int(sig.get("context_window", 0)):,}-token window'
              if cp is not None else "n/a")
    signal_bits = [
        f'<li>Tool failures: <strong>{_n("failure_signal_count")}</strong> '
        f'(longest streak {_n("consecutive_failure_max")})</li>',
        f'<li>Repeated identical calls: <strong>{_n("retry_count")}</strong></li>',
        f'<li>Edit churn: <strong>{_n("edit_churn_count")}</strong> file(s)</li>',
        f'<li>Compactions: <strong>{_n("compaction_count")}</strong> '
        f'({_n("mid_task_compaction_count")} mid-task)</li>',
        f'<li>Peak context pressure: <strong>{cp_str}</strong></li>',
    ]
    if health.get("give_up"):
        signal_bits.append('<li style="color:#d29922">Final reply reads like a '
                           'capitulation (soft failure)</li>')
    churned = sig.get("churned_files") or []
    if churned:
        items = "".join(
            f'<li>{html_mod.escape(c.get("path", ""))} '
            f'&mdash; {int(c.get("edits", 0))} edits</li>' for c in churned[:8]
        )
        signal_bits.append(f'<li>Churned files:<ul>{items}</ul></li>')

    basis_str = ", ".join(basis) if basis else "&mdash;"
    conf_str = f' &middot; {confidence} confidence' if confidence else ""
    return (
        '<section class="section" id="session-health-section">'
        '<div class="section-title"><h2>Session Health</h2></div>'
        f'<div class="health-panel">'
        '<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;'
        'margin-bottom:6px">'
        f'{grade_block}'
        f'<span>Outcome: {_outcome_badge_html(outcome)}{conf_str}</span>'
        '</div>'
        f'<p style="color:var(--fg-dim,#888);font-size:13px;margin:4px 0">'
        f'Scored on: {basis_str}</p>'
        f'{pen_table}'
        f'<ul style="margin-top:10px;line-height:1.6">{"".join(signal_bits)}</ul>'
        '</div>'
        '</section>'
    )


def _chip_html(text: str, *, color: str = "#57606a") -> str:
    return (f'<span style="display:inline-block;padding:3px 10px;margin:2px;'
            f'border-radius:12px;background:{color};color:#fff;font-size:13px">'
            f'{html_mod.escape(text)}</span>')


_ARCHETYPE_COLORS = {"quick": "#0969da", "standard": "#1a7f37",
                     "deep": "#8250df", "marathon": "#bf3989"}
_TERMINATION_LABELS = {
    "clean": ("Ended clean", "#1a7f37"),
    "awaiting_user": ("Awaiting user", "#0969da"),
    "tool_call_pending": ("Tool call pending", "#d29922"),
    "truncated": ("Truncated", "#cf222e"),
}


def _build_session_behavior_html(behavior: dict) -> str:
    """Session Behavior section — adoption / autonomy / archetype chips + taxonomy."""
    if not behavior:
        return ""
    ad = behavior.get("adoption") or {}
    arche = behavior.get("archetype", "")
    chips = [
        _chip_html(f"{arche.title()} session", color=_ARCHETYPE_COLORS.get(arche, "#57606a")),
    ]
    ar = behavior.get("autonomy_ratio")
    if ar is not None:
        chips.append(_chip_html(f"Autonomy {ar}× (tool turns / prompt)"))
    chips.append(_chip_html(f"{behavior.get('user_prompt_count', 0)} user prompts"))
    if ad.get("plan_mode_used"):
        chips.append(_chip_html("Plan mode used", color="#1a7f37"))
    sc = int(ad.get("subagent_spawn_count", 0) or 0)
    if sc:
        chips.append(_chip_html(f"{sc} subagent{'s' if sc != 1 else ''} spawned"))
    dk = int(ad.get("distinct_skill_count", 0) or 0)
    if dk:
        chips.append(_chip_html(f"{dk} distinct skill{'s' if dk != 1 else ''}"))
    term = behavior.get("termination", "")
    t_label, t_color = _TERMINATION_LABELS.get(term, (term.replace("_", " ").title(), "#57606a"))
    chips.append(_chip_html(t_label, color=t_color))
    if behavior.get("relationship") == "continuation":
        chips.append(_chip_html("Continuation", color="#8250df"))

    tax = behavior.get("tool_taxonomy") or {}
    tax_html = ""
    if tax:
        cells = " &middot; ".join(
            f'{html_mod.escape(k)} {v}' for k, v in tax.items())
        tax_html = (f'<p style="color:var(--fg-dim,#888);font-size:13px;'
                    f'margin-top:8px">Tools by category: {cells}</p>')
    return (
        '<section class="section" id="session-behavior-section">'
        '<div class="section-title"><h2>Session Behavior</h2></div>'
        f'<div class="health-panel">'
        f'<div style="line-height:2">{"".join(chips)}</div>'
        f'{tax_html}'
        '</div>'
        '</section>'
    )


def _build_window_ribbon_html(window_stats: list[dict]) -> str:
    """Multi-window 7d / 30d / 90d / all-time comparison ribbon.

    Sourced from cognitive-claude's ``cost-audit.py --verbose`` framing —
    surfaces drift the single-window dashboard hides. Returns ``""`` when
    every window is empty (no turns at all). One small KPI card per
    window with cost, cache hit %, turns, sessions, and top model.
    """
    if not window_stats:
        return ""
    if all(int(w.get("turns", 0) or 0) == 0 for w in window_stats):
        return ""
    cards: list[str] = []
    for w in window_stats:
        label = html_mod.escape(str(w.get("label") or ""))
        turns = int(w.get("turns", 0) or 0)
        if turns == 0:
            cards.append(
                f'<div class="kpi" style="min-height:auto;padding:14px 16px">'
                f'<div class="kpi-label">{label}</div>'
                f'<div class="kpi-val" style="font-size:18px">&mdash;</div>'
                f'<div class="kpi-sub">no activity</div></div>'
            )
            continue
        cost = float(w.get("total_cost", 0.0) or 0.0)
        hit  = float(w.get("cache_hit_pct", 0.0) or 0.0)
        phit = float(w.get("partial_hit_rate", 0.0) or 0.0)
        pht  = int(w.get("total_cache_turns", 0) or 0)
        sess = int(w.get("sessions", 0) or 0)
        top_model = html_mod.escape(str(w.get("top_model") or ""))
        if len(top_model) > 24:
            top_model = top_model[:22] + "&hellip;"
        partial_frag = f" &middot; partial {phit:.1f}%" if pht > 0 else ""
        cards.append(
            f'<div class="kpi cat-tokens" style="min-height:auto;padding:14px 16px">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-val" style="font-size:20px">${cost:.2f}</div>'
            f'<div class="kpi-sub">cache {hit:.1f}%{partial_frag} &middot; {turns:,} turn'
            f'{"s" if turns != 1 else ""} &middot; {sess:,} session'
            f'{"s" if sess != 1 else ""}'
            f'{(" &middot; " + top_model) if top_model else ""}</div></div>'
        )
    return (
        '<section class="section" id="window-ribbon-section">\n'
        '  <div class="section-title"><h2>Window comparison</h2>'
        '<span class="hint">trailing 7d / 30d / 90d / all-time</span></div>\n'
        '  <div class="grid kpi-grid" '
        'style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr));margin-bottom:16px">\n'
        f'    {"".join(cards)}\n'
        '  </div>\n</section>'
    )


def _build_plan_leverage_card_html(totals: dict, plan_cost: float | None) -> str:
    """Plan-leverage KPI card: API-equivalent ÷ flat-rate plan paid.

    Auto-hides when ``plan_cost`` is unset or non-positive so the card stays
    opt-in. Sourced from cognitive-claude's ``cost-audit.py`` framing —
    single-number answer to "is the subscription paying off?".
    """
    if not plan_cost or plan_cost <= 0:
        return ""
    api_cost = float(totals.get("cost", 0.0) or 0.0)
    leverage = api_cost / plan_cost
    title = (
        f"API-equivalent cost (${api_cost:.4f}) divided by the flat-rate "
        f"plan price you paid (${plan_cost:.2f}). >1× means the "
        f"subscription is paying off versus pay-as-you-go."
    )
    return (
        f'\n  <div class="kpi featured cat-save" title="{html_mod.escape(title)}">'
        f'<div class="kpi-label">Plan leverage</div>'
        f'<div class="kpi-val">{leverage:.2f}×</div>'
        f'<div class="kpi-sub">${api_cost:.2f} API &middot; '
        f'${plan_cost:.2f} plan</div></div>'
    )


# ---------------------------------------------------------------------------
# Secondary KPI cards — extracted from the inline dashboard builder so the
# instance/all-projects renderer can reuse them (it already consumes
# ``_build_plan_leverage_card_html`` / ``_build_subagent_share_card_html``).
# Each returns the full ``"\n  <div…>"`` card string or ``""`` (auto-hide),
# byte-identical to the former inline blocks.
# ---------------------------------------------------------------------------

def _build_ttl_mix_card_html(totals: dict) -> str:
    """Cache TTL-mix card: premium paid for 1-hour cache writes vs 5-minute."""
    if totals.get("cache_write_1h", 0) <= 0:
        return ""
    pct_1h = 100 * totals["cache_write_1h"] / max(1, totals["cache_write"])
    extra = totals.get("extra_1h_cost", 0.0)
    return (
        f'\n  <div class="kpi cat-tokens" '
        f'title="1-hour cache writes cost 2× input vs 1.25× for the 5-minute tier. '
        f'This card shows the premium you paid for longer cache reuse.">'
        f'<div class="kpi-label">Cache TTL mix (extra paid for 1h)</div>'
        f'<div class="kpi-val">{pct_1h:.0f}% 1h · ${extra:.4f}</div></div>'
    )


def _build_thinking_card_html(totals: dict) -> str:
    """Extended-thinking engagement card (signature-only block count)."""
    if totals.get("thinking_turn_count", 0) <= 0:
        return ""
    tn = totals["thinking_turn_count"]
    tp = totals.get("thinking_turn_pct", 0.0)
    blocks = (totals.get("content_blocks") or {}).get("thinking", 0)
    total_turns = totals.get("turns", 0)
    return (
        f'\n  <div class="kpi" '
        f'title="Claude Code stores thinking blocks signature-only — '
        f'the count is real but per-block token counts aren\'t recoverable '
        f'from the transcript (thinking tokens are rolled into output_tokens).">'
        f'<div class="kpi-label">Extended thinking engagement '
        f'({tn} of {total_turns} turns)</div>'
        f'<div class="kpi-val">{tp:.0f}% · {blocks} blocks</div></div>'
    )


def _build_tool_calls_card_html(totals: dict) -> str:
    """Tool-calls card: total count, per-turn average, and top-3 tool names."""
    if totals.get("tool_call_total", 0) <= 0:
        return ""
    tc = totals["tool_call_total"]
    avg = totals.get("tool_call_avg_per_turn", 0.0)
    top3 = totals.get("tool_names_top3") or []
    # Tool names originate from the JSONL and are attacker-controllable
    # in a compromised transcript — escape each before interpolating.
    top3_str = ", ".join(html_mod.escape(n) for n in top3) if top3 else "none"
    return (
        f'\n  <div class="kpi">'
        f'<div class="kpi-label">Tool calls &middot; top: {top3_str}</div>'
        f'<div class="kpi-val">{tc} · {avg:.1f}/turn</div></div>'
    )


def _build_advisor_card_html(totals: dict, configured_model: str | None = None) -> str:
    """Advisor-calls card. ``configured_model`` is the advisor model label
    (dug out of the per-session ``sessions`` list by the session renderer);
    instance scope has no equivalent source and passes ``None``."""
    _adv_total = totals.get("advisor_call_count", 0)
    if _adv_total <= 0:
        return ""
    _adv_cost = totals.get("advisor_cost_usd", 0.0)
    _adv_total_cost = totals.get("cost", 0.0)
    _adv_model_str = (
        f" &middot; {html_mod.escape(configured_model)}" if configured_model else ""
    )
    _adv_pct = 100 * _adv_cost / _adv_total_cost if _adv_total_cost else 0.0
    return (
        f'\n  <div class="kpi" title="Advisor turns are billed at the'
        f' advisor model\'s list rates with no prompt caching. Cost is'
        f' included in the Total cost above.">'
        f'<div class="kpi-label">Advisor calls{_adv_model_str}</div>'
        f'<div class="kpi-val">{_adv_total} call{"s" if _adv_total != 1 else ""}'
        f' &middot; +${_adv_cost:.4f} ({_adv_pct:.0f}% of total)</div></div>'
    )


def _build_partial_hit_card_html(totals: dict) -> str:
    """Partial-hit-rate card: simultaneous read+write turns / cache-active turns."""
    if totals.get("total_cache_turns", 0) <= 0:
        return ""
    return (
        f'\n  <div class="kpi" title="Turns with simultaneous cache read+write'
        f' (prefix extension) as % of all cache-active turns">'
        f'<div class="kpi-label">Partial hit rate</div>'
        f'<div class="kpi-val">{totals["partial_hit_rate"]:.1f}%</div>'
        f'<div class="kpi-sub">{totals["partial_hit_turns"]:,} of'
        f' {totals["total_cache_turns"]:,} cache turns</div></div>'
    )


def _build_attribution_coverage_html(stats: dict) -> str:
    """Trust gauge for the headline. Renders a small section with
    orphan-turn count, cycles detected, max nesting depth, and the
    spawn → attributed-turn fanout. Returns "" when there's nothing
    interesting to disclose (no spawns, no orphans, no cycles)."""
    spawns = int(stats.get("spawn_count", 0))
    orphans = int(stats.get("orphan_turns", 0))
    cycles  = int(stats.get("cycles_detected", 0))
    nested  = int(stats.get("nested_levels_seen", 0))
    attributed_count = int(stats.get("attributed_count", 0))
    if not stats.get("include_subagents"):
        return ""
    if spawns == 0 and orphans == 0 and cycles == 0 and attributed_count == 0:
        return ""
    fanout = (attributed_count / spawns) if spawns else 0.0
    # v1.26.0: render as a 2-column `models-table` so the section
    # picks up theme-aware styling (console / lattice / light / dark)
    # along with the by_subagent_type and models tables. A bare `<ul>`
    # rendered unstyled in three of the four themes.
    rows: list[str] = []
    rows.append(
        f'<tr>'
        f'<td><strong>Spawn → work fanout</strong></td>'
        f'<td>{spawns} spawn{"s" if spawns != 1 else ""} from main turns '
        f'generated {attributed_count} attributed subagent turn'
        f'{"s" if attributed_count != 1 else ""} '
        f'<span class="muted">(avg {fanout:.2f} turns/spawn)</span>'
        f'</td>'
        f'</tr>'
    )
    if orphans > 0:
        rows.append(
            '<tr>'
            f'<td><strong>Orphan subagent turns</strong></td>'
            f'<td>{orphans} — subagent JSONL turns whose parent linkage '
            f'could not be resolved. Excluded from the headline share; '
            f'the headline is therefore a <em>lower bound</em>.</td>'
            '</tr>'
        )
    if cycles > 0:
        rows.append(
            '<tr>'
            f'<td><strong>Cycles detected</strong></td>'
            f'<td>{cycles} — chains truncated during attribution to '
            f'prevent infinite recursion.</td>'
            '</tr>'
        )
    if nested >= 2:
        rows.append(
            '<tr>'
            f'<td><strong>Nesting depth</strong></td>'
            f'<td>{nested} levels observed (subagent spawning subagent…). '
            f'Tokens still roll up to the original root prompt.</td>'
            '</tr>'
        )
    return (
        '<section class="section">\n'
        '<div class="section-title"><h2>Subagent attribution coverage</h2>'
        '<span class="hint">trust gauge for the headline share — '
        'observational signal only</span></div>\n'
        '<table class="models-table attribution-coverage-table">\n'
        '<thead><tr><th>Signal</th><th>Detail</th></tr></thead>\n'
        f'<tbody>{"".join(rows)}</tbody>\n'
        '</table>\n'
        '</section>'
    )


def _build_within_session_split_html(rows: list[dict]) -> str:
    """Per-session within-session split: median combined cost on
    spawning vs. non-spawning turns. Returns "" when no session
    qualifies (each needs ≥3 turns in each bucket).
    """
    if not rows:
        return ""
    body: list[str] = []
    for r in rows:
        sid = (r.get("session_id") or "")[:8]
        ms  = float(r.get("median_spawn", 0.0))
        mns = float(r.get("median_no_spawn", 0.0))
        delta = float(r.get("delta", 0.0))
        delta_cls = "cost" if delta >= 0 else "muted"
        delta_sign = "+" if delta >= 0 else ""
        body.append(
            f'<tr>'
            f'<td><code>{html_mod.escape(sid)}…</code></td>'
            f'<td class="num">{int(r.get("spawn_n", 0)):,}</td>'
            f'<td class="num">{int(r.get("no_spawn_n", 0)):,}</td>'
            f'<td class="cost">${ms:.4f}</td>'
            f'<td class="cost">${mns:.4f}</td>'
            f'<td class="{delta_cls}">{delta_sign}${delta:.4f}</td>'
            f'<td class="num">{float(r.get("spawn_share_pct", 0.0)):.1f}%</td>'
            f'</tr>'
        )
    return (
        '<section class="section">\n'
        '<div class="section-title"><h2>Within-session spawning split</h2>'
        '<span class="hint">descriptive only · combined cost = parent + '
        'attributed subagent</span></div>\n'
        '<p class="muted" style="margin:0 0 8px 0;font-size:13px">'
        'Per session, median <em>combined</em> turn cost (parent direct '
        '+ attributed subagent) on turns that spawned a subagent vs. '
        'turns that did not. Holds task / model / context constant — '
        'but users tend to delegate the hardest sub-tasks, so this '
        'still has within-session selection bias and is <strong>not</strong> '
        'a counterfactual estimate of "what the same work would have '
        'cost in the main context".</p>\n'
        '<table class="models-table">\n'
        '<thead><tr>'
        '<th>Session</th>'
        '<th class="num">Spawning turns</th>'
        '<th class="num">Non-spawning turns</th>'
        '<th class="num">Median (spawn)</th>'
        '<th class="num">Median (no spawn)</th>'
        '<th class="num">Δ (spawn − no spawn)</th>'
        '<th class="num">Spawn-turn cost share</th>'
        '</tr></thead>\n'
        f'<tbody>{"".join(body)}</tbody>\n'
        '</table>\n'
        '</section>'
    )


def _build_cache_breaks_html(breaks: list[dict],
                               threshold: int,
                               max_rows: int = 100) -> str:
    """Render the cache-break section. Each row is an expandable <details>
    block showing the ±2 user-message context around the flagged turn.
    Returns "" when there are no breaks."""
    if not breaks:
        return ""
    rows_html: list[str] = []
    for cb in breaks[:max_rows]:
        proj = html_mod.escape(cb.get("project", "") or "")
        sid8 = (cb.get("session_id") or "")[:8]
        ts   = html_mod.escape(cb.get("timestamp_fmt") or cb.get("timestamp") or "")
        pct  = float(cb.get("cache_break_pct", 0.0))
        uncached = int(cb.get("uncached", 0))
        total    = int(cb.get("total_tokens", 0))
        snippet = html_mod.escape(cb.get("prompt_snippet") or "")
        context_rows: list[str] = []
        for ce in cb.get("context", []) or []:
            here_cls  = " cb-here" if ce.get("here") else ""
            here_mark = ' <span class="cb-mark">(this turn)</span>' if ce.get("here") else ""
            ctx_ts   = html_mod.escape(ce.get("ts", ""))
            ctx_text = html_mod.escape((ce.get("text") or "")[:240])
            slash    = ce.get("slash") or ""
            slash_html = (f' <code>/{html_mod.escape(slash)}</code>' if slash else "")
            context_rows.append(
                f'<li class="cb-ctx{here_cls}"><span class="cb-ts">{ctx_ts}</span>'
                f'{slash_html}{here_mark} — <span class="cb-txt">{ctx_text}</span></li>'
            )
        proj_cell = f'<span class="cb-proj">{proj}</span> · ' if proj else ''
        rows_html.append(
            f'<details class="cache-break-row">'
            f'<summary>'
            f'<span class="cb-uncached"><strong>{uncached:,}</strong> uncached</span>'
            f' · <span class="cb-pct">{pct:.0f}% of {total:,}</span>'
            f' · {proj_cell}<code>{sid8}</code> · <span class="cb-ts">{ts}</span>'
            f' · <span class="cb-snippet">{snippet}</span>'
            f'</summary>'
            f'<ul class="cb-context">{"".join(context_rows)}</ul>'
            f'</details>'
        )
    hint = f"single turns with input + cache_creation &gt; {threshold:,} · ±2 user-prompt context"
    count_text = f"{len(breaks)} event{'s' if len(breaks) != 1 else ''}"
    more_note = ""
    if len(breaks) > max_rows:
        more_note = (f'<p class="muted">Showing top {max_rows} of {len(breaks)} — '
                     f'raw list available in JSON export.</p>')
    return (
        f'<section class="section">\n'
        f'<div class="section-title"><h2>Cache breaks '
        f'<span class="hint-inline">({count_text})</span></h2>'
        f'<span class="hint">{hint}</span></div>\n'
        f'<div class="cache-breaks">{"".join(rows_html)}</div>\n'
        f'{more_note}'
        f'</section>'
    )


def _build_usage_insights_html(insights: list[dict]) -> str:
    """Render the Usage Insights panel for the dashboard variant.

    Top-of-fold = the highest-value insight that crossed its threshold
    (tie-break by candidate-list order). The remaining `shown` insights
    collapse into a native ``<details>``/``<summary>`` accordion. Returns
    `""` if no insights are shown — the panel disappears entirely so the
    layout reflows naturally to the existing rhythm.
    """
    shown = [i for i in (insights or []) if i.get("shown")]
    if not shown:
        return ""
    # Comparing .value across insights is safe ONLY because every
    # always_on:False ("threshold-bearing") insight carries a 0-100
    # percentage value — the count-valued insights (model_mix,
    # session_pacing, model_compare) are all always_on:True and filtered
    # out here. Keep new threshold-bearing insights on the percentage
    # scale (drift-guarded by test_threshold_bearing_insight_values_are_percentages).
    threshold_bearing = [i for i in shown if not i.get("always_on")]
    top = max(threshold_bearing, key=lambda i: i.get("value", 0)) if threshold_bearing else shown[0]
    rest = [i for i in shown if i is not top]

    def _li(insight: dict) -> str:
        # `body` and `headline` are constructed in `_compute_usage_insights`
        # with html_mod.escape already applied to identifier sub-strings
        # (model/tool names). Here we belt-and-braces escape the whole
        # string before wrapping in HTML tags. Numeric formatters
        # (`f"{pct:.0f}%"` etc.) are safe.
        h = html_mod.escape(insight.get("headline", ""))
        b = html_mod.escape(insight.get("body", ""))
        return f"      <li><strong>{h}</strong>{b}</li>"

    top_h = html_mod.escape(top.get("headline", ""))
    top_b = html_mod.escape(top.get("body", ""))
    if not rest:
        return (f'<section class="usage-insights" aria-label="Usage insights">\n'
                f'  <p class="ui-top"><strong>{top_h}</strong>{top_b}</p>\n'
                f'</section>')
    n = len(rest)
    plural = "" if n == 1 else "s"
    rest_html = "\n".join(_li(i) for i in rest)
    return (
        f'<section class="usage-insights" aria-label="Usage insights">\n'
        f'  <p class="ui-top"><strong>{top_h}</strong>{top_b}</p>\n'
        f'  <details>\n'
        f'    <summary>Show {n} more insight{plural}</summary>\n'
        f'    <ul class="ui-list">\n{rest_html}\n    </ul>\n'
        f'  </details>\n'
        f'</section>'
    )


def _build_waste_analysis_html(wa: dict) -> str:
    """Render the Turn Character & Efficiency Signals section for the dashboard.

    Returns ``""`` when ``wa`` is empty or all detections found nothing — the
    section disappears cleanly like the existing usage-insights panel.
    """
    if not wa:
        return ""
    dist   = wa.get("distribution") or {}
    total  = max(sum(dist.values()), 1)
    if total == 0:
        return ""

    # ---- Turn composition bar ------------------------------------------
    # Ordered display: productive first, then waste categories by severity
    _ORDER = [
        "productive", "cache_read", "cache_write", "reasoning",
        "subagent_overhead", "retry_error", "file_reread",
        "oververbose_edit", "paste_bomb", "dead_end",
    ]
    _COLORS = {
        "productive":        "#4ade80",  # green
        "cache_read":        "#60a5fa",  # blue
        "cache_write":       "#818cf8",  # indigo
        "reasoning":         "#c084fc",  # purple
        "subagent_overhead": "#fb923c",  # orange
        "retry_error":       "#f87171",  # red
        "file_reread":       "#fbbf24",  # amber
        "oververbose_edit":  "#f472b6",  # pink
        "paste_bomb":        "#ef4444",  # bright red — user-side waste signal
        "dead_end":          "#9ca3af",  # grey
    }
    bar_parts = []
    for cat in _ORDER:
        n = dist.get(cat, 0)
        if n == 0:
            continue
        pct  = n / total * 100
        col  = _COLORS.get(cat, "#6b7280")
        lbl  = html_mod.escape(_sm()._TURN_CHARACTER_LABELS.get(cat, cat))
        tip  = f"{lbl}: {n} turns ({pct:.1f}%)"
        bar_parts.append(
            f'<div class="wc-bar-seg" style="width:{pct:.2f}%;background:{col}"'
            f' title="{tip}"></div>'
        )
    bar_html = (
        '<div class="wc-bar">' + "".join(bar_parts) + "</div>"
        if bar_parts else ""
    )

    # ---- Distribution legend table -------------------------------------
    legend_rows = []
    for cat in _ORDER:
        n = dist.get(cat, 0)
        if n == 0:
            continue
        pct  = n / total * 100
        col  = _COLORS.get(cat, "#6b7280")
        lbl  = html_mod.escape(_sm()._TURN_CHARACTER_LABELS.get(cat, cat))
        risk = "&#9888;" if cat in _sm()._RISK_CATEGORIES else ""
        legend_rows.append(
            f'<tr>'
            f'<td><span class="wc-dot" style="background:{col}"></span>{lbl} {risk}</td>'
            f'<td class="num">{n:,}</td>'
            f'<td class="num">{pct:.1f}%</td>'
            f'</tr>'
        )
    legend_table = (
        '<table class="wc-legend">'
        '<thead><tr><th>Category</th><th class="num">Turns</th><th class="num">%</th></tr></thead>'
        '<tbody>' + "".join(legend_rows) + "</tbody>"
        "</table>"
    )

    # ---- Retry chains card ---------------------------------------------
    retry      = wa.get("retry_chains") or {}
    retry_html = ""
    if retry.get("chain_count", 0) > 0:
        chains = retry.get("chains") or []
        cost_pct = float(retry.get("retry_cost_pct", 0.0))
        chain_rows = []
        for c in chains[:5]:
            idxs = ", ".join(str(i) for i in c.get("turn_indices", []))
            chain_rows.append(
                f'<tr><td class="num">{c.get("length", 0)}</td>'
                f'<td class="num mono">{idxs}</td>'
                f'<td class="num">${float(c.get("cost_usd", 0.0)):.4f}</td></tr>'
            )
        chain_table = (
            '<table class="wc-legend">'
            '<thead><tr><th class="num">Length</th><th>Turn indices</th>'
            '<th class="num">Cost $</th></tr></thead>'
            '<tbody>' + "".join(chain_rows) + "</tbody></table>"
        ) if chain_rows else ""
        retry_html = (
            f'<div class="wc-card">'
            f'<h3>&#9854; Retry Patterns</h3>'
            f'<p>{retry["chain_count"]} chain{"s" if retry["chain_count"] != 1 else ""} '
            f'detected &nbsp;·&nbsp; {cost_pct:.1f}% of session cost</p>'
            f'{chain_table}'
            f'</div>'
        )

    # ---- File re-access card ------------------------------------------
    reaccess      = wa.get("file_reaccesses") or {}
    reaccess_html = ""
    if reaccess.get("reaccessed_count", 0) > 0:
        det      = reaccess.get("details") or []
        tot_cost = float(reaccess.get("total_reaccess_cost", 0.0))
        ra_rows  = []
        for d in det[:5]:
            p = html_mod.escape(str(d.get("path", "")))
            ra_rows.append(
                f'<tr><td class="mono" title="{p}">{p[:50]}</td>'
                f'<td class="num">{d.get("count", 0)}</td>'
                f'<td class="num">${float(d.get("cost_usd", 0.0)):.4f}</td></tr>'
            )
        ra_table = (
            '<table class="wc-legend">'
            '<thead><tr><th>File</th><th class="num">Reads</th>'
            '<th class="num">Cost $</th></tr></thead>'
            '<tbody>' + "".join(ra_rows) + "</tbody></table>"
        ) if ra_rows else ""
        reaccess_html = (
            f'<div class="wc-card">'
            f'<h3>&#128196; File Re-Access</h3>'
            f'<p>{reaccess["reaccessed_count"]} file{"s" if reaccess["reaccessed_count"] != 1 else ""} '
            f're-read 2+ times &nbsp;·&nbsp; ${tot_cost:.4f} total</p>'
            f'{ra_table}'
            f'</div>'
        )

    # ---- Verbose edits card ------------------------------------------
    verbose      = wa.get("verbose_edits") or {}
    verbose_html = ""
    if verbose.get("verbose_count", 0) > 0:
        v_tot = float(verbose.get("total_cost", 0.0))
        verbose_html = (
            f'<div class="wc-card">'
            f'<h3>&#128221; Verbose Responses</h3>'
            f'<p>{verbose["verbose_count"]} Edit turn{"s" if verbose["verbose_count"] != 1 else ""} '
            f'with output &gt; 800 tokens &nbsp;·&nbsp; ${v_tot:.4f} total</p>'
            f'</div>'
        )

    # ---- Stop reasons card ------------------------------------------
    sr        = wa.get("stop_reasons") or {}
    sr_html   = ""
    mt_count  = int(sr.get("max_tokens_count", 0))
    mt_pct    = float(sr.get("max_tokens_pct", 0.0))
    dist_sr   = sr.get("distribution") or {}
    if dist_sr:
        sr_parts = []
        for reason, cnt in sorted(dist_sr.items(), key=lambda x: -x[1]):
            sr_parts.append(f'<strong>{html_mod.escape(reason)}</strong> {cnt:,}')
        warning = (
            f' <span class="truncated-tag"'
            f' title="stop_reason: max_tokens — responses were cut off">'
            f'&#9986; {mt_count} truncated ({mt_pct:.1f}%)</span>'
        ) if mt_pct >= 5.0 else ""
        sr_html = (
            f'<div class="wc-card">'
            f'<h3>&#10003; Stop Reasons</h3>'
            f'<p>{" &nbsp;·&nbsp; ".join(sr_parts)}{warning}</p>'
            f'</div>'
        )

    cards_html = retry_html + reaccess_html + verbose_html + sr_html
    if not cards_html:
        cards_html = ""

    return (
        '<section class="section waste-analysis" aria-label="Turn character &amp; efficiency signals">\n'
        '<div class="section-title"><h2>Turn Character &amp; Efficiency Signals</h2>'
        '<span class="hint">9-category waste taxonomy · '
        '<a href="https://thoughts.jock.pl/p/token-waste-management-opus-47-2026" '
        'target="_blank" rel="noopener">methodology</a></span></div>\n'
        f'{bar_html}\n'
        f'{legend_table}\n'
        + (f'<div class="wc-cards">{cards_html}</div>\n' if cards_html else "")
        + "</section>"
    )


# ---------------------------------------------------------------------------
# Phase D — static visualizations (no new chart-library dependency). All
# builders are pure functions of their input dicts: no timestamps, no dict/set
# iteration in the emitted bytes, every coordinate routed through
# ``_svg_scale`` or rounded to 2 dp, so the byte-stable golden test holds. Each
# section auto-hides when its data is absent so the minimal test fixture (and a
# zero-cache / single-session report) renders unchanged.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase F — multi-session & temporal sections. Every builder gates on its
# data being present (project / instance scope only) and returns "" otherwise,
# so the single-session and minimal-fixture paths render byte-identically.
# All colours come from theme CSS vars — no hardcoded hex — so the four themes
# work without per-builder overrides.
# ---------------------------------------------------------------------------

def _build_session_shape_histograms_html(hist: dict) -> str:
    """Three side-by-side bar charts of per-session duration / turns / cost
    distribution (F.1). Static bars (Python sets the heights) — no JS. Returns
    "" on the degenerate single-session path (hist == {})."""
    if not hist:
        return ""

    def _panel(title: str, dist: dict, fmt) -> str:
        counts = dist.get("counts") or []
        labels = dist.get("labels") or []
        mx = max(counts) if counts else 0
        bars = "".join(
            f'<div title="{html_mod.escape(str(labels[i] if i < len(labels) else ""))}: '
            f'{c} session{"s" if c != 1 else ""}" '
            f'style="flex:1;background:var(--accent);border-radius:2px 2px 0 0;'
            f'min-height:{"0" if c == 0 else "1px"};'
            f'height:{(c / mx * 100) if mx else 0:.1f}%"></div>'
            for i, c in enumerate(counts)
        )
        lab = "".join(
            f'<div style="flex:1;text-align:center;overflow:hidden">'
            f'{html_mod.escape(str(lbl))}</div>'
            for lbl in labels
        )
        p50 = fmt(dist.get("p50", 0))
        p90 = fmt(dist.get("p90", 0))
        return (
            '<div style="background:var(--surface-deep);border:1px solid var(--border);'
            'border-radius:8px;padding:12px">\n'
            f'  <div style="font-size:12px;color:var(--fg-dim);margin-bottom:8px">{title}</div>\n'
            '  <div style="display:flex;align-items:flex-end;gap:3px;height:120px;'
            'border-bottom:1px solid var(--border-dim)">'
            f'{bars}</div>\n'
            "  <div style=\"display:flex;gap:3px;margin-top:4px;font-size:9px;"
            "color:var(--fg-dim);font-family:'JetBrains Mono',monospace\">"
            f'{lab}</div>\n'
            f'  <div style="margin-top:8px;font-size:11px;color:var(--fg-dim)">'
            f'p50 {p50} &middot; p90 {p90}</div>\n'
            '</div>'
        )

    def _dur(v):  # noqa: ANN001 — local formatter
        return html_mod.escape(_sm()._fmt_long_duration(float(v or 0)))

    def _int(v):  # noqa: ANN001
        return f"{int(v or 0):,}"

    def _cost(v):  # noqa: ANN001
        return f"${float(v or 0):,.4f}"

    panels = (
        _panel("Duration", hist.get("duration") or {}, _dur)
        + _panel("Turns", hist.get("turns") or {}, _int)
        + _panel("Cost", hist.get("cost") or {}, _cost)
    )
    return (
        '<section class="section" id="session-shape-section">\n'
        '  <div class="section-title"><h2>Session shape distribution</h2>'
        '<span class="hint">multi-session &middot; fixed bucket edges</span></div>\n'
        '  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">\n'
        f'  {panels}\n'
        '  </div>\n</section>'
    )


def _build_cache_economics_html(econ: dict) -> str:
    """Cache-economics KPI row: weighted hit ratio, no-cache counterfactual,
    actual savings, savings fraction, and (≥3 sessions) hit-ratio dispersion
    (F.2). Negative savings are surfaced honestly via label + sign — never
    clamped. Returns "" when econ == {}."""
    if not econ:
        return ""
    weighted = float(econ.get("weighted_hit_ratio", 0.0) or 0.0) * 100
    counter = float(econ.get("counterfactual_cost", 0.0) or 0.0)
    savings = float(econ.get("actual_savings", 0.0) or 0.0)
    frac = float(econ.get("savings_fraction", 0.0) or 0.0) * 100
    n = int(econ.get("session_count", 0) or 0)
    if savings < 0:
        save_label = "Cache net cost"
        save_val = f"-${-savings:,.4f}"
    else:
        save_label = "Actual savings"
        save_val = f"${savings:,.4f}"
    cards = (
        f'<div class="kpi cat-tokens"><div class="kpi-label">Weighted hit ratio</div>'
        f'<div class="kpi-val">{weighted:.1f}%</div>'
        f'<div class="kpi-sub">across {n} sessions</div></div>'
        f'<div class="kpi cat-tokens"><div class="kpi-label">No-cache counterfactual</div>'
        f'<div class="kpi-val">${counter:,.4f}</div>'
        f'<div class="kpi-sub">baseline without cache</div></div>'
        f'<div class="kpi cat-save"><div class="kpi-label">{save_label}</div>'
        f'<div class="kpi-val">{save_val}</div>'
        f'<div class="kpi-sub">vs no-cache baseline</div></div>'
        f'<div class="kpi cat-tokens"><div class="kpi-label">Savings fraction</div>'
        f'<div class="kpi-val">{frac:.1f}%</div>'
        f'<div class="kpi-sub">of counterfactual cost</div></div>'
    )
    if n >= 3:
        std = float(econ.get("hit_ratio_std", 0.0) or 0.0)
        cards += (
            f'<div class="kpi cat-tokens"><div class="kpi-label">Hit-ratio &sigma;</div>'
            f'<div class="kpi-val">{std:.4f}</div>'
            f'<div class="kpi-sub">per-session dispersion</div></div>'
        )
    return (
        '<section class="section" id="cache-economics-section">\n'
        '  <div class="section-title"><h2>Cache economics</h2>'
        '<span class="hint">weighted hit ratio &middot; no-cache counterfactual</span></div>\n'
        f'  <div class="kpi-grid">{cards}</div>\n</section>'
    )


def _build_project_concentration_html(conc: dict) -> str:
    """Cost-concentration table + headline top-N share KPI (F.3). Returns ""
    when conc == {} (fewer than top_n+1 items)."""
    if not conc:
        return ""
    top_n = int(conc.get("top_n", 3) or 3)
    share = float(conc.get("top_n_share", 0.0) or 0.0) * 100
    items = conc.get("top_items") or []
    total_cost = float(conc.get("total_cost", 0.0) or 0.0)
    top_cost = float(conc.get("top_n_cost", 0.0) or 0.0)
    rows = "".join(
        f'<tr><td>{html_mod.escape(str(it.get("name", "")))}</td>'
        f'<td style="text-align:right">${float(it.get("cost", 0.0) or 0.0):,.4f}</td>'
        f'<td style="text-align:right">{float(it.get("share", 0.0) or 0.0) * 100:.1f}%</td></tr>'
        for it in items
    )
    remainder = total_cost - top_cost
    if remainder > 0:
        rows += (
            f'<tr><td style="color:var(--fg-dim)">Other</td>'
            f'<td style="text-align:right;color:var(--fg-dim)">${remainder:,.4f}</td>'
            f'<td style="text-align:right;color:var(--fg-dim)">'
            f'{(remainder / total_cost * 100) if total_cost else 0:.1f}%</td></tr>'
        )
    return (
        '<section class="section" id="project-concentration-section">\n'
        '  <div class="section-title"><h2>Cost concentration</h2>'
        f'<span class="hint">top-{top_n} share of total spend</span></div>\n'
        '  <div class="health-panel">\n'
        f'    <div class="kpi cat-save" style="margin-bottom:12px"><div class="kpi-label">'
        f'Top-{top_n} share</div><div class="kpi-val">{share:.1f}%</div>'
        f'<div class="kpi-sub">${top_cost:,.4f} of ${total_cost:,.4f}</div></div>\n'
        '    <table class="mini-table" style="width:100%">\n'
        '      <thead><tr><th>Name</th>'
        '<th style="text-align:right">Cost</th>'
        '<th style="text-align:right">Share</th></tr></thead>\n'
        f'      <tbody>{rows}</tbody>\n'
        '    </table>\n'
        '  </div>\n</section>'
    )


def _build_activity_heatmap_html(heatmap: dict, tz_label: str = "UTC") -> str:
    """GitHub-style daily session-activity calendar (F.5). Static cells with a
    ``data-bucket`` attribute resolved by inline scoped CSS — no JS. Weeks are
    columns, weekdays rows; the first cell is offset to its weekday so the
    calendar aligns. Returns "" when there is no date data."""
    if not heatmap or not heatmap.get("dates"):
        return ""
    dates = heatmap["dates"]
    items = list(dates.items())  # already sorted by the compute layer
    first_date = items[0][0]
    try:
        first_wd = datetime.strptime(first_date, "%Y-%m-%d").weekday()  # Mon=0..Sun=6
    except ValueError:
        first_wd = 0
    cells = []
    for i, (d, n) in enumerate(items):
        b = 0 if n == 0 else 1 if n == 1 else 2 if n <= 3 else 3
        offset = f'grid-row-start:{first_wd + 1};' if i == 0 else ""
        cells.append(
            f'<div class="hm-cell" data-bucket="{b}" '
            f'title="{html_mod.escape(d)}: {n} session{"s" if n != 1 else ""}" '
            f'style="{offset}"></div>'
        )
    total_days = int(heatmap.get("total_active_days", 0) or 0)
    legend = (
        '<div style="display:flex;align-items:center;gap:6px;margin-top:10px;'
        "font-size:10px;color:var(--fg-dim);font-family:'JetBrains Mono',monospace\">"
        '<span>Less</span>'
        '<span class="hm-cell" data-bucket="0"></span>'
        '<span class="hm-cell" data-bucket="1"></span>'
        '<span class="hm-cell" data-bucket="2"></span>'
        '<span class="hm-cell" data-bucket="3"></span>'
        '<span>More</span></div>'
    )
    # Intensity ramp = one accent colour at rising opacity (bucket 0 = idle =
    # border-dim). Using opacity rather than accent-soft → accent keeps the ramp
    # monotonic in every theme (in some themes accent-soft is a contrasting hue,
    # which would read as a separate category mid-scale, not "more").
    style = (
        '<style>\n'
        "#activity-heatmap-section .hm-grid{display:grid;grid-auto-flow:column;"
        "grid-template-rows:repeat(7,12px);grid-auto-columns:12px;gap:3px;"
        "overflow-x:auto}\n"
        "#activity-heatmap-section .hm-cell{width:12px;height:12px;border-radius:2px;"
        "background:var(--border-dim);display:inline-block}\n"
        "#activity-heatmap-section .hm-cell[data-bucket='1']{background:var(--accent);opacity:.4}\n"
        "#activity-heatmap-section .hm-cell[data-bucket='2']{background:var(--accent);opacity:.7}\n"
        "#activity-heatmap-section .hm-cell[data-bucket='3']{background:var(--accent);opacity:1}\n"
        '</style>'
    )
    return (
        '<section class="section" id="activity-heatmap-section">\n'
        f'  {style}\n'
        '  <div class="section-title"><h2>Session activity</h2>'
        '<span class="hint">distinct sessions per day &middot; '
        f'{html_mod.escape(tz_label)}</span></div>\n'
        '  <div class="health-panel">\n'
        f'    <div class="hm-grid">{"".join(cells)}</div>\n'
        f'    <div style="margin-top:10px;font-size:11px;color:var(--fg-dim)">'
        f'{total_days} active day{"s" if total_days != 1 else ""}</div>\n'
        f'    {legend}\n'
        '  </div>\n</section>'
    )


def _build_session_activity_by_hour_html(by_hour: list, tz_label: str = "UTC") -> str:
    """24-bar chart of distinct sessions active in each local hour (F.4). A
    different metric from the prompt-per-hour chart (sessions, not prompts), so
    it renders as a separate section. Static bars — no JS. Returns "" when
    empty / all-zero."""
    if not by_hour or len(by_hour) != 24 or max(by_hour) == 0:
        return ""
    mx = max(by_hour)
    bars = "".join(
        f'<div title="{h:02d}:00  {c} session{"s" if c != 1 else ""}" '
        f'style="flex:1;background:var(--accent);border-radius:2px 2px 0 0;'
        f'min-height:{"0" if c == 0 else "1px"};height:{(c / mx * 100):.1f}%"></div>'
        for h, c in enumerate(by_hour)
    )
    axis = "".join(
        f'<div style="flex:1;text-align:center">{h:02d}</div>' for h in range(24)
    )
    return (
        '<section class="section" id="session-activity-hour-section">\n'
        '  <div class="section-title"><h2>Sessions per hour</h2>'
        '<span class="hint">distinct sessions active each local hour &middot; '
        f'{html_mod.escape(tz_label)}</span></div>\n'
        '  <div class="health-panel">\n'
        '    <div style="display:flex;align-items:flex-end;gap:2px;height:140px;'
        'border-bottom:1px solid var(--border-dim)">'
        f'{bars}</div>\n'
        "    <div style=\"display:flex;gap:2px;margin-top:6px;font-size:10px;"
        "color:var(--fg-dim);font-family:'JetBrains Mono',monospace\">"
        f'{axis}</div>\n'
        '  </div>\n</section>'
    )


def _build_cache_efficiency_html(totals: dict) -> str:
    """Cache-efficiency 4-segment token bar + savings callout (D.1).

    Auto-hides when there is no cache-read activity (a no-cache session has
    nothing to say here). Negative net savings are reframed as a cost — same
    discipline as the C.3 footer/KPI — never clamped to a misleading "$0 saved".
    Pure read of ``totals``; never mutates the report.
    """
    if int(totals.get("cache_read", 0) or 0) <= 0:
        return ""
    bar = _sm()._build_cache_efficiency_svg(totals)
    if not bar:
        return ""
    hit = float(totals.get("cache_hit_pct", 0.0) or 0.0)
    saved = float(totals.get("cache_savings", 0.0) or 0.0)
    if saved < 0:
        saved_txt = (f'<span style="color:#d29922">Cache net cost '
                     f'${-saved:,.4f} vs no-cache baseline</span>')
    else:
        saved_txt = f'${saved:,.4f} saved vs no-cache baseline'
    swatches = (
        ("cache-read",  "var(--accent)"),
        ("cache-write", "var(--accent-soft)"),
        ("new-input",   "var(--fg-dim)"),
        ("output",      "var(--border)"),
    )
    legend = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px">'
        f'<span style="width:11px;height:11px;border-radius:3px;'
        f'display:inline-block;background:{c}"></span>{lbl}</span>'
        for lbl, c in swatches
    )
    return (
        '<section class="section" id="cache-efficiency-section">\n'
        '  <div class="section-title"><h2>Cache efficiency</h2>'
        '<span class="hint">token composition &amp; cache savings</span></div>\n'
        '  <div class="health-panel">\n'
        f'    {bar}\n'
        f'    <div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:12px;'
        f"font-family:'JetBrains Mono',monospace;font-size:11px\">{legend}</div>\n"
        f'    <div style="margin-top:12px;font-size:13px">{hit:.1f}% cache-read '
        f'ratio &middot; {saved_txt}</div>\n'
        '  </div>\n</section>'
    )


def _build_velocity_html(report: dict) -> str:
    """Velocity KPI cards (D.2) — surfaces the C.5 ``report['velocity']`` stats
    (cost/active-min, tokens/active-min, p50/p90 request-cycle time) as a 2x2
    card grid. Auto-hides when velocity is empty (no request unit had a usable
    wall-clock). Reads precomputed values only — no recompute, no mutation, so
    the page never shows two divergent velocity numbers.
    """
    v = report.get("velocity") or {}
    if not v or not v.get("filtered_unit_count"):
        return ""
    cpm = float(v.get("cost_per_active_min", 0.0) or 0.0)
    tpm = float(v.get("tokens_per_active_min", 0.0) or 0.0)
    p50 = v.get("p50_cycle_s", 0)
    p90 = v.get("p90_cycle_s", 0)
    n = int(v.get("filtered_unit_count", 0))
    total_n = int(v.get("unit_count", 0))
    active = float(v.get("active_minutes", 0.0) or 0.0)
    cap = _sm()._VELOCITY_CYCLE_CAP_S
    # Spell out the excluded cohort: single-turn / zero-duration units have no
    # measurable wall-clock and are dropped from the throughput numerator AND
    # denominator (so the rates stay internally consistent for the timed cohort,
    # but don't describe the whole session). Make that explicit when n < total.
    excluded = max(0, total_n - n)
    sub = f'{n} of {total_n} request unit{"s" if total_n != 1 else ""}'
    if excluded:
        sub += f' ({excluded} excluded — no measurable duration)'
    cards = (
        f'<div class="kpi cat-time"><div class="kpi-label">Cost / active min</div>'
        f'<div class="kpi-val">${cpm:,.4f}</div>'
        f'<div class="kpi-sub">{active:,.1f} active min</div></div>'
        f'<div class="kpi cat-time"><div class="kpi-label">Tokens / active min</div>'
        f'<div class="kpi-val">{tpm:,.0f}</div>'
        f'<div class="kpi-sub">{sub}</div></div>'
        f'<div class="kpi cat-time"><div class="kpi-label">p50 cycle</div>'
        f'<div class="kpi-val">{p50}s</div>'
        f'<div class="kpi-sub">median request cycle</div></div>'
        f'<div class="kpi cat-time"><div class="kpi-label">p90 cycle</div>'
        f'<div class="kpi-val">{p90}s</div>'
        f'<div class="kpi-sub">each cycle capped at {cap}s</div></div>'
    )
    return (
        '<section class="section" id="velocity-section">\n'
        '  <div class="section-title"><h2>Velocity</h2>'
        '<span class="hint">cost &amp; token throughput per active minute</span></div>\n'
        f'  <div class="kpi-grid">{cards}</div>\n</section>'
    )


# Fixed 6-colour series palette for the stacked-area chart. The first four are
# theme-surface vars; the last two are the same semantic chart colours already
# used elsewhere in this file (acceptable as series colours — they are not
# theme-surface tokens).
_COST_SERIES_COLOURS = (
    "var(--accent)", "var(--accent-soft)", "var(--fg-dim)",
    "var(--border)", "#d29922", "#3fb950",
)


def _build_cost_over_time_svg_html(report: dict, top_n: int = 5) -> str:
    """Stacked-area chart of cumulative USD by model over the session's turn
    sequence (D.4). Session scope only (X = turn index); returns ``''`` for
    project/instance mode (the daily-cost rail already covers those) and when
    there are fewer than two turns with cost. Deterministic: models ranked by
    ``(-cost, id)``; all coordinates via ``_svg_scale`` on a shared y-max.
    """
    if report.get("mode") != "session":
        return ""
    turns: list[dict] = []
    for s in report.get("sessions") or []:
        for t in s.get("turns", []):
            if not t.get("is_resume_marker"):
                turns.append(t)
    n = len(turns)
    if n < 2:
        return ""
    model_cost: dict[str, float] = {}
    for t in turns:
        m = t.get("model") or "unknown"
        model_cost[m] = model_cost.get(m, 0.0) + float(t.get("cost_usd", 0.0) or 0.0)
    if not model_cost or sum(model_cost.values()) <= 0:
        return ""
    ranked = sorted(model_cost.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [m for m, _ in ranked[:top_n]]
    top_set = set(top)
    series_keys = top + (["Other"] if len(ranked) > top_n else [])
    # Per-series cumulative cost over the chronological turn sequence (running
    # sum, not per-turn) so the area rises monotonically left→right.
    csum = {k: [0.0] * n for k in series_keys}
    run = {k: 0.0 for k in series_keys}
    for i, t in enumerate(turns):
        m = t.get("model") or "unknown"
        key = m if m in top_set else "Other"
        run[key] += float(t.get("cost_usd", 0.0) or 0.0)
        for k in series_keys:
            csum[k][i] = round(run[k], 6)
    ymax = round(sum(model_cost.values()), 6)
    if ymax <= 0:
        return ""
    # Canvas with margins for axes. Uniform-scale (xMidYMid meet) so the axis
    # text isn't stretched. ML/MB leave room for $ (y) and turn (x) tick labels;
    # MR leaves room for the right-edge model labels.
    VB_W, VB_H = 720, 264
    ML, MR, MT, MB = 58, 110, 12, 30
    PAD = 6
    plot_w = VB_W - ML - MR
    plot_h = VB_H - MT - MB
    mono = "'JetBrains Mono',monospace"

    def _yat(v: float) -> float:
        # Matches _svg_scale(y_pad=PAD) within the plot area, offset by MT.
        return round(MT + plot_h - PAD - (v / ymax) * (plot_h - 2 * PAD), 2)

    x_scale = plot_w / (n - 1)

    def _xat(i: int) -> float:
        return round(ML + i * x_scale, 2)

    # --- Y gridlines + dollar tick labels -------------------------------------
    grid: list[str] = []
    for f in (0.0, 0.25, 0.5, 0.75, 1.0):
        gy = _yat(ymax * f)
        grid.append(
            f'<line x1="{ML}" y1="{gy}" x2="{ML + plot_w}" y2="{gy}" '
            f'stroke="var(--border)" stroke-width="1" stroke-opacity="0.4"/>'
        )
        grid.append(
            f'<text x="{ML - 8}" y="{round(gy + 3, 2)}" text-anchor="end" '
            f'font-family="{mono}" font-size="10" fill="var(--fg-dim)">'
            f'${ymax * f:,.2f}</text>'
        )
    # --- X axis baseline + turn-index tick labels -----------------------------
    base_y = _yat(0)
    axes = [
        f'<line x1="{ML}" y1="{base_y}" x2="{ML + plot_w}" y2="{base_y}" '
        f'stroke="var(--border)" stroke-width="1"/>'
    ]
    nticks = min(6, n)
    tick_i = sorted({round(k * (n - 1) / (nticks - 1)) for k in range(nticks)})
    xlabels = [
        f'<text x="{_xat(i)}" y="{VB_H - 11}" text-anchor="middle" '
        f'font-family="{mono}" font-size="10" fill="var(--fg-dim)">'
        f'{turns[i].get("index", i)}</text>'
        for i in tick_i
    ]
    xlabels.append(
        f'<text x="{ML + plot_w / 2}" y="{VB_H - 1}" text-anchor="middle" '
        f'font-family="{mono}" font-size="9" fill="var(--fg-dim)" '
        f'opacity="0.7">turn</text>'
    )
    # --- Stacked bands + top-edge stroke lines + point markers ----------------
    acc = [0.0] * n
    bands: list[str] = []
    lines: list[str] = []
    markers: list[str] = []
    label_data: list[tuple[float, str, str]] = []
    for ci, k in enumerate(series_keys):
        base = list(acc)
        for i in range(n):
            acc[i] = round(acc[i] + csum[k][i], 6)
        top_pairs, _, _ = _sm()._svg_scale(acc, plot_w, plot_h, y_pad=PAD,
                                           max_v=ymax)
        base_pairs, _, _ = _sm()._svg_scale(base, plot_w, plot_h, y_pad=PAD,
                                            max_v=ymax)
        if not top_pairs:
            continue
        tp = [(round(x + ML, 2), round(y + MT, 2)) for x, y in top_pairs]
        bp = [(round(x + ML, 2), round(y + MT, 2)) for x, y in base_pairs]
        colour = _COST_SERIES_COLOURS[ci % len(_COST_SERIES_COLOURS)]
        pts = ([f"{x},{y}" for x, y in tp]
               + [f"{x},{y}" for x, y in reversed(bp)])
        bands.append(f'<polygon fill="{colour}" fill-opacity="0.5" '
                     f'points="{" ".join(pts)}"/>')
        lines.append(f'<polyline fill="none" stroke="{colour}" '
                     f'stroke-width="1.5" points="{" ".join(f"{x},{y}" for x, y in tp)}"/>')
        # Data-point markers at the x-tick positions on this series' top edge.
        for i in tick_i:
            mx, my = tp[i]
            markers.append(
                f'<circle cx="{mx}" cy="{my}" r="2.2" fill="{colour}" '
                f'stroke="var(--bg)" stroke-width="1"><title>'
                f'{html_mod.escape(k[:18])} @ turn {turns[i].get("index", i)}: '
                f'${acc[i]:,.4f}</title></circle>'
            )
        label_data.append((tp[-1][1], html_mod.escape(k[:18]), colour))
    if not bands:
        return ""
    # Right-edge model labels, nudged apart so similar-height bands don't collide.
    label_data.sort()
    labels: list[str] = []
    last_y = -1e9
    for y, text, colour in label_data:
        y = max(y, last_y + 12)
        last_y = y
        labels.append(
            f'<text x="{ML + plot_w + 6}" y="{round(y + 3, 2)}" '
            f'font-family="{mono}" font-size="10" fill="{colour}">{text}</text>'
        )
    return (
        '<section class="section" id="cost-over-time-section">\n'
        '  <div class="section-title"><h2>Cost over time</h2>'
        f'<span class="hint">cumulative USD by model (top {top_n} + Other)</span></div>\n'
        '  <div class="chart-card">\n'
        f'    <svg class="cost-over-time" width="100%" viewBox="0 0 {VB_W} {VB_H}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Cumulative cost by model over turns">'
        f'{"".join(grid)}{"".join(bands)}{"".join(lines)}'
        f'{"".join(axes)}{"".join(markers)}{"".join(xlabels)}'
        f'{"".join(labels)}</svg>\n'
        '  </div>\n</section>'
    )


def _squarify(items: list[tuple[str, float]], W: int, H: int) -> list[dict]:
    """Bruls squarified treemap (D.5 helper).

    ``items`` MUST be pre-sorted descending by value (ties broken by label) so
    the layout is deterministic. Returns one ``{label, value, x, y, w, h}`` per
    positive-valued item, tiling the ``W``x``H`` canvas; coordinates are rounded
    to 2 dp for byte-stable output. Layout order matches input order, so callers
    can read rank from list position.
    """
    pos = [(lbl, float(val)) for lbl, val in items if val > 0]
    if not pos:
        return []
    total = sum(v for _, v in pos)
    sizes = [v / total * (W * H) for _, v in pos]  # value → area

    def _worst(row: list[float], length: float) -> float:
        if not row or length <= 0:
            return float("inf")
        s = sum(row)
        side = s / length
        rmax, rmin = max(row), min(row)
        return max((side * side) / rmin, rmax / (side * side)) if rmin else float("inf")

    rects: list[dict] = []
    x, y, dx, dy = 0.0, 0.0, float(W), float(H)
    idx = 0
    row: list[float] = []
    while idx < len(sizes):
        length = dy if dx >= dy else dx
        cand = sizes[idx]
        if not row or _worst(row, length) >= _worst(row + [cand], length):
            row.append(cand)
            idx += 1
            continue
        x, y, dx, dy = _layout_row(rects, row, x, y, dx, dy)
        row = []
    if row:
        _layout_row(rects, row, x, y, dx, dy)
    out: list[dict] = []
    for (lbl, val), r in zip(pos, rects, strict=False):
        out.append({"label": lbl, "value": round(val, 6),
                    "x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]})
    return out


def _layout_row(rects: list[dict], row: list[float],
                x: float, y: float, dx: float, dy: float
                ) -> tuple[float, float, float, float]:
    """Lay one squarify row along the shorter side; append rects, return the
    remaining free rectangle. Mutates ``rects`` in place (append-only)."""
    covered = sum(row)
    if dx >= dy:  # horizontal free space → stack the row vertically
        w = covered / dy if dy else 0.0
        cy = y
        for size in row:
            h = size / w if w else 0.0
            rects.append({"x": round(x, 2), "y": round(cy, 2),
                          "w": round(w, 2), "h": round(h, 2)})
            cy += h
        return (x + w, y, dx - w, dy)
    # vertical free space → stack the row horizontally
    h = covered / dx if dx else 0.0
    cx = x
    for size in row:
        w = size / h if h else 0.0
        rects.append({"x": round(cx, 2), "y": round(y, 2),
                      "w": round(w, 2), "h": round(h, 2)})
        cx += w
    return (x, y + h, dx, dy - h)


def _build_cost_treemap_html(report: dict, top_n: int = 20) -> str:
    """Squarified treemap of cost per session (D.5) — one tile per session,
    sized by ``subtotal.cost``. Auto-hides for single-session reports (fewer
    than two non-zero-cost sessions). Pure read of the report; no mutation.
    """
    sessions = report.get("sessions") or []
    costed = [(s.get("session_id", "")[:8],
               float(s.get("subtotal", {}).get("cost", 0.0) or 0.0))
              for s in sessions]
    costed = [(lbl, c) for lbl, c in costed if c > 0]
    if len(costed) < 2:
        return ""
    costed.sort(key=lambda x: (-x[1], x[0]))
    items = costed[:top_n]
    rest = costed[top_n:]
    if rest:
        items = items + [("Other", round(sum(c for _, c in rest), 6))]
        items.sort(key=lambda x: (-x[1], x[0]))
    W, H = 560, 260
    tiles = _sm()._squarify(items, W, H)
    if not tiles:
        return ""
    nt = len(tiles)
    parts: list[str] = []
    for rank, t in enumerate(tiles):
        opacity = round(0.9 - 0.6 * rank / max(1, nt - 1), 3)
        x, y, w, h = t["x"], t["y"], t["w"], t["h"]
        lbl, cost = t["label"], t["value"]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="var(--accent)" '
            f'fill-opacity="{opacity}" stroke="var(--bg)" stroke-width="1">'
            f'<title>{html_mod.escape(lbl)}: ${cost:,.4f}</title></rect>'
        )
        if w >= 40 and h >= 18:
            maxchars = max(1, int(w / 7))
            parts.append(
                f'<text x="{round(x + 4, 2)}" y="{round(y + 14, 2)}" '
                f'font-family="\'JetBrains Mono\',monospace" font-size="11" '
                f'fill="var(--fg)">{html_mod.escape(lbl[:maxchars])}</text>'
            )
    return (
        '<section class="section" id="cost-treemap-section">\n'
        '  <div class="section-title"><h2>Cost by session</h2>'
        f'<span class="hint">squarified by cost &middot; top {top_n} sessions</span></div>\n'
        '  <div class="health-panel">\n'
        f'    <svg class="cost-treemap" width="100%" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Cost by session treemap">{"".join(parts)}</svg>\n'
        '  </div>\n</section>'
    )


def _build_vital_signs_html(report: dict) -> str:
    """Session vital-signs timeline lanes — DEFERRED (D.6).

    The existing chart-rail section already shows the per-turn token-stack
    distribution at session scope; a second lane view of the same data would add
    page weight without a distinct analytical signal. The name is reserved here
    so a future implementer can add a concrete per-metric lane (e.g. latency,
    context pressure, or stop-reason over time) that the chart-rail does not
    already cover. Until then this is an intentional no-op.
    """
    return ""


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

def _theme_css() -> str:
    """Return the full themed stylesheet as a ``<style>...</style>`` block.

    Structure:
    - base reset + shared layout primitives (shell, page-header, topbar, nav,
      switcher, kpi grid, chart-card, punch, tod, rollup, blocks, chart-rail,
      timeline-table, drawer, prompts, foot)
    - four ``body.theme-<name>`` override blocks with matching colour tokens
    - legacy-class overlays (``.cards``/``.card``/``.usage-insights``/
      ``.turn-drawer``/``.prompts-table``/``.models-table``/timeline
      ``<table>`` inside ``.timeline-table`` etc.) mapped into theme
      surfaces so the Python renderer's existing f-string output keeps
      working under every theme.

    Intentionally kept as a non-f-string raw string so literal CSS braces
    don't need escaping.
    """
    return r"""<style>
/* =========================================================================
   BASE — shared reset, layout primitives, components
   ========================================================================= */
*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;padding:0}
body{min-height:100vh;font-family:'Inter',system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;transition:background-color .15s ease,color .15s ease;font-size:13px;zoom:1.25}
a{color:inherit;text-decoration:none}
.mono{font-family:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
.num{text-align:right;font-variant-numeric:tabular-nums}
.muted{opacity:.6}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}

/* Outer frame */
.shell{max-width:1440px;margin:0 auto;padding:32px 40px 80px}
.page-header{display:flex;align-items:baseline;justify-content:space-between;gap:24px;flex-wrap:wrap;margin-bottom:32px}
.page-header h1{margin:0;font-family:'Inter Tight','Inter',sans-serif;font-weight:600;font-size:28px;letter-spacing:-.02em}
.page-header .meta{font-family:'JetBrains Mono',monospace;font-size:12px;opacity:.65;text-align:right}
.crumbs{display:flex;gap:12px;align-items:center;font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.08em;text-transform:uppercase;opacity:.65;margin-bottom:10px;flex-wrap:wrap}
.crumbs .sep{opacity:.35}

.topbar{position:sticky;top:0;z-index:40;display:flex;justify-content:space-between;align-items:center;padding:14px 24px;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.topbar .brand{display:flex;gap:10px;align-items:center;font-family:'JetBrains Mono',monospace;font-size:12px;letter-spacing:.16em;text-transform:uppercase}
.topbar .brand .dot{width:8px;height:8px;border-radius:50%}
.topbar .nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.navlink{padding:6px 12px;border-radius:999px;font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;transition:all .15s ease}
.navlink.current{pointer-events:none}

.switcher{display:flex;gap:4px;padding:4px;border-radius:999px;margin-left:12px;flex-shrink:0}
.switcher button{padding:6px 12px;border-radius:999px;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;transition:all .15s ease;cursor:pointer;border:none;background:transparent}

.section{margin-top:40px}
.section-title{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-bottom:16px}
.section-title h2{margin:0;font-family:'Inter Tight','Inter',sans-serif;font-weight:600;font-size:18px;letter-spacing:-.01em}
.section-title .hint{font-family:'JetBrains Mono',monospace;font-size:11px;opacity:.55}

/* KPI grid + preview KPI cards */
.kpi-grid{display:grid;gap:16px;grid-template-columns:repeat(4,1fr)}
.kpi{padding:18px;border-radius:14px;position:relative;overflow:hidden;display:flex;flex-direction:column;gap:6px;min-height:100px}
.kpi .kpi-label{font-size:11px;letter-spacing:.1em;text-transform:uppercase;opacity:.7}
.kpi .kpi-val{font-family:'Inter Tight','Inter',sans-serif;font-weight:600;font-size:26px;letter-spacing:-.02em;line-height:1}
.kpi .kpi-sub{font-family:'JetBrains Mono',monospace;font-size:10px;opacity:.6;margin-top:auto}
.kpi .kpi-delta{font-family:'JetBrains Mono',monospace;font-size:10px}
.kpi .kpi-delta.up{color:#4ADE80}
.kpi .kpi-delta.down{color:#F87171}

/* Legacy ".cards"/".card" — maps into KPI-style surfaces */
.cards{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin:0 0 24px 0}
.cards .card{padding:14px 18px;border-radius:10px;min-width:0;position:relative}
.cards .card .val{font-family:'Inter Tight','Inter',sans-serif;font-weight:700;font-size:22px;line-height:1.1}
.cards .card .lbl{font-size:11px;margin-top:4px;opacity:.7;letter-spacing:.02em}

/* Insights details panel (preview) */
details.insights{border-radius:12px;padding:0;overflow:hidden;margin-bottom:20px}
details.insights summary{cursor:pointer;padding:14px 20px;display:flex;align-items:center;justify-content:space-between;list-style:none;font-family:'Inter Tight','Inter',sans-serif;font-weight:500;font-size:14px}
details.insights summary::-webkit-details-marker{display:none}
details.insights summary .toggle{font-family:'JetBrains Mono',monospace;font-size:11px;opacity:.5;transition:transform .2s ease}
details.insights[open] summary .toggle{transform:rotate(90deg)}
details.insights .body{padding:4px 20px 20px;font-size:13px;line-height:1.65;opacity:.88}
details.insights .body ul{margin:0;padding-left:22px}
details.insights .body li{margin:6px 0}

/* Legacy .usage-insights wrapper — styled through theme rules */
.usage-insights{margin:0 0 24px;padding:14px 18px;border-radius:12px}
/* Session-health / Session-behavior panels — theme-aware card chrome via vars
   so they match the surrounding sections across all four themes. */
.health-panel{padding:16px 18px;border-radius:12px;border:1px solid var(--border);background:var(--surface-deep,var(--surface))}
.health-panel ul{margin:8px 0 0;padding-left:20px}
.health-panel ul ul{margin:2px 0}
.health-panel .mini-table{border-collapse:collapse;font-size:13px}
.health-panel .mini-table th{text-align:left;color:var(--fg-dim,#888);font-weight:500;padding:2px 16px 2px 0;border-bottom:1px solid var(--border-dim,var(--border))}
.health-panel .mini-table td{padding:2px 16px 2px 0}
.usage-insights .ui-top{font-size:13px;line-height:1.55;margin:0}
.usage-insights .ui-top strong{font-size:15px;font-weight:600;margin-right:6px}
.usage-insights details{margin-top:10px;padding-top:8px;border-top:1px solid var(--border-dim)}
.usage-insights details > summary{list-style:none;cursor:pointer;font-size:12px;padding:4px 0;user-select:none;opacity:.75}
.usage-insights details > summary::-webkit-details-marker{display:none}
.usage-insights details > summary::before{content:"\25b8  ";font-size:10px;margin-right:4px}
.usage-insights details[open] > summary::before{content:"\25be  "}
.usage-insights ul.ui-list{list-style:none;padding:6px 0 0;margin:0}
.usage-insights ul.ui-list li{padding:7px 0;font-size:12px;line-height:1.5;border-top:1px dashed var(--border-dim)}
.usage-insights ul.ui-list li:first-child{border-top:none}
.usage-insights ul.ui-list li strong{font-weight:600;margin-right:6px}

/* Rollup / blocks / chart cards / punch / tod */
.rollup{padding:16px 20px;border-radius:12px}
.rollup table{width:100%;border-collapse:collapse;font-size:12px;font-family:'JetBrains Mono',monospace}
.rollup th,.rollup td{padding:8px 10px;text-align:right}
.rollup th:first-child,.rollup td:first-child{text-align:left}
.rollup thead th{font-weight:500;font-size:10px;letter-spacing:.1em;text-transform:uppercase;opacity:.55;border-bottom:1px solid var(--border);padding-bottom:10px}
.rollup tbody tr:hover td{background:var(--hover,transparent)}

.blocks{padding:16px 20px;border-radius:12px}
.block-row{display:grid;grid-template-columns:120px 1fr 80px 80px;gap:14px;align-items:center;padding:8px 0;font-size:12px;border-bottom:1px solid var(--border-dim)}
.block-row:last-child{border-bottom:0}
.block-row .label{font-family:'JetBrains Mono',monospace;opacity:.75}
.block-row .bar{height:8px;border-radius:4px;background:var(--bar-bg);overflow:hidden}
.block-row .bar-fill{height:100%;border-radius:4px;background:var(--accent)}

.chart-card{padding:16px 20px;border-radius:12px}
.chart-card .chart-body{width:100%;height:200px}
.chart-card svg{width:100%;height:100%;display:block}

.punch{padding:16px 20px;border-radius:12px;overflow-x:auto}
.punch-grid{min-width:580px}
.punch-row{display:flex;align-items:center;gap:3px;margin-bottom:3px}
.punch-day{flex:0 0 38px;font-family:'JetBrains Mono',monospace;font-size:10px;opacity:.45;text-align:right;padding-right:6px;white-space:nowrap}
.punch-hour{flex:1;font-family:'JetBrains Mono',monospace;font-size:9px;opacity:.45;text-align:center;overflow:hidden}
.punch-cell{flex:1;aspect-ratio:1;border-radius:3px;background:var(--punch-empty);display:flex;align-items:center;justify-content:center;min-width:0}
.punch-dot{border-radius:50%;transition:all .2s ease}
.punch-head-row{display:flex;align-items:center;gap:14px;margin-bottom:10px;flex-wrap:wrap}
.tz-select{background:var(--bg);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-family:'JetBrains Mono',monospace;font-size:11px;cursor:pointer}
.tz-select:focus{outline:none;border-color:var(--accent)}

.tod{padding:16px 20px;border-radius:12px}
.tod-head{display:flex;align-items:center;gap:14px;margin-bottom:14px;flex-wrap:wrap}
.tod-head .tod-tz{background:var(--bg);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-family:'JetBrains Mono',monospace;font-size:11px;cursor:pointer}
.tod-head .tod-tz:focus{outline:none;border-color:var(--accent)}
.tod-head .tod-total{font-family:'JetBrains Mono',monospace;font-size:11px;opacity:.65}
.tod-head .tod-total strong{opacity:1;font-weight:500}
.tod-rows{display:flex;flex-direction:column;gap:8px}
.tod-row{display:grid;grid-template-columns:130px 1fr 60px;align-items:center;gap:12px}
.tod-row .tod-label{font-family:'Inter',sans-serif;font-size:12px;opacity:.65;text-align:right}
.tod-row .tod-track{position:relative;height:20px;background:var(--punch-empty);border-radius:4px;overflow:hidden}
.tod-row .tod-fill{position:absolute;top:0;left:0;height:100%;background:var(--accent);border-radius:4px;min-width:2px;transition:width .25s ease}
.tod-row .tod-cnt{font-family:'JetBrains Mono',monospace;font-size:12px;text-align:right;opacity:.9;font-variant-numeric:tabular-nums}

/* Tables (legacy generic) — kept for Timeline / Prompts / Models */
table{width:100%;border-collapse:collapse;font-size:12px}
h1{font-size:22px;font-weight:600;margin:0 0 6px}
h2{font-size:15px;font-weight:600;margin:24px 0 12px;font-family:'Inter Tight','Inter',sans-serif;letter-spacing:-.005em}
h2 .legend{font-size:11px;font-weight:400;margin-left:10px;opacity:.6}
h2 .legend code{border-radius:3px;padding:0 4px;font-size:10px}
h2 .legend b{font-weight:600;opacity:.9}

.meta{font-size:11px;margin-bottom:20px;opacity:.65}
.meta code{border-radius:3px;padding:0 5px;font-size:10px}

th{font-weight:500;text-align:left;padding:8px 10px;white-space:nowrap;font-size:11px;letter-spacing:.04em;opacity:.75}
td{padding:6px 10px;vertical-align:middle}
tr:hover td{background:var(--hover,transparent)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.ts{white-space:nowrap;opacity:.75}
td.model{font-size:11px}
.skill-tag{display:inline-block;font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(99,102,241,.2);color:#a5b4fc;margin-left:5px;white-space:nowrap;vertical-align:middle;letter-spacing:.02em}
td.cost{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.bar{display:inline-block;height:7px;border-radius:2px;margin-right:6px;vertical-align:middle}
tr.session-header{cursor:pointer}
tr.session-header td{padding:10px 12px;font-size:12px}
tr.session-header:hover td{filter:brightness(1.15)}
.toggle-arrow{display:inline-block;font-size:10px;transition:transform .15s;margin-right:4px}
tr.session-header.open .toggle-arrow{transform:rotate(90deg)}
tr.subtotal td{font-weight:600}
.models-table{padding:14px 16px;border-radius:12px}
.models-table table{font-size:12px;font-family:'JetBrains Mono',monospace}
.models-table code{font-size:11px}
.models-table th,.models-table td{padding:7px 12px}

/* Turn character & efficiency signals (v1.8.0) */
.waste-analysis{padding:14px 16px;border-radius:12px}
.waste-analysis h2{font-size:13px;font-weight:600;margin:0 0 10px;letter-spacing:.04em;text-transform:uppercase;opacity:.7}
.wc-bar{display:flex;height:18px;border-radius:9px;overflow:hidden;width:100%;margin-bottom:12px;gap:1px}
.wc-bar-seg{height:100%;min-width:2px;transition:opacity .15s}
.wc-bar-seg:hover{opacity:.8;cursor:default}
.wc-legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:11px;margin-bottom:14px}
.wc-legend td{padding:2px 4px;font-size:11px}
.wc-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
.wc-cards{display:flex;flex-wrap:wrap;gap:10px;margin-top:4px}
.wc-card{flex:1 1 200px;min-width:160px;padding:10px 12px;border-radius:8px;border:1px solid var(--border);background:var(--surface-deep,var(--border-dim));font-size:11px;font-family:'JetBrains Mono',monospace}
.wc-card h3{font-size:11px;font-weight:600;margin:0 0 6px;opacity:.8;text-transform:uppercase;letter-spacing:.04em}
.wc-card .wc-cost{font-size:12px;font-weight:600;color:var(--accent);margin-bottom:4px}
.wc-card ul{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:3px}
.wc-card li{opacity:.85;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wc-char{font-size:11px}
.wc-char-inner{display:flex;align-items:center;gap:4px;max-width:160px;overflow:hidden;white-space:nowrap}
.wc-char-inner > span.wc-lbl{overflow:hidden;text-overflow:ellipsis;min-width:0;flex:1}
.wc-risk-badge{display:inline-block;flex-shrink:0;font-size:9px;padding:0 3px;border-radius:3px;background:rgba(248,113,113,.18);color:#f87171;border:1px solid rgba(248,113,113,.3);vertical-align:middle;cursor:help}

/* Cache breaks (Phase A v1.6.0) — surface gets per-theme background via theme override blocks below; CSS-variable-driven inner styles work across all four variants. */
.cache-breaks{padding:14px 16px;border-radius:12px;display:flex;flex-direction:column;gap:8px}
.cache-break-row{padding:10px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface-deep,var(--border-dim));font-family:'JetBrains Mono',monospace;font-size:11px;cursor:pointer;transition:border-color .15s ease,background .15s ease}
.cache-break-row[open]{background:var(--hover,rgba(165,139,255,.05));border-color:var(--accent)}
.cache-break-row summary{list-style:none;display:flex;flex-wrap:wrap;align-items:baseline;gap:6px;line-height:1.6}
.cache-break-row summary::-webkit-details-marker{display:none}
.cache-break-row summary::before{content:"\25b8";display:inline-block;color:var(--accent);font-size:10px;margin-right:4px;transition:transform .15s ease;width:10px}
.cache-break-row[open] summary::before{transform:rotate(90deg)}
.cache-break-row .cb-uncached{color:#F87171}
.cache-break-row .cb-uncached strong{font-size:12px;font-weight:600}
.cache-break-row .cb-pct{opacity:.7}
.cache-break-row .cb-proj{color:var(--accent);opacity:.85;font-weight:500}
.cache-break-row .cb-ts{opacity:.6;font-size:10px}
.cache-break-row .cb-snippet{opacity:.85;flex:1 1 240px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cb-context{list-style:none;margin:10px 0 4px;padding:8px 12px;border-left:2px solid var(--border);font-size:11px;line-height:1.6;background:var(--bg);border-radius:0 6px 6px 0}
.cb-context li{padding:3px 0;display:flex;gap:10px;align-items:baseline;font-family:'JetBrains Mono',monospace}
.cb-context .cb-ts{flex-shrink:0;opacity:.5;font-size:10px;min-width:140px}
.cb-context .cb-txt{opacity:.85;word-break:break-word}
.cb-context li.cb-here{background:rgba(251,191,36,.06);margin:4px -12px;padding:5px 12px;border-left:2px solid #FBBF24;border-radius:0}
.cb-context li.cb-here .cb-mark{color:#FBBF24;font-size:10px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}

/* Phase-B (v1.7.0) "+N subagents" badge on Prompts table rows. Teal contrasts with the purple slash-command badge so the two badges stay distinguishable when both render on the same row. */
.prompts-subagent{display:inline-block;margin-left:6px;padding:1px 6px;font-size:10px;font-weight:500;letter-spacing:.04em;border-radius:4px;background:rgba(94,226,198,.14);color:#5EE2C6;border:1px solid rgba(94,226,198,.3);vertical-align:middle;cursor:help;white-space:nowrap}
.advisor-badge{display:inline-block;margin-left:6px;padding:1px 6px;font-size:10px;font-weight:500;letter-spacing:.04em;border-radius:4px;background:rgba(251,191,36,.12);color:#FCD34D;border:1px solid rgba(251,191,36,.3);vertical-align:middle;cursor:help;white-space:nowrap}
.ru-badge{display:inline-block;margin-left:6px;padding:1px 6px;font-size:10px;font-weight:500;border-radius:4px;background:rgba(245,158,11,.14);color:#f59e0b;border:1px solid rgba(245,158,11,.3);vertical-align:middle;cursor:help;white-space:nowrap}
.ru-risk{color:#f59e0b;font-variant-numeric:tabular-nums;cursor:help}
.models-table .prompts-slash{display:inline-block;padding:0 5px;font-size:10px;border-radius:3px;margin-left:6px;background:rgba(137,87,229,.18);border:1px solid rgba(137,87,229,.4);color:#bc8cff}

td.mode-fast{font-size:10px;font-weight:600}
td.mode-std{font-size:10px;opacity:.55}

/* TTL + content-block badges (existing contract) */
.badge-ttl{display:inline-block;margin-left:6px;padding:0 5px;font-size:9px;font-weight:600;letter-spacing:.06em;border-radius:3px;vertical-align:middle;cursor:help}
.badge-ttl.ttl-1h{background:rgba(165,139,255,.18);color:var(--accent)}
.badge-ttl.ttl-mix{background:rgba(251,191,36,.18);color:#FBBF24}
td.content-blocks,th.content-blocks{font-variant-numeric:tabular-nums;font-family:'JetBrains Mono',monospace;font-size:11px;white-space:nowrap;cursor:help;opacity:.85}
td.content-blocks.muted{opacity:.35;cursor:default}

.legend-block{font-size:11px;margin:-4px 0 12px;padding:8px 12px;border-radius:6px;line-height:1.6;opacity:.85}
.legend-block b{font-weight:600}
.legend-block code{border-radius:3px;padding:0 4px;font-size:10px}

.chart-page-label{font-size:11px;padding:8px 12px 0;margin-top:4px;opacity:.65}

/* Resume markers */
tr.resume-marker-row td{padding:6px 10px;border-top:1px dashed var(--border);border-bottom:1px dashed var(--border)}
tr.resume-marker-row td.resume-marker-idx{color:var(--accent);opacity:.7}
tr.resume-marker-row td.resume-marker-cell{text-align:center;font-size:12px;opacity:.8}
.resume-marker-pill{display:inline-flex;align-items:center;gap:8px;padding:3px 10px;border-radius:12px;cursor:help;background:rgba(165,139,255,.08);border:1px solid rgba(165,139,255,.28)}
.resume-marker-pill strong{color:var(--accent);font-weight:600;font-size:12px;letter-spacing:.2px}
.resume-marker-pill .resume-marker-icon{color:var(--accent);font-size:14px;line-height:1}
.resume-marker-pill .resume-marker-time{font-size:11px;opacity:.7;font-variant-numeric:tabular-nums}
.resume-marker-pill.terminal{background:rgba(251,191,36,.1);border-color:rgba(251,191,36,.4)}
.resume-marker-pill.terminal strong,.resume-marker-pill.terminal .resume-marker-icon{color:#FBBF24}
.resume-marker-pill.compaction{background:rgba(56,189,248,.1);border-color:rgba(56,189,248,.4)}
.resume-marker-pill.compaction strong,.resume-marker-pill.compaction .resume-marker-icon{color:#38BDF8}
.resume-marker-pill.continued{background:rgba(148,163,184,.08);border-color:rgba(148,163,184,.3)}
.resume-marker-pill.continued strong,.resume-marker-pill.continued .resume-marker-icon{color:var(--fg-dim)}

/* Idle-gap dividers */
tr.idle-gap-row td{padding:4px 10px;border-top:1px solid rgba(255,255,255,.06);border-bottom:1px solid rgba(255,255,255,.06)}
.idle-gap-cell{text-align:center;font-size:11px;opacity:.6}
.idle-gap-pill{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:10px;background:rgba(100,116,139,.12);border:1px solid rgba(100,116,139,.25);color:#94a3b8;font-variant-numeric:tabular-nums}

/* Model-switch dividers */
tr.model-switch-row td{padding:4px 10px;border-top:1px solid rgba(255,255,255,.06);border-bottom:1px solid rgba(255,255,255,.06)}
.model-switch-cell{text-align:center;font-size:11px;opacity:.65}
.model-switch-pill{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:10px;background:rgba(6,182,212,.08);border:1px solid rgba(6,182,212,.22);color:#67e8f9;font-variant-numeric:tabular-nums}

/* Truncated-response badge */
.truncated-tag{display:inline-block;font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(251,146,60,.18);color:#fb923c;margin-left:5px;white-space:nowrap;vertical-align:middle;letter-spacing:.02em}

/* Cache-break inline badge */
.cache-break-tag{display:inline-block;font-size:10px;padding:0 4px;border-radius:3px;background:rgba(251,191,36,.15);color:#fbbf24;margin-left:4px;white-space:nowrap;vertical-align:middle;cursor:help}

tr.turn-row{cursor:pointer}
tr.turn-row:focus{outline:1px solid var(--accent);outline-offset:-1px}

/* Chart container + controls */
#chart-container{border-radius:12px;margin-bottom:24px;min-height:420px;overflow:hidden}
.chart-controls{display:flex;gap:10px;align-items:center;padding:10px 16px 0;flex-wrap:wrap}
.chart-controls label{font-size:11px;display:flex;align-items:center;gap:5px;cursor:pointer;opacity:.75}
.chart-controls input[type=range]{width:120px;accent-color:var(--accent)}
.chart-controls span{font-size:11px;color:var(--accent);min-width:28px}

/* Turn drawer (preview) */
.drawer{position:fixed;top:0;right:0;height:100vh;width:min(520px,100%);transform:translateX(100%);transition:transform .25s cubic-bezier(.2,.8,.2,1);z-index:1000;display:flex;flex-direction:column;overflow:hidden;border-left:1px solid var(--border);background:var(--bg)}
.drawer.open{transform:translateX(0)}
.drawer-head{padding:24px 24px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:baseline;gap:16px}
.drawer-head h3{margin:0;font-family:'Inter Tight','Inter',sans-serif;font-weight:600;font-size:20px}
.drawer-head .x{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-size:18px;opacity:.6;background:none;border:0;cursor:pointer;color:inherit}
.drawer-head .x:hover{opacity:1;background:var(--hover,rgba(255,255,255,.05))}
.drawer-body{flex:1;overflow-y:auto;padding:20px 24px 32px}
.drawer-sec{margin-bottom:20px}
.drawer-sec h4{margin:0 0 8px;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;opacity:.55;font-weight:500}
.drawer-kv{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;font-family:'JetBrains Mono',monospace;font-size:12px;margin:0}
.drawer-kv dt{opacity:.55}
.drawer-kv dd{margin:0;text-align:right;font-variant-numeric:tabular-nums;word-break:break-word}
.drawer-prompt{padding:14px;border-radius:8px;background:var(--surface-deep,var(--border-dim));font-family:'JetBrains Mono',Menlo,Consolas,monospace;font-size:12px;line-height:1.55;white-space:pre-wrap;word-break:break-word;max-height:260px;overflow-y:auto;border:1px solid var(--border)}
.drawer-more{margin-top:8px;border:1px solid var(--border);padding:4px 10px;font-size:11px;border-radius:4px;cursor:pointer;color:var(--accent);background:none}
.drawer-more:hover{border-color:var(--accent)}
.drawer-tools-list{list-style:none;padding:0;margin:0;font-family:'JetBrains Mono',monospace;font-size:11px}
.drawer-tools-list li{padding:5px 0;border-top:1px dashed var(--border-dim)}
.drawer-tools-list li:first-child{border-top:none}
.drawer-tool-preview{font-size:10px;opacity:.7;margin-left:6px;word-break:break-word}
.drawer-savings{color:#3fb950;font-size:11px;margin-top:6px;font-family:'JetBrains Mono',monospace}
.drawer-wc-label{font-weight:600;margin:0 0 6px;font-size:13px}
.drawer-wc-label.risk{color:var(--acc-warn,#f0a500)}
.drawer-wc-label.ok{color:#3fb950}
.drawer-wc-explain{margin:0;font-size:12px;opacity:.8;line-height:1.55;font-family:'Inter',sans-serif}
.drawer-backdrop{position:fixed;inset:0;background:var(--backdrop,rgba(0,0,0,.5));opacity:0;pointer-events:none;transition:opacity .2s ease;z-index:999}
.drawer-backdrop.open{opacity:1;pointer-events:auto}

/* Chart-rail (horizontally-scrollable per-turn column chart) */
.chartrail-card{padding:20px 20px 16px;border-radius:20px;position:relative;--bar-h:200px;--head-h:0px;--foot-h:44px;--col-gap:4px}
.chartrail-legend{display:flex;gap:16px;flex-wrap:wrap;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;opacity:.7;margin-bottom:14px}
.chartrail-legend .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.chartrail-legend .sw.i{background:var(--accent)}
.chartrail-legend .sw.o{background:#5EE2C6}
.chartrail-legend .sw.cr{background:var(--accent);opacity:.3}
.chartrail-legend .sw.cw{background:#FBBF24}
.chartrail-legend .sw.cost{background:#F87171;border-radius:50%;width:8px;height:8px}
.chartrail-wrap{position:relative;display:grid;grid-template-columns:56px 1fr;gap:12px;align-items:start}
.chartrail-yaxis{position:relative;height:var(--bar-h);margin-top:var(--head-h);font-family:'JetBrains Mono',monospace;font-size:10px;opacity:.55}
.chartrail-yaxis .tick{position:absolute;right:4px;transform:translateY(-50%);white-space:nowrap}
.chartrail-yaxis .tick::after{content:"";position:absolute;right:-10px;top:50%;width:6px;height:1px;background:var(--border)}
.chartrail-scroll{position:relative;overflow-x:auto;overflow-y:hidden;scrollbar-width:thin;scroll-behavior:smooth;scroll-snap-type:x mandatory;padding-bottom:8px}
.chartrail-scroll::-webkit-scrollbar{height:6px}
.chartrail-scroll::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.chartrail-scroll::-webkit-scrollbar-track{background:transparent}
.chartrail-inner{display:flex;gap:var(--col-gap,4px);align-items:flex-start;min-width:100%}
.tcol{flex:0 0 auto;width:40px;padding:6px 2px;scroll-snap-align:start;cursor:pointer;position:relative;display:flex;flex-direction:column;outline:none;border-radius:8px;border:1px solid transparent;background:transparent;transition:background .15s ease,border-color .15s ease,transform .15s ease}
.tcol:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tcol:hover,.tcol.active{background:var(--hover,rgba(165,139,255,.06));border-color:var(--border)}
.tcol.active{border-color:var(--accent)}
.tcol .tc-bar{position:relative;width:100%;height:var(--bar-h);display:flex;flex-direction:column-reverse;justify-content:flex-start;border-radius:4px;overflow:hidden;background:rgba(255,255,255,.015)}
.tcol .tc-bar .seg{width:100%;display:block;flex-shrink:0;transition:opacity .15s ease}
.tcol .tc-bar .seg.i{background:var(--accent)}
.tcol .tc-bar .seg.o{background:#5EE2C6}
.tcol .tc-bar .seg.cw{background:#FBBF24}
.tcol .tc-bar .seg.cr{background:var(--accent);opacity:.3}
.tcol .tc-bar .seg.cost{background:var(--accent)}
.tcol .tc-foot{height:var(--foot-h);padding-top:6px;display:flex;flex-direction:column;align-items:center;gap:2px;font-family:'JetBrains Mono',monospace;font-size:10px;line-height:1.2;overflow:hidden}
.tcol .tc-foot .tc-n{color:var(--accent);font-weight:500}
.tcol .tc-foot .tc-time{opacity:.6;font-size:9px}
.tcol .tc-foot .tc-cost{font-family:'Inter Tight','Inter',sans-serif;font-weight:600;font-size:11px;opacity:.9}
.tcol.session-break{margin-left:16px;padding-left:12px;border-left:1px dashed var(--border)}
.tcol.session-break .tc-seslabel{position:absolute;top:-16px;left:12px;font-family:'JetBrains Mono',monospace;font-size:9px;opacity:.55;letter-spacing:.08em;white-space:nowrap}
.tcol.resume .tc-bar{background:rgba(165,139,255,.1);display:flex;align-items:center;justify-content:center;flex-direction:row}
.tcol.resume .tc-bar::before{content:"\2634";color:var(--accent);font-size:16px}
.rail-chev{position:absolute;top:130px;width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:var(--surface,#111);border:1px solid var(--border);z-index:3;cursor:pointer;opacity:.85;color:inherit;font-size:16px}
.rail-chev:hover{opacity:1}
.rail-chev.left{left:48px}
.rail-chev.right{right:-4px}
.rail-indicator{display:flex;align-items:center;gap:12px;justify-content:space-between;margin-top:14px;font-family:'JetBrains Mono',monospace;font-size:11px;opacity:.65}
.rail-progress{flex:1;height:2px;background:var(--border);border-radius:1px;overflow:hidden}
.rail-progress-fill{height:100%;background:var(--accent);width:10%;transition:width .1s linear}

/* Prompts (preview) */
.prompts{padding:20px;border-radius:16px;margin-top:16px}
.prompts table{font-size:12px}
.prompts th,.prompts td{padding:10px 12px;border-bottom:1px solid var(--border-dim);text-align:left;vertical-align:top}
.prompts th.num,.prompts td.num{text-align:right;font-family:'JetBrains Mono',monospace}
.prompts thead th{font-weight:500;font-size:10px;letter-spacing:.12em;text-transform:uppercase;opacity:.55;border-bottom:1px solid var(--border)}
.prompts .prompt-text{max-width:560px;font-family:'Inter',sans-serif;line-height:1.55;font-size:13px;opacity:.88}
.prompts .prompt-text.truncate{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.prompts tbody tr[data-turn]{cursor:pointer;transition:background .1s ease}
.prompts tbody tr[data-turn]:hover td,.prompts tbody tr[data-turn].active td{background:var(--hover,rgba(165,139,255,.05))}
.prompts tbody tr[data-turn].active td:first-child{box-shadow:inset 2px 0 0 var(--accent)}
.prompts tbody tr[data-turn]:focus{outline:1px solid var(--accent);outline-offset:-1px}
.prompts .prompt-turn-link{color:var(--accent);text-decoration:none;font-family:'JetBrains Mono',monospace}
.prompts .prompt-turn-link:hover{text-decoration:underline}
.prompts td.cost{color:#d29922;font-variant-numeric:tabular-nums;white-space:nowrap}
.prompts td.model code{font-size:11px}
.prompts .prompts-slash{display:inline-block;padding:0 5px;font-size:10px;border-radius:3px;margin-left:6px;background:rgba(137,87,229,.18);border:1px solid rgba(137,87,229,.4);color:#bc8cff}

/* Footer */
.foot{margin-top:60px;padding:20px 0;border-top:1px solid var(--border-dim);font-family:'JetBrains Mono',monospace;font-size:11px;opacity:.5;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}

/* =========================================================================
   THEME 1 — BEACON MINIMAL (default)
   ========================================================================= */
body.theme-beacon{
  --bg:#0A0A0C;--surface:#111114;--surface-deep:#0E0E12;--border:#1E1E22;--border-dim:#16161a;
  --fg:#EDECEF;--fg-dim:#8C8B93;--accent:#A58BFF;--accent-soft:#7C6BD9;
  --punch-empty:#141418;--bar-bg:#1a1a1f;--hover:rgba(165,139,255,.05);
  --backdrop:rgba(0,0,0,.65);
  background:#0A0A0C;color:#EDECEF;
}
body.theme-beacon .topbar{background:rgba(10,10,12,.78);border-bottom:1px solid #16161a}
body.theme-beacon .topbar .brand .dot{background:#A58BFF;box-shadow:0 0 12px rgba(165,139,255,.5)}
body.theme-beacon .navlink{color:#8C8B93}
body.theme-beacon .navlink.current{color:#EDECEF;background:rgba(165,139,255,.1)}
body.theme-beacon .navlink:hover{color:#EDECEF}
body.theme-beacon .switcher{background:rgba(17,17,20,.88);border:1px solid #1E1E22;backdrop-filter:blur(12px)}
body.theme-beacon .switcher button{color:#8C8B93}
body.theme-beacon .switcher button.active{background:#A58BFF;color:#0A0A0C}
body.theme-beacon .kpi{background:#111114;border:1px solid #1E1E22;position:relative}
body.theme-beacon .kpi::before{content:"";position:absolute;top:0;left:0;width:20px;height:1px;background:#A58BFF}
body.theme-beacon .kpi::after{content:"";position:absolute;top:0;left:0;width:1px;height:20px;background:#A58BFF}
body.theme-beacon .kpi.featured .kpi-val{color:#A58BFF}
body.theme-beacon details.insights,body.theme-beacon .usage-insights,
body.theme-beacon .rollup,body.theme-beacon .blocks,body.theme-beacon .chart-card,
body.theme-beacon .punch,body.theme-beacon .tod,body.theme-beacon .models-table,
body.theme-beacon .cache-breaks,body.theme-beacon .waste-analysis,
body.theme-beacon .cards .card,body.theme-beacon #chart-container,
body.theme-beacon .legend-block,body.theme-beacon .prompts,
body.theme-beacon .timeline-table,body.theme-beacon .chartrail-card,
body.theme-beacon .drawer,body.theme-beacon #weekly-rollup,
body.theme-beacon #session-blocks,body.theme-beacon #hod-chart{background:#111114;border:1px solid #1E1E22}
body.theme-beacon .cards .card .val{color:#A58BFF}
body.theme-beacon .cards .card.green .val{color:#3fb950}
body.theme-beacon .cards .card.amber .val{color:#d29922}
body.theme-beacon th{background:#0E0E12;border-bottom:1px solid #1E1E22;color:#8C8B93}
body.theme-beacon td{border-bottom:1px solid #16161a}
body.theme-beacon tr.session-header td{background:#14141a;color:#A58BFF;border-top:2px solid #1E1E22}
body.theme-beacon tr.subtotal td{background:#111114;border-top:1px solid #1E1E22}

/* =========================================================================
   THEME 2 — CONSOLE GLASS
   ========================================================================= */
body.theme-console{
  --bg:#08080A;--surface:rgba(165,139,255,.04);--surface-deep:rgba(165,139,255,.02);
  --border:rgba(165,139,255,.16);--border-dim:rgba(165,139,255,.08);
  --fg:#E8E6F0;--fg-dim:#8A88A0;--accent:#A58BFF;--accent-soft:#5EE2C6;
  --punch-empty:rgba(165,139,255,.05);--bar-bg:rgba(165,139,255,.08);--hover:rgba(165,139,255,.07);
  --backdrop:rgba(0,0,0,.7);
  background:#08080A;color:#E8E6F0;
  background-image:radial-gradient(circle at 1px 1px,#1A1A20 1px,transparent 1px);
  background-size:24px 24px;
}
body.theme-console .page-header h1{font-family:'JetBrains Mono',monospace;font-weight:500;text-transform:uppercase;letter-spacing:.04em;font-size:20px}
body.theme-console .page-header h1::before{content:"[ ";color:#A58BFF;opacity:.7}
body.theme-console .page-header h1::after{content:" ]";color:#A58BFF;opacity:.7}
body.theme-console .section-title h2{font-family:'JetBrains Mono',monospace;font-weight:500;text-transform:uppercase;letter-spacing:.08em;font-size:12px}
body.theme-console .section-title h2::before{content:"[ ";color:#A58BFF;opacity:.6}
body.theme-console .section-title h2::after{content:" ]";color:#A58BFF;opacity:.6}
body.theme-console h2{font-family:'JetBrains Mono',monospace;font-weight:500;text-transform:uppercase;letter-spacing:.06em;font-size:12px;color:#A58BFF}
body.theme-console .topbar{background:rgba(8,8,10,.88);border-bottom:1px solid rgba(165,139,255,.12)}
body.theme-console .topbar .brand .dot{background:#A58BFF;box-shadow:0 0 8px #A58BFF,0 0 16px rgba(165,139,255,.5)}
body.theme-console .navlink{color:#8A88A0;font-family:'JetBrains Mono',monospace}
body.theme-console .navlink.current{color:#A58BFF;background:rgba(165,139,255,.08);border:1px solid rgba(165,139,255,.25)}
body.theme-console .switcher{background:rgba(8,8,10,.92);border:1px solid rgba(165,139,255,.2);backdrop-filter:blur(12px)}
body.theme-console .switcher button{color:#8A88A0}
body.theme-console .switcher button.active{background:rgba(165,139,255,.15);color:#A58BFF;border:1px solid #A58BFF}
body.theme-console .kpi{background:rgba(165,139,255,.04);border:1px solid rgba(165,139,255,.16);border-radius:10px}
body.theme-console .kpi .kpi-val{font-family:'JetBrains Mono',monospace;font-weight:500;font-size:22px;color:#A58BFF}
body.theme-console .kpi .kpi-label{font-family:'JetBrains Mono',monospace;color:#8A88A0}
body.theme-console .kpi.teal .kpi-val{color:#5EE2C6}
body.theme-console details.insights,body.theme-console .usage-insights,
body.theme-console .rollup,body.theme-console .blocks,body.theme-console .chart-card,
body.theme-console .punch,body.theme-console .tod,body.theme-console .models-table,
body.theme-console .cache-breaks,body.theme-console .waste-analysis,
body.theme-console .cards .card,body.theme-console #chart-container,
body.theme-console .legend-block,body.theme-console .prompts,
body.theme-console .timeline-table,body.theme-console .chartrail-card,
body.theme-console .drawer,body.theme-console #weekly-rollup,
body.theme-console #session-blocks,body.theme-console #hod-chart{background:rgba(165,139,255,.03);border:1px solid rgba(165,139,255,.14);border-radius:10px}
body.theme-console .cards .card .val{color:#A58BFF;font-family:'JetBrains Mono',monospace;font-weight:500}
body.theme-console .cards .card.green .val{color:#5EE2C6}
body.theme-console .cards .card.amber .val{color:#FFB86B}
body.theme-console th{background:rgba(165,139,255,.05);border-bottom:1px solid rgba(165,139,255,.16);color:#8A88A0;font-family:'JetBrains Mono',monospace}
body.theme-console td{border-bottom:1px solid rgba(165,139,255,.08)}
body.theme-console tr.session-header td{background:rgba(165,139,255,.08);color:#A58BFF;border-top:1px solid rgba(165,139,255,.2)}
body.theme-console tr.subtotal td{background:rgba(165,139,255,.05);border-top:1px solid rgba(165,139,255,.16)}
body.theme-console .drawer{background:var(--bg)}

/* =========================================================================
   THEME 3 — LATTICE COMPACT
   ========================================================================= */
body.theme-lattice{
  --bg:#09090C;--surface:#101014;--surface-deep:#0C0C10;--border:#17171C;--border-dim:#121216;
  --fg:#E4E2E8;--fg-dim:#7E7C88;--accent:#A58BFF;--accent-soft:#7C6BD9;
  --punch-empty:#131318;--bar-bg:#17171C;--hover:rgba(165,139,255,.05);
  --backdrop:rgba(0,0,0,.65);
  background:#09090C;color:#E4E2E8;font-size:12px;
}
body.theme-lattice .shell{padding-top:24px}
body.theme-lattice .page-header h1{font-family:'Inter Tight','Inter',sans-serif;font-weight:600;font-size:22px;letter-spacing:-.015em}
body.theme-lattice .section{margin-top:32px}
body.theme-lattice .section-title h2{font-weight:600;font-size:14px}
body.theme-lattice h2{font-size:14px}
body.theme-lattice .topbar{background:rgba(9,9,12,.92);border-bottom:1px solid #17171C}
body.theme-lattice .topbar .brand .dot{width:6px;height:6px;background:#A58BFF;border-radius:1px}
body.theme-lattice .navlink{color:#7E7C88}
body.theme-lattice .navlink.current{background:rgba(165,139,255,.1);color:#A58BFF}
body.theme-lattice .switcher{background:#101014;border:1px solid #17171C;border-radius:6px}
body.theme-lattice .switcher button{border-radius:4px}
body.theme-lattice .switcher button.active{background:#A58BFF;color:#09090C}
body.theme-lattice .kpi-grid{grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
body.theme-lattice .kpi{background:#101014;border-radius:8px;padding:14px;min-height:80px;position:relative;border:0}
body.theme-lattice .kpi::before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:2px;background:#A58BFF;border-radius:1px}
body.theme-lattice .kpi.cat-tokens::before{background:#5EE2C6}
body.theme-lattice .kpi.cat-time::before{background:#FBBF24}
body.theme-lattice .kpi.cat-save::before{background:#4ADE80}
body.theme-lattice .kpi .kpi-val{font-weight:600;font-size:22px}
body.theme-lattice .kpi .kpi-label{font-size:10px;letter-spacing:.08em}
body.theme-lattice details.insights,body.theme-lattice .usage-insights,
body.theme-lattice .rollup,body.theme-lattice .blocks,body.theme-lattice .chart-card,
body.theme-lattice .punch,body.theme-lattice .tod,body.theme-lattice .models-table,
body.theme-lattice .cache-breaks,body.theme-lattice .waste-analysis,
body.theme-lattice .cards .card,body.theme-lattice #chart-container,
body.theme-lattice .legend-block,body.theme-lattice .prompts,
body.theme-lattice .timeline-table,body.theme-lattice .chartrail-card,
body.theme-lattice .drawer,body.theme-lattice #weekly-rollup,
body.theme-lattice #session-blocks,body.theme-lattice #hod-chart{background:#101014;border:1px solid #17171C;border-radius:8px}
body.theme-lattice .cards .card{padding:12px 14px;position:relative}
body.theme-lattice .cards .card::before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:2px;background:#A58BFF;border-radius:1px}
body.theme-lattice .cards .card.green::before{background:#4ADE80}
body.theme-lattice .cards .card.amber::before{background:#FBBF24}
body.theme-lattice .cards .card .val{font-size:20px}
body.theme-lattice th{background:#0C0C10;border-bottom:1px solid #17171C;color:#7E7C88}
body.theme-lattice td{border-bottom:1px solid #121216}
body.theme-lattice tr.session-header td{background:#13111a;color:#A58BFF;border-top:1px solid #17171C}
body.theme-lattice tr.subtotal td{background:#101014;border-top:1px solid #17171C}

/* =========================================================================
   THEME 4 — PULSE (amber+lilac gradient)
   ========================================================================= */
body.theme-pulse{
  --bg:#0D0B14;--surface:#15121C;--surface-deep:#110F18;--border:#2A2438;--border-dim:#1D1928;
  --fg:#F2EFF7;--fg-dim:#9E9AAE;--accent:#C084FC;--accent-soft:#FFB86B;
  --punch-empty:#1D1928;--bar-bg:#1D1928;--hover:rgba(192,132,252,.08);
  --backdrop:rgba(0,0,0,.65);
  background:radial-gradient(circle at 85% -20%,rgba(255,184,107,.08),transparent 40%),radial-gradient(circle at -10% 120%,rgba(192,132,252,.12),transparent 50%),#0D0B14;
  color:#F2EFF7;
}
body.theme-pulse .page-header h1{font-weight:700;font-size:30px;letter-spacing:-.025em;background:linear-gradient(90deg,#FFB86B,#C084FC 60%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent}
body.theme-pulse h2{font-weight:600;font-size:17px;letter-spacing:-.015em}
body.theme-pulse .topbar{background:rgba(13,11,20,.82);border-bottom:1px solid #1D1928}
body.theme-pulse .topbar .brand .dot{background:#FFB86B;box-shadow:0 0 10px rgba(255,184,107,.6)}
body.theme-pulse .navlink{color:#9E9AAE}
body.theme-pulse .navlink.current{background:rgba(192,132,252,.12);color:#C084FC}
body.theme-pulse .switcher{background:rgba(21,18,28,.92);border:1px solid #2A2438;backdrop-filter:blur(12px)}
body.theme-pulse .switcher button{color:#9E9AAE}
body.theme-pulse .switcher button.active{background:linear-gradient(90deg,#FFB86B,#C084FC);color:#0D0B14}
body.theme-pulse .kpi{background:#15121C;border:1px solid #2A2438;border-radius:14px;position:relative;overflow:hidden}
body.theme-pulse .kpi::before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 100% 0%,rgba(255,184,107,.08),transparent 50%);pointer-events:none}
body.theme-pulse .kpi .kpi-val{font-weight:700;font-size:28px;letter-spacing:-.02em}
body.theme-pulse .kpi.featured{background:linear-gradient(135deg,rgba(192,132,252,.18),rgba(255,184,107,.12) 60%,#15121C);border:1px solid rgba(192,132,252,.35);animation:sm-pulse-ring-lg 3s ease-in-out infinite}
body.theme-pulse .kpi.featured .kpi-val{font-size:44px;line-height:1;background:linear-gradient(90deg,#FFB86B,#C084FC 60%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent}
body.theme-pulse .kpi.featured .kpi-label{color:#FFB86B;font-weight:600}
body.theme-pulse .kpi.cat-save .kpi-val,body.theme-pulse .kpi.teal .kpi-val{color:#5EE2C6}
body.theme-pulse .kpi.cat-time .kpi-val{color:#FFB86B}
@keyframes sm-pulse-ring-lg{0%,100%{box-shadow:0 0 0 0 rgba(192,132,252,.25)}50%{box-shadow:0 0 0 4px rgba(192,132,252,0)}}
body.theme-pulse details.insights,body.theme-pulse .usage-insights,
body.theme-pulse .rollup,body.theme-pulse .blocks,body.theme-pulse .chart-card,
body.theme-pulse .punch,body.theme-pulse .tod,body.theme-pulse .models-table,
body.theme-pulse .cache-breaks,body.theme-pulse .waste-analysis,
body.theme-pulse .cards .card,body.theme-pulse #chart-container,
body.theme-pulse .legend-block,body.theme-pulse .prompts,
body.theme-pulse .timeline-table,body.theme-pulse .chartrail-card,
body.theme-pulse .drawer,body.theme-pulse #weekly-rollup,
body.theme-pulse #session-blocks,body.theme-pulse #hod-chart{background:#15121C;border:1px solid #2A2438;border-radius:14px}
body.theme-pulse .cards .card .val{background:linear-gradient(90deg,#FFB86B,#C084FC 60%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;font-weight:700}
body.theme-pulse .cards .card.green .val{background:none;-webkit-text-fill-color:initial;color:#5EE2C6}
body.theme-pulse .cards .card.amber .val{background:none;-webkit-text-fill-color:initial;color:#FFB86B}
body.theme-pulse th{background:#110F18;border-bottom:1px solid #2A2438;color:#9E9AAE}
body.theme-pulse td{border-bottom:1px solid #1D1928}
body.theme-pulse tr.session-header td{background:#1D1928;color:#C084FC;border-top:1px solid #2A2438}
body.theme-pulse tr.subtotal td{background:#15121C;border-top:1px solid #2A2438}

/* =========================================================================
   Responsive
   ========================================================================= */
@media (max-width:1200px){
  .kpi-grid{grid-template-columns:repeat(3,1fr)}
}
@media (max-width:780px){
  .shell{padding:20px 16px 40px}
  .kpi-grid{grid-template-columns:repeat(2,1fr)}
  .topbar{flex-wrap:wrap;gap:8px}
  .topbar .nav{margin-left:0}
  .switcher{margin-left:0}
  .drawer{width:100%}
}
@media print{
  .drawer,.drawer-backdrop,.topbar,.switcher{display:none!important}
  .shell{max-width:none;padding:0}
}
</style>"""


def _theme_picker_markup() -> str:
    """4-button theme switcher embedded inside the topbar's <nav> element.

    The four buttons match the four themes in ``_theme_css()``. The active
    class is toggled by ``_theme_bootstrap_body_js()`` on apply.
    """
    return (
        '<div class="switcher" role="tablist" aria-label="Theme variant switcher">'
        '<button data-theme="theme-beacon">Beacon</button>'
        '<button data-theme="theme-console" class="active">Console</button>'
        '<button data-theme="theme-lattice">Lattice</button>'
        '<button data-theme="theme-pulse">Pulse</button>'
        '</div>'
    )


def _theme_bootstrap_head_js() -> str:
    """Pre-paint <head> script: reads URL hash (``#theme=X``), falls back to
    ``localStorage['sm_theme']``, defaults to ``console``. Writes the resolved
    theme onto ``<html data-sm-theme=...>`` so the body-end script can apply
    synchronously without a paint-flash."""
    return (
        '<script>'
        '(function(){try{'
          'var h=(location.hash.match(/theme=([a-z]+)/)||[])[1];'
          'var t=h||(function(){try{return localStorage.getItem("sm_theme");}'
                    'catch(e){return null;}})()||"console";'
          'if(!/^(beacon|console|lattice|pulse)$/.test(t))t="console";'
          'document.documentElement.setAttribute("data-sm-theme",t);'
        '}catch(e){}})();'
        '</script>'
    )


def _theme_bootstrap_body_js() -> str:
    """End-of-body script: applies the theme class to <body>, wires the
    switcher buttons, persists to ``localStorage`` wrapped in try/catch
    (Firefox ``privacy.file_unique_origin=true`` throws ``SecurityError``
    on ``file://``), and rewrites any ``a[data-sm-nav]`` href with the
    current ``#theme=`` so cross-file nav preserves the picked theme.

    Also re-skins accent-color-bearing chart libraries when possible —
    current strategy: reload with the hash preserved. uPlot/Highcharts
    have no cheap post-init accent API so a reload is the simplest
    correct answer, and the hash makes it seamless.
    """
    return (
        '<script>'
        '(function(){'
          'function apply(t,isUserAction){'
            'document.body.className='
              'document.body.className.replace(/\\btheme-\\w+\\b/g,"").trim()'
              '+" theme-"+t;'
            'var btns=document.querySelectorAll(".switcher button");'
            'btns.forEach(function(b){'
              'b.classList.toggle("active",b.dataset.theme==="theme-"+t);'
            '});'
            'try{localStorage.setItem("sm_theme",t);}catch(e){}'
            'var h="theme="+t;'
            'if(location.hash.indexOf("theme=")>=0){'
              'location.hash=location.hash.replace(/theme=[a-z]+/,h);'
            '}else if(location.hash&&location.hash.length>1){'
              'location.hash=location.hash.substring(1)+"&"+h;'
            '}else{'
              'location.hash=h;'
            '}'
            'document.querySelectorAll("a[data-sm-nav]").forEach(function(a){'
              'a.href=a.href.split("#")[0]+"#"+h;'
            '});'
            'if(isUserAction&&window.SM_RESKIN_CHARTS){'
              'try{window.SM_RESKIN_CHARTS();}catch(e){}'
            '}'
          '}'
          'var init=document.documentElement.getAttribute("data-sm-theme")||"console";'
          'apply(init,false);'
          'document.querySelectorAll(".switcher button").forEach(function(b){'
            'b.addEventListener("click",function(){'
              'apply(b.dataset.theme.replace("theme-",""),true);'
            '});'
          '});'
        '})();'
        '</script>'
    )


# Phase E — interactive overlay (Cmd/Ctrl+K palette, / find bar, J/K section
# navigation, ? help, sticky chip nav). The named sections (those carrying an
# ``id`` attribute) in DOCUMENT order — this list is the source of truth for the
# chip nav band built in ``render_html``. Order matters for byte-stability: it
# must match the order the sections appear in the rendered body f-string. The
# palette and J/K navigation cover *all* sections (named + anonymous) via the
# live ``.section-title h2`` text scan in ``_overlay_js``; only these named
# sections become hash-addressable chips.
_OVERLAY_NAMED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("session-health-section", "Health"),
    ("session-behavior-section", "Behavior"),
    ("cache-efficiency-section", "Cache"),
    ("velocity-section", "Velocity"),
    ("window-ribbon-section", "Windows"),
    ("weekly-rollup-section", "Weekly"),
    ("session-blocks-section", "Blocks"),
    ("session-duration-section", "Duration"),
    ("hod-section", "Hour of day"),
    ("cost-treemap-section", "Cost / session"),
    ("cost-over-time-section", "Cost / time"),
    ("pricing-advisory-section", "Pricing"),
)


def _stamp_sections_and_build_chips(body_html: str) -> tuple[str, str]:
    """Stamp ``data-sm-section`` onto each named section present in ``body_html``
    and build the sticky chip nav band.

    For every ``(id, label)`` in :data:`_OVERLAY_NAMED_SECTIONS` whose
    ``id="<id>"`` literal appears in the assembled body, rewrite that single
    occurrence to ``id="<id>" data-sm-section="<id>"`` so the overlay JS can
    map a chip / hash to the section element. The ``id`` values are ASCII slugs
    that occur exactly once, so a bounded ``replace(.., 1)`` is unambiguous and
    deterministic (no regex, no float folds, no dict iteration).

    Returns ``(stamped_body, chip_nav_html)``. The chip nav is emitted only
    when **3 or more** named sections are present (the resolved threshold); for
    fewer it returns ``""`` so sparse variants (e.g. ``detail``) stay clean.
    """
    present: list[tuple[str, str]] = []
    for sid, label in _OVERLAY_NAMED_SECTIONS:
        needle = f'id="{sid}"'
        if needle in body_html:
            body_html = body_html.replace(
                needle, f'{needle} data-sm-section="{sid}"', 1)
            present.append((sid, label))
    if len(present) < 3:
        return body_html, ""
    chips = "".join(
        f'<button class="sm-chip" type="button" data-target="{sid}" '
        f'aria-pressed="false">{html_mod.escape(label)}</button>'
        for sid, label in present
    )
    chip_nav = (
        '<nav id="sm-chip-nav" aria-label="Jump to section">' + chips + '</nav>'
    )
    return body_html, chip_nav


def _overlay_css() -> str:
    """Overlay stylesheet (command palette / find bar / help / chip nav).

    Uses ONLY existing theme custom-properties (``--bg``/``--surface``/
    ``--surface-deep``/``--border``/``--border-dim``/``--fg``/``--fg-dim``/
    ``--accent``/``--accent-soft``/``--hover``/``--backdrop``) so the four
    ``body.theme-*`` blocks restyle the overlay for free — the across-theme
    check passes without any per-theme override. Positioned above the drawer
    (``z-index:1000``); the overlay layers use ``1099``/``1100``. Raw string so
    literal CSS braces need no escaping.
    """
    return r"""<style>
/* Phase E — interactive overlay (theme-var only; no hardcoded colours) */
#sm-ovl-backdrop{position:fixed;inset:0;background:var(--backdrop,rgba(0,0,0,.6));z-index:1099;display:none}
#sm-ovl-backdrop.on{display:block}
#sm-palette{position:fixed;top:13vh;left:50%;transform:translateX(-50%);width:min(560px,92vw);background:var(--surface);border:1px solid var(--border);border-radius:14px;z-index:1100;display:none;flex-direction:column;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.5)}
#sm-palette.on{display:flex}
.sm-palette-input{width:100%;padding:15px 18px;font-size:15px;background:var(--surface-deep);color:var(--fg);border:0;border-bottom:1px solid var(--border);outline:none}
.sm-palette-input::placeholder{color:var(--fg-dim)}
.sm-palette-list{list-style:none;margin:0;padding:6px;max-height:52vh;overflow:auto}
.sm-palette-item{padding:9px 12px;border-radius:8px;cursor:pointer;color:var(--fg);display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:13px}
.sm-palette-item .sm-pi-kind{color:var(--fg-dim);font-family:'JetBrains Mono',ui-monospace,monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase}
.sm-palette-item.selected,.sm-palette-item:hover{background:var(--hover);outline:1px solid var(--accent-soft)}
.sm-palette-empty{padding:14px 16px;color:var(--fg-dim);font-size:12px}
#sm-findbar{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);width:min(520px,92vw);background:var(--surface);border:1px solid var(--border);border-radius:12px;z-index:1100;display:none;align-items:center;gap:8px;padding:8px 10px;box-shadow:0 16px 40px rgba(0,0,0,.45)}
#sm-findbar.on{display:flex}
.sm-find-input{flex:1;padding:8px 10px;font-size:13px;background:var(--surface-deep);color:var(--fg);border:1px solid var(--border);border-radius:8px;outline:none}
.sm-find-input::placeholder{color:var(--fg-dim)}
.sm-find-count{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:11px;color:var(--fg-dim);min-width:70px;text-align:center}
.sm-find-btn{padding:6px 10px;border-radius:8px;color:var(--fg);border:1px solid var(--border);background:var(--surface-deep);cursor:pointer}
.sm-find-btn:hover{background:var(--hover);border-color:var(--accent-soft)}
mark.sm-hit{background:var(--accent-soft);color:var(--bg);border-radius:2px}
mark.sm-hit.sm-hit-cur{background:var(--accent);outline:2px solid var(--accent)}
#sm-help{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:min(440px,92vw);background:var(--surface);border:1px solid var(--border);border-radius:14px;z-index:1100;display:none;padding:22px 24px;box-shadow:0 24px 60px rgba(0,0,0,.5)}
#sm-help.on{display:block}
.sm-help-close{position:absolute;top:10px;right:12px;width:28px;height:28px;border-radius:8px;color:var(--fg-dim);font-size:18px;line-height:1;border:1px solid var(--border);background:var(--surface-deep);cursor:pointer}
.sm-help-close:hover{color:var(--fg);background:var(--hover);border-color:var(--accent-soft)}
#sm-help h3{margin:0 0 14px;font-family:'Inter Tight','Inter',sans-serif;font-size:16px;color:var(--fg)}
.sm-help-table{width:100%;border-collapse:collapse;font-size:13px;color:var(--fg)}
.sm-help-table td{padding:6px 4px;border-bottom:1px solid var(--border-dim)}
.sm-help-table td.k{white-space:nowrap;width:46%}
.sm-help-table kbd{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:11px;background:var(--surface-deep);border:1px solid var(--border);border-radius:5px;padding:2px 6px;color:var(--fg-dim)}
#sm-chip-nav{position:sticky;top:0;z-index:35;display:flex;gap:8px;overflow-x:auto;padding:10px 24px;scrollbar-width:thin;background:var(--bg);border-bottom:1px solid var(--border-dim)}
.sm-chip{flex:0 0 auto;padding:5px 12px;border-radius:999px;border:1px solid var(--border);background:var(--surface);color:var(--fg-dim);font-family:'JetBrains Mono',ui-monospace,monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap;cursor:pointer;transition:all .15s ease}
.sm-chip:hover{color:var(--fg);border-color:var(--accent-soft)}
.sm-chip.sm-chip-active{color:var(--fg);background:var(--hover);border-color:var(--accent)}
</style>"""


def _overlay_js() -> str:
    """Overlay behaviour as a single self-contained IIFE ``<script>``.

    DETERMINISTIC BY CONSTRUCTION: a static raw string — no f-string
    interpolation, no ``json.dumps``, no timestamps, no dict/set iteration. The
    ``test_overlay_js_is_deterministic`` guard asserts two calls return
    byte-identical strings; never inject runtime data here.

    Subsystems (all keyboard-driven, all reading section labels from the live
    DOM so they work on every page that includes this script):
      * Command palette (Cmd/Ctrl+K) — fuzzy-jump to any section by h2 text.
      * Find bar (/) — TreeWalker text search with ``<mark>`` highlighting.
      * Section navigation (J / ] forward, K / [ back).
      * Help overlay (?).
      * Chip nav sync (clicking / hashchange highlights the active chip).
    Focus is restored to the pre-open element on close; palette and help trap
    Tab focus. ``/``, ``j``/``k`` and ``?`` are suppressed while a text field is
    focused (only Escape stays global), so typing in the palette/find inputs is
    never hijacked.
    """
    return r"""<script>
(function(){
  'use strict';
  if(window.__smOverlayInit)return; window.__smOverlayInit=true;
  var D=document;
  function ready(fn){if(D.readyState!=='loading'){fn();}else{D.addEventListener('DOMContentLoaded',fn);}}
  function isEditable(el){if(!el)return false;var t=el.tagName;return t==='INPUT'||t==='TEXTAREA'||t==='SELECT'||el.isContentEditable;}
  function preserveTheme(){var m=location.hash.match(/theme=[a-z]+/);return m?m[0]:'';}
  function setHash(id){var th=preserveTheme();try{location.hash=id+(th?'&'+th:'');}catch(e){}}
  function focusables(c){return [].slice.call(c.querySelectorAll('input,button,[tabindex]')).filter(function(e){return !e.disabled&&e.offsetParent!==null;});}
  function trap(c,ev){if(ev.key!=='Tab')return;var f=focusables(c);if(!f.length)return;var first=f[0],last=f[f.length-1];if(ev.shiftKey&&D.activeElement===first){ev.preventDefault();last.focus();}else if(!ev.shiftKey&&D.activeElement===last){ev.preventDefault();first.focus();}}

  ready(function(){
    // ---- section registry (source of truth for palette + J/K nav) ----
    var heads=[].slice.call(D.querySelectorAll('.section-title h2'));
    var sections=heads.map(function(h){
      var sec=h.closest?h.closest('.section'):null;
      return {el:sec||h,label:(h.textContent||'').trim(),id:sec?sec.getAttribute('data-sm-section'):null};
    }).filter(function(s){return s.label;});
    var curIdx=-1,lastFocused=null;

    // ---- build overlay DOM (runtime, keeps the static HTML minimal) ----
    var backdrop=D.createElement('div');backdrop.id='sm-ovl-backdrop';
    var palette=D.createElement('div');palette.id='sm-palette';
    palette.setAttribute('role','dialog');palette.setAttribute('aria-modal','true');palette.setAttribute('aria-label','Jump to section');
    var pInput=D.createElement('input');pInput.className='sm-palette-input';pInput.type='text';
    pInput.setAttribute('placeholder','Jump to section…');pInput.setAttribute('aria-label','Jump to section');
    pInput.setAttribute('role','combobox');pInput.setAttribute('autocomplete','off');pInput.setAttribute('aria-expanded','false');pInput.name='sm-palette-q';
    pInput.setAttribute('aria-controls','sm-palette-list');pInput.setAttribute('aria-haspopup','listbox');
    var pList=D.createElement('ul');pList.className='sm-palette-list';pList.id='sm-palette-list';pList.setAttribute('role','listbox');
    palette.appendChild(pInput);palette.appendChild(pList);
    var findbar=D.createElement('div');findbar.id='sm-findbar';findbar.setAttribute('role','search');
    var fInput=D.createElement('input');fInput.className='sm-find-input';fInput.type='text';
    fInput.setAttribute('placeholder','Find in page…');fInput.setAttribute('aria-label','Find in page');fInput.setAttribute('autocomplete','off');fInput.name='sm-find-q';
    var fCount=D.createElement('span');fCount.className='sm-find-count';fCount.setAttribute('aria-live','polite');fCount.textContent='0 / 0';
    var fPrev=D.createElement('button');fPrev.className='sm-find-btn';fPrev.type='button';fPrev.textContent='↑';fPrev.setAttribute('aria-label','Previous match');
    var fNext=D.createElement('button');fNext.className='sm-find-btn';fNext.type='button';fNext.textContent='↓';fNext.setAttribute('aria-label','Next match');
    findbar.appendChild(fInput);findbar.appendChild(fCount);findbar.appendChild(fPrev);findbar.appendChild(fNext);
    var help=D.createElement('div');help.id='sm-help';help.setAttribute('role','dialog');help.setAttribute('aria-modal','true');help.setAttribute('aria-label','Keyboard shortcuts');
    help.innerHTML='<button class="sm-help-close" type="button" aria-label="Close help">&times;</button>'+
      '<h3>Keyboard shortcuts</h3><table class="sm-help-table"><tbody>'+
      '<tr><td class="k"><kbd>Cmd</kbd>/<kbd>Ctrl</kbd>+<kbd>K</kbd></td><td>Command palette</td></tr>'+
      '<tr><td class="k"><kbd>/</kbd></td><td>Find in page</td></tr>'+
      '<tr><td class="k"><kbd>J</kbd> / <kbd>]</kbd></td><td>Next section</td></tr>'+
      '<tr><td class="k"><kbd>K</kbd> / <kbd>[</kbd></td><td>Previous section</td></tr>'+
      '<tr><td class="k"><kbd>?</kbd></td><td>This help</td></tr>'+
      '<tr><td class="k"><kbd>Esc</kbd></td><td>Close</td></tr></tbody></table>';
    D.body.appendChild(backdrop);D.body.appendChild(palette);D.body.appendChild(findbar);D.body.appendChild(help);

    function modalOpen(){return palette.classList.contains('on')||help.classList.contains('on');}
    function anyOpen(){return modalOpen()||findbar.classList.contains('on');}
    function showBackdrop(on){backdrop.classList.toggle('on',on);}
    function rememberFocus(){lastFocused=D.activeElement;}
    function restoreFocus(){if(lastFocused&&typeof lastFocused.focus==='function'){lastFocused.focus();}lastFocused=null;}

    function scrollToSection(s){if(!s||!s.el)return;s.el.scrollIntoView({behavior:'smooth',block:'start'});if(s.id)setHash(s.id);}
    function nav(dir){if(!sections.length)return;curIdx+=dir;if(curIdx<0)curIdx=0;if(curIdx>=sections.length)curIdx=sections.length-1;scrollToSection(sections[curIdx]);}

    // ---- palette ----
    function buildList(q){
      pList.innerHTML='';var ql=(q||'').toLowerCase();
      var matched=sections.filter(function(s){return s.label.toLowerCase().indexOf(ql)>=0;});
      matched.forEach(function(s,i){
        var li=D.createElement('li');li.className='sm-palette-item';li.setAttribute('role','option');li.id='sm-pi-'+i;
        var lbl=D.createElement('span');lbl.textContent=s.label;
        var kind=D.createElement('span');kind.className='sm-pi-kind';kind.textContent='section';
        li.appendChild(lbl);li.appendChild(kind);li.__section=s;
        li.addEventListener('click',function(){activate(li);});
        pList.appendChild(li);
      });
      if(!matched.length){var em=D.createElement('li');em.className='sm-palette-empty';em.textContent='No matching section';pList.appendChild(em);}
      var act=D.createElement('li');act.className='sm-palette-item';act.setAttribute('role','option');act.id='sm-pi-find';
      var al=D.createElement('span');al.textContent='Find in page…';
      var ak=D.createElement('span');ak.className='sm-pi-kind';ak.textContent='/';
      act.appendChild(al);act.appendChild(ak);act.__action='find';
      act.addEventListener('click',function(){activate(act);});
      pList.appendChild(act);
      select(0);
    }
    function items(){return [].slice.call(pList.querySelectorAll('.sm-palette-item'));}
    function select(i){var it=items();if(!it.length)return;if(i<0)i=0;if(i>=it.length)i=it.length-1;
      it.forEach(function(e,j){e.classList.toggle('selected',j===i);});var sel=it[i];
      pInput.setAttribute('aria-activedescendant',sel&&sel.id?sel.id:'');
      if(sel)sel.scrollIntoView({block:'nearest'});}
    function selectedIdx(){var it=items();for(var i=0;i<it.length;i++){if(it[i].classList.contains('selected'))return i;}return -1;}
    function activate(li){
      if(li.__action==='find'){closePalette();openFind();return;}
      var s=li.__section;if(s){closePalette();curIdx=sections.indexOf(s);scrollToSection(s);if(s.id)setActiveChip(s.id);}
    }
    function openPalette(){rememberFocus();showBackdrop(true);palette.classList.add('on');pInput.setAttribute('aria-expanded','true');pInput.value='';buildList('');pInput.focus();}
    function closePalette(){palette.classList.remove('on');pInput.setAttribute('aria-expanded','false');if(!modalOpen())showBackdrop(false);restoreFocus();}
    function togglePalette(){palette.classList.contains('on')?closePalette():openPalette();}
    pInput.addEventListener('input',function(){buildList(pInput.value);});
    pInput.addEventListener('keydown',function(ev){
      if(ev.key==='ArrowDown'){ev.preventDefault();select(selectedIdx()+1);}
      else if(ev.key==='ArrowUp'){ev.preventDefault();select(selectedIdx()-1);}
      else if(ev.key==='Enter'){ev.preventDefault();var it=items(),i=selectedIdx();if(i>=0&&it[i])activate(it[i]);}
    });
    palette.addEventListener('keydown',function(ev){trap(palette,ev);});

    // ---- find bar ----
    var hits=[],curHit=-1;
    function clearMarks(){
      var ms=D.querySelectorAll('mark.sm-hit');
      [].forEach.call(ms,function(m){var p=m.parentNode;if(!p)return;p.replaceChild(D.createTextNode(m.textContent),m);p.normalize();});
      hits=[];curHit=-1;
    }
    function textNodes(){
      var skip={SCRIPT:1,STYLE:1,NOSCRIPT:1,MARK:1};
      var w=D.createTreeWalker(D.body,NodeFilter.SHOW_TEXT,{acceptNode:function(n){
        if(!n.nodeValue||!n.nodeValue.trim())return NodeFilter.FILTER_REJECT;
        var p=n.parentNode;
        while(p&&p!==D.body){
          if(skip[p.tagName])return NodeFilter.FILTER_REJECT;
          if(p.id&&(p.id==='turn-data'||p.id==='chartrail-data'||p.id==='costail-data'||p.id==='tod-epoch-secs'||p.id.indexOf('sm-')===0))return NodeFilter.FILTER_REJECT;
          p=p.parentNode;
        }
        return NodeFilter.FILTER_ACCEPT;
      }});
      var out=[],n;while((n=w.nextNode()))out.push(n);return out;
    }
    function updateCount(){fCount.textContent=(hits.length?(curHit+1):0)+' / '+hits.length;}
    function focusHit(){
      hits.forEach(function(m,i){m.classList.toggle('sm-hit-cur',i===curHit);});
      if(curHit>=0&&hits[curHit])hits[curHit].scrollIntoView({behavior:'smooth',block:'center'});
      updateCount();
    }
    function runFind(q){
      clearMarks();
      if(!q){updateCount();return;}
      var ql=q.toLowerCase(),n=q.length;
      textNodes().forEach(function(node){
        var text=node.nodeValue,lower=text.toLowerCase(),idx=lower.indexOf(ql);
        if(idx<0)return;
        var frag=D.createDocumentFragment(),last=0;
        while(idx>=0){
          if(idx>last)frag.appendChild(D.createTextNode(text.slice(last,idx)));
          var mk=D.createElement('mark');mk.className='sm-hit';mk.textContent=text.slice(idx,idx+n);
          frag.appendChild(mk);hits.push(mk);last=idx+n;idx=lower.indexOf(ql,last);
        }
        if(last<text.length)frag.appendChild(D.createTextNode(text.slice(last)));
        if(node.parentNode)node.parentNode.replaceChild(frag,node);
      });
      curHit=hits.length?0:-1;focusHit();
    }
    function stepHit(dir){if(!hits.length)return;curHit=(curHit+dir+hits.length)%hits.length;focusHit();}
    function openFind(){rememberFocus();findbar.classList.add('on');fInput.value='';runFind('');fInput.focus();}
    function closeFind(){findbar.classList.remove('on');clearMarks();updateCount();restoreFocus();}
    fInput.addEventListener('input',function(){runFind(fInput.value);});
    fInput.addEventListener('keydown',function(ev){if(ev.key==='Enter'){ev.preventDefault();stepHit(ev.shiftKey?-1:1);}});
    fPrev.addEventListener('click',function(){stepHit(-1);});
    fNext.addEventListener('click',function(){stepHit(1);});

    // ---- help ----
    function openHelp(){rememberFocus();showBackdrop(true);help.classList.add('on');var cb=help.querySelector('.sm-help-close');if(cb)cb.focus();}
    function closeHelp(){help.classList.remove('on');if(!modalOpen())showBackdrop(false);restoreFocus();}
    function toggleHelp(){help.classList.contains('on')?closeHelp():openHelp();}
    help.addEventListener('keydown',function(ev){trap(help,ev);});
    var _hClose=help.querySelector('.sm-help-close');if(_hClose)_hClose.addEventListener('click',closeHelp);

    function closeAll(){if(palette.classList.contains('on'))closePalette();if(help.classList.contains('on'))closeHelp();if(findbar.classList.contains('on'))closeFind();}
    backdrop.addEventListener('click',closeAll);

    // ---- chip nav sync ----
    var chips=[].slice.call(D.querySelectorAll('#sm-chip-nav .sm-chip'));
    function setActiveChip(id){chips.forEach(function(c){var on=c.dataset.target===id;c.classList.toggle('sm-chip-active',on);c.setAttribute('aria-pressed',on?'true':'false');});}
    chips.forEach(function(c){c.addEventListener('click',function(){
      var id=c.dataset.target,s=sections.filter(function(x){return x.id===id;})[0];
      if(s){curIdx=sections.indexOf(s);scrollToSection(s);}setActiveChip(id);
    });});
    function syncFromHash(){var raw=location.hash.replace(/^#/,'').split('&')[0];if(raw)setActiveChip(raw);}
    window.addEventListener('hashchange',syncFromHash);syncFromHash();

    // ---- global key router ----
    window.addEventListener('keydown',function(ev){
      if((ev.metaKey||ev.ctrlKey)&&(ev.key==='k'||ev.key==='K')){ev.preventDefault();togglePalette();return;}
      if(ev.key==='Escape'){closeAll();return;}
      if(isEditable(D.activeElement))return;
      if(ev.key==='?'){ev.preventDefault();toggleHelp();return;}
      if(anyOpen())return;
      if(ev.key==='/'){ev.preventDefault();openFind();return;}
      if(ev.key==='j'||ev.key==='J'||ev.key===']'){ev.preventDefault();nav(1);return;}
      if(ev.key==='k'||ev.key==='K'||ev.key==='['){ev.preventDefault();nav(-1);return;}
    });
  });
})();
</script>"""


def _build_chartrail_section_html(chartrail_data: list) -> str:
    """Return the chartrail section HTML for a given list of turn dicts.

    Returns an empty string if ``chartrail_data`` is empty.
    """
    if not chartrail_data:
        return ""
    rail_json = json.dumps(chartrail_data, separators=(",", ":"),
                            default=str).replace("</", "<\\/")
    n_turns = len(chartrail_data)
    return (
        '<section class="section">\n'
        '<div class="section-title"><h2>Token usage over time</h2>'
        '<span class="hint">scroll horizontally &middot; click a turn '
        'to drill in &middot; \u2190 \u2192</span></div>\n'
        '<div class="chartrail-card">\n'
        '  <div class="chartrail-legend">\n'
        '    <span><span class="sw i"></span>Input (new)</span>\n'
        '    <span><span class="sw o"></span>Output</span>\n'
        '    <span><span class="sw cw"></span>Cache write</span>\n'
        '    <span><span class="sw cr"></span>Cache read</span>\n'
        '    <span><span class="sw cost"></span>Cost $</span>\n'
        '  </div>\n'
        '  <div class="chartrail-wrap">\n'
        '    <div class="chartrail-yaxis" id="chartrail-yaxis"></div>\n'
        '    <div class="chartrail-scroll" id="chartrail-scroll" '
        'tabindex="0">\n'
        '      <div class="chartrail-inner" id="chartrail-inner">'
        '</div>\n'
        '    </div>\n'
        '    <button class="rail-chev left" id="rail-prev" '
        'aria-label="Scroll turns left">\u2039</button>\n'
        '    <button class="rail-chev right" id="rail-next" '
        'aria-label="Scroll turns right">\u203a</button>\n'
        '  </div>\n'
        '  <div class="rail-indicator">\n'
        f'    <span><span id="rail-counter">01</span> / {n_turns}</span>\n'
        '    <div class="rail-progress">'
        '<div class="rail-progress-fill" id="rail-progress-fill">'
        '</div></div>\n'
        '    <span>scroll or use \u2190 \u2192</span>\n'
        '  </div>\n'
        '</div>\n'
        '<script type="application/json" id="chartrail-data">'
        f'{rail_json}</script>\n'
        '</section>'
    )


def _chartrail_script() -> str:
    """Return the full chartrail interaction JS string."""
    return """<script>
(function () {
  var root = document.getElementById('chartrail-data');
  if (!root) return;
  var rows; try { rows = JSON.parse(root.textContent); } catch (e) { return; }
  var scroll = document.getElementById('chartrail-scroll');
  var inner  = document.getElementById('chartrail-inner');
  var yaxis  = document.getElementById('chartrail-yaxis');
  var counter= document.getElementById('rail-counter');
  var progress = document.getElementById('rail-progress-fill');
  if (!scroll || !inner || !yaxis) return;

  // Max tokens = inp + out + cr + cw per turn
  var maxTok = 0;
  rows.forEach(function (t) {
    var tot = (t.inp||0) + (t.out||0) + (t.cr||0) + (t.cw||0);
    if (tot > maxTok) maxTok = tot;
  });
  if (!maxTok) maxTok = 1;

  // Y-axis ticks: 5 bands 0..max
  var yHtml = '';
  for (var i = 0; i <= 4; i++) {
    var v = (maxTok / 4) * i;
    var label = v >= 1e6 ? (v/1e6).toFixed(1) + 'M'
              : v >= 1e3 ? Math.round(v/1e3) + 'k'
              : Math.round(v);
    var pct = 100 - (i/4) * 100;
    yHtml += '<span class="tick" style="top:' + pct + '%">' + label + '</span>';
  }
  yaxis.innerHTML = yHtml;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  var parts = [];
  rows.forEach(function (t, i) {
    if (t.resm) {
      var label = t.term ? 'Session exited' : 'Session resumed';
      parts.push('<div class="tcol resume' +
        (t.sbrk && i > 0 ? ' session-break' : '') +
        '" title="' + esc(label + ' at ' + (t.ts || '')) + '">' +
        (t.sbrk && i > 0
          ? '<div class="tc-seslabel">' + esc(t.slbl || '') + '</div>'
          : '') +
        '<div class="tc-bar" aria-hidden="true"></div>' +
        '<div class="tc-foot"><span class="tc-n">' +
        String(t.n).padStart(2, '0') + '</span>' +
        '<span class="tc-time">' + esc(t.time || '') + '</span>' +
        '<span class="tc-cost" style="opacity:.5">&mdash;</span></div>' +
        '</div>');
      return;
    }
    var pctI  = (t.inp /maxTok) * 100;
    var pctO  = (t.out /maxTok) * 100;
    var pctCw = (t.cw  /maxTok) * 100;
    var pctCr = (t.cr  /maxTok) * 100;
    var tot = (t.inp||0) + (t.out||0) + (t.cr||0) + (t.cw||0);
    var title = 'Turn ' + t.n + ' \u00b7 ' + (t.time || '') + ' \u00b7 ' +
                (t.mdl || '') + ' \u00b7 tokens ' + tot.toLocaleString() +
                ' \u00b7 $' + (t.cost || 0).toFixed(4);
    parts.push('<div class="tcol' +
      (t.sbrk && i > 0 ? ' session-break' : '') +
      '" data-turn="' + esc(t.key) + '" tabindex="0" title="' + esc(title) + '">' +
      (t.sbrk && i > 0
        ? '<div class="tc-seslabel">' + esc(t.slbl || '') + '</div>'
        : '') +
      '<div class="tc-bar" aria-hidden="true">' +
      '<span class="seg i"  style="height:' + pctI.toFixed(2) + '%"></span>' +
      '<span class="seg o"  style="height:' + pctO.toFixed(2) + '%"></span>' +
      '<span class="seg cw" style="height:' + pctCw.toFixed(2) + '%"></span>' +
      '<span class="seg cr" style="height:' + pctCr.toFixed(2) + '%"></span>' +
      '</div>' +
      '<div class="tc-foot">' +
      '<span class="tc-n">' + String(t.n).padStart(2, '0') + '</span>' +
      '<span class="tc-time">' + esc(t.time || '') + '</span>' +
      '<span class="tc-cost">$' + (t.cost || 0).toFixed(3) + '</span>' +
      '</div></div>');
  });
  inner.innerHTML = parts.join('');

  // Click → open drawer via shared opener (from drawer script).
  inner.addEventListener('click', function (ev) {
    var col = ev.target && ev.target.closest ? ev.target.closest('.tcol') : null;
    if (!col) return;
    var key = col.getAttribute('data-turn');
    if (key && typeof window.smOpenDrawer === 'function') window.smOpenDrawer(key);
  });
  inner.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' || ev.key === ' ') {
      var el = document.activeElement;
      if (el && el.classList && el.classList.contains('tcol')) {
        var key = el.getAttribute('data-turn');
        if (key && typeof window.smOpenDrawer === 'function') {
          ev.preventDefault();
          window.smOpenDrawer(key);
        }
      }
    }
  });

  // Chevrons scroll-by a ~10-col chunk (320px is a sensible default).
  var lchev = document.querySelector('.rail-chev.left');
  var rchev = document.querySelector('.rail-chev.right');
  if (lchev) lchev.addEventListener('click', function () {
    scroll.scrollBy({left: -320, behavior: 'smooth'});
  });
  if (rchev) rchev.addEventListener('click', function () {
    scroll.scrollBy({left: 320, behavior: 'smooth'});
  });

  // Keyboard \u2190/\u2192 scroll the rail; Enter/Space opens drawer via click handler above.
  scroll.addEventListener('keydown', function (ev) {
    if (ev.key === 'ArrowRight') {
      ev.preventDefault();
      scroll.scrollBy({left: 160, behavior: 'smooth'});
    } else if (ev.key === 'ArrowLeft') {
      ev.preventDefault();
      scroll.scrollBy({left: -160, behavior: 'smooth'});
    }
  });

  // Wheel-to-horizontal: translate vertical wheel to horizontal scroll so users
  // can navigate without a horizontal trackpad gesture.
  scroll.addEventListener('wheel', function (ev) {
    if (Math.abs(ev.deltaY) > Math.abs(ev.deltaX)) {
      scroll.scrollLeft += ev.deltaY;
      ev.preventDefault();
    }
  }, {passive: false});

  // Update counter + progress bar as user scrolls.
  function updateIndicator() {
    var max = scroll.scrollWidth - scroll.clientWidth;
    var t = max > 0 ? scroll.scrollLeft / max : 0;
    if (progress) progress.style.width = Math.max(2, t * 100) + '%';
    var firstCol = scroll.querySelector('.tcol');
    if (firstCol && counter) {
      var cw = firstCol.getBoundingClientRect().width + 4;
      var idx = Math.min(rows.length - 1,
        Math.max(0, Math.round(scroll.scrollLeft / Math.max(1, cw))));
      counter.textContent = String(rows[idx].n).padStart(2, '0');
    }
  }
  scroll.addEventListener('scroll', updateIndicator);
  updateIndicator();
})();
</script>"""


def _build_daily_cost_rail_html(daily_data: list) -> str:
    """Return a horizontally-scrollable daily-cost rail for the instance page.

    Each column is one calendar day; bar height is proportional to cost.
    Reuses ``.chartrail-card`` CSS layout; DOM IDs use the ``costail-``
    prefix so the element names don't clash with the per-session chartrail.

    Returns ``""`` if ``daily_data`` is empty.
    """
    if not daily_data:
        return ""
    rail_json = json.dumps(
        [{"n": i, "date": d.get("date", ""), "cost": float(d.get("cost", 0.0))}
         for i, d in enumerate(daily_data, 1)],
        separators=(",", ":"),
    ).replace("</", "<\\/")
    n_days = len(daily_data)
    return (
        '<section class="section">\n'
        '<div class="section-title"><h2>Daily cost timeline</h2>'
        '<span class="hint">one bar per calendar day &middot; '
        'scroll horizontally &middot; \u2190 \u2192</span></div>\n'
        '<div class="chartrail-card">\n'
        '  <div class="chartrail-wrap">\n'
        '    <div class="chartrail-yaxis" id="costail-yaxis"></div>\n'
        '    <div class="chartrail-scroll" id="costail-scroll" tabindex="0">\n'
        '      <div class="chartrail-inner" id="costail-inner"></div>\n'
        '    </div>\n'
        '    <button class="rail-chev left"  id="costail-prev" '
        'aria-label="Scroll days left">\u2039</button>\n'
        '    <button class="rail-chev right" id="costail-next" '
        'aria-label="Scroll days right">\u203a</button>\n'
        '  </div>\n'
        '  <div class="rail-indicator">\n'
        f'    <span><span id="costail-counter">01</span> / {n_days} days</span>\n'
        '    <div class="rail-progress">'
        '<div class="rail-progress-fill" id="costail-progress"></div></div>\n'
        '    <span>scroll or use \u2190 \u2192</span>\n'
        '  </div>\n'
        '</div>\n'
        '<script type="application/json" id="costail-data">'
        f'{rail_json}</script>\n'
        '</section>'
    )


def _daily_cost_rail_script() -> str:
    """Interaction JS for the daily-cost rail (costail).

    Renders one bar per calendar day whose height is proportional to cost.
    Y-axis ticks show dollar amounts.  Wires chevrons, keyboard, and wheel
    scroll — identical UX to the per-session chartrail.
    """
    return """<script>
(function () {
  var root = document.getElementById('costail-data');
  if (!root) return;
  var rows; try { rows = JSON.parse(root.textContent); } catch (e) { return; }
  var scroll   = document.getElementById('costail-scroll');
  var inner    = document.getElementById('costail-inner');
  var yaxis    = document.getElementById('costail-yaxis');
  var counter  = document.getElementById('costail-counter');
  var progress = document.getElementById('costail-progress');
  if (!scroll || !inner || !yaxis) return;

  var maxCost = 0;
  rows.forEach(function (r) { if (r.cost > maxCost) maxCost = r.cost; });
  if (!maxCost) maxCost = 1;

  // Y-axis: 5 dollar-amount ticks
  var yHtml = '';
  for (var i = 0; i <= 4; i++) {
    var v   = (maxCost / 4) * i;
    var lbl = v >= 100 ? '$' + Math.round(v)
            : v >= 1   ? '$' + v.toFixed(1)
            :            '$' + v.toFixed(2);
    var pct = 100 - (i / 4) * 100;
    yHtml += '<span class="tick" style="top:' + pct + '%">' + lbl + '</span>';
  }
  yaxis.innerHTML = yHtml;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  var parts = [];
  rows.forEach(function (r, i) {
    var pct   = (r.cost / maxCost) * 100;
    var label = esc(r.date) + ' \u00b7 $' + r.cost.toFixed(2);
    // Shorten date for column label: keep MM-DD portion
    var dateShort = String(r.date).slice(5);   // "YYYY-MM-DD" → "MM-DD"
    parts.push(
      '<div class="tcol" title="' + label + '">' +
      '<div class="tc-bar" aria-hidden="true">' +
      '<span class="seg cost" style="height:' + pct.toFixed(2) + '%"></span>' +
      '</div>' +
      '<div class="tc-foot">' +
      '<span class="tc-n">' + String(r.n).padStart(2,'0') + '</span>' +
      '<span class="tc-time">' + esc(dateShort) + '</span>' +
      '<span class="tc-cost">$' + r.cost.toFixed(2) + '</span>' +
      '</div></div>'
    );
  });
  inner.innerHTML = parts.join('');

  // Chevrons
  var lchev = document.getElementById('costail-prev');
  var rchev = document.getElementById('costail-next');
  if (lchev) lchev.addEventListener('click', function () {
    scroll.scrollBy({left: -320, behavior: 'smooth'});
  });
  if (rchev) rchev.addEventListener('click', function () {
    scroll.scrollBy({left: 320, behavior: 'smooth'});
  });

  // Keyboard ←/→
  scroll.addEventListener('keydown', function (ev) {
    if (ev.key === 'ArrowRight') {
      ev.preventDefault(); scroll.scrollBy({left: 160, behavior: 'smooth'});
    } else if (ev.key === 'ArrowLeft') {
      ev.preventDefault(); scroll.scrollBy({left: -160, behavior: 'smooth'});
    }
  });

  // Vertical wheel → horizontal scroll
  scroll.addEventListener('wheel', function (ev) {
    if (Math.abs(ev.deltaY) > Math.abs(ev.deltaX)) {
      scroll.scrollLeft += ev.deltaY;
      ev.preventDefault();
    }
  }, {passive: false});

  function updateIndicator() {
    var max = scroll.scrollWidth - scroll.clientWidth;
    var t   = max > 0 ? scroll.scrollLeft / max : 0;
    if (progress) progress.style.width = Math.max(2, t * 100) + '%';
    var firstCol = scroll.querySelector('.tcol');
    if (firstCol && counter) {
      var cw  = firstCol.getBoundingClientRect().width + 4;
      var idx = Math.min(rows.length - 1,
        Math.max(0, Math.round(scroll.scrollLeft / Math.max(1, cw))));
      counter.textContent = String(rows[idx].n).padStart(2, '0');
    }
  }
  scroll.addEventListener('scroll', updateIndicator);
  updateIndicator();
})();
</script>"""


def render_html(report: dict, variant: str = "single",
                nav_sibling: str | None = None,
                chart_lib: str = "highcharts",
                idle_gap_minutes: int = 10) -> str:
    """Render the full report as a dark-themed HTML page with interactive charts.

    ``variant`` picks the page layout:
    - ``"single"`` (default): everything in one file. Backward-compatible.
    - ``"dashboard"``: summary cards + insight sections + links to the
      detail page. No chart, no turn-level table, no chart-library JS
      inline (massive size win).
    - ``"detail"``: token-usage chart + timeline table + models pricing
      table. No insight sections.

    ``nav_sibling`` is the relative href of the companion file shown in
    the top nav bar. When ``None`` (single-page mode) the nav bar is omitted.

    ``chart_lib`` selects the chart renderer (see ``_sm().CHART_RENDERERS``).
    Use ``"none"`` to emit the detail page with no chart at all — smallest
    possible output, no JS dependency.
    """
    if report.get("mode") == "instance":
        return _sm()._render_instance_html(report, chart_lib=chart_lib)
    include_insights = variant in ("single", "dashboard", "project")
    include_chart    = variant in ("single", "detail", "project")
    include_hc_chart = variant == "single"   # Highcharts 3D for single only; detail/project use chartrail
    # Escaped at the source: slug derives from a directory path and lands in
    # <title>/<h1> below (parity with the instance renderer, which escapes
    # the same field in _dispatch).
    slug = html_mod.escape(report["slug"])
    totals = report["totals"]
    mode = report["mode"]
    generated = _sm()._fmt_generated_at(report)
    skill_version = report.get("skill_version", "?")
    sessions = report["sessions"]

    # ---- Chart data --------------------------------------------------------
    # Built only when the variant actually renders a chart — saves real work
    # (and, for the dashboard variant, drops the inline library JS bundle).
    # The renderer is selected via ``_sm().CHART_RENDERERS[chart_lib]``; each
    # returns ``(body_html, head_js)`` so the caller can place the JS in
    # ``<head>`` while the container div goes in the body.
    chart_html      = ""
    chart_head_html = ""
    if include_hc_chart:
        if mode == "project":
            all_turns = [t for s in sessions for t in s["turns"]]
        else:
            all_turns = sessions[0]["turns"]
        renderer = _sm().CHART_RENDERERS.get(chart_lib) or _sm()._render_chart_none
        chart_html, chart_head_html = renderer(all_turns)

    # Always resolved for the timeline header (and anywhere else the HTML
    # renders timestamps) — the "detail" variant has no insights block
    # but still needs tz_label for the Timeline table.
    tz_label  = report.get("tz_label", "UTC")
    tz_offset = report.get("tz_offset_hours", 0.0)

    # ---- Insights sections (positioned above charts) ---------------------
    tod_html  = ""
    if include_insights:
        tod_section    = report.get("time_of_day", {})
        # Multi-window comparison ribbon (project scope only — single-
        # session reports cover one window by definition; build_report
        # only stamps ``window_stats`` when mode == 'project'). Renders
        # ahead of the weekly rollup so the trailing-window framing sets
        # context before the per-week breakdown.
        window_html    = _build_window_ribbon_html(report.get("window_stats", []) or [])
        rollup_html    = _build_weekly_rollup_html(report.get("weekly_rollup", {}))
        blocks_html    = _build_session_blocks_html(
            report.get("session_blocks", []),
            report.get("block_summary", {}),
            tz_label, tz_offset,
        )
        duration_html  = _build_session_duration_html(sessions, tz_label, tz_offset)
        hod_html       = _build_hour_of_day_html(tod_section, tz_label, tz_offset,
                                                  peak=report.get("peak"))
        punchcard_html = _build_punchcard_html(tod_section, tz_label, tz_offset)
        heatmap_html   = _build_tod_heatmap_html(tod_section, tz_label, tz_offset)
        # Shared epoch-seconds blob — must precede the three sections that
        # JSON.parse it (their IIFEs run at document parse time).
        tod_html       = (window_html + rollup_html + blocks_html + duration_html
                          + _build_tod_epoch_blob(tod_section)
                          + hod_html + punchcard_html + heatmap_html)
        # Phase F — multi-session & temporal sections (project scope only;
        # the keys are absent at single-session scope so each builder returns
        # "" and the page is unchanged).
        tod_html      += (
            _build_session_shape_histograms_html(report.get("session_shape_histograms") or {})
            + _build_cache_economics_html(report.get("cache_economics") or {})
            + _build_project_concentration_html(report.get("project_concentration") or {})
            + _build_activity_heatmap_html(report.get("activity_heatmap") or {}, tz_label)
            + _build_session_activity_by_hour_html(
                report.get("session_activity_by_hour") or [], tz_label)
        )

    # ---- Table rows --------------------------------------------------------
    show_mode    = _sm()._has_fast(report)
    show_ttl     = _sm()._has_1h_cache(report)
    show_content = _sm()._has_content_blocks(report)
    show_waste   = bool(report.get("waste_analysis")) and include_chart

    # Total columns = #, Time, Model, [Mode], Input, Output, CacheRd, CacheWr,
    #                 [Content], Total, Cost, [Turn Character]
    _full_cols = (10 + (1 if show_mode else 0) + (1 if show_content else 0)
                     + (1 if show_waste else 0))
    # Label cell in subtotal rows spans the non-numeric prefix: #, Time, Model, [Mode]
    _label_span = 4 if show_mode else 3

    def _cwr_cell(tokens: int, tokens_5m: int, tokens_1h: int,
                  ttl: str, bold: bool = False,
                  is_cache_break: bool = False) -> str:
        num = f"{tokens:,}"
        inner = f"<strong>{num}</strong>" if bold else num
        cb_badge = (
            ' <span class="cache-break-tag"'
            ' title="Cache break — high uncached token spend on this turn">&#9889;</span>'
        ) if is_cache_break else ""
        if ttl in ("1h", "mix"):
            cls = "ttl-1h" if ttl == "1h" else "ttl-mix"
            title = f"5m: {tokens_5m:,} · 1h: {tokens_1h:,} tokens"
            badge = f'<span class="badge-ttl {cls}" title="{title}">{ttl}</span>'
            return f'<td class="num" title="{title}">{inner}{badge}{cb_badge}</td>'
        return f'<td class="num">{inner}{cb_badge}</td>'

    def _content_cell(cb: dict) -> str:
        label = _fmt_content_cell(cb)
        title = _fmt_content_title(cb)
        if label == "-":
            return '<td class="content-blocks muted">&ndash;</td>'
        return (f'<td class="content-blocks" title="{html_mod.escape(title)}">'
                f'<span>{label}</span></td>')

    def turn_row(t: dict, session_id: str) -> str:
        # Resume markers replace the normal data row with a full-width divider
        # so users see "session resumed here" inline with the timeline rather
        # than an all-zero row labelled `<synthetic>`. The marker is still
        # counted in the turn index; only the rendering changes.
        if t.get("is_clear_event"):
            ts_fmt = html_mod.escape(t.get("timestamp_fmt", ""))
            clear_divider = (
                f'<tr class="resume-marker-row" data-session="{session_id[:8]}">'
                f'<td class="num resume-marker-idx"></td>'
                f'<td colspan="{_full_cols - 1}" class="resume-marker-cell">'
                f'<span class="resume-marker-pill terminal" '
                f'title="A /clear command was issued before this turn, '
                f'resetting the conversation context. Cache hit rate typically '
                f'drops here due to cold-start cache rebuild.">'
                f'<span class="resume-marker-icon">&#8855;</span>'
                f'<strong>Context cleared</strong>'
                f'<span class="resume-marker-time">before turn {t["index"]}</span>'
                f'</span></td></tr>'
            )
        else:
            clear_divider = ""
        # Q1c item 2: "continued from prior conversation" pill on a session's
        # first turn when it opened on a compaction summary (the boundary lives
        # in a predecessor file). Lightweight + muted — distinct from the
        # in-session compaction divider below. Rendered above the turn row.
        if t.get("is_continued_from_prior"):
            continued_divider = (
                f'<tr class="resume-marker-row" data-session="{session_id[:8]}">'
                f'<td class="num resume-marker-idx"></td>'
                f'<td colspan="{_full_cols - 1}" class="resume-marker-cell">'
                f'<span class="resume-marker-pill continued" '
                f'title="This session opened on a compaction summary — it '
                f'continues a prior conversation whose compact_boundary lives in '
                f'a predecessor JSONL. The first turn rebuilds context from that '
                f'summary.">'
                f'<span class="resume-marker-icon">&#8617;&#65039;</span>'
                f'<strong>Continued from prior conversation</strong>'
                f'</span></td></tr>'
            )
        else:
            continued_divider = ""
        # Q1c item 1: in-session compaction divider before the first turn that
        # followed a compact_boundary. Mirrors clear_divider (prepended row; the
        # real turn stays clickable). Sourced from the deduped boundary set, so
        # one divider per boundary that had a following turn.
        if t.get("is_post_compaction"):
            _trig = t.get("compaction_trigger") or "auto"
            _rec  = t.get("compaction_reclaimed_tokens")
            _rec_str = (f' &middot; {_rec:,} reclaimed'
                        if isinstance(_rec, int) else "")
            compaction_divider = (
                f'<tr class="resume-marker-row" data-session="{session_id[:8]}">'
                f'<td class="num resume-marker-idx"></td>'
                f'<td colspan="{_full_cols - 1}" class="resume-marker-cell">'
                f'<span class="resume-marker-pill compaction" '
                f'title="A context-window compaction (compact_boundary) occurred '
                f'before this turn. The conversation was summarised and older '
                f'messages dropped from context; the next turn rebuilds cache '
                f'from the summary, so cache-read typically dips here.">'
                f'<span class="resume-marker-icon">&#128476;&#65039;</span>'
                f'<strong>Context compacted ({html_mod.escape(str(_trig))})</strong>'
                f'<span class="resume-marker-time">before turn {t["index"]}'
                f'{_rec_str}</span>'
                f'</span></td></tr>'
            )
        else:
            compaction_divider = ""
        if t.get("is_resume_marker"):
            ts_fmt = html_mod.escape(t.get("timestamp_fmt", ""))
            is_terminal = t.get("is_terminal_exit_marker", False)
            # Terminal: this is the most recent /exit with no subsequent work
            # in the JSONL. The user may or may not have resumed yet — the
            # JSONL alone can't tell us. Resume: there is later work in the
            # file, so a return is observable.
            if is_terminal:
                pill_cls   = "resume-marker-pill terminal"
                icon_html  = "&#9211;"  # ⏻ power symbol
                label_text = "Session exited"
                tooltip    = ("Most recent /exit local command in this JSONL "
                              "with no subsequent assistant turn observed. "
                              "Whether the user has resumed since cannot be "
                              "determined from this file alone.")
            else:
                pill_cls   = "resume-marker-pill"
                icon_html  = "&#8634;"  # ↻ cycle
                label_text = "Session resumed"
                tooltip    = ("claude -c replayed a prior /exit local-command "
                              "into this session; CC emitted a no-op "
                              "`<synthetic>` assistant entry. Detection is "
                              "precise when it fires but may under-count "
                              "(resumes after Ctrl+C or crash leave no trace).")
            return (
                f'<tr class="resume-marker-row" data-session="{session_id[:8]}">'
                f'<td class="num resume-marker-idx">{t["index"]}</td>'
                f'<td colspan="{_full_cols - 1}" class="resume-marker-cell">'
                f'<span class="{pill_cls}" title="{tooltip}">'
                f'<span class="resume-marker-icon">{icon_html}</span>'
                f'<strong>{label_text}</strong>'
                f'<span class="resume-marker-time">at {ts_fmt}</span>'
                f'</span></td></tr>'
            )
        bar_w = min(100, int(t["cost_usd"] * 2000))
        mode_td = ""
        if show_mode:
            spd = t.get("speed", "")
            label = "fast" if spd == "fast" else "std"
            cls = ' class="mode-fast"' if spd == "fast" else ' class="mode-std"'
            mode_td = f'<td{cls}>{label}</td>'
        cwr_td = _cwr_cell(
            t["cache_write_tokens"],
            t.get("cache_write_5m_tokens", 0),
            t.get("cache_write_1h_tokens", 0),
            t.get("cache_write_ttl", ""),
            is_cache_break=t.get("is_cache_break", False),
        )
        content_td = (_content_cell(t.get("content_blocks") or {})
                      if show_content else "")
        # data-turn-id is the key the drawer JS uses to pull this turn's
        # detail payload out of #turn-data. Namespaced by session_id[:8] so
        # project-mode reports with multiple sessions don't collide on the
        # per-session turn index.
        turn_key = f'{session_id[:8]}-{t["index"]}'
        _si = t.get("skill_invocations") or []
        _sc = t.get("slash_command") or ""
        _skill_label = _si[0] if _si else (_sc.lstrip("/") if _sc else "")
        _skill_badge = (
            f' <span class="skill-tag" title="skill: {html_mod.escape(_skill_label)}">'
            f'{html_mod.escape(_skill_label)}</span>'
        ) if _skill_label else ""
        _truncated_badge = (
            ' <span class="truncated-tag"'
            ' title="stop_reason: max_tokens — response was cut off">&#9986; truncated</span>'
        ) if t.get("stop_reason") == "max_tokens" else ""
        _char      = t.get("turn_character", "")
        _char_lbl  = html_mod.escape(t.get("turn_character_label", ""))
        _risk      = t.get("turn_risk", False)
        _risk_badge = (
            '<span class="wc-risk-badge" title="Potentially wasteful turn type">&#9888;</span>'
        ) if _risk else ""
        waste_td   = (
            f'<td class="wc-char" title="{_char}">'
            f'<div class="wc-char-inner">'
            f'<span class="wc-lbl">{_char_lbl}</span>{_risk_badge}'
            f'</div></td>'
        ) if show_waste else ""
        return (
            f'{continued_divider}'
            f'{compaction_divider}'
            f'{clear_divider}'
            f'<tr id="turn-{turn_key}" class="turn-row" data-session="{session_id[:8]}"'
            f' data-turn-id="{turn_key}" role="button" tabindex="0">'
            f'<td class="num">{t["index"]}</td>'
            f'<td class="ts">{html_mod.escape(t["timestamp_fmt"])}</td>'
            f'<td class="model">{html_mod.escape(t["model"])}{_skill_badge}{_truncated_badge}</td>'
            f'{mode_td}'
            f'<td class="num">{t["input_tokens"]:,}</td>'
            f'<td class="num">{t["output_tokens"]:,}</td>'
            f'<td class="num">{t["cache_read_tokens"]:,}</td>'
            f'{cwr_td}'
            f'{content_td}'
            f'<td class="num">{t["total_tokens"]:,}</td>'
            f'<td class="cost"><span class="bar" style="width:{bar_w}px"></span>'
            f'${t["cost_usd"]:.4f}</td>'
            f'{waste_td}'
            f'</tr>'
        )

    def session_header(i: int, s: dict) -> str:
        if mode != "project":
            return ""
        st = s["subtotal"]
        _adv_n = st.get("advisor_call_count", 0)
        _adv_badge = ""
        if _adv_n > 0:
            _adv_c = st.get("advisor_cost_usd", 0.0)
            _adv_m = s.get("advisor_configured_model") or ""
            _adv_label = f" · {html_mod.escape(_adv_m)}" if _adv_m else ""
            _adv_badge = (
                f'&nbsp;·&nbsp; <span class="advisor-badge" '
                f'title="Advisor called {_adv_n} time(s) in this session '
                f'(cost included in total above)">'
                f'advisor{_adv_label} +${_adv_c:.4f}</span>'
            )
        # Per-session cache-trend sparkline. Empty string when the session
        # is too short to plot — the helper auto-skips below the window
        # threshold so single-edit sessions don't get a misleading flat
        # line. Surfaces mid-session degradation hidden by the session
        # subtotal's aggregate cache hit %.
        _spark = _sm()._build_cache_trend_sparkline_svg(s.get("turns") or [])
        _spark_cell = (
            f'&nbsp;·&nbsp; <span class="cache-spark-wrap" title="Rolling cache hit % over the session">{_spark}</span>'
            if _spark else ""
        )
        return (
            f'<tr class="session-header" data-toggle="sess-{i}" role="button">'
            f'<td colspan="{_full_cols}">'
            f'<span class="toggle-arrow">&#9654;</span> '
            f'<strong>Session {i}: {s["session_id"][:8]}…</strong>'
            f'&nbsp; {s["first_ts"]} → {s["last_ts"]}'
            f'&nbsp;·&nbsp; {len(s["turns"])} turns'
            f'&nbsp;·&nbsp; <strong>${st["cost"]:.4f}</strong>'
            f'{_adv_badge}'
            f'{_spark_cell}'
            f'</td></tr>'
        )

    def subtotal_row(label: str, st: dict) -> str:
        tokens_1h = st.get("cache_write_1h", 0)
        if tokens_1h > 0:
            tokens_5m = st.get("cache_write_5m", 0)
            sub_ttl = "mix" if st.get("cache_write_5m", 0) > 0 else "1h"
        else:
            tokens_5m = st.get("cache_write_5m", 0)
            sub_ttl = ""
        cwr_td = _cwr_cell(st["cache_write"], tokens_5m, tokens_1h, sub_ttl, bold=True)
        content_td = ('<td class="content-blocks muted">&nbsp;</td>'
                      if show_content else "")
        waste_td = '<td class="wc-char muted">&nbsp;</td>' if show_waste else ""
        return (
            f'<tr class="subtotal">'
            f'<td colspan="{_label_span}"><strong>{label}</strong></td>'
            f'<td class="num"><strong>{st["input"]:,}</strong></td>'
            f'<td class="num"><strong>{st["output"]:,}</strong></td>'
            f'<td class="num"><strong>{st["cache_read"]:,}</strong></td>'
            f'{cwr_td}'
            f'{content_td}'
            f'<td class="num"><strong>{st["total"]:,}</strong></td>'
            f'<td class="cost"><strong>${st["cost"]:.4f}</strong></td>'
            f'{waste_td}'
            f'</tr>'
        )

    def _idle_gap_row(gap_s: float) -> str:
        mins = int(gap_s // 60)
        if mins < 120:
            label = f"{mins} min idle"
        else:
            h, m = divmod(mins, 60)
            label = f"{h}h {m}m idle" if m else f"{h}h idle"
        return (
            f'<tr class="idle-gap-row">'
            f'<td colspan="{_full_cols}" class="idle-gap-cell">'
            f'<span class="idle-gap-pill">&#9646; {label}</span>'
            f'</td></tr>'
        )

    def _model_switch_row(prev: str, cur: str) -> str:
        def _short(m: str) -> str:
            return m.removeprefix("claude-")
        return (
            f'<tr class="model-switch-row">'
            f'<td colspan="{_full_cols}" class="model-switch-cell">'
            f'<span class="model-switch-pill">'
            f'&#8644; Model: {html_mod.escape(_short(prev))}'
            f' &rarr; {html_mod.escape(_short(cur))}'
            f'</span></td></tr>'
        )

    table_rows: list[str] = []
    model_rows = ""
    if include_chart:
        _idle_gap_s = (idle_gap_minutes * 60) if idle_gap_minutes > 0 else None
        for i, s in enumerate(sessions, 1):
            if mode == "project":
                table_rows.append(session_header(i, s))
                table_rows.append(f'<tbody class="session-body" id="sess-{i}" style="display:none">')
            _prev_ts: str | None = None
            _prev_model: str | None = None
            _prev_was_resume = False
            for t in s["turns"]:
                if not t.get("is_resume_marker"):
                    t_ts    = t.get("timestamp", "")
                    t_model = t.get("model", "")
                    # Idle gap divider
                    if _idle_gap_s and not _prev_was_resume and _prev_ts and t_ts:
                        prev_dt = _sm()._parse_iso_dt(_prev_ts)
                        cur_dt  = _sm()._parse_iso_dt(t_ts)
                        if prev_dt and cur_dt:
                            gap = (cur_dt - prev_dt).total_seconds()
                            if gap >= _idle_gap_s:
                                table_rows.append(_idle_gap_row(gap))
                    # Model switch divider
                    if (_prev_model is not None
                            and not _prev_was_resume
                            and t_model != _prev_model):
                        table_rows.append(_model_switch_row(_prev_model, t_model))
                    _prev_ts    = t_ts
                    _prev_model = t_model
                    _prev_was_resume = False
                else:
                    # Resume marker: update _prev_ts so the post-resume gap is not
                    # measured from before the resume. Do NOT update _prev_model —
                    # the synthetic "<synthetic>" model must not trigger a switch row.
                    _prev_ts = t.get("timestamp", "") or _prev_ts
                    _prev_was_resume = True
                table_rows.append(turn_row(t, s["session_id"]))
            if mode == "project":
                table_rows.append(subtotal_row(f"S{i:02} subtotal", s["subtotal"]))
                table_rows.append('</tbody>')
        table_rows.append(subtotal_row("PROJECT TOTAL" if mode == "project" else "TOTAL", totals))

        _t_total = sum(int(i.get("turns", 0)) for i in report["models"].values()) or 1
        _c_total = sum(float(i.get("cost_usd", 0.0)) for i in report["models"].values()) or 0.0

        def _model_row_html(m: str, cnt: int, cost: float, t_pct: float, c_pct: float) -> str:
            r = _sm()._pricing_for(m)
            return (f'<tr><td><code>{html_mod.escape(m)}</code></td>'
                    f'<td class="num">{cnt:,}</td>'
                    f'<td class="num">{t_pct:.1f}%</td>'
                    f'<td class="num">${cost:.4f}</td>'
                    f'<td class="num">{c_pct:.1f}%</td>'
                    f'<td class="num">${r["input"]:.2f}</td>'
                    f'<td class="num">${r["output"]:.2f}</td>'
                    f'<td class="num">${r["cache_read"]:.2f}</td>'
                    f'<td class="num">${r["cache_write"]:.2f}</td></tr>')

        model_rows = "".join(
            _model_row_html(
                m,
                int(info.get("turns", 0)),
                float(info.get("cost_usd", 0.0)),
                100.0 * int(info.get("turns", 0)) / _t_total,
                (100.0 * float(info.get("cost_usd", 0.0)) / _c_total) if _c_total else 0.0,
            )
            for m, info in sorted(report["models"].items(),
                                  key=lambda x: -float(x[1].get("cost_usd", 0.0)))
        )

    # Nav bar: cross-link to the companion page.
    # Switcher is embedded inside the topbar's <nav> to avoid positional overlap.
    # Split mode: brand left + [Dashboard | Detail | switcher] right.
    # Single mode: brand left + [switcher] right (no cross-link).
    _sw = _theme_picker_markup()
    # Cross-link to the dynamic-workflow companion deep-dive when one was
    # emitted (set on the report by ``_dispatch`` before render). Renders
    # beside the Dashboard/Detail toggle in both split and single modes.
    _wf_href = report.get("_workflow_companion_href")
    _wf_link = (
        f'<a class="navlink" data-sm-nav href="{html_mod.escape(_wf_href)}">Workflows</a>'
        if _wf_href and (report.get("by_workflow") or []) else ""
    )
    # Cross-link to the Tasks companion. Unlike the workflow companion (written
    # by the script itself), the Tasks page is generated post-export by the
    # task-breakdown flow — so `_dispatch` sets ``_tasks_companion_href`` only
    # when the caller signalled it will be generated (``--task-companion-nav``),
    # keeping the link from dangling on a raw-script run that skips grouping.
    _tasks_href = report.get("_tasks_companion_href")
    _tasks_link = (
        f'<a class="navlink" data-sm-nav href="{html_mod.escape(_tasks_href)}">Tasks</a>'
        if _tasks_href and (report.get("request_units") or []) else ""
    )
    if nav_sibling:
        label_here  = "Dashboard" if variant == "dashboard" else "Detail"
        label_other = "Detail"   if variant == "dashboard" else "Dashboard"
        nav_html = (
            f'<header class="topbar sm-nav">'
            f'<div class="brand"><span class="dot"></span>'
            f'<span>session-metrics</span></div>'
            f'<nav class="nav">'
            f'<span class="navlink current">{label_here}</span>'
            f'<a class="navlink" data-sm-nav href="{html_mod.escape(nav_sibling)}">{label_other}</a>'
            f'{_wf_link}'
            f'{_tasks_link}'
            f'{_sw}'
            f'</nav>'
            f'</header>'
        )
    else:
        nav_html = (
            f'<header class="topbar">'
            f'<div class="brand"><span class="dot"></span>'
            f'<span>session-metrics</span></div>'
            f'<nav class="nav">{_wf_link}{_tasks_link}{_sw}</nav>'
            f'</header>'
        )

    chart_section_html = ""
    if include_hc_chart and chart_html:
        chart_section_html = (
            '<section class="section">\n'
            '<div class="section-title"><h2>Token Usage Over Time</h2></div>\n'
            f'{chart_html}\n'
            '</section>'
        )

    table_section_html = ""
    if include_chart and table_rows:
        legend_parts = [
            '<b>#</b> turn index (deduplicated) · ',
            f'<b>Time</b> turn start ({html_mod.escape(tz_label)}) · ',
            '<b>Model</b> short model alias · ',
        ]
        if show_mode:
            legend_parts.append('<b>Mode</b> fast / standard · ')
        legend_parts.extend([
            '<b>Input (new)</b> net new <code>input_tokens</code> (uncached) · ',
            '<b>Output</b> <code>output_tokens</code> (includes thinking + tool_use block tokens) · ',
            '<b>CacheRd</b> <code>cache_read_input_tokens</code> · ',
        ])
        if show_ttl:
            legend_parts.append(
                '<b>CacheWr</b> <code>cache_creation_input_tokens</code> '
                '(badge marks 1h-tier turns; hover for 5m/1h split) · '
            )
        else:
            legend_parts.append('<b>CacheWr</b> <code>cache_creation_input_tokens</code> · ')
        if show_content:
            legend_parts.append(
                '<b>Content</b> per-turn content blocks: '
                '<code>T</code> thinking, <code>u</code> tool_use, '
                '<code>x</code> text, <code>r</code> tool_result, '
                '<code>i</code> image, <code>v</code> server_tool_use, '
                '<code>R</code> advisor_tool_result (zero counts omitted) · '
            )
        legend_parts.extend([
            '<b>Total</b> sum of the four billable token buckets · ',
            '<b>Cost $</b> estimated USD for this turn.',
        ])
        if show_waste:
            legend_parts.append(
                ' · <b>Turn Character</b> 9-category waste classification '
                '(⚠ = potentially wasteful)'
            )
        legend_html = '<p class="legend-block">' + ''.join(legend_parts) + '</p>'
        content_th = ('<th class="content-blocks">Content</th>'
                      if show_content else "")
        waste_th = '<th class="wc-char">Turn Character</th>' if show_waste else ""
        table_section_html = (
            '<section class="section">\n'
            '<div class="section-title"><h2>Timeline</h2></div>\n'
            + legend_html + '\n'
            + '<table class="timeline-table">\n<thead><tr>\n'
            f'  <th class="num">#</th><th>Time ({html_mod.escape(tz_label)})</th><th>Model</th>\n'
            f'  {"<th>Mode</th>" if show_mode else ""}\n'
            '  <th class="num">Input (new)</th><th class="num">Output</th>\n'
            '  <th class="num">CacheRd</th><th class="num">CacheWr</th>\n'
            f'  {content_th}\n'
            '  <th class="num">Total</th><th class="num">Cost $</th>\n'
            f'  {waste_th}\n'
            f'</tr></thead>\n<tbody>\n{"".join(table_rows)}\n</tbody>\n</table>\n'
            '</section>'
        )

    models_section_html = ""
    if include_chart and model_rows:
        models_section_html = (
            '<section class="section">\n'
            '<div class="section-title"><h2>Models</h2></div>\n'
            '<table class="models-table">\n'
            '<thead><tr><th>Model</th>\n'
            '  <th class="num">Turns</th><th class="num">Turn %</th>\n'
            '  <th class="num">Cost $</th><th class="num">Cost %</th>\n'
            '  <th class="num">$/M input</th><th class="num">$/M output</th>\n'
            '  <th class="num">$/M rd</th><th class="num">$/M wr</th></tr></thead>\n'
            f'<tbody>{model_rows}</tbody>\n</table>\n'
            '</section>'
        )

    # C.6: durable pricing advisory. Surfaces the rate-table snapshot date and
    # any models priced at family-tier fallback (mirrors the stderr [warn], but
    # in the exported file). Reuses the theme-verified .health-panel chrome so
    # no new across-theme CSS is introduced. Auto-hidden when every model
    # resolved to an exact rate.
    pricing_advisory_html = ""
    _unpriced = report.get("unpriced_models") or []
    if _unpriced:
        _snap = html_mod.escape(str(report.get("pricing_snapshot_date", "") or ""))
        _models_esc = ", ".join(html_mod.escape(m) for m in _unpriced)
        pricing_advisory_html = (
            '<section class="section" id="pricing-advisory-section">\n'
            '<div class="section-title"><h2>Pricing advisory</h2></div>\n'
            '<div class="health-panel">\n'
            f'<p style="color:var(--fg-dim)">Rate table snapshot: <strong>{_snap}</strong>. '
            f'{len(_unpriced)} model(s) priced at family-tier fallback rates '
            '(no exact entry). Pass <code>--refresh-pricing &lt;file.json&gt;</code> to '
            f'supplement these with current rates: {_models_esc}</p>\n'
            '</div>\n</section>'
        )

    summary_cards_html = ""
    health_section_html = ""
    behavior_section_html = ""
    if include_insights:
        ttl_mix_card = _build_ttl_mix_card_html(totals)
        thinking_card = _build_thinking_card_html(totals)
        tool_calls_card = _build_tool_calls_card_html(totals)
        # Advisor model label lives only on the per-session ``sessions`` list;
        # pull it from the first session that has one and pass it in so the
        # session card keeps its model annotation (instance scope passes None).
        _adv_cfgm = next(
            (s.get("advisor_configured_model") for s in sessions
             if s.get("advisor_configured_model")),
            None,
        )
        advisor_card = _build_advisor_card_html(totals, _adv_cfgm)
        resumes_card = ""
        resumes_list = report.get("resumes") or []
        if resumes_list:
            non_terminal = [r for r in resumes_list if not r.get("terminal")]
            n_resumes = len(non_terminal)
            # Collect short local times (HH:MM portion of timestamp_fmt)
            times = [r.get("timestamp_fmt", "").split(" ")[-1][:5]
                     for r in non_terminal if r.get("timestamp_fmt")]
            times_str = ", ".join(times) if times else ""
            terminal_note = ""
            n_terminal = len(resumes_list) - n_resumes
            if n_terminal:
                terminal_note = f' · {n_terminal} terminal exit'
                if n_terminal != 1:
                    terminal_note += "s"
            resumes_card = (
                f'\n  <div class="kpi">'
                f'<div class="kpi-label" title="Precise lower bound: detects claude -c '
                f'resumes that replay a prior /exit into this session. Resumes '
                f'after Ctrl+C or crash leave no trace and are not counted.">'
                f'Session resumes'
                f'{(" &middot; " + times_str) if times_str else ""}'
                f'{terminal_note}'
                f'</div>'
                f'<div class="kpi-val">&#8634; {n_resumes} detected</div></div>'
            )
        _n_trunc = sum(
            1 for s in sessions
            for t in s.get("turns", [])
            if t.get("stop_reason") == "max_tokens"
        )
        truncated_card = (
            f'\n  <div class="kpi" title="Turns where Claude hit the output token'
            f' limit (stop_reason=max_tokens). These responses are incomplete.">'
            f'<div class="kpi-label">Truncated (max_tokens)</div>'
            f'<div class="kpi-val">&#9986; {_n_trunc} turn{"s" if _n_trunc != 1 else ""}</div>'
            f'</div>'
        ) if _n_trunc > 0 else ""
        # Q1: context-compaction KPI card. Auto-hides when no boundary was
        # recorded. Reclaimed = preTokens-postTokens summed across boundaries;
        # a compaction resets working context (next turn rebuilds it → cache
        # write spike), so this card explains otherwise-anomalous token flow.
        compaction_card = ""
        _cs = report.get("compaction_summary") or {}
        _cn = int(_cs.get("boundary_count", 0) or 0)
        if _cn > 0:
            _auto = int(_cs.get("auto_count", 0) or 0)
            _manual = int(_cs.get("manual_count", 0) or 0)
            _recl = int(_cs.get("total_reclaimed_tokens", 0) or 0)
            _cont = int(_cs.get("continuation_session_count", 0) or 0)
            _split = []
            if _auto:
                _split.append(f"{_auto} auto")
            if _manual:
                _split.append(f"{_manual} manual")
            _split_str = (" &middot; " + ", ".join(_split)) if _split else ""
            _cont_note = (
                f' &middot; {_cont} continued session{"s" if _cont != 1 else ""}'
                if _cont else ""
            )
            compaction_card = (
                f'\n  <div class="kpi" title="Context-window compaction events '
                f'(compact_boundary). Reclaimed = tokens dropped from context '
                f'(preTokens - postTokens). A compaction resets the working '
                f'context; the next turn rebuilds it (cache-write spike).">'
                f'<div class="kpi-label">Context compactions{_split_str}{_cont_note}</div>'
                f'<div class="kpi-val">&#128476;&#65039; {_cn} &middot; '
                f'{_recl:,} reclaimed</div></div>'
            )
        # v1.26.0: subagent share KPI card. Always rendered (even in
        # the "attribution disabled" branch) so the framing question
        # stays visible.
        # Prefer the stats stamped by ``_build_report`` (guard pattern shared
        # with _dispatch.py's instance renderers); recompute only for callers
        # that hand-build a report without the key.
        _sa_stats = (report.get("subagent_share_stats")
                     or _sm()._compute_subagent_share(report))
        subagent_share_card = "\n  " + _build_subagent_share_card_html(_sa_stats)
        # cognitive-claude-inspired count-basis turn-share card. Empty
        # when no subagent turns are present so it auto-hides on
        # subagent-free reports.
        _turn_share = _build_subagent_turn_share_card_html(_sa_stats)
        subagent_turn_share_card = ("\n  " + _turn_share) if _turn_share else ""
        # Partial-hit rate card — shown when any turn touched the cache.
        partial_hit_card = _build_partial_hit_card_html(totals)
        # cognitive-claude-inspired plan-leverage card. Empty when
        # --plan-cost / SESSION_METRICS_PLAN_COST is unset.
        plan_leverage_card = _build_plan_leverage_card_html(
            totals, report.get("plan_cost"),
        )
        # v1.27.0: self-cost meta-metric KPI card — surfaces session-metrics'
        # own running token cost in this session. Hidden when --no-self-cost
        # stripped the field; also hidden when the session has zero
        # session-metrics turns (first-ever invocation), since a $0 / 0-turn
        # card adds no information on the dashboard.
        self_cost_card = ""
        _self_cost = report.get("self_cost") or {}
        if _self_cost and (int(_self_cost.get("turns", 0) or 0) > 0):
            _sc_turns  = int(_self_cost.get("turns", 0) or 0)
            _sc_cost   = float(_self_cost.get("cost_usd", 0.0) or 0.0)
            _sc_tokens = int(_self_cost.get("total_tokens", 0) or 0)
            self_cost_card = (
                f'\n  <div class="kpi" '
                f'title="Running total of prior session-metrics turns in '
                f'this session. The current invocation is not yet written '
                f'to the JSONL when the script reads it, so this number '
                f'always lags by one run.">'
                f'<div class="kpi-label">Skill self-cost &middot; prior runs '
                f'this session</div>'
                f'<div class="kpi-val">${_sc_cost:.4f} &middot; '
                f'{_sc_turns} turn{"s" if _sc_turns != 1 else ""} &middot; '
                f'{_sc_tokens:,} tokens</div></div>'
            )
        # Session-health (v1.72.0) — single-session reports only (the grade /
        # outcome is intrinsically per-session; a multi-session rollup has no
        # one grade). Card rides in the kpi-grid; the full breakdown is its own
        # section after the grid.
        _single_health = (sessions[0].get("session_health")
                          if len(sessions) == 1 else None)
        health_card = (("\n  " + _build_session_health_card_html(_single_health))
                       if _single_health else "")
        health_section_html = (_build_session_health_html(_single_health)
                               if _single_health else "")
        _single_behavior = (sessions[0].get("session_behavior")
                            if len(sessions) == 1 else None)
        behavior_section_html = (_build_session_behavior_html(_single_behavior)
                                 if _single_behavior else "")
        # C.3: never hide a negative cache "saving". When writes cost more than
        # reads saved, relabel the card to "Cache net cost" and tint the value
        # amber (a semantic status colour, intentionally theme-constant) so the
        # sign is unmistakable instead of reading as a cheerful $0.0000.
        _kpi_sav = totals["cache_savings"]
        if _kpi_sav >= 0:
            _kpi_sav_card = (
                '  <div class="kpi cat-save"><div class="kpi-label">Cache savings</div>'
                f'<div class="kpi-val">${_kpi_sav:.4f}</div></div>')
        else:
            _kpi_sav_card = (
                '  <div class="kpi cat-save" title="Cache writes cost more than reads saved on this run">'
                '<div class="kpi-label">Cache net cost</div>'
                f'<div class="kpi-val" style="color:#d29922">+${abs(_kpi_sav):.4f}</div></div>')
        summary_cards_html = f'''\
<div class="kpi-grid">{health_card}
  <div class="kpi featured cat-tokens"><div class="kpi-label">Total cost (USD)</div><div class="kpi-val">${totals['cost']:.4f}</div></div>{plan_leverage_card}
{_kpi_sav_card}
  <div class="kpi"><div class="kpi-label">Cache hit ratio</div><div class="kpi-val">{totals['cache_hit_pct']:.1f}%</div></div>{partial_hit_card}{subagent_share_card}{subagent_turn_share_card}
  <div class="kpi cat-tokens"><div class="kpi-label">Total input tokens</div><div class="kpi-val">{totals['total_input']:,}</div></div>
  <div class="kpi cat-tokens"><div class="kpi-label">Input tokens (new)</div><div class="kpi-val">{totals['input']:,}</div></div>
  <div class="kpi cat-tokens"><div class="kpi-label">Output tokens</div><div class="kpi-val">{totals['output']:,}</div></div>
  <div class="kpi cat-tokens"><div class="kpi-label">Cache read tokens</div><div class="kpi-val">{totals['cache_read']:,}</div></div>
  <div class="kpi cat-tokens"><div class="kpi-label">Cache write tokens</div><div class="kpi-val">{totals['cache_write']:,}</div></div>{ttl_mix_card}{thinking_card}{tool_calls_card}{advisor_card}{resumes_card}{truncated_card}{compaction_card}{self_cost_card}
</div>'''

    # Usage Insights panel — sits between the summary cards and the
    # weekly-rollup / time-of-day insight sections. Dashboard variant only;
    # rides the same `include_insights` gate as `summary_cards_html` above.
    usage_insights_html = (
        _build_usage_insights_html(report.get("usage_insights", []) or [])
        if include_insights else ""
    )

    # v1.8.0: Turn Character & Efficiency Signals — dashboard/single only.
    waste_analysis_html = (
        _build_waste_analysis_html(report.get("waste_analysis") or {})
        if include_insights else ""
    )

    # Phase-A (v1.6.0) sections — skill/subagent tables + cache-break events.
    # Dashboard/single only; detail page omits these (they already appear on dashboard).
    if include_insights:
        by_skill_html = _build_by_skill_html(report.get("by_skill", []) or [])
        by_subagent_type_html = _build_by_subagent_type_html(
            report.get("by_subagent_type", []) or [],
            subagents_included=bool(report.get("include_subagents", False)))
        by_workflow_html = _build_by_workflow_html(
            report.get("by_workflow", []) or [],
            companion_href=report.get("_workflow_companion_href"),
            show_project=bool(report.get("mode") == "instance"))
        cache_breaks_html = _build_cache_breaks_html(
            report.get("cache_breaks", []) or [],
            int(report.get("cache_break_threshold", _sm()._CACHE_BREAK_DEFAULT_THRESHOLD)),
        )
        # v1.26.0: trust gauge + within-session contrast. Both render
        # as "" when their data is empty/below-threshold, so they're
        # safe to interpolate unconditionally below.
        # Same stamped-stats reuse as ``_sa_stats`` above — both values are
        # precomputed by ``_build_report`` (subagent_share_stats /
        # subagent_within_session_split); recompute is a fallback only.
        attribution_coverage_html = _build_attribution_coverage_html(
            report.get("subagent_share_stats")
            or _sm()._compute_subagent_share(report))
        within_session_split_html = _build_within_session_split_html(
            report.get("subagent_within_session_split")
            or _sm()._compute_within_session_split(report.get("sessions") or []))
        request_units_html = _build_request_units_html(
            report.get("request_units", []) or [],
            float(totals.get("cost", 0.0) or 0.0))
        # Phase D insight sections (dashboard/single). Each auto-hides when its
        # data is absent: no cache-read → cache-efficiency hidden; no usable
        # velocity → velocity hidden; <2 costed sessions → treemap hidden.
        cache_efficiency_html = _build_cache_efficiency_html(totals)
        velocity_html = _build_velocity_html(report)
        cost_treemap_html = _build_cost_treemap_html(report)
        _build_vital_signs_html(report)  # D.6 stub — reserved no-op
    else:
        by_skill_html = ""
        by_subagent_type_html = ""
        by_workflow_html = ""
        cache_breaks_html = ""
        request_units_html = ""
        attribution_coverage_html = ""
        within_session_split_html = ""
        cache_efficiency_html = ""
        velocity_html = ""
        cost_treemap_html = ""

    toggle_script_html = ""
    if include_chart and mode == "project":
        toggle_script_html = """<script>
document.querySelectorAll('tr.session-header[data-toggle]').forEach(function (hdr) {
  hdr.addEventListener('click', function () {
    var body = document.getElementById(hdr.getAttribute('data-toggle'));
    if (!body) return;
    var open = body.style.display !== 'none';
    body.style.display = open ? 'none' : '';
    hdr.classList.toggle('open', !open);
  });
});
</script>"""

    # Per-turn drill-down: embed one JSON payload per page (keyed by
    # "<sid8>-<idx>"), render a right-side drawer + optional Prompts section,
    # and wire both Timeline rows and Prompts rows to the same open/close JS.
    # Skip resume-marker rows — the drawer doesn't open on them.
    turn_data_json_html  = ""
    turn_drawer_html     = ""
    prompts_section_html = ""
    drawer_script_html   = ""
    chartrail_section_html = ""
    cost_over_time_html  = ""  # D.4: session-scope stacked area (detail/single)
    if include_chart:
        cost_over_time_html = _build_cost_over_time_svg_html(report)
        turn_data: dict[str, dict] = {}
        prompts_rows: list[dict]   = []
        # Chart-rail data — one row per turn in document order.
        # Resume markers are rendered as a distinct column (.tcol.resume) rather
        # than a full stacked bar; they don't enter turn_data (no drawer).
        chartrail_data: list[dict] = []
        for s in sessions:
            sid8 = s["session_id"][:8]
            sess_label = f'{sid8} · {s.get("first_ts", "")}'
            first_in_session = True
            for t in s["turns"]:
                if t.get("is_resume_marker"):
                    chartrail_data.append({
                        "n":    t["index"],
                        "key":  "",
                        "ts":   t.get("timestamp_fmt", ""),
                        "time": (t.get("timestamp_fmt", "").split(" ")
                                  [-1][:5]),
                        "mdl":  "",
                        "inp":  0,
                        "out":  0,
                        "cr":   0,
                        "cw":   0,
                        "tot":  0,
                        "cost": 0.0,
                        "sid":  sid8,
                        "slbl": sess_label,
                        "sbrk": first_in_session,
                        "resm": True,
                        "term": bool(t.get("is_terminal_exit_marker")),
                    })
                    first_in_session = False
                    continue
                key = f'{sid8}-{t["index"]}'
                turn_data[key] = {
                    "idx":   t["index"],
                    "ts":    t.get("timestamp_fmt", ""),
                    "mdl":   t.get("model", ""),
                    "ps":    t.get("prompt_snippet", ""),
                    "pt":    _sm()._truncate(t.get("prompt_text", ""), _sm()._PROMPT_TEXT_CAP),
                    "sc":    t.get("slash_command", ""),
                    "tl":    t.get("tool_use_detail", []) or [],
                    "cb":    t.get("content_blocks") or {},
                    "cost":     t.get("cost_usd", 0.0),
                    "nc":       t.get("no_cache_cost_usd", 0.0),
                    "inp":      t.get("input_tokens", 0),
                    "out":      t.get("output_tokens", 0),
                    "cr":       t.get("cache_read_tokens", 0),
                    "cw":       t.get("cache_write_tokens", 0),
                    "cwt":      t.get("cache_write_ttl", ""),
                    "adv_cost": t.get("advisor_cost_usd", 0.0),
                    "adv_mdl":  t.get("advisor_model", "") or "",
                    "adv_inp":  t.get("advisor_input_tokens", 0),
                    "adv_out":  t.get("advisor_output_tokens", 0),
                    "si":    t.get("skill_invocations") or [],
                    "asnip": t.get("assistant_snippet", ""),
                    "atxt":  t.get("assistant_text", ""),
                    "sr":    t.get("stop_reason", ""),
                    "wc":    t.get("turn_character", "productive"),
                    "wcl":   t.get("turn_character_label", "Productive"),
                    "risk":  t.get("turn_risk", False),
                    "wcp":   t.get("reaccessed_paths", []),
                    "wcctx": t.get("reread_cross_ctx", False),
                }
                chartrail_data.append({
                    "n":    t["index"],
                    "key":  key,
                    "ts":   t.get("timestamp_fmt", ""),
                    "time": (t.get("timestamp_fmt", "").split(" ")
                              [-1][:5]),
                    "mdl":  t.get("model", ""),
                    "inp":  t.get("input_tokens", 0),
                    "out":  t.get("output_tokens", 0),
                    "cr":   t.get("cache_read_tokens", 0),
                    "cw":   t.get("cache_write_tokens", 0),
                    "tot":  t.get("total_tokens", 0),
                    "cost": t.get("cost_usd", 0.0),
                    "sid":  sid8,
                    "slbl": sess_label,
                    "sbrk": first_in_session,
                    "resm": False,
                    "term": False,
                })
                first_in_session = False
                if t.get("prompt_text"):
                    prompts_rows.append({
                        "key":    key,
                        "cost":   t.get("cost_usd", 0.0),
                        "idx":    t["index"],
                        "model":  t.get("model", ""),
                        "prompt": t.get("prompt_snippet", ""),
                        "tools":  [tu.get("name", "") for tu in
                                   (t.get("tool_use_detail") or [])],
                        "tokens": t.get("total_tokens", 0),
                        "slash":  t.get("slash_command", ""),
                        # Phase-B (v1.7.0): rolled-up subagent token/cost
                        # from this prompt's spawned chain. Zero on turns
                        # that didn't spawn or whose attribution is off.
                        "att_cost":   t.get("attributed_subagent_cost", 0.0),
                        "att_tokens": t.get("attributed_subagent_tokens", 0),
                        "att_count":  t.get("attributed_subagent_count", 0),
                    })
        # `</` sequences would close the surrounding <script> tag early.
        # Replace them with `<\/` (still valid JSON inside a string literal).
        payload_json = json.dumps(turn_data, separators=(",", ":"), default=str)
        payload_json = payload_json.replace("</", "<\\/")
        turn_data_json_html = (
            f'<script type="application/json" id="turn-data">{payload_json}</script>'
        )

        # Chart-rail: horizontally-scrollable column chart, one column per turn.
        # Rendered into #chartrail-inner by JS from the chartrail-data JSON blob.
        chartrail_section_html = _build_chartrail_section_html(chartrail_data)

        turn_drawer_html = '''<div class="drawer-backdrop" id="drawer-backdrop"></div>
<aside id="drawer" class="drawer" aria-hidden="true" role="dialog"
       aria-labelledby="drawer-title">
  <div class="drawer-head">
    <h3 id="drawer-title">Turn <span data-slot="idx"></span></h3>
    <button class="x" id="drawer-close" aria-label="Close">&times;</button>
  </div>
  <div class="drawer-body" id="drawer-body">
    <div class="drawer-sec">
      <h4>Meta</h4>
      <dl class="drawer-kv">
        <dt>Time</dt><dd data-slot="ts"></dd>
        <dt>Model</dt><dd><code data-slot="model"></code></dd>
        <dt data-slot="slash-wrap-dt" hidden>Slash</dt>
        <dd data-slot="slash-wrap" hidden><code data-slot="slash"></code></dd>
        <dt data-slot="skill-wrap-dt" hidden>Skill</dt>
        <dd data-slot="skill-wrap" hidden><code data-slot="skill-name"></code></dd>
        <dt data-slot="sr-wrap-dt" hidden>Stop reason</dt>
        <dd data-slot="sr-wrap" hidden><code data-slot="sr-val"></code></dd>
      </dl>
    </div>
    <div class="drawer-sec" id="wc-sec" hidden>
      <h4>Turn Character</h4>
      <p data-slot="wc-label" class="drawer-wc-label"></p>
      <p data-slot="wc-explain" class="drawer-wc-explain"></p>
    </div>
    <div class="drawer-sec">
      <h4>Prompt</h4>
      <div data-slot="prompt-snippet" class="drawer-prompt"></div>
      <button class="drawer-more" data-state="collapsed" hidden>Show full prompt</button>
      <div data-slot="prompt-full" class="drawer-prompt" hidden></div>
    </div>
    <div class="drawer-sec" data-slot="tools-sec" hidden>
      <h4>Tools called (<span data-slot="tool-count"></span>)</h4>
      <ul data-slot="tools" class="drawer-tools-list"></ul>
    </div>
    <div class="drawer-sec">
      <h4>Content blocks</h4>
      <dl data-slot="content-dl" class="drawer-kv"></dl>
    </div>
    <div class="drawer-sec">
      <h4>Tokens</h4>
      <dl class="drawer-kv">
        <dt>Input (new)</dt><dd data-slot="tok-input"></dd>
        <dt>Output</dt><dd data-slot="tok-output"></dd>
        <dt>Cache read</dt><dd data-slot="tok-cache-read"></dd>
        <dt>Cache write</dt><dd data-slot="tok-cache-write"></dd>
        <dt data-slot="tok-adv-input-dt" hidden>Advisor input</dt>
        <dd data-slot="tok-adv-input" hidden></dd>
        <dt data-slot="tok-adv-output-dt" hidden>Advisor output</dt>
        <dd data-slot="tok-adv-output" hidden></dd>
      </dl>
    </div>
    <div class="drawer-sec">
      <h4>Cost</h4>
      <dl class="drawer-kv">
        <dt data-slot="cost-primary-dt" hidden>Primary</dt>
        <dd data-slot="cost-primary" hidden></dd>
        <dt data-slot="cost-advisor-dt" hidden>Advisor (<span data-slot="cost-advisor-model"></span>)</dt>
        <dd data-slot="cost-advisor" hidden></dd>
        <dt>Cost</dt><dd data-slot="cost"></dd>
      </dl>
      <p data-slot="cache-savings" class="drawer-savings" hidden></p>
    </div>
    <div class="drawer-sec" data-slot="assistant-sec" hidden>
      <h4>Assistant response</h4>
      <div data-slot="assistant-snippet" class="drawer-prompt"></div>
      <button class="drawer-more drawer-more-a" data-state="collapsed" hidden>Show full response</button>
      <div data-slot="assistant-full" class="drawer-prompt" hidden></div>
    </div>
  </div>
</aside>'''

        if prompts_rows:
            # Phase-B (v1.7.0): default sort is now ``self + attributed
            # subagent cost`` for HTML — surfaces cheap-prompt-spawning-
            # expensive-subagent turns. ``--sort-prompts-by self`` opts
            # back into pre-Phase-B parent-cost-only ordering. CSV/JSON
            # default to ``self`` separately so script consumers stay
            # stable.
            prompts_sort_mode = report.get("sort_prompts_by") or "total"
            if prompts_sort_mode == "self":
                prompts_rows.sort(key=lambda r: -r["cost"])
            else:
                prompts_rows.sort(
                    key=lambda r: -(r["cost"] + r.get("att_cost", 0.0)))
            top = prompts_rows[:20]
            # Hide the Subagents+$ column entirely when nothing in the
            # top-N actually has attribution — keeps the table tight on
            # sessions without subagent activity.
            show_att = any(r.get("att_count", 0) > 0 for r in top)
            rows_html: list[str] = []
            for r in top:
                tool_names = r["tools"]
                if tool_names:
                    tools_str = ", ".join(html_mod.escape(n)
                                          for n in tool_names[:3])
                    if len(tool_names) > 3:
                        tools_str += f" +{len(tool_names) - 3}"
                else:
                    tools_str = "&mdash;"
                slash_badge = ""
                if r.get("slash"):
                    slash_badge = (f' <span class="prompts-slash">'
                                   f'{html_mod.escape(r["slash"])}</span>')
                # Subagent annotation appended to the prompt cell when
                # the row has attributed cost — keeps the spawn signal
                # visible even when the dedicated column is hidden.
                # v1.26.0: append "(NN% of combined cost)" — "combined"
                # not "of turn", because the visible Cost column shows
                # the *direct* turn cost only; "% of turn" would imply
                # the parent was 37% of itself.
                sub_badge = ""
                if r.get("att_count", 0) > 0:
                    _direct = float(r.get("cost", 0.0))
                    _att    = float(r.get("att_cost", 0.0))
                    _denom  = _direct + _att
                    _pct    = (100.0 * _att / _denom) if _denom > 0 else 0.0
                    sub_badge = (
                        f' <span class="prompts-subagent" title="'
                        f'Includes ${r["att_cost"]:.4f} from {r["att_count"]} '
                        f'subagent turn(s) attributed to this prompt. '
                        f'Subagents account for {_pct:.0f}% of the combined '
                        f'(direct + attributed) cost on this turn.">'
                        f'+{r["att_count"]} subagent'
                        f'{"s" if r["att_count"] != 1 else ""}'
                        f' ({_pct:.0f}% of combined cost)'
                        f'</span>'
                    )
                att_cell = (
                    f'<td class="num cost">${r["att_cost"]:.4f}</td>'
                    if show_att else ""
                )
                key_esc = html_mod.escape(r["key"])
                rows_html.append(
                    f'<tr data-turn="{key_esc}" tabindex="0">'
                    f'<td class="num">'
                    f'<a class="prompt-turn-link" href="#turn-{key_esc}">'
                    f'#{r["idx"]}</a></td>'
                    f'<td><div class="prompt-text truncate">'
                    f'{html_mod.escape(r["prompt"])}{slash_badge}{sub_badge}'
                    f'</div></td>'
                    f'<td class="cost">${r["cost"]:.4f}</td>'
                    f'{att_cell}'
                    f'<td class="model"><code>{html_mod.escape(r["model"])}</code></td>'
                    f'<td class="tools">{tools_str}</td>'
                    f'<td class="num">{r["tokens"]:,}</td>'
                    f'</tr>'
                )
            att_th = (
                '<th class="num" title="Subagent token cost rolled up '
                'onto this prompt (Phase-B attribution)">Subagents +$</th>'
                if show_att else ""
            )
            sort_hint = (
                "ranked by parent + attributed subagent cost"
                if prompts_sort_mode != "self"
                else "ranked by parent-turn cost only"
            )
            prompts_section_html = (
                '<section class="section">\n'
                '<div class="section-title"><h2>Prompts</h2>'
                f'<span class="hint">most-expensive user prompts in this report '
                f'&middot; {sort_hint} '
                f'&middot; click a row to open turn drawer</span></div>\n'
                '<div class="prompts">\n<table>\n<thead><tr>'
                '<th>Turn</th><th>Prompt</th><th class="num">Cost</th>'
                f'{att_th}'
                '<th>Model</th>'
                '<th>Tools</th><th class="num">Tokens</th></tr></thead>\n'
                f'<tbody>{"".join(rows_html)}</tbody></table>\n'
                '</div>\n</section>'
            )

        drawer_script_html = """<script>
(function () {
  var root = document.getElementById('turn-data');
  if (!root) return;
  var data; try { data = JSON.parse(root.textContent); } catch (e) { return; }
  var drawer   = document.getElementById('drawer');
  if (!drawer) return;
  var backdrop = document.getElementById('drawer-backdrop');
  var lastFocused = null;
  function sel(slot) { return drawer.querySelector('[data-slot="' + slot + '"]'); }
  function setText(slot, v) { var el = sel(slot); if (el) el.textContent = v == null ? '' : String(v); }
  function formatNum(n) { return typeof n === 'number' ? n.toLocaleString() : ''; }

  function openTurn(key) {
    var t = data[key]; if (!t) return;
    setText('idx', t.idx); setText('ts', t.ts); setText('model', t.mdl);
    var slashWrap = sel('slash-wrap');
    var slashWrapDt = sel('slash-wrap-dt');
    var slashEl = sel('slash');
    if (t.sc) {
      if (slashWrap) slashWrap.hidden = false;
      if (slashWrapDt) slashWrapDt.hidden = false;
      if (slashEl) slashEl.textContent = t.sc;
    } else {
      if (slashWrap) slashWrap.hidden = true;
      if (slashWrapDt) slashWrapDt.hidden = true;
    }
    var skillWrap = sel('skill-wrap');
    var skillWrapDt = sel('skill-wrap-dt');
    var skillNameEl = sel('skill-name');
    if (t.si && t.si.length) {
      if (skillWrap) skillWrap.hidden = false;
      if (skillWrapDt) skillWrapDt.hidden = false;
      if (skillNameEl) skillNameEl.textContent = t.si.join(', ');
    } else {
      if (skillWrap) skillWrap.hidden = true;
      if (skillWrapDt) skillWrapDt.hidden = true;
    }
    var srWrap = sel('sr-wrap');
    var srWrapDt = sel('sr-wrap-dt');
    var srValEl = sel('sr-val');
    var sr = t.sr || '';
    if (sr && sr !== 'end_turn') {
      if (srValEl) srValEl.textContent = sr;
      if (srWrap) srWrap.hidden = false;
      if (srWrapDt) srWrapDt.hidden = false;
    } else {
      if (srWrap) srWrap.hidden = true;
      if (srWrapDt) srWrapDt.hidden = true;
    }

    var snip = t.ps || '(no prompt captured)';
    setText('prompt-snippet', snip);
    var full = sel('prompt-full'), moreBtn = drawer.querySelector('.drawer-more:not(.drawer-more-a)');
    if (t.pt && t.pt.length > (t.ps || '').length) {
      moreBtn.hidden = false; moreBtn.dataset.state = 'collapsed';
      moreBtn.textContent = 'Show full prompt';
      full.hidden = true; full.textContent = t.pt;
      sel('prompt-snippet').hidden = false;
    } else {
      moreBtn.hidden = true; full.hidden = true; full.textContent = '';
      sel('prompt-snippet').hidden = false;
    }

    var tools = t.tl || [];
    var toolsSect = sel('tools-sec');
    var toolsList = sel('tools');
    setText('tool-count', tools.length);
    toolsList.innerHTML = '';
    if (tools.length) {
      toolsSect.hidden = false;
      tools.forEach(function (tu) {
        var li = document.createElement('li');
        var nm = document.createElement('code'); nm.textContent = tu.name || '';
        li.appendChild(nm);
        if (tu.input_preview) {
          var pv = document.createElement('span');
          pv.className = 'drawer-tool-preview';
          pv.textContent = ' ' + tu.input_preview;
          li.appendChild(pv);
        }
        toolsList.appendChild(li);
      });
    } else { toolsSect.hidden = true; }

    var dl = sel('content-dl'); dl.innerHTML = '';
    var cb = t.cb || {};
    var labels = {thinking:'Thinking', tool_use:'Tool use', text:'Text',
                  tool_result:'Tool result', image:'Image',
                  server_tool_use:'Server tool use', advisor_tool_result:'Advisor result'};
    Object.keys(labels).forEach(function (k) {
      var v = cb[k] || 0; if (!v) return;
      var dt = document.createElement('dt'); dt.textContent = labels[k];
      var dd = document.createElement('dd'); dd.textContent = v;
      dl.appendChild(dt); dl.appendChild(dd);
    });
    if (!dl.children.length) {
      var dt2 = document.createElement('dt'); dt2.textContent = 'No blocks';
      var dd2 = document.createElement('dd'); dd2.textContent = '\u2014';
      dl.appendChild(dt2); dl.appendChild(dd2);
    }

    setText('tok-input',       formatNum(t.inp));
    setText('tok-output',      formatNum(t.out));
    setText('tok-cache-read',  formatNum(t.cr));
    var cw = formatNum(t.cw);
    if (t.cwt) cw += '  (' + t.cwt + ')';
    setText('tok-cache-write', cw);
    var advInpDt = sel('tok-adv-input-dt'), advInpDd = sel('tok-adv-input');
    var advOutDt = sel('tok-adv-output-dt'), advOutDd = sel('tok-adv-output');
    if ((t.adv_inp || 0) > 0 || (t.adv_out || 0) > 0) {
      if (advInpDt) advInpDt.hidden = false;
      if (advInpDd) { advInpDd.hidden = false; advInpDd.textContent = formatNum(t.adv_inp || 0); }
      if (advOutDt) advOutDt.hidden = false;
      if (advOutDd) { advOutDd.hidden = false; advOutDd.textContent = formatNum(t.adv_out || 0); }
    } else {
      if (advInpDt) advInpDt.hidden = true;
      if (advInpDd) advInpDd.hidden = true;
      if (advOutDt) advOutDt.hidden = true;
      if (advOutDd) advOutDd.hidden = true;
    }
    var advCost = t.adv_cost || 0;
    var primaryDt = sel('cost-primary-dt'), primaryDd = sel('cost-primary');
    var advDt = sel('cost-advisor-dt'), advDd = sel('cost-advisor');
    var advMdlEl = sel('cost-advisor-model');
    if (advCost > 0) {
      var primaryCost = (t.cost || 0) - advCost;
      if (primaryDt) primaryDt.hidden = false;
      if (primaryDd) { primaryDd.hidden = false; primaryDd.textContent = '$' + primaryCost.toFixed(4); }
      if (advDt) advDt.hidden = false;
      if (advDd) { advDd.hidden = false; advDd.textContent = '$' + advCost.toFixed(4); }
      if (advMdlEl) advMdlEl.textContent = t.adv_mdl || 'advisor';
    } else {
      if (primaryDt) primaryDt.hidden = true;
      if (primaryDd) primaryDd.hidden = true;
      if (advDt) advDt.hidden = true;
      if (advDd) advDd.hidden = true;
    }
    setText('cost', '$' + (t.cost || 0).toFixed(4));
    var savings = (t.nc || 0) - (t.cost || 0);
    var sEl = sel('cache-savings');
    if (savings > 0) { sEl.textContent = 'Cache savings vs no-cache: $' + savings.toFixed(4); sEl.style.color = ''; sEl.hidden = false; }
    else if (savings < 0) { sEl.textContent = 'Cache net cost vs no-cache: +$' + (-savings).toFixed(4); sEl.style.color = '#d29922'; sEl.hidden = false; }
    else { sEl.textContent = ''; sEl.style.color = ''; sEl.hidden = true; }

    var asstSect = sel('assistant-sec');
    var asstSnip = sel('assistant-snippet');
    var asstFull = sel('assistant-full');
    var asstMore = drawer.querySelector('.drawer-more-a');
    if (t.asnip) {
      asstSect.hidden = false;
      asstSnip.hidden = false;
      asstSnip.textContent = t.asnip;
      if (t.atxt && t.atxt.length > t.asnip.length) {
        asstMore.hidden = false; asstMore.dataset.state = 'collapsed';
        asstMore.textContent = 'Show full response';
        asstFull.hidden = true; asstFull.textContent = t.atxt;
      } else {
        asstMore.hidden = true; asstFull.hidden = true; asstFull.textContent = '';
      }
    } else { asstSect.hidden = true; }

    // Turn Character explanation (v1.8.0)
    var wcSecEl = document.getElementById('wc-sec');
    var wcLabelEl = sel('wc-label');
    var wcExplainEl = sel('wc-explain');
    if (wcSecEl && wcLabelEl && wcExplainEl && t.wc) {
      var wc = t.wc;
      var isRisk = !!t.risk;
      wcLabelEl.textContent = t.wcl || wc;
      wcLabelEl.className = 'drawer-wc-label' + (isRisk ? ' risk' : (wc === 'productive' ? ' ok' : ''));
      var crAmt = t.cr || 0, inpAmt = t.inp || 0, cwAmt = t.cw || 0, outAmt = t.out || 0;
      var crTot = inpAmt + crAmt;
      var crPct = crTot > 0 ? Math.round(crAmt / crTot * 100) : 0;
      var thinkCt = (t.cb && t.cb.thinking) || 0;
      var paths = t.wcp || [];
      var ex;
      if (wc === 'subagent_overhead') {
        ex = 'Spawned a subagent (Agent or Task tool). Overhead includes context bootstrapping and output tokens from the spawned task, both billed to this turn.';
      } else if (wc === 'reasoning') {
        ex = 'Used extended thinking (' + thinkCt + ' thinking block' + (thinkCt !== 1 ? 's' : '') + '). Thinking tokens are billed at output rates and can significantly increase cost.';
      } else if (wc === 'cache_read') {
        ex = crPct + '% of input came from cache reads (' + crAmt.toLocaleString() + ' cached vs ' + inpAmt.toLocaleString() + ' new tokens). Cache reads cost ~10× less than new input — this is efficient.';
      } else if (wc === 'cache_write') {
        ex = 'Wrote ' + cwAmt.toLocaleString() + ' tokens to the prompt cache. Large cache payloads create checkpoints that reduce cost for subsequent turns.';
      } else if (wc === 'file_reread') {
        var crossCtx = !!t.wcctx;
        var shortPaths = paths.slice(0, 4).map(function (p) { return p.split('/').pop(); });
        var fileList = shortPaths.length
          ? ' Files: ' + shortPaths.join(', ') + (paths.length > 4 ? ' +' + (paths.length - 4) + ' more.' : '.')
          : '';
        if (crossCtx) {
          ex = 'Re-read in a new context (model or session changed).' + fileList
            + ' When a subagent or resumed session starts fresh, accessing the files it needs'
            + ' is expected and unavoidable. To reduce cost: use offset/limit on large-file'
            + ' Read calls to fetch only the relevant section, or pass key excerpts as part'
            + ' of the task prompt.';
        } else {
          ex = 'Re-read a file already accessed earlier in this context.' + fileList
            + ' Consider Grep to find specific content, or Read with offset/limit to avoid'
            + ' re-fetching the full file.';
        }
      } else if (wc === 'oververbose_edit') {
        ex = 'Edit turn with ' + outAmt.toLocaleString() + ' output tokens (threshold: 800). High output on an Edit turn may indicate over-explanation or unnecessary context repetition.';
      } else if (wc === 'retry_error') {
        ex = 'Prompt closely matches an earlier turn, suggesting a retry or repeated instruction. Retry chains waste tokens re-establishing context.';
      } else if (wc === 'dead_end') {
        ex = 'Response hit the max_tokens stop limit and was truncated. Follow-up turns may be needed to complete the task.';
      } else {
        ex = 'No waste signals detected — this turn made forward progress efficiently.';
      }
      wcExplainEl.textContent = ex;
      wcSecEl.hidden = false;
    } else if (wcSecEl) { wcSecEl.hidden = true; }

    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    if (backdrop) backdrop.classList.add('open');
    lastFocused = document.activeElement;
    var closeBtn = document.getElementById('drawer-close');
    if (closeBtn) closeBtn.focus();

    // Sync highlight state on any clickable sources bound to this turn.
    document.querySelectorAll('tr.turn-row[data-turn-id]').forEach(function (tr) {
      tr.classList.toggle('active', tr.getAttribute('data-turn-id') === key);
    });
    document.querySelectorAll('.prompts tbody tr[data-turn]').forEach(function (tr) {
      tr.classList.toggle('active', tr.getAttribute('data-turn') === key);
    });
    document.querySelectorAll('.tcol[data-turn]').forEach(function (c) {
      c.classList.toggle('active', c.getAttribute('data-turn') === key);
    });
  }
  // Expose for other modules (chart-rail) to call.
  window.smOpenDrawer = openTurn;

  function closeDrawer() {
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    if (backdrop) backdrop.classList.remove('open');
    if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
  }

  document.querySelectorAll('tr.turn-row[data-turn-id]').forEach(function (el) {
    el.addEventListener('click', function (ev) {
      if (ev.target && ev.target.closest && ev.target.closest('a')) return;
      openTurn(el.getAttribute('data-turn-id'));
    });
    el.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        openTurn(el.getAttribute('data-turn-id'));
      }
    });
  });

  document.querySelectorAll('.prompts tbody tr[data-turn]').forEach(function (el) {
    el.addEventListener('click', function (ev) {
      if (ev.target && ev.target.closest && ev.target.closest('a')) return;
      openTurn(el.getAttribute('data-turn'));
    });
    el.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        openTurn(el.getAttribute('data-turn'));
      }
    });
  });

  var closeBtnEl = document.getElementById('drawer-close');
  if (closeBtnEl) closeBtnEl.addEventListener('click', closeDrawer);
  if (backdrop) backdrop.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && drawer.classList.contains('open')) closeDrawer();
  });

  var moreBtn2 = drawer.querySelector('.drawer-more:not(.drawer-more-a)');
  if (moreBtn2) moreBtn2.addEventListener('click', function () {
    var full = sel('prompt-full'), snippet = sel('prompt-snippet');
    if (moreBtn2.dataset.state === 'collapsed') {
      full.hidden = false; snippet.hidden = true;
      moreBtn2.textContent = 'Show snippet'; moreBtn2.dataset.state = 'expanded';
    } else {
      full.hidden = true; snippet.hidden = false;
      moreBtn2.textContent = 'Show full prompt'; moreBtn2.dataset.state = 'collapsed';
    }
  });
  var moreA2 = drawer.querySelector('.drawer-more-a');
  if (moreA2) moreA2.addEventListener('click', function () {
    var full = sel('assistant-full'), snippet = sel('assistant-snippet');
    if (moreA2.dataset.state === 'collapsed') {
      full.hidden = false; snippet.hidden = true;
      moreA2.textContent = 'Show snippet'; moreA2.dataset.state = 'expanded';
    } else {
      full.hidden = true; snippet.hidden = false;
      moreA2.textContent = 'Show full response'; moreA2.dataset.state = 'collapsed';
    }
  });
})();
</script>"""

    chartrail_script_html = _chartrail_script() if chartrail_section_html else ""

    # Phase E — assemble the body into one block, stamp ``data-sm-section`` on
    # named sections, and build the chip nav + overlay script. Joining the
    # fragments with "\n" reproduces the prior per-line f-string layout
    # byte-for-byte (each fragment previously sat on its own line); the stamp
    # pass and overlay add only deterministic constant bytes.
    body_html_block = "\n".join([
        summary_cards_html, health_section_html, behavior_section_html,
        usage_insights_html, waste_analysis_html, cache_efficiency_html,
        velocity_html, cache_breaks_html, by_skill_html, by_subagent_type_html,
        by_workflow_html, attribution_coverage_html, within_session_split_html,
        tod_html, cost_treemap_html, chart_section_html, cost_over_time_html,
        chartrail_section_html, table_section_html, request_units_html,
        prompts_section_html, models_section_html, pricing_advisory_html,
    ])
    body_html_block, sm_chip_nav_html = _stamp_sections_and_build_chips(
        body_html_block)
    overlay_script_html = _overlay_js()

    title_suffix  = (" — Dashboard" if variant == "dashboard"
                     else " — Detail" if variant == "detail" else "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="chart-lib" content="{chart_lib}">
<title>Session Metrics — {slug}{title_suffix}</title>
{chart_head_html}
{_theme_css()}
{_overlay_css()}
{_theme_bootstrap_head_js()}
</head>
<body class="theme-console">
<div class="shell">
{nav_html}
{sm_chip_nav_html}
<header class="page-header">
  <h1>Session Metrics — {slug}{title_suffix}</h1>
  <p class="meta">Generated {generated} &nbsp;·&nbsp; Mode: {mode} &nbsp;·&nbsp;
  {len(sessions)} session{'s' if len(sessions) != 1 else ''}, {totals['turns']:,} turns &nbsp;·&nbsp; skill v{skill_version}</p>
</header>
{body_html_block}
<footer class="foot">
  <span class="muted">session-metrics · {generated}</span>
</footer>
</div>
{toggle_script_html}
{turn_data_json_html}
{turn_drawer_html}
{drawer_script_html}
{chartrail_script_html}
{overlay_script_html}
{_theme_bootstrap_body_js()}
</body>
</html>"""
