# Presentation Mode plan

**Status:** plan only. Written for a fresh Claude Code session to pick up cold.
**Author session:** 2026-05-17, on branch `feat/playground-sidebar-and-snap`.
**Audience:** the next session that will start implementing this.

---

## Goal

The repo currently has two parallel apps:

- **`main` branch** ships a hand-crafted *presentation* of the five-agent
  pitch-deck pipeline — pixel-art characters that animate during a run,
  commentary, evidence tabs, PPTX export. Beautiful, demo-grade, but
  hard-coded for the pitch-deck case.
- **`feat/playground-*` branches** (this branch, and its parent
  `adapt/playground-with-main-fixes`) ship a generic *playground*: a
  node-based graph editor with six presets that can be created, edited,
  saved, and executed.

The user wants both modes to live together, with a runtime toggle, and
they want the presentation experience to **work for every preset**, not
just pitch deck. So: load the Research Assistant preset, hit a
"Presentation Mode" toggle, and you should see a little researcher
character animating during the run — same UX, different preset.

This is a significant refactor because the two apps don't share an
event vocabulary or an executor. The plan below works the unification
in phases that each leave the app in a shippable state.

---

## Current state (what each side actually has)

### Main branch — `static/index.html` (94 kB, single file)

- All character art lives inline as CSS pixel-art in a JS constant
  `CHARACTERS = [...]` (starts ~line 1031 of `static/index.html` on
  `origin/main`). Each entry has `id`, `name`, `role`, and a `pixels`
  array of `{ color, coords: [[x,y], …] }`.
- Five characters: `series_producer`, `producer`, `researcher`,
  `director`, plus probably `production_manager` and a commentary
  narrator. Each is ~30 pixel groups, hand-tuned.
- The `.character-slot` CSS class has states: idle, `.active`,
  `.done`, `.rework`, `.intro-highlight`, `.intro-dim`. Active and
  rework animations are CSS keyframes.
- The page-level WS client (search `case '...'` in index.html ~line
  1598) consumes this event vocabulary:
  `pipeline_start`, `agent_start`, `agent_done`, `tool_call`,
  `rework`, `status`, `pipeline_complete`, `pipeline_error`,
  `commentary`, `outro`, `error`.
- Result tabs: Deck / Evidence / JSON / Learn — pitch-deck-specific.
- Server side: `src/orchestrator.py` (36 kB) is a *hand-coded*
  pipeline. It emits the events above directly. It's not driven by
  any graph definition; the agent ordering is in Python.

### This branch — `static/playground.html` + `src/graph/*`

- Node editor with multi-select, side-slots, drag-spawn, sidebar.
- Six presets: `pitch_deck`, `news_brief`, `trip_planner`,
  `short_film_quote`, `two_sided_take`, `research_assistant`. Each
  is a JSON graph in `src/graph/presets/`.
- `src/graph/executor.py` is generic — runs any preset. Emits:
  `graph_run_start`, `node_started`, `node_finished`, `tool_call`,
  `edge_fired`, `graph_run_complete`, `graph_run_error`.
- `app.py` is the graph-mode entry point. The pipeline orchestrator
  is **not** wired up on this branch.

### The two gaps

1. **Event vocabulary mismatch.** Main's UI listens for
   `agent_start`/`agent_done`; this branch emits
   `node_started`/`node_finished`. Either side needs to bridge.
2. **Character data only exists for pitch deck.** A Research
   Assistant preset doesn't have a "researcher woman with magnifying
   glass" sprite, because no one designed one.

---

## Architectural decision: unify on the graph executor

There are three plausible shapes. Picking **B**.

| Option | Sketch | Pros | Cons |
|---|---|---|---|
| A. Keep two orchestrators | Presentation calls the pitch-deck orchestrator; playground calls the graph executor. | Minimal change. | Presentation only works for pitch-deck — that's what we're trying to fix. ❌ |
| **B. Unify on graph executor** | Pipeline orchestrator deleted (or thin-wrapped). Presentation is a *view* that subscribes to the graph executor's events. Characters are looked up per node. | One executor, one event stream. Presentation works for any preset by definition. Pitch-deck-specific behaviour (commentary, evidence tabs) becomes optional features keyed on node subtype/metadata. | Real work. Need to port pitch-deck's special behaviours (commentary stream, evidence tab, PPTX export wiring) into the graph executor. |
| C. Hybrid | Two presentation paths — pitch-deck still uses the rich orchestrator, others use a thinner graph-driven path. | Keeps pitch-deck's polish without porting everything. | Two code paths for the same feature forever. Future presets accumulate in the thin path while pitch-deck rots in the special one. |

**Recommendation: B.** It's more work up front but produces a single
maintainable system. Option C feels safer but creates permanent drift.

---

## Character data strategy

The bottleneck is *visual content*. Each agent in each preset wants a
sprite. Five presets × 2–5 agents each ≈ 15–25 new sprites if we
hand-design every one. That's the most expensive part of this work.

