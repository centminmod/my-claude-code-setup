#!/usr/bin/env python3
"""AI Image Generator — Generate PNG images via multiple OpenRouter models or Google AI Studio.

Supports multiple image generation models via keyword shortcuts:
    gemini     — Google Gemini 3.1 Flash (default, multimodal)
    geminipro  — Google Gemini 3 Pro (multimodal, highest quality)
    riverflow  — Sourceful Riverflow v2 Pro (image-only)
    flux2      — Black Forest Labs FLUX.2 Max (image-only)
    seedream   — ByteDance SeedDream 4.5 (image-only)
    gpt5       — OpenAI GPT-5 Image (multimodal)
    gpt5.4     — OpenAI GPT-5.4 Image 2 (multimodal, 272K context)

Routes through Cloudflare AI Gateway BYOK when configured, with automatic
fallback to direct API calls. Uses only Python stdlib (no pip dependencies).

Also analyzes video via OpenRouter video-input LLMs (--analyze-video), returning
a structured JSON description by default (or --prose free text) to seed prompts
for generating or extending videos.

Usage:
    uv run python generate-image.py --output path.png --prompt "description"
    uv run python generate-image.py --output path.png --model riverflow --prompt "description"
    uv run python generate-image.py --output path.png --prompt-file prompt.txt
    uv run python generate-image.py --analyze-video -r clip.mp4 --model mimo
    uv run python generate-image.py --analyze-video -r https://youtu.be/ID --model video-quality
    uv run python generate-image.py --list-models
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any  # noqa: F401 — used in type hints below

# Default models per provider
DEFAULT_MODELS = {
    "openrouter": "google/gemini-3.1-flash-image",
    "google": "gemini-3.1-flash-image",
}

# Model registry — maps keyword shortcuts to model metadata.
# All models use the OpenRouter /v1/chat/completions endpoint.
# Image-only models use modalities: ["image"], multimodal use ["image", "text"].
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "gemini": {
        "id": "google/gemini-3.1-flash-image",
        "modalities": ["image", "text"],
        "description": "Google Gemini 3.1 Flash — multimodal (text+image), default",
    },
    "geminipro": {
        "id": "google/gemini-3-pro-image",
        "modalities": ["image", "text"],
        "description": "Google Gemini 3 Pro — multimodal (text+image), highest quality",
    },
    "riverflow": {
        "id": "sourceful/riverflow-v2-pro",
        "modalities": ["image"],
        "description": "Sourceful Riverflow v2 Pro — image-only, high quality",
    },
    "flux2": {
        "id": "black-forest-labs/flux.2-max",
        "modalities": ["image"],
        "description": "Black Forest Labs FLUX.2 Max — image-only, high quality",
    },
    "seedream": {
        "id": "bytedance-seed/seedream-4.5",
        "modalities": ["image"],
        "description": "ByteDance SeedDream 4.5 — image-only, high quality",
    },
    "gpt5": {
        "id": "openai/gpt-5-image",
        "modalities": ["image", "text"],
        "description": "OpenAI GPT-5 Image — multimodal (text+image)",
    },
    "gpt5.4": {
        "id": "openai/gpt-5.4-image-2",
        "modalities": ["image", "text"],
        "description": "OpenAI GPT-5.4 Image 2 — multimodal (text+image), 272K context",
    },
}

# Video-analysis model registry — OpenRouter LLMs that accept `video` input.
# Unlike the image models above, these OUTPUT text only: they describe a video
# (scene, action, camera, mood) so the description can seed prompts to generate
# or extend videos. Sent via the chat/completions `video_url` content part.
# Pricing is USD per 1M tokens (input/output), captured live from the OpenRouter
# models API; entries are ordered cheapest-first (by input price).
VIDEO_MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "qwen3.5-flash":      {"id": "qwen/qwen3.5-flash-02-23",      "in": 0.065,  "out": 0.26,  "ctx": "1M",   "description": "Qwen3.5 Flash — rock-bottom cost"},
    "seed-1.6-flash":     {"id": "bytedance-seed/seed-1.6-flash", "in": 0.075,  "out": 0.30,  "ctx": "262K", "description": "ByteDance Seed 1.6 Flash"},
    "seed-2.0-mini":      {"id": "bytedance-seed/seed-2.0-mini",  "in": 0.10,   "out": 0.40,  "ctx": "262K", "description": "ByteDance Seed 2.0 Mini"},
    "mimo":               {"id": "xiaomi/mimo-v2.5",              "in": 0.14,   "out": 0.28,  "ctx": "1M",   "description": "Xiaomi MiMo v2.5 — balanced, cheap (+audio input)"},
    "qwen3.6-35b":        {"id": "qwen/qwen3.6-35b-a3b",          "in": 0.14,   "out": 1.00,  "ctx": "262K", "description": "Qwen3.6 35B-A3B (MoE)"},
    "qwen3.6-flash":      {"id": "qwen/qwen3.6-flash",            "in": 0.1875, "out": 1.125, "ctx": "1M",   "description": "Qwen3.6 Flash"},
    "step-3.7-flash":     {"id": "stepfun/step-3.7-flash",        "in": 0.20,   "out": 1.15,  "ctx": "256K", "description": "StepFun Step 3.7 Flash"},
    "gemini3-flash-lite": {"id": "google/gemini-3.1-flash-lite",  "in": 0.25,   "out": 1.50,  "ctx": "1M",   "description": "Google Gemini 3.1 Flash Lite (+audio input)"},
    "seed-2.0-lite":      {"id": "bytedance-seed/seed-2.0-lite",  "in": 0.25,   "out": 2.00,  "ctx": "262K", "description": "ByteDance Seed 2.0 Lite"},
    "seed-1.6":           {"id": "bytedance-seed/seed-1.6",       "in": 0.25,   "out": 2.00,  "ctx": "262K", "description": "ByteDance Seed 1.6"},
    "qwen3.5-plus":       {"id": "qwen/qwen3.5-plus-02-15",       "in": 0.26,   "out": 1.56,  "ctx": "1M",   "description": "Qwen3.5 Plus"},
    "minimax-m3":         {"id": "minimax/minimax-m3",            "in": 0.30,   "out": 1.20,  "ctx": "1M",   "description": "MiniMax M3"},
    "qwen3.6-plus":       {"id": "qwen/qwen3.6-plus",             "in": 0.325,  "out": 1.95,  "ctx": "1M",   "description": "Qwen3.6 Plus"},
    "gemini3.5-flash":    {"id": "google/gemini-3.5-flash",       "in": 1.50,   "out": 9.00,  "ctx": "1M",   "description": "Google Gemini 3.5 Flash — DEFAULT, best accuracy/speed (+audio input)"},
    "gemini3-pro":        {"id": "google/gemini-3.1-pro-preview", "in": 2.00,   "out": 12.0,  "ctx": "1M",   "description": "Google Gemini 3.1 Pro — highest quality / quality preset (+audio input)"},
}

# Friendly preset aliases for the three recommended tiers.
VIDEO_MODEL_PRESETS = {
    "video-default": "gemini3.5-flash", # default — best accuracy/speed balance
    "video-cheap":   "qwen3.5-flash",   # rock-bottom cost
    "video-quality": "gemini3-pro",     # highest accuracy (Gemini 3.1 Pro)
}

# Default video-analysis model keyword (used when --analyze-video is given with no -m).
DEFAULT_VIDEO_MODEL = "gemini3.5-flash"

# MIME types for local video files sent as base64 data URLs.
VIDEO_MIME_MAP = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}

# Structured-output JSON Schema for --analyze-video (the default mode). All 15
# registered video models report `structured_outputs: true` on OpenRouter, so
# strict json_schema is the default; --prose opts out to free-form text.
# Strict mode requires every property in `required` and additionalProperties:false
# at every object level. The `uncertain_details` + `editing_stylization` fields
# directly counter the two observed failure modes (confabulation; missed
# freeze-frame / black-and-white stylization).
VIDEO_JSON_SCHEMA: dict[str, Any] = {
    "name": "video_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "2-3 sentence overview of the clip"},
            "setting": {"type": "string", "description": "Location, environment, and notable scene details"},
            "subjects": {
                "type": "array",
                "description": "Each distinct character/subject visible",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "description": "e.g. protagonist, antagonist, bystander"},
                        "appearance": {"type": "string", "description": "Visible appearance, clothing, distinguishing features"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"], "description": "How clearly the appearance details could be determined"},
                    },
                    "required": ["role", "appearance", "confidence"],
                    "additionalProperties": False,
                },
            },
            "shot_timeline": {
                "type": "array",
                "description": "Shot-by-shot beats in order",
                "items": {
                    "type": "object",
                    "properties": {
                        "timestamp": {"type": "string", "description": "Approx time or shot index, e.g. '0:03' or 'shot 2'"},
                        "action": {"type": "string", "description": "What happens in this beat"},
                        "camera": {"type": "string", "description": "Camera framing/movement for this beat"},
                    },
                    "required": ["timestamp", "action", "camera"],
                    "additionalProperties": False,
                },
            },
            "camera_techniques": {"type": "array", "items": {"type": "string"}, "description": "e.g. close-up, low-angle, handheld, tracking"},
            "editing_stylization": {"type": "array", "items": {"type": "string"}, "description": "Cuts, slow-motion, freeze-frames, black-and-white/monochrome shifts, color-grade changes, speed ramps"},
            "lighting": {"type": "string"},
            "color_palette": {"type": "array", "items": {"type": "string"}},
            "mood": {"type": "string"},
            "uncertain_details": {"type": "array", "items": {"type": "string"}, "description": "Anything ambiguous or not clearly visible — list it here instead of guessing"},
            "video_generation_prompt": {"type": "string", "description": "A distilled, ready-to-use prompt for generating or extending a similar video"},
        },
        "required": [
            "summary", "setting", "subjects", "shot_timeline", "camera_techniques",
            "editing_stylization", "lighting", "color_palette", "mood",
            "uncertain_details", "video_generation_prompt",
        ],
        "additionalProperties": False,
    },
}

# Default instruction prompts for --analyze-video. The JSON variant accompanies
# the enforced schema; the prose variant is used with --prose.
DEFAULT_VIDEO_PROMPT_JSON = (
    "Analyze this video and return a structured JSON description for use in video "
    "generation. Ground every field in what is visibly present. Put anything "
    "ambiguous or not clearly visible (e.g. a subject's gender or eye color) into "
    "`uncertain_details` rather than guessing. In `editing_stylization`, note cuts, "
    "slow-motion, freeze-frames, any black-and-white/monochrome or color-grade "
    "shifts, and speed ramps. Provide a timestamped `shot_timeline` and a distilled "
    "`video_generation_prompt`."
)
DEFAULT_VIDEO_PROMPT_PROSE = (
    "Describe this video in detail for use as a video-generation prompt. Cover: the "
    "scene and setting; each subject and their appearance and actions; camera "
    "movement and framing; lighting and color palette; mood; and a timestamped "
    "shot-by-shot account of how the shot evolves.\n\n"
    "Ground every claim in what is visibly present. If a detail (such as a subject's "
    "gender, eye color, or an object) is ambiguous or not clearly visible, say so "
    "plainly — do NOT invent specifics. Explicitly call out editing and stylization: "
    "cuts, slow-motion, freeze-frames, black-and-white / monochrome shifts, "
    "color-grade changes, and speed ramps. End with a concise, ready-to-use "
    "generation prompt."
)
# Appended to a user-supplied prompt in JSON mode so the anti-confabulation +
# stylization guidance still applies even when -p / --prompt-file overrides the default.
VIDEO_JSON_DIRECTIVE = (
    "\n\nReturn ONLY a JSON object matching the provided schema. Ground every field "
    "in what is visibly present; put anything ambiguous in `uncertain_details` "
    "rather than guessing; in `editing_stylization` note cuts, slow-motion, "
    "freeze-frames, and any black-and-white/monochrome or color-grade shifts."
)

# Structured-output schema for the --verify pass. The model classifies each
# substantive claim from pass 1 against the extracted still frames — it does NOT
# re-describe the video (which would just re-confabulate from the same pixels).
# `not_visible` is a first-class verdict so an undiscernible detail stays
# undiscernible rather than being "resolved" into a guess.
VERIFY_JSON_SCHEMA: dict[str, Any] = {
    "name": "video_verification",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "description": "Each substantive visual claim from the prior analysis, checked against the frames",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string", "description": "The specific claim from the prior analysis"},
                        "verdict": {"type": "string", "enum": ["supported", "contradicted", "not_visible"]},
                        "evidence": {"type": "string", "description": "Which frame(s) and what is visible that supports/contradicts it, or why it cannot be determined from the frames"},
                    },
                    "required": ["claim", "verdict", "evidence"],
                    "additionalProperties": False,
                },
            },
            "corrections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete corrections where the frames contradict the prior analysis",
            },
            "overall_accuracy": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["claims", "corrections", "overall_accuracy"],
        "additionalProperties": False,
    },
}

VERIFY_PROMPT_HEADER = (
    "You are verifying a prior analysis of a video against still frames extracted "
    "from the SAME video. The frames are in chronological order; their timestamps "
    "are listed below. A tiled contact sheet of all frames is included first, "
    "followed by individual full frames.\n\n"
    "For each substantive visual claim in the prior analysis JSON, classify it "
    "STRICTLY from what the frames show: `supported`, `contradicted`, or "
    "`not_visible`. Judge only from the frames — do not re-imagine the video. If a "
    "detail (e.g. a subject's eye color or gender) is not discernible in the "
    "frames, mark it `not_visible` — do NOT guess. List concrete corrections only "
    "where the frames actually contradict the analysis.\n\n"
    "Frame timestamps: {timestamps}\n\n"
    "Prior analysis JSON:\n{analysis}"
)

# Documented OpenRouter image_config sizes (canonical, upper-case "K" form).
# 0.5K is only honored by the Gemini 3.1 Flash *preview* build; the GA build
# (google/gemini-3.1-flash-image) rejects it with a native 400, so we catch it
# at the CLI boundary with a clear error instead of a confusing API failure.
SUPPORTED_IMAGE_SIZES = {"0.5K", "1K", "2K", "4K"}

# Environment variable names (prefixed to avoid collisions)
ENV_CF_ACCOUNT_ID = "AI_IMG_CREATOR_CF_ACCOUNT_ID"
ENV_CF_GATEWAY_ID = "AI_IMG_CREATOR_CF_GATEWAY_ID"
ENV_CF_TOKEN = "AI_IMG_CREATOR_CF_TOKEN"
ENV_OPENROUTER_KEY = "AI_IMG_CREATOR_OPENROUTER_KEY"
ENV_GEMINI_KEY = "AI_IMG_CREATOR_GEMINI_KEY"

def _load_dotenv() -> None:
    """Load .env files into os.environ (stdlib only, no pip deps).

    Search order (first found wins per key):
      1. .env in the same directory as this script (skill-level)
      2. .env in the current working directory (project-level)
    Keys already present in os.environ are never overwritten.
    """
    candidates = [
        Path(__file__).parent / ".env",
        Path.cwd() / ".env",
    ]
    for env_file in candidates:
        if not env_file.is_file():
            continue
        with env_file.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val

_load_dotenv()

# Logger — configured in main() based on --debug / --verbose flags
log = logging.getLogger("ai-image-creator")


MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def guess_mime(path: str) -> str:
    """Guess MIME type from file extension.

    Args:
        path: File path string.

    Returns:
        MIME type string, defaults to 'image/png' for unknown extensions.
    """
    ext = Path(path).suffix.lower()
    return MIME_MAP.get(ext, "image/png")


def guess_video_mime(path: str) -> str:
    """Guess a video MIME type from file extension (defaults to video/mp4)."""
    ext = Path(path).suffix.lower()
    return VIDEO_MIME_MAP.get(ext, "video/mp4")


def mask_key(key: str, visible: int = 4) -> str:
    """Mask an API key for safe logging, showing only the last N chars.

    Args:
        key: The secret key to mask.
        visible: Number of trailing characters to leave visible.

    Returns:
        Masked string like '***abcd'.
    """
    if not key or len(key) <= visible:
        return "***"
    return f"***{key[-visible:]}"


def resolve_model(model_arg: str | None, provider: str) -> tuple[str, list[str]]:
    """Resolve a model keyword or full ID to (model_id, modalities).

    Supports three modes:
    1. No --model flag: returns the default model for the provider (gemini).
    2. Keyword match (e.g. 'riverflow'): looks up MODEL_REGISTRY.
    3. Full model ID (e.g. 'sourceful/riverflow-v2-pro'): reverse-lookups
       registry for modalities, or defaults to ["image", "text"] if unknown.

    Args:
        model_arg: The --model CLI value (keyword, full model ID, or None).
        provider: Either 'openrouter' or 'google'.

    Returns:
        Tuple of (model_id, modalities_list) where model_id is the full
        OpenRouter model identifier and modalities_list is the correct
        modalities array for the API request.
    """
    if model_arg is None:
        model_id = DEFAULT_MODELS[provider]
        if provider == "openrouter":
            entry = MODEL_REGISTRY.get("gemini", {})
            return model_id, entry.get("modalities", ["image", "text"])
        return model_id, ["image", "text"]

    # Check keyword match (case-insensitive)
    keyword = model_arg.lower().strip()
    if keyword in MODEL_REGISTRY:
        entry = MODEL_REGISTRY[keyword]
        log.info(f"Resolved keyword '{keyword}' -> {entry['id']}")
        return entry["id"], entry["modalities"]

    # Full model ID — try reverse lookup in registry for modalities
    for _kw, entry in MODEL_REGISTRY.items():
        if entry["id"] == model_arg:
            log.info(f"Matched full model ID to registry entry '{_kw}'")
            return model_arg, entry["modalities"]

    # Unknown full model ID — default to multimodal (safest)
    log.info(f"Unknown model ID '{model_arg}', defaulting to multimodal modalities")
    return model_arg, ["image", "text"]


def resolve_video_model(model_arg: str | None) -> str:
    """Resolve a video-analysis model keyword/preset/full-ID to a model ID.

    Accepts a registry keyword (e.g. 'mimo'), a preset alias
    ('video-default' / 'video-cheap' / 'video-quality'), a full OpenRouter
    model ID (must contain '/'), or None (→ DEFAULT_VIDEO_MODEL).

    Args:
        model_arg: The --model CLI value, or None.

    Returns:
        The full OpenRouter model identifier.

    Raises:
        SystemExit: If an unknown bare keyword is given.
    """
    if model_arg is None:
        return VIDEO_MODEL_REGISTRY[DEFAULT_VIDEO_MODEL]["id"]

    key = model_arg.lower().strip()
    if key in VIDEO_MODEL_PRESETS:
        key = VIDEO_MODEL_PRESETS[key]
        log.info(f"Resolved video preset -> keyword '{key}'")
    if key in VIDEO_MODEL_REGISTRY:
        entry = VIDEO_MODEL_REGISTRY[key]
        log.info(f"Resolved video keyword '{key}' -> {entry['id']}")
        return entry["id"]

    # Full model ID — accept; warn if it isn't one of the verified video models.
    if "/" in model_arg:
        if not any(e["id"] == model_arg for e in VIDEO_MODEL_REGISTRY.values()):
            log.warning(
                f"'{model_arg}' is not in the verified video registry — passing "
                f"through; ensure it accepts video input on OpenRouter."
            )
        return model_arg

    valid = ", ".join(list(VIDEO_MODEL_PRESETS) + list(VIDEO_MODEL_REGISTRY))
    print(
        f"ERROR: unknown video model '{model_arg}'. Valid keywords/presets: {valid}",
        file=sys.stderr,
    )
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Namespace with output, prompt, prompt_file, provider, aspect_ratio,
        image_size, model, list_models, debug, and verbose attributes.
    """
    parser = argparse.ArgumentParser(
        description="Generate PNG images using AI (multiple models via OpenRouter/Google AI Studio)"
    )
    parser.add_argument(
        "-o", "--output", required=False, default=None, help="Output PNG file path (required unless --list-models)"
    )
    parser.add_argument(
        "-p", "--prompt", default=None, help="Inline prompt text (alternative to --prompt-file)"
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="Path to prompt text file (default: ../tmp/prompt.txt relative to script)",
    )
    parser.add_argument(
        "--provider",
        choices=["openrouter", "google"],
        default="openrouter",
        help="API provider (default: openrouter)",
    )
    parser.add_argument(
        "-a", "--aspect-ratio",
        default=None,
        help="Aspect ratio for image (OpenRouter only): 1:1, 16:9, 9:16, 3:2, 2:3, etc.",
    )
    parser.add_argument(
        "-s", "--image-size",
        default=None,
        help="Image resolution (OpenRouter only): 0.5K, 1K, 2K, 4K",
    )
    parser.add_argument(
        "-m", "--model",
        default=None,
        help="Model keyword (gemini, geminipro, riverflow, flux2, seedream, gpt5, gpt5.4) or full model ID",
    )
    parser.add_argument(
        "-r", "--ref",
        action="append",
        default=None,
        help="Reference image file(s) for editing/style transfer (repeatable, multimodal models only)",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze/describe a reference image instead of generating one. "
             "Requires -r. Returns text description (no image output).",
    )
    parser.add_argument(
        "--analyze-video",
        action="store_true",
        help="Analyze/describe a video (OpenRouter video-input models) instead of "
             "generating an image. Pass the video via -r (a local file path or a "
             "URL, e.g. YouTube). Choose a model with -m (see --list-models for "
             "video keywords/presets; default: gemini3.5-flash). Returns text (no image).",
    )
    parser.add_argument(
        "--prose",
        action="store_true",
        help="(--analyze-video only) Return a free-text prose description instead of "
             "the default structured JSON (json_schema). All video models support JSON.",
    )
    parser.add_argument(
        "--contact-sheet",
        default=None,
        metavar="PATH",
        help="(--analyze-video, local file only) Also extract evenly-spaced keyframes "
             "with ffmpeg and save a tiled contact-sheet image to PATH — a human "
             "ground-truth reference for the analysis. Skipped (with a warning) for "
             "URL/YouTube sources or if ffmpeg is unavailable.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="(--analyze-video, local file only) Run a second pass that checks the "
             "analysis against extracted still frames (no video re-sent) and classifies "
             "each claim supported/contradicted/not_visible. Adds a `verification` "
             "object to the JSON output. Costs one extra model call.",
    )
    parser.add_argument(
        "-t", "--transparent",
        action="store_true",
        help="Generate with transparent background (requires ffmpeg + imagemagick)",
    )
    parser.add_argument(
        "--costs",
        action="store_true",
        help="Display cost/generation history for this project and exit",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available model keywords and exit",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (shows full request/response details, masked keys)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging (more detail than default, less than debug)",
    )
    return parser.parse_args()


