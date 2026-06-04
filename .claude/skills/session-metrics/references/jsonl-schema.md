# Claude Code JSONL Log Schema

Location: `~/.claude/projects/<slug>/<session-uuid>.jsonl`

Each line is a self-contained JSON object (newline-delimited JSON / NDJSON).

This document serves two audiences:

1. **Maintainers debugging the parser** → the structural reference
   (entry types, shapes, dedup rules, subagent behaviour).
2. **Anyone deciding what data to surface in reports** → the **field
   catalogue** with a *Surfaced in reports?* column and the
   **Expansion-opportunity summary** at the bottom that lists the
   shortest path from "field is present in the JSONL" to "field is
   visible in HTML/MD/JSON/CSV output".

The catalogue below was built from empirical inspection of real
sessions in `~/.claude/projects/`; if you spot a field shape the doc
doesn't mention, append to it.

---

## Entry type index

| Type              | Purpose                                                           | Carries token usage?     |
|-------------------|-------------------------------------------------------------------|--------------------------|
| `assistant`       | Claude's API response — text, tool calls, thinking blocks         | **Yes** (`message.usage`)|
| `user`            | Human prompt **or** auto-generated `tool_result` payload          | No                       |
| `attachment`      | Wraps hook outputs, pasted files, and tool-use side payloads      | No                       |
| `queue-operation` | Prompt queue lifecycle (`enqueue`, …)                             | No                       |
| `last-prompt`     | Restore hint — last user prompt in the session                    | No                       |
| `system`          | Claude Code system events (e.g. Stop-hook summaries)              | No                       |
| `summary`         | Context-compression checkpoints (rare, not always present)        | No                       |

The parser (`scripts/session-metrics.py`) reads token data only from
`assistant` entries. Everything else is metadata today.

---

## Assistant entry — the cost-bearing shape

```json
{
  "type": "assistant",
  "uuid": "7e538ffb-…",
  "parentUuid": "49422fd5-…",
  "isSidechain": false,
  "timestamp": "2026-04-15T02:32:32.185Z",
  "sessionId": "60fb0cc8-…",
  "cwd": "/home/user/projects/myapp",
  "version": "2.1.111",
  "gitBranch": "master",
  "entrypoint": "claude-desktop",
  "userType": "external",
  "slug": "-home-user-projects-myapp",
  "requestId": "req_011Ca4moqagPBTkv4htSbuMU",
  "message": {
    "id": "msg_01GvBhABmRVqm3qv4G6innqL",
    "model": "claude-sonnet-4-6",
    "role": "assistant",
    "type": "message",
    "stop_reason": "tool_use",
    "stop_details": null,
    "stop_sequence": null,
    "content": [ /* thinking / tool_use / text blocks */ ],
    "usage": {
      "input_tokens": 10,
      "output_tokens": 208,
      "cache_read_input_tokens": 27839,
      "cache_creation_input_tokens": 468,
      "cache_creation": {
        "ephemeral_1h_input_tokens": 468,
        "ephemeral_5m_input_tokens": 0
      },
      "server_tool_use": {
        "web_search_requests": 0,
        "web_fetch_requests": 0
      },
      "service_tier": "standard",
      "speed": "standard",
      "inference_geo": "",
      "iterations": [ /* per-iteration breakdown */ ]
    }
  }
}
```

### Top-level fields (assistant entry)