**Suggested phasing:**

1. **MVP fallback first.** Build a *generic* animated agent
   placeholder — a stylised pixel-art figure that's typed by node
   colour (red = agent, gold = input/output, green = skill). It
   animates with the same active/done states as the bespoke
   pitch-deck characters. Every preset works on day one of
   presentation mode, even ugly.
2. **Bespoke art per preset, deferred.** Each preset's JSON gains an
   optional `presentation` block per node:
   ```json
   { "id": "n_researcher",
     "type": "agent",
     "label": "Web Researcher",
     "presentation": {
       "sprite": "researcher_v1",
       "role": "Fact Finder"
     } }
   ```
   The viewer checks `presentation.sprite` against a registry; falls
   back to the generic figure if missing.
3. **Sprite registry** lives in its own module — `static/js/sprites.js`
   or similar — exporting `{ [spriteId]: PixelData }`. The existing
   pitch-deck characters land there as the first five entries, keyed
   by sprite id (not by hard-coded role name, so other presets can
   reuse them: News Curator could borrow the producer sprite while
   waiting for its own).

This keeps art separate from preset structure, lets art evolve
independently, and gives every preset a working presentation from
day one.

---

## Phases of work (each independently shippable)

### Phase 1 — Port main's UI into this branch as a separate page

- Copy `origin/main:static/index.html` to `static/presentation.html`
  on a new branch (`feat/presentation-mode` off
  `adapt/playground-with-main-fixes`).
- Add a route in `app.py` so `/playground` serves `playground.html`
  (rename current `/` → `/playground`), `/present` serves
  `presentation.html`, and `/` becomes a small chooser.
- For now `presentation.html` still listens for the old vocabulary
  and *fails* unless you wire up the old orchestrator. That's fine —
  Phase 2 fixes it. Goal of Phase 1 is just "both pages exist
  side-by-side again."
- Lift the inline `CHARACTERS = […]` constant out of the HTML into
  `static/js/sprites.js`. No behavioural change — just stop inlining
  art in markup.

**Risk:** main's `index.html` references CSS/keyframe names that
might collide with `playground.html`. They live on different routes,
so unless you ever embed one in the other, scoping isn't urgent.

### Phase 2 — Make `presentation.html` listen to graph-executor events

Translate the old vocabulary onto the new one:

| Old event | New event | Notes |
|---|---|---|
| `pipeline_start` | `graph_run_start` | Same shape; rename in handler |
| `agent_start` | `node_started` | New event carries `node_id`; sprite lookup uses `node.presentation.sprite` |
| `agent_done` | `node_finished` | Same |
| `tool_call` | `tool_call` | Identical |
| `rework` | (deferred) | Graph executor doesn't have a rework concept yet — see Phase 5 |
| `pipeline_complete` | `graph_run_complete` | Same |
| `pipeline_error` | `graph_run_error` | Same |
| `status` | (deferred) | Used for inter-phase commentary in pitch-deck — see Phase 4 |
| `commentary`, `outro` | (deferred) | Same — Phase 4 |

After Phase 2, presentation mode works for *every* preset — but only
the core run animation. No commentary, no rework, no evidence tab.
For Research Assistant this is enough. For Pitch Deck this regresses.

### Phase 3 — Restore PPTX export

- `src/pptx_exporter.py` and `src/scene_renderer.py` already exist on
  this branch (carried over from main). The graph executor knows
  about the `pitch_deck` output subtype.
- Verify `app.py`'s `run_summary` event still includes
  `download_url` when an output node with subtype `pitch_deck` runs.
- Tab UI: `presentation.html` shows the Deck tab only when the run
  produced a pitch deck. The check is "did the run summary include a
  download_url / pitch_deck payload?", not "is this the pitch_deck
  preset?". Generalised.

### Phase 4 — Commentary stream (optional, restores pitch-deck polish)

- The current graph executor doesn't emit commentary. On main,
  `src/commentary.py` runs a parallel agent that narrates each
  pipeline stage.
- Easiest port: make commentary a *separate* graph node type
  (`commentator`?) or a `presentation.commentary: true` flag on an
  agent node. The executor optionally streams its output as
  `commentary` events alongside `tool_call`.
- Cheapest first cut: don't port it. Presentation mode runs silently.
  Phase 4 is gravy.

### Phase 5 — Rework signal (optional)

- Main's orchestrator emits `rework` when an agent's output fails
  validation and gets sent back. The graph executor doesn't have
  retry/rework semantics yet — when validation fails it just errors
  out.
- Skip for v1. If it matters, model it as a second `node_started`
  with a `attempt: 2` field, and let the UI animate the rework state
  when `attempt > 1`.

### Phase 6 — Mode toggle inside the playground

- Once `presentation.html` works for all presets, add a button in
  `playground.html`'s top bar: **`PRESENT ▶`**. Clicks navigate to
  `/present?preset=<current-preset-id>` carrying the current graph
  through the URL or sessionStorage.
