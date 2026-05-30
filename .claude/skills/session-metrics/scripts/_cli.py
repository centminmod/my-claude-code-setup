"""Session discovery, arg-parsing, and CLI entry point for session-metrics."""
import argparse
import contextlib
import importlib.util
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


def _sm():
    """Return the session_metrics module (deferred — fully loaded by call time)."""
    return sys.modules["session_metrics"]


# ---------------------------------------------------------------------------
# Session / project discovery
# ---------------------------------------------------------------------------

# Accept any non-empty filename-safe token, length <= 64.  Claude Code's
# identifier scheme may evolve — don't hard-code UUID format.
_SESSION_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
# Slug preserves the leading "-" Claude Code uses for cwd-derived paths.
_SLUG_RE    = re.compile(r'^-?[A-Za-z0-9_-]+$')


def _validate_session_id(value: str) -> str:
    if not _SESSION_RE.match(value or ""):
        raise argparse.ArgumentTypeError(
            f"invalid session id: {value!r} "
            f"(expected filename-safe token, got chars outside [A-Za-z0-9._-] or length > 64)"
        )
    return value


def _validate_slug(value: str) -> str:
    if not _SLUG_RE.match(value or ""):
        raise argparse.ArgumentTypeError(
            f"invalid project slug: {value!r} "
            f"(expected /-safe token matching {_SLUG_RE.pattern})"
        )
    return value


# Module-level override set by --projects-dir (instance mode). Takes
# precedence over $CLAUDE_PROJECTS_DIR so users running multiple Claude
# Code installs (e.g. one at ~/.claude, another under $CLAUDE_CONFIG_DIR)
# can point the tool at whichever projects dir they want in a single run.
# Canonical attribute lives on the orchestrator (session-metrics.py); reads
# and writes here go through ``_sm()._PROJECTS_DIR_OVERRIDE``.


def _projects_dir() -> Path:
    if _sm()._PROJECTS_DIR_OVERRIDE is not None:
        return _sm()._PROJECTS_DIR_OVERRIDE
    env = os.environ.get("CLAUDE_PROJECTS_DIR")
    if env:
        p = Path(env).expanduser().resolve()
        if not p.is_dir():
            print(f"[error] CLAUDE_PROJECTS_DIR={env!r} is not a directory", file=sys.stderr)
            sys.exit(1)
        return p
    return Path.home() / ".claude" / "projects"


def _ensure_within_projects(path: Path) -> Path:
    """Resolve ``path`` and assert it lives under the projects directory.

    Catches path-traversal (``..``), symlink escapes, and absolute-path
    injection via the slug/session-id arguments.
    """
    root = _projects_dir().resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        print(f"[error] refusing to read outside {root}: {resolved}", file=sys.stderr)
        sys.exit(1)
    return resolved


def _cwd_to_slug(cwd: str | None = None) -> str:
    # Claude Code writes JSONLs to ~/.claude/projects/<slug>/ where <slug>
    # is the cwd with every non-alphanumeric character (except `-`) mapped
    # to `-`. Runs of replaceable chars are preserved as consecutive `-`s
    # — e.g. `/Users/x/.claude-mem` → `-Users-x--claude-mem`. An earlier
    # version only replaced `/`, which drifted from Claude Code whenever
    # the path carried `_`, `.`, spaces, or apostrophes (e.g. $TMPDIR
    # paths under /private/var/folders/.../xxx_yyy/) and broke
    # compare-run extras that looked up session JSONLs via this slug.
    return re.sub(r"[^A-Za-z0-9-]", "-", cwd or os.getcwd())


def _find_jsonl_files(slug: str, include_subagents: bool = False) -> list[Path]:
    project_dir = _projects_dir() / slug
    if not project_dir.exists():
        return []
    files = [p for p in project_dir.glob("*.jsonl") if p.is_file()]
    if include_subagents:
        files += list(project_dir.glob("*/subagents/*.jsonl"))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _list_all_projects() -> list[tuple[str, Path]]:
    """Return ``[(slug, project_dir), ...]`` for every project under the
    projects directory that contains at least one ``.jsonl`` session file.

    Scans ``_projects_dir()`` (which honours ``--projects-dir`` override and
    ``CLAUDE_PROJECTS_DIR`` env var). Filters:
      - only immediate subdirectories whose name passes ``_SLUG_RE``
      - skips hidden entries (names starting with ``.``)
      - skips directories with zero session JSONLs so the instance dashboard
        doesn't list empty shells

    Sorted by most-recent-session mtime descending — most active projects
    surface first. Used exclusively by instance mode; single-session and
    project-cost paths keep their existing narrower helpers.
    """
    root = _projects_dir()
    if not root.is_dir():
        return []
    out: list[tuple[str, Path, float]] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith(".") or not _SLUG_RE.match(name):
            continue
        jsonls = [p for p in entry.glob("*.jsonl") if p.is_file()]
        if not jsonls:
            continue
        newest = max(p.stat().st_mtime for p in jsonls)
        out.append((name, entry, newest))
    out.sort(key=lambda t: t[2], reverse=True)
    return [(slug, path) for slug, path, _ in out]


def _slug_to_friendly_path(slug: str) -> str:
    """Best-effort reverse of ``_cwd_to_slug`` for display purposes.

    Claude Code's slug encoding is lossy (``/``, ``_``, ``.``, spaces → ``-``),
    so we can't recover the original path exactly. Heuristic: leading ``-``
    becomes ``/`` (absolute path marker), and we check whether the guessed
    path exists on disk and use it if so; otherwise fall back to inserting
    ``/`` at every single hyphen while collapsing ``--`` back to ``-`` —
    the common case where the cwd had no underscores/dots/spaces. If nothing
    matches, return the slug unchanged so users at least see the raw string.
    """
    if not slug:
        return slug
    if slug.startswith("-"):
        guess = "/" + slug[1:].replace("-", "/")
        collapsed = re.sub(r"/+", "/", guess)
        if Path(collapsed).exists():
            return collapsed
        parts = re.split(r"-+", slug[1:])
        guess2 = "/" + "/".join(parts)
        if Path(guess2).exists():
            return guess2
        return collapsed
    return slug


