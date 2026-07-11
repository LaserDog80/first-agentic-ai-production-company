#!/usr/bin/env python3
"""Render a pixel-art sprite spec (JSON) to PNGs and animated GIFs.

The spec format (see the skill's SKILL.md):

{
  "name": "courier",
  "fps": 10,                          // default; per-animation durations win
  "palette": {"k": "#1a1a1a", "s": "#f4c089", ...},
  "frames": {
    "walk1": ["...kk...", ".kssssk.", ...],   // rows of single chars
    "walk3": {"flip_h": "walk1"}              // horizontal mirror of a frame
  },
  "animations": {
    "walk": {"frames": ["walk1","walk2","walk3","walk4"],
             "durations_ms": [120,120,120,120],   // optional
             "loop": true}                        // default true
  }
}

'.' and ' ' are transparent. All frames must share one grid size.

Usage:
  python render.py SPEC.json --out DIR [--scale 10] [--fps 10]
                             [--anim walk] [--no-gif] [--export-groups]
  python render.py SPEC.json --validate

Outputs in DIR:
  <name>_<anim>_sheet.png   contact sheet: frames side by side, labelled —
                            LOOK AT THIS with the Read tool while iterating
  <name>_<anim>.gif         the animation itself
  <name>_groups.json        (--export-groups) frames as {color, coords} groups
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("render.py needs Pillow: pip install Pillow")

TRANSPARENT = {".", " "}
LABEL_H = 12  # px reserved under each contact-sheet frame for its label


# ── spec loading & validation ────────────────────────────────────────────────

def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    problems = validate_spec(spec)
    if problems:
        sys.exit("Spec invalid:\n  - " + "\n  - ".join(problems))
    return spec


def resolve_frame(spec: dict, name: str, _seen: frozenset = frozenset()) -> list[str]:
    """Return a frame's rows, resolving flip_h references."""
    raw = spec["frames"][name]
    if isinstance(raw, dict):
        ref = raw.get("flip_h")
        if name in _seen:
            raise ValueError(f"circular flip_h at '{name}'")
        rows = resolve_frame(spec, ref, _seen | {name})
        return [row[::-1] for row in rows]
    return raw


def validate_spec(spec: dict) -> list[str]:
    problems: list[str] = []
    palette = spec.get("palette") or {}
    frames = spec.get("frames") or {}
    anims = spec.get("animations") or {}
    if not frames:
        return ["no frames defined"]
    for key in palette:
        if len(key) != 1:
            problems.append(f"palette key '{key}' must be a single character")

    size: tuple[int, int] | None = None
    for fname, raw in frames.items():
        if isinstance(raw, dict):
            ref = raw.get("flip_h")
            if ref not in frames:
                problems.append(f"frame '{fname}': flip_h target '{ref}' missing")
            continue
        if not isinstance(raw, list) or not all(isinstance(r, str) for r in raw):
            problems.append(f"frame '{fname}': must be a list of row strings")
            continue
        widths = {len(r) for r in raw}
        if len(widths) != 1:
            problems.append(f"frame '{fname}': ragged rows (widths {sorted(widths)})")
            continue
        fsize = (widths.pop(), len(raw))
        size = size or fsize
        if fsize != size:
            problems.append(f"frame '{fname}': size {fsize} != {size} of earlier frames")
        unknown = {ch for row in raw for ch in row} - set(palette) - TRANSPARENT
        if unknown:
            problems.append(f"frame '{fname}': chars {sorted(unknown)} not in palette")

    for aname, anim in anims.items():
        seq = anim.get("frames") or []
        if not seq:
            problems.append(f"animation '{aname}': empty frame list")
        for f in seq:
            if f not in frames:
                problems.append(f"animation '{aname}': unknown frame '{f}'")
        durs = anim.get("durations_ms")
        if durs and len(durs) != len(seq):
            problems.append(f"animation '{aname}': {len(durs)} durations for {len(seq)} frames")
    return problems


# ── rendering ────────────────────────────────────────────────────────────────

def hex_rgba(hexstr: str) -> tuple[int, int, int, int]:
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def frame_image(spec: dict, fname: str, scale: int, bg=None) -> Image.Image:
    rows = resolve_frame(spec, fname)
    w, h = len(rows[0]), len(rows)
    img = Image.new("RGBA", (w * scale, h * scale), bg or (0, 0, 0, 0))
    px = img.load()
    palette = {k: hex_rgba(v) for k, v in spec["palette"].items()}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in TRANSPARENT:
                continue
            colour = palette[ch]
            for dy in range(scale):
                for dx in range(scale):
                    px[x * scale + dx, y * scale + dy] = colour
    return img


