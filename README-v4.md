[![GitHub stars](https://img.shields.io/github/stars/centminmod/my-claude-code-setup.svg?style=flat-square)](https://github.com/centminmod/my-claude-code-setup/stargazers) [![GitHub forks](https://img.shields.io/github/forks/centminmod/my-claude-code-setup.svg?style=flat-square)](https://github.com/centminmod/my-claude-code-setup/network) [![GitHub issues](https://img.shields.io/github/issues/centminmod/my-claude-code-setup.svg?style=flat-square)](https://github.com/centminmod/my-claude-code-setup/issues)

* Threads - https://www.threads.com/@george_sl_liu
* BlueSky - https://bsky.app/profile/georgesl.bsky.social

# My Claude Code Setup - Technical Reference

## Overview

### Purpose & Scope

This repository provides a comprehensive starter kit for Claude Code projects, including:

- **Memory Bank System**: Structured context files for persistent memory across sessions
- **Pre-configured Settings**: Optimized `.claude/settings.json` with fast tools
- **Custom Extensions**: Hooks, skills, subagents, and slash commands
- **MCP Server Integration**: Curated external tool connections
- **Alternative Provider Support**: Z.AI integration for higher quotas

### Target Audience

- **Beginners**: New to Claude Code, need step-by-step guidance
- **Intermediate Users**: Want to extend Claude Code with plugins and MCP servers
- **Advanced Users**: Building custom subagents, skills, and workflows
- **Power Users**: Need comprehensive reference for all configuration options

### Compatibility Matrix

| Component | Minimum Version | Recommended |
|-----------|-----------------|-------------|
| Node.js | 18+ | Latest LTS |
| Git | 2.30+ | Latest |
| Claude AI Account | Pro/Max | Max |
| ripgrep | 12.0+ | Latest |
| fd | 8.0+ | Latest |
| jq | 1.6+ | Latest |

---

## Table of Contents

- **Part I: Getting Started**
  - [Chapter 1: Prerequisites](#chapter-1-prerequisites)
  - [Chapter 2: Installation](#chapter-2-installation)
  - [Chapter 3: Initial Configuration](#chapter-3-initial-configuration)
- **Part II: Memory Bank System**
  - [Chapter 4: Architecture](#chapter-4-architecture)
  - [Chapter 5: Core Context Files](#chapter-5-core-context-files)
  - [Chapter 6: Operations](#chapter-6-operations)
- **Part III: Extensions**
  - [Chapter 7: Plugin System](#chapter-7-plugin-system)
  - [Chapter 8: MCP Servers](#chapter-8-mcp-servers)
- **Part IV: Customization**
  - [Chapter 9: Subagents](#chapter-9-subagents)
  - [Chapter 10: Skills](#chapter-10-skills)
  - [Chapter 11: Hooks](#chapter-11-hooks)
  - [Chapter 12: Slash Commands](#chapter-12-slash-commands)
- **Part V: Alternative Providers**
  - [Chapter 13: Z.AI Integration](#chapter-13-zai-integration)
- **Part VI: Development Workflows**
  - [Chapter 14: Git Worktrees](#chapter-14-git-worktrees)
  - [Chapter 15: Status Lines](#chapter-15-status-lines)
- **Part VII: Reference**
  - [Chapter 16: Settings](#chapter-16-settings)
  - [Chapter 17: Environment Variables](#chapter-17-environment-variables)
  - [Chapter 18: File Locations](#chapter-18-file-locations)
  - [Chapter 19: Tools Available to Claude](#chapter-19-tools-available-to-claude)
  - [Chapter 20: Cost & Rate Management](#chapter-20-cost--rate-management)
- **Appendices**
  - [Appendix A: Quick Reference Cards](#appendix-a-quick-reference-cards)
  - [Appendix B: Troubleshooting](#appendix-b-troubleshooting)
  - [Appendix C: Resources](#appendix-c-resources)
  - [Appendix D: Star History & Stats](#appendix-d-star-history--stats)

---

# Part I: Getting Started

## Chapter 1: Prerequisites

### 1.1 System Requirements

| OS | Support Level | Notes |
|----|---------------|-------|
| macOS | Full | All features supported |
| Linux | Full | All features supported |
| Windows | Full | PowerShell and CMD supported |

### 1.2 Required Accounts

| Account | Purpose | Link |
|---------|---------|------|
| Claude AI | Claude Code access | [claude.ai](https://claude.ai/) |
| GitHub (optional) | Version control | [github.com](https://github.com/) |

**Claude AI Pricing:**

| Plan | Monthly Cost | Usage Limits |
|------|-------------|--------------|
| Pro | $20 | Standard quotas |
| Max | $100 | Higher quotas |
| Max | $200 | Highest quotas |

See [official usage limits](https://support.anthropic.com/en/articles/9797557-usage-limit-best-practices).

### 1.3 Required Tools

| Tool | Version | Purpose | Installation |
|------|---------|---------|--------------|
| Node.js | 18+ | Runtime environment | [nodejs.org](https://nodejs.org/) |
| Git | Latest | Version control | [git-scm.com](https://git-scm.com/) |
| ripgrep | Latest | Fast content search | `brew install ripgrep` (macOS) |
| fd | Latest | Fast file finding | `brew install fd` (macOS) |
| jq | Latest | JSON processing | `brew install jq` (macOS) |

**macOS Installation (all tools):**
```bash
brew install ripgrep fd jq
```

---

## Chapter 2: Installation

### 2.1 Installation Methods

Choose the method that best fits your workflow:

#### Method A: Clone Entire Repository (New Projects)

```bash
# 1. Clone this repository as your new project
git clone https://github.com/centminmod/my-claude-code-setup.git my-project
cd my-project

# 2. Remove template README files (create your own project documentation)
rm README.md README-v2.md README-v3.md README-v4.md

# 3. Reinitialize git for your own project (optional)
rm -rf .git
git init

# 4. Launch Claude Code and initialize
claude
# Then run: /init
```

#### Method B: Selective Copy (Existing Projects)

For existing projects, copy only the components you need:

```bash
# Core files (recommended minimum)
cp /path/to/my-claude-code-setup/CLAUDE.md your-project/
cp -r /path/to/my-claude-code-setup/.claude your-project/

# Or selectively copy specific components:
mkdir -p your-project/.claude
cp -r /path/to/my-claude-code-setup/.claude/settings.json your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/commands your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/skills your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/agents your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/hooks your-project/.claude/
```

#### Method C: Download from GitHub

Browse the repository on GitHub and download individual files:

| Component | Path | Purpose |
|-----------|------|---------|
| Memory Bank | `CLAUDE.md` | Main context file |
| Settings | `.claude/settings.json` | Configuration template |
| Commands | `.claude/commands/` | Custom slash commands |
| Skills | `.claude/skills/` | Custom skills |
| Agents | `.claude/agents/` | Custom subagents |
| Hooks | `.claude/hooks/` | Event hooks |

After copying files, launch Claude Code in your project and run `/init`.

### 2.2 Via NPM

```bash
npm install -g @anthropic-ai/claude-code
```

### 2.3 Development Container

For isolated development with YOLO mode support:

[VS Code Dev Container Setup](https://claude-devcontainers.centminmod.com/)

Features:
- Claude Code with `dangerously_skip_permissions`
- Codex CLI with `sandbox_mode = danger-full-access`
- Gemini CLI, Vercel CLI, Cloudflare Wrangler
- Amazon AWS CLI

### 2.4 Verification

```bash
# Verify Claude Code installation
claude --version

# Verify fast tools
rg --version
fd --version
jq --version
```

---

## Chapter 3: Initial Configuration

### 3.1 Copying Starter Files

1. Copy all files from this repository to your project root
2. Review and modify `CLAUDE.md` for your project specifics
3. Modify `.claude/settings.json` as needed

### 3.2 First-Time Setup

The `.claude/settings.json` includes Terminal-Notifier for macOS notifications. Remove if not using macOS. See [Terminal-Notifier Setup](https://github.com/centminmod/terminal-notifier-setup).

### 3.3 IDE Integration

#### VS Code Extension

- Install: [Claude Code Extension](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code)
- Guides:
  - [Beginner Video](https://www.youtube.com/watch?v=rPITZvwyoMc)
  - [Advanced Video](https://www.youtube.com/watch?v=P-5bWpUbO60)

#### Git for VS Code

- [Setup Guide](https://www.youtube.com/watch?v=twsYxYaQikI)
- [Tutorial](https://www.youtube.com/watch?v=z5jZ9lrSpqk)

---

# Part II: Memory Bank System

## Chapter 4: Architecture

### 4.1 Design Philosophy

The Memory Bank System enables Claude Code to maintain context across multiple chat sessions through structured markdown files. Instead of starting fresh each session, Claude reads these files to understand:

- Project patterns and conventions
- Architecture decisions and rationale
- Current work state and goals
- Common issues and solutions

### 4.2 File Hierarchy

```
project-root/
├── CLAUDE.md                      # Main entry point
├── CLAUDE-activeContext.md        # Current session state
├── CLAUDE-patterns.md             # Code patterns
├── CLAUDE-decisions.md            # Architecture Decision Records
├── CLAUDE-troubleshooting.md      # Issue/solution database
├── CLAUDE-config-variables.md     # Configuration reference
├── CLAUDE-temp.md                 # Temporary scratch pad
├── CLAUDE-cloudflare.md           # Optional: Cloudflare/ClerkOS docs
├── CLAUDE-cloudflare-mini.md      # Optional: Cloudflare mini reference
└── CLAUDE-convex.md               # Optional: Convex database docs
```

### 4.3 Loading Behavior

| File | When Loaded | Priority |
|------|-------------|----------|
| `CLAUDE.md` | Always | High |
| `CLAUDE-activeContext.md` | Always (if exists) | High |
| `CLAUDE-patterns.md` | Always (if exists) | Medium |
| `CLAUDE-decisions.md` | Always (if exists) | Medium |
| `CLAUDE-troubleshooting.md` | Always (if exists) | Medium |
| `CLAUDE-config-variables.md` | Always (if exists) | Low |
| `CLAUDE-temp.md` | Only when referenced | Low |

### 4.4 Context Window Management

Memory bank files consume context window tokens. Optimization strategies:

- Use `/cleanup-context` command for 15-25% token reduction
- Archive older decisions and patterns
- Keep `CLAUDE-temp.md` empty when not in use
- Reference supplementary docs (`CLAUDE-cloudflare.md`) only when needed

---

## Chapter 5: Core Context Files

### 5.1 CLAUDE.md (Main Entry Point)

Primary file containing:
- Project overview
- AI guidance rules
- Memory bank system instructions
- Tool usage preferences
- Directory/file exploration commands

### 5.2 CLAUDE-activeContext.md

Current session state:
- Active goals and tasks
- Recent changes
- Work in progress
- Session continuity notes

### 5.3 CLAUDE-patterns.md

Established patterns:
- Code conventions
- Naming patterns
- Architecture patterns
- API patterns

### 5.4 CLAUDE-decisions.md

Architecture Decision Records (ADRs):
- Decision context
- Options considered
- Decision made
- Rationale
- Consequences

### 5.5 CLAUDE-troubleshooting.md

Issue/solution database:
- Common errors
- Proven fixes
- Workarounds
- Prevention tips

### 5.6 CLAUDE-config-variables.md

Configuration reference:
- Environment variables
- Build configuration
- Runtime settings

### 5.7 CLAUDE-temp.md

Temporary scratch pad:
- Only read when explicitly referenced
- Cleared after use
- For temporary notes during complex tasks

---

## Chapter 6: Operations

### 6.1 Initialization (/init)

After launching Claude Code:

```
/init
```

Claude Code will:
1. Analyze your codebase structure
2. Identify patterns and conventions
3. Populate memory bank files
4. Set up context for future sessions

### 6.2 Updates

After significant work completion:

```
update memory bank
```

Claude updates all relevant CLAUDE-*.md files.

### 6.3 Backups

Memory bank backup (copy to backup directory):

```
backup memory bank to /path/to/backup
```

Files copied:
- All CLAUDE-*.md files
- `.claude/` settings directory

### 6.4 Example Session Output

```
> update memory bank

∴ Thinking…

  The user wants me to update the memory bank files. I should update the relevant CLAUDE-*.md files to reflect the v0.1.6 changes and current state. Let me check
   which memory bank files exist and update them.

∴ Thinking…

  I need to continue updating the memory bank files. I'll update:
  1. CLAUDE-patterns.md - Add export path handling pattern (Pattern 22)
  2. CLAUDE-decisions.md - Add ADR-017 for Phoneme API migration and ADR-018 for export path handling
  3. CLAUDE-troubleshooting.md - Add new issues and solutions for v0.1.6

∴ Thinking…

  The memory bank files have been modified but not committed. The v0.1.6 release was already committed and tagged, but the memory bank documentation updates are
  still uncommitted. Let me provide a summary of the completed work and offer to commit these documentation changes.

⏺ Summary: v0.1.6 Release Complete ✅

  Memory Bank Updates Complete:
  - CLAUDE-activeContext.md - v0.1.6 session context
  - CLAUDE-patterns.md - Added patterns 22-24 (Export Path, Format Detection, API Migration)
  - CLAUDE-decisions.md - Added ADR-017 & ADR-018
  - CLAUDE-troubleshooting.md - Added 4 new issue/fix entries

  v0.1.6 Fixes Applied:
  1. Export to absolute paths (e.g., --export /tmp/test.wav)
  2. Format detection from filename extension (prevents .mp3.wav)
  3. Phoneme API migrated to /dev/phonemize
  4. Test scripts updated for --export "" syntax

  Test Results: All 29 tests passing

  The memory bank documentation updates are ready to commit. Would you like me to commit them
```

---

# Part III: Extensions

## Chapter 7: Plugin System

### 7.1 Plugin Architecture

Claude Code plugins extend functionality through the official marketplace system.

### 7.2 Official Anthropic Marketplace

**Marketplace URL:** https://code.claude.com/docs/en/discover-plugins

#### Installation Commands

```bash
# Install plugin
/plugin install plugin-name@claude-plugins-official

# Update marketplace
/plugin marketplace update claude-plugins-official
```

#### Plugin Reference Table

| Plugin | Purpose | Source | Install Command | Notes |
|--------|---------|--------|-----------------|-------|
| code-simplifier | Code cleanup & maintainability | claude-plugins-official | `/plugin install code-simplifier` | [GitHub](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/code-simplifier) |
| frontend-design | Production-grade UI generation | claude-code-plugins | `/plugin install frontend-design@claude-code-plugins` | [GitHub](https://github.com/anthropics/claude-code/tree/main/plugins/frontend-design) |
| feature-dev | 7-phase feature development | claude-code-plugins | `/plugin install feature-dev@claude-code-plugins` | [GitHub](https://github.com/anthropics/claude-code/tree/main/plugins/feature-dev) |
| ralph-wiggum | Iterative AI loops | claude-code-plugins | `/plugin install ralph-wiggum@claude-code-plugins` | [GitHub](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) |

#### Ralph Wiggum Notes

- May have issues on some systems
- Known issues: [#16398](https://github.com/anthropics/claude-code/issues/16398), [#16389](https://github.com/anthropics/claude-code/issues/16389)
- Usage guide: [YouTube](https://www.youtube.com/watch?v=RpvQH0r0ecM)
- Documentation: [Blog](https://paddo.dev/blog/ralph-wiggum-autonomous-loops/)
- Repo: [GitHub](https://github.com/snarktank/ralph)

### 7.3 Third-Party Marketplaces

#### Adding Marketplaces

```bash
/plugin marketplace add owner/repo-name
```

#### Security Considerations

- Review plugin source code before installation
- Only install from trusted sources
- Check for recent updates and maintenance

#### Third-Party Plugin Reference

| Plugin | Source | Purpose | Commands |
|--------|--------|---------|----------|
| safety-net | cc-marketplace | Catches destructive git/filesystem commands | `/plugin marketplace add kenryu42/cc-marketplace`<br>`/plugin install safety-net@cc-marketplace` |
| glm-plan-usage | zai-coding-plugins | Query Z.AI usage statistics | `/plugin marketplace add zai/zai-coding-plugins`<br>`/plugin install glm-plan-usage@zai-coding-plugins` |
| Cloudflare Skills | cloudflare/skills | Development skills for Cloudflare platform (Workers, Pages, Agents SDK) | `/plugin marketplace add cloudflare/skills` |

**Safety Net**: [GitHub](https://github.com/kenryu42/claude-code-safety-net) - Prevents destructive commands like [this incident](https://www.reddit.com/r/ClaudeAI/comments/1pgxckk/claude_cli_deleted_my_entire_home_directory_wiped/).

**Z.AI Usage**: [Docs](https://docs.z.ai/devpack/extension/usage-query-plugin)

**Cloudflare Skills**: [GitHub](https://github.com/cloudflare/skills) - Development skills for Workers, Pages, AI services, and the Agents SDK. Commands: `/cloudflare:build-agent`, `/cloudflare:build-mcp`.

---

## Chapter 8: MCP Servers

### 8.1 Protocol Overview

MCP (Model Context Protocol) enables Claude Code to connect with external tools and services.

### 8.2 Server Categories

| Category | Purpose | Examples |
|----------|---------|----------|
| Documentation | Library/platform documentation lookup | Context7, Cloudflare Docs |
| Development Tools | Browser automation, testing | Chrome DevTools |
| Metrics | Usage tracking, cost monitoring | Usage Metrics |
| AI Models | Access to other AI providers | Gemini CLI |
| Productivity | Workspace integration | Notion |

### 8.3 Complete Server Reference

| Server | Type | Transport | Purpose | Token Cost | GitHub |
|--------|------|-----------|---------|------------|--------|
| Context7 | Documentation | SSE/HTTP | Look up docs for any library | Low | [upstash/context7](https://github.com/upstash/context7) |
| Cloudflare Docs | Documentation | SSE | Cloudflare documentation | Low | [cloudflare/mcp-server-cloudflare](https://github.com/cloudflare/mcp-server-cloudflare/tree/main/apps/docs-vectorize) |
| Usage Metrics | Metrics | stdio | Claude Code cost tracking | Low | [centminmod/claude-code-opentelemetry-setup](https://github.com/centminmod/claude-code-opentelemetry-setup) |
| Gemini CLI | AI Model | stdio | Gemini model access | Variable | [centminmod/gemini-cli-mcp-server](https://github.com/centminmod/gemini-cli-mcp-server) |
| Notion | Productivity | stdio | Notion workspace integration | Variable | [makenotion/notion-mcp-server](https://github.com/makenotion/notion-mcp-server) |
| Chrome DevTools | Development | stdio | Browser automation & debugging | ~17K | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) |

### 8.4 Installation Commands (Complete)

#### Context7 MCP

```bash
claude mcp add --transport http context7 https://mcp.context7.com/mcp --header "CONTEXT7_API_KEY: YOUR_API_KEY" -s user
```

#### Cloudflare Documentation MCP

```bash
claude mcp add --transport sse cf-docs https://docs.mcp.cloudflare.com/sse -s user
```

#### Usage Metrics MCP

```bash
claude mcp add --transport stdio metrics -s user -- uv run --directory /path/to/your/mcp-server metrics-server
```

Example output from `get_current_cost`:
```json
{
  "metric": "Total Cost Today",
  "value": 27.149809833783127,
  "formatted": "$27.1498",
  "unit": "currencyUSD"
}
```

#### Gemini CLI MCP

```bash
claude mcp add gemini-cli /path/to/.venv/bin/python /path/to/mcp_server.py -s user -e GEMINI_API_KEY='YOUR_GEMINI_KEY' -e OPENROUTER_API_KEY='YOUR_OPENROUTER_KEY'
```

#### Notion MCP

```bash
claude mcp add-json notionApi '{"type":"stdio","command":"npx","args":["-y","@notionhq/notion-mcp-server"],"env":{"OPENAPI_MCP_HEADERS":"{\"Authorization\": \"Bearer ntn_API_KEY\", \"Notion-Version\": \"2022-06-28\"}"}}' -s user
```

#### Chrome DevTools MCP (On-Demand)

Due to high token overhead (~17K across 26 tools), install on-demand:

```bash
claude --mcp-config .claude/mcp/chrome-devtools.json
```

Create `.claude/mcp/chrome-devtools.json`:
```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

### 8.5 Server-Specific Configuration Notes

#### Chrome DevTools Token Breakdown

26 tools totaling ~16,977 tokens:

| Tool | Tokens |
|------|--------|
| list_console_messages | 584 |
| emulate_cpu | 651 |
| emulate_network | 694 |
| click | 636 |
| drag | 638 |
| fill | 644 |
| fill_form | 676 |
| hover | 609 |
| upload_file | 651 |
| get_network_request | 618 |
| list_network_requests | 783 |
| close_page | 624 |
| handle_dialog | 645 |
| list_pages | 582 |
| navigate_page | 642 |
| navigate_page_history | 656 |
| new_page | 637 |
| resize_page | 629 |
| select_page | 619 |
| performance_analyze_insight | 649 |
| performance_start_trace | 689 |
| performance_stop_trace | 586 |
| take_screenshot | 803 |
| evaluate_script | 775 |
| take_snapshot | 614 |
| wait_for | 643 |

#### Verification

```bash
claude mcp list
# Output:
# context7: https://mcp.context7.com/sse (SSE) - ✓ Connected
# cf-docs: https://docs.mcp.cloudflare.com/sse (SSE) - ✓ Connected
# metrics: uv run --directory /path/to/mcp-server metrics-server - ✓ Connected
```

---

# Part IV: Customization

## Chapter 9: Subagents

### 9.1 Subagent Architecture

Subagents are specialized tools that:
- Handle complex, multi-step tasks autonomously
- Use their own context window (separate from main conversation)
- Have custom prompts tailored to their purpose

Official documentation: [Claude Code Sub-agents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)

### 9.2 Built-in Subagents

Claude Code includes built-in subagent types. See official docs for complete list.

### 9.3 Creating Custom Subagents

Subagents are defined in `.claude/agents/` as markdown files.

### 9.4 Included Subagent Reference

| Agent | Location | Purpose | Key Features |
|-------|----------|---------|--------------|
| memory-bank-synchronizer | `.claude/agents/memory-bank-synchronizer.md` | Sync documentation with codebase | Pattern sync, ADR updates, code freshness validation |
| code-searcher | `.claude/agents/code-searcher.md` | Efficient codebase navigation | Standard mode + CoD mode (80% fewer tokens) |
| get-current-datetime | `.claude/agents/get-current-datetime.md` | Brisbane timezone (GMT+10) values | Multiple formats, eliminates timezone confusion |
| ux-design-expert | `.claude/agents/ux-design-expert.md` | UX/UI design guidance | Tailwind CSS, Highcharts, accessibility compliance |
| zai-cli | `.claude/agents/zai-cli.md` | z.ai GLM 4.7 CLI wrapper | JSON output, used by consult-zai skill |
| codex-cli | `.claude/agents/codex-cli.md` | Codex GPT-5.2 CLI wrapper | Readonly mode, used by consult-codex skill |

#### memory-bank-synchronizer

**Purpose**: Maintains consistency between CLAUDE-*.md files and source code.

**Responsibilities**:
- Pattern documentation synchronization
- Architecture decision updates
- Technical specification alignment
- Implementation status tracking
- Code example freshness validation
- Cross-reference validation

**Usage**: Proactively maintains documentation accuracy.

#### code-searcher

**Purpose**: Efficient codebase navigation and search.

**Modes**:
- **Standard**: Full detailed analysis
- **CoD (Chain of Draft)**: ~80% fewer tokens with ultra-concise responses

**Usage**:
```
# Standard
"Find the payment processing code"

# CoD mode
"Find the payment processing code using CoD"
# Output: "Payment→glob:*payment*→found:payment.service.ts:45"
```

**Trigger phrases for CoD**: "use CoD", "chain of draft", "draft mode"

#### get-current-datetime

**Purpose**: Accurate Brisbane, Australia (GMT+10) timestamps.

**Formats**:
- Default: Standard date output
- Filename: Safe for file naming
- Readable: Human-friendly format
- ISO: ISO 8601 format

**Usage**: File timestamps, reports, logging.

#### ux-design-expert

**Purpose**: Comprehensive UX/UI design guidance.

**Capabilities**:
- UX flow optimization
- Premium UI design with Tailwind CSS
- Data visualization with Highcharts
- Accessibility compliance
- Component library design

#### zai-cli

**Purpose**: CLI wrapper for z.ai GLM 4.7 model queries.

**Features**:
- Executes z.ai CLI with JSON output format
- Uses haiku model for minimal overhead
- Returns raw output for parent skill to process

**Usage**: Used internally by consult-zai skill; not typically invoked directly.

#### codex-cli

**Purpose**: CLI wrapper for OpenAI Codex GPT-5.2 queries.

**Features**:
- Executes Codex CLI in readonly mode with JSON output
- Uses haiku model for minimal overhead
- Returns raw output for parent skill to process

**Usage**: Used internally by consult-codex skill; not typically invoked directly.

---

## Chapter 10: Skills

### 10.1 Skill Architecture

Skills provide specialized capabilities invoked automatically or on-demand.

Official documentation: [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills)

### 10.2 Skill File Structure

Skills are defined in `.claude/skills/` directories containing:
- `SKILL.md`: Skill definition and instructions
- Supporting files as needed

### 10.3 Included Skills Reference

| Skill | Purpose | Invocation | Location |
|-------|---------|------------|----------|
| claude-docs-consultant | Fetch official Claude Code documentation | Automatic when working on Claude Code features | `.claude/skills/claude-docs-consultant/` |
| consult-zai | Dual-AI consultation: z.ai GLM 4.7 vs code-searcher | `/consult-zai "question"` or via Skill tool | `.claude/skills/consult-zai/` |
| consult-codex | Dual-AI consultation: Codex GPT-5.2 vs code-searcher | `/consult-codex "question"` or via Skill tool | `.claude/skills/consult-codex/` |

#### claude-docs-consultant

**Purpose**: Selectively consults official Claude Code documentation from docs.claude.com.

**Triggers**: Working on hooks, skills, subagents, MCP servers, or any Claude Code feature requiring official documentation.

**Behavior**: Fetches only specific documentation needed rather than loading all docs upfront.

#### consult-zai

**Purpose**: Dual-AI consultation comparing z.ai GLM 4.7 and code-searcher responses.

**Features**:
- Invokes both zai-cli and code-searcher agents in parallel
- Enhanced prompts requesting structured output with `file:line` citations
- Comparison table showing file paths, line numbers, code snippets, and accuracy
- Agreement level indicator (High/Partial/Disagreement) for confidence assessment
- Synthesized summary combining best insights from both AI sources

**Usage**: `/consult-zai "your code analysis question"` or invoke via Skill tool.

#### consult-codex

**Purpose**: Dual-AI consultation comparing OpenAI Codex GPT-5.2 and code-searcher responses.

**Features**:
- Invokes both codex-cli and code-searcher agents in parallel
- Enhanced prompts requesting structured output with `file:line` citations
- Comparison table showing file paths, line numbers, code snippets, and accuracy
- Agreement level indicator (High/Partial/Disagreement) for confidence assessment
- Synthesized summary combining best insights from both AI sources

**Usage**: `/consult-codex "your code analysis question"` or invoke via Skill tool.

---

## Chapter 11: Hooks

### 11.1 Hook Events Reference

Hooks run custom commands before or after tool execution.

### 11.2 Configuration

Hooks are configured in `.claude/hooks/`.

### 11.3 Included Hooks

**STOP Notification Hook**

Uses Terminal-Notifier to show macOS desktop notifications when Claude Code completes a response.

Setup: [Terminal-Notifier](https://github.com/centminmod/terminal-notifier-setup)

---

## Chapter 12: Slash Commands

### 12.1 Built-in Commands

Claude Code includes built-in commands like `/init`, `/config`, `/help`.

### 12.2 Custom Command Structure

Custom commands are defined in `.claude/commands/` as markdown files.

### 12.3 Included Commands Reference

| Namespace | Command | Purpose | Usage |
|-----------|---------|---------|-------|
| /anthropic | apply-thinking-to | Enhanced prompts with extended thinking | `/apply-thinking-to @/path/to/prompt.md` |
| /anthropic | convert-to-todowrite-tasklist-prompt | Task optimization (60-70% faster) | `/convert-to-todowrite-tasklist-prompt @/path/to/command.md` |
| /anthropic | update-memory-bank | Update memory bank files | `/update-memory-bank` |
| /ccusage | ccusage-daily | Usage cost analysis | `/ccusage-daily` |
| /cleanup | cleanup-context | Token reduction (15-25%) | `/cleanup-context` |
| /documentation | create-readme-section | README section generation | `/create-readme-section "topic"` |
| /documentation | create-release-note | Dual release notes | `/create-release-note` or `/create-release-note 20` |
| /security | security-audit | OWASP security audit | `/security-audit` |
| /security | check-best-practices | Best practices analysis | `/check-best-practices` |
| /security | secure-prompts | Prompt injection detection | `/secure-prompts @file.txt` |
| /architecture | explain-architecture-pattern | Pattern analysis | `/explain-architecture-pattern` |
| /promptengineering | convert-to-test-driven-prompt | TDD-style prompts | `/convert-to-test-driven-prompt "request"` |
| /promptengineering | batch-operations-prompt | Parallel processing optimization | `/batch-operations-prompt "request"` |
| /refactor | refactor-code | Refactoring plans | `/refactor-code` |

#### Command Details

##### /apply-thinking-to

Transforms prompts using:
- Progressive reasoning structure
- Sequential analytical frameworks
- Systematic verification with test cases
- Constraint optimization
- Bias detection
- Extended thinking budget management

##### /convert-to-todowrite-tasklist-prompt

Achieves 60-70% speed improvements through:
- Parallel processing
- Specialized task delegation
- Strategic file selection (max 5 files per task)
- Context overflow prevention

##### /create-release-note

Two modes:
- By commit count: `/create-release-note 20`
- Interactive selection after viewing commits

Outputs:
- Customer-facing release note (value-focused)
- Technical engineering note (SHA references, file paths)

##### /secure-prompts

Test prompts available at `.claude/commands/security/test-examples/`:
- `test-encoding-attacks.md`
- `test-advanced-injection.md`
- `test-basic-role-override.md`
- `test-css-hiding.md`
- `test-invisible-chars.md`
- `test-authority-claims.md`

Reports saved to `reports/secure-prompts/`.

##### /refactor-code

Analysis-only refactoring that:
- Analyzes code complexity
- Assesses test coverage
- Identifies architectural patterns
- Creates step-by-step plans
- Generates risk assessment
- Outputs to `reports/refactor/`

---

# Part V: Alternative Providers

## Chapter 13: Z.AI Integration

### 13.1 Overview

[Z.AI's GLM Coding Plan](https://z.ai) provides cost-effective access to GLM models optimized for coding.

**Features**:
- 55+ tokens/second performance
- Vision Understanding
- Web Search, Web Reader MCP servers
- GLM-4.7 with state-of-the-art reasoning

### 13.2 Pricing & Plans

| Plan | Prompts/5hrs | Monthly Cost | vs Claude |
|------|--------------|--------------|-----------|
| Lite | ~120 | ~$3 | 3× Claude Pro quota |
| Pro | ~600 | Higher | 3× Claude Max 5x quota |
| Max | ~2,400 | Higher | 3× Claude Max 20x quota |

Each prompt allows 15–20 model calls = billions of tokens monthly at ~1% of standard API pricing.

**Discount**: 10% off with invite code [`WWB8IFLROM`](https://z.ai/subscribe?ic=WWB8IFLROM)

### 13.3 Privacy & Data Handling

| Aspect | Details |
|--------|---------|
| Data Location | Singapore |
| Storage | No content storage |
| Policy | [Privacy Policy](https://docs.z.ai/legal-agreement/privacy-policy) |

### 13.4 Setup Instructions

#### Prerequisites

- Node.js 18+
- Z.AI API key from [dashboard](https://z.ai)
- [Official docs](https://docs.z.ai/devpack/tool/claude)

#### Automated (macOS/Linux)

```bash
curl -O "https://cdn.bigmodel.cn/install/claude_code_zai_env.sh" && bash ./claude_code_zai_env.sh
```

#### Manual Configuration

Edit `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-zai-api-key",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "API_TIMEOUT_MS": "3000000"
  }
}
```

### 13.5 Shell Function Launchers

#### macOS / Linux (Bash/Zsh)

Add to `~/.bashrc`, `~/.zshrc`, or `~/.bash_aliases`:

```bash
# Z.AI + Claude Code launcher
zai() {
    export ANTHROPIC_AUTH_TOKEN="your-zai-api-key"
    export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
    export API_TIMEOUT_MS="3000000"
    claude "$@"
}
```

Reload: `source ~/.bashrc` or `source ~/.zshrc`

<details>
<summary><strong>Windows PowerShell</strong></summary>

Add to PowerShell profile (`notepad $PROFILE`):

```powershell
# Z.AI + Claude Code launcher
function zai {
    $env:ANTHROPIC_AUTH_TOKEN = "your-zai-api-key"
    $env:ANTHROPIC_BASE_URL = "https://api.z.ai/api/anthropic"
    $env:API_TIMEOUT_MS = "3000000"
    claude $args
}
```

Reload: `. $PROFILE`

</details>

<details>
<summary><strong>Windows CMD Batch</strong></summary>

Create `zai.bat` in a PATH directory:

```batch
@echo off
set ANTHROPIC_AUTH_TOKEN=your-zai-api-key
set ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
set API_TIMEOUT_MS=3000000
claude %*
```

</details>

### 13.6 Model Mapping Configuration

**Default Mapping**:

| Claude Model | GLM Model |
|--------------|-----------|
| Opus | GLM-4.7 |
| Sonnet | GLM-4.7 |
| Haiku | GLM-4.5-Air |

**Custom Mapping** (optional):

In `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-zai-api-key",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "API_TIMEOUT_MS": "3000000",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "GLM-4.7",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "GLM-4.5",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "GLM-4.5-Air"
  }
}
```

Or in shell function:

```bash
zai() {
    export ANTHROPIC_AUTH_TOKEN="your-zai-api-key"
    export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
    export API_TIMEOUT_MS="3000000"
    export ANTHROPIC_DEFAULT_OPUS_MODEL="GLM-4.7"
    export ANTHROPIC_DEFAULT_SONNET_MODEL="GLM-4.5"
    export ANTHROPIC_DEFAULT_HAIKU_MODEL="GLM-4.5-Air"
    claude "$@"
}
```

<details>
<summary><strong>Windows PowerShell Custom Mapping</strong></summary>

```powershell
function zai {
    $env:ANTHROPIC_AUTH_TOKEN = "your-zai-api-key"
    $env:ANTHROPIC_BASE_URL = "https://api.z.ai/api/anthropic"
    $env:API_TIMEOUT_MS = "3000000"
    $env:ANTHROPIC_DEFAULT_OPUS_MODEL = "GLM-4.7"
    $env:ANTHROPIC_DEFAULT_SONNET_MODEL = "GLM-4.5"
    $env:ANTHROPIC_DEFAULT_HAIKU_MODEL = "GLM-4.5-Air"
    claude $args
}
```

</details>

<details>
<summary><strong>Windows CMD Custom Mapping</strong></summary>

```batch
@echo off
set ANTHROPIC_AUTH_TOKEN=your-zai-api-key
set ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
set API_TIMEOUT_MS=3000000
set ANTHROPIC_DEFAULT_OPUS_MODEL=GLM-4.7
set ANTHROPIC_DEFAULT_SONNET_MODEL=GLM-4.5
set ANTHROPIC_DEFAULT_HAIKU_MODEL=GLM-4.5-Air
claude %*
```

</details>

**Usage**:
```bash
zai                              # Launch
zai --model sonnet               # Specific model
zai --model opus --permission-mode plan
```

### 13.7 Z.AI + Git Worktree Integration

#### macOS / Linux (Bash/Zsh)

```bash
# Z.AI + Claude Code worktree launcher
zaix() {
    local branch_name
    if [ -z "$1" ]; then
        branch_name="worktree-$(date +%Y%m%d-%H%M%S)"
    else
        branch_name="$1"
    fi
    git worktree add "../$branch_name" -b "$branch_name" && \
    cd "../$branch_name" || return 1

    export ANTHROPIC_AUTH_TOKEN="your-zai-api-key"
    export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
    export API_TIMEOUT_MS="3000000"
    claude --model sonnet --permission-mode plan
}
```

<details>
<summary><strong>Windows PowerShell Z.AI + Worktree</strong></summary>

```powershell
# Z.AI + Claude Code worktree launcher
function zaix {
    param([string]$BranchName)
    if (-not $BranchName) {
        $BranchName = "worktree-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    }
    git worktree add "../$BranchName" -b $BranchName
    if ($LASTEXITCODE -eq 0) {
        Set-Location "../$BranchName"
        $env:ANTHROPIC_AUTH_TOKEN = "your-zai-api-key"
        $env:ANTHROPIC_BASE_URL = "https://api.z.ai/api/anthropic"
        $env:API_TIMEOUT_MS = "3000000"
        claude --model sonnet --permission-mode plan
    }
}
```

</details>

<details>
<summary><strong>Windows CMD Z.AI + Worktree</strong></summary>

Create `zaix.bat`:

```batch
@echo off
setlocal enabledelayedexpansion
if "%~1"=="" (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
    set branch_name=worktree-!datetime:~0,8!-!datetime:~8,6!
) else (
    set branch_name=%~1
)
git worktree add "../%branch_name%" -b "%branch_name%"
if %errorlevel% equ 0 (
    cd "../%branch_name%"
    set ANTHROPIC_AUTH_TOKEN=your-zai-api-key
    set ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
    set API_TIMEOUT_MS=3000000
    claude --model sonnet --permission-mode plan
)
endlocal
```

</details>

**Usage**:
```bash
zaix feature-auth  # Named worktree
zaix               # Auto-generated name
```

### 13.8 GitHub Actions Integration

Claude Code integrates with GitHub Actions to automate AI-powered workflows. With `@claude` mentions in PRs or issues, Claude can analyze code, implement features, fix bugs, and follow project standards defined in `CLAUDE.md`.

**Key Capabilities**:
| Capability | Description |
|------------|-------------|
| Issue response | Respond to `@claude` mentions in issues |
| PR automation | Create and modify code through pull requests |
| Standards compliance | Follow project guidelines from `CLAUDE.md` |
| Slash commands | Execute commands like `/review` |

**Official Documentation**: [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions)

#### Z.AI Workflow Configuration

Create `.github/workflows/claude.yml`:

<details>
<summary>Click to expand workflow YAML</summary>

```yaml
name: Claude Code

on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  issues:
    types: [opened, assigned]
  pull_request_review:
    types: [submitted]

jobs:
  claude:
    if: |
      (github.event_name == 'issue_comment' && contains(github.event.comment.body, '@claude')) ||
      (github.event_name == 'pull_request_review_comment' && contains(github.event.comment.body, '@claude')) ||
      (github.event_name == 'pull_request_review' && contains(github.event.review.body, '@claude')) ||
      (github.event_name == 'issues' && (contains(github.event.issue.body, '@claude') || contains(github.event.issue.title, '@claude')))
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write
      id-token: write
      actions: read
    steps:
      - name: Checkout repository
        uses: actions/checkout@v5
        with:
          fetch-depth: 1

      - name: Run Claude Code
        id: claude
        uses: anthropics/claude-code-action@v1
        env:
          ANTHROPIC_BASE_URL: https://api.z.ai/api/anthropic
          API_TIMEOUT_MS: 3000000
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          claude_args: |
            --model claude-opus
            --max-turns 100
```

</details>

#### Workflow Component Reference

| Component | Purpose |
|-----------|---------|
| **Event Triggers** | Listens for `issue_comment`, `pull_request_review_comment`, `issues`, and `pull_request_review` events |
| **Conditional (`if`)** | Only runs when `@claude` is mentioned in the comment/issue body or title |
| **Permissions** | `contents: write` for code changes, `pull-requests: write` for PRs, `issues: write` for issue responses, `actions: read` for CI results |
| **ANTHROPIC_BASE_URL** | Routes API calls through Z.AI endpoint for higher quotas |
| **API_TIMEOUT_MS** | Extended timeout (50 minutes) for complex operations |
| **claude_args** | Uses `claude-opus` model with up to 100 turns for complex tasks |

#### Setup Steps

1. **Add API key as secret**: Repository Settings → Secrets and variables → Actions → Add `ANTHROPIC_API_KEY` with your Z.AI API key
2. **Create workflow file**: Save the YAML above to `.github/workflows/claude.yml`
3. **Usage**: Mention `@claude` in any issue or PR comment to trigger the workflow

---

# Part VI: Development Workflows

## Chapter 14: Git Worktrees

### 14.1 Concept & Benefits

Git worktrees enable parallel Claude Code sessions with complete code isolation.

**Benefits**:
| Benefit | Description |
|---------|-------------|
| Parallel sessions | Run multiple AI coding sessions simultaneously |
| Code isolation | Each worktree has independent file state |
| Shared history | All worktrees share the same Git history |
| YOLO mode | Safe experimental environment |

**Official Documentation**: [Run parallel Claude Code sessions with git worktrees](https://code.claude.com/docs/en/common-workflows#run-parallel-claude-code-sessions-with-git-worktrees)

### 14.2 Shell Functions

#### macOS / Linux Functions

Add to `~/.bashrc`, `~/.zshrc`, or `~/.bash_aliases`:

```bash
# Codex CLI worktree launcher
cx() {
    local branch_name
    if [ -z "$1" ]; then
        branch_name="worktree-$(date +%Y%m%d-%H%M%S)"
    else
        branch_name="$1"
    fi
    git worktree add "../$branch_name" -b "$branch_name" && \
    cd "../$branch_name" || return 1
    codex -m gpt-5-codex --config model_reasoning_effort='xhigh'
}

# Claude Code worktree launcher
clx() {
    local branch_name
    if [ -z "$1" ]; then
        branch_name="worktree-$(date +%Y%m%d-%H%M%S)"
    else
        branch_name="$1"
    fi
    git worktree add "../$branch_name" -b "$branch_name" && \
    cd "../$branch_name" || return 1
    claude --model opusplan --permission-mode plan
}
```

Reload: `source ~/.bashrc` or `source ~/.zshrc`

<details>
<summary><strong>Windows PowerShell Functions</strong></summary>

Add to PowerShell profile (`notepad $PROFILE`):

```powershell
# Codex CLI worktree launcher
function cx {
    param([string]$BranchName)
    if (-not $BranchName) {
        $BranchName = "worktree-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    }
    git worktree add "../$BranchName" -b $BranchName
    if ($LASTEXITCODE -eq 0) {
        Set-Location "../$BranchName"
        codex -m gpt-5-codex --config model_reasoning_effort='xhigh'
    }
}

# Claude Code worktree launcher
function clx {
    param([string]$BranchName)
    if (-not $BranchName) {
        $BranchName = "worktree-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    }
    git worktree add "../$BranchName" -b $BranchName
    if ($LASTEXITCODE -eq 0) {
        Set-Location "../$BranchName"
        claude --model opusplan --permission-mode plan
    }
}
```

Reload: `. $PROFILE`

</details>

<details>
<summary><strong>Windows CMD Batch Files</strong></summary>

Create in a PATH directory (e.g., `C:\Users\YourName\bin\`):

**cx.bat** - Codex CLI launcher:
```batch
@echo off
setlocal enabledelayedexpansion
if "%~1"=="" (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
    set branch_name=worktree-!datetime:~0,8!-!datetime:~8,6!
) else (
    set branch_name=%~1
)
git worktree add "../%branch_name%" -b "%branch_name%"
if %errorlevel% equ 0 (
    cd "../%branch_name%"
    codex -m gpt-5-codex --config model_reasoning_effort='xhigh'
)
endlocal
```

**clx.bat** - Claude Code launcher:
```batch
@echo off
setlocal enabledelayedexpansion
if "%~1"=="" (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
    set branch_name=worktree-!datetime:~0,8!-!datetime:~8,6!
) else (
    set branch_name=%~1
)
git worktree add "../%branch_name%" -b "%branch_name%"
if %errorlevel% equ 0 (
    cd "../%branch_name%"
    claude --model opusplan --permission-mode plan
)
endlocal
```

</details>

### 14.3 Usage Examples

```bash
# Create worktree with custom name
clx feature-auth
cx bugfix-123

# Create worktree with auto-generated timestamp name
clx
cx
```

### 14.4 Worktree Management

| Command | Purpose |
|---------|---------|
| `git worktree list` | List all worktrees |
| `git worktree remove ../name` | Remove a worktree |
| `git worktree prune` | Clean up stale references |

### 14.5 The .worktreeinclude File

**Purpose**: Specify which `.gitignore`d files to copy to new worktrees.

**How It Works**:
- Uses `.gitignore`-style patterns
- Only files matched by **both** `.worktreeinclude` **AND** `.gitignore` are copied

**Example** `.worktreeinclude`:
```text
# Environment files
.env
.env.local
.env.*

# Claude Code local settings
**/.claude/settings.local.json
```

**Common Use Cases**:
- `.env` files with API keys
- `.env.local` for local overrides
- `.claude/settings.local.json` for personal settings

### 14.6 Claude Desktop Integration

| Setting | Value |
|---------|-------|
| Default location | `~/.claude-worktrees` |
| Configuration | Claude Desktop app settings |
| Requirement | Repository must be Git initialized |

**Official Documentation**: [Claude Code on Desktop](https://code.claude.com/docs/en/desktop#claude-code-on-desktop-preview)

### 14.7 Local Ignores (.git/info/exclude)

**Purpose**: Ignore files locally without modifying shared `.gitignore`.

**Usage**:
```bash
nano .git/info/exclude
```

**Example**:
```text
# Local IDE settings
.idea/
*.swp

# Personal scripts
my-local-scripts/

# Local test files
test-local.sh
```

**Comparison**:

| File | Scope | Committed |
|------|-------|-----------|
| `.gitignore` | Team-shared | Yes |
| `.git/info/exclude` | Local only | No |
| `~/.config/git/ignore` | Global (all repos) | No |

**Interaction with .worktreeinclude**: Files in `.git/info/exclude` work the same as `.gitignore` - patterns must appear in both files for copying to worktrees.

---

## Chapter 15: Status Lines

### 15.1 Configuration

Add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statuslines/statusline.sh",
    "padding": 0
  }
}
```

### 15.2 JSON Input Structure

The status line script receives JSON input with:

| Field | Path | Description |
|-------|------|-------------|
| Model | `.model.display_name` | Current model name |
| Directory | `.workspace.current_dir` | Working directory |
| Input Tokens | `.context_window.total_input_tokens` | Total input tokens |
| Output Tokens | `.context_window.total_output_tokens` | Total output tokens |
| Context Size | `.context_window.context_window_size` | Context window size |
| Cost | `.cost.total_cost_usd` | Session cost in USD |
| Lines Added | `.cost.total_lines_added` | Lines of code added |
| Lines Removed | `.cost.total_lines_removed` | Lines of code removed |

### 15.3 Example Script (Complete)

Create `~/.claude/statuslines/statusline.sh`:

```bash
#!/bin/bash
# Read JSON input from stdin
input=$(cat)

# Extract model and workspace values
MODEL_DISPLAY=$(echo "$input" | jq -r '.model.display_name')
CURRENT_DIR=$(echo "$input" | jq -r '.workspace.current_dir')

# Extract context window metrics
INPUT_TOKENS=$(echo "$input" | jq -r '.context_window.total_input_tokens')
OUTPUT_TOKENS=$(echo "$input" | jq -r '.context_window.total_output_tokens')
CONTEXT_SIZE=$(echo "$input" | jq -r '.context_window.context_window_size')

# Extract cost metrics
COST_USD=$(echo "$input" | jq -r '.cost.total_cost_usd')
LINES_ADDED=$(echo "$input" | jq -r '.cost.total_lines_added')
LINES_REMOVED=$(echo "$input" | jq -r '.cost.total_lines_removed')

# Extract percentage metrics
USED_PERCENTAGE=$(echo "$input" | jq -r '.context_window.used_percentage')
REMAINING_PERCENTAGE=$(echo "$input" | jq -r '.context_window.remaining_percentage')

# Format tokens as Xk
format_tokens() {
    local num="$1"
    if [ "$num" -ge 1000 ]; then
        echo "$((num / 1000))k"
    else
        echo "$num"
    fi
}

# Generate progress bar for context usage
generate_progress_bar() {
    local percentage=$1
    local bar_width=20
    local filled=$(awk "BEGIN {printf \"%.0f\", ($percentage / 100) * $bar_width}")
    local empty=$((bar_width - filled))
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="█"; done
    for ((i=0; i<empty; i++)); do bar+="░"; done
    echo "$bar"
}

# Calculate total
TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS))

# Generate progress bar
PROGRESS_BAR=$(generate_progress_bar "$USED_PERCENTAGE")

# Show git branch if in a git repo
GIT_BRANCH=""
if git -C "$CURRENT_DIR" rev-parse --git-dir > /dev/null 2>&1; then
    BRANCH=$(git -C "$CURRENT_DIR" branch --show-current 2>/dev/null)
    if [ -n "$BRANCH" ]; then
        # Worktree detection
        GIT_DIR=$(git -C "$CURRENT_DIR" rev-parse --git-dir 2>/dev/null)
        WORKTREE=""
        if [[ "$GIT_DIR" == *".git/worktrees/"* ]] || [[ -f "$GIT_DIR/gitdir" ]]; then
            WORKTREE=" 🌳"
        fi
        # Ahead/behind detection
        AHEAD_BEHIND=""
        UPSTREAM=$(git -C "$CURRENT_DIR" rev-parse --abbrev-ref '@{u}' 2>/dev/null)
        if [ -n "$UPSTREAM" ]; then
            AHEAD=$(git -C "$CURRENT_DIR" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
            BEHIND=$(git -C "$CURRENT_DIR" rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)
            if [ "$AHEAD" -gt 0 ] && [ "$BEHIND" -gt 0 ]; then
                AHEAD_BEHIND=" ↕${AHEAD}/${BEHIND}"
            elif [ "$AHEAD" -gt 0 ]; then
                AHEAD_BEHIND=" ↑${AHEAD}"
            elif [ "$BEHIND" -gt 0 ]; then
                AHEAD_BEHIND=" ↓${BEHIND}"
            fi
        fi
        GIT_BRANCH=" | 🌿 $BRANCH${WORKTREE}${AHEAD_BEHIND}"
    fi
fi

echo "[$MODEL_DISPLAY] 📁 ${CURRENT_DIR##*/}${GIT_BRANCH}
Context: [$PROGRESS_BAR] ${USED_PERCENTAGE}%
Cost: \$${COST_USD} | +${LINES_ADDED} -${LINES_REMOVED} lines"
```

Make executable: `chmod +x ~/.claude/statuslines/statusline.sh`

---

# Part VII: Reference

## Chapter 16: Settings

### 16.1 Configuration Scopes

| Scope | Location | Affects | Shared | Priority |
|-------|----------|---------|--------|----------|
| Managed | System directories | All users | By IT | 1 (highest) |
| User | `~/.claude/settings.json` | You (all projects) | No | 5 |
| Project | `.claude/settings.json` | All collaborators | Yes | 4 |
| Local | `.claude/settings.local.json` | You (this project) | No | 3 |

**Precedence Order** (highest to lowest):
1. Enterprise policies
2. Command line arguments
3. Local project settings
4. Shared project settings
5. User settings

### 16.2 settings.json Options (Complete)

| Key | Type | Description | Default | Example |
|-----|------|-------------|---------|---------|
| `apiKeyHelper` | string | Script to generate auth value | - | `/bin/generate_temp_api_key.sh` |
| `cleanupPeriodDays` | number | Days to retain chat transcripts | 30 | `20` |
| `env` | object | Environment variables for sessions | `{}` | `{"FOO": "bar"}` |
| `includeCoAuthoredBy` | boolean | Add Claude byline to commits | `true` | `false` |
| `permissions` | object | Permission configuration | - | See below |
| `statusLine` | object | Status line configuration | - | See Chapter 15 |

### 16.3 Permission Settings

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `allow` | array | Allowed tool use rules | `["Bash(git diff:*)"]` |
| `deny` | array | Denied tool use rules | `["WebFetch", "Bash(curl:*)"]` |
| `additionalDirectories` | array | Extra working directories | `["../docs/"]` |
| `defaultMode` | string | Default permission mode | `"acceptEdits"` |
| `disableBypassPermissionsMode` | string | Prevent bypass mode | `"disable"` |

### 16.4 Sandbox Settings

For dev containers and isolated environments, see [Dev Container Setup](https://claude-devcontainers.centminmod.com/).

---

## Chapter 17: Environment Variables

### 17.1 Authentication Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key sent as `X-Api-Key` header |
| `ANTHROPIC_AUTH_TOKEN` | Custom value for `Authorization` header (prefixed with `Bearer `) |
| `ANTHROPIC_CUSTOM_HEADERS` | Custom headers in `Name: Value` format |

### 17.2 Model Configuration Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_MODEL` | Name of custom model to use |
| `ANTHROPIC_SMALL_FAST_MODEL` | Haiku-class model for background tasks |
| `ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION` | AWS region for small/fast model on Bedrock |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | Custom Opus model mapping |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Custom Sonnet model mapping |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | Custom Haiku model mapping |

### 17.3 Behavior Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BASH_DEFAULT_TIMEOUT_MS` | Default bash command timeout | - |
| `BASH_MAX_TIMEOUT_MS` | Maximum bash command timeout | - |
| `BASH_MAX_OUTPUT_LENGTH` | Max characters before truncation | - |
| `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` | Return to original dir after bash | - |
| `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` | Credential refresh interval | - |
| `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` | Skip IDE extension auto-install | `false` |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Max output tokens per request | - |
| `MAX_THINKING_TOKENS` | Force thinking budget | - |
| `MCP_TIMEOUT` | MCP server startup timeout (ms) | - |
| `MCP_TOOL_TIMEOUT` | MCP tool execution timeout (ms) | - |
| `MAX_MCP_OUTPUT_TOKENS` | Max MCP response tokens | 25000 |

### 17.4 Complete Reference Table

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | API key for Claude SDK |
| `ANTHROPIC_AUTH_TOKEN` | Custom auth header value |
| `ANTHROPIC_BASE_URL` | Custom API endpoint |
| `ANTHROPIC_CUSTOM_HEADERS` | Custom request headers |
| `ANTHROPIC_MODEL` | Custom model name |
| `ANTHROPIC_SMALL_FAST_MODEL` | Background task model |
| `ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION` | AWS region override |
| `BASH_DEFAULT_TIMEOUT_MS` | Default bash timeout |
| `BASH_MAX_TIMEOUT_MS` | Maximum bash timeout |
| `BASH_MAX_OUTPUT_LENGTH` | Max output characters |
| `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` | Maintain working dir |
| `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` | Credential TTL |
| `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` | Skip IDE auto-install |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Max output tokens |
| `CLAUDE_CODE_USE_BEDROCK` | Use Amazon Bedrock |
| `CLAUDE_CODE_USE_VERTEX` | Use Google Vertex AI |
| `CLAUDE_CODE_SKIP_BEDROCK_AUTH` | Skip Bedrock auth |
| `CLAUDE_CODE_SKIP_VERTEX_AUTH` | Skip Vertex auth |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | Disable non-essential traffic |
| `DISABLE_AUTOUPDATER` | Disable auto-updates |
| `DISABLE_BUG_COMMAND` | Disable `/bug` command |
| `DISABLE_COST_WARNINGS` | Disable cost warnings |
| `DISABLE_ERROR_REPORTING` | Opt out of Sentry |
| `DISABLE_NON_ESSENTIAL_MODEL_CALLS` | Disable flavor text calls |
| `DISABLE_TELEMETRY` | Opt out of Statsig |
| `HTTP_PROXY` | HTTP proxy server |
| `HTTPS_PROXY` | HTTPS proxy server |
| `MAX_THINKING_TOKENS` | Thinking budget |
| `MCP_TIMEOUT` | MCP startup timeout |
| `MCP_TOOL_TIMEOUT` | MCP tool timeout |
| `MAX_MCP_OUTPUT_TOKENS` | Max MCP tokens |
| `VERTEX_REGION_CLAUDE_3_5_HAIKU` | Vertex region override |
| `VERTEX_REGION_CLAUDE_3_5_SONNET` | Vertex region override |
| `VERTEX_REGION_CLAUDE_3_7_SONNET` | Vertex region override |
| `VERTEX_REGION_CLAUDE_4_0_OPUS` | Vertex region override |
| `VERTEX_REGION_CLAUDE_4_0_SONNET` | Vertex region override |

---

## Chapter 18: File Locations

### 18.1 By Operating System

| File | macOS | Linux | Windows |
|------|-------|-------|---------|
| User settings | `~/.claude/settings.json` | `~/.claude/settings.json` | `%USERPROFILE%\.claude\settings.json` |
| Project settings | `.claude/settings.json` | `.claude/settings.json` | `.claude\settings.json` |
| Local settings | `.claude/settings.local.json` | `.claude/settings.local.json` | `.claude\settings.local.json` |
| Managed settings | `/Library/Application Support/ClaudeCode/` | `/etc/claude-code/` | `C:\Program Files\ClaudeCode\` |
| Status line scripts | `~/.claude/statuslines/` | `~/.claude/statuslines/` | `%USERPROFILE%\.claude\statuslines\` |
| Hooks | `.claude/hooks/` | `.claude/hooks/` | `.claude\hooks\` |
| Skills | `.claude/skills/` | `.claude/skills/` | `.claude\skills\` |
| Agents | `.claude/agents/` | `.claude/agents/` | `.claude\agents\` |
| Commands | `.claude/commands/` | `.claude/commands/` | `.claude\commands\` |

### 18.2 Project Files Reference

| File | Purpose | Committed |
|------|---------|-----------|
| `CLAUDE.md` | Main memory bank | Yes |
| `CLAUDE-*.md` | Context files | Yes |
| `.claude/settings.json` | Shared settings | Yes |
| `.claude/settings.local.json` | Personal settings | No |
| `.claude/hooks/` | Custom hooks | Yes |
| `.claude/skills/` | Custom skills | Yes |
| `.claude/agents/` | Custom subagents | Yes |
| `.claude/commands/` | Custom commands | Yes |
| `.worktreeinclude` | Worktree file patterns | Yes |

---

## Chapter 19: Tools Available to Claude

### 19.1 Complete Tool Reference

| Tool | Description | Permission Required |
|------|-------------|---------------------|
| Agent | Runs a sub-agent for complex, multi-step tasks | No |
| Bash | Executes shell commands in your environment | Yes |
| Edit | Makes targeted edits to specific files | Yes |
| Glob | Finds files based on pattern matching | No |
| Grep | Searches for patterns in file contents | No |
| LS | Lists files and directories | No |
| MultiEdit | Performs multiple edits on a single file atomically | Yes |
| NotebookEdit | Modifies Jupyter notebook cells | Yes |
| NotebookRead | Reads and displays Jupyter notebook contents | No |
| Read | Reads the contents of files | No |
| TodoRead | Reads the current session's task list | No |
| TodoWrite | Creates and manages structured task lists | No |
| WebFetch | Fetches content from a specified URL | Yes |
| WebSearch | Performs web searches with domain filtering | Yes |
| Write | Creates or overwrites files | Yes |

**Permission Rules**: Configure with `/allowed-tools` or in permission settings.

**Extending Tools**: Use hooks to run custom commands before/after tool execution.

---

## Chapter 20: Cost & Rate Management

### 20.1 Weekly Rate Limits

From August 28, 2025, weekly limits apply (in addition to monthly 50x 5hr session limit):

| Plan | Sonnet 4 (hrs/week) | Opus 4 (hrs/week) |
|------|---------------------|-------------------|
| Pro | 40–80 | – |
| Max ($100/mo) | 140–280 | 15–35 |
| Max ($200/mo) | 240–480 | 24–40 |

### 20.2 Cost Optimization Strategies

| Strategy | Benefit | How |
|----------|---------|-----|
| Z.AI Integration | 3× higher quotas at ~$3/mo | Use shell function launcher |
| CoD Mode | 80% token reduction | Request "use CoD" in code-searcher |
| Git Worktrees | Parallel sessions without duplicating quota | Use shell functions |
| Status Lines | Real-time monitoring | Configure statusline.sh |
| MCP Metrics | Cost tracking | Install Usage Metrics MCP |
| Context Cleanup | 15-25% token reduction | Use `/cleanup-context` |

---

# Appendices

## Appendix A: Quick Reference Cards

### Installation Checklist

- [ ] Claude AI account (Pro/Max)
- [ ] Node.js 18+
- [ ] Git installed
- [ ] Fast tools: `brew install ripgrep fd jq`
- [ ] Clone repository
- [ ] Run `/init` in Claude Code

### Common Commands

| Command | Purpose |
|---------|---------|
| `/init` | Initialize memory bank |
| `/config` | Configure Claude Code |
| `/help` | Show help |
| `update memory bank` | Update CLAUDE-*.md files |
| `/ccusage-daily` | Show usage statistics |
| `/security-audit` | Run security audit |

### Keyboard Shortcuts

See official Claude Code documentation for current shortcuts.

---

## Appendix B: Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Memory bank not loading | Ensure CLAUDE.md exists in project root |
| MCP server not connecting | Run `claude mcp list` to verify |
| Slow searches | Install ripgrep and fd |
| High token usage | Use CoD mode, cleanup context |
| Z.AI not working | Check API key and base URL |

### Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `No API key found` | Missing authentication | Set `ANTHROPIC_API_KEY` or run `/login` |
| `MCP timeout` | Server startup too slow | Increase `MCP_TIMEOUT` |
| `Context window exceeded` | Too much content | Use `/cleanup-context` |

---

## Appendix C: Resources

### Official Documentation

| Resource | URL |
|----------|-----|
| Claude Code Overview | https://docs.anthropic.com/en/docs/claude-code/overview |
| Settings Reference | https://code.claude.com/docs/en/settings |
| Hooks Documentation | https://code.claude.com/docs/en/hooks |
| Skills Documentation | https://docs.claude.com/en/docs/claude-code/skills |
| Sub-agents | https://docs.anthropic.com/en/docs/claude-code/sub-agents |
| Plugin Marketplace | https://code.claude.com/docs/en/discover-plugins |
| Git Worktrees | https://code.claude.com/docs/en/common-workflows#run-parallel-claude-code-sessions-with-git-worktrees |
| Claude Desktop | https://code.claude.com/docs/en/desktop#claude-code-on-desktop-preview |

### YouTube Guides

| Topic | Creator | URL |
|-------|---------|-----|
| Claude Code with Opus 4.5 | Alex Finn | https://www.youtube.com/watch?v=UVJXh57MgI0 |
| How To Master Claude Code (7-Hour Course) | Anthropic Official | https://www.youtube.com/watch?v=XuSFUvUdvQA |
| Claude Code Overview | Matt Maher | https://www.youtube.com/watch?v=Dekx_OzRwiI |
| VS Code Beginner | - | https://www.youtube.com/watch?v=rPITZvwyoMc |
| VS Code Advanced | - | https://www.youtube.com/watch?v=P-5bWpUbO60 |
| Git for VS Code | - | https://www.youtube.com/watch?v=twsYxYaQikI |
| Ralph Wiggum | Greg Isenberg | https://www.youtube.com/watch?v=RpvQH0r0ecM |

### Other Guides

| Topic | Creator | URL |
|-------|---------|-----|
| 31 Days of Claude Code | Ado Kukic (Anthropic) | <https://adocomplete.com/advent-of-claude-2025/> |
| 40+ Claude Code Tips | ykdojo | <https://github.com/ykdojo/claude-code-tips> |

### Community Resources

| Resource | URL |
|----------|-----|
| Safety Net Plugin | https://github.com/kenryu42/claude-code-safety-net |
| Ralph Wiggum Repo | https://github.com/snarktank/ralph |
| Dev Container Setup | https://claude-devcontainers.centminmod.com/ |

---

## Appendix D: Star History & Stats

### Star History

[![Star History Chart](https://api.star-history.com/svg?repos=centminmod/my-claude-code-setup&type=Date)](https://www.star-history.com/#centminmod/my-claude-code-setup&Date)

### Repository Stats

![Alt](https://repobeats.axiom.co/api/embed/715da1679915da77d87deb99a1f527a44e76ec60.svg "Repobeats analytics image")