def setup_logging(debug: bool = False, verbose: bool = False) -> None:
    """Configure logging based on flags."""
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(message)s")
    )
    log.addHandler(handler)
    log.setLevel(level)


def resolve_prompt(args: argparse.Namespace) -> str:
    """Resolve prompt text from --prompt, --prompt-file, or default path.

    Priority: --prompt (inline) > --prompt-file > default tmp/prompt.txt.

    Args:
        args: Parsed CLI arguments.

    Returns:
        The prompt text string.

    Raises:
        SystemExit: If prompt file is missing or empty.
    """
    if args.prompt:
        log.debug("Using inline --prompt argument")
        return args.prompt

    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        log.debug(f"Using --prompt-file: {prompt_path}")
    else:
        prompt_path = Path(__file__).parent.parent / "tmp" / "prompt.txt"
        log.debug(f"Using default prompt file: {prompt_path}")

    if not prompt_path.exists():
        print(f"ERROR: Prompt file not found: {prompt_path}", file=sys.stderr)
        print(
            "Either pass --prompt 'text' or write prompt to the file first.",
            file=sys.stderr,
        )
        sys.exit(1)

    text = prompt_path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"ERROR: Prompt file is empty: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    log.debug(f"Prompt length: {len(text)} chars")
    log.debug(f"Prompt preview: {text[:200]}{'...' if len(text) > 200 else ''}")
    return text


