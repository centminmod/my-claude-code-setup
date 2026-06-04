# Optional post-export audit — reference

> Loaded on demand from `SKILL.md` after an `--output` export, to append the
> scope-appropriate `/audit-session-metrics` suggestion. The audit is
> user-initiated — never invoked programmatically from the export turn.

## Optional post-export audit

When any `--output` format is specified (`html`, `csv`, `md`, or `json`),
always include `json` in the script invocation if it is not already present.
For example, if the user asked for `--output html`, run the script with
`--output html json`. This ensures the JSON export is always written and the
audit suggestion can always be shown.

After all `[export] FMT → path` lines are printed and the optional
`[self-cost]` line lands, append an audit suggestion based on the export scope.
Determine scope from the JSON filename printed by the `[export] JSON` line:

- `session_*.json` → session scope
- `project_*.json` → project scope
- `instance/*/index.json` → instance scope

**Session scope:**
> Want a token-usage audit of this session?
>   `/audit-session-metrics quick   <json-path>`
>   `/audit-session-metrics detailed <json-path>`  (also reads CLAUDE.md + settings)

**Project scope:**
> Want a per-session cost and cache health audit of this project?
>   `/audit-session-metrics quick   <json-path>`   (surfaces top expensive sessions, cache outliers)
>   `/audit-session-metrics detailed <json-path>`  (also drills into top session turn patterns)

**Instance scope:**
> Want a cross-project cost breakdown audit?
>   `/audit-session-metrics quick   <json-path>`   (per-project cost shares and cache health)

Substitute `<json-path>` with the actual path printed by the
`[export] JSON` line. The audit is summarisation-heavy and reads only the
disk export (not the conversation), so for a ~10× cheaper run the user can
`/model haiku` before invoking (short/early sessions only — Haiku's 200k
window can't hold a long conversation) — the skill no longer pins a model
itself.

**Do not invoke `audit-session-metrics` programmatically from this
turn.** It is a separate, user-initiated audit: running it as its own
slash command keeps the turn focused and lets the user decide when to
spend on it (and on which model). The user runs the slash command at
their own discretion.