- Symmetric button on `presentation.html`: **`◀ EDIT`** drops back
  into the playground with the same preset loaded.
- Bonus: support presenting an *unsaved* graph the user has built
  themselves in the editor. The graph travels as a JSON blob in
  sessionStorage rather than as a preset id.

### Phase 7 — Bespoke sprites for the other four presets

- Pure art work. Each agent in each preset gets a 8×12-ish pixel
  figure with a role label. Drop new entries into
  `static/js/sprites.js` and reference by `presentation.sprite` in
  the preset JSON.
- Suggested order: `research_assistant` (smallest, one agent —
  quickest win), `news_brief`, `trip_planner`, then the two-tier
  fan-outs.

---

## Mode switching — URL vs in-app toggle

Pick the URL approach (`/playground` and `/present`) rather than an
in-app toggle that hides/shows DOM. Reasons:

- Bookmarkable. "Show me the presentation for the pitch deck preset"
  becomes a URL you can paste in Slack.
- Cleaner separation. The two pages have very different chrome —
  playground has a tools panel and a log; presentation is full-bleed.
  Toggling them in one DOM is fiddly.
- The current playground state (selected node, sidebar open, zoom)
  doesn't need to survive a mode change.

Keep the in-app button as the *primary* affordance — most users won't
type URLs — but the underlying mechanism is a route.

---

## What gets dropped or significantly thinned

If we go with option B, these files on `main` either disappear or get
thinned to nothing:

- `src/orchestrator.py` — replaced by `src/graph/executor.py` plus
  pitch-deck-specific features migrated as graph features. **Delete
  after Phase 4** once commentary lives in the graph layer.
- `src/demo_runner.py` and `src/demo_data.py` — only used by the
  hand-coded pipeline path. Delete with `orchestrator.py`.
- `src/main.py` — was the CLI entry point for the pipeline. Decide
  whether the playground needs a CLI; if not, drop.

`src/pixel_art*.py`, `src/scene_renderer.py`, `src/pptx_exporter.py`,
`src/schemas.py` — keep. These serve the pitch-deck output rendering
and are already used in graph mode.

`src/prompts/*.py` — keep for now. The hand-coded prompts on main are
richer than the prompts inlined in the preset JSONs. Eventually preset
JSONs should reference these by id rather than duplicating, but
that's not part of this plan.

---

## Risks and unknowns

1. **The pitch-deck orchestrator's runtime behaviour is subtler than
   it looks.** It does retry logic, validation, and specific
   inter-agent message shapes. The graph executor is generic and may
   not reproduce identical output. Run pitch_deck before & after Phase
   2 and diff the generated decks; expect divergence; decide if it's
   acceptable.
2. **Character art for non-pitch-deck presets is design work.** Don't
   estimate Phase 7 as engineering work — it's a few hours of pixel
   pushing per preset. Could be deferred indefinitely with the generic
   placeholder.
3. **The result tabs on presentation.html (Deck / Evidence / JSON /
   Learn) are pitch-deck-specific.** Either generalise (the tabs vary
   by output subtype) or scope them to pitch-deck and show a single
   "Output" tab for other presets. Recommend: subtype-driven tab set,
   with `text` subtype getting one plain Output tab.
4. **Edges fire mid-run on the playground.** Presentation may want
   the same — i.e. when `edge_fired` arrives, the receiving character
   gets a hand-off animation. This is great UX but means
   `presentation.html` needs to handle `edge_fired` too, which the
   old `index.html` didn't.

---

## Suggested first session for the new window

Don't try to do all of this in one go. A reasonable first session is
**Phase 1 only**:

1. Create branch `feat/presentation-mode` off
   `adapt/playground-with-main-fixes`.
2. Pull `static/index.html` from `origin/main` into
   `static/presentation.html` on the new branch using
   `git show origin/main:static/index.html >
   static/presentation.html`.
3. Lift the `CHARACTERS` constant out into `static/js/sprites.js`.
   Import it. No behaviour change.
4. Wire up two routes in `app.py`: `/playground` (existing
   playground) and `/present` (new presentation page, broken).
5. Ship. PR against `adapt/playground-with-main-fixes`.

That gives the next session a clean starting point for Phase 2
without committing to the full refactor.

---

## Estimated effort

- Phase 1: half a day. File move, route wiring, asset extraction.
- Phase 2: one day. Event bridging, generic sprite fallback, smoke
  test all six presets in presentation mode.
- Phase 3: half a day. PPTX path reattachment, tab generalisation.
- Phase 4: one day if porting commentary. Skip if you want.
- Phase 5: skip unless you discover you need it.
- Phase 6: half a day. Buttons + URL plumbing + sessionStorage.
- Phase 7: 2–4 hours per preset of art work.

Total floor (Phases 1–3, 6): roughly 2.5 days. With commentary and
bespoke art: roughly a week.
