# Pixel animation — cycles, timing, and the rules that sell motion

Pixel animation is pose-to-pose: draw the KEY poses first, verify they
read, then add in-betweens only if the motion still feels stiff. A
4-frame cycle with correct keys beats a 16-frame cycle with mushy ones.

## 0. Global rules (apply to every cycle)

- **Anchor rule**: pick the ground row (the y of the feet at contact).
  It must not drift between frames unless the character is airborne.
  Verify on the contact sheet: feet bottom row identical across frames.
- **Bob budget**: torso/head vertical movement in a cycle is **1 px**
  (2 px only for big grids ≥32 px tall or exaggerated styles). More
  looks like bouncing on a trampoline.
- **Counter-motion**: arms oppose legs; hair/scarves/tails trail one
  frame behind the body (follow-through — cheapest life you can add).
- **Timing over frames**: vary `durations_ms` instead of adding frames.
  Hold key poses longer; rush the transitions. Ease-in/ease-out =
  longer durations at the extremes of a swing.
- **Frame rate**: 8–12 fps feel (100–140 ms/frame) is the genre default.
  Snappy actions run 60–90 ms; idles run 300–600 ms.
- **Pixel-integer motion**: everything moves in whole pixels. "Half a
  pixel" is faked with an intermediate shade at the leading edge
  (sub-pixel animation — advanced; skip below 16 px).
- **Mirroring**: for symmetric characters, the second half of a walk is
  `flip_h` of the first — the spec format supports
  `"walk3": {"flip_h": "walk1"}`. Asymmetric characters (satchel, scar)
  must be redrawn, not flipped.

## 1. Idle / breathe (2–4 frames, loop, 300–600 ms/frame)

| frame | change from base |
|---|---|
| 1 | base pose |
| 2 | torso+head down 1 px (exhale), shoulders in 1 px |
| 3 (optional) | = frame 1, but eyes closed (blink) |

Blink on a long-held frame, not its own fast frame. A 2-frame breathe
at 500 ms is the minimum "this character is alive" loop.

## 2. Walk (4 or 6 frames, loop, 100–140 ms/frame)

The canonical 4-frame cycle — poses in order:

| frame | pose | legs | body height | arms |
|---|---|---|---|---|
| 1 | **contact R** | right foot fwd, left back, both on ground | base | left arm fwd |
| 2 | **passing** | legs together under body, one knee up | **+1 px (up)** | arms at sides |
| 3 | **contact L** | `flip_h` of 1 (if symmetric) | base | right arm fwd |
| 4 | **passing** | often = frame 2 (or its flip) | +1 px | arms at sides |

The contact pose determines 80% of the walk — draw it first, at full
stride width (feet ~40% of grid width apart). 6-frame version: insert a
"down" pose (body −1 px, weight absorbing) after each contact.

**Moving vs in-place**: cycles are authored in place; the *game/stage*
moves the character. Feet must appear to push backwards — on contact
frames the planted foot slides 1 px back relative to the body if you
want extra grounding (optional at small sizes).

## 3. Run (4–6 frames, loop, 60–90 ms/frame)

Like walk but: lean the whole torso 1–2 px forward, stride wider, add an
**airborne frame** (both feet off ground, body +1 px) replacing one
passing pose, arms pump higher. Runs read better with FEWER, snappier
frames than walks.

## 4. Jump (5–7 frames, play once, uneven timing)

| frame | pose | timing |
|---|---|---|
| 1 | **anticipation**: crouch — body down 2 px, knees bent, arms back | 120–180 ms (hold it!) |
| 2 | **launch**: stretched tall +1 px, arms up, toes leaving ground | 60–80 ms |
| 3 | **rise/apex**: airborne, legs tucked, body at peak height | 100–140 ms |
| 4 | **fall**: legs reaching down, arms out | 80–100 ms |
| 5 | **land**: crouch again (squash — 1 px wider is the classic squash) | 100 ms |
| 6 | **recover**: back to base | 120 ms |

Anticipation and landing squash are what sell it; the airborne frames
are almost incidental. Vertical travel happens via empty rows in the
grid (author the grid tall enough) or by the stage moving the sprite —
prefer the stage for reuse, and keep the sprite's own frames at
consistent height with pose changes only. If authoring travel into the
frames, add 3–4 empty rows of headroom.

## 5. Laugh (2–3 frames, loop 3–5 times, 90–130 ms/frame)

| frame | change |
|---|---|
| 1 | head tilted back 1 px, mouth open (dark px), shoulders up 1 px |
| 2 | shoulders down 1 px, mouth closed/half |
| 3 (optional) | = 1 with eyes closed |

Laughter is shoulder motion, not face motion, at small sizes.

## 6. Wave / emote gesture (3–4 frames, ping-pong)

Arm at 3 positions (down-mid-up); play 1-2-3-2-1-2-3… Add 1 px head
tilt toward the raised arm. Ping-pong = list frames forward then
backward in the animation's frame list.

## 7. Walk-on / walk-off (for stages like the Theatre)

Don't author screen travel into frames. Loop the walk cycle while the
*renderer* translates the sprite horizontally ~1–2 px per frame at
sprite scale (i.e. one grid-pixel every 1–2 animation frames — faster
looks like skating, slower like moonwalking). Flip_h the whole cycle
for the opposite direction.

## 8. Animation QA checklist (run on every contact sheet + GIF)

1. Anchor: is the ground row identical on all grounded frames?
2. Bob: does the head move exactly 1 px, in the right frames (up on
   passing, base on contact)?
3. Alternation: on contact L, is the *right* arm forward? (Arms must
   oppose legs — the #1 walk-cycle authoring bug.)
4. Silhouette: does each frame still pass the silhouette test?
5. Cluster hygiene: did animating create orphan pixels?
6. `render.py --validate` diff counts: roughly even px-change between
   consecutive frames? A frame pair with 0 changes is a dead frame; one
   pair changing 3× more than others is a pop.
7. Watch the GIF at target scale: does anything flicker that shouldn't?
   (Usually an outline pixel appearing/disappearing between frames.)
