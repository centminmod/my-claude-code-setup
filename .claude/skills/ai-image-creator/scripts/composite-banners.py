# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Composite logo banners from JSON config using ImageMagick.

Generates pixel-perfect, color-consistent logo banners across multiple
standard sizes (IAB ads, social media headers, web assets). Composites
an existing logo/mark onto gradient or solid backgrounds with text.

No API calls, no network required — pure offline ImageMagick compositing.

Usage:
    uv run --script composite-banners.py --init
    uv run --script composite-banners.py --validate
    uv run --script composite-banners.py -c banner-config.json -o ./banners/
    uv run --script composite-banners.py -c banner-config.json -o ./banners/ -n hero-1920x600
    uv run --script composite-banners.py --list-presets
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

log = logging.getLogger("composite-banners")

# ── Preset dimensions (IAB / Social / Web) ─────────────────────────────

PRESET_DIMENSIONS = {
    # IAB Standard Ad Sizes
    "iab-leaderboard":         {"w": 728,  "h": 90,   "cat": "iab",     "layout": "horizontal-compact",
                                "logo_height_pct": 80, "title_size_pct": 38, "tagline_size_pct": 18},
    "iab-billboard":           {"w": 970,  "h": 250,  "cat": "iab",     "layout": "horizontal",
                                "logo_height_pct": 70, "title_size_pct": 16, "tagline_size_pct": 8},
    "iab-medium-rectangle":    {"w": 300,  "h": 250,  "cat": "iab",     "layout": "centered",
                                "logo_height_pct": 45, "title_size_pct": 10, "tagline_size_pct": 5.5},
    "iab-large-rectangle":     {"w": 336,  "h": 280,  "cat": "iab",     "layout": "centered",
                                "logo_height_pct": 45, "title_size_pct": 10, "tagline_size_pct": 5},
    "iab-half-page":           {"w": 300,  "h": 600,  "cat": "iab",     "layout": "centered",
                                "logo_height_pct": 30, "title_size_pct": 7, "tagline_size_pct": 4},
    "iab-skyscraper":          {"w": 160,  "h": 600,  "cat": "iab",     "layout": "centered",
                                "logo_height_pct": 18, "title_size_pct": 3.2, "tagline_size_pct": 2},
    "iab-mobile-banner":       {"w": 320,  "h": 50,   "cat": "iab",     "layout": "horizontal-compact",
                                "logo_height_pct": 80, "title_size_pct": 40, "tagline_size_pct": 0},
    "iab-mobile-interstitial": {"w": 320,  "h": 480,  "cat": "iab",     "layout": "centered",
                                "logo_height_pct": 35, "title_size_pct": 8, "tagline_size_pct": 4},
    # Social Media
    "social-twitter-header":   {"w": 1500, "h": 500,  "cat": "social",  "layout": "horizontal",
                                "logo_height_pct": 65, "title_size_pct": 12, "tagline_size_pct": 6},
    "social-linkedin-banner":  {"w": 1584, "h": 396,  "cat": "social",  "layout": "horizontal",
                                "logo_height_pct": 65, "title_size_pct": 14, "tagline_size_pct": 7},
    "social-facebook-cover":   {"w": 1640, "h": 624,  "cat": "social",  "layout": "horizontal",
                                "logo_height_pct": 60, "title_size_pct": 11, "tagline_size_pct": 5.5},
    "social-youtube-banner":   {"w": 2560, "h": 1440, "cat": "social",  "layout": "centered",
                                "logo_height_pct": 35, "title_size_pct": 6, "tagline_size_pct": 3},
    # Web Assets
    "web-hero":                {"w": 1920, "h": 600,  "cat": "website", "layout": "horizontal",
                                "logo_height_pct": 65, "title_size_pct": 12, "tagline_size_pct": 6},
    "web-og-social":           {"w": 1200, "h": 630,  "cat": "website", "layout": "centered",
                                "logo_height_pct": 45, "title_size_pct": 8, "tagline_size_pct": 4},
    "web-email-header":        {"w": 600,  "h": 200,  "cat": "website", "layout": "horizontal",
                                "logo_height_pct": 70, "title_size_pct": 18, "tagline_size_pct": 9},
    "web-square-logo":         {"w": 512,  "h": 512,  "cat": "website", "layout": "centered",
                                "logo_height_pct": 45, "title_size_pct": 9, "tagline_size_pct": 5},
    "web-favicon":             {"w": 256,  "h": 256,  "cat": "website", "layout": "centered",
                                "logo_height_pct": 55, "title_size_pct": 10, "tagline_size_pct": 5},
}

