---
name: consult-zai
description: Dual-AI code analysis pairing z.ai GLM 5.2 with Claude code-searcher — a lightweight two-model second opinion. Use for a quick z.ai-backed check on a code question.
---

# Dual-AI Consultation: z.ai GLM 5.2 vs Code-Searcher

You orchestrate consultation between z.ai's GLM 5.2 model and Claude's code-searcher to provide comprehensive analysis with comparison.

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

**Setup (run first).** `$CLAUDE_PROJECT_DIR` is not always exported into the Bash tool
shell, so resolve it with a `$PWD` fallback and ensure the tmp dir exists. Substitute the
resolved literal path for `$PROJECT_DIR`, and a freshly generated `RUN_ID`
(seconds-resolution + 4-char nonce, e.g. `run-2026-07-04-143052-a7f3`), into every command
below. The `RUN_ID` in temp filenames prevents collisions between two concurrent
invocations sharing `$PROJECT_DIR/tmp`.
```bash
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
# Validate BEFORE creating tmp — `mkdir -p` would otherwise make the check pass even
# for a bad path (it creates the dir, then `[ -d ]` always succeeds).
[ -d "$PROJECT_DIR" ] || { echo "ERROR: PROJECT_DIR '$PROJECT_DIR' is not a directory" >&2; exit 1; }
mkdir -p "$PROJECT_DIR/tmp"

# Pre-flight (fail fast, not after a 20-min hang). jq is a HARD dependency — the §2a
# parse recipe needs it — so abort now rather than warn-and-continue into opaque failures.
command -v jq >/dev/null 2>&1 || { echo "ERROR: 'jq' not found — required for output parsing; aborting" >&2; exit 1; }
# zai is a soft dependency (a shell function wrapping the claude CLI against z.ai's
# endpoint, loaded from ~/.zshrc or ~/.bashrc — hence the interactive-shell probes).
# Capture WHICH interactive shell resolves it; the dispatch below substitutes
# $INTERACTIVE_SHELL so a .bashrc-only setup on macOS still works. If neither shell
# resolves zai, skip its dispatch and label the run degraded (see §2 dispatch + §4).
ZAI_AVAIL=1; INTERACTIVE_SHELL=zsh
if   zsh  -i -c 'type zai' >/dev/null 2>&1; then ZAI_AVAIL=0; INTERACTIVE_SHELL=zsh
elif bash -i -c 'type zai' >/dev/null 2>&1; then ZAI_AVAIL=0; INTERACTIVE_SHELL=bash
else echo "WARNING: 'zai' not found in zsh or bash interactive shells — z.ai will be skipped"
fi
echo "ZAI_AVAIL=$ZAI_AVAIL"                   # MUST echo: shell vars don't persist across Bash tool calls
echo "INTERACTIVE_SHELL=$INTERACTIVE_SHELL"   # substitute into the Step-2 dispatch below

# Sweep stale orphans (>60 min) from crashed prior runs (best-effort, age-based —
# can theoretically delete a live run's files if it paused >60 min; acceptable).
find "$PROJECT_DIR/tmp" -maxdepth 1 -name 'zai-prompt-*.txt'  -mmin +60 -delete 2>/dev/null
find "$PROJECT_DIR/tmp" -maxdepth 1 -name 'zai-output-*.json' -mmin +60 -delete 2>/dev/null
find "$PROJECT_DIR/tmp" -maxdepth 1 -name 'zai-stderr-*.log'  -mmin +60 -delete 2>/dev/null

# Resolve the timeout binary used to wrap the Step-2 z.ai dispatch so a hung CLI is
# bounded rather than running unbounded — the harness may auto-background the dispatch,
# letting it escape the Bash tool's own timeout. Homebrew coreutils installs GNU
# timeout as `gtimeout`; plain `timeout` exists only when the gnubin PATH is on. If
# neither exists, TIMEOUT_CMD stays empty → dispatch UNWRAPPED (best-effort;
# `brew install coreutils` restores the hard guard).
TIMEOUT_CMD=""
if   command -v timeout  >/dev/null 2>&1; then TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT_CMD="gtimeout"
fi
echo "TIMEOUT_CMD=$TIMEOUT_CMD"   # substitute into the Step-2 dispatch (when empty: omit the wrap)
```

**Two-phase dispatch (required).** Tool calls in one message run concurrently, so emitting
the z.ai prompt-file Write and the z.ai dispatch together races the dispatch ahead of the
file existing (the `cat` pipes an empty/missing file). Use **two messages**: message 1
writes the z.ai prompt file (Step 1 below); message 2 issues the z.ai dispatch (Step 2)
and the Code-Searcher Agent call in parallel.

**Gen-dispatch timeout watchdog (`GEN_TIMEOUT=1200`).** The z.ai dispatch is wrapped in
`$TIMEOUT_CMD -k 10 1200` (resolved in Setup) — SIGTERM at 1200s (20 min), SIGKILL 10s
later (`-k 10`, reaps orphaned Node/MCP children). This bounds a hung z.ai CLI that could
otherwise run unbounded (the harness may auto-background the dispatch, so the Bash tool's
own timeout is **not** a reliable cap). **When `TIMEOUT_CMD` is empty**: omit the
`$TIMEOUT_CMD -k 10 1200` prefix and dispatch unwrapped — set the Bash tool's own
`timeout` parameter to `1300000` ms as a best-effort cap, and `brew install coreutils` to
restore the hard guard. **On a timed-out dispatch** (exit **124** = SIGTERM, **137** =
SIGKILL): the output file is empty/truncated, so the §2a `[ -z … ]` parse guard drops the
agent — treat z.ai as failed per §4 (present Code-Searcher's response and note the
timeout; do NOT retry). Code-Searcher (Agent tool) is not wrapped — it bounds itself.

