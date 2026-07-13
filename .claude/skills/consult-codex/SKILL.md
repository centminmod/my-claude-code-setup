---
name: consult-codex
description: Dual-AI code analysis pairing OpenAI Codex GPT-5.6-terra with Claude code-searcher — the lightest consult variant, two citation-verified perspectives. Use for a quick second opinion on a code question.
---

# Dual-AI Consultation: Codex GPT-5.6-terra vs Code-Searcher

You orchestrate consultation between OpenAI's Codex GPT-5.6-terra and Claude's code-searcher to provide comprehensive analysis with comparison.

## When to Use This Skill

**High value queries:**
- Complex code analysis requiring multiple perspectives
- Debugging difficult issues
- Architecture/design questions
- Code review requests
- Finding specific implementations across a codebase

**Lower value (single AI may suffice):**
- Simple syntax questions
- Basic file lookups
- Straightforward documentation queries

## Workflow

When the user asks a code question:

### 1. Build Enhanced Prompt

**Problem-restate pre-flight (non-blocking).** Before building the prompt, emit ONE line
restating the code question you are about to dispatch (and, only if genuinely ambiguous, the
alternative reading), then proceed:

> *Reading this as: «one-line restatement» (alt: «other reading», if any) — proceeding to consult; interrupt now to correct the framing.*

Emit-and-proceed — do not ask-and-wait (the orchestrator can't reliably detect its own
misframing). One line, and it guards the whole dispatch against a wrong-framing run.


Wrap the user's question with structured output requirements:

````
[USER_QUESTION]

=== Analysis Guidelines ===

**Structure your response with:**
1. **Summary:** 2-3 sentence overview
2. **Key Findings:** bullet points of discoveries
3. **Evidence:** file paths with line numbers (format: `file:line` or `file:start-end`)
4. **Confidence:** High/Medium/Low with reasoning
5. **Limitations:** what couldn't be determined

**Line Number Requirements:**
- ALWAYS include specific line numbers when referencing code
- Use format: `path/to/file.ext:42` or `path/to/file.ext:42-58`
- For multiple references: list each on a SEPARATE line with its own file path
  (avoid comma-separated multi-citation like `file.ts:45, 67, 98`)
- Include brief code snippets for key findings

**Examples of good citations:**
- "The authentication check at `src/auth/validate.ts:127-134`"
- "Configuration loaded from `config/settings.json:15`"
- "Error handling in `lib/errors.ts:45`, `lib/errors.ts:67-72`, and `lib/errors.ts:98`"

**Citations Index (required):** end your response with a fenced block, one line per
Key Finding (repeat each block entry's `file:line` inline in the finding as usual):
```citations
<finding #> — path/to/file.ext:LINE[-END]
```
````

**Severity / no-manufacture block — ORCHESTRATOR-GATED.** Append the block below to both
agents' prompts **identically** ONLY when the query is a defect hunt / code review (bug,
security audit, "what's wrong with…", "review this"). OMIT it for explanatory / "how does
X work" questions, where "found nothing" is not meaningful. The orchestrator — which knows
the query type — makes this include/omit decision once, BEFORE writing the prompt files;
do not leave it to each agent to self-classify. When included, append exactly these two
bullets (the text only — no leading marker):

    - Tag each finding with a **Severity** — Critical (wrong/broken on expected inputs) · Warning (fails on unusual but valid inputs) · Info (noteworthy, not actionable). Severity is *impact*, orthogonal to the Confidence field (*certainty*).
    - **Finding nothing is a valid, valuable result.** If the code is correct, say so plainly with one verifying note — do NOT manufacture issues to look thorough.

### 2. Invoke Both Analyses in Parallel

