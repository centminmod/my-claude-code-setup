"""Generate images of the "Old Ledger" character with the OpenAI image API.

Usage:
    python generate.py --prompt main --count 6
    python generate.py --prompt sheet --count 2 --reference output/main/001.png
"""

import argparse
import base64
import json
import os
import re
import sys
from contextlib import ExitStack
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
PROMPTS_FILE = ROOT / "prompts.json"
OUTPUT_DIR = ROOT / "output"

DEFAULT_MODEL = "gpt-image-2.5-flare"           # fast everyday generation
DEFAULT_REFERENCE_MODEL = "gpt-image-2.5-sunburst"  # more precise when following a reference
MAX_PER_REQUEST = 10                            # API limit for n

# Approximate USD per 1024x1024 image for gpt-image-2.5 (flare and sunburst are
# priced the same). Token-based in reality, so treat these as estimates and scale by
# pixel count. Reference images add a small input cost on top.
APPROX_COST_1024 = {"low": 0.006, "medium": 0.013, "high": 0.053}


def load_prompts():
    with open(PROMPTS_FILE, encoding="utf-8") as f:
        return json.load(f)["prompts"]


def estimate_cost(size, quality, count):
    w, h = (int(x) for x in size.lower().split("x"))
    per_image = APPROX_COST_1024[quality] * (w * h) / (1024 * 1024)
    return per_image, per_image * count


def next_index(folder):
    nums = [int(m.group(1)) for p in folder.glob("*.png") if (m := re.fullmatch(r"(\d+)", p.stem))]
    return max(nums, default=0) + 1


def main():
    prompts = load_prompts()
    parser = argparse.ArgumentParser(description="Generate Old Ledger images (OpenAI image API).")
    parser.add_argument("--prompt", required=True, choices=sorted(prompts), help="prompt name from prompts.json")
    parser.add_argument("--count", type=int, default=1, help="number of images (default 1)")
    parser.add_argument("--reference", action="append", default=[], metavar="PATH",
                        help="reference image to keep the character consistent (repeatable, up to 16)")
    parser.add_argument("--quality", choices=sorted(APPROX_COST_1024), default="medium")
    parser.add_argument("--size", help="override size from prompts.json, e.g. 1536x864")
    parser.add_argument("--model", help=f"default {DEFAULT_MODEL}, or {DEFAULT_REFERENCE_MODEL} with --reference")
    parser.add_argument("--yes", "-y", action="store_true", help="skip the cost confirmation")
    parser.add_argument("--dry-run", action="store_true", help="show what would be sent and the cost, then exit")
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")
    if len(args.reference) > 16:
        parser.error("at most 16 reference images")
    for ref in args.reference:
        if not Path(ref).is_file():
            parser.error(f"reference image not found: {ref}")

    entry = prompts[args.prompt]
    size = args.size or entry["size"]
    model = args.model or (DEFAULT_REFERENCE_MODEL if args.reference else DEFAULT_MODEL)
    per_image, total = estimate_cost(size, args.quality, args.count)

    print(f"Prompt:    {args.prompt}")
    print(f"Model:     {model}")
    print(f"Size:      {size}, quality: {args.quality}")
    if args.reference:
        print(f"Reference: {', '.join(args.reference)}")
    print(f"Cost:      ~${per_image:.3f} per image, ~${total:.2f} for {args.count} (approximate)")

    if args.dry_run:
        return
    if not args.yes and input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Cancelled.")
        return

    load_dotenv(ROOT / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set. Copy .env.example to .env and put your key there.")

    from openai import OpenAI
    client = OpenAI()

    out_dir = OUTPUT_DIR / args.prompt
    out_dir.mkdir(parents=True, exist_ok=True)
    index = next_index(out_dir)
    remaining = args.count

    while remaining > 0:
        n = min(remaining, MAX_PER_REQUEST)
        params = dict(model=model, prompt=entry["prompt"], size=size, quality=args.quality, n=n)
        if args.reference:
            with ExitStack() as stack:
                images = [stack.enter_context(open(p, "rb")) for p in args.reference]
                result = client.images.edit(image=images, **params)
        else:
            result = client.images.generate(**params)

        for item in result.data or []:
            path = out_dir / f"{index:03d}.png"
            path.write_bytes(base64.b64decode(item.b64_json))
            print(f"Saved {path.relative_to(ROOT)}")
            index += 1
        if result.usage:
            print(f"  tokens used: in {result.usage.input_tokens}, out {result.usage.output_tokens}")
        remaining -= n


if __name__ == "__main__":
    main()
