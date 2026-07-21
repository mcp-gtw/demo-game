#!/usr/bin/env python3
"""
Generate an image from a text prompt and save it to disk.

Examples
--------
    python gen-image.py \\
        --prompt "Minimal tech blog hero with permission checkmarks" \\
        --output ./frontend/public/images/blog/claude-permissions.jpg

    python gen-image.py \\
        --prompt "..." \\
        --output ./out.jpg \\
        --size 1983x793

Requirements: openai, Pillow, python-dotenv
Auth: set OPENAI_API_KEY in the environment, .env, or --api-key.
"""

import argparse
import base64
import os
import re
import sys
from io import BytesIO
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:
    sys.exit("Missing dependency: pip install openai")

try:
    from PIL import Image
except ImportError:
    sys.exit("Missing dependency: pip install Pillow")


MODEL = "gpt-image-2"
MIN_PIXELS = 655_360
MAX_PIXELS = 8_294_400
MAX_EDGE = 3840
MAX_RATIO = 3.0


def parse_size(value: str) -> tuple[int, int]:
    """Parse WIDTHxHEIGHT into integers."""
    match = re.fullmatch(r"(\d+)\s*[xX]\s*(\d+)", value.strip())
    if not match:
        raise ValueError(f'Invalid size "{value}". Use WIDTHxHEIGHT (e.g. 1983x793).')
    return int(match.group(1)), int(match.group(2))


def parse_aspect(value: str):
    """Parse W:H into a float ratio, or None to skip cropping."""
    if not value or value.lower() == "none":
        return None
    w, h = value.split(":")
    return int(w) / int(h)


def snap_to_step(value: int, step: int = 16) -> int:
    """Round a dimension to the nearest valid step."""
    return max(step, round(value / step) * step)


def prepare_api_size(width: int, height: int) -> tuple[int, int]:
    """Adjust dimensions to satisfy API constraints."""
    w, h = snap_to_step(width), snap_to_step(height)
    if max(w, h) > MAX_EDGE:
        scale = MAX_EDGE / max(w, h)
        w = snap_to_step(int(w * scale))
        h = snap_to_step(int(h * scale))
    ratio = max(w, h) / min(w, h)
    if ratio > MAX_RATIO:
        raise ValueError(f"Aspect ratio {ratio:.2f}:1 exceeds limit of {MAX_RATIO}:1.")
    pixels = w * h
    if pixels < MIN_PIXELS:
        scale = (MIN_PIXELS / pixels) ** 0.5
        w = snap_to_step(int(w * scale))
        h = snap_to_step(int(h * scale))
    if w * h > MAX_PIXELS:
        scale = (MAX_PIXELS / (w * h)) ** 0.5
        w = snap_to_step(int(w * scale))
        h = snap_to_step(int(h * scale))
    return w, h


def crop_to_aspect(img: Image.Image, target_aspect: float) -> Image.Image:
    """Center-crop to the requested aspect ratio."""
    w, h = img.size
    current = w / h
    if abs(current - target_aspect) < 1e-3:
        return img
    if current > target_aspect:
        new_w = round(h * target_aspect)
        left = (w - new_w) // 2
        return img.crop((left, 0, left + new_w, h))
    new_h = round(w / target_aspect)
    top = (h - new_h) // 2
    return img.crop((0, top, w, top + new_h))


def resize_to(img: Image.Image, width: int, height: int) -> Image.Image:
    """Resize to exact target dimensions."""
    if img.size == (width, height):
        return img
    return img.resize((width, height), Image.Resampling.LANCZOS)


def save_image(img: Image.Image, out: Path, fmt: str, compression: int):
    """Write image to disk, creating parent folders if needed."""
    out.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "jpeg":
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(out, "JPEG", quality=compression, optimize=True, progressive=True)
    elif fmt == "png":
        img.save(out, "PNG", optimize=True)
    elif fmt == "webp":
        img.save(out, "WEBP", quality=compression, method=6)
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate an image from a text prompt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--prompt", required=True, help="Image description.")
    parser.add_argument("-o", "--output", required=True, help="Output file path.")
    parser.add_argument(
        "--size",
        default="1983x793",
        help="Target size WIDTHxHEIGHT (default: 1983x793).",
    )
    parser.add_argument(
        "--aspect-ratio",
        default="none",
        help='Optional crop before resize, e.g. "16:9". Default: none.',
    )
    parser.add_argument(
        "--format",
        default=None,
        choices=["jpeg", "png", "webp"],
        help="Output format (default: inferred from --output).",
    )
    parser.add_argument(
        "--quality",
        default="high",
        choices=["low", "medium", "high", "auto"],
        help="Generation quality (default: high).",
    )
    parser.add_argument(
        "--compression",
        type=int,
        default=90,
        help="Save quality 0-100 (default: 90).",
    )
    parser.add_argument(
        "--moderation",
        default="auto",
        choices=["auto", "low"],
        help="Moderation strictness (default: auto).",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="API key (defaults to $OPENAI_API_KEY).",
    )
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Missing OPENAI_API_KEY (set env, .env, or pass --api-key).")

    target_w, target_h = parse_size(args.size)
    target_aspect = parse_aspect(args.aspect_ratio)
    out = Path(args.output)
    fmt = args.format or ("png" if out.suffix.lower() == ".png" else "jpeg")

    api_w, api_h = prepare_api_size(target_w, target_h)
    api_size = f"{api_w}x{api_h}"

    print(f"model:       {MODEL}")
    print(f"api size:    {api_size}")
    print(f"target size: {target_w}x{target_h}")
    print(f"quality:     {args.quality}")
    print(f"output:      {out}")
    print(f"prompt:      {args.prompt[:120]}{'…' if len(args.prompt) > 120 else ''}")

    client = OpenAI(api_key=args.api_key)

    request = dict(
        model=MODEL,
        prompt=args.prompt,
        size=api_size,
        quality=args.quality,
        n=1,
        output_format=fmt,
        moderation=args.moderation,
    )
    if fmt in ("jpeg", "webp"):
        request["output_compression"] = args.compression

    print("generating…")
    response = client.images.generate(**request)

    raw = base64.b64decode(response.data[0].b64_json)
    img = Image.open(BytesIO(raw))
    print(f"received:    {img.size[0]}x{img.size[1]}")

    if target_aspect is not None:
        img = crop_to_aspect(img, target_aspect)
        print(f"cropped:     {img.size[0]}x{img.size[1]}")

    img = resize_to(img, target_w, target_h)
    print(f"resized:     {img.size[0]}x{img.size[1]}")

    save_image(img, out, fmt, args.compression)
    print(f"saved:       {out}")

    usage = getattr(response, "usage", None)
    if usage:
        print(f"usage:       {usage}")


if __name__ == "__main__":
    main()