def detect_mode(provider: str) -> tuple[str, dict[str, str]]:
    """Detect gateway vs direct mode based on available env vars.

    Args:
        provider: Either 'openrouter' or 'google'.

    Returns:
        Tuple of (mode, config) where mode is 'gateway' or 'direct' and
        config contains the relevant credentials.

    Raises:
        SystemExit: If no credentials are configured for the provider.
    """
    cf_account = os.environ.get(ENV_CF_ACCOUNT_ID, "").strip()
    cf_gateway = os.environ.get(ENV_CF_GATEWAY_ID, "").strip()
    cf_token = os.environ.get(ENV_CF_TOKEN, "").strip()
    has_gateway = all([cf_account, cf_gateway, cf_token])

    log.debug(f"Env check: {ENV_CF_ACCOUNT_ID}={'set' if cf_account else 'MISSING'}")
    log.debug(f"Env check: {ENV_CF_GATEWAY_ID}={'set' if cf_gateway else 'MISSING'}")
    log.debug(f"Env check: {ENV_CF_TOKEN}={'set (' + mask_key(cf_token) + ')' if cf_token else 'MISSING'}")

    if provider == "openrouter":
        direct_key = os.environ.get(ENV_OPENROUTER_KEY, "").strip()
        log.debug(f"Env check: {ENV_OPENROUTER_KEY}={'set (' + mask_key(direct_key) + ')' if direct_key else 'MISSING'}")
    else:
        direct_key = os.environ.get(ENV_GEMINI_KEY, "").strip()
        log.debug(f"Env check: {ENV_GEMINI_KEY}={'set (' + mask_key(direct_key) + ')' if direct_key else 'MISSING'}")

    if has_gateway:
        log.info(f"Mode: gateway (account={cf_account}, gateway={cf_gateway})")
        log.debug(f"Gateway has direct_key fallback: {'yes' if direct_key else 'no'}")
        return "gateway", {
            "cf_account": cf_account,
            "cf_gateway": cf_gateway,
            "cf_token": cf_token,
            "direct_key": direct_key,
        }
    elif direct_key:
        log.info("Mode: direct (gateway env vars not fully set)")
        return "direct", {"direct_key": direct_key}
    else:
        print("ERROR: No API credentials configured.", file=sys.stderr)
        print("", file=sys.stderr)
        print("For CF AI Gateway BYOK (preferred), set:", file=sys.stderr)
        print(f"  export {ENV_CF_ACCOUNT_ID}=your-account-id", file=sys.stderr)
        print(f"  export {ENV_CF_GATEWAY_ID}=your-gateway-name", file=sys.stderr)
        print(f"  export {ENV_CF_TOKEN}=your-gateway-auth-token", file=sys.stderr)
        print("", file=sys.stderr)
        if provider == "openrouter":
            print("For direct OpenRouter access, set:", file=sys.stderr)
            print(f"  export {ENV_OPENROUTER_KEY}=sk-or-...", file=sys.stderr)
        else:
            print("For direct Google AI Studio access, set:", file=sys.stderr)
            print(f"  export {ENV_GEMINI_KEY}=AI...", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "See references/setup-guide.md for full setup instructions.",
            file=sys.stderr,
        )
        sys.exit(1)


def build_gateway_url(provider: str, model: str, config: dict[str, str]) -> str:
    """Build CF AI Gateway URL for the given provider.

    Args:
        provider: 'openrouter' or 'google'.
        model: Model ID (used in Google URL path).
        config: Credentials dict with cf_account, cf_gateway keys.

    Returns:
        Full gateway URL string.
    """
    base = f"https://gateway.ai.cloudflare.com/v1/{config['cf_account']}/{config['cf_gateway']}"
    if provider == "openrouter":
        url = f"{base}/openrouter/v1/chat/completions"
    else:
        # Google AI Studio paths use the bare model id; strip an OpenRouter-style
        # "google/" prefix so we don't emit .../models/google/<model>:generateContent.
        model_path = model.removeprefix("google/")
        url = f"{base}/google-ai-studio/v1beta/models/{model_path}:generateContent"
    log.debug(f"Built gateway URL: {url}")
    return url


def build_direct_url(provider: str, model: str) -> str:
    """Build direct API URL for the given provider.

    Args:
        provider: 'openrouter' or 'google'.
        model: Model ID (used in Google URL path).

    Returns:
        Full direct API URL string.
    """
    if provider == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
    else:
        # Google's native API also wants the bare model id (no "google/" prefix).
        model_path = model.removeprefix("google/")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent"
    log.debug(f"Built direct URL: {url}")
    return url


