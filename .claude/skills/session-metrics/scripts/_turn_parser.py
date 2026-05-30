"""Turn extraction and per-turn record construction for session-metrics."""
import json
import re
import sys
from datetime import timedelta, timezone

from _dt import _parse_iso_dt


def _sm():
    """Return the session_metrics module (deferred — fully loaded by call time)."""
    return sys.modules["session_metrics"]


# ---------------------------------------------------------------------------
# Resume-marker detection
# ---------------------------------------------------------------------------
# Identifies synthetic no-op turns written into the JSONL by claude -c / the
# desktop auto-continue client. Marked as is_resume_marker in turn records so
# downstream aggregators can skip them rather than counting them as a billable
# row.
#
# 1. `/exit` local-command triplet replayed by `claude -c` into the resumed
#    JSONL (Session 22 discovery). Matched via _EXIT_CMD_MARKER in a
#    plain-string user content.
# 2. An `isMeta` user entry with text `Continue from where you left off.`
#    (Session 34 discovery) — the desktop client injects this placeholder
#    pair when an auto-continue attempt couldn't reach the backend (e.g.
#    five-hour rate-limit window). The user can't type `isMeta`, and the
#    synthetic self-reply `No response requested.` makes the pair
#    unambiguous. Matched via _CONTINUE_FROM_RESUME_MARKER in a
#    text-block list user content.
#
# See CLAUDE-session-metrics-development-history.md S22 for the original
# corpus-scan data; the S34 scan confirmed 3 new disjoint matches across
# 7,731 JSONLs with zero overlap into unrelated synthetic flows.
_EXIT_CMD_MARKER = "<command-name>/exit</command-name>"
_CLEAR_CMD_MARKER = "<command-name>/clear</command-name>"
_CONTINUE_FROM_RESUME_MARKER = "Continue from where you left off."
_RESUME_LOOKBACK_USER_ENTRIES = 10


def _resume_fingerprint_match(recent_user_contents: list) -> bool:
    """True if any recent user entry carries a resume-marker fingerprint."""
    for c in recent_user_contents:
        if isinstance(c, str) and _EXIT_CMD_MARKER in c:
            return True
        if isinstance(c, list):
            for block in c:
                if (isinstance(block, dict)
                        and block.get("type") == "text"
                        and _CONTINUE_FROM_RESUME_MARKER in (block.get("text") or "")):
                    return True
    return False