**Setup (run first).** `$CLAUDE_PROJECT_DIR` is not always exported into the Bash
tool shell, so resolve it with a `$PWD` fallback and ensure the tmp dir exists.
Substitute the resolved literal path for `$PROJECT_DIR`, and a freshly generated
`RUN_ID` (seconds-resolution + 4-char nonce, e.g. `run-2026-05-25-143052-a7f3`),
into every command below. The `RUN_ID` in temp filenames prevents collisions
between two concurrent invocations sharing `$PROJECT_DIR/tmp`.
```bash
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
# Validate BEFORE creating tmp — `mkdir -p` would otherwise make the check pass even
# for a bad path (it creates the dir, then `[ -d ]` always succeeds).
[ -d "$PROJECT_DIR" ] || { echo "ERROR: PROJECT_DIR '$PROJECT_DIR' is not a directory" >&2; exit 1; }
mkdir -p "$PROJECT_DIR/tmp"

# Pre-flight (fail fast, not after a 10-min hang). jq is a HARD dependency — output
# parsing needs it — so abort now rather than warn-and-continue into opaque failures.
command -v jq >/dev/null 2>&1 || { echo "ERROR: 'jq' not found — required for output parsing; aborting" >&2; exit 1; }
# codex is a soft dependency — the CODEX_BIN resilience block below resolves or SKIPs it.
command -v codex >/dev/null 2>&1 || \
  zsh  -i -c "type codex" >/dev/null 2>&1 || \
  bash -i -c "type codex" >/dev/null 2>&1 || \
  echo "WARNING: 'codex' not found — will attempt nvm resolution below, else SKIP"

# Sweep stale orphans (>60 min) from crashed prior runs (best-effort, age-based —
# can theoretically delete a live run's files if it paused >60 min; acceptable).
find "$PROJECT_DIR/tmp" -maxdepth 1 -name '*-prompt-*.txt'   -mmin +60 -delete 2>/dev/null
find "$PROJECT_DIR/tmp" -maxdepth 1 -name '*-output-*.jsonl' -mmin +60 -delete 2>/dev/null
```

**Codex binary resilience (run once, before dispatch).** An nvm-managed `codex`
can be a symlink whose `@openai/codex` install is broken (deleted vendor binary →
`spawn ... ENOENT`), and a broken version can sit EARLIER on `PATH` than a working
one. `command -v` / `zsh -i` return the broken path, so detect by RUNNING the
binary. If the PATH-resolved codex fails, hunt all nvm node installs for one whose
`--version` succeeds and emit its absolute path. Emit `CODEX_BIN=SKIP` if none work.
```bash
CODEX_BIN=""; INTERACTIVE_SHELL=zsh
# Capture WHICH interactive shell resolves codex (nvm may be in only one of
# ~/.zshrc / ~/.bashrc). The dispatch below uses $INTERACTIVE_SHELL so a
# .bashrc-only setup on macOS still works (prior bug: probe accepted bash,
# dispatch hardcoded zsh).
if   zsh  -i -c 'codex --version' >/dev/null 2>&1; then CODEX_BIN="codex"; INTERACTIVE_SHELL=zsh   # codex resolves via zsh
elif bash -i -c 'codex --version' >/dev/null 2>&1; then CODEX_BIN="codex"; INTERACTIVE_SHELL=bash  # codex resolves via bash
else
  # Match symlinks too (-type l): nvm/npm install codex as a bin/ symlink, which -type f misses.
  CODEX_BIN=$(find "$HOME/.nvm/versions/node" -maxdepth 5 -name codex \( -type f -o -type l \) 2>/dev/null | while IFS= read -r p; do
    "$p" --version >/dev/null 2>&1 && { printf '%s\n' "$p"; break; }
  done)
  [ -z "$CODEX_BIN" ] && CODEX_BIN="SKIP"
fi
echo "CODEX_BIN=$CODEX_BIN"                   # MUST echo: shell vars don't persist across Bash tool calls
echo "INTERACTIVE_SHELL=$INTERACTIVE_SHELL"   # the interactive shell that resolves codex; substitute into the dispatch below

# Resolve the timeout binary used to wrap the Codex gen dispatch (§Step 2 below) so a
# hung CLI is bounded rather than running unbounded — the harness may auto-background
# the dispatch, letting it escape the Bash tool's own timeout. Probe BOTH names:
# Homebrew coreutils installs GNU timeout as `gtimeout`; plain `timeout` exists only
# when the coreutils gnubin PATH is on. If neither exists, TIMEOUT_CMD stays empty and
# the dispatch runs UNWRAPPED (best-effort Bash-tool timeout; `brew install coreutils`
# restores the hard guard).
TIMEOUT_CMD=""
if   command -v timeout  >/dev/null 2>&1; then TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT_CMD="gtimeout"
fi
echo "TIMEOUT_CMD=$TIMEOUT_CMD"   # substitute into the §Step-2 Codex dispatch (when empty: omit the wrap)
```

