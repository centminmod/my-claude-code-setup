# Prompt Engineering — Core Principles

Foundational rules for composing high-quality image generation prompts. Read this when a category is detected or the user asks for prompt enhancement.

---

## Core Prompting Principles

1. **Narrative over keywords** — Describe a scene like directing a photographer, not listing attributes. "A warm afternoon in a sunlit café with a steaming latte on a marble table" beats "latte, café, warm, marble, afternoon, sunlit."

2. **Specificity creates quality** — Detailed descriptions produce dramatically better results. "Weathered ceramic mug with visible glaze cracks and a thin gold rim" beats "old mug."

3. **Camera language = photorealism** — Including real camera specs (lens, aperture, camera model) pushes models toward photorealistic output. Use this for any photography-style generation.

4. **Ignore quality modifiers** — Words like "4k", "ultra HD", "masterpiece", "best quality" are ignored by modern image models. They waste prompt space. Focus on describing WHAT you want instead.

5. **Prompt length sweet spot** — 100–250 words is optimal. Enough detail to guide the model, not so much that it gets confused or ignores parts.

6. **Background specification** — Always explicitly describe the background. "White background", "dark moody gradient", "blurred outdoor scene" — never leave it implied.

7. **Transparent mode (`-t`) interaction** — When the user wants transparency, the script auto-injects green screen instructions. Your prompt should complement this by specifying an isolated subject with NO environment, shadows, reflections, or floor. Just the subject.

8. **Editing mode (`-r`) interaction** — When reference images are provided, describe what to CHANGE, not the entire scene. "Change the background to a sunset" not "Create a photo of a mug on a table with a sunset background." The model sees the reference and needs edits, not a full new description.

---

## Camera & Lens Specifications

Use these when the category calls for photorealistic output (product_hero, lifestyle, food_drink, architecture, portrait).

### By Purpose

| Purpose | Camera | Lens | Aperture | Notes |
|---------|--------|------|----------|-------|
| Product hero shot | Sony A7R IV | 85mm macro | f/2.8 | Sharp detail, controlled blur |
| Product flat lay | Canon 5D Mark IV | 50mm | f/8 | Even sharpness across frame |
| Portrait / lifestyle | Sony A7III | 85mm | f/1.4–f/1.8 | Beautiful subject isolation |
| Wide lifestyle / scene | Sony A7III | 35mm | f/2.8 | Environmental context |
| Food & beverage | Canon R5 | 100mm macro | f/2.8 | Tight detail, creamy blur |
| Architecture / interior | Canon 5D | 24mm tilt-shift | f/11 | Corrected verticals, deep focus |
| Fashion editorial | Hasselblad 500C | 80mm | f/2.8 | Medium format aesthetic |

### Aperture Guide

| Aperture | Depth of Field | Best For |
|----------|---------------|----------|
| f/1.4–f/2.0 | Maximum background blur | Portraits, single product isolation |
| f/2.8–f/4.0 | Moderate depth | Lifestyle with context, food |
| f/5.6–f/8.0 | Deep focus | Flat lays, group product shots |
| f/11–f/16 | Maximum sharpness | Architecture, detailed arrays |

---

## Lighting Setups

Include lighting descriptions in prompts for photorealistic categories. Describe the EFFECT, not just the setup name.

| Setup | Prompt Language |
|-------|----------------|
| **Single softbox key** | "Soft key light from upper-left casting gentle shadows that define the product's contours" |
| **Three-point** | "Key light at 45 degrees with fill light opposite and rim light from behind creating edge definition" |
| **Natural window** | "Soft diffused daylight from a large window, casting natural shadows across the scene" |
| **Dramatic single source** | "Hard directional spotlight creating deep shadows and a sense of luxury and mystery" |
| **Flat / even** | "Even, diffused studio lighting revealing every texture without harsh shadows" |
| **Golden hour** | "Warm low-angle golden hour sunlight streaming through, creating long shadows and warm pools of light" |
| **Studio HDRI** | "Even, controlled studio illumination with neutral color temperature" |

### Film Stock as Aesthetic Shorthand

Adding a film stock reference communicates an entire aesthetic in a few words:

| Film Stock | Aesthetic Effect |
|-----------|-----------------|
| "Shot on Kodak Portra 400" | Warm skin tones, fine grain, soft pastel palette |
| "Shot on Fuji Pro 400H" | Cool greens, soft highlights, ethereal |
| "Shot on Kodak Ektar 100" | Ultra-saturated, vivid colors, fine grain |
| "Shot on Ilford HP5 Plus" | Black and white, contrasty, documentary feel |
| "Shot on CineStill 800T" | Cinematic tungsten tones, halation glow around highlights |

---

## Text Rendering Rules

AI image models can render text but need precise instructions for accuracy.

### 7 Rules for 95%+ Text Accuracy

1. **Always wrap text in quotation marks** — `"MEMENTO MORI"` not MEMENTO MORI
2. **Describe font style, not font name** — "bold condensed sans-serif" not "Bebas Neue"
3. **Specify placement** — "centered below the main graphic" or "upper-left corner"
4. **Keep text short** — Headlines under 5 words render most reliably
5. **Specify case explicitly** — "ALL-CAPS" or "lowercase" — don't assume
6. **For multiple text elements** — Describe hierarchy: "large headline above, smaller tagline below"
7. **Describe integration** — "text integrated into the design" vs "text overlaid on the image"

### Font Style Descriptions

Use these descriptions instead of font names:

| Desired Look | Prompt Description |
|-------------|-------------------|
| Bebas / Futura | "bold condensed geometric sans-serif, ALL-CAPS" |
| Cloister Black | "ornate gothic blackletter with sharp serifs" |
| Helvetica Bold | "clean modern sans-serif, heavy weight" |
| Script / cursive | "flowing hand-written script with natural curves" |
| Distressed | "weathered, partially worn sans-serif with grunge texture" |
| Retro display | "rounded retro display font with 70s character" |
| Stencil | "military-style stencil lettering with characteristic gaps" |
| Minimal / light | "ultra-clean thin sans-serif, wide letter-spacing, lowercase" |
| Slab serif | "bold slab-serif with strong horizontal strokes" |

---

## Model-Specific Recommendations

| Category | Recommended Model | Why |
|----------|------------------|-----|
| product_hero, lifestyle | `gemini` or `gpt5.4` | Best photorealism, lighting accuracy |
| food_drink | `gemini` or `gpt5.4` | Macro detail, appetizing color |
| illustration, pod_design | `riverflow` or `flux2` | Artistic quality, clean lines |
| web_app, icon_logo | `gemini` | Clean output, good text rendering |
| social_media | `gemini` or `seedream` | Bold colors, visual impact |
| architecture | `gpt5.4` or `flux2` | Accurate perspective, materials |
| marketing_banner | `gemini` | Text rendering, layout control |
| infographic | `gemini` or `qwen` | Text accuracy, clean layout (`qwen` renders text down to 10px) |

When the user doesn't specify a model, default to `gemini` (most versatile). Suggest alternatives when a different model would produce notably better results for the detected category.
