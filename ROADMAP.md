# Roadmap

Living document. Items move up when we decide to do them; new ideas land at the bottom of the relevant section. Each entry should answer *what*, *why*, and *enough design intent that the next person can start*.

---

## Sooner (this session or next)

### 0b. Creative Director → Artist workflow with image generation and feedback loop

**What.** A new preset / workflow: a Creative Director agent receives a brief, interprets it, and delegates to an Artist node. The Artist turns the interpretation into an image-generation prompt and calls an image API (placeholder/mock for v1). The CD then examines the returned image, decides whether it matches the brief, and either approves or returns feedback to the Artist for another attempt. Capped at **5 iterations**.

**Why.** First non-text-only workflow in the app. Exercises the rework-loop pattern on a multimodal output and forces us to build image display into the runtime — a prerequisite for any visual production workflow (storyboards, mood boards, character design).

**Design intent.**
- **Nodes.** New `artist` agent type. CD is a regular agent with a `delegate` edge to Artist plus a feedback/rework edge back from Artist's output.
- **Image API.** Start with a placeholder skill (`generate_image`) that returns a stub image URL or a locally-generated placeholder PNG. Wire the real provider (Nebius image endpoint? OpenAI Images? decide later) behind the same skill interface.
- **CD review step.** The CD needs to "see" the image. For v1 the CD reads the image's prompt + any returned metadata/caption and decides text-only; v2 uses a vision model to actually look at it. Mark this clearly — the v1 review is a stand-in.
- **Loop control.** Reuse the existing rework-loop machinery (Series Producer pattern) with `max_iterations: 5` on the CD→Artist edge. On exhaustion, emit the best-so-far with a "max iterations reached" flag.
- **Image display in the UI.** Biggest piece. The playground/presentation UI currently only renders text outputs. Need:
  - A new output subtype `image` (or `image_set` for multi-attempt).
  - Node output panel renders `<img>` thumbnails with click-to-enlarge.
  - Run summary panel shows the iteration history as a row of thumbnails with the CD's feedback under each.
  - Presentation mode renders the final image full-bleed.
- **Persistence.** Images saved under `output/web/<run_id>/` and served via the existing download route pattern; same `_RUN_ID_PATTERN` validation.

**Risk / open questions.**
- Real image generation is slow and costs more than text. Hard cap the 5 iterations and surface estimated cost in the run summary.
- Vision-based CD review is the right long-term answer; flag the text-only v1 review as a known limitation.

**Where it lives.** New preset under `src/graph/presets/`, new skill under `src/graph/skills/`, schema additions in `src/graph/schema.py` for the `image` output subtype, UI changes across `static/playground.html`, `static/presentation.html`, and the JS run-output renderers.

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
