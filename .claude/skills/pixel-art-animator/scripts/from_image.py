#!/usr/bin/env python3
"""Convert a supplied image into a draft pixel-art sprite spec.

Downsamples the image to a target grid, quantizes to a small palette, and
emits the skill's spec JSON with one frame ("base") plus the ASCII grid on
stdout. The output is a *draft*: hand-refine the grid afterwards (clean
stray pixels, strengthen the silhouette, re-ramp the palette) and only then
start animating — see the skill's SKILL.md.

Usage:
  python from_image.py INPUT.png --width 16 [--colors 8] [--out spec.json]
                                 [--alpha-threshold 128]
"""
from __future__ import annotations

import argparse
import json
import string
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("from_image.py needs Pillow: pip install Pillow")

# Palette slot letters, assigned most-frequent-first. Skips confusing chars.
SLOT_CHARS = [c for c in string.ascii_lowercase + string.ascii_uppercase
              if c not in "lIoO"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path)
    ap.add_argument("--width", type=int, default=16, help="target grid width in pixels")
    ap.add_argument("--colors", type=int, default=8, help="max palette size")
    ap.add_argument("--alpha-threshold", type=int, default=128,
                    help="alpha below this becomes transparent")
    ap.add_argument("--out", type=Path, help="write draft spec JSON here")
    args = ap.parse_args()

    img = Image.open(args.input).convert("RGBA")
    # Trim fully transparent borders so the subject fills the grid.
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)

    grid_w = args.width
    grid_h = max(1, round(img.height * grid_w / img.width))
    small = img.resize((grid_w, grid_h), Image.BOX)

    alpha = small.getchannel("A")
    rgb = small.convert("RGB").quantize(colors=args.colors, dither=Image.NONE).convert("RGB")

    # Count colour frequency to assign slot letters most-used-first.
    counts: dict[tuple, int] = {}
    px, ax = rgb.load(), alpha.load()
    for y in range(grid_h):
        for x in range(grid_w):
            if ax[x, y] < args.alpha_threshold:
                continue
            counts[px[x, y]] = counts.get(px[x, y], 0) + 1
    if not counts:
        sys.exit("Image is fully transparent at this threshold.")
    ordered = sorted(counts, key=counts.get, reverse=True)
    if len(ordered) > len(SLOT_CHARS):
        sys.exit(f"Too many colours ({len(ordered)}); lower --colors.")
    slot_of = {c: SLOT_CHARS[i] for i, c in enumerate(ordered)}

    rows = []
    for y in range(grid_h):
        row = []
        for x in range(grid_w):
            row.append("." if ax[x, y] < args.alpha_threshold else slot_of[px[x, y]])
        rows.append("".join(row))

    palette = {slot: "#%02x%02x%02x" % c for c, slot in slot_of.items()}
    spec = {
        "name": args.input.stem,
        "fps": 8,
        "palette": palette,
        "frames": {"base": rows},
        "animations": {"idle": {"frames": ["base"], "loop": True}},
    }

    print(f"# {grid_w}x{grid_h}, {len(palette)} colours")
    for slot, colour in palette.items():
        print(f"#   {slot} = {colour}")
    print("\n".join(rows))
    if args.out:
        args.out.write_text(json.dumps(spec, indent=1), encoding="utf-8")
        print(f"\nwrote draft spec to {args.out}")


if __name__ == "__main__":
    main()