def build_headers(provider: str, mode: str, config: dict[str, str]) -> dict[str, str]:
    """Build HTTP headers for the request.

    Args:
        provider: 'openrouter' or 'google'.
        mode: 'gateway' or 'direct'.
        config: Credentials dict.

    Returns:
        Dict of HTTP header name-value pairs.
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ai-image-creator/1.0",
    }

    if mode == "gateway":
        headers["cf-aig-authorization"] = f"Bearer {config['cf_token']}"
        if provider == "google":
            headers["cf-aig-byok-alias"] = "aistudio"
        if provider == "openrouter" and config.get("direct_key"):
            headers["Authorization"] = f"Bearer {config['direct_key']}"
    else:
        if provider == "openrouter":
            headers["Authorization"] = f"Bearer {config['direct_key']}"
        else:
            headers["x-goog-api-key"] = config["direct_key"]

    # Log headers with masked sensitive values
    safe_headers = {}
    for k, v in headers.items():
        if k.lower() in ("authorization", "cf-aig-authorization", "x-goog-api-key"):
            safe_headers[k] = f"{v[:12]}...{mask_key(v)}"
        else:
            safe_headers[k] = v
    log.debug(f"Request headers: {json.dumps(safe_headers, indent=2)}")

    return headers


def build_request_body(
    provider: str,
    model: str,
    prompt: str,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    modalities: list[str] | None = None,
    ref_images: list[str] | None = None,
    video_source: str | None = None,
    analysis_images: list[str] | None = None,
    json_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build JSON request body for the given provider.

    Args:
        provider: 'openrouter' or 'google'.
        model: Model ID string.
        prompt: The image generation prompt text.
        aspect_ratio: Optional aspect ratio (OpenRouter only), e.g. '16:9'.
        image_size: Optional image size (OpenRouter only), e.g. '2K'.
        modalities: Output modalities list, e.g. ['image'] for image-only models
            or ['image', 'text'] for multimodal models. Defaults to ['image', 'text']
            if not specified. Only used for OpenRouter provider.
        ref_images: Optional list of file paths to reference images for
            editing/style transfer. Only supported by multimodal models.
        video_source: Optional video file path or URL for video analysis
            (OpenRouter only). When set, builds a text + video_url request and
            takes precedence over ref_images.
        analysis_images: Optional list of still-image paths for a text-out
            analysis request (OpenRouter only), e.g. the --verify pass (contact
            sheet + keyframes). Builds text + image_url parts with no output
            modalities; honors json_schema. Used only when video_source is unset.
        json_schema: Optional OpenRouter json_schema object (name/strict/schema).
            When set on a video request, adds response_format=json_schema and
            provider.require_parameters=true for strict structured output.

    Returns:
        Dict suitable for JSON serialization as request body.
    """
    refs = ref_images or []

    if provider == "openrouter" and video_source:
        # Video-analysis request: text prompt + a single video_url content part.
        # The url accepts a public/YouTube URL directly, or a base64 data URL
        # for a local file. Output is text only (modalities=["text"]).
        if video_source.startswith(("http://", "https://")):
            video_url = video_source
            log.info(f"Video source (URL): {video_source}")
        else:
            vb64 = base64.b64encode(Path(video_source).read_bytes()).decode()
            vmime = guess_video_mime(video_source)
            video_url = f"data:{vmime};base64,{vb64}"
            log.info(f"Video source (file): {video_source} ({vmime}, {len(vb64)} base64 chars)")
        # No `modalities` key: that field is the image-generation output-modality
        # extension. Video analysis is a plain text-out chat completion, so omit it
        # to avoid sending an unrecognized field to these LLMs.
        body = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "video_url", "video_url": {"url": video_url}},
                ],
            }],
        }
        if json_schema is not None:
            # Strict structured output. require_parameters forces OpenRouter to route
            # only to a provider that honors response_format (so strict mode holds).
            body["response_format"] = {"type": "json_schema", "json_schema": json_schema}
            body["provider"] = {"require_parameters": True}
            log.info("Structured JSON mode: response_format json_schema (strict)")
        # Guard the serialization: a base64 video body is large, and an unguarded
        # f-string would json.dumps() the whole payload even at non-debug levels.
        if log.isEnabledFor(logging.DEBUG):
            log.debug(f"Request body size: {len(json.dumps(body))} bytes")
        return body

    if provider == "openrouter" and analysis_images:
        # Text-out analysis over still images (e.g. the --verify pass). Plain
        # chat completion — no `modalities` (that is the image-generation
        # output-modality extension). Honors json_schema for strict output.
        content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img_path in analysis_images:
            b64 = base64.b64encode(Path(img_path).read_bytes()).decode()
            mime = guess_mime(img_path)
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
            log.info(f"Analysis image: {img_path} ({mime}, {len(b64)} base64 chars)")
        body = {
            "model": model,
            "messages": [{"role": "user", "content": content_parts}],
        }
        if json_schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": json_schema}
            body["provider"] = {"require_parameters": True}
            log.info("Structured JSON mode (verify): response_format json_schema (strict)")
        if log.isEnabledFor(logging.DEBUG):
            log.debug(f"Request body size: {len(json.dumps(body))} bytes")
        return body

    if provider == "openrouter":
        if refs:
            # Multimodal content array: text + image_url parts
            content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            for ref_path in refs:
                b64 = base64.b64encode(Path(ref_path).read_bytes()).decode()
                mime = guess_mime(ref_path)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
                log.info(f"Reference image: {ref_path} ({mime}, {len(b64)} base64 chars)")
            body: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": content_parts}],
                "modalities": modalities or ["image", "text"],
            }
        else:
            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "modalities": modalities or ["image", "text"],
            }
        image_config: dict[str, str] = {}
        if aspect_ratio:
            image_config["aspect_ratio"] = aspect_ratio
        if image_size:
            image_config["image_size"] = image_size
        if image_config:
            body["image_config"] = image_config
            log.debug(f"Image config: {json.dumps(image_config)}")
    else:
        # Google AI Studio
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for ref_path in refs:
            b64 = base64.b64encode(Path(ref_path).read_bytes()).decode()
            mime = guess_mime(ref_path)
            parts.append({"inline_data": {"mime_type": mime, "data": b64}})
            log.info(f"Reference image: {ref_path} ({mime}, {len(b64)} base64 chars)")
        body = {"contents": [{"parts": parts}]}

    log.debug(f"Request body size: {len(json.dumps(body))} bytes")
    # Log body without the full prompt or base64 data (can be very long)
    body_preview = json.dumps(body)
    if len(body_preview) > 500:
        log.debug(f"Request body (truncated): {body_preview[:500]}...")
    else:
        log.debug(f"Request body: {body_preview}")

    return body