| Field             | Description                                        | Surfaced in reports?                                |
|-------------------|----------------------------------------------------|-----------------------------------------------------|
| `type`            | Always `"assistant"` here.                         | filter                                              |
| `uuid`            | Per-entry UUID.                                    | N/A                                                 |
| `parentUuid`      | Threading parent.                                  | N/A                                                 |
| `sessionId`       | Session ID (matches filename).                     | **tracked** (session grouping)                      |
| `timestamp`       | ISO-8601 UTC.                                      | **tracked** (timeline, re-rendered in user tz)      |
| `cwd`             | Working directory when the turn ran.               | **tracked** (slug derivation)                       |
| `version`         | Claude Code version.                               | available-not-shown                                 |
| `gitBranch`       | Git branch at turn time.                           | available-not-shown — useful for cost-by-branch     |
| `entrypoint`      | `claude-desktop`, `claude-code`, …                 | available-not-shown                                 |
| `userType`        | `external` / `internal`.                           | N/A                                                 |
| `isSidechain`     | `true` for subagent turns.                         | **tracked** (default filter; `--include-subagents` flips it) |
| `slug`            | Project slug string.                               | redundant (derivable from `cwd`)                    |
| `requestId`       | Anthropic API request ID.                          | available-not-shown — useful for API-log x-ref      |
| `advisorModel`    | String — e.g. `"claude-opus-4-7"`. Stamped on **every** assistant entry when the Advisor feature is configured for the session, regardless of whether the advisor was actually called on that turn. Absent when Advisor is not configured. Use to detect advisor-enabled sessions and to look up advisor model pricing. | **tracked** (session-level `advisor_configured_model` field; drives "Advisor calls" dashboard card) |
| `message`         | The payload (see below).                           | **tracked** (all cost data is here)                 |

### `message` fields (assistant role)

| Field           | Description                                              | Surfaced in reports?                               |
|-----------------|----------------------------------------------------------|----------------------------------------------------|
| `id`            | `msg_…` Anthropic message ID.                            | **tracked** (dedup key — see below)                |
| `model`         | Pricing-lookup key.                                      | **tracked** (Model column)                         |
| `role`          | Always `"assistant"`.                                    | filter                                             |
| `type`          | Always `"message"`.                                      | N/A                                                |
| `stop_reason`   | `end_turn`, `tool_use`, `max_tokens`, `stop_sequence`.   | available-not-shown — flag truncated responses     |
| `stop_details`  | Sub-object when the stop reason has nuance. Often null.  | N/A                                                |
| `stop_sequence` | Matched stop-sequence string, if any.                    | N/A                                                |
| `content`       | Array of content blocks — see **Content blocks** below.  | partially surfaced (Model column shows some info; see Proposal B) |
| `usage`         | Token usage dictionary — see next table.                 | **tracked**                                        |

### `message.usage` — billable vs. metadata field dictionary