def _extract_turns(entries: list[dict]) -> list[dict]:
    """Deduplicate on message.id and return one entry per assistant turn.

    Claude Code writes a single assistant response across **multiple JSONL
    entries** that all share the same ``message.id`` and an identical
    ``usage`` dict, but each carries a **different single content block**
    (one thinking block, one text block, one tool_use block, etc.).  This
    is how Anthropic's streaming output is persisted.  Dedup strategy:

    - ``usage``, ``model``, and timestamp come from the **last** occurrence
      (canonical "message settled" snapshot; cost math was always correct
      because ``usage`` is constant across occurrences).
    - ``content`` is the **union** of content blocks across **every**
      occurrence (so the turn record reflects the full thinking + text +
      tool_use distribution the model actually emitted).  Empirically,
      each occurrence contributes exactly one distinct block and they never
      overlap; if Claude Code ever starts shipping cumulative snapshots
      alongside incremental ones, we'd need to dedup block-by-block here.

    Each returned entry has ``_preceding_user_content`` attached — the
    ``message.content`` of the user entry immediately before this turn's
    **first** occurrence in the raw stream (content-block counters use
    this to attribute ``tool_result`` / ``image`` blocks to the turn that
    consumed them).

    Also attaches ``_is_resume_marker``: True when the turn is a synthetic
    no-op whose preceding ``_RESUME_LOOKBACK_USER_ENTRIES`` user entries
    carry either of two high-precision fingerprints:

    - A ``/exit`` local-command triplet (``claude -c`` resume, Session 22).
    - A ``"Continue from where you left off."`` isMeta user entry (desktop
      auto-continue placeholder, Session 34 — typically a five-hour
      rate-limit backoff where the client couldn't reach the API).

    Precision is high (both fingerprints are client-generated and the
    ``<synthetic>`` assistant reply is unambiguous); recall is incomplete
    (resumes after Ctrl+C / crash leave no trace).
    """
    last_entry: dict[str, dict] = {}
    merged_content: dict[str, list] = {}
    preceding_user: dict[str, object] = {}
    # Per-turn predecessor timestamp — the ISO-8601 timestamp of the user or
    # tool_result entry immediately before this assistant turn's first
    # streaming chunk. Drives ``latency_seconds`` (the model's wall-clock
    # response time for this single turn). First-occurrence wins, mirroring
    # ``preceding_user`` above.
    preceding_user_ts: dict[str, str] = {}
    # Phase-B: links from a user entry's ``toolUseResult.agentId`` to the
    # ``tool_use_id`` of every ``tool_result`` block in its content. Indexed
    # by the *next* assistant ``msg_id`` so subagent attribution can map
    # ``tool_use.id → agentId`` after turn assembly.
    preceding_user_agent_links: dict[str, list[tuple[str, str]]] = {}
    resume_marker_msg_ids: set[str] = set()
    recent_user_contents: list[object] = []
    last_user_content = None
    last_user_timestamp: str = ""
    last_user_agent_links: list[tuple[str, str]] = []
    # Accumulators for content blocks across every user entry in the gap
    # between two assistant turns. Parallel Task tool_results land in N
    # separate user entries; without accumulation only the last entry's
    # blocks survive into ``_preceding_user_content`` and content-block
    # counts (tool_result / image) on the next assistant turn under-count.
    # ``gap_user_str`` preserves the rare string-form content (compaction
    # summaries) when no list-shaped content appeared in the gap.
    gap_user_blocks: list = []
    gap_user_str: str | None = None
    # Tracks slash commands seen in recent user entries so that skill-dispatch
    # flows (which inject two user entries: the raw slash command entry then the
    # SKILL.md payload) don't lose the slash command when the second entry
    # becomes the immediate predecessor of the assistant turn.
    last_user_slash_cmd: str = ""
    preceding_user_slash_cmd: dict[str, str] = {}
    clear_event_msg_ids: set[str] = set()
    _pending_clear_event: bool = False
    # Suppresses slash-command tracking while inside a local-command group.
    # Claude Code splits "/model"/"/clear" invocations into multiple consecutive
    # user entries (caveat, command-name, stdout); only the caveat entry carries
    # the local-command-caveat marker. We activate this flag on the caveat entry
    # and clear it when an assistant first-occurrence fires, so the command-name
    # and stdout entries are also suppressed without any per-entry string search.
    _local_cmd_group_active: bool = False
    for entry in entries:
        t = entry.get("type")
        if t == "user":
            msg = entry.get("message") or {}
            last_user_content = msg.get("content")
            _raw_str = last_user_content if isinstance(last_user_content, str) else ""
            if "local-command-caveat" in _raw_str:
                _local_cmd_group_active = True
            elif isinstance(last_user_content, list):
                for _blk in last_user_content:
                    if isinstance(_blk, dict) and "local-command-caveat" in (_blk.get("text") or ""):
                        _local_cmd_group_active = True
                        break
            if _CLEAR_CMD_MARKER in _raw_str:
                _pending_clear_event = True
            # Compaction summaries start with this sentinel. They contain quoted
            # transcript text (including <command-name> tags) that must not be
            # mistaken for a new slash-command invocation.
            _is_compaction_entry = _raw_str.startswith(
                "This session is being continued from a previous conversation"
            )
            if not _local_cmd_group_active and not _is_compaction_entry:
                candidate_slash = _extract_slash_command("", last_user_content)
                if candidate_slash:
                    last_user_slash_cmd = candidate_slash
            # Use the entry's own timestamp; do not fall back to the previous
            # user's. Empty/missing → blank, so downstream latency math
            # records ``None`` rather than fabricating a gap against an
            # earlier (unrelated) user turn.
            last_user_timestamp = entry.get("timestamp", "") or ""
            recent_user_contents.append(last_user_content)
            if len(recent_user_contents) > _RESUME_LOOKBACK_USER_ENTRIES:
                recent_user_contents.pop(0)
            # Phase-B: extract Agent/Task tool_result agentId linkage.
            # ``toolUseResult.agentId`` is a top-level field on the JSONL
            # entry that Claude Code synthesises when an Agent/Task
            # subagent completes. We pair it with every ``tool_result``
            # block's ``tool_use_id`` in the message content (typically
            # one block, but we scan all to be safe).
            agent_links: list[tuple[str, str]] = []
            tur = entry.get("toolUseResult")
            tur_agent_id = ""
            if isinstance(tur, dict):
                aid = tur.get("agentId")
                if isinstance(aid, str) and aid:
                    tur_agent_id = aid
            if tur_agent_id and isinstance(last_user_content, list):
                for _blk in last_user_content:
                    if isinstance(_blk, dict) and _blk.get("type") == "tool_result":
                        tuid = _blk.get("tool_use_id")
                        if isinstance(tuid, str) and tuid:
                            agent_links.append((tuid, tur_agent_id))
            last_user_agent_links.extend(agent_links)
            # Same accumulation for the message content blocks themselves so
            # tool_result / image counts on the next assistant turn include
            # every parallel-spawn user entry, not just the most recent one.
            # String content (compaction summary) preserved separately so the
            # downstream ``isinstance(user_raw, str)`` compaction guard still
            # fires when the gap held only a single string-form user entry.
            if isinstance(last_user_content, list):
                gap_user_blocks.extend(last_user_content)
            elif isinstance(last_user_content, str):
                gap_user_str = last_user_content
            continue
        if t != "assistant":
            continue
        # Null-safe on BOTH levels. `entry.get("message", {})` only defaults on a
        # MISSING key, so a present `"message": null` would yield None and crash
        # the membership test below; `or {}` collapses null to {} (matches the
        # user branch at :141). The `isinstance` guard then subsumes missing /
        # null / non-dict `usage` in one check — a present `"usage": null` would
        # otherwise pass a bare `"usage" not in msg` (key present) and crash
        # downstream at `_build_turn_record` (`u.get(...)` on None).
        msg = entry.get("message") or {}
        if not isinstance(msg.get("usage"), dict):
            continue
        msg_id = msg.get("id")
        if not msg_id:
            continue
        # Resume-marker detection runs once per msg_id (first occurrence);
        # streaming dupes of the same synthetic msg_id carry the same
        # preceding-user context by construction.
        if msg.get("model") == "<synthetic>" and msg_id not in resume_marker_msg_ids:
            if _resume_fingerprint_match(recent_user_contents):
                resume_marker_msg_ids.add(msg_id)
        # First-occurrence wins for the preceding user pointer — streaming
        # echo entries of the same msg_id don't see a new user prompt in
        # between, so the triggering user entry is the one we saw before
        # the first streaming chunk.
        if msg_id not in preceding_user:
            # Snapshot merged blocks across the gap when any list-shape content
            # appeared; fall back to the string-form content for compaction
            # summaries; fall back to the prior gap's last_user_content for the
            # rare back-to-back-assistants case (no user entry in this gap) so
            # existing semantics are preserved.
            if gap_user_blocks:
                preceding_user[msg_id] = list(gap_user_blocks)
            elif gap_user_str is not None:
                preceding_user[msg_id] = gap_user_str
            else:
                preceding_user[msg_id] = last_user_content
            preceding_user_ts[msg_id] = last_user_timestamp
            preceding_user_agent_links[msg_id] = list(last_user_agent_links)
            preceding_user_slash_cmd[msg_id] = last_user_slash_cmd
            if _pending_clear_event:
                clear_event_msg_ids.add(msg_id)
                _pending_clear_event = False
            last_user_slash_cmd = ""
            last_user_agent_links = []
            gap_user_blocks = []
            gap_user_str = None
            _local_cmd_group_active = False
        content = msg.get("content")
        if isinstance(content, list):
            merged_content.setdefault(msg_id, []).extend(content)
        last_entry[msg_id] = entry
    turns: list[dict] = []
    for msg_id, entry in last_entry.items():
        merged_msg = {**entry["message"], "content": merged_content.get(msg_id, [])}
        turns.append({
            **entry,
            "message": merged_msg,
            "_preceding_user_content": preceding_user.get(msg_id),
            "_preceding_user_slash_cmd": preceding_user_slash_cmd.get(msg_id, ""),
            "_preceding_user_timestamp": preceding_user_ts.get(msg_id, ""),
            "_preceding_user_agent_links": preceding_user_agent_links.get(msg_id, []),
            "_is_resume_marker": msg_id in resume_marker_msg_ids,
            "_is_clear_event": msg_id in clear_event_msg_ids,
        })
    turns.sort(key=lambda e: e.get("timestamp", ""))
    return turns


