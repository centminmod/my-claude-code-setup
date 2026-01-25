---
name: consult-zai
description: Compare z.ai GLM 4.7 and code-searcher responses for comprehensive dual-AI code analysis. Use when you need multiple AI perspectives on code questions.
---

# Dual-AI Consultation: z.ai GLM 4.7 vs Code-Searcher

You orchestrate consultation between z.ai's GLM 4.7 model and Claude's code-searcher to provide comprehensive analysis with comparison.

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

- **For z.ai GLM 4.7:** Use a temp file to avoid shell quoting issues:

  **Step 1:** Write the enhanced prompt to a temp file using the Write tool:
  ```
  Write to $CLAUDE_PROJECT_DIR/tmp/zai-prompt.txt with the ENHANCED_PROMPT content
  ```

  **Step 2:** Execute z.ai with the temp file:

  **macOS:**
  ```bash
  zsh -i -c 'zai -p "$(cat $CLAUDE_PROJECT_DIR/tmp/zai-prompt.txt)" --output-format json --append-system-prompt "You are GLM 4.7 model accessed via z.ai API." 2>&1'
  ```

  **Linux:**
  ```bash
  bash -i -c 'zai -p "$(cat $CLAUDE_PROJECT_DIR/tmp/zai-prompt.txt)" --output-format json --append-system-prompt "You are GLM 4.7 model accessed via z.ai API." 2>&1'
  ```

  This approach avoids all shell quoting issues regardless of prompt content.

- **For Code-Searcher:** Use Task tool with `subagent_type: "code-searcher"` with the same enhanced prompt

This parallel execution significantly improves response time.

### 3. Cleanup Temp Files

After processing the z.ai response (success or failure), clean up the temp prompt file:

```bash
rm -f $CLAUDE_PROJECT_DIR/tmp/zai-prompt.txt
```

This prevents stale prompts from accumulating and avoids potential confusion in future runs.

### 4. Handle Errors

- If one agent fails or times out, still present the successful agent's response
- Note the failure in the comparison: "Agent X failed to respond: [error message]"
- Provide analysis based on the available response

### 5. Create Comparison Analysis

Use this exact format:

---

## z.ai (GLM 4.7) Response

[Raw output from zai-cli agent]

---

## Code-Searcher (Claude) Response

[Raw output from code-searcher agent]

---

## Comparison Table

| Aspect | z.ai (GLM 4.7) | Code-Searcher (Claude) |
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

## Key Differences

- **z.ai GLM 4.7:** [unique findings, strengths, approach]
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