| Field                                         | Billable?                          | Description                                                                                          | Surfaced in reports?                                              |
|-----------------------------------------------|------------------------------------|------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| `input_tokens`                                | **Yes** — input rate               | Net new input tokens (excludes cached).                                                              | **tracked** (Input column, cost)                                  |
| `output_tokens`                               | **Yes** — output rate              | All output. **Includes thinking-block tokens** and tool_use serialised args — these roll up here.    | **tracked** (Output column, cost)                                 |
| `cache_read_input_tokens`                     | **Yes** — cache_read rate (0.1× input) | Tokens served from prompt cache.                                                                 | **tracked** (CacheRd column, cost)                                |
| `cache_creation_input_tokens`                 | **Yes** — cache_write rate         | Tokens written into the cache. **Sum** of the 5m and 1h ephemeral buckets.                           | **tracked** (CacheWr column). Currently all priced at 5m rate — see Proposal A. |
| `cache_creation.ephemeral_5m_input_tokens`    | **Yes** — 1.25× input (5m rate)    | Portion of the cache write landing in the 5-minute TTL tier.                                         | **available-not-shown** — Proposal A                              |
| `cache_creation.ephemeral_1h_input_tokens`    | **Yes** — 2× input (1h rate)       | Portion of the cache write landing in the 1-hour TTL tier. **Currently under-costed.**               | **available-not-shown** — Proposal A                              |
| `server_tool_use.web_search_requests`         | **Yes** — $0.01/request            | Count of web-search requests Claude made server-side this turn.                                      | **Billed since v1.64.0** — `_cost` adds requests × $0.01 (after any fast mult) |
| `server_tool_use.web_fetch_requests`          | No — token-only                    | Count of web-fetch requests Claude made server-side this turn.                                       | No per-request charge (Anthropic pricing) — intentionally not billed |
| `service_tier`                                | Metadata                           | `"standard"` observed; priority tier is a possible other value.                                      | N/A                                                               |
| `speed`                                       | Metadata (drives multiplier)       | `"standard"` or `"fast"` (Claude Code `/fast` mode).                                                 | **tracked** (Mode column). 6× fast-mode multiplier is **not** applied in cost math — known limitation, see `references/pricing.md`. |
| `inference_geo`                               | Multiplier (1.0× or 1.1×)          | Empty string in observed data. Anthropic documents US-only inference at 1.1× (data-residency surcharge). | available-not-shown                                               |
| `iterations`                                  | **Yes** (when advisor called)      | Array of per-iteration usage for turns that stream across multiple passes. Length 1 on regular turns. On advisor turns the array has **3 entries**: `{type:"message"}` (pre-advisor pass), `{type:"advisor_message", input_tokens:N, output_tokens:M, model:"claude-opus-4-7"}` (the advisor model's own inference billed at list rates with no caching discount), and another `{type:"message"}` (post-advisor pass). The advisor iteration's tokens are **not** reflected in the top-level `usage` fields — they must be extracted from `iterations` to avoid a 6.6× cost under-count. | **tracked** (v1.25.0) — `_advisor_info()` extracts advisor tokens; cost added to `cost_usd` via `_cost()` |

**Derived per-turn values the parser computes** (not fields in the JSONL):
`total_tokens` (sum of the four billable token buckets) and `cost_usd`
(per `_cost()` in `scripts/session-metrics.py:92`).

---

## Content blocks (`message.content[]`)

Each element of `content` is an object with a `type`. Empirical counts
across two sampled sessions: `thinking` × 47, `tool_use` × 105,
`tool_result` × 105, `text` × 24, `image` × 1.

### `thinking` (assistant-message block)

Anthropic extended-thinking block.

- **Billing.** Thinking tokens are **rolled into `output_tokens`** and
  billed at the output rate. There is **no** separate
  `thinking_tokens` field on `usage`.
- **Storage in Claude Code JSONL.** The `thinking` string is stored
  **empty** and only a `signature` is retained (signature-only block).
  Per-turn thinking-token counts are **not recoverable** from the
  transcript alone.
- **What *is* possible:** counting the number of `thinking` blocks
  per turn and per session — see Proposal B.

Observed shape:

```json
{"type": "thinking", "signature": "<opaque>", "thinking": ""}
```

### `tool_use` (assistant-message block)

A tool call the model is requesting. The block carries the tool's
`name`, serialised `input` (arguments), and its own `id`. Tokens for
the block are inside `output_tokens`; the block count is an
independent behavioural signal.

Tool names observed in sampled sessions include `Read`, `Bash`,
`Edit`, `Write`, `Glob`, `Grep`, `Agent`, `TodoWrite`, `WebSearch`,
`ExitPlanMode`, `AskUserQuestion`, `ToolSearch`.

### `text` (assistant-message block)

Plain prose output from Claude. Tokens counted in `output_tokens`.

### `tool_result` (user-entry block)

The tool's response, written to the JSONL as a `user`-type entry
immediately after the assistant's `tool_use`. **Must be filtered out
when counting user-prompt activity** — otherwise user-activity
metrics inflate 10-20× on tool-heavy sessions. Implementation:
`_is_user_prompt` in `scripts/session-metrics.py`.

### `image` (user-entry block)

Pasted / attached image. Rare in shell-bound sessions.

### `server_tool_use` (assistant-message block)

Server-side tool invocation. The `id` field uses a `srvtoolu_` prefix
(distinct from the `toolu_` prefix on client-side `tool_use` blocks).
The `name` field identifies the server tool — currently only
`"advisor"` is observed in practice.

When `name == "advisor"`, this block marks an advisor call. The advisor
model's inference cost is **not** in the top-level `usage` fields; it
is carried by the `usage.iterations` entry with `type == "advisor_message"`.

Observed shape:

```json
{"type": "server_tool_use", "id": "srvtoolu_01Abc", "name": "advisor", "input": {}}
```

**Content encoding.** Classified as letter `v` in the timeline Content
column. The tool name `"advisor"` is added to `tool_use_names` and
appears in the per-turn drawer's tools list alongside client-side tools.

### `advisor_tool_result` (assistant-message block)

The encrypted response returned by the advisor model. `content` is an
array with a single `advisor_redacted_result` entry whose `data` field
holds the encrypted payload — the advisor's feedback is not readable
from the JSONL.

Observed shape:

```json
{
  "type": "advisor_tool_result",
  "tool_use_id": "srvtoolu_01Abc",
  "content": [{"type": "advisor_redacted_result", "data": "REDACTED_ENCRYPTED_CONTENT"}]
}
```

**Content encoding.** Classified as letter `R` in the timeline Content
column. Always paired with a preceding `server_tool_use` block with the
same `tool_use_id`.

### `text` (user-entry block)

The user's typed prompt. Also observed as a **plain string** (see
**User entry** below) rather than a structured block.

