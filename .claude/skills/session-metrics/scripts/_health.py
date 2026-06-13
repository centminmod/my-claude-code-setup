"""Session-health layer for session-metrics.

A thin session-quality layer computed over data the JSONL already carries.
It answers "how did this session go?" (not just "what did it cost?") via:

- a **tool-health pass** over per-turn ``tool_results`` / ``tool_use_detail``
  (failure detection, consecutive-failure streak, byte-identical retries,
  edit churn) — see ``compute_tool_health``;
- an **outcome classifier** (completed / abandoned / errored / unknown /
  in_progress) with a confidence and a recency gate — ``classify_outcome``;
- a **context-pressure** ratio (peak per-turn context ÷ model window) plus a
  mid-task-compaction flag — ``compute_context_pressure`` / the boundary scan;
- a **penalty-based 0–100 health score** with an A–F grade and an auditable
  per-signal breakdown — ``compute_health_score``.

All functions are pure (no I/O, no globals beyond ``_sm()`` back-refs for the
synthetic-model sentinel and the context-window table). ``build_session_health``
is the single entry point the report builder calls per session.
"""
import re
import sys


def _sm():
    """Return the session_metrics module (fully loaded by call time)."""
    return sys.modules["session_metrics"]


# ---------------------------------------------------------------------------
# Tool-failure detection
# ---------------------------------------------------------------------------
# `is_error` (read off each tool_result in the parser) is the primary, reliable
# signal. The content heuristics below only ENRICH the rare case where is_error
# is absent (older transcripts) — they never override an explicit is_error.

_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)")
_JS_STACK_RE = re.compile(r"^\s+at\s", re.MULTILINE)
_CONTENT_FAILURE_NEEDLES = (
    "command not found",
    "permission denied",
    "no such file or directory",
    "fatal error",
)


def _is_content_failure(text: str) -> bool:
    """Heuristic failure detection on a tool_result's text.

    Used only when ``is_error`` is absent. Conservative: matches well-known
    error signatures (tracebacks, missing-command / permission errors, and
    JS-style stack traces with ≥3 ``at`` frames).
    """
    if not text:
        return False
    low = text.lower()
    if any(n in low for n in _CONTENT_FAILURE_NEEDLES):
        return True
    if _TRACEBACK_RE.search(text):
        return True
    return len(_JS_STACK_RE.findall(text)) >= 3


def _tool_result_is_failure(tr: dict) -> bool:
    """True when a ``tool_results`` entry represents a failed tool call.

    Leads with the explicit ``is_error`` flag; falls back to content
    heuristics only when ``is_error`` is ``None`` (field absent).
    """
    ie = tr.get("is_error")
    if ie is True:
        return True
    if ie is False:
        return False
    return _is_content_failure(tr.get("text") or "")


def _real_turns(turn_records: list[dict]) -> list[dict]:
    """Assistant turns excluding synthetic placeholders + resume markers."""
    syn = _sm()._SYNTHETIC_MODEL
    return [t for t in turn_records
            if t.get("model") != syn and not t.get("is_resume_marker")]


