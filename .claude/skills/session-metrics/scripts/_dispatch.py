"""Output dispatch, session execution, and instance rendering for session-metrics."""
import csv as csv_mod
import html as html_mod
import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from _constants import _CACHE_BREAK_DEFAULT_THRESHOLD

_EXTENSIONS = {"text": "txt", "json": "json", "csv": "csv", "md": "md", "html": "html"}

# Exported names accessed by session-metrics.py via _load_leaf(); listed here so
# static analysers don't flag them as unreachable private functions.
__all__ = [
    "_run_single_session", "_run_project_cost", "_run_all_projects",
    "_dispatch_instance", "_render_instance_text", "_render_instance_csv",
    "_render_instance_md", "_render_instance_html", "_run_render_tasks",
]


def _sm():
    """Return the session_metrics module (deferred — fully loaded by call time)."""
    return sys.modules["session_metrics"]


def _maybe_run_invariants(report: dict, thresholds: dict | None) -> None:
    """Evaluate the invariants suite and exit non-zero on violation.

    Called after a normal dispatch so the report artefacts (HTML / JSON /
    etc.) still land — the invariant check is a CI gate, not a render
    suppression. Prints results to stderr and ``sys.exit(_INVARIANT_EXIT_CODE)``
    if any predicate fails.
    """
    if thresholds is None:
        return
    results = _sm()._run_invariants(report, thresholds)
    print(_sm()._format_invariant_results(results), file=sys.stderr)
    code = _sm()._invariants_exit_code(results)
    if code != 0:
        sys.exit(code)


def _export_dir() -> Path:
    """Return the directory exports are written to.

    Resolution order (v1.41.0):
      1. ``--export-dir`` CLI flag (sets ``_sm()._EXPORT_DIR_OVERRIDE``)
      2. ``CLAUDE_SESSION_METRICS_EXPORT_DIR`` env var
      3. Default ``<cwd>/exports/session-metrics``

    Mirrors the ``--cache-dir`` / ``--projects-dir`` precedence pattern.
    ``_instance_export_root`` already calls this helper, so the override
    flows through to the dated subfolder under ``<root>/instance/...``
    automatically.
    """
    if _sm()._EXPORT_DIR_OVERRIDE is not None:
        return _sm()._EXPORT_DIR_OVERRIDE
    env = os.environ.get("CLAUDE_SESSION_METRICS_EXPORT_DIR")
    if env:
        return Path(env).expanduser()
    return Path(os.getcwd()) / "exports" / "session-metrics"


