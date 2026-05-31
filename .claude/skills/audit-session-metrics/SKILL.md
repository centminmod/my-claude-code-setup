---
name: audit-session-metrics
effort: low
description: >
  Audit a session-metrics JSON export for token-usage waste and produce a
  plain-English findings report. Trigger when the user runs
  /audit-session-metrics, when session-metrics suggests an audit after an
  HTML export, or when the user asks to audit / review / find waste in a
  saved session-metrics JSON. Two modes: "quick" (ratios + cache health +
  top expensive turns/sessions) and "detailed" (adds CLAUDE.md / settings /
  re-read scan). Supports session, project, and instance JSON scopes.
  Args: $ARGUMENTS[0] = quick|detailed,
  $ARGUMENTS[1] = path to a session-metrics JSON export.
---

# Audit Session-Metrics

Reads a session-metrics JSON export and produces a prioritised, plain-English
audit of token-usage waste. It runs on the session's current model (it no
longer pins one — a hard model pin capped the usable context at that model's
window and broke invocation on long sessions). The work is mostly
summarisation over a small disk-read export, so for a ~10× cheaper run
`/model haiku` before invoking (short/early sessions only — Haiku's 200k
window can't hold a long conversation).

Supports three JSON scopes auto-detected from `digest.scope`:
- **session** — single session (`session_*.json`) — per-turn analysis
- **project** — all sessions for one project (`project_*.json`) — per-session analysis
- **instance** — all projects (`instance/*/index.json`) — per-project analysis

## Dispatch — how to route this invocation

**First positional argument received:** `$ARGUMENTS[0]`
**Second positional argument received:** `$ARGUMENTS[1]`

Read `$ARGUMENTS[0]` and match by **literal equality**:

| `$ARGUMENTS[0]` | Route                    | Then read (session scope) | Then read (project/instance scope) |
|-----------------|--------------------------|---------------------------|------------------------------------|
| `quick`         | Quick audit              | [`references/quick-audit.md`](references/quick-audit.md) | see Scope routing below |
| `detailed`      | Detailed audit           | [`references/detailed-audit.md`](references/detailed-audit.md) | see Scope routing below |
| *(empty / other)* | Print usage and stop   | this file's "Usage" block below | — |

`$ARGUMENTS[1]` must be the path to a JSON export written by session-metrics.
Accepted patterns:
- `exports/session-metrics/session_<id8>_<ts>.json` — session scope
- `exports/session-metrics/project_<ts>.json` — project scope
- `exports/session-metrics/instance/<datedir>/index.json` — instance scope

If `$ARGUMENTS[1]` is missing, empty, or the file does not exist, print:

> Usage: /audit-session-metrics {quick|detailed} <path-to-session-metrics.json>
>
> Accepted JSON types:
>   session:  exports/session-metrics/session_*.json
>   project:  exports/session-metrics/project_*.json
>   instance: exports/session-metrics/instance/*/index.json

…and stop without further work.

## Steps

1. Run the extract helper once with the input path:

   ```
   python3 scripts/audit-extract.py $ARGUMENTS[1] --mode $ARGUMENTS[0]
   ```

   The helper emits a single JSON digest to stdout. Read `digest.scope`
   from the output — it will be `"session"`, `"project"`, or `"instance"`.
   **Do not** read the raw `.jsonl`, and **do not** re-derive numbers the
   digest already carries.

2. **Scope routing — read the matching reference file:**

   | `digest.scope` | `$ARGUMENTS[0]` | Reference file |
   |----------------|-----------------|----------------|
   | `session`      | `quick`         | [`references/quick-audit.md`](references/quick-audit.md) |
   | `session`      | `detailed`      | [`references/detailed-audit.md`](references/detailed-audit.md) |
   | `project`      | `quick`         | [`references/project-quick-audit.md`](references/project-quick-audit.md) |
   | `project`      | `detailed`      | [`references/project-detailed-audit.md`](references/project-detailed-audit.md) |
   | `instance`     | `quick` or `detailed` | [`references/instance-quick-audit.md`](references/instance-quick-audit.md) |

   Follow the playbook step-by-step. Do not improvise additional phases.

3. For `detailed` mode **on session scope only**, the playbook also asks
   you to read the user's config files (`~/.claude/CLAUDE.md`,
   `./CLAUDE.md`, `~/.claude/settings.json`, `./.claude/settings.json`,
   `./.claudeignore`). Each is capped at ≤500 lines — if a file is
   bigger, that itself is a finding.

4. **Output contract — three artefacts.** All playbooks specify the
   same three-artefact contract:
   - **JSON sidecar** at `<project>/exports/session-metrics/audit_<id8>_<ts>_<mode>.json` — structured findings (versioned schema, enum'd metrics).
   - **Markdown copy** at `<project>/exports/session-metrics/audit_<id8>_<ts>_<mode>.md` — same content rendered for humans.
   - **Inline chat output** — the markdown content printed in your reply.

   `<id8>` and `<ts>` come from `digest.session_id_short` and
   `digest.ts_str` (the helper parses the input filename and
   normalises all three filename patterns).

5. **Write order.** Populate the JSON object first using the digest
   values, write the JSON sidecar, render the markdown using the
   template in the playbook, write the markdown copy, then print the
   markdown inline (without the H1 heading — the chat client already
   shows context above the audit). Finish with two stderr-style lines
   on their own:
   `[audit] saved → <json-path>`
   `[audit] saved → <md-path>`

   **IMPORTANT:** Use the **Write tool** directly for steps 3 and 5.
   Do NOT generate a Python script (e.g. writing to `/tmp/audit_synthesis.py`
   and executing it) — this adds unnecessary failure modes (syntax errors,
   f-string escaping) and is never required. Build the JSON in the AI's own
   context; call Write. Render the markdown in context; call Write again.

## Tone

- **Direct and specific.** Cite the exact ratio, dollar figure, or turn
  index. No motivational language, no LLM-theory padding.
- **Prioritise by impact.** Sort findings so the costliest fix is first.
- **Quote sparingly.** Snippets capped at 5 lines each.
- **Honour the playbook.** If quick-audit.md asks for 5 rows, produce 5
  rows — don't invent a 6th to look thorough.

## Why this is a separate skill

The audit is a distinct, user-initiated analysis step over a finished
export, not part of generating one. It reads only the on-disk JSON — never
the conversation — so it stands alone as its own turn, which is why
session-metrics *suggests* `/audit-session-metrics` rather than invoking it
programmatically. Running it as a fresh slash command keeps the turn focused
and lets the user decide when to spend on it. The work is summarisation-heavy
and the input is tiny, so the cost path is `/model haiku` before invoking
(short/early sessions only — Haiku's 200k window can't hold a long
conversation) — ~10× cheaper than a frontier model, with identical output
(every dollar figure is pre-computed by `audit-extract.py`, not guessed by
the model).

## Reference files

### Session scope
- [`references/quick-audit.md`](references/quick-audit.md) — Distilled
  ratios + cache health + top expensive turns. Read when scope=session,
  mode=quick.
- [`references/detailed-audit.md`](references/detailed-audit.md) — Quick
  audit findings plus config + re-read scans. Read when scope=session,
  mode=detailed.

### Project scope
- [`references/project-quick-audit.md`](references/project-quick-audit.md) —
  Per-session cost outliers, cache health, breaks, weekly trend. Read when
  scope=project, mode=quick.
- [`references/project-detailed-audit.md`](references/project-detailed-audit.md) —
  Project quick findings plus per-session turn-level drilldown on the most
  expensive sessions. Read when scope=project, mode=detailed.

### Instance scope
- [`references/instance-quick-audit.md`](references/instance-quick-audit.md) —
  Per-project cost breakdown, cache health, weekly cost trend. Used for both
  quick and detailed modes (no per-turn data available at instance scope).