def compute_tool_health(turn_records: list[dict]) -> dict:
    """Derive tool-health signals from per-turn tool data.

    Returns a dict with::

        failure_signal_count, consecutive_failure_max, trailing_failure_streak,
        retry_count, repeated_calls, edit_churn_count, churned_files,
        per_tool (name -> {calls, failures, rate}), total_tool_calls

    The passes are independent and each linear in the turn count.
    """
    # Map tool_use_id -> tool name across the whole session (results carry the
    # id, not the name).
    id_to_name: dict[str, str] = {}
    for t in turn_records:
        for d in t.get("tool_use_detail") or []:
            tid = d.get("id")
            if tid:
                id_to_name[tid] = d.get("name") or ""

    # --- failure pass (ordered over every tool_result in turn/block order) ---
    failure_count = 0
    cur_streak = 0
    max_streak = 0
    trailing_streak = 0
    per_tool: dict[str, dict] = {}
    for t in turn_records:
        for tr in t.get("tool_results") or []:
            name = id_to_name.get(tr.get("tool_use_id", ""), "") or "(unknown)"
            row = per_tool.setdefault(name, {"calls": 0, "failures": 0})
            row["calls"] += 1
            failed = _tool_result_is_failure(tr)
            if failed:
                failure_count += 1
                row["failures"] += 1
                cur_streak += 1
                max_streak = max(max_streak, cur_streak)
                trailing_streak += 1
            else:
                cur_streak = 0
                trailing_streak = 0
    for row in per_tool.values():
        row["rate"] = round(row["failures"] / row["calls"], 4) if row["calls"] else 0.0

    # --- retry pass: runs of byte-identical consecutive (name, input_hash) ---
    seq: list[tuple[str, str]] = []
    for t in turn_records:
        for d in t.get("tool_use_detail") or []:
            h = d.get("input_hash") or ""
            if h:
                seq.append((d.get("name") or "", h))
    retry_count = 0
    repeated_calls: list[dict] = []
    i = 0
    while i < len(seq):
        j = i + 1
        while j < len(seq) and seq[j] == seq[i]:
            j += 1
        run = j - i
        if run >= 3:
            retry_count += run - 1
            repeated_calls.append({"name": seq[i][0], "count": run})
        i = j

    # --- edit-churn pass: a file edited 3+ times within a <10 ordinal span ---
    # Ordinal = global index of each Edit/Write call across the session.
    file_ordinals: dict[str, list[int]] = {}
    ordinal = 0
    for t in turn_records:
        for d in t.get("tool_use_detail") or []:
            name = d.get("name") or ""
            ordinal += 1
            if name in ("Edit", "Write", "MultiEdit"):
                fp = d.get("file_path") or ""
                if fp:
                    file_ordinals.setdefault(fp, []).append(ordinal)
    churned_files: list[dict] = []
    for fp, ords in file_ordinals.items():
        ords.sort()  # parallel subagent results can interleave — sort first
        churned = any(
            ords[k + 2] - ords[k] < 10 for k in range(len(ords) - 2)
        )
        if churned:
            churned_files.append({"path": fp, "edits": len(ords)})
    churned_files.sort(key=lambda r: (-r["edits"], r["path"]))

    total_calls = sum(r["calls"] for r in per_tool.values())
    return {
        "failure_signal_count":   failure_count,
        "consecutive_failure_max": max_streak,
        "trailing_failure_streak": trailing_streak,
        "retry_count":            retry_count,
        "repeated_calls":         repeated_calls,
        "edit_churn_count":       len(churned_files),
        "churned_files":          churned_files,
        "per_tool":               per_tool,
        "total_tool_results":     total_calls,
    }


# ---------------------------------------------------------------------------
# Outcome classification
# ---------------------------------------------------------------------------

_GIVE_UP_PHRASES = (
    "i'm unable to", "i am unable to",
    "i can't proceed", "i cannot proceed",
    "i don't have access", "i do not have access",
    "i'm not able to", "i am not able to",
    "unable to complete", "i was unable to",
    "i give up",
)

RECENCY_WINDOW_SECONDS = 600  # 10 min — a session touched this recently is "in progress"
_MIN_TURNS_FOR_OUTCOME = 2


def _has_give_up(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in _GIVE_UP_PHRASES)


def classify_outcome(
    *,
    turn_count: int,
    last_role: str,
    trailing_failure_streak: int,
    last_assistant_text: str,
    last_stop_reason: str,
    seconds_since_last: float | None,
) -> dict:
    """Classify how a session ended.

    Returns ``{"outcome": str, "confidence": str, "give_up": bool}``.

    Guards first (can't-classify cases), then the substantive cascade:
    refusal / trailing failure streak → ``errored``; ended-on-user →
    ``abandoned``; ended-on-assistant → ``completed`` (downgraded to low
    confidence when the final reply reads like a capitulation).
    """
    give_up = _has_give_up(last_assistant_text)
    # Recency gate — a mid-session report run must not call a live session
    # "abandoned". Uses report-generation time vs the last record's time.
    if seconds_since_last is not None and seconds_since_last < RECENCY_WINDOW_SECONDS:
        return {"outcome": "in_progress", "confidence": "low", "give_up": give_up}
    if turn_count < _MIN_TURNS_FOR_OUTCOME:
        return {"outcome": "unknown", "confidence": "low", "give_up": give_up}
    if last_stop_reason == "refusal":
        return {"outcome": "errored", "confidence": "high", "give_up": give_up}
    if trailing_failure_streak >= 3:
        return {"outcome": "errored", "confidence": "high", "give_up": give_up}
    if last_role == "user":
        return {"outcome": "abandoned", "confidence": "medium", "give_up": give_up}
    if give_up:
        return {"outcome": "completed", "confidence": "low", "give_up": give_up}
    return {"outcome": "completed", "confidence": "high", "give_up": give_up}


# ---------------------------------------------------------------------------
# Context pressure
# ---------------------------------------------------------------------------