def _resolve_session(args) -> tuple[Path, str]:
    slug: str = args.slug or _env_slug() or _cwd_to_slug()
    _validate_slug(slug)
    session_id: str | None = args.session or _env_session_id()

    if session_id:
        candidate = _ensure_within_projects(_projects_dir() / slug / f"{session_id}.jsonl")
        if candidate.exists():
            return candidate, slug
        for p in _projects_dir().rglob(f"{session_id}.jsonl"):
            return _ensure_within_projects(p), p.parent.name
        print(f"[error] Session {session_id!r} not found", file=sys.stderr)
        sys.exit(1)

    files = _find_jsonl_files(slug)
    if not files:
        print(f"[error] No sessions found for slug: {slug}", file=sys.stderr)
        print("        Try --slug=<slug> or set CLAUDE_PROJECT_SLUG", file=sys.stderr)
        sys.exit(1)
    return files[0], slug


def _env_validated(env_key: str, validator) -> str | None:
    """Read ``env_key`` and run it through ``validator``.

    Returns the validated value, ``None`` if the env var is unset, or
    exits 1 with an `[error] <KEY>: <msg>` line on validation failure.
    """
    v = os.environ.get(env_key)
    if v is None:
        return None
    try:
        return validator(v)
    except argparse.ArgumentTypeError as exc:
        print(f"[error] {env_key}: {exc}", file=sys.stderr)
        sys.exit(1)


def _env_slug() -> str | None:
    return _env_validated("CLAUDE_PROJECT_SLUG", _validate_slug)


def _env_session_id() -> str | None:
    return _env_validated("CLAUDE_SESSION_ID", _validate_session_id)


