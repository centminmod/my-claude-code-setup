[![GitHub stars](https://img.shields.io/github/stars/centminmod/my-claude-code-setup.svg?style=flat-square)](https://github.com/centminmod/my-claude-code-setup/stargazers) [![GitHub forks](https://img.shields.io/github/forks/centminmod/my-claude-code-setup.svg?style=flat-square)](https://github.com/centminmod/my-claude-code-setup/network) [![GitHub issues](https://img.shields.io/github/issues/centminmod/my-claude-code-setup.svg?style=flat-square)](https://github.com/centminmod/my-claude-code-setup/issues)

* Threads - https://www.threads.com/@george_sl_liu
* BlueSky - https://bsky.app/profile/georgesl.bsky.social

# My Claude Code Setup

A comprehensive starter kit for Claude Code projects featuring a memory bank system for context retention, pre-configured hooks, skills, subagents, and MCP server recommendations.

## Table of Contents

- [Quick Start](#quick-start)
- **Beginner**
  - [1. Getting Started](#1-getting-started)
  - [2. Memory Bank System](#2-memory-bank-system)
- **Intermediate**
  - [3. Extending Claude Code](#3-extending-claude-code)
  - [4. Development Workflows](#4-development-workflows)
- **Advanced**
  - [5. Customization](#5-customization)
  - [6. Alternative Providers (Z.AI)](#6-alternative-providers)
  - [7. Cost & Rate Management](#7-cost--rate-management)
- **Reference**
  - [8. Configuration Reference](#8-configuration-reference)
  - [9. Resources](#9-resources)

---

## Quick Start

Get up and running in under 5 minutes:

**Prerequisites Checklist:**
- [ ] [Paid Claude AI account](https://claude.ai/) (Pro $20/mo, Max $100/mo, or Max $200/mo)
- [ ] Node.js 18+ installed
- [ ] Git installed
- [ ] macOS: `brew install ripgrep fd jq`

**Installation Options:**

Choose the method that works best for you:

### Option A: Clone Entire Repository (New Projects)

```bash
# 1. Clone this repository as your new project
git clone https://github.com/centminmod/my-claude-code-setup.git my-project
cd my-project

# 2. Remove template README files (create your own project README)
rm README.md README-v2.md README-v3.md README-v4.md

# 3. Reinitialize git for your own project (optional)
rm -rf .git
git init

# 4. Launch Claude Code and initialize
claude
# Then run: /init
```

### Option B: Selective Copy (Existing Projects)

Copy only the files you need into your existing project:

```bash
# Core files (recommended)
cp /path/to/my-claude-code-setup/CLAUDE.md your-project/
cp -r /path/to/my-claude-code-setup/.claude your-project/

# Or selectively copy specific components:
cp -r /path/to/my-claude-code-setup/.claude/commands your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/skills your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/agents your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/hooks your-project/.claude/
```

### Option C: Download Specific Files (GitHub)

Browse the repository on GitHub and download individual files:
- `CLAUDE.md` - Memory bank main file
- `.claude/settings.json` - Settings template
- `.claude/commands/` - Slash commands you want
- `.claude/skills/` - Skills you want
- `.claude/agents/` - Subagents you want

After copying files, launch Claude Code in your project and run `/init`.

---

# BEGINNER SECTION

---

## 1. Getting Started

### 1.1 What This Repository Provides

- **Memory Bank System**: Structured context files for persistent memory across sessions
- **Pre-configured Settings**: Optimized `.claude/settings.json` with fast tools
- **Custom Hooks**: Desktop notifications when Claude Code completes tasks
- **Custom Skills**: Specialized agents for documentation lookup
- **Custom Subagents**: Task-specific agents for code search, UX design, and more
- **Custom Slash Commands**: Security audits, refactoring plans, prompt engineering
- **MCP Server Recommendations**: Curated list of useful MCP servers

### 1.2 Prerequisites

| Requirement | Version | Purpose |
|------------|---------|---------|
| Claude AI Account | Pro/Max | Required for Claude Code access |
| Node.js | 18+ | Runtime environment |
| Git | Latest | Version control |
| ripgrep | Latest | Fast content search |
| fd | Latest | Fast file finding |
| jq | Latest | JSON processing |

**Operating System Support:**
- macOS: Fully supported
- Linux: Fully supported
- Windows: Supported (PowerShell or CMD)

### 1.3 Installation Steps

1. **Copy Repository Files**

   Copy all files from this GitHub repo to your project directory (where your intended codebase will be).

2. **Modify Template Files**

   Edit `CLAUDE.md` to match your project. The `.claude/settings.json` file includes Terminal-Notifier for macOS notifications ([setup guide](https://github.com/centminmod/terminal-notifier-setup)). Remove this file if not using macOS.

3. **Initialize Memory Bank**

   After launching Claude Code in your project directory, run `/init` to analyze your codebase and populate memory bank files.

4. **Install Fast Tools (macOS)**

   ```bash
   brew install ripgrep fd jq
   ```

### 1.4 Optional Enhancements

- **Visual Studio Code**: Install [VS Code](https://code.visualstudio.com/) and the [Claude Code Extension](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code)
  - [Beginner YouTube guide](https://www.youtube.com/watch?v=rPITZvwyoMc)
  - [Additional guide](https://www.youtube.com/watch?v=P-5bWpUbO60)

- **GitHub Integration**: Set up Git for VS Code
  - [Git setup guide](https://www.youtube.com/watch?v=twsYxYaQikI)
  - [VS Code + Git tutorial](https://www.youtube.com/watch?v=z5jZ9lrSpqk)

- **Dev Container**: Run Claude Code, Codex GPT-5, Gemini CLI, and more in an isolated [VS Code dev container](https://claude-devcontainers.centminmod.com/) with full YOLO mode support.

- **Platform-Specific Docs**: If using Cloudflare/ClerkOS, keep `CLAUDE-cloudflare.md` or `CLAUDE-cloudflare-mini.md` and reference them in `CLAUDE.md`. For Convex database, use `CLAUDE-convex.md`.

### 1.5 Useful Learning Resources

- [Advent of Claude: 31 Days of Claude Code](https://adocomplete.com/advent-of-claude-2025/) by Ado Kukic (Anthropic)
- [Claude Code with Opus 4.5](https://www.youtube.com/watch?v=UVJXh57MgI0) by Alex Finn
- [Claude Code Overview](https://www.youtube.com/watch?v=Dekx_OzRwiI) by Matt Maher

---

## 2. Memory Bank System

### 2.1 What is Memory Bank?

The Memory Bank System is a structured set of markdown files that help Claude Code retain context across multiple chat sessions. Instead of starting fresh each time, Claude Code reads these files to understand your project's patterns, decisions, and current state.

### 2.2 Core Context Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Main entry point with project overview and AI guidance |
| `CLAUDE-activeContext.md` | Current session state, goals, and progress |
| `CLAUDE-patterns.md` | Established code patterns and conventions |
| `CLAUDE-decisions.md` | Architecture decisions and rationale (ADRs) |
| `CLAUDE-troubleshooting.md` | Common issues and proven solutions |
| `CLAUDE-config-variables.md` | Configuration variables reference |
| `CLAUDE-temp.md` | Temporary scratch pad (only read when referenced) |

### 2.3 Setting Up Memory Bank

1. Copy the template files from this repository to your project root
2. Run `/init` in Claude Code to analyze your codebase
3. Claude Code will populate the memory bank files based on your project

### 2.4 Updating Memory Bank

After completing significant work, ask Claude Code to update the memory bank:

```
update memory bank
```

### 2.5 Memory Bank Example Output

Here's what Claude Code's thinking looks like when updating the memory bank:

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

# INTERMEDIATE SECTION

---

## 3. Extending Claude Code

### 3.1 Plugin System

Claude Code supports plugins from both official and third-party marketplaces.

#### Official Anthropic Marketplace

Browse and install plugins from the [official marketplace](https://code.claude.com/docs/en/discover-plugins).

```bash
# Install a plugin
/plugin install plugin-name@claude-plugins-official

# Update marketplace
/plugin marketplace update claude-plugins-official
```

#### Recommended Official Plugins

| Plugin | Description | Install Command |
|--------|-------------|-----------------|
| [code-simplifier](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/code-simplifier) | Simplifies and refines code for clarity, consistency, and maintainability | `/plugin install code-simplifier` |
| [frontend-design](https://github.com/anthropics/claude-code/tree/main/plugins/frontend-design) | Creates distinctive, production-grade frontend interfaces | `/plugin install frontend-design@claude-code-plugins` |
| [feature-dev](https://github.com/anthropics/claude-code/tree/main/plugins/feature-dev) | Systematic 7-phase approach to building new features | `/plugin install feature-dev@claude-code-plugins` |
| [ralph-wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) | Interactive self-referential AI loops for iterative development | `/plugin install ralph-wiggum@claude-code-plugins` |

> **Note**: Ralph Wiggum may have issues on some systems. See [#16398](https://github.com/anthropics/claude-code/issues/16398) and [#16389](https://github.com/anthropics/claude-code/issues/16389). Usage guide: [YouTube by Greg Isenberg](https://www.youtube.com/watch?v=RpvQH0r0ecM) | [GitHub](https://github.com/snarktank/ralph)

#### Third-Party Marketplaces

| Plugin | Source | Description | Install Commands |
|--------|--------|-------------|------------------|
| [safety-net](https://github.com/kenryu42/claude-code-safety-net) | cc-marketplace | Catches destructive git/filesystem commands before execution | `/plugin marketplace add kenryu42/cc-marketplace`<br>`/plugin install safety-net@cc-marketplace` |
| [glm-plan-usage](https://docs.z.ai/devpack/extension/usage-query-plugin) | zai-coding-plugins | Query Z.AI usage statistics | `/plugin marketplace add zai/zai-coding-plugins`<br>`/plugin install glm-plan-usage@zai-coding-plugins` |

### 3.2 MCP Servers

MCP (Model Context Protocol) servers extend Claude Code's capabilities by connecting to external tools and documentation.

#### Recommended MCP Servers

| Server | Purpose | Transport | Token Cost | Install Command |
|--------|---------|-----------|------------|-----------------|
| [Context7](https://github.com/upstash/context7) | Documentation lookup for any library | SSE | Low | See below |
| [Cloudflare Docs](https://github.com/cloudflare/mcp-server-cloudflare/tree/main/apps/docs-vectorize) | Cloudflare documentation | SSE | Low | See below |
| [Usage Metrics](https://github.com/centminmod/claude-code-opentelemetry-setup) | Claude Code usage and cost tracking | stdio | Low | See below |
| [Gemini CLI](https://github.com/centminmod/gemini-cli-mcp-server) | Access to Gemini models | stdio | Variable | See below |
| [Notion](https://github.com/makenotion/notion-mcp-server) | Notion workspace integration | stdio | Variable | See below |
| [Chrome DevTools](https://github.com/ChromeDevTools/chrome-devtools-mcp) | Browser automation & debugging | stdio | ~17K tokens | See below |

#### Installation Commands

**Context7 MCP** (with API key):
```bash
claude mcp add --transport http context7 https://mcp.context7.com/mcp --header "CONTEXT7_API_KEY: YOUR_API_KEY" -s user
```

**Cloudflare Documentation MCP**:
```bash
claude mcp add --transport sse cf-docs https://docs.mcp.cloudflare.com/sse -s user
```

**Usage Metrics MCP**:
```bash
claude mcp add --transport stdio metrics -s user -- uv run --directory /path/to/your/mcp-server metrics-server
```

**Gemini CLI MCP**:
```bash
claude mcp add gemini-cli /path/to/.venv/bin/python /path/to/mcp_server.py -s user -e GEMINI_API_KEY='YOUR_KEY' -e OPENROUTER_API_KEY='YOUR_KEY'
```

**Notion MCP**:
```bash
claude mcp add-json notionApi '{"type":"stdio","command":"npx","args":["-y","@notionhq/notion-mcp-server"],"env":{"OPENAPI_MCP_HEADERS":"{\"Authorization\": \"Bearer ntn_API_KEY\", \"Notion-Version\": \"2022-06-28\"}"}}' -s user
```

**Chrome DevTools MCP** (high token cost - use on-demand):

Due to the ~17K token overhead across 26 tools, install only when needed via `--mcp-config`:

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

#### Verify MCP Servers

```bash
claude mcp list
# Output:
# context7: https://mcp.context7.com/sse (SSE) - ✓ Connected
# cf-docs: https://docs.mcp.cloudflare.com/sse (SSE) - ✓ Connected
# metrics: uv run --directory /path/to/mcp-server metrics-server - ✓ Connected
```

#### Usage Metrics Example

The `get_current_cost` MCP tool returns today's total USD cost:
```json
{
  "metric": "Total Cost Today",
  "value": 27.149809833783127,
  "formatted": "$27.1498",
  "unit": "currencyUSD"
}
```

---

## 4. Development Workflows

### 4.1 Git Worktrees for Parallel Sessions

Git worktrees allow you to run parallel Claude Code sessions with complete code isolation. Each worktree has its own working directory while sharing Git history.

**Benefits:**
- Run multiple AI coding sessions in parallel
- Each worktree has independent file state
- Changes in one worktree won't affect others
- Ideal for experimental features or YOLO mode

**Official Documentation:** [Run parallel Claude Code sessions with git worktrees](https://code.claude.com/docs/en/common-workflows#run-parallel-claude-code-sessions-with-git-worktrees)

#### macOS / Linux Shell Functions

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

After adding, reload: `source ~/.bashrc` or `source ~/.zshrc`

<details>
<summary><strong>Windows PowerShell Functions</strong></summary>

Add to your PowerShell profile (`notepad $PROFILE`):

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

Create in a directory in your PATH (e.g., `C:\Users\YourName\bin\`):

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

#### Usage

```bash
# Create worktree with custom name
clx feature-auth
cx bugfix-123

# Create worktree with auto-generated timestamp name
clx
cx
```

#### Worktree Management

```bash
# List all worktrees
git worktree list

# Remove a worktree when done
git worktree remove ../worktree-name

# Clean up stale worktree references
git worktree prune
```

#### Environment Setup

Each new worktree needs its own development environment:
- **JavaScript/Node.js**: Run `npm install` or `yarn`
- **Python**: Create virtual environment or run `pip install -r requirements.txt`
- **Other languages**: Follow your project's standard setup process

#### The .worktreeinclude File

When Claude Code creates a worktree, files ignored via `.gitignore` aren't automatically available. The `.worktreeinclude` file specifies which ignored files should be copied.

**How It Works:**
- Uses `.gitignore`-style patterns
- Only files matched by **both** `.worktreeinclude` **AND** `.gitignore` are copied

Create `.worktreeinclude` in your repository root:
```text
# Environment files
.env
.env.local
.env.*

# Claude Code local settings
**/.claude/settings.local.json
```

**Common Use Cases:**
- `.env` files with API keys and secrets
- `.env.local` for local development overrides
- `.claude/settings.local.json` for personal Claude Code settings

#### Claude Desktop Worktree Location

When using Claude Code via the Claude Desktop app:
- Default location: `~/.claude-worktrees`
- Configurable through Claude Desktop app settings
- Repository must be Git initialized for worktree sessions

**Official Documentation:** [Claude Code on Desktop](https://code.claude.com/docs/en/desktop#claude-code-on-desktop-preview)

#### Local Ignores Without .gitignore

Use `.git/info/exclude` to ignore files locally without modifying shared `.gitignore`:

```bash
# Edit the local exclude file
nano .git/info/exclude
```

Add patterns:
```text
# Local IDE settings
.idea/
*.swp

# Personal scripts
my-local-scripts/
```

| File | Scope | Committed to Git |
|------|-------|------------------|
| `.gitignore` | Shared with team | Yes |
| `.git/info/exclude` | Local only | No |
| `~/.config/git/ignore` | Global (all repos) | No |

### 4.2 Status Lines

Configure custom status lines in `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statuslines/statusline.sh",
    "padding": 0
  }
}
```

#### Example Status Line Script

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

# Format tokens as Xk
format_tokens() {
    local num="$1"
    if [ "$num" -ge 1000 ]; then
        echo "$((num / 1000))k"
    else
        echo "$num"
    fi
}

# Calculate total
TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS))

# Show git branch if in a git repo
GIT_BRANCH=""
if git rev-parse --git-dir > /dev/null 2>&1; then
    BRANCH=$(git branch --show-current 2>/dev/null)
    if [ -n "$BRANCH" ]; then
        GIT_BRANCH=" | 🌿 $BRANCH"
    fi
fi

echo "[$MODEL_DISPLAY] 📁 ${CURRENT_DIR##*/}${GIT_BRANCH}
Tokens: $(format_tokens "$TOTAL_TOKENS") (in:$(format_tokens "$INPUT_TOKENS")+out:$(format_tokens "$OUTPUT_TOKENS")) | Ctx:$(format_tokens "$CONTEXT_SIZE")
Cost: \$${COST_USD} | +${LINES_ADDED} -${LINES_REMOVED} lines"
```

### 4.3 IDE Integration

- **VS Code Extension**: [Claude Code for VS Code](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code)
- **Dev Containers**: [Isolated dev environment](https://claude-devcontainers.centminmod.com/) with Claude Code, Codex CLI, Gemini CLI, and YOLO mode support

---

# ADVANCED SECTION

---

## 5. Customization

### 5.1 Custom Subagents

Subagents are specialized tools that handle complex, multi-step tasks autonomously with their own context window and custom prompts. Learn more in the [official documentation](https://docs.anthropic.com/en/docs/claude-code/sub-agents).

#### Included Subagents

| Agent | Location | Purpose |
|-------|----------|---------|
| **memory-bank-synchronizer** | `.claude/agents/` | Synchronizes memory bank documentation with codebase state |
| **code-searcher** | `.claude/agents/` | Efficient codebase navigation with optional Chain of Draft mode |
| **get-current-datetime** | `.claude/agents/` | Accurate Brisbane timezone (GMT+10) values |
| **ux-design-expert** | `.claude/agents/` | Comprehensive UX/UI design guidance with Tailwind CSS & Highcharts |

#### memory-bank-synchronizer

Proactively maintains consistency between CLAUDE-*.md files and source code:
- Pattern documentation synchronization
- Architecture decision updates
- Technical specification alignment
- Implementation status tracking

#### code-searcher

Efficiently searches the codebase with two modes:
- **Standard mode**: Full detailed analysis
- **CoD mode**: ~80% fewer tokens with ultra-concise responses

```
# Standard: "Find the payment processing code"
# CoD: "Find the payment processing code using CoD"
```

#### get-current-datetime

Returns accurate Brisbane, Australia (GMT+10) timestamps:
- Supports multiple formats (default, filename, readable, ISO)
- Eliminates timezone confusion

#### ux-design-expert

Comprehensive UX/UI guidance:
- UX flow optimization
- Premium UI design with Tailwind CSS
- Data visualization with Highcharts
- Accessibility compliance

### 5.2 Custom Skills

Skills provide specialized capabilities. See [Agent Skills documentation](https://docs.claude.com/en/docs/claude-code/skills).

#### Included Skills

| Skill | Purpose | Invocation |
|-------|---------|------------|
| **claude-docs-consultant** | Selectively fetches official Claude Code documentation from docs.claude.com | Automatic when working on Claude Code features |

### 5.3 Custom Slash Commands

#### `/anthropic` Commands

| Command | Purpose |
|---------|---------|
| `/apply-thinking-to` | Applies Anthropic's extended thinking patterns to enhance prompts |
| `/convert-to-todowrite-tasklist-prompt` | Converts prompts to TodoWrite tasklist methods (60-70% speed improvement) |
| `/update-memory-bank` | Updates CLAUDE.md and memory bank files |

#### `/ccusage` Commands

| Command | Purpose |
|---------|---------|
| `/ccusage-daily` | Generates comprehensive usage cost analysis with daily breakdowns |

#### `/cleanup` Commands

| Command | Purpose |
|---------|---------|
| `/cleanup-context` | Memory bank optimization (15-25% token reduction) |

#### `/documentation` Commands

| Command | Purpose |
|---------|---------|
| `/create-readme-section` | Generates README sections with professional formatting |
| `/create-release-note` | Creates dual release notes (customer-facing + technical) |

#### `/security` Commands

| Command | Purpose |
|---------|---------|
| `/security-audit` | Comprehensive security audit using OWASP guidelines |
| `/check-best-practices` | Analyzes code against language-specific best practices |
| `/secure-prompts` | Detects prompt injection attacks and malicious instructions |

Example test prompts at `.claude/commands/security/test-examples/`

#### `/architecture` Commands

| Command | Purpose |
|---------|---------|
| `/explain-architecture-pattern` | Identifies and explains architectural patterns |

#### `/promptengineering` Commands

| Command | Purpose |
|---------|---------|
| `/convert-to-test-driven-prompt` | Transforms requests into TDD-style prompts |
| `/batch-operations-prompt` | Optimizes prompts for parallel processing |

#### `/refactor` Commands

| Command | Purpose |
|---------|---------|
| `/refactor-code` | Creates detailed refactoring plans with risk assessment |

### 5.4 Hooks System

Hooks run custom commands before or after tool execution.

#### Included Hooks

The `STOP` hook uses Terminal-Notifier for macOS desktop notifications when Claude Code completes a response. Setup: [Terminal-Notifier](https://github.com/centminmod/terminal-notifier-setup)

---

## 6. Alternative Providers

### 6.1 Using Z.AI with Claude Code

[Z.AI's GLM Coding Plan](https://z.ai) provides cost-effective access to high-performance language models optimized for coding.

> **10% Discount**: Use invite code [`WWB8IFLROM`](https://z.ai/subscribe?ic=WWB8IFLROM)

#### Overview

- **Performance**: 55+ tokens/second for real-time interaction
- **Features**: Vision Understanding, Web Search, Web Reader MCP servers
- **Multimodal**: GLM-4.7 with state-of-the-art reasoning capabilities

#### Pricing & Plans

| Plan | Prompts/5hrs | Approx. Monthly Cost | vs Claude |
|------|--------------|---------------------|-----------|
| Lite | ~120 | ~$3 | 3× Claude Pro quota |
| Pro | ~600 | Higher | 3× Claude Max 5x quota |
| Max | ~2,400 | Higher | 3× Claude Max 20x quota |

Each prompt allows 15–20 model calls, yielding billions of tokens monthly at ~1% of standard API pricing.

#### Privacy & Data Handling

- **Data Location**: Singapore
- **Privacy Guarantee**: Z.AI does not store any content you provide or generate
- See [Privacy Policy](https://docs.z.ai/legal-agreement/privacy-policy)

#### Prerequisites

- Node.js 18+
- Z.AI API key from [Z.AI dashboard](https://z.ai)
- [Official documentation](https://docs.z.ai/devpack/tool/claude)

#### Setup Instructions

**Option 1: Automated Setup** (macOS/Linux only)

```bash
curl -O "https://cdn.bigmodel.cn/install/claude_code_zai_env.sh" && bash ./claude_code_zai_env.sh
```

**Option 2: Manual Configuration**

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

#### Shell Function Launchers

The easiest way to use Z.AI without affecting your existing Claude Code setup.

**macOS / Linux (Bash/Zsh)**

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

Create `zai.bat` in a directory in your PATH:

```batch
@echo off
set ANTHROPIC_AUTH_TOKEN=your-zai-api-key
set ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
set API_TIMEOUT_MS=3000000
claude %*
```

</details>

#### Model Mapping

GLM Coding Plan maps Claude model names to GLM models:

| Claude Model | GLM Model |
|--------------|-----------|
| Opus | GLM-4.7 |
| Sonnet | GLM-4.7 |
| Haiku | GLM-4.5-Air |

**Customizing Model Mappings** (optional):

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
<summary><strong>Windows PowerShell Model Mapping</strong></summary>

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
<summary><strong>Windows CMD Model Mapping</strong></summary>

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

#### Usage

```bash
# Launch with Z.AI configuration
zai

# Launch with specific model
zai --model sonnet

# Launch with permission mode
zai --model opus --permission-mode plan
```

#### Z.AI + Git Worktree Integration

Combine Z.AI with git worktrees for isolated parallel sessions.

**macOS / Linux (Bash/Zsh)**

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

**Usage:**
```bash
# Create worktree with custom name
zaix feature-auth

# Create worktree with auto-generated timestamp name
zaix
```

---

## 7. Cost & Rate Management

### 7.1 Claude Plan Weekly Rate Limits

From August 28, 2025, weekly rate limits apply in addition to monthly 50x 5hr session limits:

| Plan | Sonnet 4 (hrs/week) | Opus 4 (hrs/week) |
|------|---------------------|-------------------|
| Pro | 40–80 | – |
| Max ($100/mo) | 140–280 | 15–35 |
| Max ($200/mo) | 240–480 | 24–40 |

### 7.2 Cost Tracking

Use the Usage Metrics MCP server to track costs:
```bash
claude mcp add --transport stdio metrics -s user -- uv run --directory /path/to/mcp-server metrics-server
```

Or use the `/ccusage-daily` slash command for detailed cost analysis.

### 7.3 Optimization Tips

- Use **Z.AI** for higher quotas at lower cost
- Configure **status lines** to monitor real-time usage
- Use **git worktrees** for parallel sessions without duplicating quota
- Leverage **CoD mode** in code-searcher for 80% token reduction

---

# REFERENCE SECTION

---

## 8. Configuration Reference

### 8.1 Settings Scopes

| Scope | Location | Affects | Shared? |
|-------|----------|---------|---------|
| Managed | System directories | All users | By IT |
| User | `~/.claude/settings.json` | You (all projects) | No |
| Project | `.claude/settings.json` | All collaborators | Yes |
| Local | `.claude/settings.local.json` | You (this project) | No |

**Precedence** (highest to lowest):
1. Enterprise policies
2. Command line arguments
3. Local project settings
4. Shared project settings
5. User settings

### 8.2 settings.json Options

| Key | Description | Example |
|-----|-------------|---------|
| `apiKeyHelper` | Script to generate auth value | `/bin/generate_temp_api_key.sh` |
| `cleanupPeriodDays` | Days to retain chat transcripts (default: 30) | `20` |
| `env` | Environment variables for every session | `{"FOO": "bar"}` |
| `includeCoAuthoredBy` | Include `co-authored-by Claude` in commits | `false` |
| `permissions` | Permission rules (see below) | |

#### Permission Settings

| Key | Description | Example |
|-----|-------------|---------|
| `allow` | Array of allowed tool use rules | `["Bash(git diff:*)"]` |
| `deny` | Array of denied tool use rules | `["WebFetch", "Bash(curl:*)"]` |
| `additionalDirectories` | Additional working directories | `["../docs/"]` |
| `defaultMode` | Default permission mode | `"acceptEdits"` |
| `disableBypassPermissionsMode` | Prevent bypass mode | `"disable"` |

### 8.3 Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | API key for Claude SDK |
| `ANTHROPIC_AUTH_TOKEN` | Custom auth header value |
| `ANTHROPIC_BASE_URL` | Custom API endpoint |
| `ANTHROPIC_MODEL` | Custom model name |
| `ANTHROPIC_SMALL_FAST_MODEL` | Haiku-class model for background tasks |
| `BASH_DEFAULT_TIMEOUT_MS` | Default bash command timeout |
| `BASH_MAX_TIMEOUT_MS` | Maximum bash command timeout |
| `BASH_MAX_OUTPUT_LENGTH` | Max characters before truncation |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Max output tokens per request |
| `CLAUDE_CODE_USE_BEDROCK` | Use Amazon Bedrock |
| `CLAUDE_CODE_USE_VERTEX` | Use Google Vertex AI |
| `DISABLE_AUTOUPDATER` | Disable automatic updates |
| `DISABLE_TELEMETRY` | Opt out of Statsig telemetry |
| `HTTP_PROXY` / `HTTPS_PROXY` | Proxy server settings |
| `MAX_THINKING_TOKENS` | Force thinking budget |
| `MCP_TIMEOUT` | MCP server startup timeout |
| `MCP_TOOL_TIMEOUT` | MCP tool execution timeout |
| `MAX_MCP_OUTPUT_TOKENS` | Max MCP response tokens (default: 25000) |

### 8.4 File Locations by OS

| File | macOS | Linux | Windows |
|------|-------|-------|---------|
| User settings | `~/.claude/settings.json` | `~/.claude/settings.json` | `%USERPROFILE%\.claude\settings.json` |
| Project settings | `.claude/settings.json` | `.claude/settings.json` | `.claude\settings.json` |
| Local settings | `.claude/settings.local.json` | `.claude/settings.local.json` | `.claude\settings.local.json` |

### 8.5 Tools Available to Claude

| Tool | Description | Permission Required |
|------|-------------|---------------------|
| Agent | Runs sub-agents for complex tasks | No |
| Bash | Executes shell commands | Yes |
| Edit | Makes targeted file edits | Yes |
| Glob | Finds files by pattern | No |
| Grep | Searches file contents | No |
| LS | Lists files and directories | No |
| MultiEdit | Multiple edits atomically | Yes |
| NotebookEdit | Modifies Jupyter cells | Yes |
| NotebookRead | Reads Jupyter notebooks | No |
| Read | Reads file contents | No |
| TodoRead | Reads task list | No |
| TodoWrite | Creates/manages task lists | No |
| WebFetch | Fetches URL content | Yes |
| WebSearch | Performs web searches | Yes |
| Write | Creates/overwrites files | Yes |

### 8.6 Configuration Commands

```bash
# List settings
claude config list

# Get a setting
claude config get <key>

# Set a setting
claude config set <key> <value>

# Add to a list setting
claude config add <key> <value>

# Remove from a list setting
claude config remove <key> <value>

# Global configuration
claude config set -g <key> <value>
```

#### Global Configuration Options

| Key | Description | Example |
|-----|-------------|---------|
| `autoUpdates` | Enable automatic updates (default: true) | `false` |
| `preferredNotifChannel` | Notification method | `iterm2`, `terminal_bell`, `notifications_disabled` |
| `theme` | Color theme | `dark`, `light`, `light-daltonized`, `dark-daltonized` |
| `verbose` | Show full command outputs | `true` |

---

## 9. Resources

### Official Documentation

- [Claude Code Overview](https://docs.anthropic.com/en/docs/claude-code/overview)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)
- [Claude Code Hooks](https://code.claude.com/docs/en/hooks)
- [Claude Code Skills](https://docs.claude.com/en/docs/claude-code/skills)
- [Claude Code Sub-agents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)
- [Plugin Marketplace](https://code.claude.com/docs/en/discover-plugins)

### YouTube Guides

- [Advent of Claude: 31 Days of Claude Code](https://adocomplete.com/advent-of-claude-2025/) - Ado Kukic (Anthropic)
- [Claude Code with Opus 4.5](https://www.youtube.com/watch?v=UVJXh57MgI0) - Alex Finn
- [Claude Code Overview](https://www.youtube.com/watch?v=Dekx_OzRwiI) - Matt Maher
- [VS Code Beginner Guide](https://www.youtube.com/watch?v=rPITZvwyoMc)
- [Ralph Wiggum Tutorial](https://www.youtube.com/watch?v=RpvQH0r0ecM) - Greg Isenberg & Ryan Carson

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=centminmod/my-claude-code-setup&type=Date)](https://www.star-history.com/#centminmod/my-claude-code-setup&Date)

---

## Stats

![Alt](https://repobeats.axiom.co/api/embed/715da1679915da77d87deb99a1f527a44e76ec60.svg "Repobeats analytics image")