def _context_window_for(model: str) -> int:
    """Context window (tokens) for a model id.

    The 1M long-context beta is flagged by a ``[1m]`` suffix and overrides the
    family default. Otherwise longest-prefix match against the family table.
    """
    if "[1m]" in model:
        return _sm()._LONG_CONTEXT_WINDOW
    best_len = -1
    best = _sm()._DEFAULT_CONTEXT_WINDOW
    for prefix, window in _sm()._MODEL_CONTEXT_WINDOWS.items():
        if model.startswith(prefix) and len(prefix) > best_len:
            best_len = len(prefix)
            best = window
    return best


def compute_context_pressure(turn_records: list[dict]) -> dict:
    """Peak per-turn context size ÷ the model's window.

    Returns ``{"context_pressure": float|None, "peak_context_tokens": int,
    "context_window": int}``. ``context_pressure`` is ``None`` when there are
    no real turns to measure.
    """
    real = _real_turns(turn_records)
    if not real:
        return {"context_pressure": None, "peak_context_tokens": 0, "context_window": 0}
    peak = 0
    peak_model = real[-1].get("model", "")
    for t in real:
        ctx = (t.get("input_tokens", 0) + t.get("cache_read_tokens", 0)
               + t.get("cache_write_tokens", 0))
        if ctx > peak:
            peak = ctx
            peak_model = t.get("model", peak_model)
    window = _context_window_for(peak_model)
    # Physical invariant: a turn's context can't exceed the real window. The
    # per-turn ``message.model`` in the JSONL drops the ``[1m]`` long-context
    # suffix, so a session actually running on the 1M tier looks like the base
    # model here. If the observed peak exceeds our base-tier estimate, the
    # session must be on the extended tier — upgrade the window so pressure
    # can't read >100% (which also avoids a spurious context-pressure penalty).
    if peak > window:
        window = _sm()._LONG_CONTEXT_WINDOW
    pressure = round(peak / window, 4) if window else None
    return {"context_pressure": pressure, "peak_context_tokens": peak,
            "context_window": window}


def count_mid_task_compactions(turn_records: list[dict]) -> int:
    """Count compaction boundaries that interrupted active work.

    For each turn flagged ``is_post_compaction``, compare the distinct tool
    names in the ~10 turns before the boundary with the ~5 turns at/after it;
    ≥2 distinct names in common is strong evidence the compaction landed
    mid-task and the agent resumed the same work.
    """
    n = len(turn_records)
    count = 0
    for i, t in enumerate(turn_records):
        if not t.get("is_post_compaction"):
            continue
        before: set[str] = set()
        for b in turn_records[max(0, i - 10):i]:
            before.update(b.get("tool_use_names") or [])
        after: set[str] = set()
        for a in turn_records[i:min(n, i + 5)]:
            after.update(a.get("tool_use_names") or [])
        if len(before & after) >= 2:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Automated-session gate
# ---------------------------------------------------------------------------
# A benchmark / warm-up / harness session shouldn't be graded "abandoned" —
# it was never an interactive user session. Detection is deliberately
# conservative (the costly error is hiding a real session's grade), so it only
# fires on a tiny set of exact launcher prompts with a single user turn.

_AUTOMATED_FIRST_PROMPT_NEEDLES = (
    "reply with the single word ok",   # benchmark cache warm-up ping
)


def detect_automated_session(turn_records: list[dict]) -> bool:
    """Best-effort: is this a non-interactive (benchmark/harness) session?"""
    real = _real_turns(turn_records)
    prompts = [t.get("prompt_text", "") for t in real if t.get("prompt_text")]
    if not prompts:
        return False
    first = prompts[0].lower()
    return len(prompts) <= 1 and any(n in first for n in _AUTOMATED_FIRST_PROMPT_NEEDLES)


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------

def _grade_from_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def compute_health_score(*, tool_health: dict, outcome: str,
                         compaction_count: int, mid_task_compactions: int,
                         context_pressure: float | None) -> dict:
    """Capped-weighted-penalty 0–100 score with an auditable breakdown.

    Each signal is ``raw × weight`` clamped to a per-signal cap so no single
    noisy signal dominates. Returns ``{"score": int, "grade": str,
    "penalties": {...}}`` — the caller decides whether scoring is warranted
    (see ``_can_score``).
    """
    penalties = {
        "failures":             min(tool_health["failure_signal_count"] * 3, 30),
        "retries":              min(tool_health["retry_count"] * 5, 25),
        "churn":                min(tool_health["edit_churn_count"] * 4, 20),
        "streak":               10 if tool_health["consecutive_failure_max"] >= 3 else 0,
        "compactions":          min((compaction_count - 1) * 5, 15) if compaction_count >= 2 else 0,
        "mid_task_compactions": min(mid_task_compactions * 8, 18),
        "context_pressure":     10 if (context_pressure is not None and context_pressure > 0.9) else 0,
        "outcome":              30 if outcome == "errored" else (15 if outcome == "abandoned" else 0),
    }
    score = max(0, 100 - sum(penalties.values()))
    return {"score": score, "grade": _grade_from_score(score), "penalties": penalties}


