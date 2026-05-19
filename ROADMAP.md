# Roadmap

Living document. Items move up when we decide to do them; new ideas land at the bottom of the relevant section. Each entry should answer *what*, *why*, and *enough design intent that the next person can start*.

---

## Sooner (this session or next)

### 0c. Run-output tray UX upgrades (thumbnails, resizable, image-strip view)

**What.** Three related improvements to the bottom run-output panel that became obvious as soon as the `cd_artist` preset shipped real images into it.

1. **Thumbnails, not full-bleed.** Right now the OUTPUT tab renders each image at intrinsic size — a single 1024×576 fal image fills the whole tray and pushes everything else off-screen. Render each attempt as a small thumbnail (~180px wide) in a flex-wrap row. Click a thumbnail to enlarge it (modal lightbox / inline expand — either is fine).
2. **Resizable tray.** The bottom region is currently a fixed `200px` row in the grid. Add a drag-handle on the top edge so the user can pull it up to see more of the output (or shove it down to give the canvas more room). Persist the height in localStorage.
3. **Image-strip view of all attempts.** Today the OUTPUT tab stacks attempts vertically with the final on top. After (1), put the *whole* iteration history into a horizontal strip — first attempt on the left, last on the right, latest framed in gold. Optionally promote this into its own tab next to LOG and OUTPUT (e.g. "IMAGES (3)"), so the user can flick to it during a run and watch attempts land one at a time without losing the LOG view.

**Why.** During the first live demo the final image dominated the tray; the user never saw the earlier attempts (they were below the fold, hidden behind the FINAL frame) and couldn't resize to reveal them. The whole point of the rework loop is showing the *evolution* — that needs to be visible by default, not after a scroll.

**Design intent.**
- Thumbnails: existing `.output-image-card` already has a `.final` modifier; switch the wrap from `flex-direction: column` to `flex-direction: row; flex-wrap: wrap;` and constrain card width. Lightbox can be a single `<div>` overlay that copies the `src`, no library.
- Resizable: a 6px-tall absolutely-positioned handle inside the grid track's top border; `mousedown` → capture, `mousemove` → write a CSS variable for the row height, `mouseup` → save to localStorage. Re-apply on page load.
- Image-strip tab: cheap option is just to keep it in OUTPUT but lay them horizontally. The dedicated IMAGES tab is nicer — gate it on `run_summary.images.length > 0` so it doesn't show up for text-only runs.

**Where it lives.** `static/playground.html` (markup + CSS for the new tab/handle, switchTab() to render the strip, the lightbox overlay). No backend changes — `run_summary.images` already carries everything needed.

---

### 1. Snap-to-hierarchy on node placement and drag

**What.** When a node is dropped or dragged, snap it to a column/row in an implicit hierarchy: the same x-coordinate as nodes at the same depth from the input, the same y-coordinate as its siblings. A first pass can be axis-snap (just lock to the nearest existing column/row within N pixels); a second pass can auto-layout the whole graph on demand (`L` key, maybe).

**Why.** The graphs read as agent hierarchies (Series Producer → Producer → Researcher / Director / Production Manager). Right now the user does the alignment by eye every time and it drifts as soon as a node is added. Snapping makes the hierarchy *visible* and makes screenshots / demos look intentional without manual fussing.

**Design intent.**
- Compute depth for each node by BFS from the input node (or from any node with no incoming edges if there's no input).
- For each depth level, collect the existing x-coordinates of nodes at that depth. While dragging, if the cursor x is within ~12px of one of those, snap to it. Same idea for y vs. siblings (same parent).
- Keep the existing `GRID = 16` snap as a fallback when there's no hierarchy match.
- Visual: a faint vertical/horizontal guide line at the snap target while dragging, like Figma.
- Out of scope for v1: full auto-layout. Just snap-while-dragging.

**Where it lives.** `static/js/editor.js` — `_onMouseMove` while `this._drag` is active, before writing back `node.position`.

---

### 2. Node detail sidebar (click → inspect)

**What.** Click any node, a sidebar slides in from the right showing every editable property for that node: name, system prompt (full multi-line editor, not a one-line wizard field), model tier, max iterations, attached skills (read-only list of incoming skill edges), and — for non-agent nodes — whatever the equivalent fields are (skill config, output subtype, etc.). Edits apply live. Close with `Esc` or by clicking the canvas.

**Why.** This is the single biggest UX gap. Right now creating an agent goes through a one-shot wizard, and revising the system prompt afterwards is awkward. As prompts get longer (and they will — the pitch deck preset has agents with multi-paragraph prompts), there's nowhere good to read or edit them. A sidebar is the standard solution in every node-graph tool worth copying (ComfyUI, n8n, Retool, Cursor's agents pane).

**Design intent.**
- Reuse the existing `onSelect(node)` hook in `editor.js:102` — it already fires on selection. Instead of (or alongside) launching the wizard, render a sidebar panel in the page chrome.
- Keep the canvas the centre of gravity: sidebar is ~360px wide on the right, overlays nothing important, has a close button. Pixel-art aesthetic matches the rest (chunky border, monospace, gold accent).
- Two-way binding: editing the textarea writes straight into `node.system_prompt` and triggers a re-render. No "Save" button — the graph is already saved to localStorage on change.
- Show *derived* info too: a small "Connections" section listing incoming/outgoing edges by kind, so you can see what tools this agent has been granted without leaving the sidebar.
- Long prompts: monospace textarea, soft-wrap, autoresizing up to a max-height with internal scroll.
- Mobile/narrow: collapses to a bottom sheet. Not a priority but cheap to keep in mind.

