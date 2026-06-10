# Model comparison (`--compare`)

Compare two Claude Code sessions — or two sets of sessions — across tokens, cost, cache behaviour, tool-call fan-out, and IFEval-style instruction compliance. Designed to answer:

- "Is the newer model really using more tokens on my content?"
- "How much of my cost delta is tokenizer-driven vs workload-driven?"
- "Does the compliance delta justify the cost delta?"

This doc is the long-form companion to the `--compare*` flags. Start at [When to use](#when-to-use), then follow one of the two workflows.

---

## When to use

You want a controlled comparison across two models on a fixed, reproducible prompt suite. Common cases:

- A new Claude model shipped; you want to know the cost impact on your specific content shape before switching.
- You already use both models in different contexts and want to attribute a spend swing.
- You need a reproducible "how much does my CLAUDE.md cost to summarise" number, not a vibes-based guess.

If you just want per-session metrics for today's work, don't use this — run `session-metrics` with no flags.

---

## Entry points

Four CLI surfaces. Pick the one that matches the input the user already has:

| Flag | Input | Output | Auth | Validity |
|------|-------|--------|------|----------|
| **`--compare-run`** *(preferred)* | Model IDs only (defaults to `[1m]` pair) | Auto-captures two sessions via `claude -p` headless, then renders Mode 1 report | Claude subscription (inherits Claude Code auth) | Clean attribution, same prompts both sides, no human-in-the-loop variance. |
| **`--compare A B`** Mode 1 (controlled) | Two single-session JSONLs that both ran the canonical suite | Per-turn paired table, IFEval column, tokenizer-ratio summary | None (reads local JSONL) | Clean attribution if both ran the canonical suite. |
| **`--compare A B`** Mode 2 (observational) | `all-<family>` or two project-level specifiers | Aggregate-only cards, no per-turn pairing | None (reads local JSONL) | Drift summary. Conflates tokenizer shift with prompt-distribution shift. |
| **`--count-tokens-only`** | Prompt suite + model IDs | Input-token counts only, no inference | `ANTHROPIC_API_KEY` | Input-only. Can't measure output/cost. Use for a pre-capture tokenizer smoke test. |

`--compare` `auto` scope (default) picks Mode 1 for session pairs, Mode 2 for any `all-<family>` arg. Force with `--compare-scope session|project`.

**Default model pair (for `--compare-run` and `--compare-prep`):**
`claude-opus-4-6[1m]` vs `claude-opus-4-7[1m]` — matches Claude Code's
shipping Opus tier. Users opt into the 200k variants by passing the
unsuffixed IDs. `--count-tokens-only` keeps the unsuffixed defaults
because the Anthropic API endpoint does not accept the `[1m]` tag.

---

## Workflow A — Automated (recommended)

**One command.** No `/model` juggling, no paste-10-prompts-twice,
no `/exit` dance. The skill spawns two [headless Claude Code](https://code.claude.com/docs/en/headless)
sub-processes under the hood (one per model), feeds each the canonical
suite, then runs `--compare` on the resulting JSONL pair. Runs entirely
against local JSONLs — no `ANTHROPIC_API_KEY` involved.

### Prerequisites

- **A Claude subscription plan** (Pro / Max / Team / Enterprise).
  Headless `claude -p` inherits whatever auth the interactive CLI is
  using — the same session quota, the same models.
- **`claude` on your PATH.** Verify with `claude --version`.
- **`/model` access to both models.** Headless uses the same entitlement
  system as interactive; if `/model claude-opus-4-6` doesn't work
  interactively, `claude -p --model claude-opus-4-6` won't either. Run
  `/model` in any existing session to inspect the picker.

### One command

```
/session-metrics compare-run claude-opus-4-6 claude-opus-4-7
```

(Or from a shell: `uv run python <skill-dir>/scripts/session-metrics.py
--compare-run claude-opus-4-6 claude-opus-4-7`.)

### The 4-way Opus combo

The two positional args accept any model ID your Claude subscription
exposes via `/model`. For the Opus 4 family that's typically these
four IDs (two models × two context tiers):

| ID | Variant |
|----|---------|
| `claude-opus-4-6` | 4.6, default context tier |
| `claude-opus-4-7` | 4.7, default context tier |
| `claude-opus-4-6[1m]` | 4.6, 1M-context tier |
| `claude-opus-4-7[1m]` | 4.7, 1M-context tier |

Any two of those IDs can be passed to `--compare-run`. Pick the pair
that matches what you are actually deciding:

| Pair | What the cost ratio measures |
|------|------------------------------|
| 4-6 vs 4-7 *(same tier)* | Tokenizer delta at default tier. |
| 4-6[1m] vs 4-7[1m] *(same tier)* | Tokenizer delta at 1M tier. |
| 4-6 vs 4-6[1m] *(same model)* | Pure context-tier delta. |
| 4-7 vs 4-7[1m] *(same model)* | Same, for 4.7. |
| 4-6 vs 4-7[1m] *(mixed)* | Tokenizer **and** tier. |
| 4-6[1m] vs 4-7 *(mixed)* | Same, flipped. |

Mixed-tier pairs are valid but will fire the compare report's
existing `context-tier-mismatch` advisory — the ratio then conflates
tokenizer shift with window-tier shift. Match tiers on both sides
when you want a clean tokenizer-only read.

Quote the brackets in an interactive shell: `'claude-opus-4-7[1m]'`
(bash / zsh treat `[…]` as a glob pattern). The slash-command
form (`/session-metrics compare-run …` inside Claude Code)
pre-tokenizes args, so quoting is unnecessary there.

The run will:

1. Create a throwaway scratch directory under `$TMPDIR` (override with
   `--compare-run-scratch-dir DIR`).
2. Gate on interactive confirmation — it prints *"about to run 20
   headless Claude Code invocations (10 prompts × 2 models) against
   your subscription quota"* and waits for `y`. Bypass with `--yes` /
   `-y` (required on non-TTY stdin).
3. For side A, mint one fresh session UUID and loop the 10 suite
   prompts through `claude -p --session-id <uuid>` (first) then
   `claude -p --resume <uuid>` (remaining nine). All 10 turns land in
   a single JSONL. Repeat for side B with a different UUID.
4. Auto-invoke the existing `--compare` renderer on the two JSONL
   paths. You get the same HTML / Markdown / JSON report as the
   manual workflow.

Every `claude -p` subprocess inherits a pinned tool set and permission
mode so both sides are symmetric:

- `--allowedTools "Bash,Read,Write,Edit,Glob,Grep"` (override with
  `--compare-run-allowed-tools`)
- `--permission-mode bypassPermissions` (override with
  `--compare-run-permission-mode`; pass `""` to omit)
- `--output-format json` (for deterministic stdout parsing)

Optional safety belts:

- `--compare-run-max-budget-usd USD` — per-subprocess cost ceiling
  (Claude Code's own `--max-budget-usd`).
- `--compare-run-per-call-timeout SECONDS` — wall-clock timeout per
  prompt; default 900 (15 min) because the `tool_heavy_task` prompt
  can fan out.
- `--compare-run-max-turns N` — agentic-loop ceiling threaded as
  `claude -p --max-turns <N>` to every subprocess; default 100 —
  deliberately far above any legitimate suite usage (the heaviest
  prompt, `tool_heavy_task`, needs ~5 turns) so the cap never binds
  on real behaviour and never censors the how-much-work-does-each-
  model-do signal the comparison measures. It is pure insurance
  against infinite retry loops; single stuck tool calls are bounded
  by the Bash timeout env caps + per-call timeout instead. Pass 0
  for unbounded turns.
- `--compare-run-effort [LEVEL [LEVEL]]` — pin `claude -p --effort`
  (`low | medium | high | xhigh | max`). Takes 0, 1, or 2 values:
  zero omits the flag entirely so each model keeps its shipping
  default (Opus 4.6 → `high`, Opus 4.7 → `xhigh`); one value applies
  to both sides; two values map to A and B. Use this when you want
  to hold effort constant across a version comparison (e.g. both
  sides at `high`) instead of letting each model fall back to its
  own default — useful when isolating tokenizer / algorithm changes
  from the effort-level change that ships alongside a new model.
  The resolved effort for each side is threaded into the compare
  report (text summary, Markdown "Effort" column, HTML side-meta,
  analysis.md front matter) so consumers of the artefacts can see
  what effort level produced the numbers.

Annotation-only flag for the `compare` route (when you're rendering
a report over two JSONLs that already exist and want the effort
labels to appear even though they're not recorded in the transcript):

- `--compare-effort [LEVEL [LEVEL]]` — purely cosmetic. Accepts 0,
  1, or 2 values like `--compare-run-effort`, but does **not** spawn
  any subprocess; it only tags the Side A / Side B metadata so the
  renderers show the effort level. `--compare-run` already infers
  the effort labels from `--compare-run-effort` automatically, so
  this flag is relevant only for the manual-capture / re-render
  workflows.

Prompt-steering flags for the `compare-run` route:

- `--compare-run-prompt-steering VARIANT` — wrap every prompt in the
  suite with steering text before feeding it to `claude -p`. VARIANT
  is one of `concise`, `think-step-by-step`, `ultrathink`, or
  `no-tools`. Applied symmetrically to both sides so the A/B remains
  apples-to-apples; what shifts is each model's behaviour under the
  same instruction, surfaced as token / cost / thinking / tool-call
  deltas vs the unsteered baseline.

- `--compare-run-prompt-steering-position {prefix,append,both}` —
  controls where the steering text lands relative to the prompt body.
  `prefix` prepends, `append` appends, `both` sandwiches the body
  between the variant's prefix and suffix. Default `prefix`. Ignored
  when `--compare-run-prompt-steering` is absent.

**On steering vs IFEval predicates.** The 10 prompts each carry an
IFEval predicate (e.g. exactly 120 words, exactly 3 bullets, no CJK
codepoints, valid JSON shape). When steering is applied, predicate
pass rates may legitimately differ from the unsteered baseline —
"be concise" can violate the 120-word constraint; "use extended
reasoning" can inflate output past the 200-token bound on the
stack-trace prompt. **That is the measurement, not a regression.**
Read pass-rate deltas under steering as a behavioural signal, not a
quality regression: a variant that compresses output but breaks two
strict predicates may still be the right tool for tasks where length
matters more than format compliance. For multi-variant sweeps with
auto-rendered comparison articles ranking variants on the
quality-vs-cost tradeoff, use the `benchmark-effort-prompt` skill.

**Variant phrasings.** The concise and think-step-by-step variants
quote the canonical phrasings from Anthropic's prompting best-
practices guide
([source](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)).
The ultrathink variant approximates the doc's "think harder /
thoroughly" guidance — Anthropic does not use the literal word
"ultrathink" in the guide; that is a Claude Code CLI magic word, not
a docs-recommended steer. The no-tools variant has no canonical
phrasing because the guide focuses on encouraging appropriate tool
*use* rather than blanket suppression. Edit
`_PROMPT_STEERING_VARIANTS` in `session_metrics_compare.py` to swap
phrasings; no callers depend on the wording.

**Note on thinking-word sensitivity.** Anthropic's guide notes that
Claude Opus 4.5 is "particularly sensitive to the word 'think' and
its variants" when extended thinking is *disabled*. That means the
deltas the benchmark measures for `think-step-by-step` and
`ultrathink` are conditional on the model's thinking configuration:
under adaptive thinking (the 4.6 / 4.7 default) the steers behave as
expected; with thinking disabled they may produce larger or
opposite-direction shifts than the unsteered baseline. When
interpreting cross-model results, hold the thinking configuration
constant or report it explicitly alongside the deltas.

If any single `claude -p` call fails, the orchestrator aborts with
the stderr from that call and leaves the partial JSONL on disk for
inspection. No retry loop — Claude Code itself handles transient
rate-limit retries internally (via `system/api_retry` events).

### Typical output

```
About to run --compare-run: 10 prompts × 2 models = 20 headless Claude Code invocations.
  Side A: claude-opus-4-6   Side B: claude-opus-4-7
  Scratch dir: /tmp/sm-compare-run-abc123
  (with --compare-run-effort high xhigh the Side line becomes:
   "Side A: claude-opus-4-6 (effort=high)   Side B: claude-opus-4-7 (effort=xhigh)")
Each call runs full inference and counts against your subscription quota / rate limit.
Proceed? [y/N]: y

=== Side A: claude-opus-4-6  session_id=<uuid-a> ===
  [claude-opus-4-6] prompt 1/10: claudemd_summarise
  [claude-opus-4-6] prompt 2/10: english_prose
  …
=== Side B: claude-opus-4-7  session_id=<uuid-b> ===
  [claude-opus-4-7] prompt 1/10: claudemd_summarise
  …
=== Capture complete. Rendering compare report (A=<uuid-a>, B=<uuid-b>) ===
<compare report output follows>
```

### Extras — per-session dashboards + analysis scaffold

`compare-run` **defaults to `--output md html`** so every invocation
emits the per-session dashboards + analysis scaffold on disk. The pre-
v1.7.1 text-only default is still reachable with
`--no-compare-run-extras` (strips the companions) or by passing
`--output text` explicitly. Any explicit `--output …` value overrides
the default entirely.

When `--output <fmt>` is in effect (either by default or explicit), the
orchestrator emits the compare report **plus five companion files** in
`exports/session-metrics/`:

| File | What it is |
|------|------------|
| `session_<a8>_<ts>_dashboard.html` + `session_<a8>_<ts>_detail.html` | Per-session HTML dashboard + detail for side A (standard 2-page split) |
| `session_<a8>_<ts>.json` | Side A full structured report (same schema as the default single-session JSON) |
| `session_<b8>_<ts>_dashboard.html` + `session_<b8>_<ts>_detail.html` + `session_<b8>_<ts>.json` | Same trio for side B |
| `compare_<a8>_vs_<b8>_<ts>_analysis.md` | Markdown analysis scaffold with headline ratios, per-prompt table, cost decomposition, advisories list, and a bolded decision-framework verdict row |

All six companions share a single run timestamp `<ts>` so relative
links inside the analysis scaffold resolve cleanly.

The analysis scaffold carries `{{TODO}}` placeholders in the prose
sections (title hook, TL;DR, interpretation of extended thinking,
should-I-switch workload note) — the deterministic ~80% of the write-up
lands auto-filled, and a follow-up chat (or manual edit) fills the
prose.

**Opt out** with `--no-compare-run-extras` when you want only the
compare report (the pre-1.7.0 behaviour). Without any `--output` flag,
no files are written to disk (text-to-stdout path preserved); the
extras are a **superset** of the compare HTML/MD/JSON emission, never
an addition to the stdout-only path.

The analysis scaffold's decision-framework row is driven by the same
cost-ratio / IFEval-delta thresholds in the *Decision framework*
section below — any threshold bump needs to land in both places.

### When to use Workflow B (manual) instead

Fall back to the manual protocol below when any of these apply:

- You don't have `claude` on PATH (e.g. CI container without the CLI installed).
- Your plan exposes `/model` differently in interactive vs headless and
  the automated run can't reach one of the models.
- You want a human in the loop for each prompt (e.g. debugging why
  one side's tool-heavy prompt behaves oddly before committing to a
  full 20-call run).

---

## Workflow B — Manual controlled capture (fallback)

Five ordered steps. Runs entirely against local JSONL files — no
`ANTHROPIC_API_KEY` involved at any point.

### Prerequisites

- **A Claude subscription plan** (Pro / Max / Team / Enterprise). The
  skill reads whatever Claude Code writes to `~/.claude/projects/…` —
  auth is whatever Claude Code is already using.
- **Access to both models via `/model`.** Open any existing Claude
  Code session and type `/model`; the popup lists the models your
  account can switch to. If `claude-opus-4-6` or `claude-opus-4-7` is
  not listed, stop here — your plan tier does not expose the pair you
  want to compare, and the rest of this workflow cannot proceed.
- **The `session-metrics` skill installed** (plugin marketplace or
  direct copy — see the repo README).

### Step 1 — Create an empty scratch directory

A throwaway project dir isolates the capture from any `CLAUDE.md`,
memory files, or prior session state in your real projects. Without
this, side A and side B warm different caches and the ratios no
longer attribute cleanly to the model.

```bash
mkdir -p /tmp/compare-4-6-vs-4-7
cd /tmp/compare-4-6-vs-4-7
```

**Every subsequent step runs from this directory.** Step 5's
`last-opus-4-6` / `last-opus-4-7` magic tokens resolve only against
the current working directory's project slug — launching the final
compare from a different shell dir will find no sessions.

### Step 2 — Print the 10-prompt suite

In the scratch dir, start a Claude Code session:

```bash
claude
```

Invoke the prep command (skill dispatch; `$ARGUMENTS[0]` = `compare-prep`):

```
/session-metrics compare-prep
```

The skill prints the capture protocol followed by all 10 prompts to
stdout. Copy the prompts somewhere you can paste from twice — a
second terminal tab, an editor buffer, or:

```
/session-metrics compare-prep > /tmp/compare-prompts.md
```

Each prompt body begins with a sentinel like
`[session-metrics:compare-suite:v2:prompt=claudemd_summarise]`. **Do
not strip it** when pasting — the compare report uses the sentinel to
pair A-side and B-side turns back to their source prompt and to run
the IFEval predicate.

Default pair is `claude-opus-4-6` vs `claude-opus-4-7`. To prep for a
different pair, pass two positional model IDs:

```
/session-metrics compare-prep claude-opus-4-7 claude-opus-4-8
```

Exit this prep session with `/exit` before Step 3.

### Step 3 — Capture side A (Opus 4.6)

Still in the scratch dir, start a **fresh** Claude Code session:

```bash
claude
```

Switch to the baseline model and verify the switch took effect:

```
/model claude-opus-4-6
/model
```

The second `/model` call (no argument) echoes the currently-active
model. Confirm it reads `claude-opus-4-6` before pasting any prompts
— otherwise the capture is invalid.

Paste the 10 prompts **one at a time, in order**. Wait for each
reply to fully finish (no streaming cursor) before pasting the next.
Pasting two at once interleaves tool calls and breaks the per-turn
pairing.

When all 10 prompts have completed, exit:

```
/exit
```

Claude Code writes the session JSONL to
`~/.claude/projects/-tmp-compare-4-6-vs-4-7/<uuid>.jsonl`.

### Step 4 — Capture side B (Opus 4.7)

Repeat Step 3 in a **new** fresh Claude Code session from the same
scratch dir:

```bash
claude
```

```
/model claude-opus-4-7
/model
```

Paste the **same 10 prompts in the same order**. Wait for each,
then `/exit`.

### Step 5 — Generate the compare report

Still in the scratch dir:

```
/session-metrics compare last-opus-4-6 last-opus-4-7 --output html
```

(Or from any shell, bypassing the skill dispatch:
`uv run python <skill-dir>/scripts/session-metrics.py --compare last-opus-4-6 last-opus-4-7 --output html`.)

`last-opus-4-6` resolves to the most recent qualifying
single-session JSONL for the `opus-4-6` family **in the current
project slug**; same for `last-opus-4-7`. Because you captured both
sides from `/tmp/compare-4-6-vs-4-7`, both tokens resolve to the
sessions you just recorded.

If auto-resolution returns nothing (usually because a session was
shorter than the 5-user-turn minimum), pass explicit JSONL paths:

```
/session-metrics compare \
  ~/.claude/projects/-tmp-compare-4-6-vs-4-7/<uuid-a>.jsonl \
  ~/.claude/projects/-tmp-compare-4-6-vs-4-7/<uuid-b>.jsonl \
  --output html
```

Or loosen the filter with `--compare-min-turns 1`.

Output-format options: `--output text` (stdout, default), `md`,
`json`, `csv`, `html`. HTML is the richest and is self-contained
(one file, shareable).

### What the output shows

- **Summary strip** — input / output / total / cost ratios (B ÷ A), IFEval pass rate per side, pass-rate delta in percentage points, plus paired-samples statistics (McNemar mid-p, Wilson 95% CIs, low-sample-size banner when N < 20). See [*Statistical interpretation*](#statistical-interpretation-ifeval-pass-rate-delta) below.
- **Per-turn table** — one row per paired turn with A and B tokens, ratios, a `prompt` column naming the suite prompt, and `A✓` / `B✓` columns showing IFEval pass/fail.
- **Advisories banner** — flags `context-tier-mismatch` (e.g. one side on 1M-context tier), `cache-share-drift` (sides differ by >10 pp in cache-read share), `suite-version-mismatch`, empty-side. **Read any advisory before trusting the headline ratio.**

### Interpretation

- **Cost ratio ≫ 1.0 with identical pricing** → tokenizer- or output-length-driven. Pricing is identical between `claude-opus-4-6` and `claude-opus-4-7` at the time of writing, so the full cost delta is tokenizer (see [`pricing.md`](pricing.md)).
- **IFEval pass rate up + cost up** → classic quality/cost trade-off. Read the two together; the [Should I switch?](#should-i-switch-decision-framework) table below codifies the decision.
- **Near-1.0× on CJK prose, large ratio on code / CLAUDE.md** → expected; Claude 4.7's tokenizer compresses code/prose differently than CJK.

---

## Workflow B — Observational drift summary

Use when you already have a pile of historical sessions and want a spend summary across models, even though the prompts differ.

```bash
session-metrics --compare all-opus-4-6 all-opus-4-7 --yes
```

- `--yes` skips the confirmation gate (the CLI otherwise asks before rolling up N sessions per side).
- Output has no per-turn table and no IFEval column (predicates can't pair to unknown prompts). It has aggregate ratios, per-side averages (avg input per prompt, avg output per turn, tool-calls per turn), and cache-read share.
- The banner tells you this is a drift summary, not a benchmark.

---

## Workflow C — Inference-free tokenizer check (`--count-tokens-only`)

The fastest "am I affected?" check. Hits `POST /v1/messages/count_tokens` once per prompt × model — no inference runs, no output/cost data, just the input-token delta the article is about.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
session-metrics --count-tokens-only --yes     # defaults: opus-4-6 vs opus-4-7
session-metrics --count-tokens-only \
    --compare-models claude-sonnet-4-6 claude-sonnet-4-7 --yes
```

- **Input only.** Output length and total cost are NOT measured — those columns don't exist in this mode. For a full comparison run Workflow A against two real sessions.
- **Confirmation gate.** Prints the total API-call count (`N prompts × 2 models`) and waits for `y`. Bypass with `--yes`. Non-TTY stdin without `--yes` is a hard refusal to avoid surprise rate-limit burn in scripts.
- **Probe fallback.** On startup, calls the first model with the first prompt as a probe. If that call fails (e.g. the API key no longer has access to the baseline model), the mode collapses to counting the second model only and prints a friendly explanation. Ratios are not computable from that collapsed state — the run still gives you absolute input-token counts, which is useful for "how many tokens does my prompt suite consume on model X" questions.
- **Rate limits.** count_tokens requests don't incur per-token charges but they do count against the account's request rate limit. A 10-prompt × 2-model suite is 20 calls — negligible on any real account.
- **Custom suite directory.** Pairs with `--compare-prompts DIR` to point at an alternative prompt set (same YAML-frontmatter-plus-body format as the packaged suite; predicates are ignored in this mode since no inference runs).

---

## Prompt suite (v1)

Located at `.claude/skills/session-metrics/references/model-compare/prompts/`. Each file is a Markdown document with YAML frontmatter, a prompt body, and an optional Python predicate.

Every prompt body starts with a sentinel:

```
[session-metrics:compare-suite:v2:prompt=<name>]
```

The skill detects this sentinel in user prompts to (a) identify which suite prompt a turn corresponds to, (b) run the IFEval predicate against the assistant's text output, and (c) refuse when the two compared sessions carry different suite versions.

Suite **v2** (2026-06) rewrote `tool_heavy_task` to read three frozen
fixture files that `--compare-run` stages into the scratch directory
(`references/model-compare/fixtures/`), replacing v1's repo-relative
paths that never resolved in the scratch cwd. v1 therefore measured
failed-Read *recovery* behaviour on that prompt (and could wedge
high-effort models in filesystem-wide `find` escalations); v2 measures
clean three-Read fan-out. The two versions' `tool_heavy_task` numbers
are not comparable — which is exactly what the version checker guards.

| # | Name | Content shape | Predicate |
|--:|------|---------------|-----------|
| 1 | `claudemd_summarise` | prose-dense CLAUDE.md | exactly 120 words |
| 2 | `english_prose` | English prose | zero commas |
| 3 | `code_review` | Python diff | exactly 3 bullet items |
| 4 | `stack_trace_debug` | Python stack trace | ≤ ~200 output tokens |
| 5 | `tool_heavy_task` | agentic tool-use | *(none — ratio only)* |
| 6 | `cjk_prose` | Japanese prose | no CJK codepoints remaining |
| 7 | `json_reshape` | structured JSON | valid JSON with required shape |
| 8 | `csv_transform` | structured CSV | valid CSV, no prose preamble |
| 9 | `typescript_refactor` | TypeScript code | word "refactor" appears exactly twice |
| 10 | `instruction_stress` | stacked constraints | 50 words, no commas, "foo" ×2, lowercase |

To add, remove, or preview custom prompts, see
[`references/custom-prompts.md`](custom-prompts.md) for the step-by-step guide
(beginner-friendly; no YAML or predicates required for the common case).

---

## Methodology caveats

- **Single-run variance.** Each prompt runs once per side. One-offs can swing ±10% on tokenizer ratios. The article this feature is based on acknowledges the same limitation. Multi-trial support (`--compare-trials N`) is on the roadmap but not in this release.
- **Cache warmth.** Running B immediately after A means B's CLAUDE.md cache is in a different state than A's was on first turn. The skill emits a `cache-share-drift` advisory when the two sides' cache-read share differs by >10 pp. When you see it, read the cache column with skepticism.
- **Context-tier confound.** Claude Code's default Opus 4.7 arrives tagged `claude-opus-4-7[1m]` (1M-context tier). If side A is on the default tier and side B is `[1m]`, the `context-tier-mismatch` advisory fires — the ratio then conflates tokenizer + window tier + cache-hit-rate. Run both sides on the same tier when practical.
- **System-prompt drift.** Claude Code's system prompt evolves over time. Compares across months can drift for that reason alone; Mode 2 is especially exposed. Protocol encourages same-day capture.
- **Prompt-suite representativeness.** The canonical 10 prompts cover the content shapes the referenced article measured. Your workload may be skewed. Add your own prompts and re-run.

---

## Statistical interpretation (IFEval pass-rate delta)

**Design.** The two runs feed the same prompts to both models, and
`--pair-by fingerprint` (default) matches turns by the hash of the first
500 chars of the user prompt. **Same prompt, two outputs → paired
samples.** The correct statistical test for paired binary outcomes is
**McNemar's test**, not a two-proportion z-test. A naive "A 70%, B 80%,
Δ+10pp" comparison ignores the pairing and overstates the evidence for
a real difference.

**What the report emits** (v1.13.0+, alongside the existing
`pass_delta_pp` field):

| Field | Meaning |
|-------|---------|
| `instruction_mcnemar_b` | Count of discordant pairs where A passes and B fails. |
| `instruction_mcnemar_c` | Count of discordant pairs where A fails and B passes. |
| `instruction_mcnemar_pvalue` | Two-sided **mid-p** McNemar test p-value on `(b, c)`. `None` when `b + c == 0`. Mid-p is less conservative than the exact binomial tail at small N, which matters on a 10-prompt suite. |
| `instruction_pass_rate_a_ci` | 95% **Wilson score** CI on A's marginal pass rate, `(lo, hi)` both in [0, 1]. `None` when N is 0. |
| `instruction_pass_rate_b_ci` | Same for B. |
| `low_sample_size` | `True` when N < 20. |
| `sample_size_note` | Human-readable reminder surfaced as a banner in text/MD/HTML. |

**How to read them.** McNemar only counts discordant pairs — concordant
pairs (both pass, both fail) carry no information about the delta. If
`b = 2, c = 3`, the null says these flips are coin flips; with only 5
discordant trials there isn't enough evidence to reject it, and
`p ≈ 0.7`. The "+10 pp" reads as a real gap at first glance but doesn't
survive a paired test.

Wilson CIs matter most at boundary proportions (0/10 or 10/10) — the
naive Wald interval would give a zero-width band there, which is
obviously wrong. Wilson stays inside [0, 1] at both extremes and has
better coverage at small N generally.

**Rule of thumb.**

- `N ≥ 20` and `mcnemar_pvalue < 0.05` → real effect worth quoting.
- `N < 20` → treat pass-rate deltas as **directional**, not conclusive.
  Report the banner. The skill surfaces this automatically.
- `mcnemar_b + mcnemar_c == 0` → models agree on every prompt; the
  raw delta is exactly 0 and there is nothing to test. `pvalue` is
  reported as `None`.

**Why not a two-proportion z-test?** It would treat A's 10 trials and
B's 10 trials as independent samples, which they aren't (each prompt
appears in both). The paired design gives strictly more power for the
same N when the models' outcomes are correlated (which they typically
are on the canonical suite), so using the unpaired test is
statistically sloppy in both directions — sometimes it inflates
evidence, sometimes it masks a real shift.

**Small-N warning threshold.** The default is N < 20 because, with a
10-prompt suite, a single-prompt flip moves the raw pass rate by 10 pp
— roughly the same magnitude as the headline effect the tool is trying
to measure. Below 20 the noise floor and the signal ceiling are
indistinguishable without a significance test. The threshold is a
heuristic, not a hard rule.

---

## "Should I switch?" decision framework

| Cost ratio | IFEval Δ | Recommendation |
|------------|----------|----------------|
| ≤ 1.05× | any | Switch. Minimal cost impact. |
| 1.05–1.20× | +5 pp or more | Switch if quality matters. |
| 1.05–1.20× | ±2 pp | Suite-agnostic — depends on workload. Test with your own content. |
| 1.20–1.45× | +10 pp or more | Trade-off call. Model your spend at the new ratio. |
| ≥ 1.45× | any | Stay, or use the newer model selectively (e.g. code review only). |

IFEval Δ is side B minus side A in percentage points.

---

## Reference ratios (observed)

| Pair | Suite | Avg cost ratio | IFEval Δ | Source |
|------|-------|----------------|----------|--------|
| `claude-opus-4-6` → `claude-opus-4-7` | v1 | 1.21–1.45× *(content-shape-dependent)* | ≈ +5 pp | [Tokenizer article][article-url] |

When you run the suite on a new pair, you can PR your observed ratio into this table — it grows into a community registry.

[article-url]: https://www.claudecodecamp.com/p/i-measured-claude-4-7-s-new-tokenizer-here-s-what-it-costs-you

---

## Troubleshooting

- **"compare-suite versions differ"** — you ran the suite at v1 on one side and v2 on the other. Re-run both sides with the same suite, or pass `--allow-suite-mismatch` to proceed (ratios will be misleading).
- **"aggregate compare requires --yes when stdin is not a TTY"** — Mode 2 guards against accidental large rollups in scripts. Add `--yes` or run interactively.
- **Predicate says ✗ but the text looks right** — check the predicate in the prompt file. Predicates are strict by design (IFEval-style); near-misses still fail.
- **`last-opus-4-7` resolves to nothing** — the default threshold is 5 user turns. Short or crashed sessions are filtered out. Override with `--compare-min-turns 1`.
- **`--count-tokens-only requires ANTHROPIC_API_KEY`** — set the env var and re-run. The endpoint is lightweight (no inference) but still requires authentication.
- **`probe failed: HTTP 403` in count-tokens mode** — the first model is not accessible to the API key. The mode auto-falls-back to counting the second model only and tells you in stderr. Use Workflow A (sessions) if you need a true A-vs-B comparison.