---

## User entry

```json
{
  "type": "user",
  "uuid": "…",
  "parentUuid": "…",
  "timestamp": "2026-04-15T02:32:30.000Z",
  "sessionId": "…",
  "message": {
    "role": "user",
    "content": [ /* blocks */ ]   // OR a plain string — both shapes observed
  }
}
```

`message.content` has **two** observed shapes:

1. **List of content blocks** — blocks of `type`: `text`, `image`,
   `tool_result`.
2. **Plain string** (~10% of entries) — a direct user prompt with no
   structured wrapper.

**Filter rule for user-activity metrics.** A genuine user prompt is a
user entry whose `message.content` is either a non-empty string **or**
a list containing at least one `text`/`image` block. Pure
`tool_result`-only lists must be excluded — see `_is_user_prompt` in
`scripts/session-metrics.py`.

Top-level fields unique to user entries (beyond the assistant-entry
set): `isMeta`, `permissionMode` (e.g. `"plan"`), `promptId`,
`toolUseResult`, `sourceToolAssistantUUID`.

---

## Specialty entry types

### `attachment`

Wraps hook outputs, pasted files, and tool-use side payloads. The
top-level `attachment` sub-object carries `type` (e.g. `hook_success`),
`hookName`, `toolUseID`, and the rich payload inline. Not cost-bearing.
Relevant if you ever want to surface hook-firing counts — currently
ignored by the parser.

### `queue-operation`

Tiny prompt-queue lifecycle events: `type`, `operation` (e.g.
`enqueue`), `sessionId`, `timestamp`, `content` (the queued prompt
text). Not cost-bearing.

### `last-prompt`

Session restore hint. Fields: `type`, `sessionId`, `lastPrompt`. Not
cost-bearing.

### `system`

Claude Code system events. Most common subtype observed is
`stop_hook_summary`, with fields: `subtype`, `hookCount`, `hookInfos[]`,
`hookErrors[]`, `preventedContinuation`, `level`, `toolUseID`,
`stopReason`, `hasOutput`. Useful if you ever want to report hook
failure rate or prevented-continuation events. Currently ignored by
the parser.

### `summary`

Context-compression checkpoints — `type`, `summary`, `leafUuid`. Not
observed in every session. Not cost-bearing.

---

## Deduplication behaviour

Claude Code writes the same `message.id` to the JSONL at multiple
lifecycle points (start of stream, after each tool result, after
final `stop_reason`). Token counts in earlier writes may be partial
or zero.

**Always keep the LAST occurrence** of each `message.id` — it reflects
the final settled usage values.

---

## Subagent logs

Spawned agents (Agent/Task tool) write to
`<session-uuid>/subagents/agent-<hex>.jsonl`. Folded in by default
(`--include-subagents`, on); pass `--no-include-subagents` to skip.

### Dynamic-workflow transcripts (Workflow tool, v1.48.0)

The `Workflow` tool (dynamic workflows / ultracode) fans out to
**20–100+ agents** per run, and their transcripts live **one tier
deeper** than the Agent/Task path:

```
<session-uuid>/
  subagents/
    agent-<hex>.jsonl                       ← Agent/Task subagents
    workflows/<runId>/
        agent-<hex>.jsonl                   ← WORKFLOW agents (full usage; the bulk of ultracode cost)
        agent-<hex>.meta.json               ← {agentType, description}
        journal.jsonl                       ← key/value event log, NO usage — MUST be excluded
  workflows/
    wf_<runId>.json                         ← run journal (metadata, sibling of subagents/)
    scripts/<name>-<runId>.js               ← the workflow script
```

