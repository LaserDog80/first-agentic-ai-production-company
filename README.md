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

You compose AI agents on a canvas. Each agent is a node with its own system prompt and model tier. You connect agents to each other to set up delegation (who can ask whom to do work), and you connect skill nodes (web search, lookup tools, static text sources, image generation) to grant agents abilities. Then you type a brief into the input, click **RUN**, and watch the graph execute live — nodes light up gold while running, gold sparks travel along edges as one agent delegates to another. A meter in the log bar tracks tokens and estimated cost as the run progresses, **■ STOP** cancels a run mid-flight, and **↻ REPLAY** re-plays the last run's animation without spending a token.

Presets that ship with the app:

- **Pitch Deck Pipeline** — five agents (Series Producer → Producer → Researcher / Director / Production Manager) collaborating to turn a one-line TV idea into a broadcast-ready pitch deck, exported as PPTX. Originally the proof-of-concept for this engine.
- **Research Assistant** — a single agent with web search. The simplest possible playground graph; useful as a starting template.
- **Creative Director → Artist** — a Creative Director delegates a brief to a Visual Artist, who generates an image via fal.ai (`fal-ai/flux/schnell`) and replies with the URL and a description. The CD reviews and either approves or sends feedback for another attempt. The final image renders in the OUTPUT tab with earlier attempts kept as history. Requires `FAL_KEY` in `.env`.
- **News Brief Builder**, **Short Film Budget Quote**, **Quick Trip Planner**, **Two-Sided Take** — smaller multi-agent workflows showing different graph shapes.

You can save your own graphs to localStorage, swap presets in and out, and build new agents from the library panel.

## How it works

Three layers:

- **Graph runtime** (`src/graph/`) — a graph is a JSON document of `nodes` and `edges`. The `GraphExecutor` walks the graph by recursion: each agent node becomes an `AgentRuntime` (a generic ReAct loop) whose tool list is built dynamically from its incoming edges. A `delegate` edge from A → B becomes a `delegate_to_b` tool on agent A; calling it runs B and returns its output. A `skill` edge from a web-search node to an agent becomes the `web_search` tool on that agent. The graph result is the output of whichever agent is wired to the OUTPUT node.
- **Agent runtime** (`src/agent.py`) — generic ReAct loop. Calls the LLM, executes tool calls (in parallel when the model requests several at once — a producer fanning out to three specialists really does run them concurrently), feeds results back, loops until done. Oversized tool results are truncated before re-entering the context; malformed tool calls from the model are reported back as recoverable errors instead of crashing the run.
- **Provider client** (`src/provider.py`) — config-driven OpenAI-compatible client. Three model tiers (`strong`/`research`/`utility`) are mapped to concrete model IDs in `config.yaml`.

Because graphs run server-side with the server's API keys, `config.yaml` enforces guardrails: per-call timeouts, a cap on iterations per agent, limits on graph size, and a global rate limit. Runs can be cancelled from the UI (or by disconnecting — an abandoned run stops burning tokens).

The frontend is a custom Canvas2D node editor in `static/js/editor.js` (no external library). It renders nodes as bordered rectangles with stepped 90° edges, animates running nodes with a pulsing gold border, and listens to a WebSocket for `node_started` / `edge_fired` / `node_finished` events emitted by the executor.

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

**macOS shortcut:** double-click `start.command`. It creates the venv, installs dependencies, starts the server, and opens the app in your browser. On first run it copies `.env.example` to `.env` and opens it so you can paste in your keys.

## Usage

```bash
python app.py
# Open http://localhost:8000
```

The root URL is a mode chooser:

- **`/playground`** — node-based canvas editor (the default working surface). Loads the **Pitch Deck Pipeline** preset by default. Type a brief into the top input and click **RUN**.
- **`/present`** — cinematic view of the pitch-deck pipeline. Pixel-art characters animate as each agent works; runs go through the same graph executor as the playground. The **DEMO** button plays a scripted run with zero API calls.

Both modes have a persistent **mode switch** affordance — a "▶ PRESENT" button on `/playground` and a "▣ PLAYGROUND" button on `/present`, plus a small "⌂" link back to the chooser.

Building your own graph:

1. Drop an **INPUT** and an **OUTPUT** node from the left library panel.
2. Add an **AGENT**. The wizard prompts for a name and system prompt.
3. Drag from the agent's bottom slot to another agent's top slot to set up delegation. Drag from a skill node to an agent to grant it that skill. Connect input → root agent and the deck-producing agent → output to complete the graph. **The OUTPUT edge decides which agent's response is the run result.**
4. Type a brief, click **RUN**. Click **■ STOP** to cancel, **↻ REPLAY** to watch it again for free.

Controls: click a library item to add a node, drag nodes to position, drag bottom-slot to top-slot to connect, double-click an edge to delete it, **DEL** to delete the selected node, scroll to zoom, shift+drag to pan, **F** to fit to view.

The pitch deck preset has an output node with `subtype: "pitch_deck"` — when its run completes, the server tries to parse the output as a pitch deck JSON and exposes a **↓ PPTX** download in the bottom log bar.

## Configuration

Everything tunable lives in `config.yaml`:

- `providers` — model IDs per tier and the API base URL.
- `pipeline` — per-LLM-call timeout and completion-token budget.
- `limits` — graph guardrails: max nodes, max agents, iteration cap per node, tool-result truncation length.
- `pricing` — approximate per-tier USD per 1M tokens, used only for the cost meter. Edit to match your provider's price list, or remove the block to hide the meter.
- `rate_limiting` — global runs-per-hour/day caps.
- `tools` — search provider selection and per-provider search depth.

## Tests

```bash
pytest -q
```

The suite covers the graph schema and validator (including the size/iteration guardrails), the executor with stubbed LLM clients (output-edge selection, cancellation, token/cost accounting, timeout wiring), preset integrity, the FastAPI/WebSocket protocol end-to-end (including a full stubbed run and the stop message), the agent runtime (parallel tool calls, malformed-argument recovery, result truncation), the tool registry (docstring → schema parameter descriptions), the PPTX exporter, and rate limiting.

## Deployment (Hugging Face Spaces)

1. Create a new Docker Space.
2. Add secrets `NEBIUS_API_KEY` and `TAVILY_API_KEY` (or `LINKUP_API_KEY`), plus `FAL_KEY` if you want image generation.
3. `git push` to the Space remote.

Run artefacts (PPTX files, generated images) are pruned automatically — only the most recent 40 runs are kept on disk.

## Development notes

- The original linear orchestrator is gone. Its logic lives on entirely as `src/graph/presets/pitch_deck.json` plus the generic `GraphExecutor` — and as of v3 the presentation view runs through that same executor, so there is exactly one runtime.
- The frontend is intentionally framework-free. Vanilla JS, single canvas. If you find yourself reaching for React or a graph library, ask whether the pixel aesthetic survives.

## Licence

MIT