def _extract_compaction_events(entries: list[dict]) -> dict:
    """Extract context-compaction events from raw JSONL entries.

    Claude Code records a compaction as a ``system`` entry with
    ``subtype:"compact_boundary"`` carrying a ``compactMetadata`` object,
    immediately followed by a ``user`` entry with ``isCompactSummary:true``
    (the summary that starts with "This session is being continued…").
    These entries are ``type != "assistant"`` so ``_extract_turns`` drops
    them — this is the only place they are surfaced.

    Two manifestations (see CLAUDE-compaction-operations.md): a mid-session
    in-place boundary, or a resume-start head boundary at the top of a new
    session file. ``starts_with_summary`` flags the latter (the file *begins*
    as a continuation of a prior conversation).

    MAIN-SESSION boundaries only: subagents ALSO get compacted (their JSONLs
    carry their own ``compact_boundary`` entries — verified empirically), but
    those are internal to a one-shot agent run and don't affect the user's
    conversation flow or lineage, so entries tagged ``_subagent_agent_id``
    (set by ``_load_session`` when merging subagent logs) are skipped. This
    is what makes post-dedup extraction over the merged entries list safe.

    All ``compactMetadata`` fields are treated as OPTIONAL — older Claude Code
    builds omit ``preCompactDiscoveredTools``/``preservedSegment``/
    ``preservedMessages``. Returns a dict::

        {"boundaries": [ {kind, trigger, pre_tokens, post_tokens,
                          reclaimed_tokens, duration_ms, timestamp, uuid,
                          logical_parent_uuid, preserved_uuids,
                          discovered_tools}, … ],
         "starts_with_summary": bool}

    ``boundaries`` is ordered as encountered (a single file can hold several).
    """
    boundaries: list[dict] = []
    starts_with_summary = False
    seen_first_user = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # Skip merged subagent entries — subagents have their own compactions
        # but they're internal to the agent run, not main-session events.
        if entry.get("_subagent_agent_id"):
            continue
        etype = entry.get("type")
        # First user entry: does the file BEGIN as a continuation?
        if etype == "user" and not seen_first_user:
            seen_first_user = True
            if entry.get("isCompactSummary") is True:
                starts_with_summary = True
        if etype != "system" or entry.get("subtype") != "compact_boundary":
            continue
        cm = entry.get("compactMetadata")
        if not isinstance(cm, dict):
            cm = {}
        pre = cm.get("preTokens")
        post = cm.get("postTokens")
        reclaimed = (
            pre - post
            if isinstance(pre, int) and isinstance(post, int)
            else None
        )
        pm = cm.get("preservedMessages")
        if not isinstance(pm, dict):
            pm = {}
        # `uuids` is the file-present preserved subset; `allUuids` is NOT
        # file-safe (can carry sub-message/merged uuids with no entry).
        preserved_uuids = [u for u in (pm.get("uuids") or []) if isinstance(u, str)]
        discovered = [
            t for t in (cm.get("preCompactDiscoveredTools") or []) if isinstance(t, str)
        ]
        boundaries.append({
            "kind":                "boundary",
            "trigger":             cm.get("trigger"),  # "auto" | "manual" | None
            "pre_tokens":          pre,
            "post_tokens":         post,
            "reclaimed_tokens":    reclaimed,
            "duration_ms":         cm.get("durationMs"),
            "timestamp":           entry.get("timestamp", "") or "",
            "uuid":                entry.get("uuid", "") or "",
            "logical_parent_uuid": entry.get("logicalParentUuid", "") or "",
            "preserved_uuids":     preserved_uuids,
            "discovered_tools":    discovered,
        })
    return {"boundaries": boundaries, "starts_with_summary": starts_with_summary}


