---
title: Agentic Production Company
emoji: 🎬
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
---

# The Agentic Production Company

> A multi-agent pipeline that turns a one-line TV show idea into a structured pitch deck.

## Status

Phase 1 (Engine) — built, pending live testing with API keys.
Phase 2 (Frontend) — pixel art web UI with real-time WebSocket updates.

## What It Does

You give it a one-line show idea (e.g. *"A 3x60 documentary about the last lighthouse keepers in Britain"*) and five AI agents collaborate to produce a broadcast-ready pitch deck:

1. **Series Producer** — parses the brief into a structured creative direction
2. **Producer** — breaks the brief into specialist assignments
3. **Researcher** — searches the web (LinkUp primary, Tavily fallback) for real facts, people, and competing shows
4. **Director** — shapes a creative treatment with narrative arc and key sequences
5. **Production Manager** — assesses feasibility, budget, crew, and logistics

The Series Producer reviews the final package and can send work back for revision — making this genuinely agentic (real tool use and feedback loops) rather than a simple prompt chain.

## How It Works

Three-layer architecture:
- **Provider Client** — config-driven OpenAI-compatible client (currently Nebius Token Factory, swappable via config)
- **Agent Runtime** — generic ReAct loop: model calls tools, gets results, loops until done
- **Orchestrator** — sequences agents, handles rework loops (max 2), logs every step

Output is a structured JSON pitch deck with an evidence pack tracing every decision.

## Quick Start

```bash
# Clone and set up
git clone <repo-url>
cd first-agentic-ai-production-company
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your NEBIUS_API_KEY and TAVILY_API_KEY

# Run the pipeline
python -m src.main "A 3x60 documentary about the last lighthouse keepers in Britain"

# Save output to files
python -m src.main "Your show idea here" --output output/run1
```

## Usage

### Web UI (recommended)

```bash
# Start the web server
python app.py
# Open http://localhost:8000 in your browser
```

The web UI features:
- **Pixel art characters** standing in a row — one for each agent role
- **Speech bubbles** showing what each agent is currently doing or generating
- **Live status bar** with progress tracking and step counter
- **Event log** with timestamped updates as the pipeline runs
- **Result overlay** displaying the final pitch deck

### CLI

```bash
# Basic usage
python -m src.main "Your one-line show idea"

# With custom config and output directory
python -m src.main "Your idea" --config config.yaml --output output/

# Run tests
pytest -v
```

Output includes:
- `pitch_deck.json` — the full pitch deck
- `evidence.json` — evidence pack tracing every agent's contribution
- `log.json` — detailed orchestration log with token usage and timing

### Demo Mode

Demo mode runs the pipeline with fixture data and no API calls — useful for testing the UI and pipeline flow without incurring costs.

**CLI** (always available):
```bash
python -m src.main --demo
```

**Web UI** (must be explicitly enabled):
```bash
ENABLE_DEMO=true python app.py
```

When `ENABLE_DEMO=true` is set, a "DEMO" button appears next to the input field. Demo mode is disabled by default.

## Deployment

### Hugging Face Spaces

This app can be deployed as a [Hugging Face Space](https://huggingface.co/spaces) using the Docker SDK.

1. **Create a new Space** on Hugging Face with SDK type **Docker**.

2. **Add secrets** in the Space settings:
   - `NEBIUS_API_KEY` — your Nebius API key
   - `LINKUP_API_KEY` — your LinkUp search API key (primary)
   - `TAVILY_API_KEY` — your Tavily search API key (fallback)
   - (Optional) `ENABLE_DEMO` — set to `true` to show the demo button

3. **Push the repo** to the Space:
   ```bash
   git remote add hf https://huggingface.co/spaces/YOUR_USER/YOUR_SPACE
   git push hf main
   ```

The Dockerfile is pre-configured for HF Spaces (port 7860, health check included). The app will be available at `https://YOUR_USER-YOUR_SPACE.hf.space`.

## Development

See `CLAUDE.md` for development conventions and workflow.

### Running Tests

```bash
pytest -v          # all tests
pytest -v -k test_integration  # integration tests only
```

## Licence

MIT