**Two-phase dispatch (required).** Tool calls in one message run concurrently, so emitting the Codex prompt-file Write and the Codex dispatch together races the dispatch ahead of the file (Codex errors on a missing prompt file). Use **two messages**: message 1 writes the Codex prompt file (Step 1 below); message 2 issues the Codex dispatch (Step 2) and the Code-Searcher Agent call in parallel:

**Gen-dispatch timeout watchdog (`GEN_TIMEOUT=1200`).** Each `$TIMEOUT_CMD -k 10 1200`-prefixed CLI gen below — SIGTERM at 1200s (20 min), SIGKILL 10s later (`-k 10`, which also reaps orphaned Node/MCP children) — is bounded against a hung provider CLI that would otherwise run unbounded (the harness may auto-background the dispatch, so the Bash tool's own timeout is **not** a reliable cap). **When `TIMEOUT_CMD` is empty** (no `timeout`/`gtimeout`): omit the `$TIMEOUT_CMD -k 10 1200` prefix and dispatch unwrapped (the existing §Setup fallback) — set the Bash tool's own `timeout` parameter to `1300000` ms as a best-effort cap, and `brew install coreutils` to restore the hard guard. **On a timed-out gen** (exit **124** = SIGTERM, **137** = SIGKILL): the output file is empty/truncated, so the existing `[ -z … ]` parse guard already drops the agent — additionally surface `Agent X timed out after 1200s` (distinct from an auth failure, which leaves non-empty stderr) and re-count against the §Setup minimum-agent guard. Do **not** retry. Code-Searcher (Agent tool) carries **no** `$TIMEOUT_CMD -k 10 1200` prefix — it is bounded by its own mechanism, not this watchdog.

- **For Codex GPT-5.6-terra:**

  **Step 1:** Write the enhanced prompt to a temp file using the Write tool:
  ```
  Write to $PROJECT_DIR/tmp/codex-prompt-RUN_ID.txt with the ENHANCED_PROMPT content
  ```

  **Step 2:** Execute Codex (allow ~10 min; Codex can be slow). Pipe the prompt
  via stdin and capture the JSONL event stream to a file.

  **Pick the form based on `CODEX_BIN` from Setup:**
  - `CODEX_BIN=codex` → use the **interactive-shell** form below (`$INTERACTIVE_SHELL` resolved in Setup).
  - `CODEX_BIN` is an absolute path → use the **absolute-path** form (calls the
    binary directly so PATH ordering can't shadow it again).
  - `CODEX_BIN=SKIP` → no working codex; skip this dispatch, present only the
    Code-Searcher response. **Label the report a degraded single-AI run** — Code-Searcher is
    the sole agent, so there is no cross-comparison — and note that a direct Read or a lighter
    path would have been cheaper. Record the skip in §4 (error handling) / §5 (comparison report).

  **macOS/Linux (`CODEX_BIN=codex`; `$INTERACTIVE_SHELL` = the `zsh`|`bash` literal resolved in Setup):**
  ```bash
  cat "$PROJECT_DIR/tmp/codex-prompt-RUN_ID.txt" \
    | $TIMEOUT_CMD -k 10 1200 $INTERACTIVE_SHELL -i -c "codex exec -s read-only --json -C '$PROJECT_DIR' 2>&1" \
    > "$PROJECT_DIR/tmp/codex-output-RUN_ID.jsonl"
  ```

  **Absolute-path (`CODEX_BIN` resolved to a path — macOS & Linux):** substitute
  the literal absolute path for `CODEX_BIN_LITERAL`; no shell wrapper needed.
  ```bash
  cat "$PROJECT_DIR/tmp/codex-prompt-RUN_ID.txt" \
    | $TIMEOUT_CMD -k 10 1200 CODEX_BIN_LITERAL exec -s read-only --json -C "$PROJECT_DIR" \
    > "$PROJECT_DIR/tmp/codex-output-RUN_ID.jsonl" 2>&1
  ```

  Why this exact form (each piece prevents a failure seen in practice):
  - **`-s read-only`** is the portable Codex sandbox flag — it needs no
    `~/.codex/config.toml` `[profiles.readonly]` entry, unlike `-p readonly`
    (which silently misbehaves when that profile is absent).
  - **stdin pipe** (`cat … | …`) instead of `"$(cat …)"` avoids the
    `Reading additional input from stdin...` hang (Codex waits on stdin when the
    prompt is passed as a positional) and ARG_MAX limits on large prompts.
  - **`-C '$PROJECT_DIR'`** — outer-shell single-quote expansion of an absolute
    path — gives Codex project context. Do NOT pass the dir via an inner-shell
    positional (`-C "$0"`/literal placeholders): besides being fragile, a skill
    loaded WITH user arguments has its `$0`/`$1`/`$2` rewritten by Claude Code's
    argument substitution, so a wrong-bound `$0` produces a cryptic
    `Error: No such file or directory (os error 2)`.

  Parse `$PROJECT_DIR/tmp/codex-output-RUN_ID.jsonl` with the §2a recipes.

- **For Code-Searcher:** Use Agent tool with `subagent_type: "code-searcher"` with the same enhanced prompt (plus the orchestrator-gated Severity block above on defect-hunt runs)

This parallel execution significantly improves response time.

### 2a. Parse Codex `--json` Output Files (jq Recipes)

Codex CLI with `--json` typically emits **newline-delimited JSON events** (JSONL). Some environments may prefix lines with terminal escape sequences; these recipes strip everything before the first `{` and then `fromjson?` safely.

Set a variable first:

```bash
FILE="$PROJECT_DIR/tmp/codex-output-RUN_ID.jsonl"   # the file the §2 dispatch redirected to
```

**List event types (top-level `.type`)**

```bash
jq -Rr 'sub("^[^{]*";"") | fromjson? | .type // empty' "$FILE" | sort | uniq -c | sort -nr
```

**List item types (nested `.item.type` on `item.completed`)**

```bash
jq -Rr 'sub("^[^{]*";"") | fromjson? | select(.type=="item.completed") | .item.type? // empty' "$FILE" | sort | uniq -c | sort -nr
```

**Extract only “reasoning” and “agent_message” text (human-readable)**

```bash
jq -Rr '
  sub("^[^{]*";"")
  | fromjson?
  | select(.type=="item.completed" and (.item.type? | IN("reasoning","agent_message")))
  | "===== \(.item.type) \(.item.id) =====\n\(.item.text // "")\n"
' "$FILE"
```

**Extract ALL `agent_message` events** (Codex frequently emits multiple; extracting only the last would truncate the answer)

```bash
out=$(jq -Rr '
  sub("^[^{]*";"")
  | fromjson?
  | select(.type=="item.completed" and .item.type?=="agent_message")
  | .item.text // empty
' "$FILE")
[ -z "$out" ] && echo "ERROR: Codex produced no agent_message events — check the raw output for errors" >&2
printf '%s\n' "$out"
```

**Build a clean JSON array for downstream tools**

```bash
jq -Rn '
  [inputs
   | sub("^[^{]*";"")
   | fromjson?
   | select(.type=="item.completed" and (.item.type? | IN("reasoning","agent_message")))
   | {type:.item.type, id:.item.id, text:(.item.text // "")}
  ]
' "$FILE"
```

**Extract command executions (command + exit code), avoiding huge stdout/stderr**

Codex JSON schemas vary slightly; this tries multiple common field names.

```bash
jq -Rr '
  sub("^[^{]*";"")
  | fromjson?
  | select(.type=="item.completed" and .item.type?=="command_execution")
  | [
      (.item.id // ""),
      (.item.command // .item.cmd // .item.command_line // "<no command field>"),
      (.item.exit_code // .item.exitCode // "<no exit>")
    ]
  | @tsv
' "$FILE"
```

**Discover actual fields present in `command_execution` for your environment**

```bash
jq -Rr '
  sub("^[^{]*";"")
  | fromjson?
  | select(.type=="item.completed" and .item.type?=="command_execution")
  | (.item | keys | @json)
' "$FILE" | head -n 5
```

### 3. Cleanup Temp Files

After processing the Codex response (success or failure), clean up the temp files:

```bash
rm -f "$PROJECT_DIR/tmp/codex-prompt-RUN_ID.txt" "$PROJECT_DIR/tmp/codex-output-RUN_ID.jsonl"
```

This prevents stale prompts from accumulating and avoids potential confusion in future runs.

### 4. Handle Errors

- If one agent fails or times out, still present the successful agent's response
- Note the failure in the comparison: "Agent X failed to respond: [error message]"
- Provide analysis based on the available response

### 5. Create Comparison Analysis

Use this exact format:

---

## Codex (GPT-5.6-terra) Response

[Raw output from codex-cli agent]

---

## Code-Searcher (Claude) Response

[Raw output from code-searcher agent]

---

## Comparison Table

(MANDATORY — always render this table on a multi-agent run; it is the at-a-glance visual diff readers rely on, so never skip it. Omit only in a degraded single-AI run, where there is nothing to compare.)

| Aspect | Codex (GPT-5.6-terra) | Code-Searcher (Claude) |
|--------|-----------------|------------------------|
| File paths | [Specific/Generic/None] | [Specific/Generic/None] |
| Line numbers | [Provided/Missing] | [Provided/Missing] |
| Code snippets | [Yes/No + details] | [Yes/No + details] |
| Unique findings | [List any] | [List any] |
| Accuracy | [Note discrepancies] | [Note discrepancies] |
| Strengths | [Summary] | [Summary] |

## Agreement Level

- **High Agreement:** Both AIs reached similar conclusions - Higher confidence in findings
- **Partial Agreement:** Some overlap with unique findings - Investigate differences
- **Disagreement:** Contradicting findings - Manual verification recommended

[State which level applies and explain]

## Findings by Corroboration

Bucket each *distinct* finding by how many agents independently reached it:

- **Corroborated** — both agents report it. Highest trust *as a consensus signal* — this
  dual has no citation-verification stage, so it is agreement, not verified correctness.
- **Solo** — reported by one agent only. Plausible but unconfirmed.
- **Disputed** — the agents contradict on the point. Flag for manual verification.

(Cluster findings across agents by their claim + `file:line` — the Citations Index blocks
make this pairing mechanical. On a defect-hunt run, tag each listed finding with its
agent-assigned Severity — Critical/Warning/Info.)

## Key Differences

- **Codex GPT-5.6-terra:** [unique findings, strengths, approach]
- **Code-Searcher:** [unique findings, strengths, approach]

## Synthesized Summary

[Combine the best insights from both sources into unified analysis. Prioritize findings that are:
1. Corroborated by both agents
2. Supported by specific file:line citations
3. Include verifiable code snippets]

## Recommendation

[Which source was more helpful for this specific query and why. Consider:
- Accuracy of file paths and line numbers
- Quality of code snippets provided
- Completeness of analysis
- Unique insights offered]
