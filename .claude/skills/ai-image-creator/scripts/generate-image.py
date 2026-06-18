#!/usr/bin/env python3
"""AI Image Generator — Generate PNG images via multiple OpenRouter models or Google AI Studio.

Supports multiple image generation models via keyword shortcuts:
    gemini     — Google Gemini 3.1 Flash (default, multimodal)
    geminipro  — Google Gemini 3 Pro (multimodal, highest quality)
    riverflow  — Sourceful Riverflow v2 Fast (image-only)
    flux2      — Black Forest Labs FLUX.2 Klein 4B (image-only)
    seedream   — ByteDance SeedDream 4.5 (image-only)
    gpt5       — OpenAI GPT-5 Image Mini (multimodal)

Routes through Cloudflare AI Gateway BYOK when configured, with automatic
fallback to direct API calls. Uses only Python stdlib (no pip dependencies).

Usage:
    uv run python generate-image.py --output path.png --prompt "description"
    uv run python generate-image.py --output path.png --model riverflow --prompt "description"
    uv run python generate-image.py --output path.png --prompt-file prompt.txt
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
        url = f"{base}/google-ai-studio/v1beta/models/{model}:generateContent"
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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
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

    Returns:
        Dict suitable for JSON serialization as request body.
    """
    refs = ref_images or []

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
        timeout: Request timeout in seconds (default: 120).

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
        raise RuntimeError(
            f"HTTP {e.code}: {e.reason}\n{error_body}"
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
    text_content = message.get("content", "")

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
        print("Available model keywords:")
        for kw, info in MODEL_REGISTRY.items():
            default = " (default)" if info["id"] == DEFAULT_MODELS.get("openrouter") else ""
            print(f"  {kw:12s} -> {info['id']}{default}")
            print(f"               {info['description']}")
            print(f"               modalities: {', '.join(info['modalities'])}")
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

    # Validate --output is provided (required unless --list-models, --costs, or --analyze)
    if not args.output and not args.analyze:
        print("ERROR: --output is required (unless using --list-models, --costs, or --analyze)", file=sys.stderr)
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
    model, modalities = resolve_model(args.model, args.provider)

    # Validate reference images
    ref_images = args.ref or []
    if ref_images:
        # Check model supports multimodal input
        if "text" not in modalities:
            print(
                f"ERROR: Reference images (-r) require a multimodal model. "
                f"'{model}' only supports image output.\n"
                f"Use --model gemini, geminipro, or gpt5 for image editing/style transfer.",
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

    # Default prompt for analyze mode (if user didn't provide one)
    if args.analyze and not args.prompt and not args.prompt_file:
        default_prompt_path = Path(__file__).parent.parent / "tmp" / "prompt.txt"
        if not default_prompt_path.exists():
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

    # Override modalities for analyze mode (text-only output)
    if args.analyze:
        modalities = ["text"]
        print("Mode: analyze (text-only output)", file=sys.stderr)

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
    )

    print(f"URL: {url}", file=sys.stderr)
    if args.analyze:
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
            except RuntimeError as e2:
                print(f"ERROR: Direct API also failed: {e2}", file=sys.stderr)
                log.debug(f"Both gateway and direct failed. Total time: {time.time() - total_start:.1f}s")
                sys.exit(1)
        else:
            print(f"ERROR: {e}", file=sys.stderr)
            log.debug(f"Request failed. Total time: {time.time() - total_start:.1f}s")
            sys.exit(1)

    # --- Analyze mode: extract text only, no image ---
    if args.analyze:
        total_elapsed = time.time() - total_start
        try:
            if args.provider == "openrouter":
                analysis_text = extract_text_openrouter(response)
            else:
                analysis_text = extract_text_google(response)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            log.debug(f"Text extraction failed. Raw response keys: {list(response.keys()) if response else 'None'}")
            sys.exit(1)

        print(f"\nAnalysis complete ({total_elapsed:.1f}s)", file=sys.stderr)
        log.info(f"Total elapsed: {total_elapsed:.1f}s")

        # Log cost entry
        try:
            log_cost_entry(
                response=response,
                provider=args.provider,
                model=model,
                mode=mode,
                aspect_ratio=None,
                image_size=None,
                output_file="(analyze)",
                size_bytes=0,
                elapsed_seconds=total_elapsed,
            )
        except OSError as e:
            log.warning(f"Could not log cost entry: {e}")

        # Print machine-readable output to stdout
        result = {
            "ok": True,
            "analyze": True,
            "analysis": analysis_text,
            "provider": args.provider,
            "model": model,
            "mode": mode,
            "elapsed_seconds": round(total_elapsed, 1),
            "ref_images": len(ref_images),
        }
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