def contact_sheet(spec: dict, anim_name: str, scale: int) -> Image.Image:
    """Frames side by side on a neutral checker background, labelled."""
    seq = spec["animations"][anim_name]["frames"]
    imgs = [frame_image(spec, f, scale) for f in seq]
    fw, fh = imgs[0].size
    pad = max(4, scale)
    sheet = Image.new("RGBA",
                      ((fw + pad) * len(imgs) + pad, fh + pad * 2 + LABEL_H),
                      (34, 37, 54, 255))
    draw = ImageDraw.Draw(sheet)
    checker = (42, 46, 66, 255)
    for i, (img, fname) in enumerate(zip(imgs, seq)):
        x0 = pad + i * (fw + pad)
        for cy in range(0, fh, scale * 2):
            for cx in range(0, fw, scale * 2):
                draw.rectangle([x0 + cx, pad + cy,
                                x0 + min(cx + scale, fw) - 1,
                                pad + min(cy + scale, fh) - 1], fill=checker)
        sheet.alpha_composite(img, (x0, pad))
        draw.text((x0, fh + pad + 2), f"{i + 1}:{fname}", fill=(200, 205, 230, 255))
    return sheet


def render_gif(spec: dict, anim_name: str, scale: int, fps: int, out: Path) -> None:
    anim = spec["animations"][anim_name]
    seq = anim["frames"]
    default_ms = round(1000 / (spec.get("fps") or fps))
    durations = anim.get("durations_ms") or [default_ms] * len(seq)
    bg = (34, 37, 54, 255)  # GIF has no partial alpha; use the stage colour
    imgs = [frame_image(spec, f, scale, bg=bg).convert("P", dither=Image.NONE)
            for f in seq]
    imgs[0].save(
        out, save_all=True, append_images=imgs[1:],
        duration=durations, loop=0 if anim.get("loop", True) else 1,
        disposal=2,
    )


def export_groups(spec: dict) -> dict:
    """Frames as {color, coords} pixel groups (theatre-sprites.js shape)."""
    result: dict = {"name": spec.get("name", "sprite"), "animations": {}}
    for aname, anim in spec["animations"].items():
        frames_out = []
        for fname in anim["frames"]:
            rows = resolve_frame(spec, fname)
            by_colour: dict[str, list[list[int]]] = {}
            for y, row in enumerate(rows):
                for x, ch in enumerate(row):
                    if ch in TRANSPARENT:
                        continue
                    by_colour.setdefault(spec["palette"][ch], []).append([x, y])
            frames_out.append({"pixels": [
                {"color": c, "coords": coords} for c, coords in by_colour.items()
            ]})
        result["animations"][aname] = {
            "frames": frames_out,
            "durations_ms": anim.get("durations_ms"),
            "loop": anim.get("loop", True),
        }
    return result


# ── frame-to-frame diff (animation QA) ───────────────────────────────────────

def diff_report(spec: dict, anim_name: str) -> list[str]:
    seq = spec["animations"][anim_name]["frames"]
    lines = []
    for a, b in zip(seq, seq[1:] + seq[:1]):
        ra, rb = resolve_frame(spec, a), resolve_frame(spec, b)
        changed = sum(1 for y in range(len(ra))
                      for x in range(len(ra[0])) if ra[y][x] != rb[y][x])
        lines.append(f"  {a} -> {b}: {changed} px changed")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--out", type=Path, default=Path("pixel_out"))
    ap.add_argument("--scale", type=int, default=10)
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--anim", help="render only this animation")
    ap.add_argument("--no-gif", action="store_true")
    ap.add_argument("--export-groups", action="store_true")
    ap.add_argument("--validate", action="store_true", help="check the spec and exit")
    args = ap.parse_args()

    spec = load_spec(args.spec)
    name = spec.get("name", args.spec.stem)

    if args.validate:
        w = len(resolve_frame(spec, next(iter(spec["frames"])))[0])
        h = len(resolve_frame(spec, next(iter(spec["frames"]))))
        print(f"OK: {len(spec['frames'])} frames @ {w}x{h}, "
              f"{len(spec.get('animations', {}))} animations")
        for aname in spec.get("animations", {}):
            print(f"animation '{aname}':")
            print("\n".join(diff_report(spec, aname)))
        return

    args.out.mkdir(parents=True, exist_ok=True)
    anims = spec.get("animations", {})
    targets = [args.anim] if args.anim else list(anims)
    for aname in targets:
        if aname not in anims:
            sys.exit(f"No animation '{aname}' (have: {', '.join(anims)})")
        sheet = contact_sheet(spec, aname, args.scale)
        sheet_path = args.out / f"{name}_{aname}_sheet.png"
        sheet.save(sheet_path)
        print(f"wrote {sheet_path}")
        if not args.no_gif:
            gif_path = args.out / f"{name}_{aname}.gif"
            render_gif(spec, aname, args.scale, args.fps, gif_path)
            print(f"wrote {gif_path}")

    if args.export_groups:
        gpath = args.out / f"{name}_groups.json"
        gpath.write_text(json.dumps(export_groups(spec), indent=1), encoding="utf-8")
        print(f"wrote {gpath}")


if __name__ == "__main__":
    main()