def _build_basis(tool_health: dict, context: dict, compaction_count: int) -> list[str]:
    """Which signal categories actually had data to contribute."""
    basis = ["outcome"]
    if tool_health["total_tool_results"] > 0 or tool_health["retry_count"] > 0 \
            or tool_health["edit_churn_count"] > 0:
        basis.append("tool_health")
    if (context.get("peak_context_tokens") or 0) > 0 or compaction_count > 0:
        basis.append("context")
    return basis


def _can_score(outcome: str, confidence: str, basis: list[str]) -> bool:
    """Refuse to emit a misleading score on outcome-only, low-confidence data.

    Suppress (score = null) ONLY when the outcome is an unknown low-confidence
    guess AND no tool/context signal was available. A session with any tool or
    context data always scores.
    """
    if outcome in ("in_progress", "automated"):
        return False
    return not (outcome == "unknown" and confidence == "low" and basis == ["outcome"])


# ---------------------------------------------------------------------------
# Behavioral & adoption signals (Phase B / v1.73.0)
# ---------------------------------------------------------------------------

_PLAN_MODE_TOOLS = ("ExitPlanMode", "EnterPlanMode")


def _tool_category(name: str) -> str:
    """Normalise a raw tool name into one of ~8 canonical categories."""
    if name in ("Read", "NotebookRead"):
        return "read"
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return "edit"
    if name == "Bash":
        return "shell"
    if name in ("Grep", "Glob"):
        return "search"
    if name in ("Task", "Agent", "Workflow") or "subagent" in name.lower():
        return "delegate"
    if name in ("Skill", "skill"):
        return "skill"
    if name in ("WebFetch", "WebSearch"):
        return "web"
    if name in ("TodoWrite", "ExitPlanMode", "EnterPlanMode"):
        return "plan"
    return "other"


def _archetype_label(user_prompt_count: int) -> str:
    """Bucket a session by user-message count (verbatim thresholds)."""
    if user_prompt_count <= 5:
        return "quick"
    if user_prompt_count <= 15:
        return "standard"
    if user_prompt_count <= 50:
        return "deep"
    return "marathon"


def _classify_termination(real: list[dict]) -> str:
    """How the session ended, mechanically (distinct from outcome).

    ``tool_call_pending`` — the last turn issued tool calls with no follow-up
    turn (hung / awaiting a tool result or permission). ``awaiting_user`` — the
    last turn stopped cleanly on ``end_turn``/``stop_sequence`` (ball in the
    user's court). ``clean`` — anything else.
    """
    if not real:
        return "clean"
    last = real[-1]
    if (last.get("tool_use_detail") or []):
        return "tool_call_pending"
    if last.get("stop_reason") in ("end_turn", "stop_sequence"):
        return "awaiting_user"
    return "clean"


