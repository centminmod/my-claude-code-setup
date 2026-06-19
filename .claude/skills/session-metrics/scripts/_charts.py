"""Chart rendering helpers for session-metrics."""
import functools
import hashlib
import json
import sys


def _sm():
    """Return the session_metrics module (deferred — fully loaded by call time)."""
    return sys.modules["session_metrics"]


_CHART_PAGE = 60   # max data points per chart panel before splitting into multiple


def _build_chart_html(
    cats: list, cache_rd: list, cache_wr: list,
    output: list, input_: list, cost: list, x_title: str,
    models: list[str] | None = None,
) -> str:
    """Return the full chart section HTML: containers + controls + JS.

    If len(cats) > _CHART_PAGE the data is split across multiple charts — one
    per page — each labelled 'Turns 1–60', 'Turns 61–120', etc.  A single set
    of 3D-rotation sliders drives all charts simultaneously.

    Optimisations:
    - Chart data is emitted once as a single JSON blob; a shared renderPage()
      function creates each Highcharts instance from that blob.
    - IntersectionObserver lazily renders charts only when scrolled into view.
    - Slider controls sync all rendered charts.

    models: optional per-bar model name list (same length as cats).  When
    provided, the tooltip header shows the model alongside the x-axis label.
    """
    n = len(cats)
    slices = [(s, min(s + _CHART_PAGE, n)) for s in range(0, n, _CHART_PAGE)]
    n_pages = len(slices)
    models_py = models or []

    # --- Build single DATA blob with all page slices -----------------------
    pages_data: list[dict] = []
    for s, e in slices:
        pages_data.append({
            "cats":     cats[s:e],
            "crd":      cache_rd[s:e],
            "cwr":      cache_wr[s:e],
            "out":      output[s:e],
            "inp":      input_[s:e],
            "cost":     cost[s:e],
            "models":   models_py[s:e] if models_py else [],
        })
    # Escape ``</`` → ``<\/`` so a ``</script>`` token in chart data (e.g. a
    # crafted/odd model id or a malformed timestamp) can't close this executable
    # <script> block and break out into the HTML body. Mirrors the turn-drawer /
    # timeline JSON payloads in _html_sections.py (v1.80.1).
    data_json = json.dumps(pages_data, separators=(",", ":")).replace("</", "<\\/")

    # --- Container divs ---------------------------------------------------
    divs: list[str] = []
    for pg, (s, e) in enumerate(slices):
        label = (
            f'<div class="chart-page-label">{x_title}s {s + 1}\u2013{e} of {n}</div>'
            if n_pages > 1 else ""
        )
        divs.append(f'{label}<div id="hc-chart-{pg}" class="hc-lazy" '
                    f'data-pg="{pg}" style="height:380px;padding:8px"></div>')

    containers_html = "\n".join(divs)

    # --- Single JS block: data + renderPage + lazy observer + sliders -----
    script = f"""\
(function () {{
  var charts = [];
  var DATA = {data_json};
  var X_TITLE = '{x_title}';

  // HTML-escape untrusted strings (e.g. model ids) before they enter the
  // tooltip HTML string below. Mirrors the esc() helper in the chartrail /
  // costail rails (_html_sections.py) — the JSON close-tag escape on
  // ``data_json`` only blocks <script> breakout, not attribute injection in
  // the tooltip formatter, so model names must be escaped JS-side too.
  function esc(s) {{
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }}

  function renderPage(pg) {{
    var d = DATA[pg];
    var c = Highcharts.chart('hc-chart-' + pg, {{
      chart: {{
        type: 'column', backgroundColor: '#161b22', plotBorderColor: '#30363d',
        options3d: {{
          enabled: true, alpha: 12, beta: 10, depth: 50, viewDistance: 25,
          frame: {{
            back: {{ color: '#21262d', size: 1 }},
            bottom: {{ color: '#21262d', size: 1 }},
            side: {{ color: '#21262d', size: 1 }}
          }}
        }}
      }},
      title: {{ text: null }},
      xAxis: {{
        categories: d.cats,
        title: {{ text: X_TITLE, style: {{ color: '#8b949e' }} }},
        labels: {{ style: {{ color: '#8b949e', fontSize: '10px' }}, rotation: -45 }},
        lineColor: '#30363d', tickColor: '#30363d'
      }},
      yAxis: [
        {{
          title: {{ text: 'Tokens', style: {{ color: '#8b949e' }} }},
          labels: {{ style: {{ color: '#8b949e', fontSize: '10px' }},
                     formatter: function () {{
                       return this.value >= 1000 ? (this.value / 1000).toFixed(0) + 'k' : this.value;
                     }} }},
          gridLineColor: '#21262d', stackLabels: {{ enabled: false }}
        }},
        {{
          title: {{ text: 'Cost (USD)', style: {{ color: '#d29922' }} }},
          labels: {{ style: {{ color: '#d29922', fontSize: '10px' }},
                     formatter: function () {{ return '$' + this.value.toFixed(4); }} }},
          opposite: true, gridLineWidth: 0
        }}
      ],
      legend: {{
        enabled: true, margin: 20, padding: 12,
        itemStyle: {{ color: '#8b949e', fontSize: '11px', fontWeight: 'normal' }},
        itemHoverStyle: {{ color: '#e6edf3' }}
      }},
      tooltip: {{
        backgroundColor: '#1c2128', borderColor: '#30363d',
        style: {{ color: '#e6edf3', fontSize: '11px' }},
        shared: true,
        formatter: function () {{
          var s = '<b>' + this.x + '</b>';
          if (d.models.length && d.models[this.points[0].point.index]) {{
            s += '&nbsp; <span style="color:#a5d6ff;font-size:10px">' +
                 esc(d.models[this.points[0].point.index]) + '</span>';
          }}
          s += '<br/>';
          this.points.forEach(function (p) {{
            var val = p.series.options.yAxis === 1
              ? '$' + p.y.toFixed(4)
              : p.y.toLocaleString() + ' tokens';
            s += '<span style="color:' + p.color + '">\u25cf</span> ' +
                 p.series.name + ': <b>' + val + '</b><br/>';
          }});
          return s;
        }}
      }},
      plotOptions: {{
        column: {{ stacking: 'normal', depth: 30, borderWidth: 0, groupPadding: 0.1 }},
        line:   {{ depth: 0, zIndex: 10, marker: {{ enabled: true, radius: 3 }} }}
      }},
      series: [
        {{ name: 'Cache Read',  data: d.crd,  color: '#d29922', yAxis: 0 }},
        {{ name: 'Cache Write', data: d.cwr,  color: '#9e6a03', yAxis: 0 }},
        {{ name: 'Output',      data: d.out,  color: '#3fb950', yAxis: 0 }},
        {{ name: 'Input (new)', data: d.inp,  color: '#1f6feb', yAxis: 0 }},
        {{ name: 'Cost $', type: 'line', data: d.cost,
           color: '#f78166', yAxis: 1, lineWidth: 2, zIndex: 10 }}
      ],
      credits: {{ enabled: false }},
      exporting: {{ buttons: {{ contextButton: {{
        symbolStroke: '#8b949e', theme: {{ fill: '#161b22' }}
      }} }} }}
    }});
    charts.push(c);
  }}

  /* Render first page immediately, lazy-render the rest on scroll */
  renderPage(0);
  var lazy = document.querySelectorAll('.hc-lazy');
  if ('IntersectionObserver' in window && lazy.length > 1) {{
    var obs = new IntersectionObserver(function (entries) {{
      entries.forEach(function (e) {{
        if (e.isIntersecting) {{
          var pg = +e.target.getAttribute('data-pg');
          if (pg > 0) renderPage(pg);
          obs.unobserve(e.target);
        }}
      }});
    }}, {{ rootMargin: '200px' }});
    for (var i = 1; i < lazy.length; i++) obs.observe(lazy[i]);
  }} else {{
    for (var i = 1; i < DATA.length; i++) renderPage(i);
  }}

  function bindSlider(id, valId, opt) {{
    var el = document.getElementById(id);
    var vEl = document.getElementById(valId);
    el.addEventListener('input', function () {{
      vEl.textContent = el.value + (opt === 'depth' ? '' : '\u00b0');
      charts.forEach(function (c) {{
        var o = c.options.chart.options3d;
        o[opt] = +el.value;
        c.update({{ chart: {{ options3d: o }} }}, true, false, false);
      }});
    }});
  }}
  bindSlider('alpha', 'alpha-val', 'alpha');
  bindSlider('beta',  'beta-val',  'beta');
  bindSlider('depth', 'depth-val', 'depth');
}})();"""

    return f"""\
<div id="chart-container">
  <div class="chart-controls">
    <label>Alpha &nbsp;<input type="range" id="alpha" min="-30" max="30" value="12">
      <span id="alpha-val">12\u00b0</span></label>
    <label style="margin-left:12px">Beta &nbsp;<input type="range" id="beta" min="-30" max="30" value="10">
      <span id="beta-val">10\u00b0</span></label>
    <label style="margin-left:12px">Depth &nbsp;<input type="range" id="depth" min="10" max="120" value="50">
      <span id="depth-val">50</span></label>
  </div>
  {containers_html}
</div>
<script>
{script}
</script>"""


