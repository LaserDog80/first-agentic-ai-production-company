---
name: pixel-art-animator
description: Create and animate pixel-art characters from a text description or a supplied image — sprite specs as editable ASCII-grid JSON, rendered to PNG contact sheets and animated GIFs at any grid size, aspect ratio, and scale. Use when asked to design pixel sprites or characters, make walk/idle/jump/laugh/emote cycles, convert an image to pixel art, or produce retro game-style animated assets.
---

# Pixel Art Animator

Author pixel characters as **data** (ASCII grids + palette in JSON), render
them with the bundled script, **look at the render**, and iterate. Never
trust an unrendered grid: you cannot judge pixel art from row strings, and
neither can anyone else.

## The non-negotiable loop

```
draw/edit spec  →  render contact sheet  →  Read the PNG  →  critique
     ↑                                                          |
     └────────────── fix what the checklist caught ←────────────┘
```

Minimum two passes for a new character; more for animation. Only ship
after a render you have actually looked at passes both checklists
(`references/character-design.md` §6 and `references/animation.md` §8).

## Workflow

### 1. Read the references first

- `references/character-design.md` — grid/aspect choice, proportions,
  palette ramps, outlines, cluster hygiene, the static checklist.
- `references/animation.md` — per-cycle recipes (idle, walk, run, jump,
  laugh, wave, walk-on), timing tables, the animation checklist.

### 2. Establish the brief

From a description: pick grid size + aspect from the table in
character-design.md (default a standing humanoid to **16×20 or 16×24**;
go smaller only if the target style demands it), list the 2–3
identifying features that must survive, and choose ≤8 palette colours
with proper ramps. State these choices before drawing.

From a supplied image: run
`python scripts/from_image.py INPUT --width N --colors 8 --out spec.json`,
then hand-refine per character-design.md §7. The converter output is a
draft, never a deliverable.

### 3. Author the spec

One JSON file per character:

```json
{
  "name": "courier",
  "fps": 10,
  "palette": {"k": "#22242e", "s": "#f4c089", "t": "#e94560"},
  "frames": {
    "base":  ["..kk..", ".ksstk", "..tt.."],
    "walk1": ["..kk..", ".ksstk", ".t..t."],
    "walk3": {"flip_h": "walk1"}
  },
  "animations": {
    "idle": {"frames": ["base", "breathe"], "durations_ms": [500, 500]},
    "walk": {"frames": ["walk1", "pass", "walk3", "pass"], "durations_ms": [120, 120, 120, 120]}
  }
}
```

- Rows are strings, one char per pixel; `.` = transparent; every frame
  the same size. Any width/height works — the grid defines resolution
  and aspect ratio.
- `{"flip_h": "other"}` mirrors a frame — use for the second half of
  walk cycles on symmetric characters only.
- Draw the **base pose first** and get it approved by the loop before
  animating. Then author key poses (contact poses for walks,
  anticipation/land for jumps) before in-betweens.
- Editing tip: copy the previous frame and change the minimum number of
  pixels the recipe demands. Big inter-frame diffs are almost always
  authoring accidents — check with `--validate`.

### 4. Render and look

```bash
python scripts/render.py spec.json --out out/ --scale 10        # everything
python scripts/render.py spec.json --out out/ --anim walk       # one cycle
python scripts/render.py spec.json --validate                   # lint + frame diffs
```

- `*_sheet.png` — frames side by side, labelled. **Read this file** and
  run the checklists against it. This is where the iteration happens.
- `*.gif` — the moving result. Read it last to confirm; the first frame
  is what preview shows, so judge motion from the sheet + diff counts +
  final visual check.
- Critique concretely ("left arm merges with torso on frame 2 — move it
  1 px out", not "looks okay"). Fix, re-render, re-look.

### 5. Deliver / integrate

- Ship the spec JSON (the source of truth) plus rendered GIF/PNGs at the
  scale the user needs (`--scale`).
- `--export-groups` writes frames as `{color, coords}` pixel groups —
  drop-in for canvas renderers like this repo's `theatre-sprites.js`
  (`drawSprite` consumes exactly this shape, one frame at a time).
- For CSS/game engines: the contact sheet PNG is a usable spritesheet
  (fixed cell width = frame width × scale + padding), or render frames
  individually by looping `--anim` with `--no-gif` off.

## Example

`examples/courier.json` is a complete worked character (16×22, idle +
walk + jump + laugh) produced with this workflow — copy it as a starting
skeleton rather than starting from zero.
