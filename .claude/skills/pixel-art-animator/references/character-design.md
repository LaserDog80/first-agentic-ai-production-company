# Pixel character design — grids, proportions, palettes, readability

The static character has to be right before any animation starts. A bad
base sprite animated well still looks bad; a great base sprite with a
2-frame bob already looks alive.

## 1. Pick the grid (resolution + aspect ratio)

Grid choice IS the art style. Pick the smallest grid that can carry the
character's identifying features — every extra pixel is more work in
every animation frame.

| Grid (w×h) | Style | Head:body | Carries |
|---|---|---|---|
| 8×8       | icon / tiny NPC | 1:1 | one silhouette + 1 accessory |
| 12×12–16×16 | classic retro | 1:1.5 | face dots, 2 accessories |
| 16×20–16×24 | chibi (this range is the sweet spot for characters) | 1:2 | eyes, hands, props, expression |
| 24×32 | detailed chibi | 1:3 | fingers-ish, clothing folds |
| 32×48+ | "hi-bit" | 1:3.5 | real anatomy, shading ramps |

- **Aspect ratio**: standing humanoids want portrait grids (w:h around
  2:3 to 1:2). Wide characters (animals, vehicles) invert this. Nothing
  in the spec format assumes any ratio — set it per character.
- Leave **1–2 empty columns/rows of margin** in the grid around the
  resting pose: animation needs room (arm swings, jump crouch, hair
  follow-through) without resizing the canvas mid-project.
- **Even-width grids** make symmetric characters easier (2-px spine);
  odd widths give a true 1-px centreline. Both fine — just decide.

## 2. Proportions

At small sizes, exaggerate what identifies the character and delete
everything else. Order of importance: **silhouette → head → torso colour
→ accessory → face**. Hands and feet become 1–2 px blocks; necks usually
don't exist below 24 px tall.

## 3. Palette discipline

- **2–4 shades per material** (skin, hair, cloth). More reads as noise.
- **Hue-shift the ramps**: shadows go cooler/darker-blue, highlights go
  warmer — not just darker/lighter of the same hue. A shadow for
  `#e94560` red is `#8f2b4e` (toward purple), not `#752230` (just dark).
- Avoid pure `#000` / `#fff` except for eyes, sparkle, or deliberate
  high-contrast outline at tiny sizes.
- Whole character: **≤8 colours** below 24 px tall, ≤12 above.
- Check contrast against the intended background colour, at the intended
  *display* scale, not zoomed in.

## 4. Outlines

- **≤16 px tall**: full dark outline (near-black, not pure black) keeps
  the sprite readable on any background.
- **Bigger**: use *sel-out* (selective outline) — outline each region
  with a darker shade of its own fill; drop the outline entirely on the
  light-facing side. Uniform black outlines at high resolutions look
  like colouring books.
- Interior lines only where materials meet; never outline every cluster.

## 5. Cluster hygiene (what makes pixel art look "clean")

- A **cluster** is a contiguous same-colour region. Good sprites are made
  of deliberate clusters, 2+ px each. **Orphan pixels** (a single pixel
  not connected to its colour's cluster) read as dirt — every one must
  be intentional (eye glint, sparkle).
- Avoid **banding**: parallel 1-px lines of stepped shades hugging an
  edge (staircase within staircase). Merge or offset them.
- Avoid perfectly straight long diagonals broken by one irregular step
  ("jaggies") — keep stair steps even: 1-1-1 or 2-2-2, not 1-2-1.

## 6. The self-review checklist (run on every render)

Look at the rendered contact sheet and answer honestly:

1. **Silhouette test** — imagine it filled with one colour: still
   recognisable? (Trace the outer edge with your eyes.)
2. Are the read priorities right — do you see head/face first?
3. Any orphan pixels or accidental banding?
4. Do materials separate (hair vs skin vs cloth) at 1× mental zoom?
5. Is it balanced over its feet? (Centre of mass above the contact row.)
6. Symmetry check: if the pose is symmetric, are left/right actually
   mirrored? (Off-by-one arms are the most common authoring bug.)

## 7. Converting a supplied image

`scripts/from_image.py` gets you a quantized draft, never a finished
sprite. After conversion always: delete orphan pixels, re-limit the
palette (quantizers keep muddy in-betweens), rebuild the silhouette by
hand, and push identifying features 20% bigger than "accurate". Faces
almost always need manual re-drawing — quantizers destroy eyes.