- **For z.ai GLM 5.2:**

  **Step 1:** Write the enhanced prompt to a temp file using the Write tool:
  ```
  Write to $PROJECT_DIR/tmp/zai-prompt-RUN_ID.txt with the ENHANCED_PROMPT content
  ```

  **Step 2:** Execute z.ai (skip if Setup echoed `ZAI_AVAIL=1` — no working `zai`;
  present only the Code-Searcher response and **label the report a degraded single-AI
  run**: no cross-comparison, and note a direct Read or lighter path would have been
  cheaper). Pipe the prompt via stdin and capture output/stderr to files
  (`$INTERACTIVE_SHELL` = the `zsh`|`bash` literal resolved in Setup):
  ```bash
  cat "$PROJECT_DIR/tmp/zai-prompt-RUN_ID.txt" | \
    $TIMEOUT_CMD -k 10 1200 $INTERACTIVE_SHELL -i -c "zai --bare --print --output-format json --model 'glm-5.2[1m]' --allowedTools 'Read,Grep,Glob' --add-dir '$PROJECT_DIR'" \
    > "$PROJECT_DIR/tmp/zai-output-RUN_ID.json" \
    2> "$PROJECT_DIR/tmp/zai-stderr-RUN_ID.log"
  ```

  Why this exact form (each piece prevents a failure seen in practice):
  - **`--bare` is required** — `zai` exports `ANTHROPIC_AUTH_TOKEN`; without `--bare` the
    parent session's OAuth token shadows it → 401 against the z.ai endpoint.
  - **`--model 'glm-5.2[1m]'` is required** — guarantees GLM 5.2 regardless of which tier
    default resolution would pick (guards against the `glm-5-turbo` subagent default).
  - **Read-only is hard-enforced** via `--allowedTools 'Read,Grep,Glob'` — consultation is
    analysis, not modification; never relax these flags.
  - **stdin pipe** (`cat … | …`) instead of `-p "$(cat …)"` avoids shell-quoting breakage
    and ARG_MAX limits on large prompts.
  - **`--add-dir '$PROJECT_DIR'`** — outer-shell single-quote expansion of the absolute
    path gives z.ai project context; never pass the dir via an inner-shell positional
    (skill argument substitution rewrites positional tokens).
  - stderr captured separately; on a 401/auth failure it carries the diagnostic.

- **For Code-Searcher:** Use Agent tool with `subagent_type: "code-searcher"` with the same enhanced prompt (plus the orchestrator-gated Severity block above on defect-hunt runs)

This parallel execution significantly improves response time.

### 2a. Parse z.ai JSON Output (jq Recipe)

`zai --print --output-format json` emits a JSON array (possibly prefixed with ANSI/OSC
terminal escapes — iTerm2 shell-integration codes); rarely the CLI returns a bare object
instead of an array. Canonical slice, then a bare-object fallback:

```bash
ZAI_FILE="$PROJECT_DIR/tmp/zai-output-RUN_ID.json"
response=$(jq -Rrs '
  (try (match("\\[\\s*\\{[\\s\\S]*\\]").string) catch empty)
  | fromjson?
  | .[]
  | select(.type=="result")
  | .result // empty
' "$ZAI_FILE")
# Fallback (rare — primary slice empty on a NON-empty file): salvage ONLY a genuine
# result/message/assistant shape.
if [ -z "$response" ] && [ -s "$ZAI_FILE" ]; then
  response=$(jq -Rrs '
    (try (match("\\{[\\s\\S]*\\}").string) catch empty)
    | fromjson?
    | if   .type=="result"    then (.result // empty)
      elif .type=="message"   then ((.content[]? | select(.type=="text") | .text) // empty)
      elif .type=="assistant" then ((.message.content[]? | select(.type=="text") | .text) // empty)
      else empty end
  ' "$ZAI_FILE")
fi
[ -z "$response" ] && echo "ERROR: z.ai produced no result event — check the stderr log (and the --bare / --model 'glm-5.2[1m]' flags)" >&2
printf '%s\n' "$response"
```

### 3. Cleanup Temp Files

After processing the z.ai response, clean up the temp files — on a FAILURE, do this only
AFTER §4 has quoted the stderr tail (cleanup deletes the diagnostic):

```bash
rm -f "$PROJECT_DIR/tmp/zai-prompt-RUN_ID.txt" \
      "$PROJECT_DIR/tmp/zai-output-RUN_ID.json" \
      "$PROJECT_DIR/tmp/zai-stderr-RUN_ID.log"
```

This prevents stale prompts from accumulating and avoids potential confusion in future runs.

### 4. Handle Errors

- If one agent fails or times out, still present the successful agent's response
- Note the failure in the comparison: "Agent X failed to respond: [error message]"
- On a z.ai failure, quote the tail of `zai-stderr-RUN_ID.log` (auth/endpoint diagnostics
  live there) before cleanup
- Provide analysis based on the available response; with only one agent, label the report
  a degraded single-AI run (no cross-comparison)

### 5. Create Comparison Analysis

Use this exact format:

---

## z.ai (GLM 5.2) Response

[Raw output from zai-cli agent]

---

## Code-Searcher (Claude) Response

[Raw output from code-searcher agent]

---

## Comparison Table

(MANDATORY — always render this table on a multi-agent run; it is the at-a-glance visual diff readers rely on, so never skip it. Omit only in a degraded single-AI run, where there is nothing to compare.)

| Aspect | z.ai (GLM 5.2) | Code-Searcher (Claude) |
|--------|----------------|------------------------|
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

- **z.ai GLM 5.2:** [unique findings, strengths, approach]
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
