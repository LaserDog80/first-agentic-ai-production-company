---
title: Agent Orchestrator
emoji: 🔀
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
---

# Agent Orchestrator

> A multi-agent orchestration framework that runs configurable AI pipelines — from TV pitch decks to research reports to startup pitches.

## What It Does

Define a workflow as a sequence of AI agent steps. Each agent has a role, tools, and a model tier. The framework handles orchestration, tool calling, validation, rework loops, and real-time event streaming.

**Bundled pipelines:**

| Pipeline | Input | Agents | Output |
|----------|-------|--------|--------|
| **TV Production** | One-line show idea | Series Producer, Producer, Researcher, Director, Production Manager | Pitch deck (JSON + PPTX) |
| **Research Report** | Research topic | Research Director, Investigator, Analyst, Writer, Reviewer | Structured report with sourced findings |
| **Startup Pitch** | Business idea | Strategist, Market Researcher, Business Architect, Financial Modeller, Pitch Writer, Investor Reviewer | Investor-ready pitch |

## How It Works

```
                        ┌─────────────────┐
                        │   User Input     │
                        └────────┬────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Pipeline Framework     │
                    │  (BasePipeline class)    │
                    └────────────┬────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                     │
      ┌─────▼─────┐      ┌──────▼──────┐      ┌──────▼──────┐
      │  Agent 1   │      │  Agent 2    │      │  Agent N    │
      │ (ReAct)    │      │ (ReAct)     │      │ (ReAct)     │
      │ + tools    │      │ + tools     │      │ + tools     │
      └─────┬──────┘      └──────┬──────┘      └──────┬──────┘
            │                    │                     │
            └────────────────────┼────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Review / Rework Loop   │
                    │  (cascade dependencies)  │
                    └────────────┬────────────┘
                                 │
                        ┌────────▼────────┐
                        │  Validated JSON  │
                        │  + Evidence Log  │
                        └─────────────────┘
```

**Core architecture:**
- **Agent Runtime** — generic ReAct loop: model calls tools, gets results, loops until done
- **Pipeline Framework** — `BasePipeline` class with agent execution, validation, logging, and rework support
- **Pipeline Plugins** — each pipeline is a YAML definition + Python class. Add your own.
- **Tool Registry** — tools are registered by name and referenced in pipeline configs
- **Config-driven** — providers, models, rate limits all in `config.yaml`

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
# Edit .env: NEBIUS_API_KEY, TAVILY_API_KEY

# List available pipelines
python -m src.main --list

# Run a pipeline (interactive selection)
python -m src.main

# Run a specific pipeline
python -m src.main -p tv_production "A 3x60 documentary about lighthouse keepers"
python -m src.main -p research_report "Impact of microplastics on freshwater ecosystems"
python -m src.main -p startup_pitch "AI platform matching translators with legal document work"

# Save output to files
python -m src.main -p research_report "Your topic" --output output/run1
```

## Usage

### Web UI

```bash
python app.py
# Open http://localhost:8000
```

The web UI features:
- **Pipeline selector** — choose which pipeline to run
- **Dynamic step display** — see each agent activate in real time
- **Event log** — timestamped tool calls, rework events, and commentary
- **Result viewer** — copy JSON output or download PPTX (TV Production)

### CLI

```bash
python -m src.main --list                          # List pipelines
python -m src.main -p tv_production "Show idea"    # Run specific pipeline
python -m src.main --demo                          # Demo mode (no API calls)
```

### Demo Mode

Demo mode uses fixture data — no API calls needed.

```bash
python -m src.main --demo                      # CLI
ENABLE_DEMO=true python app.py                 # Web UI
```

## Adding a Pipeline

1. Create a directory under `src/pipelines/your_pipeline/`
2. Add `pipeline.yaml` with metadata, agents, and steps
3. Add `pipeline.py` with a class inheriting `BasePipeline`
4. Add `prompts.py` and `schemas.py` as needed
5. The framework discovers it automatically

```yaml
# src/pipelines/your_pipeline/pipeline.yaml
id: your_pipeline
name: "Your Pipeline"
description: "Does something useful"
category: "Your Category"

input:
  label: "Your Input"
  placeholder: "Enter something..."

agents:
  planner:
    role: "Planner"
    model_tier: strong
  worker:
    role: "Worker"
    model_tier: research
    tools: [web_search]

steps:
  - id: plan
    agent: planner
    label: "Planning"
  - id: execute
    agent: worker
    label: "Execution"
```

```python
# src/pipelines/your_pipeline/pipeline.py
from src.core.pipeline import BasePipeline, PipelineResult

class YourPipeline(BasePipeline):
    def execute(self, input_text: str) -> PipelineResult:
        _, plan = self.run_agent_step(
            name="planner", phase="planning",
            system_prompt="You are a planner...",
            user_message=input_text,
            step_num=1, total_steps=2,
            start_message="Planning...",
            done_message="Plan ready.",
        )
        # ... more steps ...
        return PipelineResult(output=plan)
```

## File Structure

```
src/
├── core/                    # Framework
│   ├── agent.py             # ReAct agent runtime
│   ├── pipeline.py          # BasePipeline + discovery
│   ├── registry.py          # Tool registry
│   └── schemas.py           # Logging schemas
├── pipelines/               # Pipeline plugins
│   ├── tv_production/       # TV pitch deck pipeline
│   ├── research_report/     # Research report pipeline
│   └── startup_pitch/       # Startup pitch pipeline
├── tools/                   # Shared tools
│   ├── search.py            # Web search (Tavily/Linkup)
│   └── __init__.py          # Tool decorator + auto-schema
├── provider.py              # Config-driven LLM client
├── main.py                  # CLI entry point
└── commentary.py            # Live commentary engine
```

## Development

See `CLAUDE.md` for development conventions and workflow.

```bash
pytest -v                              # All tests
pytest -v tests/test_core.py           # Core framework tests
pytest -v tests/test_integration.py    # Integration tests
```

## Deployment

### Hugging Face Spaces

1. Create a Space with SDK type **Docker**
2. Add secrets: `NEBIUS_API_KEY`, `TAVILY_API_KEY`
3. Push: `git push hf main`

## Licence

MIT
