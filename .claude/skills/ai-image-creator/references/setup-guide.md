# Setup Guide — AI Image Creator

Step-by-step instructions to configure all required services for the ai-image-creator skill.

## Prerequisites

- **uv** (Python runner): Install via `curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`
- **Python 3.10+**: Bundled with uv or install separately
- A Cloudflare account (free tier works)
- An OpenRouter account and/or Google AI Studio account

### Optional (for transparent mode `-t`)

- **FFmpeg 4.3+**: `brew install ffmpeg` (macOS) / `apt install ffmpeg` (Linux)
- **ImageMagick 7+**: `brew install imagemagick` (macOS) / `apt install imagemagick` (Linux)

These are only needed if you use the `-t` flag for transparent background generation.

---

## 1. Get an OpenRouter API Key

1. Create an account at [openrouter.ai](https://openrouter.ai)
2. Go to [openrouter.ai/keys](https://openrouter.ai/keys) and click **Create Key**
3. Copy the key (starts with `sk-or-...`)
4. Add credits at [openrouter.ai/credits](https://openrouter.ai/credits) (pay-as-you-go pricing)

**Model pricing:** `google/gemini-3.1-flash-image` — check current rates at [openrouter.ai/models](https://openrouter.ai/models) (search for "gemini-3.1-flash-image")

---

## 2. Get a Google AI Studio API Key

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Click **Create API Key**
3. Select or create a Google Cloud project
4. Copy the key (starts with `AI...`)

**Pricing:** Free tier has rate limits. Check quotas at [ai.google.dev/pricing](https://ai.google.dev/pricing)

**Important:** The free tier has a quota of **0** for `gemini-3.1-flash-image` image generation. You must enable billing on the linked Google Cloud project for image generation to work. Without billing, requests return `429 RESOURCE_EXHAUSTED` with `limit: 0`. The OpenRouter provider is recommended as a simpler alternative (pay-as-you-go credits, no GCP billing setup required).

---

## 3. Create a Cloudflare AI Gateway

1. Log in to [dash.cloudflare.com](https://dash.cloudflare.com)
2. Select your account
3. Navigate to **AI** > **AI Gateway**
4. Click **Create Gateway**
5. Enter a name (e.g., `my-ai-gateway`) — this becomes your Gateway ID
6. Click **Create**

**Note your credentials:**
- **Account ID**: Found in the dashboard URL (`dash.cloudflare.com/{account_id}/...`) or on the account Overview page
- **Gateway ID**: The name you chose in step 5

### Enable Authentication (Recommended)

1. In your gateway settings, enable **Authentication**
2. Copy the **auth token** — this is your `AI_IMG_CREATOR_CF_TOKEN`

---

## 4. Configure BYOK Provider Keys in CF AI Gateway

Store your API keys securely in Cloudflare so they're never sent in request headers.

### Add OpenRouter Key

1. In your gateway dashboard, go to **Provider Keys**
2. Click **Add**
3. Select **OpenRouter** as the provider
4. Paste your OpenRouter API key (`sk-or-...`)
5. Set alias to `default`
6. Click **Save**

### Add Google AI Studio Key

1. Click **Add** again
2. Select **Google AI Studio** as the provider
3. Paste your Google AI Studio API key (`AI...`)
4. Set alias to `aistudio`
5. Click **Save**

---

## 5. Set Environment Variables

Add these to your shell profile or system environment variables.

### macOS / Linux

Edit `~/.zshrc` (macOS) or `~/.bashrc` (Linux):

```bash
# AI Image Creator — CF AI Gateway (preferred mode)
export AI_IMG_CREATOR_CF_ACCOUNT_ID="your-cloudflare-account-id"
export AI_IMG_CREATOR_CF_GATEWAY_ID="your-gateway-name"
export AI_IMG_CREATOR_CF_TOKEN="your-gateway-auth-token"

# AI Image Creator — Direct API keys (fallback, optional if BYOK configured)
export AI_IMG_CREATOR_OPENROUTER_KEY="sk-or-your-key-here"
export AI_IMG_CREATOR_GEMINI_KEY="AIyour-key-here"
```

Apply changes:

```bash
source ~/.zshrc   # macOS
source ~/.bashrc  # Linux
```

### Windows

Set environment variables via PowerShell (user-level, persists across sessions):

```powershell
# AI Image Creator — CF AI Gateway (preferred mode)
[Environment]::SetEnvironmentVariable("AI_IMG_CREATOR_CF_ACCOUNT_ID", "your-cloudflare-account-id", "User")
[Environment]::SetEnvironmentVariable("AI_IMG_CREATOR_CF_GATEWAY_ID", "your-gateway-name", "User")
[Environment]::SetEnvironmentVariable("AI_IMG_CREATOR_CF_TOKEN", "your-gateway-auth-token", "User")

# AI Image Creator — Direct API keys (fallback, optional if BYOK configured)
[Environment]::SetEnvironmentVariable("AI_IMG_CREATOR_OPENROUTER_KEY", "sk-or-your-key-here", "User")
[Environment]::SetEnvironmentVariable("AI_IMG_CREATOR_GEMINI_KEY", "AIyour-key-here", "User")
```

Or use **Settings > System > About > Advanced system settings > Environment Variables** to add them via the GUI.

Restart your terminal after setting variables.

### Verify

```bash
echo $AI_IMG_CREATOR_CF_ACCOUNT_ID   # macOS/Linux
echo %AI_IMG_CREATOR_CF_ACCOUNT_ID%  # Windows CMD
$env:AI_IMG_CREATOR_CF_ACCOUNT_ID    # Windows PowerShell
```

---

## 6. Install the Skill

### Per-Project Installation

Copy the `ai-image-creator/` folder to your project:
```bash
cp -r /path/to/ai-image-creator .claude/skills/
```

Add permission to `.claude/settings.local.json`:
```json
{
  "permissions": {
    "allow": [
      "Skill(ai-image-creator)",
      "Bash(uv run:*)"
    ]
  }
}
```

### Global Installation

Place in your home directory:
```bash
cp -r /path/to/ai-image-creator ~/.claude/skills/
```

Add permission to `~/.claude/settings.json`:
```json
{
  "permissions": {
    "allow": [
      "Skill(ai-image-creator)",
      "Bash(uv run:*)"
    ]
  }
}
```

---

## 7. Verify Setup

Test the skill:

```
/ai-image-creator
```

Then ask: "Generate a simple blue circle on white background" with output to `test-image.png`.

**Expected result:** A PNG file is created. The script outputs the file path and size.

**Clean up test file:**
```bash
rm test-image.png
```

---

## Troubleshooting

### "No API credentials configured"
Environment variables are not set or not exported. Run `echo $AI_IMG_CREATOR_CF_ACCOUNT_ID` to verify.

### "HTTP 401: Unauthorized"
- **Gateway mode:** Check `AI_IMG_CREATOR_CF_TOKEN` is correct. Regenerate in CF dashboard if needed.
- **Direct mode:** Check `AI_IMG_CREATOR_OPENROUTER_KEY` or `AI_IMG_CREATOR_GEMINI_KEY`.

### "uv: command not found"
Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`

### Gateway returns unexpected errors
Test direct mode by temporarily unsetting CF variables:
```bash
unset AI_IMG_CREATOR_CF_ACCOUNT_ID
/ai-image-creator
```
If direct mode works, the issue is with the gateway configuration.

### BYOK key not found
Verify in CF dashboard: AI > AI Gateway > your gateway > Provider Keys. Ensure aliases match: `default` for OpenRouter, `aistudio` for Google AI Studio.