def _run_render_tasks(export_json: str, grouping_json: str,
                      formats: list[str] | None = None) -> int:
    """Render the standalone Tasks companion from an export + grouping file.

    ``--render-tasks`` entry point. Loads a session-metrics JSON export and a
    Claude-authored ``grouping.json``, validates + resolves the grouping
    against the export's ``request_units`` via ``_assemble_tasks`` (all
    cost/turn figures summed from the export — the grouping is never trusted
    for math), then writes ``<stem>_tasks.html`` / ``<stem>_tasks.md`` next to
    the export. Prints any validation warnings + the output paths. Returns a
    process exit code (0 ok, non-zero on hard error).
    """
    exp_path = Path(export_json).expanduser()
    grp_path = Path(grouping_json).expanduser()
    try:
        report = json.loads(exp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read export JSON {exp_path}: {e}", file=sys.stderr)
        return 2
    try:
        grouping = json.loads(grp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read grouping JSON {grp_path}: {e}", file=sys.stderr)
        return 2
    if not isinstance(report, dict) or "request_units" not in report:
        print("error: export JSON has no 'request_units' — re-run "
              "session-metrics to regenerate the export (the per-request "
              "breakdown was added in a newer version).", file=sys.stderr)
        return 2
    if not isinstance(grouping, dict):
        print("error: grouping JSON must be an object with a 'tasks' array.",
              file=sys.stderr)
        return 2

    assembled = _sm()._assemble_tasks(report, grouping)
    if not assembled.get("tasks"):
        print("error: grouping produced no tasks (empty 'tasks' array and no "
              "request units to fall back on).", file=sys.stderr)
        return 2

    fmts = formats or ["html", "md"]
    stem = exp_path.stem  # e.g. session_2b74cec9_20260530T...
    out_dir = exp_path.parent
    written: list[Path] = []
    if "html" in fmts:
        html = _sm()._build_tasks_companion_html(report, assembled)
        hp = out_dir / f"{stem}_tasks.html"
        hp.write_text(html, encoding="utf-8")
        written.append(hp)
    if "md" in fmts:
        md = _sm()._build_tasks_companion_md(report, assembled)
        mp = out_dir / f"{stem}_tasks.md"
        mp.write_text(md, encoding="utf-8")
        written.append(mp)

    for w in assembled.get("warnings") or []:
        print(f"  ! {w}", file=sys.stderr)
    print(f"Tasks companion: {assembled['unit_count']} requests → "
          f"{len(assembled['tasks'])} task(s), "
          f"{assembled['coverage_pct']:.0f}% grouped, "
          f"${assembled['total_cost_usd']:.4f} total.", file=sys.stderr)
    for w in written:
        print(str(w))
    return 0


def _write_output(fmt: str, content: str, report: dict,
                   suffix: str = "",
                   explicit_ts: str | None = None,
                   share_safe: bool = False) -> Path:
    """Write ``content`` to an export file; ``suffix`` is appended before
    the extension (e.g. ``"_dashboard"``, ``"_detail"``).

    ``explicit_ts`` overrides the default ``datetime.now(UTC)`` stamp in the
    filename. Used by ``_emit_compare_run_extras`` so a bundle of companion
    files (per-session dashboards + analysis.md) all share the same
    timestamp and the Markdown href links resolve.

    ``share_safe`` chmods the file to ``0o600`` (rw-------) immediately
    after the write. Set by ``--export-share-safe`` so single-user shells
    can drop exports into shared directories (Dropbox, etc.) without
    accidentally publishing freeform prompt text.
    """
    out_dir = _export_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = report["mode"]
    ts = explicit_ts or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if mode == "project":
        stem = f"project_{ts}"
    elif mode == "compare":
        a_sid = (report.get("side_a") or {}).get("session_id") or "a"
        b_sid = (report.get("side_b") or {}).get("session_id") or "b"
        stem = f"compare_{a_sid[:8]}_vs_{b_sid[:8]}_{ts}"
    else:
        sid = report["sessions"][0]["session_id"][:8]
        stem = f"session_{sid}_{ts}"
    path = out_dir / f"{stem}{suffix}.{_EXTENSIONS[fmt]}"
    path.write_text(content, encoding="utf-8")
    if share_safe:
        path.chmod(0o600)
    return path
# Pattern for resolving subagent type from its filename when a meta sidecar
# is missing. Matches the Anthropic session-report convention
# ``agent-a<label>-<hash>.jsonl`` — we peel off the label as the agent type.
_SUBAGENT_FILENAME_RE = re.compile(r"^agent-a([^-]+)-[0-9a-fA-F]+$")


def _parse_workflow_journal(path: Path) -> dict | None:
    """Parse one ``workflows/wf_<runId>.json`` journal into a display summary.

    The journal is the Workflow tool's own run record (metadata + an
    aggregate ``totalTokens`` that EXCLUDES cache reads, so it is NOT used
    for cost — transcripts are the source of truth). We mine it only for
    display fields the per-agent transcripts don't carry: the human workflow
    name, run status, phase structure, and per-agent labels / previews.

    Returns ``None`` on any read/parse error so a malformed journal never
    breaks the report (the transcripts still drive tokens/cost).
    """
    try:
        with open(path, encoding="utf-8") as fh:
            j = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(j, dict):
        return None
    run_id = j.get("runId") or path.stem
    agents: list[dict] = []
    for e in j.get("workflowProgress") or []:
        if not isinstance(e, dict) or e.get("type") != "workflow_agent":
            continue
        agents.append({
            "agentId":     str(e.get("agentId") or ""),
            "label":       str(e.get("label") or ""),
            "model":       str(e.get("model") or ""),
            "phaseIndex":  e.get("phaseIndex"),
            "phaseTitle":  str(e.get("phaseTitle") or ""),
            "state":       str(e.get("state") or ""),
            "tokens":      int(e.get("tokens") or 0),
            "toolCalls":   int(e.get("toolCalls") or 0),
            "durationMs":  int(e.get("durationMs") or 0),
            "promptPreview":  str(e.get("promptPreview") or ""),
            "resultPreview":  str(e.get("resultPreview") or ""),
        })
    phases = []
    for p in j.get("phases") or []:
        if isinstance(p, dict):
            phases.append({"title": str(p.get("title") or ""),
                           "detail": str(p.get("detail") or "")})
    return {
        "run_id":          str(run_id),
        "workflow_name":   str(j.get("workflowName") or run_id),
        "status":          str(j.get("status") or ""),
        "agent_count":     int(j.get("agentCount") or 0),
        "total_tool_calls": int(j.get("totalToolCalls") or 0),
        "journal_total_tokens": int(j.get("totalTokens") or 0),
        "duration_ms":     int(j.get("durationMs") or 0),
        "default_model":   str(j.get("defaultModel") or ""),
        "phases":          phases,
        "agents":          agents,
    }


def _resolve_subagent_type(sub_path: Path) -> str:
    """Three-tier fallback identical in spirit to Anthropic's session-report:
    (1) ``<stem>.meta.json`` → ``agentType`` field, (2) filename label via
    :data:`_SUBAGENT_FILENAME_RE`, (3) ``"fork"`` sentinel.
    """
    meta_path = sub_path.with_suffix(".meta.json")
    try:
        if meta_path.is_file():
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
            agent_type = meta.get("agentType") if isinstance(meta, dict) else None
            if isinstance(agent_type, str) and agent_type:
                return agent_type
    except (OSError, json.JSONDecodeError):
        pass
    m = _SUBAGENT_FILENAME_RE.match(sub_path.stem)
    if m:
        return m.group(1)
    return "fork"


def _extract_workflow_spawn_links(entries: list[dict]) -> dict[str, str]:
    """Map ``runId → spawning tool_use_id`` from main-thread Workflow
    ``tool_result`` entries.

    Each launched workflow writes back a ``toolUseResult`` carrying its
    ``runId`` on the user entry whose ``message.content`` holds the matching
    ``tool_result`` block — that block's ``tool_use_id`` is the assistant
    tool_use that spawned the run. Capturing the pair lets Phase-B attribution
    resolve ``runId → tool_use_id → spawning-prompt anchor``.

    Run this over the *pre-dedup* entry list: the cross-file ``seen_uuids``
    filter can drop a resumed session's replayed ``toolUseResult`` entry, and
    losing it would silently re-orphan the whole run's cost. First write wins.
    """
    links: dict[str, str] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        tur = e.get("toolUseResult")
        run_id = tur.get("runId") if isinstance(tur, dict) else None
        if not run_id or run_id in links:
            continue
        msg = e.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                tuid = b.get("tool_use_id")
                if isinstance(tuid, str) and tuid:
                    links[run_id] = tuid
                    break
    return links


def _load_session(
    jsonl_path: Path, include_subagents: bool, use_cache: bool = True,
    seen_uuids: set[str] | None = None,
    compaction_sink: dict | None = None,
    include_workflows: bool = True,
    workflow_sink: dict | None = None,
) -> tuple[str, list[dict], list[int]]:
    """Load a session JSONL and return structured data for report building.

    Parses the JSONL file, optionally merging subagent logs, then extracts
    both assistant turns (for token/cost tracking) and user timestamps (for
    time-of-day activity analysis).  User timestamps are extracted from the
    full entry list *before* assistant-only filtering discards them.

    ``seen_uuids`` is an opt-in cross-file dedup guard. When provided, any
    entry whose ``uuid`` field is already in the set is dropped; surviving
    entries are added. Callers supply a set shared across JSONLs they want
    to treat as one scope (project/instance); pass ``None`` to skip dedup
    (session scope — the in-file ``message.id`` dedup in ``_extract_turns``
    already handles streaming splits).

    ``compaction_sink`` is an opt-in mutable accumulator (same idiom as
    ``seen_uuids``). When provided, this session's compaction events
    (``_extract_compaction_events``) are stored under
    ``compaction_sink[session_id]``. Threaded this way rather than via a
    return-tuple element so callers (incl. the separate compare tool) that
    don't need it are unaffected, and so we avoid a second parse —
    ``_cached_parse_jsonl`` is a per-call disk pickle load, not in-memory
    memoized, so re-reading would cost a full second deserialize per file.

    Returns:
        3-tuple of (session_id, assistant_turns, user_epoch_secs) where
        session_id is the JSONL filename stem, assistant_turns is the
        deduplicated/sorted list of raw assistant entries, and
        user_epoch_secs is a sorted list of UTC epoch-seconds for every
        genuine user prompt (tool_results and meta entries excluded).
    """
    entries = list(_sm()._cached_parse_jsonl(jsonl_path, use_cache=use_cache))
    if include_subagents:
        subagent_dir = jsonl_path.parent / jsonl_path.stem / "subagents"
        if subagent_dir.exists():
            for sub in sorted(subagent_dir.glob("*.jsonl")):
                agent_type = _resolve_subagent_type(sub)
                # Phase-B: filename stem sans ``agent-`` prefix is the
                # canonical agentId Claude Code uses to link a subagent
                # JSONL to the parent's ``toolUseResult.agentId``. Tag
                # every entry so ``_attribute_subagent_tokens`` can roll
                # tokens up onto the spawning prompt.
                agent_id = sub.stem
                if agent_id.startswith("agent-"):
                    agent_id = agent_id[len("agent-"):]
                sub_entries = _sm()._cached_parse_jsonl(sub, use_cache=use_cache)
                for e in sub_entries:
                    if isinstance(e, dict):
                        e["_subagent_type"] = agent_type
                        e["_subagent_agent_id"] = agent_id
                        entries.append(e)
            # Dynamic-workflow agents (Workflow tool: agent()/parallel()/
            # pipeline()) persist their transcripts one tier deeper, under
            # ``subagents/workflows/<runId>/agent-*.jsonl`` — a level the
            # non-recursive glob above never reaches. These carry full
            # per-message ``usage`` blocks, so once merged the existing
            # per-model pricing tallies them exactly. ``journal.jsonl`` (a
            # key/value event log with no ``usage``) shares the dir and must
            # be excluded; the ``agent-*.jsonl`` glob does so naturally. A
            # workflow can fan out to 100s of agents, so this is the bulk of
            # token spend under ultracode — see references/jsonl-schema.md.
            if include_workflows:
                wf_root = subagent_dir / "workflows"
                if wf_root.exists():
                    for run_dir in sorted(wf_root.iterdir()):
                        if not run_dir.is_dir():
                            continue
                        run_id = run_dir.name
                        for sub in sorted(run_dir.glob("agent-*.jsonl")):
                            agent_type = _resolve_subagent_type(sub)
                            agent_id = sub.stem
                            if agent_id.startswith("agent-"):
                                agent_id = agent_id[len("agent-"):]
                            sub_entries = _sm()._cached_parse_jsonl(
                                sub, use_cache=use_cache)
                            for e in sub_entries:
                                if isinstance(e, dict):
                                    e["_subagent_type"] = agent_type
                                    e["_subagent_agent_id"] = agent_id
                                    e["_workflow_run_id"] = run_id
                                    entries.append(e)
    # Capture runId → spawning tool_use_id BEFORE the dedup below — a resumed
    # session can have its replayed ``toolUseResult`` entry filtered out, which
    # would lose the link and re-orphan the run's cost.
    workflow_spawn_links: dict[str, str] = {}
    if workflow_sink is not None and include_subagents and include_workflows:
        workflow_spawn_links = _extract_workflow_spawn_links(entries)
    # Cross-file UUID dedup (opt-in). Anthropic's session-report uses this
    # to prevent resumed-session replays from double-counting across sibling
    # JSONLs. We do the same — but only when the caller provides the set
    # (scope = {session, project, instance}); otherwise the caller wants the
    # single-file-only ``message.id`` dedup handled by ``_extract_turns``.
    if seen_uuids is not None:
        filtered: list[dict] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            uid = e.get("uuid")
            if isinstance(uid, str) and uid:
                if uid in seen_uuids:
                    continue
                seen_uuids.add(uid)
            filtered.append(e)
        entries = filtered
    # Compaction events: extract AFTER the cross-file dedup above, NOT before.
    # Verified empirically (this project: 206 files, 136 boundary entries but
    # only 109 distinct uuids — 3 uuids appear in >1 file): resume REPLAYS
    # compact_boundary entries across sibling JSONLs, just like turns. So
    # boundaries need the same first-occurrence-wins ``seen_uuids`` protection,
    # or project/instance summaries would double-count the ~27 replayed ones.
    # At session scope ``seen_uuids is None`` → no filtering → all in-file
    # boundaries kept (correct). The merged ``entries`` also holds subagent
    # logs (which DO carry their own boundaries), but ``_extract_compaction_events``
    # skips ``_subagent_agent_id``-tagged entries so only main-session
    # boundaries count.
    if compaction_sink is not None:
        compaction_sink[jsonl_path.stem] = _sm()._extract_compaction_events(entries)
    # Dynamic-workflow journals: display metadata (workflow name, status,
    # phases, per-agent labels) keyed by runId. Cost/tokens come from the
    # merged transcripts above — the journal is enrichment only. Same
    # opt-in mutable-accumulator idiom as ``compaction_sink``. The journals
    # live in ``<session>/workflows/`` (sibling of ``subagents/``).
    if workflow_sink is not None and include_subagents and include_workflows:
        wf_meta_dir = jsonl_path.parent / jsonl_path.stem / "workflows"
        if wf_meta_dir.is_dir():
            run_meta: dict[str, dict] = {}
            for jp in sorted(wf_meta_dir.glob("wf_*.json")):
                summary = _parse_workflow_journal(jp)
                if summary:
                    run_meta[summary["run_id"]] = summary
            if run_meta:
                # Phase-B link (captured pre-dedup above): runId → the
                # ``tool_use_id`` of the Workflow call that launched it, the
                # bridge that lets us roll a run's cost onto the prompt that
                # spawned it (workflow agents have ``parentUuid: null`` so the
                # agentId path orphans).
                for rid, tuid in workflow_spawn_links.items():
                    if rid in run_meta:
                        run_meta[rid]["spawn_tool_use_id"] = tuid
                workflow_sink[jsonl_path.stem] = run_meta
    return (
        jsonl_path.stem,
        _sm()._extract_turns(entries),
        _sm()._extract_user_timestamps(entries, include_sidechain=include_subagents),
    )


def _run_single_session(jsonl_path: Path, slug: str, include_subagents: bool,
                         formats: list[str], tz_offset: float, tz_label: str,
                         peak: dict | None = None,
                         single_page: bool = False,
                         use_cache: bool = True,
                         chart_lib: str = "highcharts",
                         idle_gap_minutes: int = 10,
                         suppress_model_compare_insight: bool = False,
                         cache_break_threshold: int = _CACHE_BREAK_DEFAULT_THRESHOLD,
                         subagent_attribution: bool = True,
                         sort_prompts_by: str | None = None,
                         no_self_cost: bool = False,
                         redact_user_prompts: bool = False,
                         share_safe: bool = False,
                         plan_cost: float | None = None,
                         invariants_thresholds: dict | None = None,
                         evidence: bool = False,
                         include_workflows: bool = True,
                         no_workflow_detail: bool = False,
                         task_companion_nav: bool = False) -> None:
    print(f"Session : {jsonl_path.stem}", file=sys.stderr)
    print(f"File    : {jsonl_path}", file=sys.stderr)
    print(file=sys.stderr)

    # Single-session scope: ``message.id`` dedup in ``_extract_turns`` already
    # handles streaming splits for the one file being loaded, so we don't need
    # cross-file UUID dedup here. Pass ``None`` to disable.
    compaction_by_session: dict = {}
    workflow_by_session: dict = {}
    session_id, turns, user_ts = _load_session(jsonl_path, include_subagents,
                                                 use_cache=use_cache,
                                                 seen_uuids=None,
                                                 compaction_sink=compaction_by_session,
                                                 include_workflows=include_workflows,
                                                 workflow_sink=workflow_by_session)
    if not turns:
        print("[info] No assistant turns with usage data found.", file=sys.stderr)
        return

    report = _sm()._build_report(
        "session", slug, [(session_id, turns, user_ts)],
        tz_offset_hours=tz_offset, tz_label=tz_label, peak=peak,
        suppress_model_compare_insight=suppress_model_compare_insight,
        cache_break_threshold=cache_break_threshold,
        subagent_attribution=subagent_attribution,
        sort_prompts_by=sort_prompts_by,
        include_subagents=include_subagents,
        compaction_events_by_session=compaction_by_session,
        workflow_journals_by_session=workflow_by_session,
    )
    if plan_cost is not None:
        report["plan_cost"] = float(plan_cost)
    self_cost = report.pop("self_cost", None) if no_self_cost else report.get("self_cost")
    _dispatch(report, formats, single_page=single_page, chart_lib=chart_lib,
              idle_gap_minutes=idle_gap_minutes,
              redact_user_prompts=redact_user_prompts,
              share_safe=share_safe,
              evidence=evidence,
              no_workflow_detail=no_workflow_detail,
              task_companion_nav=task_companion_nav)
    if not no_self_cost and self_cost:
        _print_self_cost_summary(self_cost)
    _maybe_run_invariants(report, invariants_thresholds)


def _run_project_cost(slug: str, include_subagents: bool, formats: list[str],
                      tz_offset: float, tz_label: str,
                      peak: dict | None = None,
                      single_page: bool = False,
                      use_cache: bool = True,
                      chart_lib: str = "highcharts",
                      idle_gap_minutes: int = 10,
                      suppress_model_compare_insight: bool = False,
                      cache_break_threshold: int = _CACHE_BREAK_DEFAULT_THRESHOLD,
                      subagent_attribution: bool = True,
                      sort_prompts_by: str | None = None,
                      no_self_cost: bool = False,
                      redact_user_prompts: bool = False,
                      share_safe: bool = False,
                      plan_cost: float | None = None,
                      invariants_thresholds: dict | None = None,
                      evidence: bool = False,
                      include_workflows: bool = True,
                      no_workflow_detail: bool = False,
                      task_companion_nav: bool = False) -> None:
    files = _sm()._find_jsonl_files(slug)
    if not files:
        print(f"[error] No sessions found for slug: {slug}", file=sys.stderr)
        sys.exit(1)

    # Project scope: one shared ``seen_uuids`` across every JSONL in the
    # project so a resumed session replaying prior entries doesn't
    # double-count tokens in project totals (gap #8 fix).
    project_seen: set[str] = set()
    compaction_by_session: dict = {}
    workflow_by_session: dict = {}
    sessions_raw = []
    for path in reversed(files):   # oldest first
        sid, turns, user_ts = _load_session(path, include_subagents,
                                              use_cache=use_cache,
                                              seen_uuids=project_seen,
                                              compaction_sink=compaction_by_session,
                                              include_workflows=include_workflows,
                                              workflow_sink=workflow_by_session)
        if turns:
            sessions_raw.append((sid, turns, user_ts))

    if not sessions_raw:
        print("[info] No turns with usage data found across any session.", file=sys.stderr)
        return

    report = _sm()._build_report(
        "project", slug, sessions_raw,
        tz_offset_hours=tz_offset, tz_label=tz_label, peak=peak,
        suppress_model_compare_insight=suppress_model_compare_insight,
        cache_break_threshold=cache_break_threshold,
        subagent_attribution=subagent_attribution,
        sort_prompts_by=sort_prompts_by,
        include_subagents=include_subagents,
        compaction_events_by_session=compaction_by_session,
        workflow_journals_by_session=workflow_by_session,
    )
    if plan_cost is not None:
        report["plan_cost"] = float(plan_cost)
    self_cost = report.pop("self_cost", None) if no_self_cost else report.get("self_cost")
    _dispatch(report, formats, single_page=single_page, chart_lib=chart_lib,
              idle_gap_minutes=idle_gap_minutes,
              redact_user_prompts=redact_user_prompts,
              share_safe=share_safe,
              evidence=evidence,
              no_workflow_detail=no_workflow_detail,
              task_companion_nav=task_companion_nav)
    if not no_self_cost and self_cost:
        _print_self_cost_summary(self_cost)
    _maybe_run_invariants(report, invariants_thresholds)


def _run_all_projects(formats: list[str],
                      tz_offset: float, tz_label: str,
                      peak: dict | None = None,
                      single_page: bool = False,
                      use_cache: bool = True,
                      chart_lib: str = "highcharts",
                      idle_gap_minutes: int = 10,
                      include_subagents: bool = False,
                      drilldown: bool = True,
                      suppress_model_compare_insight: bool = False,
                      cache_break_threshold: int = _CACHE_BREAK_DEFAULT_THRESHOLD,
                      subagent_attribution: bool = True,
                      sort_prompts_by: str | None = None,
                      share_safe: bool = False,
                      plan_cost: float | None = None,
                      invariants_thresholds: dict | None = None,
                      evidence: bool = False,
                      include_workflows: bool = True,
                      no_workflow_detail: bool = False) -> None:
    projects_dir = _sm()._projects_dir()
    print(f"Scanning: {projects_dir}", file=sys.stderr)
    discovered = _sm()._list_all_projects()
    if not discovered:
        print(f"[error] No projects with session JSONLs found under {projects_dir}",
              file=sys.stderr)
        sys.exit(1)
    print(f"Found   : {len(discovered)} project(s)", file=sys.stderr)
    print(f"TZ      : {tz_label} (UTC{'+' if tz_offset >= 0 else '-'}{abs(tz_offset):g})",
          file=sys.stderr)
    print(file=sys.stderr)

    # Instance-scope UUID dedup: one set spans every JSONL across every
    # project so a session that was resumed (replaying prior UUIDs into a
    # new file) can't double-count in instance totals. Loaded entries add
    # their UUIDs; subsequent files skip anything already present.
    instance_seen: set[str] = set()
    # Compaction events for every session across every project, keyed by
    # session_id. Populated in the serial load phase below and handed to each
    # per-project ``_build_report`` (which picks out only its own sessions).
    instance_compaction: dict = {}
    # Dynamic-workflow journals for every session across every project,
    # keyed by session_id — handed to each per-project ``_build_report``.
    instance_workflows: dict = {}
    # Raw sessions_raw tuples across every project — preserved so the
    # instance-scope insights (_build_session_blocks, _build_weekly_rollup)
    # see the same raw JSONL shape they do in project mode. Without this
    # the post-processed turn records lack the ``message.usage`` subtree
    # that session_blocks reads for token tallies.
    all_sessions_raw: list[tuple[str, list[dict], list[int]]] = []
    # P4.3: split per-project work into two phases. Phase 1 (this loop)
    # remains serial because `_load_session` mutates the shared
    # `instance_seen` UUID set — parallelising it would race the dedup
    # ("first occurrence wins" needs deterministic order). Phase 2 fans
    # out the pure-CPU `_build_report` calls across a thread pool below.
    project_inputs: list[tuple[str, list[tuple[str, list[dict], list[int]]]]] = []
    for i, (slug, project_dir) in enumerate(discovered, 1):
        jsonls = sorted(
            [p for p in project_dir.glob("*.jsonl") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
        )  # oldest first
        sessions_raw = []
        for path in jsonls:
            try:
                sid, turns, user_ts = _load_session(path, include_subagents,
                                                     use_cache=use_cache,
                                                     seen_uuids=instance_seen,
                                                     compaction_sink=instance_compaction,
                                                     include_workflows=include_workflows,
                                                     workflow_sink=instance_workflows)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[warn] {slug}: skipping {path.name} ({exc})",
                      file=sys.stderr)
                continue
            if turns:
                sessions_raw.append((sid, turns, user_ts))
        if not sessions_raw:
            print(f"[skip] {slug}: no usable turns", file=sys.stderr)
            continue
        print(f"[{i}/{len(discovered)}] Loaded {slug} "
              f"({len(sessions_raw)} session(s))", file=sys.stderr)
        project_inputs.append((slug, sessions_raw))
        all_sessions_raw.extend(sessions_raw)

    # Phase 2: build per-project reports in parallel. `_build_report` is
    # pure over its `sessions_raw` argument (no shared mutable state across
    # projects — `_load_session`'s parse cache is the only on-disk shared
    # store and it's atomic via lockfile). Threads suffice over processes:
    # JSON parsing inside `_build_turn_record` releases the GIL on most
    # CPython builds, and the pickle / start-up cost of processes would
    # erase the gain on small projects. Order is preserved by collecting
    # results in submit-order rather than completion-order so per-project
    # ordering across `project_reports` matches the discovery order.
    def _build_one_project(slug_and_raw: tuple[str, list]) -> dict:
        slug_, sessions_raw_ = slug_and_raw
        return _sm()._build_report(
            "project", slug_, sessions_raw_,
            tz_offset_hours=tz_offset, tz_label=tz_label, peak=peak,
            suppress_model_compare_insight=True,  # per-project, suppress noise
            cache_break_threshold=cache_break_threshold,
            subagent_attribution=subagent_attribution,
            sort_prompts_by=sort_prompts_by,
            include_subagents=include_subagents,
            compaction_events_by_session=instance_compaction,
            workflow_journals_by_session=instance_workflows,
        )

    if len(project_inputs) > 1:
        max_workers = min(8, (os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            project_reports: list[dict] = list(
                ex.map(_build_one_project, project_inputs)
            )
    else:
        project_reports = [_build_one_project(p) for p in project_inputs]

    if not project_reports:
        print("[info] No projects yielded usable turns.", file=sys.stderr)
        return

    instance_report = _sm()._build_instance_report(
        project_reports,
        all_sessions_raw,
        tz_offset_hours=tz_offset,
        tz_label=tz_label,
        projects_dir=projects_dir,
        peak=peak,
        cache_break_threshold=cache_break_threshold,
    )
    instance_report["_suppress_model_compare_insight"] = \
        suppress_model_compare_insight
    if plan_cost is not None:
        # Stamp on instance + every per-project report so the plan-leverage
        # KPI card surfaces consistently in the instance index and in each
        # drilldown HTML.
        instance_report["plan_cost"] = float(plan_cost)
        for pr in project_reports:
            pr["plan_cost"] = float(plan_cost)

    # ``single_page`` is accepted from the CLI but has no effect at instance
    # scope: the instance ``index.html`` is always a single page by design,
    # and the per-project drilldown HTMLs are always emitted as single-page
    # variants. The argument is kept for CLI symmetry only.
    _ = single_page
    _sm()._dispatch_instance(instance_report, project_reports, formats,
                              chart_lib=chart_lib,
                              idle_gap_minutes=idle_gap_minutes,
                              drilldown=drilldown,
                              share_safe=share_safe,
                              evidence=evidence)
    _maybe_run_invariants(instance_report, invariants_thresholds)


def _instance_export_root(now: datetime | None = None) -> Path:
    """Dated subfolder under ``exports/session-metrics/instance/`` for one run."""
    now = now or datetime.now(UTC)
    stamp = now.strftime("%Y-%m-%d-%H%M%S")
    return _export_dir() / "instance" / stamp


def _dispatch_instance(instance_report: dict,
                        project_reports: list[dict],
                        formats: list[str],
                        chart_lib: str = "highcharts",
                        idle_gap_minutes: int = 10,
                        drilldown: bool = True,
                        share_safe: bool = False,
                        evidence: bool = False) -> None:
    """Write all instance exports (and, optionally, per-project drilldown
    HTMLs) into a dated subfolder so successive runs don't overwrite each
    other. The instance ``index.html`` uses relative ``projects/<slug>.html``
    hrefs so the folder is portable (zip, move, serve as static files).
    """
    # Always print text to stdout
    print(_sm().render_text(instance_report))

    root = _instance_export_root()
    root.mkdir(parents=True, exist_ok=True)

    # Note which project slugs will have a drilldown so the HTML renderer
    # knows which rows to hyperlink vs render as plain text.
    drilldown_slugs: set[str] = set()
    if drilldown:
        projects_sub = root / "projects"
        projects_sub.mkdir(parents=True, exist_ok=True)

    written: list[tuple[str, Path]] = []
    for fmt in formats or []:
        if fmt == "text":
            continue
        if fmt == "html":
            instance_report_for_html = dict(instance_report)
            instance_report_for_html["_drilldown_slugs"] = \
                {pr["slug"] for pr in project_reports} if drilldown else set()
            content = _sm().render_html(instance_report_for_html, variant="single",
                                   chart_lib=chart_lib,
                                   idle_gap_minutes=idle_gap_minutes)
        else:
            content = _sm()._RENDERERS[fmt](instance_report)
        out = root / f"index.{_EXTENSIONS[fmt]}"
        out.write_text(content, encoding="utf-8")
        if share_safe:
            out.chmod(0o600)
        written.append((fmt, out))
        print(f"[export] {fmt.upper():4} → {out}", file=sys.stderr)
        if evidence and fmt == "json":
            sha_p, prov_p = _sm()._write_evidence_pack(
                out, share_safe=share_safe,
                provenance_extra={
                    "mode": instance_report.get("mode"),
                    "slug": instance_report.get("slug"),
                    "project_count": instance_report.get("project_count", 0),
                },
            )
            print(f"[export] EVID → {sha_p}", file=sys.stderr)
            print(f"[export] EVID → {prov_p}", file=sys.stderr)

    if drilldown:
        total = len(project_reports)
        for i, pr in enumerate(project_reports, 1):
            slug = pr["slug"]
            print(f"[{i}/{total}] Rendering drilldown: {slug}...",
                  file=sys.stderr)
            try:
                dash_html = _sm().render_html(pr, variant="dashboard",
                                         nav_sibling=f"{slug}_detail.html",
                                         chart_lib=chart_lib,
                                         idle_gap_minutes=idle_gap_minutes)
                det_html  = _sm().render_html(pr, variant="detail",
                                         nav_sibling=f"{slug}_dashboard.html",
                                         chart_lib=chart_lib,
                                         idle_gap_minutes=idle_gap_minutes)
            except (ValueError, KeyError, RuntimeError) as exc:
                print(f"[warn] {slug}: HTML render failed ({exc})",
                      file=sys.stderr)
                continue
            dash_p = root / "projects" / f"{slug}_dashboard.html"
            det_p  = root / "projects" / f"{slug}_detail.html"
            dash_p.write_text(dash_html, encoding="utf-8")
            det_p.write_text(det_html, encoding="utf-8")
            if share_safe:
                dash_p.chmod(0o600)
                det_p.chmod(0o600)
            drilldown_slugs.add(slug)
        print(f"[export] per-project drilldowns → {root / 'projects'}",
              file=sys.stderr)


def _render_instance_text(report: dict) -> str:
    """Terse ASCII summary for stdout: header cards, top 10 projects by
    cost, aggregated models, date range. Always emitted to stdout by the
    instance dispatcher (mirrors ``render_text`` for the other modes)."""
    out = io.StringIO()

    def p(*args, **kw):
        print(*args, **kw, file=out)

    totals = report.get("totals", {})
    projects = report.get("projects", [])
    models = report.get("models", {})
    tz_label = report.get("tz_label", "UTC")
    generated = _sm()._fmt_generated_at(report)

    p("=" * 78)
    p("  Claude Code — all-projects instance dashboard")
    p("=" * 78)
    p(f"  Generated : {generated}")
    p(f"  Scanning  : {report.get('projects_dir', '?')}")
    p(f"  Timezone  : {tz_label}")
    p(f"  Projects  : {report.get('project_count', 0)}")
    p(f"  Sessions  : {report.get('session_count', 0)}")
    p(f"  Turns     : {totals.get('turns', 0):,}")
    p(f"  Cost (USD): ${float(totals.get('cost', 0.0)):.4f}")
    p(f"  Input     : {totals.get('input', 0):,} new / "
      f"{totals.get('cache_read', 0):,} cache_read")
    p(f"  Output    : {totals.get('output', 0):,}")
    p(f"  Cache wr  : {totals.get('cache_write', 0):,} "
      f"(5m {totals.get('cache_write_5m', 0):,}, "
      f"1h {totals.get('cache_write_1h', 0):,})")
    p("")
    if projects:
        p(f"Top projects by cost (showing up to 10 of {len(projects)}):")
        p(f"  {'#':>2}  {'Slug':<42}  {'Sessions':>8}  {'Turns':>6}  {'Cost $':>10}")
        p("  " + "-" * 74)
        for i, proj in enumerate(projects[:10], 1):
            slug = proj["slug"]
            if len(slug) > 42:
                slug = slug[:39] + "..."
            p(f"  {i:>2}  {slug:<42}  "
              f"{proj.get('session_count', 0):>8}  "
              f"{proj.get('turn_count', 0):>6}  "
              f"${proj.get('cost_usd', 0.0):>9.4f}")
        p("")
    if models:
        p("Models used (aggregated):")
        for name, info in sorted(models.items(),
                                  key=lambda kv: -int(kv[1].get("turns", 0))):
            turns = info.get("turns", 0)
            cost = float(info.get("cost_usd", 0.0))
            p(f"  {name:<44}  {turns:>6} turns  ${cost:>9.4f}")
        p("")
    return out.getvalue()
def _render_instance_csv(report: dict) -> str:
    """One row per session across all projects, with a ``project_slug``
    column. Per-turn rows would explode at instance scale; per-session
    rows give a CSV that's pivotable in Excel without being unwieldy."""
    out = io.StringIO()
    w = csv_mod.writer(out)
    w.writerow([f"# Session Metrics skill v{report.get('skill_version', '?')}",
                report.get("generated_at", ""), report.get("mode", "")])
    w.writerow([
        "project_slug", "session_id", "first_ts", "last_ts",
        "duration_seconds", "turn_count",
        "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_write_tokens",
        "cache_write_5m_tokens", "cache_write_1h_tokens",
        "total_tokens", "cost_usd",
    ])
    for proj in report.get("projects", []):
        slug = proj["slug"]
        for s in proj.get("sessions", []):
            st = s.get("subtotal", {}) or {}
            w.writerow([
                slug, s.get("session_id", ""),
                s.get("first_ts", ""), s.get("last_ts", ""),
                s.get("duration_seconds", 0),
                s.get("turn_count", 0),
                st.get("input", 0), st.get("output", 0),
                st.get("cache_read", 0), st.get("cache_write", 0),
                st.get("cache_write_5m", 0), st.get("cache_write_1h", 0),
                st.get("total", 0),
                f"{float(st.get('cost', 0.0)):.6f}",
            ])

    # Instance-level summary row and projects-breakdown section
    totals = report.get("totals", {}) or {}
    w.writerow([])
    w.writerow(["# INSTANCE TOTALS"])
    w.writerow(["project_count", "session_count", "turn_count",
                 "input", "output", "cache_read", "cache_write",
                 "cost_usd"])
    w.writerow([
        report.get("project_count", 0),
        report.get("session_count", 0),
        totals.get("turns", 0),
        totals.get("input", 0), totals.get("output", 0),
        totals.get("cache_read", 0), totals.get("cache_write", 0),
        f"{float(totals.get('cost', 0.0)):.6f}",
    ])
    w.writerow([])
    w.writerow(["# PROJECTS BREAKDOWN (sorted by cost desc)"])
    w.writerow(["project_slug", "friendly_path", "sessions",
                 "turns", "first_ts", "last_ts", "cost_usd"])
    for proj in report.get("projects", []):
        w.writerow([
            proj["slug"],
            proj.get("friendly_path", ""),
            proj.get("session_count", 0),
            proj.get("turn_count", 0),
            proj.get("first_ts", ""),
            proj.get("last_ts", ""),
            f"{float(proj.get('cost_usd', 0.0)):.6f}",
        ])
    return out.getvalue()


def _render_instance_md(report: dict) -> str:
    """GitHub-flavored Markdown for instance scope: summary cards, projects
    breakdown, aggregated models, weekly/hour-of-day sections."""
    out = io.StringIO()

    def p(*args, **kw):
        print(*args, **kw, file=out)

    totals = report.get("totals", {})
    projects = report.get("projects", [])
    models = report.get("models", {})
    tz_label = report.get("tz_label", "UTC")
    generated = _sm()._fmt_generated_at(report)
    skill_version = report.get("skill_version", "?")

    p("# Session Metrics — all projects")
    p()
    p(f"Generated: {generated}  |  Mode: instance  |  "
      f"Scanning: `{report.get('projects_dir', '?')}`  |  Skill: v{skill_version}")
    p()

    # Summary cards
    p("## Summary")
    p()
    p("| Metric | Value |")
    p("|--------|-------|")
    p(f"| Projects | {report.get('project_count', 0)} |")
    p(f"| Sessions | {report.get('session_count', 0)} |")
    p(f"| Total turns | {totals.get('turns', 0):,} |")
    p(f"| Total cost | ${float(totals.get('cost', 0.0)):.4f} |")
    _share_line = _sm()._build_subagent_share_md(
        report.get("subagent_share_stats") or _sm()._compute_subagent_share(report))
    if _share_line:
        p(_share_line)
    p(f"| Input tokens (new) | {totals.get('input', 0):,} |")
    p(f"| Output tokens | {totals.get('output', 0):,} |")
    p(f"| Cache read tokens | {totals.get('cache_read', 0):,} |")
    p(f"| Cache write tokens | {totals.get('cache_write', 0):,} |")
    _ics = report.get("compaction_summary") or {}
    if int(_ics.get("boundary_count", 0) or 0) > 0:
        _split = []
        if _ics.get("auto_count"):
            _split.append(f"{_ics['auto_count']} auto")
        if _ics.get("manual_count"):
            _split.append(f"{_ics['manual_count']} manual")
        _split_str = f" ({', '.join(_split)})" if _split else ""
        p(f"| Context compactions | {_ics['boundary_count']}{_split_str} · "
          f"{int(_ics.get('total_reclaimed_tokens', 0) or 0):,} tokens reclaimed |")
    if totals.get("cache_write_1h", 0) > 0:
        pct_1h = 100 * totals["cache_write_1h"] / max(1, totals["cache_write"])
        p(f"| Cache TTL mix (1h share of writes) | {pct_1h:.1f}% |")
    if projects:
        top = projects[0]
        p(f"| Top project by cost | `{top['slug']}` "
          f"(${top.get('cost_usd', 0.0):.4f}) |")
    if models:
        top_model = max(models.items(),
                        key=lambda kv: float(kv[1].get("cost_usd", 0.0)))[0]
        p(f"| Top model by cost | `{top_model}` |")
    p()

    # v1.26.0: within-session split table at instance scope. Sources
    # the precomputed list from ``_build_instance_report``; renderer
    # returns "" when no session qualifies.
    _ws_split_md = _sm()._build_within_session_split_md(
        report.get("subagent_within_session_split") or [])
    if _ws_split_md:
        p(_ws_split_md)

    # Projects breakdown — sorted by cost desc (already sorted by builder)
    p("## Projects breakdown")
    p()
    p("| # | Project | Friendly path | Sessions | Turns | "
      "First | Last | Cost $ |")
    p("|--:|---------|---------------|---------:|------:|"
      "-------|------|-------:|")
    for i, proj in enumerate(projects, 1):
        p(f"| {i} | `{proj['slug']}` | `{proj.get('friendly_path', '')}` "
          f"| {proj.get('session_count', 0):,} "
          f"| {proj.get('turn_count', 0):,} "
          f"| {proj.get('first_ts', '')} | {proj.get('last_ts', '')} "
          f"| ${proj.get('cost_usd', 0.0):.4f} |")
    p()

    # Models table (aggregated)
    if models:
        p("## Models (aggregated)")
        p()
        p("| Model | Turns | Input | Output | CacheRd | CacheWr | Cost $ |")
        p("|-------|------:|------:|-------:|--------:|--------:|-------:|")
        for name, info in sorted(models.items(),
                                  key=lambda kv: -float(kv[1].get("cost_usd", 0.0))):
            p(f"| `{name}` | {int(info.get('turns', 0)):,} "
              f"| {int(info.get('input_tokens', 0)):,} "
              f"| {int(info.get('output_tokens', 0)):,} "
              f"| {int(info.get('cache_read_tokens', 0)):,} "
              f"| {int(info.get('cache_write_tokens', 0)):,} "
              f"| ${float(info.get('cost_usd', 0.0)):.4f} |")
        p()

    # Time-of-day (aggregated)
    tod = report.get("time_of_day", {})
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

    # 5-hour session blocks (aggregated)
    blocks = report.get("session_blocks", []) or []
    summary = report.get("block_summary", {}) or {}
    if blocks:
        p(f"## 5-hour session blocks (aggregated, {tz_label})")
        p()
        p(f"- Trailing 7 days: **{summary.get('trailing_7', 0)}** blocks")
        p(f"- Trailing 14 days: **{summary.get('trailing_14', 0)}** blocks")
        p(f"- Trailing 30 days: **{summary.get('trailing_30', 0)}** blocks")
        p(f"- All time: **{summary.get('total', len(blocks))}** blocks")
        p()

    # Per-project sub-sections with per-session subtotals
    p("## Per-project session subtotals")
    p()
    for proj in projects:
        p(f"### `{proj['slug']}`")
        p()
        p(f"`{proj.get('friendly_path', '')}` &nbsp;·&nbsp; "
          f"{proj.get('session_count', 0)} sessions &nbsp;·&nbsp; "
          f"{proj.get('turn_count', 0):,} turns &nbsp;·&nbsp; "
          f"**${proj.get('cost_usd', 0.0):.4f}**")
        p()
        sessions = proj.get("sessions", [])
        if sessions:
            p("| # | Session | First | Last | Turns | Input | Output | "
              "CacheRd | CacheWr | Cost $ |")
            p("|--:|---------|-------|------|------:|------:|-------:|"
              "--------:|--------:|-------:|")
            for i, s in enumerate(sessions, 1):
                st = s.get("subtotal", {}) or {}
                p(f"| {i} | `{s.get('session_id', '')[:8]}…` "
                  f"| {s.get('first_ts', '')} | {s.get('last_ts', '')} "
                  f"| {s.get('turn_count', 0):,} "
                  f"| {int(st.get('input', 0)):,} "
                  f"| {int(st.get('output', 0)):,} "
                  f"| {int(st.get('cache_read', 0)):,} "
                  f"| {int(st.get('cache_write', 0)):,} "
                  f"| ${float(st.get('cost', 0.0)):.4f} |")
            p()
    return out.getvalue()


def _render_instance_html(report: dict, chart_lib: str = "highcharts") -> str:
    """Full instance dashboard HTML.

    Reuses the same visual language (dark theme, cards, tables) as the
    session/project renderer but:
      - suppresses the per-turn drawer CSS/JS (no per-turn data at this
        scope — users drill down into ``projects/<slug>.html`` for that)
      - replaces the timeline-of-turns chart with a **daily cost**
        timeline stacked by the top 10 projects (via the existing chart
        renderers, whose contract is a list of turn-ish dicts)
      - replaces the session timeline table with a **projects breakdown**
        table sorted by cost descending; each row links to the
        corresponding drilldown HTML when present in ``_drilldown_slugs``
    """
    totals = report.get("totals", {}) or {}
    projects = report.get("projects", []) or []
    models = report.get("models", {}) or {}
    tz_label = report.get("tz_label", "UTC")
    tz_offset = report.get("tz_offset_hours", 0.0)
    generated = _sm()._fmt_generated_at(report)
    skill_version = report.get("skill_version", "?")
    projects_dir = html_mod.escape(str(report.get("projects_dir", "?")))
    drilldown_slugs = report.get("_drilldown_slugs") or set()

    # ---- Chart: synthesise turn-ish dicts from per-day buckets -------------
    # The existing CHART_RENDERERS all expect ``list[dict]`` where each dict
    # carries ``timestamp``, ``cost_usd``, ``total_tokens``, and a ``model``
    # key. We reduce the daily buckets to one synthetic "turn" per day so
    # the same renderer contract applies without any chart-lib rework.
    daily = report.get("daily") or []
    synth_turns: list[dict] = []
    for d in daily:
        synth_turns.append({
            "timestamp":     f"{d['date']}T12:00:00Z",
            "timestamp_fmt": d["date"],
            "cost_usd":      float(d.get("cost", 0.0)),
            "total_tokens":  int(d.get("tokens", 0)),
            # v1.14.1: pipe real per-day token buckets through to the
            # chart renderer. Prior to this change all four series were
            # hardcoded to 0, producing a flatlined stacked-bar chart
            # where only the Cost $ line carried real data.
            "input_tokens":       int(d.get("input", 0)),
            "output_tokens":      int(d.get("output", 0)),
            "cache_read_tokens":  int(d.get("cache_read", 0)),
            "cache_write_tokens": int(d.get("cache_write", 0)),
            "model":         "instance",
            "index":         0,
        })
    # Instance page shows a daily cost rail (not the Highcharts 3D chart and
    # not the per-session chartrail — each is wrong at instance scope).
    daily_cost_rail_html   = _sm()._build_daily_cost_rail_html(daily)
    daily_cost_rail_script = _sm()._daily_cost_rail_script() if daily_cost_rail_html else ""

    # ---- Summary cards -----------------------------------------------------
    top_project = projects[0] if projects else None
    top_model_name = ""
    if models:
        top_model_name = max(models.items(),
                              key=lambda kv: float(kv[1].get("cost_usd", 0.0)))[0]

    active_days = len({d["date"] for d in daily}) if daily else 0

    cards = [
        (f"${float(totals.get('cost', 0.0)):.2f}", "Total cost"),
        (f"{totals.get('turns', 0):,}",            "Total turns"),
        (f"{report.get('project_count', 0):,}",    "Projects"),
        (f"{report.get('session_count', 0):,}",    "Sessions"),
        (f"{active_days:,}",                        "Active days"),
        (f"{totals.get('input', 0):,}",             "Input tokens (new)"),
        (f"{totals.get('output', 0):,}",            "Output tokens"),
        (f"{totals.get('cache_read', 0):,}",        "Cache read"),
        (f"{totals.get('cache_write', 0):,}",       "Cache write"),
    ]
    # Q1: instance-wide context-compaction card. Auto-hides when none recorded.
    _ics = report.get("compaction_summary") or {}
    if int(_ics.get("boundary_count", 0) or 0) > 0:
        cards.append((
            f"{_ics['boundary_count']} · "
            f"{int(_ics.get('total_reclaimed_tokens', 0) or 0):,} reclaimed",
            "Context compactions",
        ))
    if top_project:
        cards.append((f"`{top_project['slug'][:18]}…`"
                       if len(top_project["slug"]) > 18
                       else f"`{top_project['slug']}`",
                      "Top project by cost"))
    if top_model_name:
        cards.append((f"{top_model_name[:20]}…"
                       if len(top_model_name) > 20 else top_model_name,
                      "Top model by cost"))

    cards_html_parts = []
    for idx, (val, lbl) in enumerate(cards):
        safe_val = html_mod.escape(val)
        safe_lbl = html_mod.escape(lbl)
        # First card is "Total cost" — elevate to .featured
        kpi_cls = "kpi featured cat-tokens" if idx == 0 else "kpi cat-tokens"
        cards_html_parts.append(
            f'<div class="{kpi_cls}"><div class="kpi-label">{safe_lbl}</div>'
            f'<div class="kpi-val">{safe_val}</div></div>'
        )
    # v1.26.0: subagent share KPI card at instance scope. Read from
    # the precomputed stats stashed by ``_build_instance_report``.
    _sa_stats = (report.get("subagent_share_stats")
                 or _sm()._compute_subagent_share(report))
    inst_share_card = _sm()._build_subagent_share_card_html(_sa_stats)
    inst_turn_share_card = _sm()._build_subagent_turn_share_card_html(_sa_stats)
    inst_plan_leverage_card = _sm()._build_plan_leverage_card_html(
        totals, report.get("plan_cost"))
    summary_cards_html = (
        f'<div class="kpi-grid">{"".join(cards_html_parts)}'
        f'{inst_plan_leverage_card}{inst_share_card}{inst_turn_share_card}</div>'
    )

    # ---- Reused insights helpers ------------------------------------------
    # Each of these already handles the "empty" case gracefully by returning
    # "" when the underlying data is absent — so we can drop them in without
    # additional conditionals.
    window_html = _sm()._build_window_ribbon_html(report.get("window_stats", []) or [])
    rollup_html = _sm()._build_weekly_rollup_html(report.get("weekly_rollup", {}))
    blocks_html = _sm()._build_session_blocks_html(
        report.get("session_blocks", []),
        report.get("block_summary", {}),
        tz_label, tz_offset,
    )
    tod_section = report.get("time_of_day", {}) or {}
    hod_html    = _sm()._build_hour_of_day_html(tod_section, tz_label, tz_offset)
    punchcard_html = _sm()._build_punchcard_html(tod_section, tz_label, tz_offset)
    heatmap_html = _sm()._build_tod_heatmap_html(tod_section, tz_label, tz_offset)

    insights_html = window_html + rollup_html + blocks_html + hod_html + punchcard_html + heatmap_html

    # Phase-A instance-level sections (v1.6.0).
    inst_by_skill_html = _sm()._build_by_skill_html(report.get("by_skill", []) or [])
    inst_by_subagent_type_html = _sm()._build_by_subagent_type_html(
        report.get("by_subagent_type", []) or [],
        subagents_included=bool(report.get("include_subagents", False)))
    inst_by_workflow_html = _sm()._build_by_workflow_html(
        report.get("by_workflow", []) or [], show_project=True)
    inst_cache_breaks_html = _sm()._build_cache_breaks_html(
        report.get("cache_breaks", []) or [],
        int(report.get("cache_break_threshold", _sm()._CACHE_BREAK_DEFAULT_THRESHOLD)),
    )
    # v1.26.0: instance-scope coverage + within-session split.
    inst_attribution_coverage_html = _sm()._build_attribution_coverage_html(
        report.get("subagent_share_stats")
        or _sm()._compute_subagent_share(report))
    inst_within_session_split_html = _sm()._build_within_session_split_html(
        report.get("subagent_within_session_split") or [])

    # ---- Projects breakdown table -----------------------------------------
    proj_rows_html_parts = []
    for i, proj in enumerate(projects, 1):
        slug = proj["slug"]
        slug_safe = html_mod.escape(slug)
        friendly = html_mod.escape(proj.get("friendly_path", ""))
        if slug in drilldown_slugs:
            name_cell = (
                f'<a class="drilldown" data-sm-nav href="projects/{slug_safe}_dashboard.html">'
                f'<code>{slug_safe}</code></a>'
            )
        else:
            name_cell = f'<code>{slug_safe}</code>'
        wd = proj.get("waste_dist") or {}
        _wn = sum(wd.values()) or 1
        if wd:
            waste_cells = (
                f'<td class="num">{wd.get("productive", 0) / _wn * 100:.0f}%</td>'
                f'<td class="num">{wd.get("retry_error", 0) / _wn * 100:.0f}%</td>'
                f'<td class="num">{wd.get("file_reread", 0) / _wn * 100:.0f}%</td>'
                f'<td class="num">{wd.get("oververbose_edit", 0) / _wn * 100:.0f}%</td>'
                f'<td class="num">{wd.get("dead_end", 0) / _wn * 100:.0f}%</td>'
            )
        else:
            waste_cells = '<td colspan="5" class="muted">—</td>'
        proj_rows_html_parts.append(
            f'<tr>'
            f'<td class="num">{i}</td>'
            f'<td>{name_cell}</td>'
            f'<td class="muted mono">{friendly}</td>'
            f'<td class="num">{proj.get("session_count", 0):,}</td>'
            f'<td class="num">{proj.get("turn_count", 0):,}</td>'
            f'<td class="ts">{html_mod.escape(proj.get("first_ts", ""))}</td>'
            f'<td class="ts">{html_mod.escape(proj.get("last_ts", ""))}</td>'
            f'<td class="cost">${float(proj.get("cost_usd", 0.0)):.4f}</td>'
            f'{waste_cells}'
            f'</tr>'
        )
    # Only show waste columns if at least one project has waste data
    any_waste = any(proj.get("waste_dist") for proj in projects)
    waste_th = (
        '<th class="num">Productive</th><th class="num">Retry</th>'
        '<th class="num">File Rrd</th><th class="num">Verbose</th>'
        '<th class="num">Stuck</th>'
    ) if any_waste else ""
    projects_table_html = (
        f'<section class="section">'
        f'<div class="section-title"><h2>Projects breakdown</h2>'
        f'<span class="hint">sorted by cost descending · click project to open drilldown</span></div>'
        f'<table class="timeline-table">'
        f'<thead><tr>'
        f'<th class="num">#</th><th>Project</th><th>Path</th>'
        f'<th class="num">Sessions</th><th class="num">Turns</th>'
        f'<th>First</th><th>Last</th><th class="num">Cost $</th>'
        f'{waste_th}'
        f'</tr></thead>'
        f'<tbody>{"".join(proj_rows_html_parts)}</tbody>'
        f'</table>'
        f'</section>'
    )

    # ---- Models table (aggregated) ----------------------------------------
    if models:
        model_rows_html_parts = []
        for name, info in sorted(models.items(),
                                  key=lambda kv: -float(kv[1].get("cost_usd", 0.0))):
            r = info.get("rates") or _sm()._pricing_for(name)
            model_rows_html_parts.append(
                f'<tr>'
                f'<td><code>{html_mod.escape(name)}</code></td>'
                f'<td class="num">{int(info.get("turns", 0)):,}</td>'
                f'<td class="num">{int(info.get("input_tokens", 0)):,}</td>'
                f'<td class="num">{int(info.get("output_tokens", 0)):,}</td>'
                f'<td class="num">{int(info.get("cache_read_tokens", 0)):,}</td>'
                f'<td class="num">{int(info.get("cache_write_tokens", 0)):,}</td>'
                f'<td class="num">${r["input"]:.2f}</td>'
                f'<td class="num">${r["output"]:.2f}</td>'
                f'<td class="num">${r["cache_read"]:.2f}</td>'
                f'<td class="num">${r["cache_write"]:.2f}</td>'
                f'<td class="cost">${float(info.get("cost_usd", 0.0)):.4f}</td>'
                f'</tr>'
            )
        models_table_html = (
            f'<section class="section">'
            f'<div class="section-title"><h2>Models (aggregated)</h2></div>'
            f'<table class="models-table">'
            f'<thead><tr>'
            f'<th>Model</th><th class="num">Turns</th>'
            f'<th class="num">Input</th><th class="num">Output</th>'
            f'<th class="num">CacheRd</th><th class="num">CacheWr</th>'
            f'<th class="num">$/M in</th><th class="num">$/M out</th>'
            f'<th class="num">$/M rd</th><th class="num">$/M wr</th>'
            f'<th class="num">Cost $</th>'
            f'</tr></thead>'
            f'<tbody>{"".join(model_rows_html_parts)}</tbody>'
            f'</table>'
            f'</section>'
        )
    else:
        models_table_html = ""

    page_title = "Session Metrics — all projects"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="chart-lib" content="{chart_lib}">
<title>{page_title}</title>
{_sm()._theme_css()}
{_sm()._theme_bootstrap_head_js()}
</head>
<body class="theme-console">
<div class="shell">
<header class="topbar">
  <div class="brand"><span class="dot"></span><span>session-metrics</span></div>
  <nav class="nav"><span class="navlink current">Instance</span>{_sm()._theme_picker_markup()}</nav>
</header>
<header class="page-header">
  <h1>{page_title}</h1>
  <p class="meta">Generated {generated} &nbsp;·&nbsp; Scanning: <code>{projects_dir}</code>
   &nbsp;·&nbsp; {report.get("project_count", 0)} projects,
   {report.get("session_count", 0)} sessions,
   {totals.get("turns", 0):,} turns &nbsp;·&nbsp; skill v{skill_version}</p>
</header>
{summary_cards_html}
{daily_cost_rail_html}
{inst_cache_breaks_html}
{inst_by_skill_html}
{inst_by_subagent_type_html}
{inst_by_workflow_html}
{inst_attribution_coverage_html}
{inst_within_session_split_html}
{projects_table_html}
{insights_html}
{models_table_html}
<footer class="foot">
  <span class="muted">session-metrics (instance) · {generated}</span>
</footer>
</div>
{daily_cost_rail_script}
{_sm()._theme_bootstrap_body_js()}
</body>
</html>"""

def _print_self_cost_summary(self_cost: dict | None) -> None:
    """Print a one-line `[self-cost]` stderr summary for the current run.

    Always rendered after the `[export]` lines so users see how much the
    skill itself has cost in this session before seeing any audit
    suggestion. The number reflects **prior** session-metrics turns in
    this session — the current run is not yet written to the JSONL when
    we read it.
    """
    if not self_cost or not isinstance(self_cost, dict):
        return
    turns  = int(self_cost.get("turns", 0) or 0)
    cost   = float(self_cost.get("cost_usd", 0.0) or 0.0)
    tokens = int(self_cost.get("total_tokens", 0) or 0)
    print(
        f"[self-cost] session-metrics consumed {turns} prior "
        f"turn{'s' if turns != 1 else ''} this session, ${cost:.4f}, "
        f"{tokens:,} tokens (current run not yet logged).",
        file=sys.stderr,
    )


def _dispatch(report: dict, formats: list[str],
               single_page: bool = False,
               chart_lib: str = "highcharts",
               idle_gap_minutes: int = 10,
               redact_user_prompts: bool = False,
               share_safe: bool = False,
               evidence: bool = False,
               no_workflow_detail: bool = False,
               task_companion_nav: bool = False) -> None:
    # Always render text to stdout
    print(_sm().render_text(report))

    is_compare = report.get("mode") == "compare"

    # One timestamp for the whole run, shared by dashboard / detail / the
    # workflow companion AND every _write_output format (json/md/csv/single
    # HTML), so all files for a run carry the same ``<stem>`` and sort
    # together in the export directory.
    run_ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    # Dynamic-workflow companion deep-dive: when an HTML (or Markdown) export
    # contains ≥1 workflow run, write a standalone ``<stem>_workflows.{html,md}``
    # alongside the main output — same timestamped ``<stem>`` as dashboard /
    # detail so the companion sorts next to them — and link the inline HTML
    # table to it (href set BEFORE render so it appears). Skipped for compare
    # mode (no companion), when suppressed, or when no workflow ran. The href
    # is stripped from JSON via its ``_`` prefix.
    if (not is_compare and not no_workflow_detail
            and (report.get("by_workflow") or [])
            and ("html" in formats or "md" in formats)):
        mode = report.get("mode", "session")
        if mode == "project":
            stem = f"project_{run_ts}"
        else:
            sid = (report.get("sessions") or [{}])[0].get("session_id", "session")
            stem = f"session_{str(sid)[:8]}_{run_ts}"
        _export_dir().mkdir(parents=True, exist_ok=True)
        if "html" in formats:
            companion_name = f"{stem}_workflows.html"
            report["_workflow_companion_href"] = companion_name
            companion_html = _sm()._build_workflow_companion_html(report)
            if companion_html:
                cp = _export_dir() / companion_name
                cp.write_text(companion_html, encoding="utf-8")
                if share_safe:
                    cp.chmod(0o600)
                print(f"[export] HTML (workflows) → {cp}", file=sys.stderr)
        if "md" in formats:
            companion_md = _sm()._build_workflow_companion_md(report)
            if companion_md:
                mp = _export_dir() / f"{stem}_workflows.md"
                mp.write_text(companion_md, encoding="utf-8")
                if share_safe:
                    mp.chmod(0o600)
                print(f"[export] MD   (workflows) → {mp}", file=sys.stderr)

    # Tasks-companion nav link. The Tasks page itself is generated post-export
    # by the task-breakdown flow (it needs an LLM to group request units), so
    # the script can't write it here — but when the caller signals it WILL be
    # generated (``--task-companion-nav``), point the dashboard/detail nav at
    # the deterministic ``<stem>_tasks.html`` filename so the button is present
    # when the page lands. Set BEFORE the render loop so the nav picks it up.
    if (task_companion_nav and not is_compare
            and (report.get("request_units") or [])
            and "html" in formats):
        _mode = report.get("mode", "session")
        _stem = (f"project_{run_ts}" if _mode == "project"
                 else f"session_{str((report.get('sessions') or [{}])[0].get('session_id', 'session'))[:8]}_{run_ts}")
        report["_tasks_companion_href"] = f"{_stem}_tasks.html"

    for fmt in formats:
        if fmt == "text":
            continue   # already printed
        if fmt == "html" and is_compare:
            # Compare HTML is always single-page — the report is compact
            # enough to read at a glance, and splitting dashboard/detail
            # would fragment the story (summary cards and per-turn table
            # are read together). ``--single-page`` / ``--chart-lib`` are
            # silently ignored for compare output.
            smc = sys.modules["session_metrics_compare"]
            content = smc.render_compare_html(
                report, redact_user_prompts=redact_user_prompts,
            )
            path = _write_output(fmt, content, report, explicit_ts=run_ts,
                                 share_safe=share_safe)
            print(f"[export] HTML (compare) → {path}", file=sys.stderr)
            continue
        if fmt == "html" and not single_page:
            # Split into two files. Dashboard references detail as a sibling
            # by filename-only href so file:// works without a server.
            mode = report["mode"]
            ts = run_ts
            stem = (f"project_{ts}" if mode == "project"
                    else f"session_{report['sessions'][0]['session_id'][:8]}_{ts}")
            dashboard_name = f"{stem}_dashboard.html"
            detail_name    = f"{stem}_detail.html"
            dash = _sm().render_html(report, variant="dashboard",
                                nav_sibling=detail_name, chart_lib=chart_lib,
                                idle_gap_minutes=idle_gap_minutes)
            det  = _sm().render_html(report, variant="detail",
                                nav_sibling=dashboard_name, chart_lib=chart_lib,
                                idle_gap_minutes=idle_gap_minutes)
            p1   = _export_dir() / dashboard_name
            p2   = _export_dir() / detail_name
            _export_dir().mkdir(parents=True, exist_ok=True)
            p1.write_text(dash, encoding="utf-8")
            p2.write_text(det,  encoding="utf-8")
            if share_safe:
                p1.chmod(0o600)
                p2.chmod(0o600)
            print(f"[export] HTML (dashboard) → {p1}", file=sys.stderr)
            print(f"[export] HTML (detail)    → {p2}", file=sys.stderr)
            continue
        if fmt == "html":
            content = _sm().render_html(report, variant="single", chart_lib=chart_lib,
                                   idle_gap_minutes=idle_gap_minutes)
        elif fmt == "json":
            content = _sm().render_json(report, redact_user_prompts=redact_user_prompts)
        else:
            content = _sm()._RENDERERS[fmt](report)
        path = _write_output(fmt, content, report, explicit_ts=run_ts,
                             share_safe=share_safe)
        print(f"[export] {fmt.upper():4} → {path}", file=sys.stderr)
        if evidence and fmt == "json":
            sha_p, prov_p = _sm()._write_evidence_pack(
                path, share_safe=share_safe,
                provenance_extra={
                    "mode": report.get("mode"),
                    "slug": report.get("slug"),
                },
            )
            print(f"[export] EVID → {sha_p}", file=sys.stderr)
            print(f"[export] EVID → {prov_p}", file=sys.stderr)