def _list_sessions(slug: str) -> None:
    files = _find_jsonl_files(slug)
    if not files:
        print(f"No sessions found for slug: {slug}")
        return
    print(f"Sessions for {slug}:")
    print(f"  {'Session UUID':<40} {'Modified':<20} {'Size':>8}")
    print("  " + "-" * 72)
    for p in files:
        stat = p.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {p.stem:<40} {mtime:<20} {stat.st_size / 1024:>6.1f}K")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Tally Claude Code session token usage and cost estimates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--session", "-s", metavar="UUID", type=_validate_session_id,
                   help="Session UUID to analyse. Also reads $CLAUDE_SESSION_ID.")
    p.add_argument("--slug", metavar="SLUG", type=_validate_slug,
                   help="Project slug (use --slug=<val> when value starts with '-'). "
                        "Also reads $CLAUDE_PROJECT_SLUG.")
    p.add_argument("--list", "-l", action="store_true",
                   help="List available sessions for this project and exit.")
    p.add_argument("--project-cost", "-p", action="store_true",
                   help="Show all sessions in chronological order with per-session "
                        "subtotals and a grand project total.")
    p.add_argument("--all-projects", action="store_true",
                   help="Instance-wide dashboard: aggregate every project under the "
                        "projects directory into one report. Writes HTML/MD/CSV/JSON "
                        "and (unless --no-project-drilldown) a per-project HTML "
                        "drilldown for each project into a dated subfolder under "
                        "exports/session-metrics/instance/.")
    p.add_argument("--no-project-drilldown", action="store_true",
                   help="With --all-projects: skip the per-project HTML drilldown "
                        "pass. Fast path for CI / quick-glance runs. The instance "
                        "HTML still renders, but project rows are plain text "
                        "without hyperlinks.")
    p.add_argument("--projects-dir", metavar="PATH",
                   help="Override the Claude Code projects directory (normally "
                        "~/.claude/projects or $CLAUDE_PROJECTS_DIR). Highest "
                        "precedence. Makes it trivial to script multi-instance "
                        "dashboards: run --all-projects once per path.")
    p.add_argument("--cache-dir", metavar="PATH",
                   help="Override the parse-cache directory (normally "
                        "~/.cache/session-metrics/parse or "
                        "$CLAUDE_SESSION_METRICS_CACHE_DIR). Highest "
                        "precedence. Useful for CI / shared boxes / ephemeral "
                        "envs where ~/.cache is not writable or shared.")
    p.add_argument("--export-dir", metavar="PATH",
                   help="Override the directory exports are written to "
                        "(normally <cwd>/exports/session-metrics or "
                        "$CLAUDE_SESSION_METRICS_EXPORT_DIR). Highest "
                        "precedence. Per-project drilldowns and instance "
                        "dashboards land in dated subfolders under this root.")
    p.add_argument("--output", "-o", nargs="+", metavar="FMT",
                   choices=["text", "json", "csv", "md", "html"],
                   help="Export formats in addition to stdout text. "
                        "One or more of: json csv md html. "
                        "Written to exports/session-metrics/ in the project root.")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="Suppress the per-turn timeline on stdout, printing "
                        "only the legend, scope header, grand-total subtotal, "
                        "and footer (plus the [export] path lines). Keeps "
                        "stdout small on large session/project exports so the "
                        "export paths aren't buried under an overflow-sized "
                        "dump. The full per-turn detail still lands in the "
                        "written HTML/JSON. Session and project scopes only.")
    p.add_argument("--include-subagents", action=argparse.BooleanOptionalAction,
                   default=True,
                   help="Tally spawned subagent JSONL files (default: on). "
                        "Pass --no-include-subagents to skip for faster runs.")
    p.add_argument("--include-workflows", action=argparse.BooleanOptionalAction,
                   default=True,
                   help="Tally dynamic-workflow agent transcripts under "
                        "subagents/workflows/<runId>/ (default: on). These can "
                        "fan out to 100s of agents and dominate cost under "
                        "ultracode. Requires --include-subagents. Pass "
                        "--no-include-workflows to skip the extra parse IO.")
    p.add_argument("--no-workflow-detail", action="store_true",
                   help="Suppress the auto-emitted *_workflows.html/.md "
                        "companion deep-dive when an export contains dynamic "
                        "workflows. The summary table still renders inline.")
    p.add_argument("--task-companion-nav", action="store_true",
                   help="Render a 'Tasks' nav button on the dashboard/detail "
                        "pages pointing to the deterministic <stem>_tasks.html. "
                        "Set by the task-breakdown flow, which generates that "
                        "companion right after the export; without that "
                        "follow-up the link would dangle, so it is off by "
                        "default for raw-script runs.")
    p.add_argument("--cache-break-threshold", type=int,
                   default=_sm()._CACHE_BREAK_DEFAULT_THRESHOLD, metavar="TOKENS",
                   help=(f"Turns whose input + cache_creation exceed TOKENS are "
                         f"flagged as cache-break events (default: "
                         f"{_sm()._CACHE_BREAK_DEFAULT_THRESHOLD:,}). Matches Anthropic "
                         f"session-report's convention."))
    p.add_argument("--no-subagent-attribution", action="store_true",
                   help="Disable Phase-B subagent → parent-prompt token "
                        "attribution. By default, subagent token usage rolls "
                        "up onto the user prompt that spawned the subagent "
                        "chain via additional ``attributed_subagent_*`` "
                        "fields (no double-counting).")
    p.add_argument("--sort-prompts-by", choices=["total", "self"],
                   default=None, metavar="MODE",
                   help="How to rank top-prompts: 'total' (parent + attributed "
                        "subagent cost — bubbles cheap prompts that spawned "
                        "expensive subagents) or 'self' (parent only — pre-"
                        "Phase-B behaviour). Default: 'total' for HTML/MD "
                        "outputs, 'self' for CSV/JSON to keep machine "
                        "consumers stable.")
    p.add_argument("--tz", metavar="IANA",
                   help="IANA timezone for time-of-day bucketing "
                        "(e.g. 'America/Los_Angeles', 'Australia/Brisbane'). "
                        "Defaults to system local timezone.")
    p.add_argument("--utc-offset", type=float, metavar="H",
                   help="Fixed UTC offset in hours for time-of-day bucketing "
                        "(e.g. -8, 5.5). DST-naive; use --tz for DST-aware.")
    p.add_argument("--peak-hours", type=_sm()._parse_peak_hours, metavar="H-H",
                   help="Overlay a translucent band on the hour-of-day chart "
                        "for the given hour range (e.g. '5-11'). Community-reported; "
                        "not an official Anthropic SLA.")
    p.add_argument("--peak-tz", metavar="IANA",
                   help="IANA tz the peak hours are defined in (default: "
                        "'America/Los_Angeles'). Only used when --peak-hours is set.")
    p.add_argument("--single-page", action="store_true",
                   help="HTML export: emit a single self-contained file instead "
                        "of the default 2-page split (dashboard + detail).")
    p.add_argument("--no-cache", action="store_true",
                   help="Skip the parse cache at ~/.cache/session-metrics/parse/ "
                        "and always re-parse JSONL from scratch.")
    p.add_argument("--no-self-cost", action="store_true",
                   help="Suppress the self-cost meta-metric (skill's own "
                        "running-total cost in this session). Drops the "
                        "stderr [self-cost] summary line, the HTML KPI "
                        "card, and the JSON `self_cost` top-level key. "
                        "Only meaningful at session and project scope; "
                        "instance scope (--all-projects) does not compute "
                        "self-cost.")
    p.add_argument("--export-share-safe", action="store_true",
                   help="One-flag pre-share gesture for exports published "
                        "to articles, gists, or shared folders. Implies "
                        "--redact-user-prompts and --no-self-cost, and "
                        "chmods every written export file to 0600 "
                        "(rw-------) immediately after the write. "
                        "Caveat: full prompt-text redaction only applies "
                        "to JSON exports and compare HTML — HTML / MD / "
                        "CSV / text exports are still chmod'd but contain "
                        "verbatim prompt text. For maximum redaction "
                        "before publishing, prefer --output json. "
                        "No-op for instance JSON (no per-turn records).")
    p.add_argument("--chart-lib", metavar="LIB",
                   choices=sorted(_sm().CHART_RENDERERS.keys()),
                   default="highcharts",
                   help="Chart renderer for HTML export. One of: "
                        f"{', '.join(sorted(_sm().CHART_RENDERERS.keys()))}. "
                        "Default: highcharts (vendored, non-commercial). "
                        "Alternatives: uplot/chartjs (MIT). "
                        "Use 'none' for a no-JS detail page.")
    p.add_argument("--allow-unverified-charts", action="store_true",
                   help="Downgrade vendor-chart SHA-256 verification failures "
                        "(missing manifest entry, missing file, hash mismatch) "
                        "from hard errors to stderr warnings. Default: fail "
                        "loudly so tampered or corrupted installs are caught.")
    p.add_argument("--idle-gap-minutes", type=int, default=10, metavar="N",
                   help="HTML: insert an idle-gap divider row when consecutive "
                        "turns are separated by more than N wall-clock minutes. "
                        "0 disables. Default: 10.")
    p.add_argument("--plan-cost", type=float, metavar="USD", default=None,
                   help="Flat-rate plan price (e.g. Claude Pro / Max "
                        "subscription) used to compute the plan-leverage KPI "
                        "card on the HTML dashboard: API-equivalent cost ÷ "
                        "this number. Card auto-hides when unset. Also "
                        "honours $SESSION_METRICS_PLAN_COST as a fallback so "
                        "the value can persist across runs without being "
                        "retyped.")
    p.add_argument("--evidence", action="store_true",
                   help="When emitting JSON (via --output json), also write "
                        "an sha256 sidecar (<file>.json.sha256) plus a "
                        "<file>.json.provenance.json with skill version, "
                        "host platform, generation timestamp, and the JSON "
                        "size in bytes. Lets a third party verify a "
                        "published report wasn't massaged after the fact. "
                        "Implies --output json — the JSON file is added to "
                        "the export list automatically.")
    # --- Invariants (CI mode) ----------------------------------------------
    p.add_argument("--invariants", action="store_true",
                   help="CI-friendly check mode. After the report is built, "
                        "evaluate metric-contract predicates (cache hit %, "
                        "cost per turn, sub-agent turn share, 1h cache "
                        "share, tool calls per turn) and exit with code 4 "
                        "if any predicate is violated. Pair with --output to "
                        "still emit the dashboard alongside the gate. "
                        "Per-predicate threshold flags below override the "
                        "hard-coded defaults; set the relevant flag to a "
                        "sentinel (-1 for *_min, 0 for *_max) to skip an "
                        "individual predicate.")
    p.add_argument("--invariants-cache-hit-min", type=float, default=None,
                   metavar="PCT",
                   help="Minimum cache_hit_pct allowed (default 90.0). "
                        "Pass -1 to skip this predicate.")
    p.add_argument("--invariants-cost-per-turn-max", type=float, default=None,
                   metavar="USD",
                   help="Maximum cost (USD) per turn allowed (default 0.50). "
                        "Pass 0 to skip this predicate.")
    p.add_argument("--invariants-subagent-turn-share-min", type=float,
                   default=None, metavar="PCT",
                   help="Minimum sub-agent turn-share %% (default 0 — disabled. "
                        "Pass a positive value to enforce, e.g. 50).")
    p.add_argument("--invariants-cache-1h-share-max", type=float, default=None,
                   metavar="PCT",
                   help="Maximum %% of cache_write tokens written at the 1h "
                        "TTL tier (default 50.0). Pass 0 to skip.")
    p.add_argument("--invariants-tool-calls-per-turn-max", type=float,
                   default=None, metavar="N",
                   help="Maximum average tool calls per turn (default 5.0). "
                        "Pass 0 to skip.")
    p.add_argument("--strict-tz", action="store_true",
                   help="When --tz / --peak-tz cannot be resolved (e.g. on "
                        "Windows without the 'tzdata' pip package), raise "
                        "instead of warning and falling back to UTC. Default: "
                        "warn and fall back so reports still render. See "
                        "references/platform-notes.md.")
    # --- Compare-mode flags ------------------------------------------------
    # ``--compare`` is the single entrypoint: any other compare-mode flag is
    # a no-op without it. Kept out of the ``--project-cost`` / single-session
    # code paths so natural-language prompts ("session cost?") never fall
    # into this branch — dispatch only happens when the user explicitly
    # passes two specifiers via ``--compare``.
    # The four primary-mode flags are mutually exclusive at the CLI: passing
    # two of them together is caught here rather than silently last-wins.
    _mode = p.add_mutually_exclusive_group()
    _mode.add_argument("--compare", nargs=2, metavar=("A", "B"),
                   help="Run a model-compare report over two sessions. Each "
                        "arg may be a .jsonl path, a session UUID, or a "
                        "'last-<family>' / 'all-<family>' magic token. "
                        "Supports Mode 1 (controlled session pair) and "
                        "Mode 2 (observational project aggregate). "
                        "See references/model-compare.md.")
    p.add_argument("--pair-by", choices=["fingerprint", "ordinal"],
                   default="fingerprint",
                   help="Turn-pairing strategy for --compare. 'fingerprint' "
                        "(default) hashes the first 200 chars of each user "
                        "prompt; 'ordinal' pairs by turn index.")
    p.add_argument("--compare-min-turns", type=int, default=5, metavar="N",
                   help="Minimum user-prompt turns required for a 'last-<family>' "
                        "resolver match. Default 5; lower when deliberately "
                        "comparing short sessions.")
    p.add_argument("--compare-scope", choices=["auto", "session", "project"],
                   default="auto",
                   help="Force a compare-mode scope. 'auto' (default) picks "
                        "'controlled' for session pairs and 'observational' "
                        "for project aggregates. 'session' refuses "
                        "'all-<family>' args. 'project' forces observational "
                        "mode even when both args are single sessions.")
    p.add_argument("--yes", "-y", action="store_true",
                   help="Auto-accept confirmation prompts for expensive "
                        "compare paths (Phase 3: 'all-<family>' rollups, "
                        "count-tokens API mode, multi-trial runs). Accepted "
                        "now for CLI-shape stability.")
    # --- Compare capture-protocol helper (Phase 4) -----------------------
    _mode.add_argument("--compare-prep", nargs="*", metavar="MODEL",
                   default=None,
                   help="Emit the capture protocol + canonical prompt suite "
                        "to stdout. Takes 0-2 positional model IDs; defaults "
                        "to 'claude-opus-4-6 claude-opus-4-7'. Pipe to a file "
                        "for easy copy-paste into two fresh Claude Code "
                        "sessions.")
    p.add_argument("--compare-prompts", metavar="DIR",
                   help="Override the compare-suite prompt directory (default: "
                        "references/model-compare/prompts next to this script). "
                        "Used by --compare for predicate eval and by "
                        "--compare-prep for the prompt list.")
    p.add_argument("--compare-list-prompts", action="store_true",
                   help="Print which prompts will run on the next --compare-run "
                        "(built-in suite + any user extras from "
                        "~/.session-metrics/prompts/) and the total inference-"
                        "call count. No inference is performed. Respects "
                        "--compare-prompts if given.")
    p.add_argument("--compare-add-prompt", metavar="TEXT",
                   help="Add a custom prompt to ~/.session-metrics/prompts/ and "
                        "print the file path and remove command. The prompt runs "
                        "automatically on every subsequent --compare-run with no "
                        "flags required. Supports plain-text prompts — no YAML "
                        "or predicate needed.")
    p.add_argument("--compare-remove-prompt", metavar="NAME",
                   help="Remove a user prompt from ~/.session-metrics/prompts/ "
                        "by its name (as shown by --compare-list-prompts). "
                        "Cannot remove built-in prompts.")
    p.add_argument("--allow-suite-mismatch", action="store_true",
                   help="Proceed with a --compare even when the two sessions "
                        "ran different compare-suite versions. Without this "
                        "flag the compare refuses (ratios would conflate "
                        "suite shift with model shift).")
    p.add_argument("--compare-effort", nargs="*", metavar="LEVEL",
                   default=None,
                   help="Annotate the compare report with the reasoning "
                        "effort level each side was captured at. Purely "
                        "cosmetic — does not re-run anything — this flag "
                        "surfaces the effort used during capture on the "
                        "text, MD, CSV, HTML, and analysis.md outputs. "
                        "Takes 0, 1, or 2 positional levels from "
                        "{low, medium, high, xhigh, max}. With 1 value "
                        "both sides share that label; with 2 values the "
                        "first applies to side A, the second to side B. "
                        "--compare-run already infers this from "
                        "--compare-run-effort, so you rarely need to "
                        "pass this flag manually unless you're running "
                        "--compare on JSONLs captured outside the "
                        "orchestrator.")
    # --- Phase 6 / 7 — HTML compare + Insights card ----------------------
    p.add_argument("--redact-user-prompts", action="store_true",
                   help="Replace freeform user-prompt and assistant-reply "
                        "text with '[redacted]' so reports are safe to "
                        "share. Applies to: compare HTML "
                        "(prompt fingerprints; sentinel-tagged suite "
                        "prompts stay visible) and JSON exports of "
                        "single-session and project reports "
                        "(prompt_text / prompt_snippet / assistant_text / "
                        "assistant_snippet on every turn). Tool inputs, "
                        "slash-command names, and structured cost / token "
                        "fields stay visible. No-op for instance-scope "
                        "JSON, which carries no per-turn records.")
    p.add_argument("--no-model-compare-insight", action="store_true",
                   help="Suppress the Model-compare insight card on the "
                        "single-session / project dashboards. Use when the "
                        "hint is noisy (e.g. a project with many historical "
                        "families but no interest in running a benchmark).")
    # --- Phase 8 — count_tokens API mode --------------------------------
    _mode.add_argument("--count-tokens-only", action="store_true",
                   help="Compare input-token counts between two models using "
                        "the /v1/messages/count_tokens API — no inference, no "
                        "cost (other than request rate). Requires "
                        "ANTHROPIC_API_KEY. Pair with --compare-models to "
                        "choose the pair (defaults: claude-opus-4-6 vs "
                        "claude-opus-4-7). Output tokens and total cost are "
                        "NOT measured — run --compare for that.")
    p.add_argument("--compare-models", nargs="*", metavar="MODEL",
                   default=None,
                   help="Model pair for --count-tokens-only. Takes 0-2 "
                        "positional model IDs; defaults to 'claude-opus-4-6 "
                        "claude-opus-4-7'. A single model is accepted for "
                        "input-token measurement without ratios.")
    # --- Task-breakdown companion renderer -------------------------------
    _mode.add_argument("--render-tasks", nargs=2,
                   metavar=("EXPORT_JSON", "GROUPING_JSON"),
                   help="Render the standalone Tasks companion page "
                        "(*_tasks.html + *_tasks.md) from a session-metrics "
                        "JSON export and a Claude-authored grouping.json "
                        "(schema: {schema_version, tasks:[{title, verdict, "
                        "rationale, request_unit_ids:[...]}]}). All cost/turn "
                        "figures are summed from the export's request_units — "
                        "the grouping only assigns requests to tasks. Used by "
                        "the task-breakdown skill; writes next to the export "
                        "(or --export-dir).")
    # --- Phase 10 — Automated headless capture ---------------------------
    _mode.add_argument("--compare-run", nargs="*", metavar="MODEL",
                   default=None,
                   help="Fully automated compare: spawns two 'claude -p' "
                        "(headless) sessions, feeds each the canonical "
                        "10-prompt suite, then runs --compare on the result. "
                        "Takes 0-2 positional model IDs; defaults to "
                        "'claude-opus-4-6[1m] claude-opus-4-7[1m]' because "
                        "that matches Claude Code's shipping default (1M-"
                        "context Opus). Pass 'claude-opus-4-6 claude-opus-4-7' "
                        "to compare the 200k-context variants instead; mixed "
                        "tiers are accepted and fire the existing context-"
                        "tier-mismatch advisory on the report. Runs 2 × N "
                        "inference calls against your subscription quota — "
                        "confirmation gate requires --yes on non-TTY.")
    p.add_argument("--compare-run-scratch-dir", metavar="DIR", default=None,
                   help="Scratch directory for --compare-run captures. "
                        "Defaults to a fresh mkdtemp under $TMPDIR. The "
                        "directory becomes the cwd for every 'claude -p' "
                        "subprocess, which determines the project slug "
                        "Claude Code writes session JSONLs under.")
    p.add_argument("--compare-run-allowed-tools", metavar="TOOLS",
                   default=None,
                   help="--allowedTools value passed to each 'claude -p' "
                        "subprocess in --compare-run. Default: "
                        "'Bash,Read,Write,Edit,Glob,Grep'. Identical on both "
                        "sides so the tool-call ratio stays comparable.")
    p.add_argument("--compare-run-permission-mode", metavar="MODE",
                   default=None,
                   help="--permission-mode value for every --compare-run "
                        "subprocess (default: 'bypassPermissions' so the "
                        "headless calls don't stall waiting for human "
                        "approval). Pass an empty string to omit the flag.")
    p.add_argument("--compare-run-max-budget-usd", type=float, default=None,
                   metavar="USD",
                   help="Per-subprocess --max-budget-usd ceiling for "
                        "--compare-run. Not set by default. Threaded to each "
                        "'claude -p' invocation unchanged.")
    p.add_argument("--compare-run-per-call-timeout", type=float, default=None,
                   metavar="SECONDS",
                   help="Wall-clock timeout for each 'claude -p' subprocess "
                        "in --compare-run. Default 900s (15 min); the "
                        "tool-heavy prompt is the usual slowest.")
    p.add_argument("--compare-run-effort", nargs="*", metavar="LEVEL",
                   default=None,
                   help="Reasoning effort level threaded as 'claude -p "
                        "--effort <level>' to each --compare-run subprocess. "
                        "Takes 0, 1, or 2 positional levels from "
                        "{low, medium, high, xhigh, max}. With 0 (flag "
                        "absent or given with no arguments) the flag is "
                        "omitted entirely, so each model uses Claude Code's "
                        "per-model default (opus-4-6 → high, opus-4-7 → "
                        "xhigh). With 1 value both sides pin to that level. "
                        "With 2 values the first applies to side A, the "
                        "second to side B. Useful when you want to hold "
                        "effort constant across a version comparison "
                        "instead of letting each model fall back to its own "
                        "default.")
    p.add_argument("--no-compare-run-extras", action="store_true",
                   help="Skip the per-session HTML/JSON dashboards and the "
                        "analysis.md companion that --compare-run normally "
                        "emits alongside the compare report. Extras only fire "
                        "when --compare-run is combined with --output (the "
                        "text-only stdout path stays file-free regardless). "
                        "Use this flag to restore the pre-v1.7.0 minimal "
                        "single-artefact output.")
    p.add_argument("--compare-run-prompt-steering", metavar="VARIANT",
                   default=None,
                   help="Wrap each of the 10 canonical prompts with prompt-"
                        "steering text before feeding them to 'claude -p'. "
                        "VARIANT must be one of: concise, think-step-by-step, "
                        "ultrathink, no-tools. Applied symmetrically to both "
                        "sides so the A/B comparison stays clean. Default: "
                        "unset (no wrapper, identical to baseline behaviour). "
                        "IFEval pass rates may differ from baseline under "
                        "steering by design — predicate breakage is the "
                        "measurement, not a regression. For multi-variant "
                        "sweeps with auto-rendered comparison articles use "
                        "the benchmark-effort-prompt skill instead.")
    p.add_argument("--compare-run-prompt-steering-position",
                   metavar="POSITION", default="prefix",
                   choices=["prefix", "append", "both"],
                   help="Where to inject the steering text relative to the "
                        "prompt body when --compare-run-prompt-steering is "
                        "set. 'prefix' prepends; 'append' appends; 'both' "
                        "sandwiches the prompt between the steering prefix "
                        "and suffix. Default: prefix. Ignored when "
                        "--compare-run-prompt-steering is absent.")
    return p


