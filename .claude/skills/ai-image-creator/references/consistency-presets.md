# Frame Consistency & Preset Image Hints

Generate a **set** of images where the same character(s), object(s), and scene stay
visually consistent across frames — for image-to-video frames (start/last frame),
storyboards, or comic strips that are later stitched together.

## When to use this

Match any of: "consistent character", "same character across frames", "keep the same
product", "comic strip", "storyboard", "frame set", "start and end frame", "before/after",
"panel", or any request that produces **more than one image of the same subject**.

For a single one-off image, skip this — generate directly.

## The consistency problem

`generate-image.py` has **no seed flag**. Identity consistency therefore comes from two
levers, and you should use **both together**:

1. **Canonical anchor text** — a fixed description block reused *verbatim* (copy-paste, never
   paraphrase) in every frame's prompt.
2. **Reference-image chaining** — pass an anchor image via `-r`. **Multimodal models only**
   (`gemini`, `geminipro`, `gpt5`). Image-only models (`riverflow`, `flux2`, `seedream`)
   ignore or error on `-r`.

## Step 1 — Define the preset (anchors)

A **preset** is a named bundle of *anchor blocks*. Lock only the invariant attributes;
keep per-frame variables OUT of the anchors.

| Anchor | Lock these (invariant) | Keep OUT (per-frame) |
|--------|------------------------|----------------------|
| **Character** | face/hair/skin (with hex), clothing colors, body type, glasses/accessories | pose, expression, action, camera |
| **Object / prop** | shape, material, color, branding/logo, proportions | placement, angle, lighting state |
| **Scene / setting** | location, time of day, lighting, color palette | camera angle, framing, who's present |

Use the template at the bottom of this file. The character sheets in a project's style-preset
file (e.g. the Create Images project's `CLAUDE-style-presets.md`) **are** reusable character
anchors — reference them directly rather than rewriting.

## Step 2 — Establish a key / reference image

Generate **one** canonical image first — a clean "key frame" (single subject, neutral pose,
plain background) or a "cast sheet" (all recurring subjects together). This becomes the `-r`
reference for every other frame.

```bash
RUN=exports/frames/$(date +%Y%m%d_%H%M%S); mkdir -p "$RUN"
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "$RUN/key.png" -m geminipro -a 16:9 -s 2K \
  -p "<CHARACTER ANCHOR verbatim>, neutral standing pose, plain light-grey studio background"
```

## Step 3 — Generate each frame

For every frame: **prompt = anchor block (verbatim) + a per-frame action/scene line**, plus
`-r` to the key image. Hold `-m`, `-a`, and `-s` identical across all frames.

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "$RUN/frame-01.png" -m geminipro -a 16:9 -s 2K \
  -r "$RUN/key.png" \
  -p "<ANCHOR BLOCK verbatim>. SCENE: <this frame's action / camera / expression>"
```

Two chaining strategies:

- **Hub (recommended)** — every frame references the **same key image**. Prevents cumulative
  drift; best for casts and comic panels.
- **Chain** — frame N references frame N-1 (`-r "$RUN/frame-0$((N-1)).png"`). Good for gradual
  scene evolution, but drift accumulates — re-anchor to the key image every few frames.

If a frame drifts off-model, regenerate it referencing the **key image**, not the drifted frame.
Higher `-s` (2K/4K) preserves fine identity detail.

## Workflow A — Video frames (first / last frame)

1. Define preset → generate key image (Step 2).
2. `frame-start.png` = anchor + opening pose, `-r key.png`.
3. `frame-end.png` = **same anchor** + closing pose, `-r frame-start.png` (so the two match).
4. Match `-a` to the target video ratio (usually `16:9`).
5. Hand both to `ai-video-creator`: `--first-frame "$RUN/frame-start.png" --last-frame "$RUN/frame-end.png"`
   (Seedance / Veo 3.1 / Seedance 1.5 Pro support first+last; most others take `--first-frame` only —
   see that skill's Step 4).

## Workflow B — Comic strip / storyboard

1. Define preset → generate a **cast sheet** key image.
2. One image per panel: anchor + panel action + the panel's caption/dialogue text, `-r cast-sheet.png`.
3. Stitch panels into a strip with ImageMagick (offline, no API):

```bash
magick montage "$RUN"/panel-*.png -tile 3x1 -geometry +8+8 -background white "$RUN/strip.png"   # 3 across
magick montage "$RUN"/panel-*.png -tile 2x2 -geometry +8+8 -background white "$RUN/strip.png"   # 2x2 grid
```

Comic **style** (bold outlines, cel-shading, speech bubbles) is a separate concern: combine the
consistency anchors here with a *style* preset (e.g. a project's `CLAUDE-style-presets.md`).

## Preset block template

```
### Preset: <name>
RECOMMENDED: -m geminipro   -a 16:9   -s 2K     (multimodal model REQUIRED for -r)
KEY IMAGE:   <path to cast sheet / key frame, once generated>

CHARACTER ANCHOR — <id>:
<locked face / hair / skin (hex) / clothing (hex) / body / accessories — NO pose or expression>

OBJECT ANCHOR — <id>:
<locked shape / material / color / branding / proportions — NO placement or angle>

SCENE ANCHOR:
<locked location / time / lighting / palette — NO camera angle or framing>

PER-FRAME VARIABLES (never put in anchors): pose, expression, action, camera, framing.
```
