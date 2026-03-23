# The Agentic Production Company

> A multi-agent pipeline that turns a one-line TV show idea into a structured pitch deck.

## Status

Phase 1 (Engine) — built, pending live testing with API keys.

## What It Does

You give it a one-line show idea (e.g. *"A 3x60 documentary about the last lighthouse keepers in Britain"*) and five AI agents collaborate to produce a broadcast-ready pitch deck:

1. **Series Producer** — parses the brief into a structured creative direction
2. **Producer** — breaks the brief into specialist assignments
3. **Researcher** — searches the web (via Tavily) for real facts, people, and competing shows
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

## Development

See `CLAUDE.md` for development conventions and workflow.

### Running Tests

```bash
pytest -v          # all tests
pytest -v -k test_integration  # integration tests only
```

## Licence

MIT
