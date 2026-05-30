---
name: task-breakdown
model: sonnet
description: >
  Group a session-metrics session's turns into higher-level SEMANTIC TASKS
  ("what was I actually trying to do") and render a Tasks companion page
  (*_tasks.html + *_tasks.md) with a worth-it / mixed / likely-waste verdict
  per task. Trigger when the user runs /task-breakdown, when session-metrics
  suggests a task breakdown after a JSON export, or when the user asks to
  "group my turns into tasks", "what tasks did this session cover", "which
  work was worth it vs wasted", or "break this session into tasks". Consumes
  the deterministic per-request breakdown (request_units) from a
  session-metrics JSON export — it never re-derives cost or token numbers.
  Args: $ARGUMENTS[0] = path to a session-metrics JSON export (optional;
  if omitted, generate one first).
---

# Task Breakdown

Turns a session's **per-request breakdown** (the deterministic `request_units`
emitted by session-metrics) into **semantic tasks** the user actually thinks
in — "added auth", "debugged the cache miss" — and labels each with a verdict.
You do the one thing deterministic code can't: decide which requests belong to
the same task. The script does everything else (cost, turns, tokens, waste
signals, the themed page).

**Division of labour — do not blur it:**
- **The export owns the numbers.** Every cost / turn / token / waste figure
  comes from `request_units` in the JSON export. You MUST NOT sum money or
  invent figures — `--render-tasks` recomputes all totals from the export.
- **You own the grouping + labels only.** You assign each `request_unit_id` to
  a task, write a short title, a verdict, and a one-line rationale.

## Inputs

`$ARGUMENTS[0]` (optional) = path to a session-metrics JSON export, e.g.
`exports/session-metrics/session_<id8>_<ts>.json` (session scope is the primary
target; `project_*.json` also works — units carry a `session_id`). The export
must contain a `request_units` array.

If `$ARGUMENTS[0]` is missing, first generate a session export by invoking the
**session-metrics** skill (or run its script) for the session of interest with
`--output json html`, then use the written `session_*.json` path.

## Steps

1. **Locate the export and the renderer.**
   - Export: `$ARGUMENTS[0]`, or the JSON you just generated.
   - Renderer: the sibling **session-metrics** skill's script. Resolve its
     path (it ships in the same plugin):
     - plugin install: `../session-metrics/scripts/session-metrics.py`
     - dev repo: `.claude/skills/session-metrics/scripts/session-metrics.py`
     Use whichever exists (glob if unsure).

2. **Read the request units.** Load the export JSON and read `request_units`.
   Each unit has: `unit_id` (`"<session_id>:<anchor_index>"`), `prompt_snippet`,
   `prompt_text`, `turn_count`, `combined_cost_usd`, `total_tokens`,
   `tool_histogram`, `risk_turn_count`, `reread_path_count`, `cache_break_count`,
   `wall_clock_seconds`, `idle_gap_before_seconds`, `slash_command`,
   `spawned_subagents`, `workflow_run_ids`, `multi_intent_possible`.
   **If `request_units` is absent**, tell the user to re-run session-metrics to
   regenerate the export (the per-request breakdown is a newer feature) and stop.

3. **Group into semantic tasks.** Read the units in order and cluster
   consecutive requests that pursue the same goal into one task. Signals, in
   priority order:
   - **Topical/lexical continuity** of `prompt_snippet`/`prompt_text` (same
     feature, file, bug, or subject) — the PRIMARY signal.
   - **Shared `tool_histogram` / file targets** across adjacent requests.
   - **Slash command / skill** starts (`slash_command`, a `/debug`,
     `/feature-dev`, etc.) often begin a task.
   - **Idle gaps** (`idle_gap_before_seconds`) — a WEAK, confirming-only hint.
     A long gap supports a split you already suspect topically; never split on
     a gap alone (lunch breaks, overnight continuations).
   - A unit flagged `multi_intent_possible` may belong to two tasks — note it,
     but keep the unit whole (it cannot be divided).
   Most sessions yield a handful of tasks. Don't over-segment ("now fix the
   test" is usually the SAME task as the feature it follows), and don't
   under-segment (one giant "misc" task is useless).
   **At large scale** (many dozens of units, e.g. a project-scope export):
   group at **session granularity** — one titled task per coherent
   session-goal — rather than attempting per-unit segmentation. **Never emit a
   single untitled catch-all task that swallows everything**: the renderer's
   collapse guard flags a blank-titled task covering the bulk of requests, and
   it is a useless grouping anyway. If you cannot segment meaningfully, that is
   a signal the input is too coarse for this skill (prefer a single-session
   export).

4. **Label each task with a verdict**, using the deterministic waste signals as
   evidence, NOT a guess:
   - `worth_it` — the task reached its goal at reasonable cost; low
     `risk_turn_count` / re-read churn relative to its size.
   - `likely_waste` — high `risk_turn_count`, repeated `reread_path_count`,
     many `cache_break_count`, or a long turn/cost run with little to show
     (e.g. a debug loop that churned).
   - `mixed` — partly productive, partly churn, or you're unsure.
   **Bias toward `mixed`/`worth_it` when uncertain** — a wrong `likely_waste`
   damages trust more than a missed one. Keep the `rationale` to one honest
   sentence tied to the signals ("12 turns, 4 risky re-reads of the same file
   before the fix landed").

5. **Write `grouping.json`** next to the export (same directory), shape:
   ```json
   {
     "schema_version": "1",
     "scope_label": "session <id8> · <first_ts>",
     "tasks": [
       {
         "title": "Add token-refresh to auth",
         "verdict": "worth_it",
         "rationale": "8 requests, one short debug detour, shipped.",
         "request_unit_ids": ["<sid>:2", "<sid>:3", "<sid>:5"]
       }
     ]
   }
   ```
   Cover **every** `unit_id` exactly once across all tasks. (Any you leave out
   are swept into a synthetic "Ungrouped requests" task automatically, and the
   renderer warns — aim for full coverage.)

6. **Render the companion:**
   ```
   python3 <renderer> --render-tasks <export.json> <grouping.json>
   ```
   The script validates the grouping (flags duplicate / unknown unit ids,
   schema drift), recomputes every total from the export, and writes
   `<stem>_tasks.html` + `<stem>_tasks.md` next to the export. It prints the
   output paths and any validation warnings.

7. **Report back** to the user: the task list with each verdict, turn count and
   cost (read these back from the script's stdout / the rendered `*_tasks.md` —
   do not recompute), the paths to the two companion files, and any grouping
   warnings the script surfaced. Offer to open the HTML page.

## Guardrails

- **Never invent or sum numbers.** If you need a total, read it from the export
  or from the rendered `*_tasks.md` after `--render-tasks` runs.
- **Don't touch the workflow companion** (`*_workflows.*`) — the Tasks page is
  a separate, additional artifact.
- **Honest framing:** the deterministic dashboard section is "per-request
  breakdown"; only this skill's output is allowed to call groups "tasks",
  because only here did a human-level judgement decide the boundaries.