# ---------------------------------------------------------------------------
# Chart library dispatch (vendored, offline, SHA-256 verified)
# ---------------------------------------------------------------------------
#
# The HTML export supports pluggable chart renderers. Each renderer reads
# its JS payload from ``scripts/vendor/charts/<lib>/...`` — no CDN fetch,
# no runtime cache writes, no network access. ``manifest.json`` lists the
# expected SHA-256 per file; the verifier refuses to inline a file whose
# digest doesn't match (defense-in-depth against accidental edits or
# supply-chain tampering).
#
# Current renderers:
#   - "highcharts" — 3D stacked columns (non-commercial license; see LICENSE.txt).
#   - "uplot"      — flat 2D stacked bars + cost line (MIT). Lightest.
#   - "chartjs"    — 2D stacked bar + line combo (MIT). Familiar API.
#   - "none"       — emit the detail page with no chart at all.

# _VENDOR_CHARTS_DIR and _ALLOW_UNVERIFIED_CHARTS are defined in session-metrics.py
# (not here) and accessed at runtime via _sm(). All reads in this module use _sm().


class VendorChartVerificationError(RuntimeError):
    """Raised when a vendored chart asset fails SHA-256 verification or is
    otherwise unavailable, and ``--allow-unverified-charts`` is not set."""