def _count_content_blocks(content) -> tuple[dict[str, int], list[str]]:
    """Count content blocks by type. Return (counts, tool_names).

    ``content`` is the ``message.content`` field, which is either a list of
    block dicts (normal case) or a plain string (rare: old-style user prompts)
    or missing entirely.  Non-list content has no structured blocks, so the
    returned counts are all zero.
    """
    counts = {"thinking": 0, "tool_use": 0, "text": 0,
              "tool_result": 0, "image": 0,
              "server_tool_use": 0, "advisor_tool_result": 0}
    names: list[str] = []
    if not isinstance(content, list):
        return counts, names
    for block in content:
        if not isinstance(block, dict):
            continue
        t = block.get("type", "")
        if t in counts:
            counts[t] += 1
        if t in ("tool_use", "server_tool_use"):
            name = block.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return counts, names


# ---------------------------------------------------------------------------
# Per-turn drill-down helpers
# ---------------------------------------------------------------------------
# These feed the HTML detail report's right-side drawer + Prompts section.
# All five are defensive against the JSONL's two observed user-content shapes
# (plain string OR list[block]) and return plain strings that are safe to
# HTML-escape at the point of insertion.

# `<command-name>/foo</command-name>` is the wrapped slash-command marker CC
# writes when the user types a local command. Unwrapped `/foo` appears when
# the user types a slash command as a chat message.
_SLASH_WRAPPED_RE  = re.compile(r"<command-name>\s*(/[A-Za-z][\w-]*)\s*</command-name>")
_SLASH_BARE_RE     = re.compile(r"^\s*(/[A-Za-z][\w-]*)\b")
# Stripped at prompt-extract time so the snippet shows the user's intent, not
# the plumbing. `<local-command-stdout>…</local-command-stdout>` wraps the
# stdout of a local command and isn't the user's typing.
_XML_MARKER_RE     = re.compile(
    r"<(?:command-name|command-message|command-args|local-command-stdout|"
    r"local-command-stderr|local-command-caveat|system-reminder)[^>]*>"
    r"[\s\S]*?</(?:command-name|command-message|command-args|local-command-stdout|"
    r"local-command-stderr|local-command-caveat|system-reminder)>",
    re.IGNORECASE,
)

# Bound on embedded assistant-text payload to keep the HTML JSON blob tractable
# even when a session has a few 10k-char monologues. Prompt text is bounded by
# the natural shape of user input and typically doesn't need a cap.
_ASSISTANT_TEXT_CAP = 2000
_PROMPT_TEXT_CAP   = 1000


def _truncate(text: str | None, n: int) -> str:
    """Slice to ``n`` characters, appending an ellipsis when truncated."""
    if text is None:
        return ""
    if len(text) <= n:
        return text
    # Prefer a clean break at whitespace within the last 20% of the window
    cut = text[:n].rstrip()
    return cut + "…"