**Where it lives.** `static/playground.html` for the sidebar markup + styles, `static/js/editor.js` for the data binding, and a small `sidebar.js` (new) to keep editor.js from ballooning.

---

## Later (on the list, not next)

### 2a. CD → Artist v1.1: vision review and presentation-mode rendering

**What.** Follow-ups to the v1 `cd_artist` preset that just shipped.
- **Vision-based review.** Today the CD reads the Artist's text description of the generated image — it never "sees" the image. Switch the CD to a vision-capable model (or add a separate "Critic" vision-agent node) so review feedback is grounded in pixels, not adjectives.
- **Presentation-mode wiring.** Right now the final image only renders in `/playground`'s OUTPUT tab. `/present` still assumes the legacy pitch-deck event vocabulary. Teach the presentation runtime to render arbitrary `output_subtype: "image"` runs full-bleed, with the iteration history as a filmstrip below.
- **Cost meter.** Surface estimated fal.ai cost per run in the run summary (≈$0.003/image × N attempts).

**Why.** v1 ships the loop and the playground experience. These two changes are what makes it demo-grade: real visual judgement from the CD, and a cinematic surface for showing it off.

**Where it lives.** `src/prompts/` (CD prompt change), `src/agent.py` or a new vision-call helper, `static/presentation.html` + `static/js/`, `app.py` run summary.

---

### 3. Edge directionality controls

**What.** Right now an edge's *kind* is derived from `(srcType, dstType)` and its *direction* is implicit (source bottom slot → target top slot). We want to be able to mark an edge as:
- **Unidirectional** (current default — A delegates to B, B never calls back).
- **Bidirectional** (A and B can both invoke each other — think: a Producer ↔ Researcher dialogue loop).
- **Omnidirectional / broadcast** (one source fans out to many, all of them can respond back into the source).

The UI piece is choosing direction at edge-creation time (or by clicking the edge to flip it). The runtime piece is bigger: the executor today walks the graph as a DAG. Bidirectional and omnidirectional edges break that assumption and need cycle handling, depth limits, and a clear semantics for "B calls A back" — probably "A exposes B as a tool *and* B exposes A as a tool, with a shared call-depth budget to prevent infinite ping-pong."

**Why.** Some of the most interesting agent patterns aren't trees. Reviewer/writer loops, debate, planner ↔ executor refinement — all need a back-channel.

**Design intent.**
- Edge schema: add `direction: "forward" | "bidirectional" | "broadcast"`, default `"forward"`. Existing edges migrate as forward.
- Visual: forward = single arrowhead (current); bidirectional = arrowhead at both ends; broadcast = open dot at the "many" end. Colour stays kind-coded.
- Editor: while dragging an edge, hold `Shift` to make it bidirectional, `Alt` for broadcast. Also a small dropdown when an edge is selected.
- Runtime: a bidirectional `delegate` edge between A and B means A gets a `delegate_to_b` tool *and* B gets a `delegate_to_a` tool. Add a shared `call_depth` counter on the run context; abort if it exceeds a configurable max (default 4). This is the hardest part — leave a design doc before coding.

**Risk.** Cycles. Don't ship this without an explicit recursion budget and a test that proves a two-agent ping-pong terminates.

---

### 4. Flow animation: make information movement legible

**What.** We already have gold sparks travelling along firing edges (`_sparks` in editor.js). The next pass:
- **Show the payload, not just the firing.** A short hover tooltip on an active edge that shows the most recent message that travelled along it (truncated).
- **Replay mode.** After a run finishes, scrub a timeline at the bottom of the canvas to replay node activations and edge firings in order. Useful for demos and for debugging "why did this agent call that one?"
- **Direction-aware sparks.** Once edges can be bidirectional, sparks need to travel both ways and be visually distinguishable (e.g. gold for forward call, silver for return).
- **Idle-state hint.** A very subtle dashed flow animation on edges *before* the run starts, just enough to communicate "this is a live wire" without being noisy. Optional, behind a toggle.

**Why.** When a graph gets to 5+ agents, "who just called whom and what did they say" stops being obvious from the gold pulse alone. Replay is also the single best demo asset — it turns a black box into a story.

**Design intent.**
- Payload tooltip: server already emits `edge_fired` events; extend with a payload preview (first ~200 chars of the delegation message). Frontend stores per-edge last-payload and shows on hover.
- Replay: server logs a `run_trace` (ordered list of events) per run; frontend can re-emit them client-side at configurable speed.
- Build replay first — it's the most useful and the cleanest to scope. Idle animation last.

---

## Parking lot (ideas, not commitments)

- Node groups / collapsible subgraphs (a "Production" group containing Director + Production Manager).
- Live cost meter per run (tokens spent per agent, summed in the bottom bar).
- Export a graph as a self-contained Python script (the graph compiled to code, for users who want to leave the playground).
- Versioned graph history — undo/redo beyond the last action, named checkpoints.

---

## How to use this file

- New items land in **Parking lot** by default.
- Promote to **Later** when we agree it's worth doing eventually.
- Promote to **Sooner** when it's the next thing on deck.
- Done items get deleted, not crossed out — the commit history is the record.
