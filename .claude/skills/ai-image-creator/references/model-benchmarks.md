# Model Benchmarks — Claude Opus Robot Preset

Measured cost, time and output for each image model on one fixed prompt, so model choice can be
based on real numbers instead of list prices. Re-run with the `ai-image-test-run` skill; add each new
run as a dated section below and update the headline figures in `SKILL.md` → Model Selection.

## Run 1 — 2026-09-28

**Test:** the Claude Opus robot from the Claude robot family cast sheet
(`Create Images/claude-models/claude-robots-castsheet-v2.png`), described in text only by the
standard prompt `ai-image-test-run/references/opus-standard-prompt.txt`. It uses the preset's style
DNA and Opus anchor, with no reference image, so every model gets identical input (`muse` and
`recraft-flash` cannot take `-r`).

**Settings:** `-a 1:1` (`muse` has no aspect-ratio option, so it gets the model default), default
size and quality, OpenRouter via the Cloudflare AI Gateway. Cost is the `usage.cost` OpenRouter
billed. Time is end-to-end `elapsed_seconds` (request → decoded image). **One sample per model**:
times vary run to run, so treat them as rough. Total run cost: $0.375.

| Keyword | Model ID | Cost | Time | Tokens (in / out) | Native output | Fidelity to the cast-sheet Opus |
|---|---|---|---|---|---|---|
| `recraft-flash` | `recraft/recraft-v4.1-flash` | $0.007 | 5.4 s | 457 / 4175 | WebP 1024² | Least faithful: no black screen faceplate (eyes drawn on the ivory head); clean, flat, barely weathered |
| `muse` | `meta/muse-image` | $0.010 | 18.2 s | 457 / 1686 | WebP 1600² | Very close; laurel drawn as a circlet; weathered matte finish and thick outlines match the sheet's style |
| `gpt-flare` | `openai/gpt-image-2.5-flare` | $0.015 | 18.6 s | 431 / 439 | PNG 1024² | Faithful, broad heavy build; detailed plaza (banners, fountain) despite "gently out of focus" |
| `gpt-sunburst` | `openai/gpt-image-2.5-sunburst` | $0.015 | 25.8 s | 431 / 439 | PNG 1024² | Most convincing heavy-mecha Opus; busiest background (statue, fountain, banners) |
| `mai-flash` | `microsoft/mai-image-2.6-flash` | $0.020 | 14.8 s | 424 / 1024 | PNG 1024² | Faithful; slightly more ornate armour; sharp, detailed background |
| `qwen` | `qwen/qwen-image-3` | $0.030 | 63.0 s | 457 / 4175 | PNG 1024² | Faithful with a restrained warm background; slow |
| `gemini-lite` | `google/gemini-3.1-flash-lite-image` | $0.034 | 5.1 s | 423 / 1120 | JPEG 1024² | Faithful, but small in frame and drew a picture-frame border |
| `seedream` | `bytedance-seed/seedream-5-0-lite` | $0.035 | 39.9 s | 457 / 16384 | JPEG 2048² | Slimmer and lighter than a heavy mecha; drew a picture-frame border; 2K by default |
| `qwen-pro` | `qwen/qwen-image-3-pro` | $0.040 | 56.6 s | 457 / 4175 | PNG 1024² | Very faithful; no visible gain over `qwen` on this prompt |
| `mai` | `microsoft/mai-image-2.6` | $0.041 | 24.6 s | 424 / 1024 | PNG 1024² | Faithful; heavier armour (hexagonal knee guards); rich scenic background |
| `grok` | `x-ai/grok-imagine-image-2.0` | $0.060 | 66.0 s | 457 / 4175 | JPEG 1024² | Faithful; moodier, darker shading; billed above its $0.04 list price; slowest |
| `gemini` (baseline) | `google/gemini-3.1-flash-image` | $0.067 | 12.4 s | 423 / 1120 | PNG 1024² | Closest match overall, with a home advantage: Gemini drew the original cast sheet |

**Every model** spelled the chest plaque `CLAUDE OPUS` correctly and produced the laurel wreath,
purple starry cape, sun medallion, star pauldrons, belt, gold knee guards and cyan crescent eyes.

### Takeaways

- **Best value:** `muse` ($0.010) and `gpt-flare` / `gpt-sunburst` ($0.015) come near baseline
  fidelity at 15–25% of `gemini`'s cost.
- **Fastest:** `gemini-lite` (5.1 s) and `recraft-flash` (5.4 s). **Slowest:** `grok`, `qwen`,
  `qwen-pro` (~1 minute each).
- **List price vs billed:** `grok` billed $0.06 against a $0.04 list price. MAI and GPT Image 2.5
  are token-billed and came in far below a flat-rate reading of their per-token prices.
- **Background restraint:** GPT Image 2.5 and both MAI models add detailed scenery even when asked
  for a soft, out-of-focus background. Say so more strongly if the background must stay plain.
- **Native formats:** `gemini-lite`, `grok` and `seedream` return JPEG; `muse` and
  `recraft-flash` return WebP. `generate-image.py` now converts to the `-o` extension (ImageMagick).

### Known quirk of the standard prompt

"centered in a square frame" made `gemini-lite` and `seedream` draw a literal picture frame. The
wording is kept verbatim so later runs stay comparable with this one; if the prompt is ever changed,
start a new benchmark series instead of mixing results.

**Artifacts:** `Create Images/ai-image-creator-test-images/` — `opus-<keyword>.png` per model, its
`.prompt.md`, `standardized-prompt.txt`, `00-reference-opus-from-castsheet.png` and the labelled
comparison sheet `opus-model-comparison.png`.

## Run 2 — 2026-10-07

**Test:** Nano Banana 2.1 (released on OpenRouter 2026-10-06) against the `gemini` baseline, with the
same standard prompt and settings as Run 1 (`-a 1:1`, default size, CF gateway). One sample per
model. Total run cost: $0.105.

| Keyword | Model ID | Cost | Time | Tokens (in / out) | Native output | Fidelity to the cast-sheet Opus |
|---|---|---|---|---|---|---|
| `nano-banana-2.1` | `google/gemini-nano-banana-2.1` | $0.038 | 11.9 s | 424 / 1585 | non-PNG (converted) 1024² | Passes every check; one-line plaque, stockier chibi build, hand-on-hip pose, cape hides the left pauldron |
| `gemini` (baseline) | `google/gemini-3.1-flash-image` | $0.067 | 10.9 s | 423 / 1120 | PNG 1024² | Still the closest match: two-line plaque and upright, symmetric stance like the sheet |

### Takeaways

- **Cost:** `nano-banana-2.1` is 44% cheaper than `gemini` at 1K. OpenRouter lists its image-output
  tokens at $30/M, half of `gemini`'s $60/M. The 1120 image tokens come to about $0.034. The
  other ~465 output tokens are text/thinking billed at $7.50/M (~$0.003); `gemini` emits none.
- **Speed:** same as `gemini` within one-sample noise (11.9 s vs 10.9 s; `gemini` took 12.4 s in Run 1).
- **Fidelity:** both pass every check. `gemini` stays marginally closer to the sheet's layout,
  probably helped by having drawn the original cast sheet.
- **Native format:** the saved PNG carries ImageMagick's conversion chunks, so the API returned a
  non-PNG format. `results.json` does not record which one.
- **Not measured:** 2K/4K cost, `-r` editing quality, `--analyze`.

**Artifacts:** `Create Images/ai-image-creator-test-images/20261007_084553/` (`results.json`,
`opus-model-comparison.png`).