def _extract_user_prompt_text(content) -> str:
    """Flatten a user-entry ``message.content`` to a single prompt string.

    Accepts either a plain string (rare: old-style prompts) or a list of
    content blocks. Strips XML markers (<command-name>, <local-command-stdout>,
    <system-reminder>, etc.) so the returned snippet reflects the user's
    intent, not the plumbing around it. Ignores ``tool_result`` / ``image``
    blocks — those aren't user typing and are already counted separately.
    """
    if isinstance(content, str):
        raw = content
    elif isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                txt = block.get("text")
                if isinstance(txt, str) and txt:
                    parts.append(txt)
        raw = "\n".join(parts)
    else:
        return ""
    # Strip XML markers (including their inner text) before collapsing whitespace.
    raw = _XML_MARKER_RE.sub("", raw).strip()
    # Collapse runs of whitespace so snippets don't waste characters on
    # indentation or blank lines.
    raw = re.sub(r"\s+", " ", raw)
    return raw


def _extract_slash_command(prompt_text: str, raw_content=None) -> str:
    """Return a leading slash-command name (``/clear``) or empty string.

    Checks the wrapped XML form first (matches even if ``prompt_text`` has
    been stripped of XML markers), then falls back to a bare `/foo` at the
    start of the user prompt. Returns "" when neither matches.
    """
    if isinstance(raw_content, str):
        m = _SLASH_WRAPPED_RE.search(raw_content)
        if m:
            return m.group(1)
    elif isinstance(raw_content, list):
        for block in raw_content:
            if isinstance(block, dict) and block.get("type") == "text":
                txt = block.get("text") or ""
                m = _SLASH_WRAPPED_RE.search(txt)
                if m:
                    return m.group(1)
    if isinstance(prompt_text, str):
        m = _SLASH_BARE_RE.match(prompt_text)
        if m:
            return m.group(1)
    return ""


def _extract_assistant_text(content) -> str:
    """Join all assistant ``text`` blocks into a single string.

    Ignores ``thinking`` blocks (signature-only anyway) and ``tool_use``
    blocks (captured separately in ``tool_use_detail``). Caps at
    ``_ASSISTANT_TEXT_CAP`` characters so the embedded JSON payload stays
    bounded for very long monologue turns.
    """
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            txt = block.get("text")
            if isinstance(txt, str) and txt:
                parts.append(txt)
    raw = "\n\n".join(parts).strip()
    if len(raw) > _ASSISTANT_TEXT_CAP:
        raw = raw[:_ASSISTANT_TEXT_CAP].rstrip() + "…"
    return raw