- **Cost source of truth = the nested `agent-*.jsonl` transcripts.** They
  carry full per-message `usage`, so the existing per-model pricing tallies
  them exactly (incl. cache-read, which dominates). Discovered by
  `_load_session` walking `subagents/workflows/<runId>/`; gated by
  `--include-workflows` (default on, requires `--include-subagents`).
- **`wf_<runId>.json` journal = display metadata only.** Mined by
  `_parse_workflow_journal` for `workflowName`, `status`, `phases[]`,
  `totalToolCalls`, `durationMs`, and the per-agent
  `workflowProgress[type=workflow_agent]` entries (`label`, `model`,
  `tokens`, `phaseTitle`, `promptPreview`/`resultPreview`). Its own
  top-level `totalTokens` **excludes cache reads** and is NOT used for cost.
- **`agents` vs `agent_count`.** The `by_workflow` row's `agents` counts
  distinct agent **transcripts on disk** (often `agentCount + 1` — the run
  includes one `<synthetic>`-model orchestrator placeholder, zero-priced via
  `_pricing_for`); `agent_count` is the journal's reported figure. They are
  *supposed* to differ — not a reconciliation bug.
- **Attribution.** Workflow agents have `parentUuid: null` and no
  main-thread per-agent tool_use, so the agentId path orphans. Instead the
  main-thread `toolUseResult.runId` + the sibling `tool_result.tool_use_id`
  bridge `runId → tool_use_id → spawning-prompt anchor` (captured pre-dedup
  so a resumed session can't lose the link). Surfaced via the dedicated
  **Dynamic workflows** table (session/project/instance), the
  `by_workflow` JSON array, the MD/CSV sections, and an auto-emitted
  `*_workflows.html` companion deep-dive (phase→agent timeline).

---

## Expansion-opportunity summary

Shortlist of untracked-but-available fields, ordered highest-ROI
first. Each row is a candidate for a future report-expansion plan.

| Field / signal                                                    | If surfaced, the report gains…                                                                                                              |
|-------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| `cache_creation.ephemeral_{5m,1h}_input_tokens`                   | **Proposal A** *(implemented v1.2.0)*. Fixes 1h-tier cost under-count + "Cache TTL mix" dashboard card.                                    |
| `message.content[].type` counts (thinking / tool_use / text / tool_result / image) | **Proposal B** *(implemented v1.3.0)*. Per-turn "Content" column + "Extended thinking engagement" and "Tool calls" cards.         |
| Cross-cutting derived insights (parallel sessions, big context, big cache misses, subagent-heavy, top-3 tool dominance, off-peak share, cost concentration, model mix, session pacing, long sessions) | **Proposal C** *(implemented v1.5.0)*. Computes 10 candidate "Usage Insights" with auto-hide thresholds; renders the highest-value as an above-the-fold prose insight + the rest in a `<details>` accordion on the HTML dashboard. Also flows into JSON (`usage_insights`) and Markdown (`## Usage Insights` section). Inspired by Anthropic's `/usage` slash command. No cost-math change — pure derivation pass. |
| Cache-break events (single turns >100 k uncached) + `by_skill` + `by_subagent_type` aggregation + UUID-based cross-file dedup | **Proposal D** *(implemented v1.6.0)*. Inspired by Anthropic's `session-report` skill. Three new cross-cutting sections auto-hide when empty and render at every scope (session / project / instance): Cache breaks (configurable threshold via `--cache-break-threshold`, with ±2 user-prompt context), Skills & slash commands (invocations / turns / cost / % cached), and Subagent types (spawn count always; token cost when `--include-subagents`). UUID-based seen-set dedup runs at project + instance scope to prevent resumed-session replays from double-counting. No cost-math change for single-session reports; instance reports gain a correctness fix. |
| `toolUseResult.agentId` (top-level on user entries) + Agent/Task `tool_use.id` + filename-derived subagent agentId | **Proposal E** *(implemented v1.7.0)*. Subagent → parent-prompt token attribution via three-stage linkage (mirrors Anthropic's `session-report` model): Stage 1 maps `tool_use.id → prompt_anchor_index`, Stage 2 maps `agentId → anchor` via `toolUseResult.agentId` paired with the tool_result block's `tool_use_id`, Stage 3 walks the chain (with cycle guard) to roll subagent tokens onto the **root** user prompt. New per-turn fields `attributed_subagent_tokens / _cost / _count` are purely additive — `cost_usd` and `total_tokens` on every turn are unchanged so existing aggregators see identical numbers. HTML prompts table sorts by `cost_usd + attributed_subagent_cost` by default (toggleable via `--sort-prompts-by`); CSV/JSON keep `self` ordering. Disable with `--no-subagent-attribution`. |
| `advisorModel` (entry field) + `server_tool_use` / `advisor_tool_result` content blocks + `usage.iterations[type=="advisor_message"]` | **Implemented v1.25.0.** Advisor cost correction (up to 6.6× previously hidden cost per call), new content block classification letters `v` / `R`, per-turn advisor fields (`advisor_calls`, `advisor_cost_usd`, `advisor_model`, `advisor_input_tokens`, `advisor_output_tokens`), session-level `advisor_configured_model`, "Advisor calls" dashboard card, advisor annotation on project-cost session rows, and schema documentation for 4 new fields. Graceful degradation: sessions without advisor activity are unaffected. |
| `server_tool_use.{web_search,web_fetch}_requests`                 | **Implemented v1.64.0** (web_search): `_cost` adds `web_search_requests × $0.01` after any fast multiplier. `web_fetch` confirmed token-only (no per-request charge). See **Adjacent**. |
| `usage.speed == "fast"` cost multiplier                           | **Implemented v1.64.0.** Per-model fast tier (Opus 4.6/4.7 6×, 4.8 2×) scales the primary token cost; advisor sub-cost excluded; `--no-fast-premium` disables. See `references/pricing.md` § Fast mode. |
| `usage.inference_geo`                                             | 1.1× multiplier for US-only inference. Untracked; no non-empty values observed yet.                                                         |
| `message.stop_reason`, `message.stop_details`                     | Flag truncated-response turns (`max_tokens`), surface non-standard stops in a "Notes" column.                                               |
| `message.content[].tool_use.name`                                 | Top-N called tools in the dashboard. Cheap to extract.                                                                                      |
| `gitBranch`                                                       | Cost-by-branch aggregation — useful for feature-cost accounting.                                                                            |
| `version`                                                         | Cost-by-Claude-Code-version trend; minor value.                                                                                             |
| `system.stop_hook_summary` fields (`hookErrors`, `preventedContinuation`) | Hook-failure rate / prevention rate as a session-health signal.                                                                  |

---

## Proposal A — Ephemeral cache TTL drilldown

**Status:** **Implemented in v1.2.0.** Cost math, per-turn records,
CSV/JSON exports, the Markdown legend + annotation, the HTML TTL
badge + "Cache TTL mix" dashboard card, and the new column legend
all ship in this release. The sections below are retained as
historical design context.

**Fields.** `cache_creation.ephemeral_1h_input_tokens` and
`cache_creation.ephemeral_5m_input_tokens` (both nested inside
`message.usage.cache_creation`).

**Why it matters.** Anthropic bills the two TTL tiers differently:
5-minute cache writes cost **1.25× base input**, 1-hour writes cost
**2× base input**. The skill's pricing table today stores only one
`cache_write` rate per model (the 5-minute rate — see
[`references/pricing.md`](pricing.md) lines 51-53). Turns that pay
the 1-hour premium are **under-costed by up to 60%** on the
cache-write component. This drilldown turns the existing known
limitation into a fix.

**What to surface.**

1. **Pricing accuracy fix.** Extend `_PRICING` with a `cache_write_1h`
   rate per model (2× base input). `_cost()` splits
   `cache_creation_input_tokens` into its 1h and 5m buckets using the
   `cache_creation.ephemeral_*_input_tokens` fields and charges each
   at the correct rate. Falls back to the existing 5m rate when the
   drilldown is absent (legacy / foreign transcripts).
2. **Per-turn display (HTML detail + MD).** Keep the single `CacheWr`
   column for scanability, but have the tooltip / md cell show
   `A + B (1h + 5m)`. Add a compact TTL badge — `1h` / `5m` / `mix` —
   next to the value so 1h-heavy turns are visible at a glance.
3. **CSV/JSON exports.** Two new per-turn numeric fields:
   `cache_write_5m_tokens`, `cache_write_1h_tokens`. Existing
   `cache_write_tokens` stays as the sum for backwards compatibility.
4. **HTML dashboard card — "Cache TTL mix".** Totals for the session
   (and per-session in project mode): share of cache writes that were
   1-hour vs 5-minute, and the **extra cost paid for 1h tier**
   (`1h_tokens × (1h_rate − 5m_rate) / 1_000_000`). Makes the
   trade-off explicit.
5. **Cache savings footer.** The existing "cache savings vs no-cache"
   footer gains a 1h-tier line so the 1h investment is accounted for
   distinctly.

**Script touchpoints.** `_PRICING` (lines 57-80), `_cost()` (line 92),
`_build_turn_record()` (lines 787-806), HTML table header/row
(~2697-2791), CSV header (line 1164), JSON schema, dashboard card
templates.

---

## Proposal B — Content-block distribution

> **Status: Implemented in v1.3.0.** The prose below is preserved as
> historical design context. See `SKILL.md` for the current column/card
> specification and `scripts/session-metrics.py` for the
> implementation.

**Fields.** Per-turn counts of `message.content[].type` values:
`thinking`, `tool_use`, `text` on assistant entries, and
`tool_result`, `image` on the preceding user entry.

**Why it matters.** Cost columns tell users *how expensive* a turn
was, not *what the model was doing*. Block counts cheaply distinguish:

- **Agentic turns** — high `tool_use`, few `text`.
- **Conversational turns** — `text`-dominant, no `tool_use`.
- **Extended-thinking turns** — `thinking` blocks present.
  (Signature-only storage: the block count is real but the per-turn
  thinking-token count is **not** recoverable — thinking tokens
  already flow through `output_tokens` and its cost.)
- **Multimodal turns** — `image` blocks on the paired user entry.

None of these shapes are inferable from token counts alone.

**What to surface.**

1. **Per-turn "Content" column (HTML detail + MD).** Compact letter
   encoding such as `T3 u2 x1` (3 thinking, 2 tool_use, 1 text).
   Tooltip / md footnote explains the legend. Zero counts omitted
   so short rows stay clean. Emoji variant possible if the user
   explicitly opts in.
2. **CSV/JSON exports.** Per-turn integer fields:
   `thinking_blocks`, `tool_use_blocks`, `text_blocks`, plus
   `tool_result_blocks` and `image_blocks` attributed from the
   preceding user entry.
3. **HTML dashboard cards.**
   - *Extended thinking engagement* — "N of M assistant turns
     (X%) contained thinking blocks; Y thinking blocks total." Plain
     counts, no token claim. A short tooltip explains the
     signature-only caveat so nobody over-interprets it.
   - *Tool calls* — total `tool_use` blocks, average per assistant
     turn, top-3 most-called tool names (from `tool_use.name`).
4. **Optional chart (HTML detail).** Stacked bar per turn showing
   `thinking / tool_use / text` counts — a behavioural timeline
   paired with the existing cost timeline. Opt-in via the existing
   `--chart-lib` wiring so it inherits the lib choice.
5. **Explicit non-scope note.** There will **not** be a "thinking
   tokens" column. Anthropic rolls thinking tokens into
   `output_tokens` and Claude Code stores thinking text
   signature-only. Any column purporting to report thinking tokens
   from the JSONL would be an estimate, not a measurement.

**Script touchpoints.** `_extract_turns()` (line 196) gains
content-block counting; per-turn record schema grows five integer
fields; CSV header + JSON schema + HTML templates gain matching
columns/cards.

---

## Adjacent — server-side tool billing

`server_tool_use.web_search_requests` is billed **$0.01 per request**
($10 / 1,000 searches) by Anthropic, outside the token rate. **Since
v1.64.0** `_cost` / `_no_cache_cost` add `web_search_requests × $0.01`
**after** any fast-mode multiplier (a flat per-request charge is not
tier-scaled). `server_tool_use.web_fetch_requests` carries **no
per-request charge** — it is token-only (the fetched content bills as
ordinary input tokens) — so it is intentionally **not** counted.
Source: Anthropic pricing § "Web search tool" / "Web fetch tool".
