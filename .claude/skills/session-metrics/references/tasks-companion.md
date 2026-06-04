# Automatic Tasks companion — reference

> Loaded on demand from `SKILL.md` for a single-session HTML export with
> 2–40 request units. The deterministic worksheet (`--prepare-tasks`) is
> your single source of grouping signals — do not re-probe the JSON.

## Automatic Tasks companion (no extra command)

The per-request breakdown is the deterministic foundation for **task grouping**
("what was I actually trying to do"). To remove the friction of a separate
`/task-breakdown` step, the Tasks companion is generated **automatically as part
of an HTML export**, in this same turn — the user gets it for free.

**Scope gate — the auto-companion is a single-session feature.** Generate it
only for **single-session exports** (the default route / `--session <id>`).
**Never** auto-generate it for `--project-cost` or `--all-projects`: semantic
task grouping does not span sessions, and hand-grouping hundreds of requests
across many sessions is impractical and not meaningful (this is exactly the
case that produces a single blank "blob" task). At project / instance scope,
skip both the companion and the nav button, and simply tell the user that
`/task-breakdown` can be run manually on a *single* session if they want a
task view.

**When `html` is among the requested formats AND this is a single-session
export AND the auto-companion will actually be generated** (see the count gate
below), add `--task-companion-nav` to the script invocation (alongside the
always-on `json`). This renders a `Tasks` nav button on the dashboard/detail
pages pointing at `<stem>_tasks.html`. Do **not** add `--task-companion-nav`
when you are skipping the companion — it would render a button pointing at a
`<stem>_tasks.html` that was never written (a dead link).

**Then, after the `[export]` lines, if this is a single-session export and the
JSON export's `request_units` array has between 2 and 40 entries**, generate
the companion automatically. Skip when there is only one unit (a single-prompt
session needs no grouping) or when there are more than ~40 units (an unusually
large session — tell the user it is too large for a clean auto-grouping and
that `/task-breakdown` remains available manually).

You are an **editor, not an author**: `--prepare-tasks` does the deterministic
work (clustering, seeded titles, suggested verdicts) and writes a *renderable*
skeleton; you only refine the semantic parts. This is far cheaper than
authoring `grouping.json` from scratch.

1. Run `--prepare-tasks` — it prints a compact per-request worksheet to stdout
   and writes a candidate `<stem>_grouping.json` next to the export:

   ```bash
   uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --prepare-tasks \
     <export.json>
   ```

   The worksheet is your single source of grouping signals — **do not re-probe
   the JSON with `jq`/`Read`.** Each row carries the unit's candidate cluster
   (`cl`), turns, cost, tokens, `risk/reread/cbreak`, idle gap, snippet, and
   tools. `[cont]` = an agent-completion continuation, `[blank]` = a no-prompt
   unit; both are pre-attached to the preceding cluster.

2. **Edit** the skeleton `grouping.json` (do not rewrite it from scratch):
   - **Titles** — replace each seeded title with a real task name, and **remove
     that task's `_auto_title` field** (or set it `false`) once you've named it.
     A leftover `_auto_title` on a task covering >60% of requests trips a
     collapse warning at render time — that is the safety net for an unedited
     skeleton, not a target.
   - **Merge / split** — combine clusters that are one semantic task (rewrite
     the affected tasks' `request_unit_ids`); split a cluster only when the
     worksheet clearly shows two distinct goals (e.g. a real prompt that the
     heuristic over-attached). Keep every `unit_id` covered exactly once.
   - **Rationales** — write a one-line `rationale` per task.
   - **Verdicts** — the skeleton pre-fills `worth_it`/`mixed`; a blank `verdict`
     means the waste signals were high enough that *you* must judge it (use the
     `_hint.suggested_verdict` and the worksheet's `risk/reread/cbreak` as
     evidence — **bias toward `mixed`/`worth_it` when unsure**, never re-sum
     numbers). Override a pre-filled verdict only when you actively disagree.

   The `_auto_title` / `_hint` underscore fields are advisory — the renderer
   ignores them for all cost/coverage math.

3. Run the renderer (it recomputes all totals from the export and validates the
   grouping). Make sure the edited JSON still parses first:

   ```bash
   uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --render-tasks \
     <export.json> <grouping.json>
   ```

4. Tell the user the task list (verdicts + turns + cost, read back from the
   renderer's stdout / the rendered `*_tasks.md` — do not recompute) and the
   `*_tasks.html` / `*_tasks.md` paths. The dashboard `Tasks` nav button now
   resolves to that page. If the renderer printed a collapse warning, fix the
   grouping and re-render rather than shipping it.

This is automatic for HTML exports. The standalone `/task-breakdown
<json-path>` skill remains for re-grouping a saved JSON export later without
re-running session-metrics. It is session-oriented; pointing it at a
project-scope export with hundreds of units will produce a coarse grouping at
best, so prefer a single-session export as its input. Keep it lightweight:
most sessions are a handful of tasks; don't over- or under-segment. The
deterministic "Per-request breakdown" section in the dashboard is the honest
*per-request* view; the Tasks page is the *semantic* layer you just authored.