# ── Starter config template ────────────────────────────────────────────

STARTER_CONFIG = """{
  "logo": {
    "path": "logo.png",
    "mode": "full",
    "crop": {"x": 0, "y": 0, "w": 200, "h": 100},
    "background": "white",
    "fuzz": "15%",
    "aspect_ratio": null
  },
  "brand": {
    "title": "MY BRAND",
    "tagline": "YOUR TAGLINE HERE",
    "url_text": null,
    "title_color": "#ffffff",
    "tagline_color": "#b0b8cc",
    "url_color": "#8090aa",
    "background": {"start": "#1a1f3a", "end": "#2d1b4e"}
  },
  "fonts": {
    "title":   ["Arial-Bold", "DejaVu-Sans-Bold", "Liberation-Sans-Bold"],
    "tagline": ["Arial", "DejaVu-Sans", "Liberation-Sans"],
    "url":     ["Arial", "DejaVu-Sans", "Liberation-Sans"]
  },
  "banners": [
    {
      "name": "hero-1920x600",
      "width": 1920, "height": 600,
      "category": "website",
      "layout": "horizontal",
      "logo_height_pct": 65,
      "title_size_pct": 12,
      "tagline_size_pct": 6,
      "url_size_pct": 3
    },
    {
      "name": "og-social-1200x630",
      "width": 1200, "height": 630,
      "category": "website",
      "layout": "centered",
      "logo_height_pct": 45,
      "title_size_pct": 8,
      "tagline_size_pct": 4,
      "url_size_pct": 2.5
    },
    {
      "name": "square-logo-512x512",
      "width": 512, "height": 512,
      "category": "website",
      "layout": "centered",
      "logo_height_pct": 45,
      "title_size_pct": 9,
      "tagline_size_pct": 5,
      "url_size_pct": 0
    }
  ]
}
"""

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
VALID_LAYOUTS = {"horizontal", "horizontal-compact", "centered"}


# ── ImageMagick helpers ────────────────────────────────────────────────

def find_magick() -> str:
    path = shutil.which("magick")
    if not path:
        print("ERROR: ImageMagick 7 not found. Install: brew install imagemagick (macOS) "
              "or apt install imagemagick (Linux)", file=sys.stderr)
        sys.exit(1)
    return path


_font_cache: set[str] | None = None


def _get_available_system_fonts(magick: str) -> set[str]:
    global _font_cache
    if _font_cache is not None:
        return _font_cache
    try:
        result = subprocess.run([magick, "-list", "font"], capture_output=True, text=True, timeout=10)
        fonts = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Font:"):
                fonts.add(line.split(":", 1)[1].strip())
        _font_cache = fonts
        log.debug(f"Found {len(fonts)} system fonts")
        return fonts
    except (subprocess.TimeoutExpired, OSError) as e:
        log.warning(f"Could not list fonts: {e}")
        _font_cache = set()
        return _font_cache


def detect_available_font(candidates: list[str], magick: str) -> str | None:
    system_fonts = _get_available_system_fonts(magick)
    for candidate in candidates:
        if candidate.startswith("/"):
            if Path(candidate).exists():
                log.debug(f"Font file found: {candidate}")
                return candidate
        elif candidate in system_fonts:
            log.debug(f"System font found: {candidate}")
            return candidate
    return None


