# Roadmap

Living document. Items move up when we decide to do them; new ideas land at the bottom of the relevant section. Each entry should answer *what*, *why*, and *enough design intent that the next person can start*.

---

## Sooner (this session or next)

### 0d. Theatre: LLM colour commentator (tier 2 narration)

**What.** The Theatre's caption bar is currently rule-based (deterministic teaching beats keyed on event type — free, instant, always on). Add an optional second tier: a cheap `utility`-tier model receives batched trace events plus a rolling summary every few seconds and produces one-liner colour commentary in a persona (sports commentator, nature documentary). Rendered as a sixth pixel character at a commentary desk.

**Why.** Rule-based captions teach; a live commentator entertains. The "entertaining" leg of the simple/measurable/entertaining brief.

**Design intent.** Server-side: a small `/api/commentary` WebSocket or the existing live broker; reuse `src/provider.py` tiers. Client: a `commentary` event type already conceptually exists (presentation view has one). Keep tier 1 as fallback when no API key is configured — the Theatre must stay zero-key.

### 0e. Theatre: sharpen live-mode agent attribution

**What.** Hook payloads carry no agent identity, so live mode attributes tool events to the most recently spawned open subagent (see `src/trace/live.py`). Improve: correlate against the session transcript file (`transcript_path` arrives in every hook payload — tail it server-side to know which sidechain is active), or at minimum track multiple open Tasks as a set with round-robin hints.

**Why.** Parallel delegations are exactly the moment the Theatre is most impressive — and currently the moment live badges are least accurate.

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

## Later (on the list, not next)

### 2a. CD → Artist v1.1: vision review

**What.** Today the CD reads the Artist's *text description* of the generated image — it never "sees" the image. Switch the CD to a vision-capable model (or add a separate "Critic" vision-agent node) so review feedback is grounded in pixels, not adjectives.

**Why.** It's the difference between the rework loop being real and being theatre.

**Where it lives.** `src/agent.py` or a new vision-call helper (image content blocks in the messages), plus a vision-capable model tier in `config.yaml` and the CD node's prompt in `src/graph/presets/cd_artist.json`.

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
- **Heads-up:** the validator currently hard-rejects delegate cycles (`validate_graph`) and the executor *also* suppresses revisits at runtime. Pick one place for the cycle budget and make the other defer to it before shipping this.

**Risk.** Cycles. Don't ship this without an explicit recursion budget and a test that proves a two-agent ping-pong terminates.

---

### 4. Flow animation: make information movement legible

**What.** We already have gold sparks travelling along firing edges (`_sparks` in editor.js) and a client-side ↻ REPLAY of the last run. The next pass:
- **Show the payload, not just the firing.** A short hover tooltip on an active edge that shows the most recent message that travelled along it (truncated).
- **Direction-aware sparks.** Once edges can be bidirectional, sparks need to travel both ways and be visually distinguishable (e.g. gold for forward call, silver for return).
- **Idle-state hint.** A very subtle dashed flow animation on edges *before* the run starts, just enough to communicate "this is a live wire" without being noisy. Optional, behind a toggle.

**Why.** When a graph gets to 5+ agents, "who just called whom and what did they say" stops being obvious from the gold pulse alone.

**Design intent.**
- Payload tooltip: server already emits `edge_fired` events; extend with a payload preview (first ~200 chars of the delegation message). Frontend stores per-edge last-payload and shows on hover.
- Replay already exists client-side; a server-persisted `run_trace` per run_id would let replays survive a page reload — only worth it if demos need it.

---

## Parking lot (ideas, not commitments)

- Node groups / collapsible subgraphs (a "Production" group containing Director + Production Manager).
- Export a graph as a self-contained Python script (the graph compiled to code, for users who want to leave the playground).
- Versioned graph history — undo/redo beyond the last action, named checkpoints.
- Multiple named save slots for graphs (today SAVE/RESTORE is a single localStorage slot).
- Blackboard / artifact store: `write_artifact`/`read_artifact` tools (opt-in skill node) so deep graphs stop relaying full payloads through every parent's context.
- Structured outputs (`response_format: json_schema`) for the pitch deck instead of parsing fenced JSON — pending provider support check.
- Token streaming into the log panel (watch agents "think" live).
- Theatre: adapters for other agent frameworks (LangGraph, OpenAI Agents SDK) — the normalized trace schema in `src/trace/claude_adapter.py` was designed to be source-agnostic.
- Theatre: walk-on/walk-off sprite animations (legs actually moving) and a "commentary desk" corner set-piece.
- Theatre: export a replay as a shareable video/GIF for talks.
- Theatre: headless `claude -p --output-format stream-json` relay script as an alternative live source (hooks already cover both interactive and -p runs).

---

## How to use this file

- New items land in **Parking lot** by default.
- Promote to **Later** when we agree it's worth doing eventually.
- Promote to **Sooner** when it's the next thing on deck.
- Done items get deleted, not crossed out — the commit history is the record.