def make_request(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: int = 300,
) -> dict[str, Any]:
    """Make HTTP POST request and return parsed JSON response.

    Args:
        url: Full API endpoint URL.
        headers: HTTP headers dict.
        body: Request body dict (will be JSON-serialized).
        timeout: Request timeout in seconds (default: 300).

    Returns:
        Parsed JSON response as a dict.

    Raises:
        RuntimeError: On HTTP errors, connection errors, or timeouts.
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    log.debug(f"Sending POST to {url} ({len(data)} bytes, timeout={timeout}s)")
    start_time = time.time()

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.time() - start_time
            response_data = resp.read().decode("utf-8")
            log.info(f"Response received: HTTP {resp.status} in {elapsed:.1f}s ({len(response_data)} bytes)")
            log.debug(f"Response headers: {dict(resp.headers)}")

            parsed = json.loads(response_data)

            # Log response structure (without huge base64 data)
            log.debug(f"Response top-level keys: {list(parsed.keys())}")
            if "choices" in parsed:
                for i, choice in enumerate(parsed["choices"]):
                    msg = choice.get("message", {})
                    log.debug(f"  choices[{i}].message keys: {list(msg.keys())}")
                    if "images" in msg:
                        log.debug(f"  choices[{i}].message.images count: {len(msg['images'])}")
                    if "content" in msg:
                        log.debug(f"  choices[{i}].message.content: {str(msg['content'])[:200]}")
            if "candidates" in parsed:
                for i, cand in enumerate(parsed["candidates"]):
                    parts = cand.get("content", {}).get("parts", [])
                    log.debug(f"  candidates[{i}].content.parts count: {len(parts)}")
                    for j, part in enumerate(parts):
                        ptype = "inlineData" if "inlineData" in part else "text" if "text" in part else "unknown"
                        if ptype == "inlineData":
                            mime = part["inlineData"].get("mimeType", "?")
                            dlen = len(part["inlineData"].get("data", ""))
                            log.debug(f"    part[{j}]: inlineData ({mime}, {dlen} base64 chars)")
                        elif ptype == "text":
                            log.debug(f"    part[{j}]: text ({len(part['text'])} chars): {part['text'][:100]}")

            return parsed
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass
        log.debug(f"HTTP error after {elapsed:.1f}s: {e.code} {e.reason}")
        log.debug(f"Error response headers: {dict(e.headers) if hasattr(e, 'headers') else 'N/A'}")
        log.debug(f"Error response body: {error_body[:1000]}")
        # Surface Cloudflare AI Gateway diagnostics (cf-aig-* + CF-RAY) in the error
        # itself, so an auth/guardrail failure (e.g. 2009 Unauthorized) is debuggable
        # without re-running under --debug.
        cf_diag = ""
        if hasattr(e, "headers") and e.headers:
            cf_hdrs = {
                k: v for k, v in e.headers.items()
                if k.lower().startswith("cf-aig-") or k.lower() == "cf-ray"
            }
            if cf_hdrs:
                cf_diag = f"\nCloudflare: {json.dumps(cf_hdrs)}"
        raise RuntimeError(
            f"HTTP {e.code}: {e.reason}\n{error_body}{cf_diag}"
        ) from e
    except urllib.error.URLError as e:
        elapsed = time.time() - start_time
        log.debug(f"URL error after {elapsed:.1f}s: {e.reason}")
        raise RuntimeError(f"Connection error: {e.reason}") from e
    except TimeoutError:
        elapsed = time.time() - start_time
        log.debug(f"Request timed out after {elapsed:.1f}s (limit: {timeout}s)")
        raise RuntimeError(f"Request timed out after {timeout}s")


def extract_image_openrouter(response: dict) -> tuple[bytes, str]:
    """Extract base64 image data from OpenRouter response.

    Args:
        response: Parsed JSON response from OpenRouter API.

    Returns:
        Tuple of (image_bytes, text_content) where image_bytes is the decoded
        PNG data and text_content is any accompanying model text.

    Raises:
        RuntimeError: If no image data found in response.
    """
    choices = response.get("choices", [])
    if not choices:
        error = response.get("error", {})
        if error:
            msg = error.get("message", str(error))
            raise RuntimeError(f"API error: {msg}")
        raise RuntimeError(f"No choices in response: {json.dumps(response)[:500]}")

    message = choices[0].get("message", {})
    text_content = message.get("content", "")
    images = message.get("images", [])

    if not images:
        raise RuntimeError(
            f"No images in response. Model text: {text_content or '(empty)'}"
        )

    data_url = images[0]["image_url"]["url"]
    log.debug(f"Image data URL prefix: {data_url[:60]}...")
    log.debug(f"Image data URL total length: {len(data_url)} chars")

    # Strip data URL prefix: "data:image/png;base64,..."
    if "," in data_url:
        b64_data = data_url.split(",", 1)[1]
    else:
        b64_data = data_url

    image_bytes = base64.b64decode(b64_data)
    log.info(f"Decoded image: {len(image_bytes)} bytes ({len(b64_data)} base64 chars)")
    return image_bytes, text_content


def extract_image_google(response: dict) -> tuple[bytes, str]:
    """Extract base64 image data from Google AI Studio response.

    Args:
        response: Parsed JSON response from Google generateContent API.

    Returns:
        Tuple of (image_bytes, text_content) where image_bytes is the decoded
        PNG data and text_content is any accompanying model text.

    Raises:
        RuntimeError: If no image data found or prompt was blocked by safety filter.
    """
    candidates = response.get("candidates", [])
    if not candidates:
        block_reason = response.get("promptFeedback", {}).get("blockReason", "")
        if block_reason:
            raise RuntimeError(f"Prompt blocked by safety filter: {block_reason}")
        raise RuntimeError(f"No candidates in response: {json.dumps(response)[:500]}")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("No parts in response candidate")

    image_bytes = None
    text_content = ""

    for i, part in enumerate(parts):
        if "inlineData" in part:
            b64_data = part["inlineData"]["data"]
            mime_type = part["inlineData"].get("mimeType", "unknown")
            log.debug(f"Found inlineData in part[{i}]: {mime_type}, {len(b64_data)} base64 chars")
            image_bytes = base64.b64decode(b64_data)
            log.info(f"Decoded image: {len(image_bytes)} bytes")
        elif "text" in part:
            text_content = part["text"]
            log.debug(f"Found text in part[{i}]: {text_content[:200]}")

    if image_bytes is None:
        raise RuntimeError(
            f"No image data in response parts. Text: {text_content or '(empty)'}"
        )

    return image_bytes, text_content


def extract_text_openrouter(response: dict) -> str:
    """Extract text-only content from OpenRouter response (analyze mode).

    Args:
        response: Parsed JSON response from OpenRouter API.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If no text content found in response.
    """
    choices = response.get("choices", [])
    if not choices:
        error = response.get("error", {})
        if error:
            msg = error.get("message", str(error))
            raise RuntimeError(f"API error: {msg}")
        raise RuntimeError(f"No choices in response: {json.dumps(response)[:500]}")

    message = choices[0].get("message", {})
    raw_content = message.get("content", "")

    # OpenRouter/OpenAI allow `content` to be either a plain string or an array of
    # content parts (e.g. [{"type":"text","text":"..."}]). Normalize both to a string
    # so callers always receive text, never a list.
    if isinstance(raw_content, list):
        text_content = "".join(
            part.get("text", "")
            for part in raw_content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    else:
        text_content = raw_content

    if not text_content:
        raise RuntimeError("No text content in response (empty model reply)")

    log.info(f"Extracted text: {len(text_content)} chars")
    return text_content


def extract_text_google(response: dict) -> str:
    """Extract text-only content from Google AI Studio response (analyze mode).

    Args:
        response: Parsed JSON response from Google generateContent API.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If no text content found or prompt was blocked.
    """
    candidates = response.get("candidates", [])
    if not candidates:
        block_reason = response.get("promptFeedback", {}).get("blockReason", "")
        if block_reason:
            raise RuntimeError(f"Prompt blocked by safety filter: {block_reason}")
        raise RuntimeError(f"No candidates in response: {json.dumps(response)[:500]}")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("No parts in response candidate")

    text_parts = [part["text"] for part in parts if "text" in part]
    if not text_parts:
        raise RuntimeError("No text content in response parts")

    text_content = "\n".join(text_parts)
    log.info(f"Extracted text: {len(text_content)} chars")
    return text_content


def find_imagemagick() -> str | None:
    """Find ImageMagick binary (magick for v7, convert for v6).

    Returns:
        Path to binary, or None if not found.
    """
    for cmd in ("magick", "convert"):
        path = shutil.which(cmd)
        if path:
            log.debug(f"Found ImageMagick: {cmd} at {path}")
            return cmd
    return None


def check_ffmpeg_despill() -> bool:
    """Check if FFmpeg supports the despill filter (requires 4.3+).

    Returns:
        True if despill is available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-filters"],
            capture_output=True, text=True, timeout=10,
        )
        return "despill" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def process_transparent(input_path: Path, output_path: Path) -> None:
    """Remove green screen background and trim transparent padding.

    3-step pipeline:
    1. FFmpeg chroma key — removes green background pixels
    2. FFmpeg despill — removes green fringe from edges (if available)
    3. ImageMagick trim — crops transparent padding

    Args:
        input_path: Path to the raw generated image (with green background).
        output_path: Final output path for the transparent image.

    Raises:
        RuntimeError: If required tools are missing or processing fails.
    """
    # Check tool availability
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError(
            "Transparent mode requires FFmpeg. Install with: brew install ffmpeg"
        )

    magick_cmd = find_imagemagick()
    if not magick_cmd:
        raise RuntimeError(
            "Transparent mode requires ImageMagick. Install with: brew install imagemagick"
        )

    has_despill = check_ffmpeg_despill()

    # Step 1+2: FFmpeg chroma key (+ despill if available)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_keyed:
        tmp_keyed_path = Path(tmp_keyed.name)

    try:
        if has_despill:
            vf = "colorkey=0x00FF00:0.3:0.15,despill=green"
        else:
            print("WARNING: FFmpeg despill filter not available (requires 4.3+). "
                  "Green fringe removal skipped.", file=sys.stderr)
            vf = "colorkey=0x00FF00:0.3:0.15"

        log.info(f"FFmpeg chroma key: {vf}")
        result = subprocess.run(
            ["ffmpeg", "-i", str(input_path), "-vf", vf, "-y", str(tmp_keyed_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg chroma key failed: {result.stderr[-500:]}")

        # Step 3: ImageMagick trim transparent padding
        log.info("ImageMagick trim")
        trim_args = [magick_cmd]
        if magick_cmd == "magick":
            trim_args += [str(tmp_keyed_path), "-fuzz", "15%", "-trim", "+repage", str(output_path)]
        else:
            # ImageMagick 6 (convert)
            trim_args += [str(tmp_keyed_path), "-fuzz", "15%", "-trim", "+repage", str(output_path)]

        result = subprocess.run(trim_args, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"ImageMagick trim failed: {result.stderr[-500:]}")

        print("Transparent background processing complete.", file=sys.stderr)

    finally:
        # Cleanup temp file
        tmp_keyed_path.unlink(missing_ok=True)


def _fmt_ts(seconds: float) -> str:
    """Format a second offset as M:SS for frame labels."""
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def _ffprobe_duration(video_path: Path) -> float | None:
    """Return the video duration in seconds via ffprobe, or None if unavailable."""
    if not shutil.which("ffprobe"):
        return None
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return None


def extract_keyframes(
    video_path: Path,
    out_dir: Path,
    count: int = 12,
    min_count: int = 4,
    max_count: int = 24,
    max_width: int = 480,
) -> list[tuple[float, Path]] | None:
    """Extract evenly-spaced keyframes (including first & last) as JPEGs.

    Uniform sampling with min/max caps — deliberately NOT scene-detect, which
    mis-fires (0 frames on static clips, hundreds on fast cuts) precisely on the
    stylized/AI footage this is meant to ground-truth.

    Args:
        video_path: Local video file.
        out_dir: Directory to write frames into (created if needed).
        count: Target number of frames; clamped to [min_count, max_count].
        max_width: Frames are downscaled to this width (aspect preserved).

    Returns:
        List of (timestamp_seconds, frame_path) in chronological order, or None
        if ffmpeg is not installed (caller should warn and continue, not exit).
    """
    if not shutil.which("ffmpeg"):
        return None
    count = max(min_count, min(max_count, count))
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = _ffprobe_duration(video_path)
    vf = f"scale={max_width}:-1"

    if duration and duration > 0:
        # Evenly spaced including both endpoints; nudge the final sample just
        # inside the end so the seek lands on a real frame.
        if count == 1:
            timestamps = [0.0]
        else:
            step = duration / (count - 1)
            last = max(0.0, duration - 0.05)
            timestamps = [min(i * step, last) for i in range(count)]
        frames: list[tuple[float, Path]] = []
        for i, ts in enumerate(timestamps):
            fp = out_dir / f"kf_{i:04d}.jpg"
            result = subprocess.run(
                ["ffmpeg", "-ss", f"{ts:.3f}", "-i", str(video_path),
                 "-frames:v", "1", "-vf", vf, "-q:v", "3", "-y", str(fp)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and fp.is_file():
                frames.append((ts, fp))
            else:
                log.debug(f"keyframe extract failed @ {ts:.2f}s: {result.stderr[-200:]}")
        return frames or None

    # No ffprobe/duration: single-pass 1fps extraction, capped with -frames:v so
    # a long clip can't explode into thousands of stills. Timestamps assume 1fps.
    log.debug("No ffprobe duration; falling back to 1fps capped extraction")
    result = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vf", f"fps=1,{vf}",
         "-frames:v", str(max_count), "-q:v", "3", "-y", str(out_dir / "kf_%04d.jpg")],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        log.debug(f"fps fallback extract failed: {result.stderr[-200:]}")
        return None
    paths = sorted(out_dir.glob("kf_*.jpg"))
    return [(float(i), p) for i, p in enumerate(paths)] or None


def build_contact_sheet(
    frames: list[tuple[float, Path]],
    out_path: Path,
    columns: int = 4,
) -> bool:
    """Tile keyframes into a single contact-sheet image (chronological order,
    left→right, top→bottom).

    Prefers ImageMagick `montage` (adds per-tile M:SS timestamp labels); falls
    back to ffmpeg's `tile` filter (unlabeled) so the only hard dependency is
    ffmpeg. Returns True on success, False if neither tool could produce a sheet.
    """
    if not frames:
        return False
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    columns = max(1, min(columns, len(frames)))

    magick = find_imagemagick()
    montage_cmd: list[str] | None = None
    if magick == "magick":
        montage_cmd = ["magick", "montage"]
    elif shutil.which("montage"):
        montage_cmd = ["montage"]

    if montage_cmd:
        args_list = list(montage_cmd)
        for ts, fp in frames:
            args_list += ["-label", _fmt_ts(ts), str(fp)]
        args_list += ["-tile", f"{columns}x", "-geometry", "+6+6",
                      "-background", "white", str(out_path)]
        try:
            result = subprocess.run(args_list, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and out_path.is_file():
                return True
            log.debug(f"montage failed: {result.stderr[-300:]}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.debug(f"montage error: {e}")

    # Fallback: ffmpeg tile (unlabeled). Copy frames into a temp dir under a
    # sequential pattern so the image2 demuxer reads them in order.
    if not shutil.which("ffmpeg"):
        return False
    rows = (len(frames) + columns - 1) // columns
    tmp = Path(tempfile.mkdtemp(prefix="aivc_tile_"))
    try:
        for i, (_, fp) in enumerate(frames):
            shutil.copy(fp, tmp / f"tile_{i:04d}.jpg")
        result = subprocess.run(
            ["ffmpeg", "-framerate", "1", "-start_number", "0",
             "-i", str(tmp / "tile_%04d.jpg"), "-frames:v", "1",
             "-vf", f"tile={columns}x{rows}:padding=6:color=white",
             "-update", "1", "-y", str(out_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log.debug(f"ffmpeg tile failed: {result.stderr[-300:]}")
        return result.returncode == 0 and out_path.is_file()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def get_costs_path() -> Path:
    """Get project-level costs file path.

    Returns:
        Path to .ai-image-creator/costs.json in current working directory.
    """
    return Path.cwd() / ".ai-image-creator" / "costs.json"


def log_cost_entry(
    response: dict[str, Any],
    provider: str,
    model: str,
    mode: str,
    aspect_ratio: str | None,
    image_size: str | None,
    output_file: str,
    size_bytes: int,
    elapsed_seconds: float,
) -> None:
    """Append a cost entry to the project-level costs file.

    Only stores non-sensitive operational data. Never stores API keys, tokens,
    account IDs, or any credentials.

    Args:
        response: Raw API response dict (for extracting token usage).
        provider: 'openrouter' or 'google'.
        model: Full model ID.
        mode: 'gateway' or 'direct'.
        aspect_ratio: Aspect ratio used, or None.
        image_size: Image size used, or None.
        output_file: Output file path string.
        size_bytes: Size of generated image in bytes.
        elapsed_seconds: Total generation time.
    """
    costs_path = get_costs_path()

    # Extract token usage (provider-specific format)
    token_usage: dict[str, int] = {}
    if provider == "openrouter":
        usage = response.get("usage", {})
        if usage:
            token_usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
    else:
        # Google AI Studio format
        usage = response.get("usageMetadata", {})
        if usage:
            token_usage = {
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            }

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "provider": provider,
        "mode": mode,
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
        "output_file": output_file,
        "size_bytes": size_bytes,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "token_usage": token_usage,
    }

    # Read existing entries
    costs_path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    if costs_path.exists():
        try:
            entries = json.loads(costs_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning(f"Could not read {costs_path}, starting fresh")

    entries.append(entry)
    # Atomic write: temp file + rename to prevent corruption on Ctrl-C
    import tempfile as _tf
    with _tf.NamedTemporaryFile("w", dir=str(costs_path.parent), delete=False, suffix=".tmp") as f:
        f.write(json.dumps(entries, indent=2) + "\n")
        tmp_path = Path(f.name)
    tmp_path.replace(costs_path)
    log.info(f"Cost entry logged to {costs_path}")

    # Warn about .gitignore if applicable
    gitignore = Path.cwd() / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if ".ai-image-creator" not in content:
            print(
                "TIP: Consider adding '.ai-image-creator/' to .gitignore",
                file=sys.stderr,
            )


def display_costs() -> None:
    """Display cost/generation history grouped by model.

    Reads .ai-image-creator/costs.json from CWD and prints a formatted summary.
    """
    costs_path = get_costs_path()
    if not costs_path.exists():
        print("No cost history found for this project.", file=sys.stderr)
        print(f"Expected: {costs_path}", file=sys.stderr)
        sys.exit(0)

    try:
        entries = json.loads(costs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: Could not read costs file: {e}", file=sys.stderr)
        sys.exit(1)

    if not entries:
        print("No generation entries recorded.", file=sys.stderr)
        sys.exit(0)

    # Group by model
    by_model: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        model = entry.get("model", "unknown")
        by_model.setdefault(model, []).append(entry)

    print(f"\nGeneration History ({len(entries)} total)")
    print(f"Project: {Path.cwd()}")
    print("=" * 60)

    total_tokens = 0
    total_time = 0.0

    for model, model_entries in sorted(by_model.items()):
        model_tokens = sum(
            e.get("token_usage", {}).get("total_tokens", 0) for e in model_entries
        )
        model_time = sum(e.get("elapsed_seconds", 0) for e in model_entries)
        total_tokens += model_tokens
        total_time += model_time

        print(f"\n  {model}")
        print(f"    Generations: {len(model_entries)}")
        print(f"    Total tokens: {model_tokens:,}")
        print(f"    Total time: {model_time:.1f}s")

        # Show last 3 entries
        for entry in model_entries[-3:]:
            ts = entry.get("timestamp", "?")[:19]
            out = entry.get("output_file", "?")
            size = entry.get("size_bytes", 0)
            print(f"      {ts}  {out} ({size / 1024:.1f} KB)")

    print(f"\n{'=' * 60}")
    print(f"  Total: {len(entries)} generations, {total_tokens:,} tokens, {total_time:.1f}s")
    print()


def main() -> None:
    """Main entry point — parse args, generate image, write output."""
    args = parse_args()

    # Configure logging
    setup_logging(debug=args.debug, verbose=args.verbose)

    log.debug("=" * 60)
    log.debug("AI Image Creator — Debug Session")
    log.debug(f"Python: {sys.version}")
    log.debug(f"Script: {__file__}")
    log.debug(f"CWD: {os.getcwd()}")
    log.debug(f"Args: {vars(args)}")
    log.debug("=" * 60)

    # Handle --costs (display and exit)
    if args.costs:
        display_costs()
        sys.exit(0)

    # Handle --list-models
    if args.list_models:
        print("Image generation model keywords:")
        for kw, info in MODEL_REGISTRY.items():
            default = " (default)" if info["id"] == DEFAULT_MODELS.get("openrouter") else ""
            print(f"  {kw:12s} -> {info['id']}{default}")
            print(f"               {info['description']}")
            print(f"               modalities: {', '.join(info['modalities'])}")
        print("\nVideo analysis model keywords (--analyze-video, cheapest first):")
        for kw, info in VIDEO_MODEL_REGISTRY.items():
            default = " (default)" if kw == DEFAULT_VIDEO_MODEL else ""
            print(f"  {kw:18s} -> {info['id']}{default}")
            print(f"               {info['description']}")
            print(f"               ${info['in']}/${info['out']} per 1M tok in/out, {info['ctx']} ctx")
        print("\nVideo presets:")
        for alias, kw in VIDEO_MODEL_PRESETS.items():
            print(f"  {alias:18s} -> {kw} ({VIDEO_MODEL_REGISTRY[kw]['id']})")
        sys.exit(0)

    # Validate --analyze mode
    if args.analyze:
        if not args.ref:
            print("ERROR: --analyze requires at least one reference image (-r)", file=sys.stderr)
            sys.exit(1)
        if args.transparent:
            print("ERROR: --analyze is incompatible with --transparent", file=sys.stderr)
            sys.exit(1)
        if args.aspect_ratio or args.image_size:
            print("ERROR: --analyze is incompatible with --aspect-ratio / --image-size", file=sys.stderr)
            sys.exit(1)

    # Validate --analyze-video mode
    if args.analyze_video:
        if args.analyze:
            print("ERROR: --analyze and --analyze-video are mutually exclusive", file=sys.stderr)
            sys.exit(1)
        if not args.ref:
            print("ERROR: --analyze-video requires a video via -r (file path or URL)", file=sys.stderr)
            sys.exit(1)
        if len(args.ref) != 1:
            print("ERROR: --analyze-video accepts exactly one video source (-r)", file=sys.stderr)
            sys.exit(1)
        if args.provider != "openrouter":
            print("ERROR: --analyze-video requires --provider openrouter (video models are OpenRouter-only)", file=sys.stderr)
            sys.exit(1)
        if args.transparent:
            print("ERROR: --analyze-video is incompatible with --transparent", file=sys.stderr)
            sys.exit(1)
        if args.aspect_ratio or args.image_size:
            print("ERROR: --analyze-video is incompatible with --aspect-ratio / --image-size", file=sys.stderr)
            sys.exit(1)

    if args.prose and not args.analyze_video:
        print("ERROR: --prose only applies to --analyze-video", file=sys.stderr)
        sys.exit(1)

    if args.contact_sheet and not args.analyze_video:
        print("ERROR: --contact-sheet only applies to --analyze-video", file=sys.stderr)
        sys.exit(1)

    if args.verify and not args.analyze_video:
        print("ERROR: --verify only applies to --analyze-video", file=sys.stderr)
        sys.exit(1)

    # Structured JSON is the default for --analyze-video; --prose opts out.
    video_json_mode = args.analyze_video and not args.prose

    # Validate --output is provided (required unless --list-models, --costs, --analyze, or --analyze-video)
    if not args.output and not args.analyze and not args.analyze_video:
        print("ERROR: --output is required (unless using --list-models, --costs, --analyze, or --analyze-video)", file=sys.stderr)
        sys.exit(1)

    # Validate output path
    output_path = Path(args.output) if args.output else None
    if output_path and output_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        print(
            "WARNING: Output file does not have an image extension. "
            "The generated file will be PNG format regardless of extension.",
            file=sys.stderr,
        )

    # Resolve model and modalities
    if args.analyze_video:
        model = resolve_video_model(args.model)
        modalities = ["text"]
    else:
        model, modalities = resolve_model(args.model, args.provider)

    # Normalize + validate image size at the CLI boundary (e.g. "2k" -> "2K").
    if args.image_size:
        size = args.image_size.strip().upper()
        if size not in SUPPORTED_IMAGE_SIZES:
            print(
                f"ERROR: invalid --image-size '{args.image_size}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_IMAGE_SIZES))}.",
                file=sys.stderr,
            )
            sys.exit(1)
        if size == "0.5K" and "preview" not in model:
            print(
                f"ERROR: --image-size 0.5K is only supported on the Gemini 3.1 Flash "
                f"preview build, not '{model}'. Use 1K/2K/4K, or pass "
                f"-m google/gemini-3.1-flash-image-preview-20260226.",
                file=sys.stderr,
            )
            sys.exit(1)
        args.image_size = size

    # Video source for --analyze-video (a file path or URL passed via -r).
    # Kept separate from the image ref_images plumbing below.
    video_source: str | None = None
    if args.analyze_video:
        vsrc = str(args.ref[0])
        if not vsrc.startswith(("http://", "https://")):
            vpath = Path(vsrc)
            # is_file() (not exists()) so a directory/special file fails here with
            # a clear error instead of an uncaught IsADirectoryError at read time.
            if not vpath.is_file():
                print(
                    f"ERROR: Video file not found (or not a regular file): {vsrc}\n"
                    f"  (if this is a URL, prefix it with http:// or https://)",
                    file=sys.stderr,
                )
                sys.exit(1)
            if vpath.suffix.lower() not in VIDEO_MIME_MAP:
                print(f"WARNING: Unusual video extension: {vsrc}", file=sys.stderr)
            size_bytes = vpath.stat().st_size
            if size_bytes == 0:
                print(f"ERROR: Video file is empty: {vsrc}", file=sys.stderr)
                sys.exit(1)
            size_mb = size_bytes / (1024 * 1024)
            if size_mb > 20:
                print(
                    f"WARNING: Video is {size_mb:.1f} MB — large base64 payloads may be "
                    f"rejected or slow. Consider a hosted URL or a shorter/lower-res clip.",
                    file=sys.stderr,
                )
        video_source = vsrc
        print(f"Video source: {vsrc}", file=sys.stderr)

    # Frame grounding for --contact-sheet / --verify: extract keyframes once and
    # build a contact sheet. Local files only (ffmpeg cannot read a remote URL
    # without downloading) — warn and skip otherwise. Never hard-exit on a
    # missing dep: grounding is an additive aid, the analysis itself proceeds.
    grounding_tmpdir: Path | None = None
    grounding_frames: list[tuple[float, Path]] | None = None
    grounding_sheet: Path | None = None
    if args.analyze_video and video_source and (args.contact_sheet or args.verify):
        which = " / ".join(
            f for f, on in (("--contact-sheet", args.contact_sheet), ("--verify", args.verify)) if on
        )
        is_url = video_source.startswith(("http://", "https://"))
        if is_url:
            print(f"WARNING: {which} needs local frames; skipped for a URL source.", file=sys.stderr)
        elif not shutil.which("ffmpeg"):
            print(f"WARNING: {which} requires ffmpeg (not found); skipping frame grounding.", file=sys.stderr)
        else:
            grounding_tmpdir = Path(tempfile.mkdtemp(prefix="aivc_kf_"))
            print("Extracting keyframes for grounding...", file=sys.stderr)
            grounding_frames = extract_keyframes(Path(video_source), grounding_tmpdir)
            if not grounding_frames:
                print("WARNING: keyframe extraction produced no frames; skipping grounding.", file=sys.stderr)
            else:
                sheet_target = Path(args.contact_sheet) if args.contact_sheet else (grounding_tmpdir / "contact_sheet.png")
                if build_contact_sheet(grounding_frames, sheet_target):
                    grounding_sheet = sheet_target
                    if args.contact_sheet:
                        print(f"Contact sheet ({len(grounding_frames)} frames): {sheet_target}", file=sys.stderr)
                else:
                    print("WARNING: contact sheet could not be built.", file=sys.stderr)

    # Validate reference images (image-generation / --analyze paths only)
    ref_images = [] if args.analyze_video else (args.ref or [])
    if ref_images:
        # Check model supports multimodal input
        if "text" not in modalities:
            print(
                f"ERROR: Reference images (-r) require a multimodal model. "
                f"'{model}' only supports image output.\n"
                f"Use --model gemini, geminipro, gpt5, or gpt5.4 for image editing/style transfer.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Validate all ref files exist
        for ref_path in ref_images:
            if not Path(ref_path).exists():
                print(f"ERROR: Reference image not found: {ref_path}", file=sys.stderr)
                sys.exit(1)
            if Path(ref_path).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                print(f"WARNING: Unusual image extension: {ref_path}", file=sys.stderr)

        print(f"Reference images: {len(ref_images)} file(s)", file=sys.stderr)

    # Validate transparent mode tools
    if args.transparent:
        if not shutil.which("ffmpeg"):
            print("ERROR: Transparent mode requires FFmpeg. Install with: brew install ffmpeg", file=sys.stderr)
            sys.exit(1)
        if not find_imagemagick():
            print("ERROR: Transparent mode requires ImageMagick. Install with: brew install imagemagick", file=sys.stderr)
            sys.exit(1)
        print("Transparent mode: enabled", file=sys.stderr)

    # Default prompt for analyze / analyze-video mode (if user didn't provide one)
    if (args.analyze or args.analyze_video) and not args.prompt and not args.prompt_file:
        default_prompt_path = Path(__file__).parent.parent / "tmp" / "prompt.txt"
        if not default_prompt_path.exists():
            if args.analyze_video:
                args.prompt = DEFAULT_VIDEO_PROMPT_JSON if video_json_mode else DEFAULT_VIDEO_PROMPT_PROSE
                log.debug(f"Using default analyze-video prompt ({'json' if video_json_mode else 'prose'})")
            else:
                args.prompt = (
                    "Describe this image in detail. Include the subject, style, colors, "
                    "composition, mood, and any text visible in the image."
                )
                log.debug("Using default analyze prompt")

    # Resolve prompt
    prompt = resolve_prompt(args)

    # Inject green screen instructions for transparent mode
    if args.transparent:
        prompt += (
            "\n\nIMPORTANT: Place the subject on a perfectly solid, flat, bright green "
            "background (#00FF00). No shadows, no gradients, no floor reflections — "
            "just pure #00FF00 green everywhere behind the subject."
        )

    # In JSON mode, ensure a user-supplied prompt still carries the schema/anti-
    # confabulation guidance (the default JSON prompt already includes it).
    if video_json_mode and prompt != DEFAULT_VIDEO_PROMPT_JSON:
        prompt += VIDEO_JSON_DIRECTIVE

    # Override modalities for analyze mode (text-only output)
    if args.analyze:
        modalities = ["text"]
        print("Mode: analyze (text-only output)", file=sys.stderr)
    elif args.analyze_video:
        modalities = ["text"]
        print(f"Mode: analyze-video ({'structured JSON' if video_json_mode else 'prose'} output)", file=sys.stderr)

    print(f"Provider: {args.provider}", file=sys.stderr)
    print(f"Model: {model}", file=sys.stderr)
    print(f"Modalities: {', '.join(modalities)}", file=sys.stderr)
    print(f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}", file=sys.stderr)
    if args.aspect_ratio:
        print(f"Aspect ratio: {args.aspect_ratio}", file=sys.stderr)
    if args.image_size:
        print(f"Image size: {args.image_size}", file=sys.stderr)

    # Detect mode
    mode, config = detect_mode(args.provider)
    print(f"Mode: {mode}", file=sys.stderr)

    # Build request
    if mode == "gateway":
        url = build_gateway_url(args.provider, model, config)
    else:
        url = build_direct_url(args.provider, model)

    headers = build_headers(args.provider, mode, config)
    body = build_request_body(
        args.provider, model, prompt, args.aspect_ratio, args.image_size,
        modalities=modalities,
        ref_images=ref_images if ref_images else None,
        video_source=video_source,
        json_schema=VIDEO_JSON_SCHEMA if video_json_mode else None,
    )

    print(f"URL: {url}", file=sys.stderr)
    if args.analyze_video:
        print("Analyzing video (this may take a few minutes for large clips)...", file=sys.stderr)
    elif args.analyze:
        print("Analyzing image (this may take up to 2 minutes)...", file=sys.stderr)
    else:
        print("Generating image (this may take up to 2 minutes)...", file=sys.stderr)

    # Make request with fallback
    total_start = time.time()
    response = None
    try:
        response = make_request(url, headers, body)
    except RuntimeError as e:
        if mode == "gateway" and config.get("direct_key"):
            print(
                f"Gateway request failed: {e}\nFalling back to direct API...",
                file=sys.stderr,
            )
            log.info("Initiating fallback to direct API")
            url = build_direct_url(args.provider, model)
            headers = build_headers(args.provider, "direct", config)
            try:
                response = make_request(url, headers, body)
                # Reflect the actual transport used, so the cost log and result
                # JSON report "direct" (not the failed "gateway") after fallback.
                mode = "direct"
            except RuntimeError as e2:
                print(f"ERROR: Direct API also failed: {e2}", file=sys.stderr)
                log.debug(f"Both gateway and direct failed. Total time: {time.time() - total_start:.1f}s")
                if grounding_tmpdir:
                    shutil.rmtree(grounding_tmpdir, ignore_errors=True)
                sys.exit(1)
        else:
            print(f"ERROR: {e}", file=sys.stderr)
            log.debug(f"Request failed. Total time: {time.time() - total_start:.1f}s")
            if grounding_tmpdir:
                shutil.rmtree(grounding_tmpdir, ignore_errors=True)
            sys.exit(1)

    # --- Analyze / analyze-video mode: extract text only, no image ---
    if args.analyze or args.analyze_video:
        total_elapsed = time.time() - total_start
        try:
            if args.provider == "openrouter":
                analysis_text = extract_text_openrouter(response)
            else:
                analysis_text = extract_text_google(response)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            log.debug(f"Text extraction failed. Raw response keys: {list(response.keys()) if response else 'None'}")
            if grounding_tmpdir:
                shutil.rmtree(grounding_tmpdir, ignore_errors=True)
            sys.exit(1)

        print(f"\nAnalysis complete ({total_elapsed:.1f}s)", file=sys.stderr)
        log.info(f"Total elapsed: {total_elapsed:.1f}s")

        # In structured-JSON mode the model returns a JSON string; parse it so the
        # result's `analysis` is a structured object. If a model ignored the schema
        # and returned non-JSON, keep the raw text and flag structured=false.
        analysis_payload: Any = analysis_text
        structured_ok = False
        if video_json_mode:
            try:
                analysis_payload = json.loads(analysis_text)
                structured_ok = True
            except (json.JSONDecodeError, TypeError):
                print(
                    "WARNING: structured-JSON mode but response was not valid JSON; "
                    "returning raw text (structured=false). Try --prose, or retry.",
                    file=sys.stderr,
                )
                log.debug(f"JSON parse failed; raw head: {str(analysis_text)[:200]}")

        # Log cost entry
        try:
            log_cost_entry(
                response=response,
                provider=args.provider,
                model=model,
                mode=mode,
                aspect_ratio=None,
                image_size=None,
                output_file="(analyze-video)" if args.analyze_video else "(analyze)",
                size_bytes=0,
                elapsed_seconds=total_elapsed,
            )
        except OSError as e:
            log.warning(f"Could not log cost entry: {e}")

        # --- Optional second pass: verify the analysis against still frames ---
        verification: Any = None
        verification_ok = False
        if args.verify:
            if not grounding_sheet or not grounding_frames:
                print("WARNING: --verify skipped (no extracted frames available).", file=sys.stderr)
            else:
                # Send the contact sheet plus up to 6 evenly-spaced full frames.
                # No video is re-sent — re-sending it would just re-confabulate
                # from the same pixels rather than check the claims.
                step = max(1, len(grounding_frames) // 6)
                picked = grounding_frames[::step][:6]
                legend = ", ".join(f"frame@{_fmt_ts(ts)}" for ts, _ in picked)
                analysis_str = (
                    json.dumps(analysis_payload, indent=2)
                    if structured_ok else str(analysis_payload)
                )
                vprompt = VERIFY_PROMPT_HEADER.format(timestamps=legend, analysis=analysis_str)
                vimages = [str(grounding_sheet)] + [str(p) for _, p in picked]
                print(f"Verifying analysis against {len(vimages)} frame image(s)...", file=sys.stderr)
                vbody = build_request_body(
                    args.provider, model, vprompt,
                    analysis_images=vimages,
                    json_schema=VERIFY_JSON_SCHEMA,
                )
                vstart = time.time()
                try:
                    vresponse = make_request(url, headers, vbody)
                    vtext = extract_text_openrouter(vresponse)
                    try:
                        verification = json.loads(vtext)
                        verification_ok = True
                    except (json.JSONDecodeError, TypeError):
                        verification = vtext
                        print("WARNING: verify pass returned non-JSON; keeping raw text.", file=sys.stderr)
                    velapsed = time.time() - vstart
                    print(f"Verification complete ({velapsed:.1f}s)", file=sys.stderr)
                    try:
                        log_cost_entry(
                            response=vresponse, provider=args.provider, model=model,
                            mode=mode, aspect_ratio=None, image_size=None,
                            output_file="(verify)", size_bytes=0, elapsed_seconds=velapsed,
                        )
                    except OSError as e:
                        log.warning(f"Could not log verify cost entry: {e}")
                except RuntimeError as e:
                    print(f"WARNING: --verify pass failed: {e}", file=sys.stderr)

        # Clean up extracted-frame temp dir (the saved --contact-sheet lives
        # outside it, so it survives). Done before exit; SystemExit still runs no
        # further code here, so unlink explicitly.
        if grounding_tmpdir:
            shutil.rmtree(grounding_tmpdir, ignore_errors=True)

        # Print machine-readable output to stdout
        result: dict[str, Any] = {
            "ok": True,
            "analyze": True,
            "analysis": analysis_payload,
            "provider": args.provider,
            "model": model,
            "mode": mode,
            "elapsed_seconds": round(total_elapsed, 1),
        }
        if args.analyze_video:
            result["analyze_video"] = True
            result["structured"] = structured_ok
            result["video_source"] = video_source
            if args.contact_sheet and grounding_sheet:
                result["contact_sheet"] = str(grounding_sheet)
            if args.verify:
                result["verification"] = verification
                result["verification_structured"] = verification_ok
        else:
            result["ref_images"] = len(ref_images)
        log.debug(f"Result JSON: {json.dumps(result, indent=2)}")
        print(json.dumps(result))
        sys.exit(0)

    # --- Image generation mode ---

    # Extract image
    try:
        if args.provider == "openrouter":
            image_bytes, text_content = extract_image_openrouter(response)
        else:
            image_bytes, text_content = extract_image_google(response)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        log.debug(f"Image extraction failed. Raw response keys: {list(response.keys()) if response else 'None'}")
        sys.exit(1)

    # Write output (or process transparent mode)
    assert output_path is not None  # guaranteed by validation above
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.transparent:
        # Write to temp file, then process through transparent pipeline
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_raw:
            tmp_raw_path = Path(tmp_raw.name)
        try:
            tmp_raw_path.write_bytes(image_bytes)
            process_transparent(tmp_raw_path, output_path)
            # Re-read the processed file for size reporting
            image_bytes = output_path.read_bytes()
        finally:
            tmp_raw_path.unlink(missing_ok=True)
    else:
        output_path.write_bytes(image_bytes)

    total_elapsed = time.time() - total_start

    # Save prompt alongside image as .prompt.md
    prompt_path = output_path.with_suffix(".prompt.md")
    try:
        prompt_meta = f"# Prompt\n\n"
        prompt_meta += f"- **Model:** {model}\n"
        prompt_meta += f"- **Provider:** {args.provider} ({mode})\n"
        if args.aspect_ratio:
            prompt_meta += f"- **Aspect ratio:** {args.aspect_ratio}\n"
        if args.image_size:
            prompt_meta += f"- **Image size:** {args.image_size}\n"
        if args.transparent:
            prompt_meta += f"- **Transparent:** yes\n"
        if ref_images:
            prompt_meta += f"- **Reference images:** {', '.join(ref_images)}\n"
        prompt_meta += f"- **Elapsed:** {total_elapsed:.1f}s\n"
        prompt_meta += f"\n## Prompt Text\n\n{prompt}\n"
        prompt_path.write_text(prompt_meta, encoding="utf-8")
        log.info(f"Prompt saved: {prompt_path}")
    except OSError as e:
        log.warning(f"Could not save prompt file: {e}")

    # Report success
    size_kb = len(image_bytes) / 1024
    print(f"\nImage saved: {output_path} ({size_kb:.1f} KB)", file=sys.stderr)
    if args.transparent:
        print("  (transparent background)", file=sys.stderr)
    if text_content:
        print(f"Model notes: {text_content}", file=sys.stderr)
    log.info(f"Total elapsed: {total_elapsed:.1f}s")
    log.debug(f"Output file: {output_path.resolve()}")
    log.debug(f"File size: {len(image_bytes)} bytes ({size_kb:.1f} KB)")

    # Log cost entry
    try:
        log_cost_entry(
            response=response,
            provider=args.provider,
            model=model,
            mode=mode,
            aspect_ratio=args.aspect_ratio,
            image_size=args.image_size,
            output_file=str(output_path),
            size_bytes=len(image_bytes),
            elapsed_seconds=total_elapsed,
        )
    except OSError as e:
        log.warning(f"Could not log cost entry: {e}")

    # Print machine-readable output to stdout
    result = {
        "ok": True,
        "output": str(output_path),
        "size_bytes": len(image_bytes),
        "provider": args.provider,
        "model": model,
        "mode": mode,
        "elapsed_seconds": round(total_elapsed, 1),
        "transparent": args.transparent,
        "ref_images": len(ref_images),
    }
    log.debug(f"Result JSON: {json.dumps(result, indent=2)}")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
