"""JSON rendering helpers for session-metrics."""
import json
import sys
from datetime import datetime, timezone


def _tod_for_json(tod: dict) -> dict:
    """Convert a ``time_of_day`` section for JSON export.

    Replaces internal ``epoch_secs`` (integer list) with human-readable
    ``utc_timestamps`` (ISO-8601 strings).  The conversion is O(n) but only
    runs once per export — no deep-copy of the full report is needed.
    """
    return {
        "utc_timestamps": [
            datetime.fromtimestamp(e, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            for e in tod.get("epoch_secs", [])
        ],
        "message_count": tod.get("message_count", 0),
        "buckets":       tod.get("buckets", {}),
        "hour_of_day":   tod.get("hour_of_day", {}),
        "weekday_hour":  tod.get("weekday_hour", {}),
        "offset_hours":  tod.get("offset_hours", 0.0),
    }


# Fields redacted from JSON exports under ``--redact-user-prompts``. These
# carry freeform user / assistant text that may contain PII; ``slash_command``
# and tool input previews are canonical / structured and stay visible so the
# export remains useful for cost analysis.
_REDACTED_TURN_FIELDS = (
    "prompt_text", "prompt_snippet",
    "assistant_text", "assistant_snippet",
)
_REDACTED_PLACEHOLDER = "[redacted]"


def _redact_turns_for_json(sessions: list[dict],
                           redact_tool_io: bool = False) -> list[dict]:
    """Return a shallow copy of ``sessions`` with freeform prompt/assistant
    text replaced by ``[redacted]`` on every turn. Empty fields stay empty so
    downstream filters (``if t.get("prompt_text"):``) keep their meaning.

    ``redact_tool_io`` (set under the ``--export-share-safe`` publication
    bundle) additionally masks ``tool_use_detail[].input_preview`` — which can
    echo Bash commands, grep patterns, URLs, and file paths — leaving the
    structured ``name`` / ``id`` fields intact for cost analysis. Under the
    plain ``--redact-user-prompts`` flag (cost-analysis use), tool-input
    previews stay visible.
    """
    out = []
    for s in sessions:
        new_turns = []
        for t in s.get("turns", []):
            redacted = {**t}
            for fld in _REDACTED_TURN_FIELDS:
                if redacted.get(fld):
                    redacted[fld] = _REDACTED_PLACEHOLDER
            # tool_result text can echo file contents / command output that may
            # carry PII — mask it too, leaving is_error + tool_use_id (the
            # cost-analysis-relevant structured fields) intact.
            if redacted.get("tool_results"):
                redacted["tool_results"] = [
                    {**tr, "text": _REDACTED_PLACEHOLDER} if tr.get("text") else tr
                    for tr in redacted["tool_results"]
                ]
            if redact_tool_io and redacted.get("tool_use_detail"):
                redacted["tool_use_detail"] = [
                    {**td, "input_preview": _REDACTED_PLACEHOLDER}
                    if td.get("input_preview") else td
                    for td in redacted["tool_use_detail"]
                ]
            new_turns.append(redacted)
        out.append({**s, "turns": new_turns})
    return out


def _redact_workflows_for_json(by_workflow: list[dict]) -> list[dict]:
    """Mask the freeform ``promptPreview`` / ``resultPreview`` on each workflow
    agent detail under the ``--export-share-safe`` bundle. These can carry source
    text, paths, or agent output; the structured agent metadata stays intact."""
    out = []
    for wf in by_workflow:
        details = wf.get("agent_details")
        if not details:
            out.append(wf)
            continue
        new_details = [
            {**d,
             **({"promptPreview": _REDACTED_PLACEHOLDER} if d.get("promptPreview") else {}),
             **({"resultPreview": _REDACTED_PLACEHOLDER} if d.get("resultPreview") else {})}
            for d in details
        ]
        out.append({**wf, "agent_details": new_details})
    return out


def _redact_request_units_for_json(units: list[dict]) -> list[dict]:
    """Return a shallow copy of ``units`` with the anchor prompt text masked.

    Mirrors ``_redact_turns_for_json`` for the top-level ``request_units``
    list, which carries its own ``prompt_text`` / ``prompt_snippet`` copies."""
    out = []
    for u in units:
        red = {**u}
        for fld in ("prompt_text", "prompt_snippet"):
            if red.get(fld):
                red[fld] = _REDACTED_PLACEHOLDER
        out.append(red)
    return out


def render_json(report: dict, *, redact_user_prompts: bool = False,
                redact_tool_io: bool = False) -> str:
    """Render the full report as indented JSON.

    Internal ``epoch_secs`` lists in ``time_of_day`` sections are converted to
    ISO-8601 ``utc_timestamps`` for human readability.  The transform uses a
    shallow copy of the report — session turns, subtotals, and model dicts are
    shared by reference to avoid copying ~thousands of turn record dicts.

    ``redact_user_prompts`` masks ``prompt_text`` / ``prompt_snippet`` and
    ``assistant_text`` / ``assistant_snippet`` on every turn with
    ``[redacted]``. Tool inputs, slash-command names, and structured cost /
    token fields stay visible (cost-analysis use). Instance-scope JSON has no
    per-turn records, so the flag is a no-op there.

    ``redact_tool_io`` (set under the ``--export-share-safe`` publication
    bundle) ADDITIONALLY masks ``tool_use_detail[].input_preview`` and the
    workflow ``agent_details[].promptPreview`` / ``resultPreview`` previews,
    which can carry Bash commands, file paths, URLs, source text, or agent
    output — closing the share-safe gap where a flag named for publication left
    those previews intact.
    """
    if report.get("mode") == "compare":
        return sys.modules["session_metrics_compare"].render_compare_json(report)
    if report.get("mode") == "instance":
        return _render_instance_json(report)
    # Shallow-transform: only replace time_of_day sections
    export = {**report}
    # Transient render-only hint (companion filename) — keep out of the JSON
    # so machine consumers see a stable schema.
    export.pop("_workflow_companion_href", None)
    export.pop("_tasks_companion_href", None)
    if "time_of_day" in export:
        export["time_of_day"] = _tod_for_json(export["time_of_day"])
    if "sessions" in export:
        sessions = export["sessions"]
        if redact_user_prompts or redact_tool_io:
            sessions = _redact_turns_for_json(sessions, redact_tool_io=redact_tool_io)
        export["sessions"] = [
            {**s, "time_of_day": _tod_for_json(s["time_of_day"])}
            if "time_of_day" in s else s
            for s in sessions
        ]
    # Under the share-safe bundle, also scrub workflow agent previews.
    if redact_tool_io and export.get("by_workflow"):
        export["by_workflow"] = _redact_workflows_for_json(export["by_workflow"])
    # Request units carry their own copy of the anchor prompt text — redact
    # it under the same flag so the per-request breakdown is share-safe too.
    if redact_user_prompts and export.get("request_units"):
        export["request_units"] = _redact_request_units_for_json(
            export["request_units"])
    # allow_nan=False: refuse to emit non-standard NaN/Infinity tokens (invalid
    # per the JSON spec — strict parsers reject them). A finite-cost invariant
    # holds in normal runs; this turns a silently-malformed export into a loud
    # error if a poisoned value ever reaches here (see _load_pricing_supplement).
    return json.dumps(export, indent=2, allow_nan=False)


def _render_instance_json(report: dict) -> str:
    """Serialise the full instance report as indented JSON.

    Per-turn records are never retained at instance scope so the JSON
    stays bounded even for users with hundreds of sessions — only
    per-session summaries, per-project summaries, and cross-project
    aggregates appear.
    """
    export = {k: v for k, v in report.items()
              if not k.startswith("_")}  # drop transient _drilldown_slugs etc.
    # Convert time_of_day epoch lists to human-readable timestamps
    if "time_of_day" in export:
        export["time_of_day"] = _tod_for_json(export["time_of_day"])
    # allow_nan=False — see the session-scope export above: fail loud rather
    # than emit invalid NaN/Infinity JSON tokens.
    return json.dumps(export, indent=2, default=str, allow_nan=False)
