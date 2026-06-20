---
name: ai-image-creator
description: Generate PNG images using AI (multiple models via OpenRouter including Gemini, FLUX.2, Riverflow, SeedDream, GPT-5 Image, GPT-5.4 Image 2, proxied through Cloudflare AI Gateway BYOK). Also analyze/describe existing images using multimodal AI vision, and analyze video (--analyze-video) via OpenRouter video-input models (mimo, gemini, qwen, seed, minimax) to get text descriptions for video prompts. Use when user asks to "generate an image", "create a PNG", "make an icon", "make it transparent", "describe this image", "analyze this image", "what's in this image", "explain this image", "describe this video", "analyze this video", "what happens in this video", or needs AI-generated visual assets for the project. Supports model selection via keywords (gemini, geminipro, riverflow, flux2, seedream, gpt5, gpt5.4), configurable aspect ratios/resolutions, transparent backgrounds (-t), reference image editing (-r), image analysis (--analyze), video analysis (--analyze-video), and per-project cost tracking (--costs).
allowed-tools: Bash, Read, Write
compatibility: Requires uv (Python runner) and network access. Environment variables for CF AI Gateway or direct API keys must be configured in shell profile (~/.zshrc on macOS, ~/.bashrc on Linux, or System Environment Variables on Windows).
metadata:
  tags: image-generation, ai, openrouter, cloudflare, gemini, flux2, riverflow, seedream, gpt5, gpt54
---

# AI Image Creator

Generate PNG images via multiple AI models, routed through Cloudflare AI Gateway BYOK or directly via OpenRouter/Google AI Studio.

## Model Selection

When the user mentions a model keyword in their image request, use the corresponding `--model` flag:

| Keyword | Model | Use When User Says |
|---------|-------|--------------------|
| `gemini` | [Google Gemini 3.1 Flash](https://openrouter.ai/google/gemini-3.1-flash-image) (default) | "gemini", "generate an image" (no model specified) |
| `geminipro` | [Google Gemini 3 Pro](https://openrouter.ai/google/gemini-3-pro-image) | "geminipro", "gemini pro", "use gemini pro" |
| `riverflow` | [Sourceful Riverflow v2 Pro](https://openrouter.ai/sourceful/riverflow-v2-pro) | "riverflow", "use riverflow" |
| `flux2` | [FLUX.2 Max](https://openrouter.ai/black-forest-labs/flux.2-max) | "flux2", "flux", "use flux" |
| `seedream` | [ByteDance SeedDream 4.5](https://openrouter.ai/bytedance-seed/seedream-4.5) | "seedream", "use seedream" |
| `gpt5` | [OpenAI GPT-5 Image](https://openrouter.ai/openai/gpt-5-image) | "gpt5", "gpt5 image", "use gpt5" |
| `gpt5.4` | [OpenAI GPT-5.4 Image 2](https://openrouter.ai/openai/gpt-5.4-image-2) | "gpt5.4", "gpt-5.4 image", "use gpt5.4" |

## Instructions

> **Routing check:** If the user asks to **describe, analyze, or explain an existing image** (not generate a new one), skip directly to the **Image Analysis (`--analyze`)** section below. No prompt enhancement or output path needed.
>
> **Video routing:** If the user asks to **describe, analyze, or explain a video** (or wants a text description of a clip to seed/extend a video prompt), skip directly to the **Video Analysis (`--analyze-video`)** section below.

### Step 1: Write Prompt

For long or complex prompts (recommended), write to `${CLAUDE_SKILL_DIR}/tmp/prompt.txt` using the Write tool:

```
Write prompt text to ${CLAUDE_SKILL_DIR}/tmp/prompt.txt
```

For short prompts (under 200 chars, no special characters), pass inline via `--prompt`.

**CRITICAL — Prompt Quality Tips:**
- Be detailed and descriptive. Include style, colors, composition, background, and intended use.
- Good: "A flat-design globe icon with vertical timezone band lines in blue and teal, white background, clean vector style, suitable for a web app at 512x512 pixels"
- Bad: "globe icon"
- Specify "transparent background" or "white background" explicitly.
- For icons, mention the target size (e.g., "512x512", "favicon at 32x32").
- For photos, describe lighting, camera angle, and mood.

### Step 1.5: Prompt Enhancement (Optional — Progressive Disclosure)

Professional prompt patterns are available in 3 reference files. These are **not loaded by default** — only read them when the user's request matches a category or they explicitly ask for enhancement.

**Category Detection** — Match the user's request to a category:

| If request mentions... | Category | Also read |
|----------------------|----------|-----------|
| "product shot", "product photo", "hero image" | `product_hero` | `prompt-core.md` + `prompt-categories.md` § product_hero |
| "lifestyle", "in-use", "in context" | `lifestyle` | `prompt-core.md` + `prompt-categories.md` § lifestyle |
| "instagram", "social media", "tiktok", "pinterest" | `social_media` | `prompt-core.md` + `prompt-platforms.md` + `prompt-categories.md` § social_media |
| "banner", "ad", "email header" | `marketing_banner` | `prompt-core.md` + `prompt-platforms.md` + `prompt-categories.md` § marketing_banner. **Routing hint:** If user has an existing logo and wants multiple standard sizes → use composite mode instead (see `## Composite Banners`). |
| "website", "app", "logo", "ad format", "leaderboard", "skyscraper" | `web_app` | `prompt-core.md` + `prompt-platforms.md` + `prompt-categories.md` § web_app. **Routing hint:** For "logo banners" or "OG images with my logo" where user has existing logo → use `composite-banners.py`. For "design me a new logo" → use `generate-image.py`. |
| "brand kit", "logo banners", "banner sizes", "IAB sizes", "consistent banners" + user has existing logo | `composite` | Read `references/composite-reference.md`, use `composite-banners.py` |
| "icon", "favicon", "app icon" | `icon_logo` | `prompt-core.md` + `prompt-categories.md` § icon_logo |
| "mascot", "character", "illustration", "artwork" | `illustration` | `prompt-core.md` + `prompt-categories.md` § illustration |
| "food", "drink", "recipe", "restaurant" | `food_drink` | `prompt-core.md` + `prompt-categories.md` § food_drink |
| "building", "interior", "room", "architecture" | `architecture` | `prompt-core.md` + `prompt-categories.md` § architecture |
| "chart", "infographic", "data", "diagram" | `infographic` | `prompt-core.md` + `prompt-categories.md` § infographic |
| "t-shirt", "mug design", "poster", "POD", "print-on-demand" | `pod_design` | `prompt-core.md` + `prompt-platforms.md` + `prompt-categories.md` § pod_design |
| "consistent character", "same character/product across frames", "comic strip", "storyboard", "frame set", "start and last frame", "panels", "before/after" | `frame_consistency` | Read `references/consistency-presets.md` — keep people/objects/scenes consistent across a SET of frames (for video first/last frames or stitched comic strips) |
| "describe", "analyze", "what's in this image", "explain image" | `analyze` | Skip prompt enhancement — use `--analyze` mode directly. Read `references/analyze-reference.md` for advanced analysis patterns |
| No match / simple request | — | Skip patterns, generate directly |

**When to skip enhancement:**
- User's prompt is already detailed (150+ words with camera/lighting/composition specifics)
- Simple/direct requests ("generate a blue circle on white background")
- User says "no pattern" or provides a fully formed prompt

**When to apply:**
- User says "use product_hero pattern" or "apply social_media pattern" (explicit)
- Request clearly matches a category above (auto-detect)
- User asks for "enhanced prompt" or "professional quality"

**Reference files** (in `references/` directory):
- `prompt-core.md` — Foundational rules: narrative prompting, camera/lens/lighting specs, text rendering rules, model recommendations
- `prompt-platforms.md` — Social media ratios, IAB ad sizes, web dimensions, POD specs — all mapped to `-a`/`-s` flags
- `prompt-categories.md` — 11 category formulas with templates and complete example prompts

### Step 2: Run Generation Script

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "OUTPUT_PATH" \
  [--provider openrouter|google] \
  [-a "16:9"] \
  [-s "2K"] \
  [-m "model-id"] \
  [-r "ref-image.png"] \
  [-t]
```

With a specific model:
```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "OUTPUT_PATH" \
  -m riverflow \
  -p "A serene mountain lake at sunset"
```

With transparent background (requires ffmpeg + imagemagick):
```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "mascot.png" \
  -t \
  -p "A friendly robot mascot character"
```

With reference image for editing/style transfer (multimodal models only):
```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "edited.png" \
  -r "original.png" \
  -p "Change the background to a sunset scene"
```

Or with inline prompt (default model):
```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "OUTPUT_PATH" \
  -p "A simple blue circle on white background"
```

### Step 3: Clean Up (if temp file used)

```bash
rm -f ${CLAUDE_SKILL_DIR}/tmp/prompt.txt
```

### Step 4: Verify Output

```bash
file OUTPUT_PATH
```

Confirm it shows "PNG image data" and report the file path and size to the user.

### Step 5: Post-Processing (optional)

If the user needs resizing, format conversion, or other manipulation, first detect available image tools, then use them. See **Image Tools** section below.

## Parameters

| Argument | Short | Required | Default | Description |
|----------|-------|----------|---------|-------------|
| `--output` | `-o` | Yes | -- | Output file path (parent dirs auto-created) |
| `--prompt` | `-p` | No | -- | Inline prompt text |
| `--prompt-file` | -- | No | `../tmp/prompt.txt` | Path to prompt file |
| `--provider` | -- | No | `openrouter` | `openrouter` or `google` |
| `--aspect-ratio` | `-a` | No | model default | OpenRouter only: `1:1`, `16:9`, `9:16`, `3:2`, `2:3`, `4:3`, `3:4`, `4:5`, `5:4`, `21:9` |
| `--image-size` | `-s` | No | model default | OpenRouter only: `0.5K`, `1K`, `2K`, `4K` |
| `--model` | `-m` | No | `gemini` | Model keyword (`gemini`, `geminipro`, `riverflow`, `flux2`, `seedream`, `gpt5`, `gpt5.4`) or full model ID |
| `--ref` | `-r` | No | -- | Reference image file (repeatable). For editing/style transfer. Multimodal models only (gemini, geminipro, gpt5, gpt5.4) |
| `--analyze` | -- | No | -- | Analyze/describe a reference image (text-only output, no image generated). Requires `-r`. Multimodal models only |
| `--analyze-video` | -- | No | -- | Analyze/describe a video. Pass the video via `-r` (local file or URL). OpenRouter only. Choose a model/preset with `-m` (default `gemini3.5-flash`). Returns **structured JSON** by default |
| `--prose` | -- | No | -- | (`--analyze-video` only) Return free-text prose instead of the default structured JSON |
| `--contact-sheet` | -- | No | -- | (`--analyze-video`, local file only) Extract evenly-spaced keyframes with ffmpeg and save a labeled contact-sheet image to `PATH` — a human ground-truth reference. Skipped for URL sources / if ffmpeg is missing |
| `--verify` | -- | No | -- | (`--analyze-video`, local file only) Second pass that checks the analysis against extracted frames (no video re-sent) and classifies each claim `supported`/`contradicted`/`not_visible`. Adds a `verification` object. Costs one extra model call |
| `--transparent` | `-t` | No | -- | Generate with transparent background. Requires ffmpeg + imagemagick |
| `--costs` | -- | No | -- | Display generation/cost history for this project and exit |
| `--list-models` | -- | No | -- | List available model keywords and exit |

## Environment Variables

| Variable | Required For | Description |
|----------|-------------|-------------|
| `AI_IMG_CREATOR_CF_ACCOUNT_ID` | Gateway mode | Cloudflare account ID |
| `AI_IMG_CREATOR_CF_GATEWAY_ID` | Gateway mode | AI Gateway name |
| `AI_IMG_CREATOR_CF_TOKEN` | Gateway mode | Gateway auth token |
| `AI_IMG_CREATOR_OPENROUTER_KEY` | Direct OpenRouter | OpenRouter API key (`sk-or-...`) |
| `AI_IMG_CREATOR_GEMINI_KEY` | Direct Google | Google AI Studio API key |

Gateway mode activates when all 3 `CF_*` vars are set. Falls back to direct mode if gateway fails.

For first-time setup, see `references/setup-guide.md`.

## Transparent Mode (`-t`)

Generates images with transparent backgrounds using a 3-step pipeline:

1. **Green screen generation** — Prompt is augmented to place subject on solid #00FF00 green
2. **FFmpeg chroma key** — Removes green background + green fringe from edges
3. **ImageMagick auto-crop** — Trims transparent padding

**Requirements:** `brew install ffmpeg imagemagick`

**Use cases:** Game sprites, icons, logos, mascots, marketing assets with transparency.

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "sprite.png" -t -p "A pixel art treasure chest"
```

## Reference Images (`-r`)

Send existing images alongside text prompts for editing, style transfer, or guided generation. Supports multiple references. **Multimodal models only** (gemini, geminipro, gpt5, gpt5.4) — image-only models (riverflow, flux2, seedream) will error.

```bash
# Edit an existing image
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "edited.png" -r "photo.png" -p "Make the background white"

# Style transfer with multiple references
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "combined.png" -r "style1.png" -r "content.png" -p "Apply the style of the first image to the second"
```

Supported formats: PNG, JPEG, WebP, GIF.

## Image Analysis (`--analyze`)

Describe, analyze, or explain existing images using multimodal AI vision. Returns text-only output (no image generated). **Multimodal models only** (gemini, geminipro, gpt5, gpt5.4).

No `-o` output path needed. No prompt enhancement needed. The script outputs JSON to stdout with the model's analysis in the `analysis` field.

```bash
# Analyze with default prompt (describes subject, style, colors, composition, mood, text)
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "photo.png"

# Analyze with custom prompt
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "photo.png" -p "Describe this image in plain text and also in JSON structured output"

# Analyze with a specific model
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "photo.png" -m gpt5 -p "What text is visible in this image?"

# Analyze multiple images together
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "before.png" -r "after.png" -p "Compare these two images and describe the differences"
```

**JSON output format:**

```json
{"ok": true, "analyze": true, "analysis": "<model text>", "provider": "openrouter", "model": "...", "mode": "gateway", "elapsed_seconds": 3.2, "ref_images": 1}
```

**Incompatible flags:** `--analyze` cannot be combined with `-t`, `-a`, or `-s`. (`-o` is accepted but ignored in analyze mode, which returns text only.)

For advanced analysis prompt patterns (structured output, comparison, targeted analysis), read `references/analyze-reference.md`.

## Video Analysis (`--analyze-video`)

Describe or analyze a **video** using OpenRouter video-input LLMs (no image generated). Use this to turn an existing clip into a description you can feed back as a prompt to **generate or extend** a video (e.g. with the `ai-video-creator` skill).

**Structured JSON is the default.** All 15 video models support strict structured outputs (`response_format` json_schema, verified), so by default `analysis` is a **structured object** with these fields: `summary`, `setting`, `subjects[]` (each with `role`/`appearance`/`confidence`), `shot_timeline[]` (`timestamp`/`action`/`camera`), `camera_techniques[]`, `editing_stylization[]`, `lighting`, `color_palette[]`, `mood`, `uncertain_details[]`, and a distilled `video_generation_prompt`. The `editing_stylization` and `uncertain_details` fields specifically counter the two main failure modes (missed freeze-frame/black-and-white stylization, and confabulated details). Pass `--prose` for a free-text description instead. The envelope's `structured` field is `true` when JSON parsed cleanly.

Pass the video via `-r` — either a **local file** (mp4/mov/webm/mkv/avi; sent as a base64 data URL) or a **URL** (publicly accessible, including YouTube). OpenRouter only; no `-o`, prompt enhancement, or output path needed.

**Model selection (`-m`)** — three presets cover the common cases; or pick any model by keyword (see `--list-models`):

| Preset | Resolves to | When to use |
|--------|-------------|-------------|
| `video-default` (or omit `-m`) | `gemini3.5-flash` (Google Gemini 3.5 Flash) | **Default** — best accuracy + fastest; reads audio. ~11× the cost of the cheap tier |
| `video-cheap` | `qwen3.5-flash` (Qwen3.5 Flash) | Rock-bottom cost for quick scene summaries (or `mimo` for a cheap, more detailed read) |
| `video-quality` | `gemini3-pro` (Google Gemini 3.1 Pro) | Highest-accuracy reading when it matters most |

All 15 video-capable models are selectable by keyword: `qwen3.5-flash`, `seed-1.6-flash`, `seed-2.0-mini`, `mimo`, `qwen3.6-35b`, `qwen3.6-flash`, `step-3.7-flash`, `gemini3-flash-lite`, `seed-2.0-lite`, `seed-1.6`, `qwen3.5-plus`, `minimax-m3`, `qwen3.6-plus`, `gemini3.5-flash`, `gemini3-pro` (cheapest → priciest). Run `--list-models` for IDs and per-1M-token pricing.

```bash
# Default model (gemini3.5-flash), structured JSON output
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze-video -r "clip.mp4"

# Free-text prose instead of JSON
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze-video -r "clip.mp4" --prose

# Rock-bottom cost preset
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze-video -r "clip.mp4" -m video-cheap

# Highest-accuracy preset on a YouTube URL with a custom focus
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze-video -r "https://youtu.be/VIDEO_ID" -m video-quality \
  -p "Focus on camera movement and lighting"
```

**JSON output format** (default — `analysis` is a structured object):

```json
{"ok": true, "analyze": true, "analyze_video": true, "structured": true, "analysis": {"summary": "...", "setting": "...", "subjects": [{"role": "protagonist", "appearance": "...", "confidence": "high"}], "shot_timeline": [{"timestamp": "0:00", "action": "...", "camera": "..."}], "camera_techniques": ["..."], "editing_stylization": ["monochrome freeze-frame", "..."], "lighting": "...", "color_palette": ["..."], "mood": "...", "uncertain_details": ["..."], "video_generation_prompt": "..."}, "provider": "openrouter", "model": "google/gemini-3.5-flash", "mode": "gateway", "elapsed_seconds": 16.9, "video_source": "clip.mp4"}
```

With `--prose`, `analysis` is a plain text string and `structured` is `false`.

### Frame grounding (`--contact-sheet`, `--verify`)

The model samples its own frames internally, but it can still slip a confabulation into a
single shot (e.g. a "golden glowing eye" in the final beat that isn't there). Two opt-in,
**local-file-only** aids ground the analysis against real pixels using ffmpeg-extracted
keyframes:

- **`--contact-sheet PATH`** — extracts ~12 evenly-spaced keyframes (always including first
  and last; capped uniform sampling, not scene-detect) and tiles them into one labeled image
  at `PATH`. This is the highest-leverage aid: a human (or you) can eyeball the whole clip at
  a glance to sanity-check the description. Built with ImageMagick `montage` (timestamp
  labels) or, if absent, ffmpeg's `tile` filter. The path is echoed back as `contact_sheet`
  in the JSON envelope.
- **`--verify`** — runs a cheap **second pass** that sends the contact sheet + a few full
  keyframes (with timestamps) and the pass-1 analysis back to the **same model**, and asks it
  to classify each claim `supported` / `contradicted` / `not_visible` strictly from the
  frames. **The video is not re-sent** (that would just re-confabulate from the same pixels),
  and undiscernible details stay `not_visible` rather than being "resolved" into a guess. Adds
  a `verification` object: `{claims[]{claim,verdict,evidence}, corrections[], overall_accuracy}`.

Both are skipped with a warning (never a hard error) for URL/YouTube sources or if ffmpeg is
missing — the analysis itself always proceeds. Extracted frames go to a temp dir that is
cleaned up automatically; only the `--contact-sheet` image is kept.

```bash
# Save a ground-truth contact sheet alongside the analysis, and verify the claims
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze-video -r "clip.mp4" \
  --contact-sheet "exports/clip_frames.png" --verify
```

**Notes:**
- **Incompatible flags:** cannot be combined with `--analyze`, `-t`, `-a`, or `-s`, and requires `--provider openrouter`.
- **Large local files** (>20 MB) trigger a warning — base64 payloads can be slow or rejected; prefer a hosted/YouTube URL or a shorter/lower-res clip.
- **Context limits:** Seed/Step models cap at ~256K tokens (fine for short clips); the 1M-context models (Qwen, Gemini, MiMo, MiniMax) are safer for longer footage.

## Cost Tracking (`--costs`)

Every generation is logged to `.ai-image-creator/costs.json` in your project directory. View history:

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py --costs
```

Shows per-model breakdown: generation count, total tokens, elapsed time, and recent entries. **Security:** Only non-sensitive data is logged (model, tokens, timing, file path). No API keys or credentials are ever stored.

Consider adding `.ai-image-creator/` to your `.gitignore`.

## Composite Banners

Generate consistent logo banners across multiple sizes from a JSON config. Uses ImageMagick for offline compositing — no API calls, no network required. Composites an existing logo/mark onto branded backgrounds with text at standard dimensions.

### Composite vs. AI Generation — Decision Rule

Use **composite-banners.py** when ALL of these are true:
- User has an existing logo/mark they want to use as-is (provides or references a logo file)
- User wants consistent branding across multiple standard sizes (not one creative image)
- The output is logo + text on a solid/gradient background (not a photograph, illustration, or creative design)

Use **generate-image.py** (AI generation) when ANY of these are true:
- User wants a creative/artistic banner design (describes a scene, mood, concept, or style)
- User wants AI to design the visual content (product shots, illustrations, creative layouts)
- User wants a single banner with artistic content, not a multi-size brand kit

**When composite mode applies**, read `references/composite-reference.md` for full config schema, preset dimensions, and font handling details.

### Quick Start

1. **Init config:** `uv run python ${CLAUDE_SKILL_DIR}/scripts/composite-banners.py --init`
2. **Edit** `banner-config.json` — set logo path, brand text, colors, banner sizes
3. **Validate:** `uv run python ${CLAUDE_SKILL_DIR}/scripts/composite-banners.py --validate`
4. **Generate:** `uv run python ${CLAUDE_SKILL_DIR}/scripts/composite-banners.py -c banner-config.json -o ./banners/`

### Composite Parameters

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--config` | `-c` | `banner-config.json` | Config JSON path |
| `--output-dir` | `-o` | `.` | Output directory |
| `--name` | `-n` | all | Generate single banner by name |
| `--format` | `-f` | `png` | `png`, `webp`, `jpeg` |
| `--list-presets` | | | List IAB/social/web size presets |
| `--init` | | | Generate starter config |
| `--validate` | | | Check config, exit 0 or 2 |
| `--dry-run` | | | Preview without rendering |
| `--json` | | | Structured JSON to stdout |
| `--verbose` | `-v` | | Verbose output |

**Requirements:** ImageMagick 7 (`brew install imagemagick` or `apt install imagemagick`).

### Workflow Hints

**Starting composite mode:**
- Ask user for: logo file path, brand name, tagline text, brand colors (hex)
- If user doesn't have a logo yet → use generate-image.py to create one first
- Run `--init` to scaffold config, then help user fill in their brand values

**During generation:**
- Always run `--validate` before generating to catch font/logo issues early
- Use `--name` to iterate on one banner before generating the full set
- Show user 3-4 representative sizes (hero, OG, square, leaderboard) for approval

**After generation:**
- If user wants creative/artistic redesign of banner visuals → switch to generate-image.py (composite only does logo + text on gradient/solid backgrounds)
- If banners look too plain → suggest AI-generating a textured or photographic background first, then compositing the logo onto it

**Combined workflow (most powerful):**
1. Use generate-image.py to AI-create a hero background or textured pattern
2. Use composite-banners.py to overlay the logo + text onto that background at all standard sizes
This gives both creative AI visuals AND pixel-perfect logo consistency.

## Image Tools

On first invocation, detect available image manipulation tools:

```bash
which magick convert sips ffmpeg 2>/dev/null
```

### Available Tools

| Tool | Check | Key Operations |
|------|-------|----------------|
| **ImageMagick 7** (`magick`) | `magick --version` | Resize, crop, convert, composite |
| **ImageMagick 6** (`convert`) | `convert --version` | Same ops, legacy command name |
| **sips** (macOS) | `sips --help` | Resize, format conversion |
| **ffmpeg** | `ffmpeg -version` | Convert formats, resize |

### Common Post-Processing

```bash
# Resize
magick output.png -resize 512x512 icon-512.png

# Multiple sizes (icons)
for s in 16 32 48 64 128 256 512; do magick output.png -resize ${s}x${s} icon-${s}.png; done

# Convert to WebP
magick output.png output.webp

# Maskable icon (add safe-zone padding)
magick output.png -gravity center -extent 120%x120% maskable.png

# macOS sips resize
sips --resampleWidth 512 --resampleHeight 512 output.png --out icon-512.png
```

CRITICAL: Check tool availability before using. Prefer `magick` (IM7) over `convert` (IM6). If no tools found, inform user: `brew install imagemagick`.

## Common Issues

### "No API credentials configured"
**Cause:** Environment variables not set or not exported.
**Fix:** Add exports to `~/.zshrc` and run `source ~/.zshrc`. See `references/setup-guide.md`.

### "HTTP 401: Unauthorized"
**Cause:** Invalid or expired API key/token.
**Fix:** Check `AI_IMG_CREATOR_CF_TOKEN` (gateway) or `AI_IMG_CREATOR_OPENROUTER_KEY` (direct). Regenerate if needed.

### "No images in response"
**Cause:** Model returned text only (safety filter, unclear prompt, or unsupported request).
**Fix:** Make the prompt more specific and descriptive. Avoid prohibited content.

### "Connection error" / timeout
**Cause:** Network issue or image generation taking too long (120s timeout).
**Fix:** Retry. If persistent, try `--provider google` as alternative. Check CF gateway status.

## Detailed API Reference

For full API formats, response schemas, BYOK configuration, and curl examples:
see [references/api-reference.md](references/api-reference.md)

For first-time setup instructions:
see [references/setup-guide.md](references/setup-guide.md)