def _chart_verification_failure(msg: str) -> None:
    """Either raise a verification error or degrade to a stderr warning."""
    if _sm()._ALLOW_UNVERIFIED_CHARTS:
        print(f"[warn] {msg} (--allow-unverified-charts: continuing)",
              file=sys.stderr)
        return
    raise VendorChartVerificationError(msg)


@functools.lru_cache(maxsize=1)
def _load_chart_manifest() -> dict:
    """Parse ``vendor/charts/manifest.json``. Returns an empty libraries dict
    if the manifest is missing (keeps the tool usable in degraded mode).

    Cached for the process lifetime — callers (``_read_vendor_files`` and
    ``_maybe_warn_chart_license``) only read from the returned dict.
    """
    mpath = _sm()._VENDOR_CHARTS_DIR / "manifest.json"
    if not mpath.exists():
        return {"libraries": {}}
    try:
        return json.loads(mpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[warn] vendor/charts/manifest.json malformed: {exc}", file=sys.stderr)
        return {"libraries": {}}


def _read_vendor_files(library: str, suffix: str) -> str:
    """Read + concatenate vendor files for ``library`` whose path ends in
    ``suffix`` (``.js`` or ``.css``). Verifies each SHA-256 against the
    manifest before inclusion. On any failure (missing manifest entry,
    missing file, or SHA mismatch) raises :class:`VendorChartVerificationError`
    — fail-closed by default to prevent shipping unverified JS to the
    browser. Set ``--allow-unverified-charts`` to degrade to stderr warnings.
    """
    manifest = _load_chart_manifest()
    lib_entry = manifest.get("libraries", {}).get(library)
    if not lib_entry:
        _chart_verification_failure(
            f"chart library {library!r} not in vendor manifest at "
            f"{_sm()._VENDOR_CHARTS_DIR / 'manifest.json'}"
        )
        return ""
    parts: list[str] = []
    for f in lib_entry.get("files", []):
        if not f["path"].endswith(suffix):
            continue
        path = _sm()._VENDOR_CHARTS_DIR / f["path"]
        if not path.exists():
            _chart_verification_failure(f"vendor file missing: {path}")
            continue
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        expected = f.get("sha256", "")
        if not expected:
            _chart_verification_failure(
                f"vendor manifest entry for {path.name} has no sha256 field"
            )
            continue
        if actual != expected:
            _chart_verification_failure(
                f"SHA-256 mismatch for {path.name}: "
                f"expected {expected[:12]}…, got {actual[:12]}…"
            )
            continue
        parts.append(data.decode("utf-8", errors="replace"))
    sep = ";\n" if suffix == ".js" else "\n"
    return sep.join(parts)


def _read_vendor_js(library: str) -> str:
    """Read + concatenate the JS payload for ``library`` from the vendor tree.
    Thin wrapper over ``_read_vendor_files`` for backward compatibility."""
    return _read_vendor_files(library, ".js")


def _read_vendor_css(library: str) -> str:
    """Read + concatenate the CSS payload for ``library`` from the vendor tree.
    Returns empty string if the library has no CSS files."""
    return _read_vendor_files(library, ".css")


def _hc_scripts() -> str:
    """Return Highcharts JS inlined as a single script block.

    Reads the vendored files from ``scripts/vendor/charts/highcharts/v12/``
    and verifies each SHA-256 against the manifest. No CDN, no network.
    """
    return _read_vendor_js("highcharts")


def _extract_chart_series(all_turns: list[dict]) -> dict:
    """Pull the per-turn series the chart renderers all need.

    Returned keys mirror the JSON blob the body-side IIFE consumes:
    ``cats`` (x-axis labels), ``crd`` / ``cwr`` / ``out`` / ``inp`` (token
    series, stacked bottom-to-top), ``cost`` (USD per turn), ``models``
    (per-bar model name for tooltip headers).
    """
    return {
        "cats":   [t["timestamp_fmt"][5:16] for t in all_turns],
        "inp":    [t["input_tokens"]        for t in all_turns],
        "out":    [t["output_tokens"]       for t in all_turns],
        "crd":    [t["cache_read_tokens"]   for t in all_turns],
        "cwr":    [t["cache_write_tokens"]  for t in all_turns],
        "cost":   [round(t["cost_usd"], 4)  for t in all_turns],
        "models": [t["model"]               for t in all_turns],
    }


def _render_chart_highcharts(all_turns: list[dict],
                             x_title: str = "Turn") -> tuple[str, str]:
    """Highcharts renderer. Returns ``(chart_body_html, head_html)``.

    ``chart_body_html`` is the full ``<div id="chart-container">…</div>`` block
    dropped in the report body; ``head_html`` is the vendored library bundle
    wrapped in a ready-to-inline ``<script>`` tag for ``<head>``.

    ``x_title`` controls the x-axis label and the pagination header
    (e.g. "Turns 1–60 of 126"). Defaults to "Turn" for session/project
    scope; the instance dashboard passes "Day" since each data point
    is a calendar day rather than a per-turn record.
    """
    if not all_turns:
        return ("", "")
    s = _extract_chart_series(all_turns)
    body = _build_chart_html(
        s["cats"], s["crd"], s["cwr"], s["out"], s["inp"], s["cost"], x_title,
        models=s["models"],
    )
    return (body, f"<script>{_hc_scripts()}</script>")


def _build_lib_chart_pages(series: dict, x_title: str) -> tuple[str, str]:
    """Pagination scaffold shared by uPlot and Chart.js renderers.

    Returns ``(containers_html, data_json)``. The renderer wraps these with
    its own per-page render function + IntersectionObserver IIFE.
    Highcharts has its own (richer) builder; this is the lean version.
    """
    n = len(series["cats"])
    slices = [(s, min(s + _CHART_PAGE, n)) for s in range(0, n, _CHART_PAGE)]
    n_pages = len(slices)
    pages_data = [{
        "cats":   series["cats"][s:e],
        "crd":    series["crd"][s:e],
        "cwr":    series["cwr"][s:e],
        "out":    series["out"][s:e],
        "inp":    series["inp"][s:e],
        "cost":   series["cost"][s:e],
        "models": series["models"][s:e],
    } for s, e in slices]
    # Escape ``</`` → ``<\/`` so chart data can't break out of the executable
    # <script> block in the uPlot / Chart.js renderers (v1.80.1; see
    # _build_chart_html for the full rationale).
    data_json = json.dumps(pages_data, separators=(",", ":")).replace("</", "<\\/")

    divs: list[str] = []
    for pg, (s, e) in enumerate(slices):
        label = (
            f'<div class="chart-page-label">{x_title}s {s + 1}\u2013{e} of {n}</div>'
            if n_pages > 1 else ""
        )
        divs.append(f'{label}<div id="chart-pg-{pg}" class="chart-lazy" '
                    f'data-pg="{pg}" style="height:380px;padding:8px"></div>')
    return ("\n".join(divs), data_json)


def _render_chart_uplot(all_turns: list[dict],
                        x_title: str = "Turn") -> tuple[str, str]:
    """uPlot renderer (MIT). Returns ``(body_html, head_html)``.

    uPlot has no built-in stacked-bars API — we pre-compute cumulative
    arrays caller-side so each bar series renders as a full stack from the
    baseline (the bottom-most series is drawn last so it sits on top
    visually).  Cost is a separate line series on a right-hand y-axis.
    Pagination + lazy rendering match the Highcharts renderer.

    ``x_title`` controls the x-series label and the pagination header.
    See :func:`_render_chart_highcharts` for the instance-scope rationale.
    """
    if not all_turns:
        return ("", "")
    series = _extract_chart_series(all_turns)
    containers_html, data_json = _build_lib_chart_pages(series, x_title)

    css = _read_vendor_css("uplot")
    js  = _read_vendor_js("uplot")
    if not js:
        return ("", "")

    head_extra_css = """
      .uplot { width: 100% !important; }
      .uplot, .uplot * { color: #8b949e; }
      .u-title { display: none; }
      .u-legend { background: #161b22; color: #e6edf3; font-size: 11px;
                  border-top: 1px solid #30363d; padding: 6px 8px; }
      .u-legend .u-marker { border-radius: 2px; }
      .u-axis { color: #8b949e; }
      .u-cursor-pt { border-color: var(--accent, #58a6ff) !important; }
    """

    init = f"""\
(function () {{
  var DATA = {data_json};
  var charts = [];
  function renderPage(pg) {{
    var d = DATA[pg];
    var n = d.cats.length;
    var xs = new Array(n);
    for (var i = 0; i < n; i++) xs[i] = i;
    /* Cumulative stacks bottom-to-top: cache_read | + cache_write |
       + output | + input. Drawing the totals as bars renders them as a
       visual stack because the smaller bars overpaint the bigger ones. */
    var s1 = d.crd.slice();
    var s2 = new Array(n), s3 = new Array(n), s4 = new Array(n);
    for (var i = 0; i < n; i++) {{
      s2[i] = s1[i] + d.cwr[i];
      s3[i] = s2[i] + d.out[i];
      s4[i] = s3[i] + d.inp[i];
    }}
    var bars = uPlot.paths.bars({{ size: [0.7, 60] }});
    var el = document.getElementById('chart-pg-' + pg);
    var w  = el.clientWidth || 800;
    var fmtTokens = function (v) {{
      if (v == null) return '';
      return v >= 1000 ? (v / 1000).toFixed(0) + 'k' : ('' + v);
    }};
    var opts = {{
      width: w, height: 380,
      title: '',
      cursor: {{ drag: {{ x: false, y: false }}, points: {{ size: 6 }} }},
      legend: {{ live: true }},
      scales: {{ x: {{ time: false }}, cost: {{ auto: true }} }},
      axes: [
        {{ stroke: '#8b949e', grid: {{ stroke: '#21262d' }},
           values: function (u, ticks) {{ return ticks.map(function (t) {{
             return d.cats[t] || '';
           }}); }},
           rotate: -45, size: 60 }},
        {{ stroke: '#8b949e', grid: {{ stroke: '#21262d' }},
           values: function (u, ticks) {{ return ticks.map(fmtTokens); }} }},
        {{ scale: 'cost', side: 1, stroke: '#d29922', grid: {{ show: false }},
           values: function (u, ticks) {{
             return ticks.map(function (v) {{ return '$' + v.toFixed(4); }});
           }} }},
      ],
      series: [
        {{ label: '{x_title}' }},
        {{ label: 'Input (new)', stroke: '#1f6feb',
           fill: 'rgba(31,111,235,0.85)', paths: bars, points: {{ show: false }},
           value: function (u, v, sIdx, dIdx) {{
             return d.inp[dIdx] != null ? d.inp[dIdx].toLocaleString() : '';
           }} }},
        {{ label: 'Output', stroke: '#3fb950',
           fill: 'rgba(63,185,80,0.85)', paths: bars, points: {{ show: false }},
           value: function (u, v, sIdx, dIdx) {{
             return d.out[dIdx] != null ? d.out[dIdx].toLocaleString() : '';
           }} }},
        {{ label: 'Cache Write', stroke: '#9e6a03',
           fill: 'rgba(158,106,3,0.85)', paths: bars, points: {{ show: false }},
           value: function (u, v, sIdx, dIdx) {{
             return d.cwr[dIdx] != null ? d.cwr[dIdx].toLocaleString() : '';
           }} }},
        {{ label: 'Cache Read', stroke: '#d29922',
           fill: 'rgba(210,153,34,0.85)', paths: bars, points: {{ show: false }},
           value: function (u, v, sIdx, dIdx) {{
             return d.crd[dIdx] != null ? d.crd[dIdx].toLocaleString() : '';
           }} }},
        {{ label: 'Cost $', stroke: '#f78166', width: 2, scale: 'cost',
           points: {{ show: true, size: 4, stroke: '#f78166', fill: '#161b22' }},
           value: function (u, v) {{ return v == null ? '' : '$' + v.toFixed(4); }} }},
      ],
    }};
    /* uPlot wants series rows in the order declared; the bar series are
       drawn back-to-front so the smallest cumulative goes last → visible. */
    var data = [xs, s4, s3, s2, s1, d.cost];
    var u = new uPlot(opts, data, el);
    charts.push(u);
  }}
  renderPage(0);
  var lazy = document.querySelectorAll('.chart-lazy');
  if ('IntersectionObserver' in window && lazy.length > 1) {{
    var obs = new IntersectionObserver(function (entries) {{
      entries.forEach(function (e) {{
        if (e.isIntersecting) {{
          var pg = +e.target.getAttribute('data-pg');
          if (pg > 0) renderPage(pg);
          obs.unobserve(e.target);
        }}
      }});
    }}, {{ rootMargin: '200px' }});
    for (var i = 1; i < lazy.length; i++) obs.observe(lazy[i]);
  }} else {{
    for (var i = 1; i < DATA.length; i++) renderPage(i);
  }}
  window.addEventListener('resize', function () {{
    charts.forEach(function (u) {{
      var el = u.root.parentNode;
      u.setSize({{ width: el.clientWidth || 800, height: 380 }});
    }});
  }});
}})();"""

    body = f"""<div id="chart-container">
{containers_html}
</div>
<script>
{init}
</script>"""

    head_html = (
        f"<style>{css}{head_extra_css}</style>\n"
        f"<script>{js}</script>"
    )
    return (body, head_html)


def _render_chart_chartjs(all_turns: list[dict],
                          x_title: str = "Turn") -> tuple[str, str]:
    """Chart.js v4 renderer (MIT). Returns ``(body_html, head_html)``.

    Mixed bar+line: four ``type: 'bar'`` datasets share ``stack: 'tokens'``
    on the left y-axis (``stacked: true``), one ``type: 'line'`` dataset
    rides on the right y-axis ``y1`` for cost. Pagination + lazy
    rendering match the Highcharts renderer.

    ``x_title`` controls the pagination header text (Chart.js itself has
    no x-axis title configured here; the instance dashboard still needs
    "Days 1–60 of N" instead of the default "Turns 1–60 of N").
    """
    if not all_turns:
        return ("", "")
    series = _extract_chart_series(all_turns)
    containers_html, data_json = _build_lib_chart_pages(series, x_title)

    js = _read_vendor_js("chartjs")
    if not js:
        return ("", "")

    init = f"""\
(function () {{
  var DATA = {data_json};
  Chart.defaults.color = '#8b949e';
  Chart.defaults.borderColor = '#30363d';
  Chart.defaults.font.size = 11;
  function renderPage(pg) {{
    var d = DATA[pg];
    var holder = document.getElementById('chart-pg-' + pg);
    holder.innerHTML = '';
    var canvas = document.createElement('canvas');
    holder.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    new Chart(ctx, {{
      type: 'bar',
      data: {{
        labels: d.cats,
        datasets: [
          {{ label: 'Cache Read',  data: d.crd, backgroundColor: '#d29922',
             stack: 'tokens', yAxisID: 'y', order: 4 }},
          {{ label: 'Cache Write', data: d.cwr, backgroundColor: '#9e6a03',
             stack: 'tokens', yAxisID: 'y', order: 3 }},
          {{ label: 'Output',      data: d.out, backgroundColor: '#3fb950',
             stack: 'tokens', yAxisID: 'y', order: 2 }},
          {{ label: 'Input (new)', data: d.inp, backgroundColor: '#1f6feb',
             stack: 'tokens', yAxisID: 'y', order: 1 }},
          {{ label: 'Cost $', type: 'line', data: d.cost,
             borderColor: '#f78166', backgroundColor: '#f78166',
             borderWidth: 2, pointRadius: 3, yAxisID: 'y1', order: 0 }},
        ]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        scales: {{
          x: {{ stacked: true, ticks: {{ maxRotation: 45, minRotation: 45,
                color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
          y: {{ stacked: true, position: 'left',
                title: {{ display: true, text: 'Tokens', color: '#8b949e' }},
                ticks: {{ color: '#8b949e', callback: function (v) {{
                  return v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v;
                }} }}, grid: {{ color: '#21262d' }} }},
          y1: {{ position: 'right', stacked: false,
                 title: {{ display: true, text: 'Cost (USD)', color: '#d29922' }},
                 ticks: {{ color: '#d29922', callback: function (v) {{
                   return '$' + v.toFixed(4);
                 }} }}, grid: {{ display: false }} }},
        }},
        plugins: {{
          legend: {{ labels: {{ color: '#8b949e', boxWidth: 12 }} }},
          tooltip: {{
            backgroundColor: '#1c2128', titleColor: '#e6edf3',
            bodyColor: '#e6edf3', borderColor: '#30363d', borderWidth: 1,
            callbacks: {{
              afterTitle: function (items) {{
                if (!items.length) return '';
                var m = d.models[items[0].dataIndex];
                return m ? m : '';
              }},
              label: function (ctx) {{
                var v = ctx.parsed.y;
                if (ctx.dataset.yAxisID === 'y1') {{
                  return ctx.dataset.label + ': $' + v.toFixed(4);
                }}
                return ctx.dataset.label + ': ' + v.toLocaleString() + ' tokens';
              }},
            }},
          }},
        }},
      }},
    }});
  }}
  renderPage(0);
  var lazy = document.querySelectorAll('.chart-lazy');
  if ('IntersectionObserver' in window && lazy.length > 1) {{
    var obs = new IntersectionObserver(function (entries) {{
      entries.forEach(function (e) {{
        if (e.isIntersecting) {{
          var pg = +e.target.getAttribute('data-pg');
          if (pg > 0) renderPage(pg);
          obs.unobserve(e.target);
        }}
      }});
    }}, {{ rootMargin: '200px' }});
    for (var i = 1; i < lazy.length; i++) obs.observe(lazy[i]);
  }} else {{
    for (var i = 1; i < DATA.length; i++) renderPage(i);
  }}
}})();"""

    body = f"""<div id="chart-container">
{containers_html}
</div>
<script>
{init}
</script>"""

    head_html = f"<script>{js}</script>"
    return (body, head_html)


def _render_chart_none(all_turns: list[dict],
                       x_title: str = "Turn") -> tuple[str, str]:
    """No-chart renderer. Emits an empty body + empty head — useful when the
    caller wants a minimal detail page with no JS dependencies.

    ``x_title`` accepted for API parity with the other renderers; ignored.
    """
    del all_turns, x_title
    return ("", "")


def _build_cache_trend_sparkline_svg(turns: list[dict],
                                      width: int = 200,
                                      height: int = 24,
                                      window: int = 5) -> str:
    """Inline SVG sparkline of rolling cache hit %% across a session.

    Surfaces mid-session cache degradation that the per-session aggregate
    hides (e.g. a clean run followed by a cache-busting CLAUDE.md edit at
    turn 50). Returns ``""`` when the session has fewer than ``window``
    cache-bearing turns — drawing a 1-2 point line would be visual noise.

    Cheap on the dashboard: no Highcharts dependency, ~200 bytes per
    sparkline. ``width`` / ``height`` / ``window`` defaults are tuned for
    inline display in the timeline session-header row.
    """
    pts: list[float] = []
    event_indices: list[tuple[int, str]] = []
    pt_idx = 0
    _pending_resume = False
    for t in turns or []:
        if t.get("is_resume_marker"):
            _pending_resume = True
            continue
        cr = int(t.get("cache_read_tokens", 0) or 0)
        cw = int(t.get("cache_write_tokens", 0) or 0)
        ip = int(t.get("input_tokens", 0) or 0)
        denom = ip + cr + cw
        if denom <= 0:
            continue
        if _pending_resume:
            event_indices.append((pt_idx, "resume"))
            _pending_resume = False
        if t.get("is_clear_event"):
            event_indices.append((pt_idx, "clear"))
        pts.append(100.0 * cr / denom)
        pt_idx += 1
    if len(pts) < window:
        return ""
    rolling: list[float] = []
    s = sum(pts[:window])
    rolling.append(s / window)
    for i in range(window, len(pts)):
        s += pts[i] - pts[i - window]
        rolling.append(s / window)
    n = len(rolling)
    if n == 1:
        return ""
    coords: list[str] = []
    for i, v in enumerate(rolling):
        x = i * (width - 1) / (n - 1)
        v_clamped = max(0.0, min(100.0, v))
        y = (height - 4) * (1.0 - v_clamped / 100.0) + 2
        coords.append(f"{x:.1f},{y:.1f}")
    last = rolling[-1]
    title = (
        f"Rolling cache hit % over {n} turns "
        f"(window={window}). Last: {last:.1f}%."
    )
    stroke = "#A58BFF" if last >= 80 else ("#FBBF24" if last >= 50 else "#F87171")
    marker_lines = ""
    for ei, etype in event_indices:
        ri = ei - window + 1
        if 0 <= ri < n:
            mx = ri * (width - 1) / (n - 1)
            mc = "#FBBF24" if etype == "clear" else "#A58BFF"
            marker_lines += (
                f'<line x1="{mx:.1f}" y1="0" x2="{mx:.1f}" y2="{height}" '
                f'stroke="{mc}" stroke-width="1" opacity="0.6"/>'
            )
    return (
        f'<svg class="cache-spark" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{title}" style="vertical-align:middle">'
        f'<title>{title}</title>'
        f'{marker_lines}'
        f'<polyline fill="none" stroke="{stroke}" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round" '
        f'points="{" ".join(coords)}"/></svg>'
    )


def _svg_scale(values: list[float], width: int, height: int,
               x_pad: int = 0, y_pad: int = 4,
               max_v: float | None = None
               ) -> tuple[list[tuple[float, float]], float, float]:
    """Coordinate-transform kernel for the static SVG charts (Phase D).

    Maps ``N`` numeric ``values`` onto an SVG canvas of ``width``x``height``,
    returning ``(xy_pairs, x_scale, y_scale)``. Each pair is
    ``(x_pad + i*x_scale, height - y_pad - v/max_v*(height-2*y_pad))`` so y grows
    upward (SVG's origin is top-left). Every coordinate is rounded to 2 dp so the
    emitted string is byte-stable across runs and platforms — no float drift, no
    timestamps, no dict iteration.

    ``max_v`` overrides the per-call maximum. Stacked charts pass a shared
    ``max_v`` so every layer is plotted on one common y-scale; single-series
    callers leave it ``None`` to auto-scale to their own peak.

    Returns ``([], 0.0, 0.0)`` when ``values`` is empty or the effective maximum
    is non-positive (nothing meaningful to plot).
    """
    n = len(values)
    if n == 0:
        return ([], 0.0, 0.0)
    m = max(values) if max_v is None else max_v
    if m <= 0:
        return ([], 0.0, 0.0)
    plot_h = height - 2 * y_pad
    x_scale = (width - 2 * x_pad) / (n - 1) if n > 1 else 0.0
    y_scale = plot_h / m
    pairs = [
        (round(x_pad + i * x_scale, 2),
         round(height - y_pad - (v / m) * plot_h, 2))
        for i, v in enumerate(values)
    ]
    return (pairs, round(x_scale, 6), round(y_scale, 6))


def _build_cache_efficiency_svg(totals: dict, width: int = 480,
                                height: int = 32) -> str:
    """4-segment proportional token bar (Phase D consumer of the totals dict).

    Segments — cache-read / cache-write / new-input / output — with pixel widths
    proportional to token counts. Token counts are integers; only the final
    per-segment pixel width uses float division, each rounded to 2 dp. The
    denominator is the local sum of the four buckets (identical to
    ``totals['total']`` today, but recomputed here so a future fifth token type
    can't silently break the proportion). Colours are theme CSS vars only — no
    hardcoded surface greys. Returns ``''`` when there are no tokens.
    """
    cr = int(totals.get("cache_read", 0) or 0)
    cw = int(totals.get("cache_write", 0) or 0)
    ip = int(totals.get("input", 0) or 0)
    op = int(totals.get("output", 0) or 0)
    total = cr + cw + ip + op
    if total <= 0:
        return ""
    segs = (
        ("cache-read",  cr, "var(--accent)"),
        ("cache-write", cw, "var(--accent-soft)"),
        ("new-input",   ip, "var(--fg-dim)"),
        ("output",      op, "var(--border)"),
    )
    rects: list[str] = []
    x = 0.0
    for label, tok, colour in segs:
        if tok <= 0:
            continue
        w = round(tok / total * width, 2)
        rects.append(
            f'<rect x="{round(x, 2)}" y="0" width="{w}" height="{height}" '
            f'fill="{colour}"><title>{label}: {tok:,} tokens '
            f'({tok / total * 100:.1f}%)</title></rect>'
        )
        x = round(x + w, 2)
    return (
        f'<svg class="cache-eff-bar" width="100%" height="{height}" '
        f'viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'role="img" aria-label="Token composition bar">{"".join(rects)}</svg>'
    )


CHART_RENDERERS = {
    "highcharts": _render_chart_highcharts,
    "uplot":      _render_chart_uplot,
    "chartjs":    _render_chart_chartjs,
    "none":       _render_chart_none,
}

