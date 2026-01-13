[![GitHub stars](https://img.shields.io/github/stars/centminmod/my-claude-code-setup.svg?style=flat-square)](https://github.com/centminmod/my-claude-code-setup/stargazers) [![GitHub forks](https://img.shields.io/github/forks/centminmod/my-claude-code-setup.svg?style=flat-square)](https://github.com/centminmod/my-claude-code-setup/network) [![GitHub issues](https://img.shields.io/github/issues/centminmod/my-claude-code-setup.svg?style=flat-square)](https://github.com/centminmod/my-claude-code-setup/issues)

* Threads - https://www.threads.com/@george_sl_liu
* BlueSky - https://bsky.app/profile/georgesl.bsky.social

# My Claude Code Setup

## What This Repository Provides

- **Starter Settings** for Claude Code projects with optimized configurations
- **Memory Bank System** for context retention across chat sessions
- **Pre-configured Hooks, Skills, and Subagents** for enhanced productivity
- **MCP Server Recommendations** for extending Claude Code capabilities

## Quick Navigation

| What do you want to do? | Jump to |
|------------------------|---------|
| Install & get started | [Getting Started](#getting-started) |
| Set up persistent memory | [Memory Bank System](#i-want-to-set-up-the-memory-bank-system) |
| Add plugins to Claude Code | [Plugins](#i-want-to-extend-claude-code-with-plugins) |
| Connect external tools | [MCP Servers](#i-want-to-connect-external-tools-mcp) |
| Run parallel AI sessions | [Git Worktrees](#i-want-to-run-parallel-ai-coding-sessions) |
| Customize Claude's behavior | [Customization](#i-want-to-customize-claudes-behavior) |
| Use Z.AI for higher quotas | [Z.AI Integration](#i-want-to-use-zai-for-higher-quotas) |
| Monitor costs and usage | [Costs & Usage](#i-want-to-monitor-costs-and-usage) |
| Look up settings/config | [Configuration Reference](#configuration-reference) |

---

## Getting Started

### Prerequisites

| Requirement | Notes |
|------------|-------|
| [Claude AI Account](https://claude.ai/) | Pro ($20/mo), Max ($100/mo), or Max ($200/mo) |
| Node.js 18+ | Runtime environment |
| Git | Version control |
| ripgrep, fd, jq | Fast tools (macOS: `brew install ripgrep fd jq`) |

### Installation Options

Choose the approach that works best for you:

#### Option A: Clone Entire Repository (New Projects)

```bash
# 1. Clone this repository as your new project
git clone https://github.com/centminmod/my-claude-code-setup.git my-project
cd my-project

# 2. Remove template README files (create your own)
rm README.md README-v2.md README-v3.md README-v4.md

# 3. Reinitialize git for your own project (optional)
rm -rf .git
git init

# 4. Launch Claude Code and initialize
claude
# Then run: /init
```

#### Option B: Selective Copy (Existing Projects)

Copy only what you need into your existing project:

```bash
# Core files (recommended)
cp /path/to/my-claude-code-setup/CLAUDE.md your-project/
cp -r /path/to/my-claude-code-setup/.claude your-project/

# Or pick specific components:
cp -r /path/to/my-claude-code-setup/.claude/commands your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/skills your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/agents your-project/.claude/
cp -r /path/to/my-claude-code-setup/.claude/hooks your-project/.claude/
```

#### Option C: Download from GitHub

Browse the repository and download individual files:
- `CLAUDE.md` - Memory bank main file
- `.claude/settings.json` - Settings template
- `.claude/commands/` - Slash commands
- `.claude/skills/` - Skills
- `.claude/agents/` - Subagents

### What Happens Next?

1. Claude Code analyzes your codebase
2. Memory bank files are populated based on your project
3. You're ready to start coding with persistent context!

### Optional Enhancements

- **VS Code Integration**: Install [Claude Code Extension](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code)
- **GitHub Setup**: Configure Git for VS Code ([guide](https://www.youtube.com/watch?v=twsYxYaQikI))
- **Dev Container**: Use the [isolated dev environment](https://claude-devcontainers.centminmod.com/) for YOLO mode
- **Platform Docs**: Add `CLAUDE-cloudflare.md` for Cloudflare/ClerkOS or `CLAUDE-convex.md` for Convex

### Learning Resources

- [Advent of Claude: 31 Days](https://adocomplete.com/advent-of-claude-2025/) by Ado Kukic (Anthropic)
- [Claude Code with Opus 4.5](https://www.youtube.com/watch?v=UVJXh57MgI0) by Alex Finn
- [Claude Code Overview](https://www.youtube.com/watch?v=Dekx_OzRwiI) by Matt Maher

---

## I want to set up the memory bank system

### What is Memory Bank?

The Memory Bank System helps Claude Code remember context across chat sessions. Instead of starting fresh each time, Claude reads structured markdown files to understand your project's patterns, decisions, and current state.

### Core Context Files

| File | What it stores |
|------|---------------|
| `CLAUDE.md` | Main entry point with project overview and AI guidance |
| `CLAUDE-activeContext.md` | Current session state, goals, and progress |
| `CLAUDE-patterns.md` | Established code patterns and conventions |
| `CLAUDE-decisions.md` | Architecture decisions and rationale (ADRs) |
| `CLAUDE-troubleshooting.md` | Common issues and proven solutions |
| `CLAUDE-config-variables.md` | Configuration variables reference |
| `CLAUDE-temp.md` | Temporary scratch pad (only read when referenced) |

### Initial Setup

1. Copy template files from this repository to your project root
2. Run `/init` in Claude Code
3. Claude analyzes your codebase and populates the memory bank

### Updating Memory Bank

After completing significant work:

```
update memory bank
```

Claude Code will update all relevant CLAUDE-*.md files with your latest changes.

### Example Output

```
> update memory bank

∴ Thinking…
  I'll update the memory bank files to reflect the v0.1.6 changes...

⏺ Summary: v0.1.6 Release Complete ✅

  Memory Bank Updates Complete:
  - CLAUDE-activeContext.md - v0.1.6 session context
  - CLAUDE-patterns.md - Added patterns 22-24
  - CLAUDE-decisions.md - Added ADR-017 & ADR-018
  - CLAUDE-troubleshooting.md - Added 4 new issue/fix entries

  Test Results: All 29 tests passing
```

> **See also:** [Customization](#i-want-to-customize-claudes-behavior) for creating custom subagents that sync memory bank with code

---

## I want to extend Claude Code with plugins

### Official Anthropic Marketplace

Browse plugins at the [official marketplace](https://code.claude.com/docs/en/discover-plugins).

```bash
# Install a plugin
/plugin install plugin-name@claude-plugins-official

# Update marketplace
/plugin marketplace update claude-plugins-official
```

### Recommended Plugins

| Plugin | What it does | Install |
|--------|-------------|---------|
| [code-simplifier](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/code-simplifier) | Simplifies code for clarity and maintainability | `/plugin install code-simplifier` |
| [frontend-design](https://github.com/anthropics/claude-code/tree/main/plugins/frontend-design) | Creates production-grade frontend interfaces | `/plugin install frontend-design@claude-code-plugins` |
| [feature-dev](https://github.com/anthropics/claude-code/tree/main/plugins/feature-dev) | 7-phase approach to building features | `/plugin install feature-dev@claude-code-plugins` |
| [ralph-wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) | Iterative AI loops for development | `/plugin install ralph-wiggum@claude-code-plugins` |

> **Note**: Ralph Wiggum has issues on some systems ([#16398](https://github.com/anthropics/claude-code/issues/16398), [#16389](https://github.com/anthropics/claude-code/issues/16389)). [Usage video](https://www.youtube.com/watch?v=RpvQH0r0ecM)

### Third-Party Plugins

**Safety Net** - Catches destructive commands before execution:
```bash
/plugin marketplace add kenryu42/cc-marketplace
/plugin install safety-net@cc-marketplace
```

**Z.AI Usage Query** - Query Z.AI usage statistics:
```bash
/plugin marketplace add zai/zai-coding-plugins
/plugin install glm-plan-usage@zai-coding-plugins
```

> **See also:** [MCP Servers](#i-want-to-connect-external-tools-mcp) for connecting external tools

---

## I want to connect external tools (MCP)

### What is MCP?

MCP (Model Context Protocol) servers extend Claude Code by connecting to external tools, documentation, and services.

### Recommended MCP Servers

| Server | What it does | Install |
|--------|-------------|---------|
| [Context7](https://github.com/upstash/context7) | Look up docs for any library | `claude mcp add --transport http context7 https://mcp.context7.com/mcp --header "CONTEXT7_API_KEY: YOUR_KEY" -s user` |
| [Cloudflare Docs](https://github.com/cloudflare/mcp-server-cloudflare/tree/main/apps/docs-vectorize) | Cloudflare documentation | `claude mcp add --transport sse cf-docs https://docs.mcp.cloudflare.com/sse -s user` |
| [Usage Metrics](https://github.com/centminmod/claude-code-opentelemetry-setup) | Track Claude Code costs | `claude mcp add --transport stdio metrics -s user -- uv run --directory /path/to/mcp-server metrics-server` |
| [Gemini CLI](https://github.com/centminmod/gemini-cli-mcp-server) | Access Gemini models | `claude mcp add gemini-cli /path/to/.venv/bin/python /path/to/mcp_server.py -s user -e GEMINI_API_KEY='KEY'` |
| [Notion](https://github.com/makenotion/notion-mcp-server) | Notion workspace integration | See below |

### Installing Notion MCP

```bash
claude mcp add-json notionApi '{"type":"stdio","command":"npx","args":["-y","@notionhq/notion-mcp-server"],"env":{"OPENAPI_MCP_HEADERS":"{\"Authorization\": \"Bearer ntn_API_KEY\", \"Notion-Version\": \"2022-06-28\"}"}}' -s user
```

### Chrome DevTools MCP (On-Demand)

Due to ~17K token overhead, install only when needed:

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

### Verify Installation

```bash
claude mcp list
# context7: ✓ Connected
# cf-docs: ✓ Connected
# metrics: ✓ Connected
```

### Example: Cost Tracking

The `get_current_cost` tool returns:
```json
{
  "metric": "Total Cost Today",
  "formatted": "$27.15",
  "unit": "currencyUSD"
}
```

> **See also:** [Plugins](#i-want-to-extend-claude-code-with-plugins) for the official plugin system

---

## I want to run parallel AI coding sessions

### Why Git Worktrees?

Git worktrees let you run multiple Claude Code sessions with complete code isolation. Each worktree has its own working directory while sharing Git history.

**Benefits:**
- Run parallel AI sessions simultaneously
- Each worktree has independent file state
- Changes won't interfere between sessions
- Perfect for experimental features or YOLO mode

### Setup Shell Functions

**macOS / Linux** - Add to `~/.bashrc` or `~/.zshrc`:

```bash
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
```

Reload: `source ~/.bashrc` or `source ~/.zshrc`

<details>
<summary><strong>Windows PowerShell</strong></summary>

Add to PowerShell profile (`notepad $PROFILE`):

```powershell
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
```

Reload: `. $PROFILE`

</details>

<details>
<summary><strong>Windows CMD Batch</strong></summary>

Create `clx.bat` in a PATH directory:

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

Create `cx.bat` similarly for Codex CLI.

</details>

### Usage

```bash
# Named worktree
clx feature-auth
cx bugfix-123

# Auto-generated timestamp name
clx
cx
```

### Managing Worktrees

```bash
git worktree list          # List all worktrees
git worktree remove ../name # Remove a worktree
git worktree prune         # Clean up stale references
```

### Environment Setup

Each worktree needs its own dependencies:
- **Node.js**: `npm install` or `yarn`
- **Python**: `pip install -r requirements.txt`

### The .worktreeinclude File

Specify which `.gitignore`d files to copy to new worktrees:

```text
# Environment files
.env
.env.local
.env.*

# Claude Code local settings
**/.claude/settings.local.json
```

### Claude Desktop Worktree Location

- Default: `~/.claude-worktrees`
- Configurable in Claude Desktop settings
- Repository must be Git initialized

### Local Ignores Without .gitignore

Use `.git/info/exclude` for local-only ignores:

```text
.idea/
my-local-scripts/
```

| File | Scope | Shared |
|------|-------|--------|
| `.gitignore` | Team | Yes |
| `.git/info/exclude` | Local | No |
| `~/.config/git/ignore` | Global | No |

> **See also:** [Z.AI + Worktrees](#zai--git-worktree-integration) for combining Z.AI with worktrees

---

## I want to customize Claude's behavior

### Custom Slash Commands

#### `/anthropic` Commands

| Command | What it does |
|---------|-------------|
| `/apply-thinking-to` | Enhances prompts with Anthropic's extended thinking patterns |
| `/convert-to-todowrite-tasklist-prompt` | Converts prompts to parallel task execution (60-70% faster) |
| `/update-memory-bank` | Updates CLAUDE.md and memory bank files |

#### `/ccusage` Commands

| Command | What it does |
|---------|-------------|
| `/ccusage-daily` | Comprehensive usage cost analysis with daily breakdowns |

#### `/cleanup` Commands

| Command | What it does |
|---------|-------------|
| `/cleanup-context` | Memory bank optimization (15-25% token reduction) |

#### `/documentation` Commands

| Command | What it does |
|---------|-------------|
| `/create-readme-section` | Generates README sections with professional formatting |
| `/create-release-note` | Creates dual release notes (customer-facing + technical) |

#### `/security` Commands

| Command | What it does |
|---------|-------------|
| `/security-audit` | OWASP-based security audit |
| `/check-best-practices` | Language-specific best practices analysis |
| `/secure-prompts` | Detects prompt injection attacks |

Test prompts available at `.claude/commands/security/test-examples/`

#### `/architecture` Commands

| Command | What it does |
|---------|-------------|
| `/explain-architecture-pattern` | Identifies and explains architectural patterns |

#### `/promptengineering` Commands

| Command | What it does |
|---------|-------------|
| `/convert-to-test-driven-prompt` | Transforms requests into TDD-style prompts |
| `/batch-operations-prompt` | Optimizes for parallel file operations |

#### `/refactor` Commands

| Command | What it does |
|---------|-------------|
| `/refactor-code` | Creates detailed refactoring plans with risk assessment |

### Custom Skills

Skills provide specialized capabilities. See [official docs](https://docs.claude.com/en/docs/claude-code/skills).

| Skill | What it does |
|-------|-------------|
| **claude-docs-consultant** | Selectively fetches official Claude Code documentation |
| **consult-zai** | Dual-AI consultation comparing z.ai GLM 4.7 and code-searcher responses |
| **consult-codex** | Dual-AI consultation comparing Codex GPT-5.2 and code-searcher responses |

### Custom Subagents

Subagents handle complex tasks autonomously with their own context window. See [official docs](https://docs.anthropic.com/en/docs/claude-code/sub-agents).

| Agent | What it does |
|-------|-------------|
| **memory-bank-synchronizer** | Keeps memory bank in sync with codebase |
| **code-searcher** | Efficient codebase search with optional CoD mode (80% fewer tokens) |
| **get-current-datetime** | Accurate Brisbane timezone (GMT+10) timestamps |
| **ux-design-expert** | Comprehensive UX/UI guidance with Tailwind CSS & Highcharts |
| **zai-cli** | CLI wrapper for z.ai GLM 4.7 (used by consult-zai skill) |
| **codex-cli** | CLI wrapper for Codex GPT-5.2 (used by consult-codex skill) |

### Hooks

Hooks run custom commands before/after tool execution.

**Included Hook:** `STOP` notification using Terminal-Notifier for macOS desktop notifications. Setup: [Terminal-Notifier](https://github.com/centminmod/terminal-notifier-setup)

> **See also:** [Configuration Reference](#configuration-reference) for all settings options

---

## I want to use Z.AI for higher quotas

### What is Z.AI?

[Z.AI's GLM Coding Plan](https://z.ai) provides cost-effective access to high-performance GLM models optimized for coding, with significantly higher quotas than standard Claude plans.

> **10% Discount**: Use invite code [`WWB8IFLROM`](https://z.ai/subscribe?ic=WWB8IFLROM)

### Pricing & Plans

| Plan | Prompts/5hrs | Monthly Cost | vs Claude |
|------|--------------|--------------|-----------|
| Lite | ~120 | ~$3 | 3× Claude Pro quota |
| Pro | ~600 | Higher | 3× Claude Max 5x quota |
| Max | ~2,400 | Higher | 3× Claude Max 20x quota |

Each prompt allows 15–20 model calls = billions of tokens monthly at ~1% of API pricing.

### Privacy

- **Data Location**: Singapore
- **Privacy Guarantee**: Z.AI does not store any content you provide
- [Privacy Policy](https://docs.z.ai/legal-agreement/privacy-policy)

### Prerequisites

- Node.js 18+
- Z.AI API key from [dashboard](https://z.ai)
- [Official docs](https://docs.z.ai/devpack/tool/claude)

### Setup Options

**Option 1: Automated** (macOS/Linux only)
```bash
curl -O "https://cdn.bigmodel.cn/install/claude_code_zai_env.sh" && bash ./claude_code_zai_env.sh
```

**Option 2: Manual** - Edit `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-zai-api-key",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "API_TIMEOUT_MS": "3000000"
  }
}
```

### Shell Function Launcher (Recommended)

Use Z.AI without affecting your existing Claude Code setup.

**macOS / Linux** - Add to `~/.bashrc` or `~/.zshrc`:

```bash
zai() {
    export ANTHROPIC_AUTH_TOKEN="your-zai-api-key"
    export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
    export API_TIMEOUT_MS="3000000"
    claude "$@"
}
```

<details>
<summary><strong>Windows PowerShell</strong></summary>

```powershell
function zai {
    $env:ANTHROPIC_AUTH_TOKEN = "your-zai-api-key"
    $env:ANTHROPIC_BASE_URL = "https://api.z.ai/api/anthropic"
    $env:API_TIMEOUT_MS = "3000000"
    claude $args
}
```

</details>

<details>
<summary><strong>Windows CMD Batch</strong></summary>

Create `zai.bat`:
```batch
@echo off
set ANTHROPIC_AUTH_TOKEN=your-zai-api-key
set ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
set API_TIMEOUT_MS=3000000
claude %*
```

</details>

### Model Mapping

| Claude Model | GLM Model |
|--------------|-----------|
| Opus | GLM-4.7 |
| Sonnet | GLM-4.7 |
| Haiku | GLM-4.5-Air |

**Customize mappings** (optional) by adding to your shell function:
```bash
export ANTHROPIC_DEFAULT_OPUS_MODEL="GLM-4.7"
export ANTHROPIC_DEFAULT_SONNET_MODEL="GLM-4.5"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="GLM-4.5-Air"
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

### Usage

```bash
zai                              # Launch Z.AI
zai --model sonnet               # Specific model
zai --model opus --permission-mode plan
```

### Z.AI + Git Worktree Integration

Combine Z.AI with worktrees for isolated parallel sessions:

**macOS / Linux**:
```bash
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
zaix feature-auth  # Named worktree
zaix               # Auto-generated name
```

> **See also:** [Parallel Sessions](#i-want-to-run-parallel-ai-coding-sessions) for more worktree details

---

## I want to monitor costs and usage

### Claude Plan Rate Limits

From August 28, 2025, weekly limits apply (plus monthly 50x 5hr session limit):

| Plan | Sonnet 4 (hrs/week) | Opus 4 (hrs/week) |
|------|---------------------|-------------------|
| Pro | 40–80 | – |
| Max ($100/mo) | 140–280 | 15–35 |
| Max ($200/mo) | 240–480 | 24–40 |

### Status Lines

Display real-time usage in Claude Code.

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
if git rev-parse --git-dir > /dev/null 2>&1; then
    BRANCH=$(git branch --show-current 2>/dev/null)
    if [ -n "$BRANCH" ]; then
        GIT_BRANCH=" | 🌿 $BRANCH"
    fi
fi

echo "[$MODEL_DISPLAY] 📁 ${CURRENT_DIR##*/}${GIT_BRANCH}
Context: [$PROGRESS_BAR] ${USED_PERCENTAGE}%
Cost: \$${COST_USD} | +${LINES_ADDED} -${LINES_REMOVED} lines"
```

### Cost Tracking MCP

Install the [Usage Metrics MCP](https://github.com/centminmod/claude-code-opentelemetry-setup):
```bash
claude mcp add --transport stdio metrics -s user -- uv run --directory /path/to/mcp-server metrics-server
```

### Cost Analysis Command

Use `/ccusage-daily` for detailed cost analysis with daily breakdowns, model statistics, and recommendations.

### Optimization Tips

- **Use Z.AI** for 3× higher quotas at lower cost
- **Use CoD mode** in code-searcher for 80% token reduction
- **Use git worktrees** for parallel sessions without duplicating quota
- **Monitor status lines** to track real-time usage

> **See also:** [Z.AI](#i-want-to-use-zai-for-higher-quotas) for higher quota options

---

## Configuration Reference

### Settings Scopes

| Scope | Location | Who it affects |
|-------|----------|----------------|
| Managed | System directories | All users (IT-controlled) |
| User | `~/.claude/settings.json` | You (all projects) |
| Project | `.claude/settings.json` | All collaborators |
| Local | `.claude/settings.local.json` | You (this project only) |

**Precedence**: Enterprise > CLI args > Local > Project > User

### settings.json Options

| Key | What it does | Example |
|-----|-------------|---------|
| `apiKeyHelper` | Script to generate auth | `/bin/generate_key.sh` |
| `cleanupPeriodDays` | Days to keep transcripts | `20` |
| `env` | Environment variables | `{"FOO": "bar"}` |
| `includeCoAuthoredBy` | Add Claude byline to commits | `false` |

### Permission Settings

| Key | What it does | Example |
|-----|-------------|---------|
| `allow` | Allowed tool rules | `["Bash(git diff:*)"]` |
| `deny` | Denied tool rules | `["WebFetch"]` |
| `additionalDirectories` | Extra working dirs | `["../docs/"]` |
| `defaultMode` | Default permission mode | `"acceptEdits"` |

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | API key for Claude SDK |
| `ANTHROPIC_AUTH_TOKEN` | Custom auth header |
| `ANTHROPIC_BASE_URL` | Custom API endpoint |
| `ANTHROPIC_MODEL` | Custom model name |
| `BASH_DEFAULT_TIMEOUT_MS` | Default bash timeout |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Max output tokens |
| `CLAUDE_CODE_USE_BEDROCK` | Use Amazon Bedrock |
| `CLAUDE_CODE_USE_VERTEX` | Use Google Vertex AI |
| `DISABLE_AUTOUPDATER` | Disable updates |
| `DISABLE_TELEMETRY` | Opt out of telemetry |
| `MCP_TIMEOUT` | MCP startup timeout |
| `MCP_TOOL_TIMEOUT` | MCP tool timeout |
| `MAX_MCP_OUTPUT_TOKENS` | Max MCP tokens (default: 25000) |

### File Locations

| File | macOS/Linux | Windows |
|------|-------------|---------|
| User settings | `~/.claude/settings.json` | `%USERPROFILE%\.claude\settings.json` |
| Project settings | `.claude/settings.json` | `.claude\settings.json` |
| Local settings | `.claude/settings.local.json` | `.claude\settings.local.json` |

### Tools Available to Claude

| Tool | What it does | Permission |
|------|-------------|------------|
| Agent | Runs sub-agents | No |
| Bash | Shell commands | Yes |
| Edit | File edits | Yes |
| Glob | Find files by pattern | No |
| Grep | Search file contents | No |
| LS | List files | No |
| MultiEdit | Multiple atomic edits | Yes |
| NotebookEdit | Jupyter cell edits | Yes |
| NotebookRead | Read Jupyter notebooks | No |
| Read | Read files | No |
| TodoRead/TodoWrite | Task management | No |
| WebFetch | Fetch URLs | Yes |
| WebSearch | Web searches | Yes |
| Write | Create/overwrite files | Yes |

### Config Commands

```bash
claude config list              # List settings
claude config get <key>         # Get setting
claude config set <key> <value> # Set setting
claude config set -g <key> <value> # Global setting
```

---

## Resources

### Official Documentation

- [Claude Code Overview](https://docs.anthropic.com/en/docs/claude-code/overview)
- [Settings Reference](https://code.claude.com/docs/en/settings)
- [Hooks](https://code.claude.com/docs/en/hooks)
- [Skills](https://docs.claude.com/en/docs/claude-code/skills)
- [Sub-agents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)
- [Plugin Marketplace](https://code.claude.com/docs/en/discover-plugins)

### YouTube Guides

* [Claude Code with Opus 4.5](https://www.youtube.com/watch?v=UVJXh57MgI0) - Alex Finn
* [Claude Code Overview](https://www.youtube.com/watch?v=Dekx_OzRwiI) - Matt Maher
* [VS Code Beginner Guide](https://www.youtube.com/watch?v=rPITZvwyoMc)
* [Ralph Wiggum Tutorial](https://www.youtube.com/watch?v=RpvQH0r0ecM) - Greg Isenberg & Ryan Carson

### Other Resources

* [Advent of Claude: 31 Days](https://adocomplete.com/advent-of-claude-2025/) - Ado Kukic
* [40+ Claude Code Tips](https://github.com/ykdojo/claude-code-tips)

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=centminmod/my-claude-code-setup&type=Date)](https://www.star-history.com/#centminmod/my-claude-code-setup&Date)

---

## Stats

![Alt](https://repobeats.axiom.co/api/embed/715da1679915da77d87deb99a1f527a44e76ec60.svg "Repobeats analytics image")
