---
title: Agentic Playground
emoji: 🎬
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
---

# Agentic Playground

> A node-based canvas where you build a team of AI agents, draw delegation lines between them, attach skills, and run the whole graph live. Pixel-art aesthetic. Like ComfyUI, but for agents.

## What it does

You compose AI agents on a canvas. Each agent is a node with its own system prompt and model tier. You connect agents to each other to set up delegation (who can ask whom to do work), and you connect skill nodes (web search, lookup tools, static text sources) to grant agents abilities. Then you type a brief into the input, click **RUN**, and watch the graph execute live — nodes light up gold while running, gold sparks travel along edges as one agent delegates to another.

Presets that ship with the app:

- **Pitch Deck Pipeline** — five agents (Series Producer → Producer → Researcher / Director / Production Manager) collaborating to turn a one-line TV idea into a broadcast-ready pitch deck. Originally the proof-of-concept for this engine; now just one preset among many.
- **Research Assistant** — a single agent with web search. The simplest possible playground graph; useful as a starting template.
- **Creative Director → Artist** — a Creative Director delegates a brief to a Visual Artist, who generates an image via fal.ai (`fal-ai/flux/schnell`) and replies with the URL and a description. The CD reviews the description (text-only in v1 — no vision model yet) and either approves or sends feedback for another attempt, up to **5 attempts**. The final image renders in the OUTPUT tab; earlier attempts are kept below as history. Requires `FAL_KEY` in `.env`.

You can save your own graphs to localStorage, swap presets in and out, and build new agents from the library panel.

## How it works

Three layers:

- **Graph runtime** (`src/graph/`) — a graph is a JSON document of `nodes` and `edges`. The `GraphExecutor` walks the graph by recursion: each agent node becomes an `AgentRuntime` (the existing ReAct loop) whose tool list is built dynamically from its incoming edges. A `delegate` edge from A → B becomes a `delegate_to_b` tool on agent A; calling it runs B and returns its output. A `skill` edge from a web-search node to an agent becomes the `web_search` tool on that agent.
- **Agent runtime** (`src/agent.py`) — generic ReAct loop. Unchanged from the original engine. Calls the LLM, executes tool calls, feeds results back, loops until done.
- **Provider client** (`src/provider.py`) — config-driven OpenAI-compatible client. Three model tiers (`strong`/`research`/`utility`) are mapped to concrete model IDs in `config.yaml`.

The frontend is a custom Canvas2D node editor in `static/js/editor.js` (~600 lines, no external library). It renders nodes as bordered rectangles with stepped 90° edges, animates running nodes with a pulsing gold border, and listens to a WebSocket for `node_started` / `edge_fired` / `node_finished` events emitted by the executor.

## Installation

```bash
git clone <repo-url>
cd first-agentic-ai-production-company
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with NEBIUS_API_KEY (LLM provider)
# and TAVILY_API_KEY or LINKUP_API_KEY (web search)
# and FAL_KEY (image generation — only needed for the Creative Director → Artist preset)
```

## Usage

```bash
python app.py
# Open http://localhost:8000
```

The root URL is a mode chooser:

- **`/playground`** — node-based canvas editor (the default working surface). Loads the **Pitch Deck Pipeline** preset by default. Type a brief into the top input and click **RUN**.
- **`/present`** — cinematic view of the pipeline running. Pixel-art characters animate as each agent works. Currently wired to the legacy pitch-deck event vocabulary; full unification with the graph executor is tracked in `docs/PRESENTATION_MODE_PLAN.md` (Phase 2+).

Both modes have a persistent **mode switch** affordance — a "▶ PRESENT" button on `/playground` and a "▣ PLAYGROUND" button on `/present`, plus a small "⌂" link back to the chooser. Iterate on a graph in the playground, then jump to presentation mode for a demo without bouncing through the chooser.

Building your own graph:

1. Drop an **INPUT** and an **OUTPUT** node from the left library panel.
2. Add an **AGENT**. The wizard prompts for a name and system prompt.
3. Drag from the agent's bottom slot to another agent's top slot to set up delegation. Drag from a skill node to an agent to grant it that skill. Connect input → root agent and root agent → output to complete the graph.
4. Type a brief, click **RUN**.

Controls: click a library item to add a node, drag nodes to position, drag bottom-slot to top-slot to connect, double-click an edge to delete it, **DEL** to delete the selected node, scroll to zoom, shift+drag to pan, **F** to fit to view.

The pitch deck preset has an output node with `subtype: "pitch_deck"` — when its run completes, the server tries to parse the output as a pitch deck JSON and exposes a **↓ PPTX** download in the bottom log bar.

## Tests

```bash
pytest -q
```

83 tests cover the graph schema and validator, the executor with stubbed LLM clients, preset integrity (including the new `cd_artist` preset with a mocked fal.ai client), the FastAPI/WebSocket protocol (including the chooser, playground, and present routes plus the sprites module), the agent runtime, the tool registry, the PPTX exporter, and rate limiting.

## Deployment (Hugging Face Spaces)

1. Create a new Docker Space.
2. Add secrets `NEBIUS_API_KEY` and `TAVILY_API_KEY` (or `LINKUP_API_KEY`).
3. `git push` to the Space remote.

## Development notes

- The original linear orchestrator is gone. Its logic lives on entirely as `src/graph/presets/pitch_deck.json` plus the generic `GraphExecutor`. If you want to bring back the rework / cascade behaviour, encode it as a graph rather than as procedural code.
- The frontend is intentionally framework-free. Vanilla JS, single canvas, ~1100 lines including the page chrome. If you find yourself reaching for React or a graph library, ask whether the pixel aesthetic survives.

## Licence

MIT
