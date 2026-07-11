---
title: Agentic Playground
emoji: 🎬
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
---

# Agent Theatre (+ Agentic Playground)

> A teaching tool for how agentic AI actually works. The star mode is the **Theatre**: watch a *real* Claude Code run — replayed from a transcript or live from your terminal — as an animated, narrated show where pixel-art agents hire each other, use tools, fail, adapt, and finish the job. Nobody draws the org chart; the AI does.

## What it does

**✦ Theatre (`/theatre`)** — the main event. Feed it a real agentic run and it becomes a stage play:

- **Replay Claude's previous runs.** The server scans `~/.claude/projects` for Claude Code session transcripts; pick one and watch it back. You can also drag-and-drop any session `.jsonl`, or press **PLAY THE DEMO** for a bundled sample run (zero API calls).
- **Go live from your terminal.** Enable the theatre hooks (one copy-paste, see below), run Claude Code as you normally would, and the run appears on stage in real time.
- **The cast assembles itself.** The run starts with one character — Claude, the orchestrator. When it delegates (a `Task` call), a new pixel person walks on stage, works with its own tools and its own context, then reports back and retires. The delegation map (smooth glowing edges, not pixel steps) draws itself as the run unfolds — that emergent structure *is* the lesson.
- **Narrated.** A caption bar explains each teaching beat in plain English: why the agent reads before it writes, what delegation buys, why a failed command is information, why only the subagent's summary survives.
- **Measured.** Per-agent token counters and context bars, run clock, tool-call and agent counts, a scrubbable timeline with play/pause and 0.5×–4× speed.

**▣ Sandbox (`/playground`)** — the original node-based canvas, reframed: now *you* try being the orchestrator. Compose agents, wire delegation and skills, run the graph live. (Presets: Pitch Deck Pipeline, Research Assistant, Creative Director → Artist, and more.)

**▶ Present (`/present`)** — cinematic view of the pitch-deck pipeline with hand-drawn characters.

## How it works

Everything hangs off one idea: an agentic run is just a stream of events. Three layers:

- **Trace adapters** (`src/trace/`) — normalize real runs into one event vocabulary (`user_message`, `thinking`, `say`, `tool_start/end`, `spawn`, `return`, `todo`, `done`). `claude_adapter.py` parses Claude Code session transcripts (including sidechains — subagent conversations — and token usage, deduped per API request). `live.py` normalizes Claude Code *hook* payloads for live mode and fans them out to WebSocket subscribers.
- **Theatre frontend** (`static/theatre.html` + `static/js/theatre.js`) — a pacing engine turns the event stream into watchable beats (real runs are bursty: quiet thinking, then six tool calls at once). Scrubbing rebuilds world state deterministically from event 0. Sprites are pixel-crunchy (`theatre-sprites.js` generates a tinted character per agent from ASCII templates, deterministic per agent); everything around them — edges, glows, panels, type — is smooth and antialiased.
- **Graph runtime** (`src/graph/`, `src/agent.py`) — the sandbox's executor: each agent node is a ReAct loop whose tools come from its edges; a delegate edge becomes a `delegate_to_x` tool. Unchanged from v3, and still the no-API-key event source for the Present view's demo.

## Installation

```bash
git clone <repo-url>
cd first-agentic-ai-production-company
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The Theatre needs **no API keys** — it replays transcripts. Keys are only needed for the sandbox/present modes that execute real graphs:

```bash
cp .env.example .env
# NEBIUS_API_KEY (LLM provider), TAVILY_API_KEY or LINKUP_API_KEY (web search),
# FAL_KEY (image generation preset only)
```

**macOS shortcut:** double-click `start.command`.

## Usage

```bash
python app.py
# Open http://localhost:8000  →  choose THEATRE
```

### Replaying a previous Claude run

Open `/theatre`. Anything under `~/.claude/projects` is listed automatically (override the location with the `CLAUDE_PROJECTS_DIR` env var). Click a run to replay it. Space = play/pause, ←/→ = step, drag the timeline to scrub — scrubbing is free, nothing re-executes.

### Watching a live run from your terminal

1. Merge the `hooks` block from `scripts/theatre-hooks.settings.json` into your `.claude/settings.json` (project or `~/.claude/settings.json` global). Each hook is a fire-and-forget `curl` to `http://localhost:8000/ingest` — if the theatre isn't running, Claude Code is unaffected.
2. Start the theatre server and open `/theatre`.
3. Run `claude` in your terminal and give it a task.
4. Click **CHECK FOR LIVE SESSIONS** → your session appears → watch.

*Live-mode caveat:* hook payloads carry no agent identity, so while a subagent is in flight its parent's parallel tool calls can be mis-badged. Replay-from-transcript is exact.

### The demo

**PLAY THE DEMO** replays a bundled sample transcript (`static/demo/demo_session.jsonl`, regenerable via `python scripts/make_demo_transcript.py`) telling the original production-company story: a one-line commissioning brief becomes a broadcastable pitch deck. Claude sets the editorial vision, hires a **Researcher**, **Director** and **Production Manager** in parallel (drawn with the presentation view's hand-made character sprites), then a **Producer** to assemble and fact-check the deck. It's the reliable classroom mode — no keys, no network, same every time.

## Configuration

`config.yaml` governs the sandbox graph runtime (model tiers, limits, pricing meter, rate limits) — see comments in the file. The Theatre has one knob: `CLAUDE_PROJECTS_DIR` for where to find transcripts.

## Tests

```bash
pytest -q
```

Covers the trace adapter (sidechain attribution, token dedupe, tool humanization), live hook normalization and Task attribution, the Theatre API routes (session listing, upload, ingest → WebSocket broadcast) — plus the whole v3 suite for the graph runtime, executor, presets, WebSocket protocol, PPTX exporter, and rate limiting.

## Deployment (Hugging Face Spaces)

Works as before (Docker Space + secrets for the sandbox modes). Note the Theatre's "previous runs" panel lists transcripts on the *server*, so on a hosted Space use drag-and-drop upload or the demo instead.

## Pixel-art animator skill

`.claude/skills/pixel-art-animator/` is a reusable Claude Code skill for creating **animated pixel characters** — from a text description or a supplied image — at any grid size and aspect ratio. Characters are authored as editable ASCII-grid JSON specs; the bundled `render.py` produces labelled contact sheets, animated GIFs, and `--export-groups` output that drops straight into this repo's `theatre-sprites.js` renderer. `references/` holds the distilled craft (grids/palettes/cluster hygiene; walk/jump/idle/laugh cycle recipes and timing), and `examples/courier.json` is a complete worked character (16×22, four animations). The skill's core rule: never trust an unrendered grid — render, look, critique against the checklists, iterate. Copy the directory to `~/.claude/skills/` to use it in other projects.

## Development notes

- v4 pivot: the app originally taught agentic AI by making *you* build the pipeline. Real agentic work is the AI spinning off and delegating agents itself — so the Theatre watches real runs, and the node builder was demoted to a sandbox. One event vocabulary powers both.
- The frontend is intentionally framework-free. Vanilla JS, Canvas2D. Pixel characters, smooth stage.

## Licence

MIT
