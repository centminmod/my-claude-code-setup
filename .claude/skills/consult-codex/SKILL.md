---
name: consult-codex
description: Compare OpenAI Codex GPT-5.2 and code-searcher responses for comprehensive dual-AI code analysis. Use when you need multiple AI perspectives on code questions.
---

# Dual-AI Consultation: Codex GPT-5.2 vs Code-Searcher

You orchestrate consultation between OpenAI's Codex GPT-5.2 and Claude's code-searcher to provide comprehensive analysis with comparison.

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

Wrap the user's question with structured output requirements:

```
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
- For multiple references: list each with its line number
- Include brief code snippets for key findings

**Examples of good citations:**
- "The authentication check at `src/auth/validate.ts:127-134`"
- "Configuration loaded from `config/settings.json:15`"
- "Error handling in `lib/errors.ts:45, 67-72, 98`"
```

### 2. Invoke Both Analyses in Parallel

Launch both simultaneously in a single message with multiple tool calls:

- **For Codex GPT-5.2:** Use a temp file to avoid shell quoting issues:

  **Step 1:** Write the enhanced prompt to a temp file using the Write tool:
  ```
  Write to /tmp/codex-prompt.txt with the ENHANCED_PROMPT content
  ```

  **Step 2:** Execute Codex with the temp file:

  **macOS:**
  ```bash
  zsh -i -c 'codex -p readonly exec "$(cat /tmp/codex-prompt.txt)" --json 2>&1'
  ```

  **Linux:**
  ```bash
  bash -i -c 'codex -p readonly exec "$(cat /tmp/codex-prompt.txt)" --json 2>&1'
  ```

  This approach avoids all shell quoting issues regardless of prompt content.

- **For Code-Searcher:** Use Task tool with `subagent_type: "code-searcher"` with the same enhanced prompt

This parallel execution significantly improves response time.

### 2a. Parse Codex `--json` Output Files (jq Recipes)

Codex CLI with `--json` typically emits **newline-delimited JSON events** (JSONL). Some environments may prefix lines with terminal escape sequences; these recipes strip everything before the first `{` and then `fromjson?` safely.

Set a variable first:

```bash
FILE="/private/tmp/claude/.../tasks/<task_id>.output"   # or a symlinked *.output to agent-*.jsonl
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

**Extract just the final `agent_message` (useful for summaries)**

```bash
jq -Rr '
  sub("^[^{]*";"")
  | fromjson?
  | select(.type=="item.completed" and .item.type?=="agent_message")
  | .item.text // empty
' "$FILE" | tail -n 1
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

After processing the Codex response (success or failure), clean up the temp prompt file:

```bash
rm -f /tmp/codex-prompt.txt
```

This prevents stale prompts from accumulating and avoids potential confusion in future runs.

### 4. Handle Errors

- If one agent fails or times out, still present the successful agent's response
- Note the failure in the comparison: "Agent X failed to respond: [error message]"
- Provide analysis based on the available response

### 5. Create Comparison Analysis

Use this exact format:

---

## Codex (GPT-5.2) Response

[Raw output from codex-cli agent]

---

## Code-Searcher (Claude) Response

[Raw output from code-searcher agent]

---

## Comparison Table

| Aspect | Codex (GPT-5.2) | Code-Searcher (Claude) |
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

## Key Differences

- **Codex GPT-5.2:** [unique findings, strengths, approach]
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