def resolve_fonts(fonts_config: dict, magick: str) -> dict[str, str]:
    resolved = {}
    for role in ("title", "tagline", "url"):
        candidates = fonts_config.get(role, [])
        if not candidates:
            candidates = ["Arial-Bold"] if role == "title" else ["Arial"]
        found = detect_available_font(candidates, magick)
        if found:
            if found != candidates[0]:
                log.warning(f"Font fallback for {role}: using '{found}' (preferred '{candidates[0]}' not available)")
            resolved[role] = found
        else:
            print(f"ERROR: No available font for '{role}'. Tried: {candidates}", file=sys.stderr)
            print("  Run `magick -list font` to see available fonts.", file=sys.stderr)
            sys.exit(1)
    return resolved


def run_magick(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    log.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        log.error(f"ImageMagick failed: {result.stderr.strip()}")
        raise RuntimeError(f"magick command failed: {result.stderr.strip()}")
    return result


def get_image_dimensions(path: Path, magick: str) -> tuple[int, int]:
    result = subprocess.run(
        [magick, "identify", "-format", "%w %h", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Cannot read image dimensions: {path}")
    parts = result.stdout.strip().split()
    return int(parts[0]), int(parts[1])


# ── Config loading & validation ────────────────────────────────────────

def resolve_logo_path(config_path: Path, logo_rel: str) -> Path:
    return (config_path.parent / logo_rel).resolve()


def load_config(config_path: Path) -> dict:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: Cannot read config: {e}", file=sys.stderr)
        sys.exit(2)

    logo_cfg = config.get("logo", {})
    logo_cfg["_resolved_path"] = resolve_logo_path(config_path, logo_cfg.get("path", "logo.png"))
    config["logo"] = logo_cfg
    return config


def validate_config(config: dict, magick: str) -> list[str]:
    errors = []
    warnings = []

    # Logo
    logo = config.get("logo", {})
    logo_path = logo.get("_resolved_path")
    if logo_path and not logo_path.exists():
        errors.append(f"Logo not found: {logo_path}")
    mode = logo.get("mode", "full")
    if mode not in ("full", "extract"):
        errors.append(f"Invalid logo.mode: '{mode}' (must be 'full' or 'extract')")
    if mode == "extract":
        crop = logo.get("crop", {})
        for k in ("x", "y", "w", "h"):
            if k not in crop:
                errors.append(f"logo.crop missing key '{k}' (required for mode='extract')")
    bg = logo.get("background", "white")
    if bg not in ("white", "transparent", "none"):
        errors.append(f"Invalid logo.background: '{bg}'")

    # Brand
    brand = config.get("brand", {})
    if not brand.get("title"):
        errors.append("brand.title is required")
    for color_key in ("title_color", "tagline_color", "url_color"):
        val = brand.get(color_key, "")
        if val and not HEX_COLOR_RE.match(val):
            errors.append(f"Invalid hex color for brand.{color_key}: '{val}'")
    bg_cfg = brand.get("background", {})
    if "start" in bg_cfg and "end" in bg_cfg:
        for k in ("start", "end"):
            if not HEX_COLOR_RE.match(bg_cfg[k]):
                errors.append(f"Invalid hex color for brand.background.{k}: '{bg_cfg[k]}'")
    elif "color" in bg_cfg:
        if not HEX_COLOR_RE.match(bg_cfg["color"]):
            errors.append(f"Invalid hex color for brand.background.color: '{bg_cfg['color']}'")
    else:
        errors.append("brand.background must have 'start'+'end' (gradient) or 'color' (solid)")

    # Fonts
    fonts_cfg = config.get("fonts", {})
    for role in ("title", "tagline"):
        candidates = fonts_cfg.get(role, [])
        if candidates:
            found = detect_available_font(candidates, magick)
            if not found:
                errors.append(f"No available font for '{role}'. Tried: {candidates}")
            elif found != candidates[0]:
                warnings.append(f"Font fallback for {role}: '{found}' (preferred '{candidates[0]}' unavailable)")
        else:
            warnings.append(f"No fonts configured for '{role}', will use defaults")

    # Banners
    banners = config.get("banners", [])
    names = set()
    for i, b in enumerate(banners):
        name = b.get("name", "")
        if not name:
            errors.append(f"Banner [{i}] missing 'name'")
        elif name in names:
            errors.append(f"Duplicate banner name: '{name}'")
        names.add(name)
        for dim in ("width", "height"):
            val = b.get(dim, 0)
            if not isinstance(val, (int, float)) or val <= 0:
                errors.append(f"Banner '{name}': {dim} must be > 0")
        layout = b.get("layout", "")
        if layout not in VALID_LAYOUTS:
            errors.append(f"Banner '{name}': invalid layout '{layout}' (must be one of {VALID_LAYOUTS})")

    return errors + [f"WARNING: {w}" for w in warnings]


_FUZZ_RE = re.compile(r"^\d+(\.\d+)?%?$")
_UNSAFE_NAME_RE = re.compile(r"[/\\]|\.\.")


def sanitize_config(config: dict) -> None:
    """Reject config values that could drive ImageMagick file-read injection or
    path traversal, then exit 2. ImageMagick treats a leading '@' on a
    text-consuming argument (-annotate, -fuzz, labels) as "read this file",
    which a crafted config could use to exfiltrate arbitrary local files onto a
    banner image or into error output. Banner names flow into output paths.
    """
    errors: list[str] = []

    logo = config.get("logo", {})
    fuzz = logo.get("fuzz", "15%")
    if not _FUZZ_RE.match(str(fuzz)):
        errors.append(f"logo.fuzz must be a number or percentage (got {fuzz!r})")
    if str(logo.get("path", "logo.png")).startswith("@"):
        errors.append("logo.path must not start with '@'")

    brand = config.get("brand", {})
    for field in ("title", "tagline", "url_text"):
        val = brand.get(field)
        if isinstance(val, str) and val.startswith("@"):
            errors.append(f"brand.{field} must not start with '@' (ImageMagick file-read)")

    for i, b in enumerate(config.get("banners", [])):
        name = str(b.get("name", ""))
        if name.startswith(("@", "-")) or _UNSAFE_NAME_RE.search(name):
            errors.append(
                f"Banner [{i}] name {name!r} is unsafe "
                "(no '/', '\\', '..', or leading '@'/'-')"
            )

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


# ── Logo extraction ────────────────────────────────────────────────────

def extract_logo_mark(logo_path: Path, logo_config: dict, tmp_dir: Path, magick: str) -> tuple[Path, tuple[float, float]]:
    mode = logo_config.get("mode", "full")
    bg_mode = logo_config.get("background", "white")
    fuzz = logo_config.get("fuzz", "15%")

    processed = tmp_dir / "logo-processed.png"

    if bg_mode == "white":
        run_magick([magick, str(logo_path), "-fuzz", fuzz, "-transparent", "white", str(processed)])
    elif bg_mode == "transparent":
        shutil.copy2(logo_path, processed)
    else:  # "none"
        shutil.copy2(logo_path, processed)

    if mode == "extract":
        crop = logo_config.get("crop", {})
        geometry = f"{crop['w']}x{crop['h']}+{crop['x']}+{crop['y']}"
        cropped = tmp_dir / "logo-cropped.png"
        run_magick([magick, str(processed), "-crop", geometry, "+repage", str(cropped)])
        processed = cropped

    # Determine aspect ratio
    ar = logo_config.get("aspect_ratio")
    if ar and isinstance(ar, (list, tuple)) and len(ar) == 2:
        aspect = (float(ar[0]), float(ar[1]))
    else:
        w, h = get_image_dimensions(processed, magick)
        aspect = (float(w), float(h))
        log.info(f"Auto-detected logo aspect ratio: {w}:{h}")

    return processed, aspect


# ── Background helpers ─────────────────────────────────────────────────

def make_bg_spec(bg_config: dict) -> str:
    if "start" in bg_config and "end" in bg_config:
        return f"gradient:{bg_config['start']}-{bg_config['end']}"
    return f"xc:{bg_config.get('color', '#1a1f3a')}"


# ── Layout renderers ───────────────────────────────────────────────────

def render_horizontal(banner: dict, brand: dict, fonts: dict, logo_path: Path,
                      logo_aspect: tuple[float, float], magick: str, output: Path):
    w, h = banner["width"], banner["height"]
    logo_h = int(h * banner.get("logo_height_pct", 65) / 100)
    title_size = max(10, int(h * banner.get("title_size_pct", 12) / 100))
    tagline_size = max(8, int(h * banner.get("tagline_size_pct", 0) / 100))
    url_size = max(0, int(h * banner.get("url_size_pct", 0) / 100))

    logo_pad_left = int(w * 0.04)
    logo_pad_top = (h - logo_h) // 2
    logo_w = int(logo_h * (logo_aspect[0] / logo_aspect[1]))
    text_x = logo_pad_left + logo_w + int(w * 0.03)
    text_center_y = h // 2

    bg_spec = make_bg_spec(brand.get("background", {}))
    cmd = [
        magick,
        "-size", f"{w}x{h}", bg_spec,
        "(", str(logo_path), "-resize", f"x{logo_h}", ")",
        "-gravity", "NorthWest",
        "-geometry", f"+{logo_pad_left}+{logo_pad_top}",
        "-composite",
        "-font", fonts["title"],
        "-pointsize", str(title_size),
        "-fill", brand.get("title_color", "#ffffff"),
        "-gravity", "NorthWest",
        "-annotate", f"+{text_x}+{text_center_y - title_size}",
        brand.get("title", ""),
    ]

    if tagline_size > 0 and banner.get("tagline_size_pct", 0) > 0:
        cmd.extend([
            "-font", fonts["tagline"],
            "-pointsize", str(tagline_size),
            "-fill", brand.get("tagline_color", "#b0b8cc"),
            "-gravity", "NorthWest",
            "-annotate", f"+{text_x}+{text_center_y + int(title_size * 0.3)}",
            brand.get("tagline", ""),
        ])

    url_text = brand.get("url_text")
    if url_text and url_size > 0 and banner.get("url_size_pct", 0) > 0:
        url_y = text_center_y + int(title_size * 0.3) + tagline_size + int(h * 0.02)
        cmd.extend([
            "-font", fonts.get("url", fonts["tagline"]),
            "-pointsize", str(url_size),
            "-fill", brand.get("url_color", "#8090aa"),
            "-gravity", "NorthWest",
            "-annotate", f"+{text_x}+{url_y}",
            url_text,
        ])

    cmd.append(str(output))
    run_magick(cmd)


def render_horizontal_compact(banner: dict, brand: dict, fonts: dict, logo_path: Path,
                              logo_aspect: tuple[float, float], magick: str, output: Path):
    w, h = banner["width"], banner["height"]
    logo_h = int(h * banner.get("logo_height_pct", 80) / 100)
    title_size = max(8, int(h * banner.get("title_size_pct", 38) / 100))
    tagline_size = max(0, int(h * banner.get("tagline_size_pct", 0) / 100))

    logo_pad = int(h * 0.1)
    logo_w = int(logo_h * (logo_aspect[0] / logo_aspect[1]))
    text_x = logo_pad + logo_w + int(w * 0.02)
    text_y = (h - title_size) // 2 + int(title_size * 0.75)

    bg_spec = make_bg_spec(brand.get("background", {}))
    cmd = [
        magick,
        "-size", f"{w}x{h}", bg_spec,
        "(", str(logo_path), "-resize", f"x{logo_h}", ")",
        "-gravity", "NorthWest",
        "-geometry", f"+{logo_pad}+{(h - logo_h) // 2}",
        "-composite",
        "-font", fonts["title"],
        "-pointsize", str(title_size),
        "-fill", brand.get("title_color", "#ffffff"),
        "-gravity", "NorthWest",
        "-annotate", f"+{text_x}+{text_y}",
        brand.get("title", ""),
    ]

    if tagline_size > 0 and banner.get("tagline_size_pct", 0) > 0:
        tagline_x = text_x + int(title_size * len(brand.get("title", "")) * 0.55) + int(w * 0.02)
        cmd.extend([
            "-font", fonts["tagline"],
            "-pointsize", str(tagline_size),
            "-fill", brand.get("tagline_color", "#b0b8cc"),
            "-gravity", "NorthWest",
            "-annotate", f"+{tagline_x}+{(h - tagline_size) // 2 + int(tagline_size * 0.75)}",
            brand.get("tagline", ""),
        ])

    cmd.append(str(output))
    run_magick(cmd)


def render_centered(banner: dict, brand: dict, fonts: dict, logo_path: Path,
                    logo_aspect: tuple[float, float], magick: str, output: Path):
    _ = logo_aspect  # interface consistency with horizontal renderers; centered uses -gravity North
    w, h = banner["width"], banner["height"]
    logo_h = int(h * banner.get("logo_height_pct", 45) / 100)
    title_size = max(10, int(h * banner.get("title_size_pct", 8) / 100))
    tagline_size = max(8, int(h * banner.get("tagline_size_pct", 4) / 100))
    url_size = max(0, int(h * banner.get("url_size_pct", 0) / 100))

    url_text = brand.get("url_text")
    has_url = url_text and url_size > 0 and banner.get("url_size_pct", 0) > 0

    total_h = logo_h + int(h * 0.04) + title_size + int(h * 0.02) + tagline_size
    if has_url:
        total_h += int(h * 0.015) + url_size
    start_y = max(int(h * 0.08), (h - total_h) // 2)

    logo_y = start_y
    title_y = logo_y + logo_h + int(h * 0.04)
    tagline_y = title_y + title_size + int(h * 0.015)

    bg_spec = make_bg_spec(brand.get("background", {}))
    cmd = [
        magick,
        "-size", f"{w}x{h}", bg_spec,
        "(", str(logo_path), "-resize", f"x{logo_h}", ")",
        "-gravity", "North",
        "-geometry", f"+0+{logo_y}",
        "-composite",
        "-font", fonts["title"],
        "-pointsize", str(title_size),
        "-fill", brand.get("title_color", "#ffffff"),
        "-gravity", "North",
        "-annotate", f"+0+{title_y}",
        brand.get("title", ""),
        "-font", fonts["tagline"],
        "-pointsize", str(tagline_size),
        "-fill", brand.get("tagline_color", "#b0b8cc"),
        "-gravity", "North",
        "-annotate", f"+0+{tagline_y}",
        brand.get("tagline", ""),
    ]

    if has_url:
        url_y = tagline_y + tagline_size + int(h * 0.015)
        cmd.extend([
            "-font", fonts.get("url", fonts["tagline"]),
            "-pointsize", str(url_size),
            "-fill", brand.get("url_color", "#8090aa"),
            "-gravity", "North",
            "-annotate", f"+0+{url_y}",
            url_text,
        ])

    cmd.append(str(output))
    run_magick(cmd)


LAYOUT_FUNCS = {
    "horizontal": render_horizontal,
    "horizontal-compact": render_horizontal_compact,
    "centered": render_centered,
}


# ── Format conversion ──────────────────────────────────────────────────

def convert_format(png_path: Path, fmt: str, magick: str) -> Path:
    if fmt == "png":
        return png_path
    ext = {"webp": ".webp", "jpeg": ".jpeg", "jpg": ".jpeg"}.get(fmt, f".{fmt}")
    out_path = png_path.with_suffix(ext)
    quality_args = []
    if fmt in ("webp",):
        quality_args = ["-quality", "90"]
    elif fmt in ("jpeg", "jpg"):
        quality_args = ["-quality", "95"]
    run_magick([magick, str(png_path)] + quality_args + [str(out_path)])
    png_path.unlink()
    return out_path


# ── Utility commands ───────────────────────────────────────────────────

def list_presets():
    print("\nAvailable dimension presets:")
    print(f"{'Preset':<30} {'Size':>10}  {'Category':<8}  Layout")
    print("-" * 72)
    for cat in ("iab", "social", "website"):
        for name, p in sorted(PRESET_DIMENSIONS.items()):
            if p["cat"] == cat:
                print(f"  {name:<28} {p['w']:>4}x{p['h']:<4}  {p['cat']:<8}  {p['layout']}")
        print()


def init_config(output_path: Path):
    if output_path.exists():
        print(f"ERROR: {output_path} already exists. Remove it first or use a different path.", file=sys.stderr)
        sys.exit(2)
    output_path.write_text(STARTER_CONFIG, encoding="utf-8")
    print(f"Created starter config: {output_path}", file=sys.stderr)
    print("Edit it with your logo path, brand text, and colors, then run --validate.", file=sys.stderr)


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate consistent logo banners from JSON config using ImageMagick",
        epilog="Run --list-presets to see available IAB/social/web dimension presets.",
    )
    parser.add_argument("--config", "-c", default="banner-config.json", help="Path to config JSON (default: banner-config.json)")
    parser.add_argument("--output-dir", "-o", default=".", help="Output directory (default: current dir)")
    parser.add_argument("--name", "-n", help="Generate only this banner (by name)")
    parser.add_argument("--format", "-f", default="png", choices=["png", "webp", "jpeg"], help="Output format (default: png)")
    parser.add_argument("--list-presets", action="store_true", help="List available dimension presets and exit")
    parser.add_argument("--init", action="store_true", help="Generate starter banner-config.json and exit")
    parser.add_argument("--validate", action="store_true", help="Validate config and exit (0=ok, 2=errors)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated without rendering")
    parser.add_argument("--json", action="store_true", help="Print structured JSON result to stdout")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Debug output (shows magick commands)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress non-error output")
    args = parser.parse_args()

    # Logging
    level = logging.WARNING
    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    elif args.quiet:
        level = logging.ERROR
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s", stream=sys.stderr)

    # --list-presets
    if args.list_presets:
        list_presets()
        sys.exit(0)

    # --init
    if args.init:
        init_config(Path(args.config))
        sys.exit(0)

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}", file=sys.stderr)
        print("  Run --init to create a starter config.", file=sys.stderr)
        sys.exit(2)

    config = load_config(config_path)
    sanitize_config(config)
    magick = find_magick()

    # --validate
    if args.validate:
        issues = validate_config(config, magick)
        if not issues:
            if args.json:
                print(json.dumps({"ok": True, "valid": True, "issues": []}))
            print("Config OK: no issues found.", file=sys.stderr)
            logo_path = config["logo"].get("_resolved_path")
            if logo_path:
                print(f"  Logo: {logo_path} ({'exists' if logo_path.exists() else 'MISSING'})", file=sys.stderr)
            fonts_cfg = config.get("fonts", {})
            resolved = {}
            for role in ("title", "tagline", "url"):
                candidates = fonts_cfg.get(role, [])
                if candidates:
                    found = detect_available_font(candidates, magick)
                    resolved[role] = found or "(none)"
            print(f"  Fonts: {resolved}", file=sys.stderr)
            print(f"  Banners: {len(config.get('banners', []))}", file=sys.stderr)
            sys.exit(0)
        else:
            errs = [i for i in issues if not i.startswith("WARNING:")]
            warns = [i for i in issues if i.startswith("WARNING:")]
            for w in warns:
                print(f"  {w}", file=sys.stderr)
            for e in errs:
                print(f"  ERROR: {e}", file=sys.stderr)
            if errs:
                if args.json:
                    print(json.dumps({"ok": False, "valid": False, "issues": errs}))
                print(f"\n{len(errs)} error(s), {len(warns)} warning(s).", file=sys.stderr)
                sys.exit(2)
            else:
                if args.json:
                    print(json.dumps({"ok": True, "valid": True, "issues": warns}))
                print(f"\nConfig OK with {len(warns)} warning(s).", file=sys.stderr)
                sys.exit(0)

    # Resolve fonts
    fonts_cfg = config.get("fonts", {})
    fonts = resolve_fonts(fonts_cfg, magick)
    log.info(f"Resolved fonts: {fonts}")

    # Extract logo
    logo_config = config.get("logo", {})
    logo_path = logo_config.get("_resolved_path")
    if not logo_path or not logo_path.exists():
        print(f"ERROR: Logo not found: {logo_path}", file=sys.stderr)
        sys.exit(1)

    tmp_dir = Path(tempfile.mkdtemp(prefix="composite-banners-"))
    try:
        logo_mark, logo_aspect = extract_logo_mark(logo_path, logo_config, tmp_dir, magick)
        if not args.quiet:
            print(f"Logo processed: {logo_mark.name} (aspect {logo_aspect[0]:.0f}:{logo_aspect[1]:.0f})", file=sys.stderr)

        # Filter banners
        brand = config.get("brand", {})
        banners = config.get("banners", [])
        if args.name:
            banners = [b for b in banners if b.get("name") == args.name]
            if not banners:
                print(f"ERROR: No banner named '{args.name}'. Available: {[b['name'] for b in config.get('banners', [])]}", file=sys.stderr)
                sys.exit(1)

        # --dry-run
        if args.dry_run:
            print(f"\nDry run — would generate {len(banners)} banner(s):", file=sys.stderr)
            for b in banners:
                ext = {"webp": ".webp", "jpeg": ".jpeg"}.get(args.format, ".png")
                print(f"  {b['name']}{ext}  {b['width']}x{b['height']}  [{b.get('category', '?')}]  {b['layout']}", file=sys.stderr)
            sys.exit(0)

        # Generate
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        start_time = time.time()
        generated = []
        failed = []

        for b in banners:
            name = b.get("name", "unnamed")
            output = output_dir / f"{name}.png"
            layout = b.get("layout", "")
            func = LAYOUT_FUNCS.get(layout)
            if not func:
                if not args.quiet:
                    print(f"  SKIP: Unknown layout '{layout}' for {name}", file=sys.stderr)
                failed.append({"name": name, "error": f"unknown layout: {layout}"})
                continue

            try:
                func(b, brand, fonts, logo_mark, logo_aspect, magick, output)
                # Convert format if needed
                final_path = convert_format(output, args.format, magick) if args.format != "png" else output
                # Verify
                result = run_magick([magick, "identify", str(final_path)], check=False)
                dims = result.stdout.strip().split()[2] if result.returncode == 0 else "?"
                size_bytes = final_path.stat().st_size if final_path.exists() else 0
                if not args.quiet:
                    print(f"  OK: {final_path.name}  {dims}  [{b.get('category', '?')}]  ({size_bytes / 1024:.1f} KB)", file=sys.stderr)
                generated.append({"name": name, "file": str(final_path), "dimensions": dims, "size_bytes": size_bytes})
            except Exception as e:
                if not args.quiet:
                    print(f"  FAIL: {name}: {e}", file=sys.stderr)
                failed.append({"name": name, "error": str(e)})

        elapsed = time.time() - start_time
        if not args.quiet:
            print(f"\nGenerated {len(generated)}/{len(banners)} banners in {output_dir}/ ({elapsed:.1f}s)", file=sys.stderr)

        # --json
        if args.json:
            result_json = {
                "ok": len(failed) == 0,
                "generated": generated,
                "failed": failed,
                "total": len(banners),
                "elapsed_seconds": round(elapsed, 1),
                "config": str(config_path),
                "output_dir": str(output_dir),
                "format": args.format,
            }
            print(json.dumps(result_json, indent=2))

        sys.exit(0 if not failed else 1)

    finally:
        # Cleanup temp
        for f in tmp_dir.iterdir():
            f.unlink(missing_ok=True)
        tmp_dir.rmdir()


if __name__ == "__main__":
    main()
