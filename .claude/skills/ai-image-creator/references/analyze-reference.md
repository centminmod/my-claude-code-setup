# Image Analysis Reference

Advanced prompt patterns for `--analyze` mode. Only read this file when the user needs structured, comparative, or targeted image analysis beyond a simple description.

## Analysis Prompt Patterns

### Plain Text Description

Default behavior — no custom prompt needed. The built-in default covers subject, style, colors, composition, mood, and visible text.

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py --analyze -r "image.png"
```

### JSON Structured Output

Ask the model to return structured data:

```
Analyze this image and return a JSON object with these fields:
- image_type: the type/medium of the image (photo, illustration, screenshot, etc.)
- subjects: array of objects with {name, position, description}
- colors: dominant color palette as hex codes
- text_content: any visible text in the image
- style: artistic style or visual treatment
- mood: emotional tone
- composition: layout and framing description
```

### Plain Text + JSON Combined

```
Describe this image in two sections:
1. PLAIN TEXT: A natural-language paragraph describing what the image shows
2. JSON: A structured JSON object with fields: image_type, subjects, colors, style, mood, composition, text_content
```

### Comparison (Multiple Images)

Use multiple `-r` flags to compare images:

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "v1.png" -r "v2.png" \
  -p "Compare these two images. Describe the differences in composition, color, and style. Which is more suitable for a professional website hero banner?"
```

### Targeted Analysis

Focus the model on specific aspects:

| Focus | Prompt Pattern |
|-------|---------------|
| Accessibility | "Evaluate this UI screenshot for accessibility: contrast ratios, text readability, color-blind friendliness" |
| Brand consistency | "Does this image match a modern tech brand aesthetic? Evaluate color palette, typography, and visual style" |
| Text extraction | "Extract all visible text from this image, preserving layout and hierarchy" |
| Technical specs | "Describe the technical properties: estimated resolution, aspect ratio, color space, compression artifacts" |
| Content moderation | "Describe the content of this image objectively. Flag any potentially sensitive content" |
| UI/UX review | "Analyze this UI screenshot: layout, visual hierarchy, spacing, typography, and potential usability issues" |

### Batch Analysis Workflow

To analyze multiple images individually (not comparing), loop in the skill:

```bash
for img in screenshots/*.png; do
  echo "=== $img ===" >&2
  uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
    --analyze -r "$img" -p "Describe this screenshot in one paragraph"
done
```

## Model Recommendations

| Model | Best For |
|-------|----------|
| `gemini` (default) | General analysis, fast and cost-effective. Good at text extraction and structured output |
| `gpt5.4` | Nuanced descriptions, creative interpretation, detailed comparisons |

## Output Handling

The `--analyze` flag outputs JSON to stdout. The `analysis` field contains the model's text response. To extract just the analysis text in a script:

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "image.png" | python -c "import sys,json; print(json.load(sys.stdin)['analysis'])"
```

Status messages go to stderr, so piping stdout gives clean JSON.
