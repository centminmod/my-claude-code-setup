---
name: claude-docs-consultant
description: Consult official Claude Code documentation from docs.claude.com using selective fetching. Use this skill when working on Claude Code hooks, skills, subagents, MCP servers, or any Claude Code feature that requires referencing official documentation for accurate implementation. Fetches only the specific documentation needed rather than loading all docs upfront.
---

# Claude Docs Consultant

## Overview

This skill enables efficient consultation of official Claude Code documentation by fetching only the specific docs needed for the current task. Instead of loading all documentation upfront, determine which docs are relevant and fetch them on-demand.

## When to Use This Skill

Invoke this skill when:

- Creating or modifying Claude Code hooks
- Building or debugging skills
- Working with subagents or understanding subagent parameters
- Implementing MCP server integrations
- Understanding any Claude Code feature that requires official documentation
- Troubleshooting Claude Code functionality
- Verifying correct API usage or parameters

## Common Documentation

For the most frequently referenced topics, fetch these detailed documentation files directly:

### Hooks Documentation

- **hooks-guide.md** - Comprehensive guide to creating hooks with examples and best practices

  - URL: `https://code.claude.com/docs/en/hooks-guide.md`
  - Use for: Understanding hook lifecycle, creating new hooks, examples

- **hooks.md** - Hooks API reference with event types and parameters
  - URL: `https://code.claude.com/docs/en/hooks.md`
  - Use for: Hook event reference, available events, parameter details

### Skills Documentation

- **skills.md** - Skills creation guide and structure reference
  - URL: `https://code.claude.com/docs/en/skills.md`
  - Use for: Creating skills, understanding SKILL.md format, bundled resources

### Subagents Documentation

- **sub-agents.md** - Subagent types, parameters, and usage
  - URL: `https://code.claude.com/docs/en/sub-agents.md`
  - Use for: Available subagent types, when to use Task tool, subagent parameters

## Workflow for Selective Fetching

Follow this process to efficiently fetch documentation:

### Step 1: Identify Documentation Needs

Determine which documentation is needed based on the task:

- **Hook-related task** → Fetch `hooks-guide.md` and/or `hooks.md`
- **Skill-related task** → Fetch `skills.md`
- **Subagent-related task** → Fetch `sub-agents.md`
- **Other Claude Code feature** → Proceed to Step 2

### Step 2: Discover Available Documentation (If Needed)

For features not covered by the 4 common docs above, fetch the docs map to discover available documentation:

```
URL: https://code.claude.com/docs/en/claude_code_docs_map.md
```

The docs map lists all available Claude Code documentation with descriptions. Identify the relevant doc(s) from the map.

### Step 3: Fetch Only Relevant Documentation

Use WebFetch to retrieve only the specific documentation needed:

```
WebFetch:
  url: https://code.claude.com/docs/en/[doc-name].md
  prompt: "Extract the full documentation content"
```

Fetch multiple docs in parallel if the task requires information from several sources.

### Step 4: Apply Documentation to Task

Use the fetched documentation to:

- Verify correct API usage
- Understand available parameters and options
- Follow best practices and examples
- Implement the feature correctly

## Examples

### Example 1: Creating a New Hook

**User request:** "Help me create a pre-tool-use hook to log all tool calls"

**Process:**

1. Identify need: Hook creation requires hooks documentation
2. Fetch `hooks-guide.md` for creation process and examples
3. Fetch `hooks.md` for pre-tool-use event reference
4. Apply: Create hook following guide, using correct event parameters

### Example 2: Debugging a Skill

**User request:** "My skill isn't loading - help me fix SKILL.md"

**Process:**

1. Identify need: Skill structure requires skills documentation
2. Fetch `skills.md` for SKILL.md format requirements
3. Apply: Validate frontmatter, structure, and bundled resources

### Example 3: Using Subagents

**User request:** "Which subagent should I use to search the codebase?"

**Process:**

1. Identify need: Subagent selection requires subagent documentation
2. Fetch `sub-agents.md` for subagent types and capabilities
3. Apply: Recommend appropriate subagent (e.g., Explore or code-searcher)

### Example 4: Unknown Feature

**User request:** "How do I configure Claude Code settings.json?"

**Process:**

1. Identify need: Not covered by the 4 common docs
2. Fetch docs map: `claude_code_docs_map.md`
3. Discover: Find relevant doc (e.g., `settings.md`)
4. Fetch specific doc: `https://code.claude.com/docs/en/settings.md`
5. Apply: Configure settings.json correctly

## Best Practices

### Token Efficiency

- Fetch only the documentation actually needed for the current task
- Fetch multiple docs in parallel if needed (single message with multiple WebFetch calls)
- Do not fetch documentation "just in case" - fetch when required

### Staying Current

- Always fetch from docs.claude.com (live docs, not cached copies)
- Documentation may be updated by Anthropic - fetching ensures latest information
- If documentation seems outdated or unclear, verify URL is correct

### Selective vs Comprehensive

- **Selective (preferred)**: Fetch hooks-guide.md for hook creation task
- **Comprehensive (avoid)**: Fetch all 4 common docs for every task
- **Discovery-based**: Use docs map when common docs don't cover the need