def _maybe_warn_chart_license(chart_lib: str, formats: list[str]) -> None:
    """Surface non-commercial licensing notice when HTML is exported with
    Highcharts. Silent for ``none`` or when the user isn't exporting HTML."""
    if "html" not in formats:
        return
    manifest = _sm()._load_chart_manifest()
    entry = manifest.get("libraries", {}).get(chart_lib, {})
    if entry.get("license", "").startswith("non-commercial"):
        print(f"[info] Chart library '{chart_lib}' is under a "
              f"{entry['license']} license. Commercial distribution of the "
              f"generated HTML may require a paid upstream license. Pass "
              f"--chart-lib none to opt out.", file=sys.stderr)


def _load_compare_module():
    """Lazy-load the sibling ``session_metrics_compare`` module.

    Split out of ``main()`` so the import cost is paid only when the
    user actually runs compare mode — everyday single-session reports
    don't touch it. Also registers this script as ``session_metrics``
    in ``sys.modules`` before the compare module executes, because the
    compare module's one-way coupling helper (``_main()``) looks up
    that name. When this file is executed directly its ``__name__`` is
    ``"__main__"``, so the registration is non-redundant.
    """
    if "session_metrics_compare" in sys.modules:
        return sys.modules["session_metrics_compare"]
    sys.modules.setdefault("session_metrics", _sm())
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "session_metrics_compare", here / "session_metrics_compare.py")
    if spec is None or spec.loader is None:
        print("[error] could not locate session_metrics_compare.py alongside "
              "session-metrics.py", file=sys.stderr)
        sys.exit(1)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["session_metrics_compare"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    args = _build_parser().parse_args()
    # P5.2: --export-share-safe is a one-flag bundle that implies
    # --redact-user-prompts and --no-self-cost (chmod 0600 is wired
    # separately at every export write site via the share_safe param).
    # Set the implications here so all downstream code paths read a
    # consistent argparse namespace regardless of which flag combination
    # the user actually typed.
    if getattr(args, "export_share_safe", False):
        args.redact_user_prompts = True
        args.no_self_cost = True
    # Resolve --plan-cost: CLI flag wins, env var is the durable fallback.
    # Invalid env values fall back silently to None so a typo doesn't kill
    # the run; the CLI flag's argparse type=float still hard-errors.
    plan_cost: float | None = args.plan_cost
    if plan_cost is None:
        _env_plan = os.environ.get("SESSION_METRICS_PLAN_COST")
        if _env_plan:
            try:
                plan_cost = float(_env_plan)
            except ValueError:
                print(
                    f"[warn] SESSION_METRICS_PLAN_COST='{_env_plan}' is not a "
                    "number; ignoring.", file=sys.stderr,
                )
    if plan_cost is not None and plan_cost <= 0:
        print(
            f"[warn] --plan-cost / SESSION_METRICS_PLAN_COST must be > 0 "
            f"(got {plan_cost}); ignoring.", file=sys.stderr,
        )
        plan_cost = None
    args.plan_cost = plan_cost
    # Resolve --invariants thresholds. Each per-predicate flag overrides
    # the hard-coded default; left None it defers to ``_default_thresholds``.
    invariants_thresholds: dict | None = None
    if args.invariants:
        invariants_thresholds = {}
        for arg_name, key in (
            ("invariants_cache_hit_min",            "cache_hit_min"),
            ("invariants_cost_per_turn_max",        "cost_per_turn_max"),
            ("invariants_subagent_turn_share_min",  "subagent_turn_share_min"),
            ("invariants_cache_1h_share_max",       "cache_1h_share_max"),
            ("invariants_tool_calls_per_turn_max",  "tool_calls_per_turn_max"),
        ):
            v = getattr(args, arg_name, None)
            if v is not None:
                invariants_thresholds[key] = float(v)
    args.invariants_thresholds = invariants_thresholds
    slug = args.slug or _env_slug() or _cwd_to_slug()
    _validate_slug(slug)
    formats: list[str] = args.output or []
    # --evidence forces JSON into the export list so the sha256 sidecar
    # has a target. Done here (before any dispatch branch) so each entry
    # point sees a consistent ``formats`` list.
    if getattr(args, "evidence", False) and "json" not in formats:
        formats = formats + ["json"]
    tz_offset, tz_label = _sm()._resolve_tz(args.tz, args.utc_offset,
                                      strict=bool(args.strict_tz))
    peak = _sm()._build_peak(args.peak_hours, args.peak_tz,
                       strict=bool(args.strict_tz))
    chart_lib: str = args.chart_lib
    # Flip the module-level gate so _read_vendor_files knows whether to
    # raise or warn on verification failures. Set before any chart code runs.
    _sm()._ALLOW_UNVERIFIED_CHARTS = bool(args.allow_unverified_charts)
    _maybe_warn_chart_license(chart_lib, formats)
    # Apply --projects-dir / --cache-dir / --export-dir overrides early so
    # the corresponding helpers (_projects_dir, _parse_cache_dir, _export_dir)
    # see them before the global cache prune or any discovery call fires.
    if args.projects_dir:
        _sm()._PROJECTS_DIR_OVERRIDE = Path(args.projects_dir).expanduser()
    if getattr(args, "cache_dir", None):
        _sm()._CACHE_DIR_OVERRIDE = Path(args.cache_dir).expanduser()
    if getattr(args, "export_dir", None):
        _sm()._EXPORT_DIR_OVERRIDE = Path(args.export_dir).expanduser()
    if not args.no_cache:
        _sm()._prune_cache_global(_sm()._parse_cache_dir())

    if args.list:
        _list_sessions(slug)
        return

    if args.compare_add_prompt:
        smc = _load_compare_module()
        _extras_dir = smc._EXTRAS_DIR
        _extras_dir.mkdir(parents=True, exist_ok=True)
        _slug = re.sub(r"[^a-z0-9]+", "_", args.compare_add_prompt.lower())[:40].strip("_") + "_user"
        _dest = _extras_dir / f"{_slug}.md"
        if _dest.exists():
            print(f"[warn] prompt '{_slug}' already exists at {_dest}")
            print("Edit it directly or delete it and re-run with a different prompt.")
        else:
            _dest.write_text(args.compare_add_prompt.strip() + "\n", encoding="utf-8")
            print(f"Added prompt to {_dest}")
            print("Will run automatically on every --compare-run "
                  "(ratio/token data only; no pass/fail scoring)")
            print("Preview: session-metrics --compare-list-prompts")
            print(f"Remove:  session-metrics --compare-remove-prompt {_slug}")
        return

    if args.compare_remove_prompt:
        smc = _load_compare_module()
        _name = args.compare_remove_prompt.removesuffix(".md")
        _extras_suite = smc._load_prompt_suite(smc._EXTRAS_DIR)
        _entry = _extras_suite.get(_name)
        if _entry is None:
            print(f"[error] no user prompt named '{_name}' in {smc._EXTRAS_DIR}.",
                  file=sys.stderr)
            print("Run: session-metrics --compare-list-prompts  to see available names.",
                  file=sys.stderr)
            sys.exit(1)
        _entry["path"].unlink()
        print(f"Removed {_entry['path']}")
        return

    if args.compare_list_prompts:
        smc = _load_compare_module()
        _suite_dir = Path(args.compare_prompts).expanduser() if args.compare_prompts else None
        try:
            _suite = smc._load_prompt_suite(_suite_dir)
        except smc.PromptSuiteError as exc:
            print(f"[error] prompt suite: {exc}", file=sys.stderr)
            sys.exit(1)
        smc._run_compare_list_prompts(_suite)
        return

    if args.render_tasks is not None:
        export_json, grouping_json = args.render_tasks
        _task_fmts = [f for f in formats if f in ("html", "md")] or ["html", "md"]
        rc = _sm()._run_render_tasks(export_json, grouping_json,
                                     formats=_task_fmts)
        sys.exit(rc)

    if args.compare_prep is not None:
        smc = _load_compare_module()
        suite_dir = Path(args.compare_prompts).expanduser() if args.compare_prompts else None
        smc._run_compare_prep(args.compare_prep, suite_dir=suite_dir)
        return

    if args.count_tokens_only:
        smc = _load_compare_module()
        suite_dir = Path(args.compare_prompts).expanduser() if args.compare_prompts else None
        smc._run_count_tokens_only(
            args.compare_models,
            suite_dir=suite_dir,
            assume_yes=args.yes,
        )
        return

    if args.compare_run is not None:
        smc = _load_compare_module()
        suite_dir = Path(args.compare_prompts).expanduser() if args.compare_prompts else None
        scratch_dir = Path(args.compare_run_scratch_dir).expanduser() \
            if args.compare_run_scratch_dir else None
        # Resolve 0/1/2 positional model IDs to an (A, B) pair. Default is
        # the 1M-context Opus tier because that is what Claude Code ships
        # as the default Opus routing — comparing 200k vs 200k is a
        # deliberate opt-out, not a realistic baseline.
        _default_a = "claude-opus-4-6[1m]"
        _default_b = "claude-opus-4-7[1m]"
        _models = list(args.compare_run)
        if len(_models) == 0:
            model_a, model_b = _default_a, _default_b
        elif len(_models) == 1:
            model_a, model_b = _models[0], _default_b
        elif len(_models) == 2:
            model_a, model_b = _models[0], _models[1]
        else:
            print("[error] --compare-run takes 0, 1, or 2 model IDs; "
                  f"got {len(_models)}", file=sys.stderr)
            sys.exit(1)
        # Allow empty string to mean "omit --permission-mode"; None means "use default".
        if args.compare_run_permission_mode is None:
            permission_mode = "bypassPermissions"
        elif args.compare_run_permission_mode == "":
            permission_mode = None
        else:
            permission_mode = args.compare_run_permission_mode
        allowed_tools = args.compare_run_allowed_tools \
            or "Bash,Read,Write,Edit,Glob,Grep"
        timeout = args.compare_run_per_call_timeout or 900.0
        # Resolve 0/1/2 positional effort values. None or empty list means
        # "let each model use its Claude Code default" (Opus 4.6 → high,
        # Opus 4.7 → xhigh). One value pins both sides; two values map
        # A then B. The orchestrator validates the level itself, so we
        # only enforce arity here.
        _efforts = list(args.compare_run_effort or [])
        if len(_efforts) == 0:
            effort_a, effort_b = None, None
        elif len(_efforts) == 1:
            effort_a = effort_b = _efforts[0]
        elif len(_efforts) == 2:
            effort_a, effort_b = _efforts[0], _efforts[1]
        else:
            print("[error] --compare-run-effort takes 0, 1, or 2 levels; "
                  f"got {len(_efforts)}", file=sys.stderr)
            sys.exit(1)
        with contextlib.suppress(OSError, AttributeError):
            _sm()._touch_compare_state_marker(_cwd_to_slug(str(scratch_dir.resolve()))
                                        if scratch_dir else slug)
        # --compare-run defaults to md + html artefact generation so the
        # user always gets the analysis.md scaffold + dashboard HTML
        # pair alongside the text report. Passing an explicit --output
        # list overrides this (empty list stays empty after override
        # only via the not-yet-exposed opt-out; see SKILL.md for the
        # rationale). --no-compare-run-extras is the escape hatch when
        # the user wants the text-only behaviour back.
        compare_run_formats = formats or ["md", "html"]
        _maybe_warn_chart_license(chart_lib, compare_run_formats)
        smc._run_compare_run(
            model_a, model_b,
            scratch_dir=scratch_dir,
            suite_dir=suite_dir,
            assume_yes=args.yes,
            allowed_tools=allowed_tools,
            permission_mode=permission_mode,
            max_budget_usd=args.compare_run_max_budget_usd,
            per_call_timeout=timeout,
            formats=compare_run_formats,
            single_page=args.single_page,
            chart_lib=chart_lib,
            redact_user_prompts=args.redact_user_prompts,
            share_safe=args.export_share_safe,
            tz_offset=tz_offset,
            tz_label=tz_label,
            use_cache=not args.no_cache,
            include_subagents=args.include_subagents,
            pair_by=args.pair_by,
            min_turns=args.compare_min_turns,
            allow_suite_mismatch=args.allow_suite_mismatch,
            compare_run_extras=not args.no_compare_run_extras,
            effort_a=effort_a,
            effort_b=effort_b,
            steering_variant=args.compare_run_prompt_steering,
            steering_position=args.compare_run_prompt_steering_position,
        )
        return

    if args.compare:
        smc = _load_compare_module()
        suite_dir = Path(args.compare_prompts).expanduser() if args.compare_prompts else None
        # Resolve 0/1/2 positional effort annotations for --compare. This is
        # cosmetic: it doesn't re-run inference, it just lets the user
        # surface the effort level the JSONLs were captured at on the
        # text/MD/HTML/CSV/analysis.md outputs. Same 0/1/2 arity as
        # --compare-run-effort so the two feel symmetric.
        _compare_efforts = list(args.compare_effort or [])
        if len(_compare_efforts) == 0:
            effort_a_compare = effort_b_compare = None
        elif len(_compare_efforts) == 1:
            effort_a_compare = effort_b_compare = _compare_efforts[0]
        elif len(_compare_efforts) == 2:
            effort_a_compare, effort_b_compare = _compare_efforts[0], _compare_efforts[1]
        else:
            print("[error] --compare-effort takes 0, 1, or 2 levels; "
                  f"got {len(_compare_efforts)}", file=sys.stderr)
            sys.exit(1)
        # State-marker file: Phase 7's dashboard insight card only fires
        # after the user has successfully run --compare once in this project.
        # Dropping the marker here (before the run, as a best-effort) means
        # that even if the compare crashes mid-way we still remember the
        # user attempted one — the whole point is to suppress spam on
        # projects where nobody's interested in a benchmark.
        with contextlib.suppress(OSError):
            _sm()._touch_compare_state_marker(slug)
        smc._run_compare(
            args.compare[0], args.compare[1],
            slug=slug,
            pair_by=args.pair_by,
            compare_scope=args.compare_scope,
            min_turns=args.compare_min_turns,
            formats=formats,
            tz_offset=tz_offset,
            tz_label=tz_label,
            include_subagents=args.include_subagents,
            use_cache=not args.no_cache,
            single_page=args.single_page,
            chart_lib=chart_lib,
            assume_yes=args.yes,
            prompt_suite_dir=suite_dir,
            allow_suite_mismatch=args.allow_suite_mismatch,
            redact_user_prompts=args.redact_user_prompts,
            share_safe=args.export_share_safe,
            effort_a=effort_a_compare,
            effort_b=effort_b_compare,
        )
        return

    if args.all_projects:
        _sm()._run_all_projects(
            formats, tz_offset, tz_label,
            peak=peak, single_page=args.single_page,
            use_cache=not args.no_cache, chart_lib=chart_lib,
            idle_gap_minutes=args.idle_gap_minutes,
            include_subagents=args.include_subagents,
            drilldown=not args.no_project_drilldown,
            suppress_model_compare_insight=args.no_model_compare_insight,
            cache_break_threshold=args.cache_break_threshold,
            subagent_attribution=not args.no_subagent_attribution,
            sort_prompts_by=args.sort_prompts_by,
            share_safe=args.export_share_safe,
            plan_cost=plan_cost,
            invariants_thresholds=invariants_thresholds,
            evidence=args.evidence,
            include_workflows=args.include_workflows,
            no_workflow_detail=args.no_workflow_detail,
        )
        return

    if args.project_cost:
        print(f"Slug : {slug}", file=sys.stderr)
        print(f"TZ   : {tz_label} (UTC{'+' if tz_offset >= 0 else '-'}{abs(tz_offset):g})", file=sys.stderr)
        print(file=sys.stderr)
        _sm()._run_project_cost(
            slug, args.include_subagents, formats, tz_offset, tz_label,
            peak=peak, single_page=args.single_page,
            use_cache=not args.no_cache, chart_lib=chart_lib,
            idle_gap_minutes=args.idle_gap_minutes,
            suppress_model_compare_insight=args.no_model_compare_insight,
            cache_break_threshold=args.cache_break_threshold,
            subagent_attribution=not args.no_subagent_attribution,
            sort_prompts_by=args.sort_prompts_by,
            no_self_cost=args.no_self_cost,
            redact_user_prompts=args.redact_user_prompts,
            share_safe=args.export_share_safe,
            plan_cost=plan_cost,
            invariants_thresholds=invariants_thresholds,
            evidence=args.evidence,
            include_workflows=args.include_workflows,
            no_workflow_detail=args.no_workflow_detail,
            task_companion_nav=args.task_companion_nav,
            quiet=args.quiet,
        )
        return

    jsonl_path, resolved_slug = _resolve_session(args)
    print(f"Slug    : {resolved_slug}", file=sys.stderr)
    print(f"TZ      : {tz_label} (UTC{'+' if tz_offset >= 0 else '-'}{abs(tz_offset):g})", file=sys.stderr)
    _sm()._run_single_session(
        jsonl_path, resolved_slug, args.include_subagents, formats,
        tz_offset, tz_label, peak=peak, single_page=args.single_page,
        use_cache=not args.no_cache, chart_lib=chart_lib,
        idle_gap_minutes=args.idle_gap_minutes,
        suppress_model_compare_insight=args.no_model_compare_insight,
        cache_break_threshold=args.cache_break_threshold,
        subagent_attribution=not args.no_subagent_attribution,
        sort_prompts_by=args.sort_prompts_by,
        no_self_cost=args.no_self_cost,
        redact_user_prompts=args.redact_user_prompts,
        share_safe=args.export_share_safe,
        plan_cost=plan_cost,
        invariants_thresholds=invariants_thresholds,
        include_workflows=args.include_workflows,
        no_workflow_detail=args.no_workflow_detail,
        task_companion_nav=args.task_companion_nav,
        quiet=args.quiet,
    )