def build_session_behavior(turn_records: list[dict], *,
                           relationship: str = "primary") -> dict:
    """Behavioral & adoption signals over already-parsed turn data.

    Cheap derivations: session archetype, autonomy ratio, plan-mode / subagent /
    distinct-skill adoption, tool-category taxonomy, behavioral turn typing, and
    a mechanical termination class.
    """
    real = _real_turns(turn_records)
    user_prompts = [t for t in real if (t.get("prompt_text") or "").strip()
                    and not t.get("is_continued_from_prior")]
    n_prompts = len(user_prompts)

    plan_mode = False
    spawn_count = 0
    skills: set[str] = set()
    tool_cat_counts: dict[str, int] = {}
    tool_carrying_turns = 0
    turn_types = {"agentic": 0, "thinking": 0, "text": 0, "other": 0}
    for t in real:
        names = t.get("tool_use_names") or []
        if any(n in _PLAN_MODE_TOOLS for n in names):
            plan_mode = True
        spawn_count += len(t.get("spawned_subagents") or [])
        for s in t.get("skill_invocations") or []:
            skills.add(s)
        if names:
            tool_carrying_turns += 1
        for n in names:
            cat = _tool_category(n)
            tool_cat_counts[cat] = tool_cat_counts.get(cat, 0) + 1
        cb = t.get("content_blocks") or {}
        if cb.get("tool_use", 0) > 0:
            turn_types["agentic"] += 1
        elif cb.get("thinking", 0) > 0:
            turn_types["thinking"] += 1
        elif cb.get("text", 0) > 0:
            turn_types["text"] += 1
        else:
            turn_types["other"] += 1

    autonomy_ratio = round(tool_carrying_turns / n_prompts, 2) if n_prompts else None
    return {
        "archetype":          _archetype_label(n_prompts),
        "user_prompt_count":  n_prompts,
        "autonomy_ratio":     autonomy_ratio,
        "tool_carrying_turns": tool_carrying_turns,
        "termination":        _classify_termination(real),
        "relationship":       relationship,
        "adoption": {
            "plan_mode_used":      plan_mode,
            "subagent_spawn_count": spawn_count,
            "distinct_skill_count": len(skills),
            "distinct_skills":     sorted(skills),
        },
        "tool_taxonomy": dict(sorted(tool_cat_counts.items())),
        "turn_types":    turn_types,
    }


def build_session_health(
    *,
    turn_records: list[dict],
    compaction_boundaries: list[dict] | None,
    last_user_epoch: int,
    last_assistant_epoch: int,
    now_epoch: int,
    is_automated: bool,
) -> dict:
    """Assemble the per-session ``session_health`` object.

    Single entry point called once per session by the report builder. Always
    returns a populated dict; ``score`` / ``grade`` are ``None`` when scoring
    is suppressed (automated, in-progress, or insufficient data).
    """
    real = _real_turns(turn_records)
    tool_health = compute_tool_health(turn_records)
    context = compute_context_pressure(turn_records)
    compaction_count = len(compaction_boundaries or [])
    mid_task = count_mid_task_compactions(turn_records)

    # last_role: did the user speak after the final assistant turn?
    last_role = "user" if (last_user_epoch and last_assistant_epoch
                           and last_user_epoch > last_assistant_epoch) else "assistant"
    last_assistant_text = real[-1].get("assistant_text", "") if real else ""
    last_stop_reason = real[-1].get("stop_reason", "") if real else ""
    last_epoch = max(last_user_epoch or 0, last_assistant_epoch or 0)
    seconds_since_last = (now_epoch - last_epoch) if (now_epoch and last_epoch) else None

    # A trailing tool-failure streak only means "ended in a failure spiral" if
    # the session actually ended on tool activity. When the final real turn is a
    # clean text-only completion (no tool calls, stopped on end_turn/stop_sequence),
    # the agent recovered and answered — so the earlier failures are not a trailing
    # streak. Zero it in that case to avoid misclassifying a recovered session as
    # "errored". (The streak itself is still reported verbatim in signals.)
    trailing_streak = tool_health["trailing_failure_streak"]
    if (real and not (real[-1].get("tool_use_detail") or [])
            and last_stop_reason in ("end_turn", "stop_sequence")):
        trailing_streak = 0

    outcome_res = classify_outcome(
        turn_count=len(real),
        last_role=last_role,
        trailing_failure_streak=trailing_streak,
        last_assistant_text=last_assistant_text,
        last_stop_reason=last_stop_reason,
        seconds_since_last=seconds_since_last,
    )
    outcome = "automated" if is_automated else outcome_res["outcome"]
    confidence = outcome_res["confidence"]
    basis = _build_basis(tool_health, context, compaction_count)

    health = {
        "outcome":            outcome,
        "outcome_confidence": confidence,
        "give_up":            outcome_res["give_up"],
        "is_automated":       is_automated,
        "basis":              basis,
        "signals": {
            **tool_health,
            "compaction_count":          compaction_count,
            "mid_task_compaction_count": mid_task,
            "context_pressure":          context["context_pressure"],
            "peak_context_tokens":       context["peak_context_tokens"],
            "context_window":            context["context_window"],
        },
    }
    if _can_score(outcome, confidence, basis):
        scored = compute_health_score(
            tool_health=tool_health,
            outcome=outcome,
            compaction_count=compaction_count,
            mid_task_compactions=mid_task,
            context_pressure=context["context_pressure"],
        )
        health["score"] = scored["score"]
        health["grade"] = scored["grade"]
        health["penalties"] = scored["penalties"]
    else:
        health["score"] = None
        health["grade"] = None
        health["penalties"] = {}
    return health