def _summarise_tool_input(name: str, tool_input) -> str:
    """One-line preview of a ``tool_use`` block's ``input`` dict.

    Picks the most meaningful field per tool to surface in the drawer's tool
    list. Falls back to a truncated ``repr`` for unknown tools. The returned
    string is plain text; escape at the point of insertion.
    """
    if not isinstance(tool_input, dict):
        return ""
    # Tool-specific fields that carry the actual "what did Claude do" signal.
    if name == "Bash":
        cmd = tool_input.get("command") or ""
        if isinstance(cmd, str):
            return cmd.splitlines()[0][:160] if cmd else ""
    if name in ("Read", "Write", "NotebookRead", "NotebookEdit"):
        p = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        return str(p)[:160]
    if name == "Edit":
        p = tool_input.get("file_path") or ""
        return str(p)[:160]
    if name == "Grep":
        pat = tool_input.get("pattern") or ""
        path = tool_input.get("path") or ""
        return f"{pat}" + (f"  in {path}" if path else "")
    if name == "Glob":
        return str(tool_input.get("pattern") or "")[:160]
    if name == "Agent" or name == "Task":
        return str(tool_input.get("description") or tool_input.get("subagent_type") or "")[:160]
    if name == "WebFetch" or name == "WebSearch":
        return str(tool_input.get("url") or tool_input.get("query") or "")[:160]
    if name == "TodoWrite":
        todos = tool_input.get("todos")
        if isinstance(todos, list):
            return f"{len(todos)} todo item(s)"
    # Generic fallback: best-effort short JSON
    try:
        j = json.dumps(tool_input, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        return ""
    return j[:160] + ("…" if len(j) > 160 else "")


# ---------------------------------------------------------------------------
# Cost helpers — deferred back-refs to monolith via _sm()
# ---------------------------------------------------------------------------

def _cache_write_split(u: dict) -> tuple[int, int]:
    """Return ``(tokens_5m, tokens_1h)`` for the cache write on this turn.

    Reads ``usage.cache_creation.ephemeral_{5m,1h}_input_tokens`` when the
    nested object is present. Legacy transcripts without ``cache_creation``
    fall back to treating the flat ``cache_creation_input_tokens`` total as
    5-minute-tier tokens — preserving pre-v1.2.0 cost math for those files.
    """
    cc = u.get("cache_creation")
    if isinstance(cc, dict):
        return (
            int(cc.get("ephemeral_5m_input_tokens", 0) or 0),
            int(cc.get("ephemeral_1h_input_tokens", 0) or 0),
        )
    return int(u.get("cache_creation_input_tokens", 0) or 0), 0


def _cost(u: dict, model: str) -> float:
    # Known limitation: fast-mode turns (Opus 4.6 research preview, usage.speed
    # == "fast") bill at 6x standard base rates. Not multiplied here — fast-mode
    # cost is therefore underestimated by 6x for those turns. See
    # references/pricing.md § "Fast mode" for the full note.
    r = _sm()._pricing_for(model)
    tokens_5m, tokens_1h = _cache_write_split(u)
    primary = (
        u.get("input_tokens", 0)              * r["input"]           / 1_000_000
        + u.get("output_tokens", 0)           * r["output"]          / 1_000_000
        + u.get("cache_read_input_tokens", 0) * r["cache_read"]      / 1_000_000
        + tokens_5m                           * r["cache_write"]     / 1_000_000
        + tokens_1h                           * r["cache_write_1h"]  / 1_000_000
    )
    # Advisor turns carry their own token counts in usage.iterations entries of
    # type "advisor_message". These are billed at the advisor model's list rates
    # with no prompt caching, and are NOT reflected in the top-level usage
    # fields — so we must accumulate them separately here.
    advisor = 0.0
    for it in u.get("iterations") or []:
        if it.get("type") == "advisor_message":
            # ``it.get("model", model)`` would return ``""`` when the key is
            # present but empty — fall through ``_pricing_for("")`` to the
            # default-pricing tier silently. ``or model`` collapses both
            # missing-key and empty-string to the parent turn's model so the
            # advisor charge tracks the parent's rate (the correct fallback
            # when the iteration record is partial).
            adv_rates = _sm()._pricing_for(it.get("model") or model)
            advisor += (
                it.get("input_tokens", 0)  * adv_rates["input"]  / 1_000_000
              + it.get("output_tokens", 0) * adv_rates["output"] / 1_000_000
            )
    return primary + advisor


def _advisor_info(u: dict, model: str) -> tuple[int, float, str | None, int, int]:
    """Extract advisor metadata from usage.iterations.

    Returns ``(call_count, advisor_cost_usd, advisor_model, input_tokens,
    output_tokens)`` for all ``advisor_message`` iterations in this turn.
    Returns all-zero/None when no advisor was called.

    ``model`` is the parent turn's model and acts as the rate fallback when
    an iteration carries no ``model`` field — same fallback path as
    ``_cost``. Without it the advisor cost would silently apply
    ``_DEFAULT_PRICING`` and diverge from ``_cost`` on the same record.
    """
    calls = 0
    cost = 0.0
    advisor_model: str | None = None
    inp = 0
    out = 0
    for it in u.get("iterations") or []:
        if it.get("type") == "advisor_message":
            calls += 1
            adv_model = it.get("model") or ""
            if adv_model and advisor_model is None:
                advisor_model = adv_model
            adv_rates = _sm()._pricing_for(adv_model or model)
            cost += (
                it.get("input_tokens", 0) * adv_rates["input"]  / 1_000_000
              + it.get("output_tokens", 0) * adv_rates["output"] / 1_000_000
            )
            inp += it.get("input_tokens", 0)
            out += it.get("output_tokens", 0)
    return calls, cost, advisor_model, inp, out


def _no_cache_cost(u: dict, model: str) -> float:
    r = _sm()._pricing_for(model)
    # Route the cache-creation token count via _cache_write_split for parity
    # with _cost (which also reads through the same helper). Empirically
    # equal today (55/55 turns per CLAUDE-activeContext.md:430-432), but
    # reading the flat ``cache_creation_input_tokens`` field directly here
    # would silently undercount if Anthropic ever stops populating it while
    # keeping the nested ``cache_creation.ephemeral_*`` fields.
    cw_5m, cw_1h = _cache_write_split(u)
    total_input = (
        u.get("input_tokens", 0)
        + u.get("cache_read_input_tokens", 0)
        + cw_5m + cw_1h
    )
    primary = (
        total_input * r["input"] / 1_000_000
        + u.get("output_tokens", 0) * r["output"] / 1_000_000
    )
    # Mirror the advisor loop in ``_cost``: advisor iterations carry their
    # own token counts and are NOT reflected in the top-level usage fields,
    # so they must be added to the no-cache baseline as well — otherwise
    # the "savings from caching" delta (cost vs no_cache_cost) is biased
    # downward on every advisor-using turn. Advisor iterations have no
    # cache fields, so the no-cache and cached forms are identical.
    advisor = 0.0
    for it in u.get("iterations") or []:
        if it.get("type") == "advisor_message":
            adv_rates = _sm()._pricing_for(it.get("model") or model)
            advisor += (
                it.get("input_tokens", 0)  * adv_rates["input"]  / 1_000_000
              + it.get("output_tokens", 0) * adv_rates["output"] / 1_000_000
            )
    return primary + advisor


# ---------------------------------------------------------------------------
# Turn record assembly
# ---------------------------------------------------------------------------

def _build_turn_record(global_index: int, entry: dict,
                       tz_offset_hours: float = 0.0) -> dict:
    msg = entry["message"]
    u = msg["usage"]
    model = msg.get("model", "unknown")
    inp = u.get("input_tokens", 0)
    out = u.get("output_tokens", 0)
    crd = u.get("cache_read_input_tokens", 0)
    cwr_5m, cwr_1h = _cache_write_split(u)
    cwr = cwr_5m + cwr_1h
    if cwr == 0:
        ttl = ""
    elif cwr_1h == 0:
        ttl = "5m"
    elif cwr_5m == 0:
        ttl = "1h"
    else:
        ttl = "mix"
    c = _cost(u, model)
    nc = _no_cache_cost(u, model)
    adv_calls, adv_cost, adv_model, adv_inp, adv_out = _advisor_info(u, model)
    # Content-block distribution: assistant blocks come from this turn's own
    # message.content; tool_result / image blocks are attributed from the user
    # entry that immediately preceded this turn in the raw JSONL stream.
    assist_content = msg.get("content")
    user_raw       = entry.get("_preceding_user_content")
    assist_counts, tool_names = _count_content_blocks(assist_content)
    user_counts, _ = _count_content_blocks(user_raw)
    content_blocks = {
        "thinking":             assist_counts["thinking"],
        "tool_use":             assist_counts["tool_use"],
        "text":                 assist_counts["text"],
        "tool_result":          user_counts["tool_result"],
        "image":                user_counts["image"],
        "server_tool_use":      assist_counts["server_tool_use"],
        "advisor_tool_result":  assist_counts["advisor_tool_result"],
    }
    # Per-turn drill-down payload: the user prompt that triggered this turn,
    # the assistant's text reply, and a tool-call list with input previews.
    # All three feed the HTML detail drawer + Prompts section. Resume-marker
    # turns keep empty strings here — the drawer excludes them anyway.
    prompt_text = _extract_user_prompt_text(user_raw)
    _raw_user_str = user_raw if isinstance(user_raw, str) else ""
    _user_is_compaction = _raw_user_str.startswith(
        "This session is being continued from a previous conversation"
    )
    slash_cmd   = (
        (not _user_is_compaction and _extract_slash_command(prompt_text, user_raw))
        or entry.get("_preceding_user_slash_cmd", "")
    )
    asst_text   = _extract_assistant_text(assist_content)
    tool_detail: list[dict] = []
    # Phase-A additions (v1.6.0): cross-turn signals for the skill/subagent-type
    # tables. Extracted once here so aggregators can walk ``turn_records``
    # without re-parsing content. Empty lists/string for main-session turns or
    # turns without the respective signal.
    skill_invocations: list[str] = []
    spawned_subagents: list[str] = []
    # Phase-B (v1.7.0): tool_use ids of Agent/Task spawn blocks on this
    # turn. Used by ``_attribute_subagent_tokens`` to map
    # ``tool_use_id → prompt_anchor_index`` so subagent tokens roll up
    # to the spawning user prompt.
    tool_use_ids: list[str] = []
    if isinstance(assist_content, list):
        for block in assist_content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            tool_detail.append({
                "name":          name if isinstance(name, str) else str(name),
                "input_preview": _summarise_tool_input(name, block.get("input")),
            })
            binput = block.get("input")
            if not isinstance(binput, dict):
                binput = {}
            if name == "Skill":
                sk = binput.get("skill")
                if isinstance(sk, str) and sk:
                    skill_invocations.append(sk)
            elif name in ("Agent", "Task"):
                st = binput.get("subagent_type")
                if isinstance(st, str) and st:
                    spawned_subagents.append(st)
                bid = block.get("id")
                if isinstance(bid, str) and bid:
                    tool_use_ids.append(bid)
    # When advisor was called, surface it in the drawer tool list so it appears
    # alongside Bash/Read etc. The actual advisor response is encrypted, so the
    # preview is a fixed label.
    if adv_calls > 0:
        tool_detail.append({
            "name":          "advisor",
            "input_preview": "advisor call",
        })
    # Subagent-type tag propagated from ``_load_session`` when the entry came
    # from a ``subagents/*.jsonl`` file. Main-session turns: empty string.
    subagent_type = str(entry.get("_subagent_type") or "")
    # Phase-B: filename-derived agentId (only present on subagent turns).
    subagent_agent_id = str(entry.get("_subagent_agent_id") or "")
    # Phase-B: ``(tool_use_id, agentId)`` pairs surfaced from the user
    # entry preceding this turn (set in ``_extract_turns``). Empty for
    # turns whose preceding user message was not an Agent/Task result.
    raw_links = entry.get("_preceding_user_agent_links") or []
    agent_links: list[tuple[str, str]] = []
    if isinstance(raw_links, list):
        for pair in raw_links:
            if (isinstance(pair, (list, tuple)) and len(pair) == 2
                    and isinstance(pair[0], str) and isinstance(pair[1], str)):
                agent_links.append((pair[0], pair[1]))
    if u.get("speed") == "fast":
        _sm()._FAST_MODE_TURNS[0] += 1
    # Per-turn latency: wall-clock seconds from the immediately preceding
    # user / tool_result entry to this assistant turn's settled timestamp.
    # ``_preceding_user_timestamp`` is set in ``_extract_turns`` (first
    # streaming chunk wins). For headless ``claude -p`` benchmark runs this
    # is the model's response time for the single turn; for tool-using
    # turns it represents the model's time after the tool result landed.
    # ``None`` when either timestamp is missing or unparseable, or when the
    # gap is non-positive (clock skew on truncated files, synthetic resume
    # markers — the JSONL writer guarantees monotone timestamps within one
    # session in practice).
    _prev_iso = entry.get("_preceding_user_timestamp", "") or ""
    _this_iso = entry.get("timestamp", "") or ""
    latency_seconds: float | None = None
    if _prev_iso and _this_iso:
        _prev_dt = _parse_iso_dt(_prev_iso)
        _this_dt = _parse_iso_dt(_this_iso)
        if _prev_dt and _this_dt:
            try:
                _gap = (_this_dt - _prev_dt).total_seconds()
                if _gap >= 0:
                    latency_seconds = round(_gap, 3)
            except (ValueError, AttributeError, TypeError, OSError):
                latency_seconds = None
    stop_reason: str = msg.get("stop_reason") or ""
    return {
        "index":                  global_index,
        "timestamp":              entry.get("timestamp", ""),
        "timestamp_fmt":          _fmt_ts(entry.get("timestamp", ""), tz_offset_hours),
        "latency_seconds":        latency_seconds,
        "model":                  model,
        "input_tokens":           inp,
        "output_tokens":          out,
        "cache_read_tokens":      crd,
        "cache_write_tokens":     cwr,
        "cache_write_5m_tokens":  cwr_5m,
        "cache_write_1h_tokens":  cwr_1h,
        "cache_write_ttl":        ttl,
        "total_tokens":           inp + out + crd + cwr,
        "cost_usd":               c,
        "no_cache_cost_usd":      nc,
        "speed":                  u.get("speed", ""),
        "stop_reason":            stop_reason,
        "is_cache_break":         False,
        "content_blocks":         content_blocks,
        "tool_use_names":         tool_names,
        "is_resume_marker":       bool(entry.get("_is_resume_marker", False)),
        "is_clear_event":         bool(entry.get("_is_clear_event", False)),
        # Q1c: stamped later by ``_build_report`` from the canonical, deduped
        # compaction-boundary set (NOT a per-file flag here — boundaries replay
        # across sibling JSONLs). ``is_post_compaction`` marks the first turn
        # after a mid-session ``compact_boundary``; ``is_continued_from_prior``
        # marks a session's first turn when it opens on a compaction summary.
        "is_post_compaction":     False,
        "is_continued_from_prior": False,
        "prompt_text":            prompt_text,
        "prompt_snippet":         _truncate(prompt_text, 240),
        "slash_command":          slash_cmd,
        "assistant_text":         asst_text,
        "assistant_snippet":      _truncate(asst_text, 240),
        "tool_use_detail":        tool_detail,
        "skill_invocations":      skill_invocations,
        "spawned_subagents":      spawned_subagents,
        "subagent_type":          subagent_type,
        # Phase-B (v1.7.0): subagent → parent-prompt attribution fields.
        # ``tool_use_ids`` / ``agent_links`` / ``subagent_agent_id`` are
        # the linkage primitives. ``prompt_anchor_index`` is filled in
        # by a one-shot pass over ``turn_records`` in ``_build_report``.
        # ``attributed_subagent_*`` start at zero and are accumulated by
        # ``_attribute_subagent_tokens`` on the spawning prompt's row.
        "tool_use_ids":              tool_use_ids,
        "agent_links":               agent_links,
        "subagent_agent_id":         subagent_agent_id,
        "prompt_anchor_index":       0,
        "attributed_subagent_tokens": 0,
        "attributed_subagent_cost":   0.0,
        "attributed_subagent_count":  0,
        # Advisor fields (v1.25.0): populated from usage.iterations when advisor
        # was called; all zero/None when advisor was disabled or not invoked.
        "advisor_calls":         adv_calls,
        "advisor_cost_usd":      adv_cost,
        "advisor_model":         adv_model,
        "advisor_input_tokens":  adv_inp,
        "advisor_output_tokens": adv_out,
    }


def _fmt_ts(ts: str, offset_hours: float = 0.0) -> str:
    dt = _parse_iso_dt(ts)
    if dt is None:
        return ts[:19] if len(ts) >= 19 else ts
    try:
        if offset_hours:
            dt = dt.astimezone(timezone(timedelta(hours=offset_hours)))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError, OSError):
        return ts[:19] if len(ts) >= 19 else ts
