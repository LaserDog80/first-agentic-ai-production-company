# Phase 1 Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working multi-agent pipeline that takes a one-line TV show brief and produces a structured pitch deck with evidence pack.

**Architecture:** Three-layer system — Provider Client (config-driven OpenAI-compatible), Agent Runtime (generic ReAct loop with tools), Orchestrator (sequential pipeline with rework loops). All I/O is Pydantic-validated JSON.

**Tech Stack:** Python 3.10+, openai SDK, tavily-python, pydantic, pyyaml, python-dotenv, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-agentic-pipeline-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `.gitignore` | Ignore .env, __pycache__, venv, .pytest_cache |
| `.env.example` | Template for required env vars |
| `config.yaml` | Provider URLs, model assignments, tool config |
| `requirements.txt` | All dependencies |
| `src/__init__.py` | Package marker |
| `src/schemas.py` | All Pydantic models (I/O contracts) |
| `src/provider.py` | Config-driven OpenAI client factory |
| `src/agent.py` | Generic agent runtime (ReAct loop) |
| `src/tools/__init__.py` | Tool registry + auto-schema generation |
| `src/tools/search.py` | Tavily web_search |
| `src/tools/rework.py` | request_rework, approve, flag_gap |
| `src/tools/research.py` | assess_confidence, reference_research |
| `src/tools/rates.py` | lookup_rates (static table) |
| `src/prompts/series_producer.py` | SP system prompt builder |
| `src/prompts/producer.py` | Producer system prompt builder |
| `src/prompts/researcher.py` | Researcher system prompt builder |
| `src/prompts/director.py` | Director system prompt builder |
| `src/prompts/production_manager.py` | PM system prompt builder |
| `src/orchestrator.py` | Pipeline sequencing, rework, logging |
| `src/main.py` | CLI entry point |
| `tests/test_schemas.py` | Schema validation tests |
| `tests/test_provider.py` | Provider client tests |
| `tests/test_agent.py` | Agent runtime tests |
| `tests/test_tools.py` | Tool function tests |
| `tests/__init__.py` | Package marker for tests |
| `tests/conftest.py` | Shared test fixtures (mock config, helpers) |
| `tests/test_orchestrator.py` | Pipeline integration tests |
| `src/prompts/evidence.py` | Evidence generator prompt builder |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `.gitignore`, `.env.example`, `config.yaml`, `requirements.txt`, `src/__init__.py`, `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Create .gitignore**

```
# Environment
.env
venv/
.venv/

# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/

# Testing
.pytest_cache/
htmlcov/
.coverage

# IDE
.vscode/
.idea/
*.swp

# Output
output/
```

- [ ] **Step 2: Create .env.example**

```
# Model API (OpenAI-compatible endpoint)
NEBIUS_API_KEY=

# Search tool
TAVILY_API_KEY=
```

- [ ] **Step 3: Create config.yaml**

```yaml
providers:
  primary:
    base_url: "https://api.tokenfactory.nebius.com/v1"
    api_key_env: "NEBIUS_API_KEY"
    models:
      strong: "Qwen3-235B-A22B-Instruct-2507"
      research: "DeepSeek-V3-0324"
      utility: "Qwen3-30B-A3B-Instruct-2507"

agents:
  series_producer:
    model_tier: "strong"
    max_iterations: 5
  producer:
    model_tier: "strong"
    max_iterations: 5
  researcher:
    model_tier: "research"
    max_iterations: 5
  director:
    model_tier: "strong"
    max_iterations: 5
  production_manager:
    model_tier: "strong"
    max_iterations: 5

pipeline:
  max_rework_cycles: 2  # TOTAL pipeline-wide cap, not per-agent
  agent_timeout_seconds: 60

tools:
  tavily:
    api_key_env: "TAVILY_API_KEY"
    search_depth: "advanced"
```

- [ ] **Step 4: Create requirements.txt**

```
openai>=1.0.0
tavily-python>=0.3.0
pydantic>=2.0.0
pyyaml>=6.0
python-dotenv>=1.0.0
pytest>=7.0.0
```

- [ ] **Step 5: Create src/__init__.py**

Empty file.

- [ ] **Step 6: Create tests/__init__.py**

Empty file.

- [ ] **Step 7: Create tests/conftest.py**

```python
# tests/conftest.py
"""Shared test fixtures."""
import pytest


@pytest.fixture
def mock_config():
    """Standard mock config dict for testing."""
    return {
        "providers": {"primary": {
            "base_url": "http://test", "api_key_env": "TEST_KEY",
            "models": {"strong": "m1", "research": "m2", "utility": "m3"},
        }},
        "agents": {
            "series_producer": {"model_tier": "strong", "max_iterations": 5},
            "producer": {"model_tier": "strong", "max_iterations": 5},
            "researcher": {"model_tier": "research", "max_iterations": 5},
            "director": {"model_tier": "strong", "max_iterations": 5},
            "production_manager": {"model_tier": "strong", "max_iterations": 5},
        },
        "pipeline": {"max_rework_cycles": 2, "agent_timeout_seconds": 60},
        "tools": {"tavily": {"api_key_env": "TAVILY_KEY", "search_depth": "advanced"}},
    }
```

- [ ] **Step 8: Commit**

```bash
git add .gitignore .env.example config.yaml requirements.txt src/__init__.py tests/__init__.py tests/conftest.py
git commit -m "feat: project scaffolding with config and dependencies"
```

---

### Task 2: Pydantic Schemas

**Files:**
- Create: `src/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schemas.py
import pytest
from src.schemas import (
    FormatSpec, ProducerBrief, ResearchBrief, DirectorBrief, PMBrief,
    CompetitorEntry, CharacterEntry, FactEntry, ArchiveEntry, LocationEntry,
    ResearchPack, NarrativeArc, SequenceEntry, ContributorEntry,
    CreativeTreatment, ShootingEstimate, BudgetBracket, CrewEntry,
    LogisticsEntry, FeasibilityAssessment, EpisodePackage,
    TitlePage, FeasibilitySummary, PitchDeck,
    ToolCallLog, LogEntry, EvidenceStep, EvidencePack,
)


def test_format_spec_valid():
    fs = FormatSpec(series_length="3x60", genre="factual", tone="warm and observational")
    assert fs.series_length == "3x60"


def test_producer_brief_valid():
    brief = ProducerBrief(
        working_title="The Last Lighthouse Keeper",
        format=FormatSpec(series_length="3x60", genre="factual", tone="warm"),
        target_broadcaster="BBC Two",
        creative_steer="An intimate portrait of solitude and duty.",
        sample_episode_focus="The daily routine and history of Lundy Island.",
        assumptions=["Access to Lundy Island is feasible"],
    )
    assert brief.working_title == "The Last Lighthouse Keeper"


def test_research_pack_valid():
    pack = ResearchPack(
        competitive_landscape=[
            CompetitorEntry(title="Lighthouse", broadcaster="BBC Four",
                            year="2019", relevance="Similar tone")
        ],
        characters=[
            CharacterEntry(name="John Smith", role="Keeper",
                           access_notes="Lives locally", story_angle="30 years of service")
        ],
        key_facts=[
            FactEntry(fact="Lundy has one lighthouse", source="Trinity House",
                      confidence="high")
        ],
        archive_sources=[
            ArchiveEntry(type="photo", description="Historical keeper photos",
                         access="public")
        ],
        locations=[
            LocationEntry(name="Lundy Island", rationale="Primary location",
                          logistics_note="Ferry access only")
        ],
        risks_and_sensitivities=["Weather dependent access"],
    )
    assert len(pack.competitive_landscape) == 1


def test_fact_entry_confidence_validation():
    with pytest.raises(Exception):
        FactEntry(fact="test", source="test", confidence="maybe")


def test_feasibility_rating_validation():
    with pytest.raises(Exception):
        FeasibilityAssessment(
            shooting_days=ShootingEstimate(estimate=10, breakdown="test"),
            budget_bracket=BudgetBracket(low=100000, high=200000,
                                         currency="GBP", notes=""),
            crew_requirements=[],
            logistics=[],
            feasibility_rating="purple",
            cost_saving_opportunities=[],
        )


def test_pitch_deck_valid():
    deck = PitchDeck(
        title_page=TitlePage(working_title="Test", genre="factual",
                             format="3x60", target_broadcaster="BBC"),
        logline="A show about testing.",
        format_and_tone=FormatSpec(series_length="3x60", genre="factual",
                                   tone="warm"),
        target_audience="Adults 25-54",
        competitive_landscape=[],
        key_characters=[],
        episode_breakdown=CreativeTreatment(
            episode_title="Pilot",
            narrative_arc=NarrativeArc(opening="", development="",
                                       climax="", resolution=""),
            key_sequences=[],
            overall_tone="warm",
            visual_approach="observational",
            contributor_usage=[],
            special_requirements=[],
        ),
        feasibility_summary=FeasibilitySummary(
            feasibility_rating="green",
            budget_bracket=BudgetBracket(low=100000, high=200000,
                                         currency="GBP", notes=""),
            shooting_days=10,
            key_risks=[],
        ),
        why_now="Testing is timely.",
        sp_review_notes="Approved.",
        unresolved_concerns=[],
    )
    assert deck.title_page.working_title == "Test"


def test_episode_package_valid():
    brief = ProducerBrief(
        working_title="Test", format=FormatSpec(series_length="1x60",
                                                 genre="factual", tone="warm"),
        target_broadcaster="BBC", creative_steer="Test",
        sample_episode_focus="Test", assumptions=[],
    )
    pack = ResearchPack(
        competitive_landscape=[], characters=[], key_facts=[],
        archive_sources=[], locations=[], risks_and_sensitivities=[],
    )
    treatment = CreativeTreatment(
        episode_title="Test",
        narrative_arc=NarrativeArc(opening="", development="",
                                    climax="", resolution=""),
        key_sequences=[], overall_tone="warm", visual_approach="obs",
        contributor_usage=[], special_requirements=[],
    )
    feasibility = FeasibilityAssessment(
        shooting_days=ShootingEstimate(estimate=5, breakdown="5 days"),
        budget_bracket=BudgetBracket(low=50000, high=100000,
                                     currency="GBP", notes=""),
        crew_requirements=[], logistics=[],
        feasibility_rating="green", cost_saving_opportunities=[],
    )
    ep = EpisodePackage(
        sp_brief=brief, research=pack, treatment=treatment,
        feasibility=feasibility,
        editorial_narrative="This works because...",
        gaps_and_conflicts=[],
    )
    assert ep.editorial_narrative == "This works because..."


def test_log_entry_valid():
    from datetime import datetime
    entry = LogEntry(
        agent_name="researcher", phase="researcher",
        timestamp=datetime.now(), input_summary="test input",
        output_summary="test output",
        token_usage={"prompt": 100, "completion": 200},
        duration_ms=1500, tool_calls=[],
        rework_requested=False, rework_target=None, rework_notes=None,
    )
    assert entry.agent_name == "researcher"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas.py -v`
Expected: FAIL — cannot import from src.schemas

- [ ] **Step 3: Implement all Pydantic models**

Create `src/schemas.py` with every model from the spec: FormatSpec, ProducerBrief, ResearchBrief, DirectorBrief, PMBrief, CompetitorEntry, CharacterEntry, FactEntry, ArchiveEntry, LocationEntry, ResearchPack, NarrativeArc, SequenceEntry, ContributorEntry, CreativeTreatment, ShootingEstimate, BudgetBracket, CrewEntry, LogisticsEntry, FeasibilityAssessment, EpisodePackage, TitlePage, FeasibilitySummary, PitchDeck, ToolCallLog, LogEntry, EvidenceStep, EvidencePack.

All classes use `from pydantic import BaseModel` and `from typing import Literal`. LogEntry uses `from datetime import datetime`.

The field definitions are specified exactly in the spec — implement them verbatim.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_schemas.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/schemas.py tests/test_schemas.py
git commit -m "feat: add all Pydantic I/O schemas with validation tests"
```

---

### Task 3: Provider Client

**Files:**
- Create: `src/provider.py`
- Test: `tests/test_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_provider.py
import os
import pytest
from unittest.mock import patch, MagicMock
from src.provider import load_config, create_client, get_model_name


def test_load_config():
    config = load_config("config.yaml")
    assert "providers" in config
    assert "primary" in config["providers"]
    assert "models" in config["providers"]["primary"]


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent.yaml")


def test_get_model_name():
    config = load_config("config.yaml")
    assert "Qwen3-235B" in get_model_name(config, "strong")
    assert "DeepSeek" in get_model_name(config, "research")
    assert "Qwen3-30B" in get_model_name(config, "utility")


def test_get_model_name_invalid_tier():
    config = load_config("config.yaml")
    with pytest.raises(KeyError):
        get_model_name(config, "nonexistent")


@patch.dict(os.environ, {"NEBIUS_API_KEY": "test-key-123"})
def test_create_client():
    config = load_config("config.yaml")
    client = create_client(config)
    assert client.api_key == "test-key-123"
    assert "tokenfactory.nebius.com" in str(client.base_url)


def test_create_client_missing_key():
    config = load_config("config.yaml")
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="API key"):
            create_client(config)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_provider.py -v`
Expected: FAIL — cannot import from src.provider

- [ ] **Step 3: Implement provider.py**

```python
# src/provider.py
"""Config-driven OpenAI-compatible client factory."""
import os
from pathlib import Path

import yaml
from openai import OpenAI


def load_config(config_path: str = "config.yaml") -> dict:
    """Load YAML config file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(path) as f:
        return yaml.safe_load(f)


def get_model_name(config: dict, tier: str) -> str:
    """Get model name for a given tier (strong/research/utility)."""
    models = config["providers"]["primary"]["models"]
    if tier not in models:
        raise KeyError(f"Unknown model tier: {tier}. Available: {list(models.keys())}")
    return models[tier]


def create_client(config: dict) -> OpenAI:
    """Create an OpenAI client from config."""
    provider = config["providers"]["primary"]
    api_key_env = provider["api_key_env"]
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(
            f"API key not found. Set the {api_key_env} environment variable."
        )
    return OpenAI(base_url=provider["base_url"], api_key=api_key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_provider.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/provider.py tests/test_provider.py
git commit -m "feat: add config-driven provider client"
```

---

### Task 4: Tool Infrastructure + Pipeline Tools

**Files:**
- Create: `src/tools/__init__.py`, `src/tools/search.py`, `src/tools/rework.py`, `src/tools/research.py`, `src/tools/rates.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tools.py
import json
import pytest
from unittest.mock import patch, MagicMock
from src.tools import tool, get_openai_tools_schema, execute_tool
from src.tools.search import web_search
from src.tools.rework import request_rework, approve, flag_gap
from src.tools.research import create_reference_research
from src.tools.rates import lookup_rates


# --- Tool registry ---

def test_tool_decorator_registers():
    """The @tool decorator should make a function discoverable."""
    @tool
    def sample_tool(query: str) -> dict:
        """A sample tool for testing."""
        return {"result": query}

    schema = get_openai_tools_schema([sample_tool])
    assert len(schema) == 1
    assert schema[0]["type"] == "function"
    assert schema[0]["function"]["name"] == "sample_tool"


def test_execute_tool():
    @tool
    def add(a: int, b: int) -> dict:
        """Add two numbers."""
        return {"sum": a + b}

    result = execute_tool("add", {"a": 2, "b": 3}, [add])
    assert result == {"sum": 5}


def test_execute_tool_unknown():
    with pytest.raises(KeyError):
        execute_tool("nonexistent", {}, [])


# --- request_rework ---

def test_request_rework():
    result = request_rework(agent="researcher", notes="Thin competitive landscape")
    assert result["status"] == "rework_requested"
    assert result["agent"] == "researcher"


# --- approve ---

def test_approve():
    result = approve()
    assert result["status"] == "approved"


# --- flag_gap ---

def test_flag_gap():
    result = flag_gap(description="No archive sources identified")
    assert result["status"] == "gap_flagged"
    assert "No archive" in result["description"]


# --- web_search (mocked) ---

@patch("src.tools.search.TavilyClient")
def test_web_search(mock_tavily_class):
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [{"title": "Test", "url": "http://test.com", "content": "Test content"}]
    }
    mock_tavily_class.return_value = mock_client

    result = web_search("lighthouse documentaries")
    assert "results" in result
    assert len(result["results"]) == 1


# --- reference_research (closure — model only sees `section` param) ---

def test_reference_research():
    mock_research = {
        "competitive_landscape": [{"title": "Test Show"}],
        "characters": [{"name": "Test Person"}],
    }
    # create_reference_research returns a tool function bound to this research pack
    ref_tool = create_reference_research(mock_research)
    result = ref_tool(section="competitive_landscape")
    assert result["section"] == "competitive_landscape"
    assert len(result["data"]) == 1


def test_reference_research_invalid_section():
    ref_tool = create_reference_research({})
    result = ref_tool(section="nonexistent")
    assert "error" in result


# --- lookup_rates ---

def test_lookup_rates():
    result = lookup_rates(role="camera operator", region="UK")
    assert "daily_rate" in result
    assert result["currency"] == "GBP"


def test_lookup_rates_unknown_role():
    result = lookup_rates(role="underwater basket weaver", region="UK")
    assert "daily_rate" in result  # returns a default/estimate
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py -v`
Expected: FAIL — cannot import

- [ ] **Step 3: Implement tool registry (`src/tools/__init__.py`)**

The `@tool` decorator marks functions as tools. `get_openai_tools_schema` inspects decorated functions and generates OpenAI-compatible tool schemas from their signatures and docstrings. `execute_tool` dispatches by name.

Use `inspect` module to extract parameter names/types from the function signature. Map Python types to JSON schema types (str→string, int→integer, dict→object, etc.). The function's docstring becomes the tool description.

- [ ] **Step 4: Implement `src/tools/rework.py`**

Three simple functions:
- `request_rework(agent: str, notes: str) -> dict` — returns `{"status": "rework_requested", "agent": agent, "notes": notes}`
- `approve() -> dict` — returns `{"status": "approved"}`
- `flag_gap(description: str) -> dict` — returns `{"status": "gap_flagged", "description": description}`

All decorated with `@tool`.

- [ ] **Step 5: Implement `src/tools/search.py`**

`web_search(query: str) -> dict` — uses `TavilyClient` (initialised from `TAVILY_API_KEY` env var). Calls `client.search(query, search_depth="advanced")`. Returns the results dict. Wraps in try/except — on failure, returns `{"results": [], "error": str(e)}`.

- [ ] **Step 6: Implement `src/tools/research.py`**

- `create_reference_research(research_pack: dict) -> Callable` — **factory function** that returns a `@tool`-decorated `reference_research(section: str) -> dict` closure. The closure captures `research_pack` so the model only sees and calls `reference_research(section)`. Looks up `section` key in the captured `research_pack`. Returns `{"section": section, "data": research_pack[section]}` or `{"error": f"Section '{section}' not found"}`.
- Note: `assess_confidence` is removed as a tool. Confidence assessment is handled through the Researcher's system prompt instruction to rate confidence on each fact entry. This avoids wasting agent iterations on a no-op tool call.

- [ ] **Step 7: Implement `src/tools/rates.py`**

`lookup_rates(role: str, region: str) -> dict` — static lookup table with common TV production roles and rough daily rates for UK, US, EU regions. Returns `{"role": role, "region": region, "daily_rate": rate, "currency": currency, "note": "Estimate only"}`. For unknown roles, returns a generic estimate.

Static table:

```python
RATES = {
    "UK": {
        "camera operator": 450, "sound recordist": 400, "director": 600,
        "producer": 550, "researcher": 300, "editor": 400,
        "production manager": 450, "runner": 150, "presenter": 800,
        "_default": 350, "_currency": "GBP",
    },
    "US": {
        "camera operator": 600, "sound recordist": 500, "director": 800,
        "producer": 700, "researcher": 400, "editor": 550,
        "production manager": 600, "runner": 200, "presenter": 1000,
        "_default": 450, "_currency": "USD",
    },
    "_default_region": "UK",
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_tools.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/tools/ tests/test_tools.py
git commit -m "feat: add tool infrastructure and all pipeline tools"
```

---

### Task 5: Agent Runtime

**Files:**
- Create: `src/agent.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_agent.py
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.agent import AgentRuntime, AgentResult
from src.tools import tool


@tool
def mock_tool(query: str) -> dict:
    """A mock tool for testing."""
    return {"answer": f"Result for {query}"}


def _make_mock_response(content: str, tool_calls=None):
    """Create a mock OpenAI chat completion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop" if not tool_calls else "tool_calls"
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    return response


def test_agent_simple_response():
    """Agent returns structured output on first call, no tool use."""
    client = MagicMock()
    output_json = '{"working_title": "Test Show"}'
    client.chat.completions.create.return_value = _make_mock_response(output_json)

    agent = AgentRuntime(
        name="test_agent",
        system_prompt="You are a test agent.",
        tools=[],
        client=client,
        model="test-model",
        max_iterations=5,
    )
    result = agent.run(user_message="Create a show.")
    assert result.output == output_json
    assert result.tool_calls == []
    assert result.iterations == 1


def test_agent_uses_tool_then_responds():
    """Agent calls a tool, gets result, then produces final output."""
    client = MagicMock()

    # First call: model requests a tool call
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "mock_tool"
    tool_call.function.arguments = '{"query": "test"}'
    first_response = _make_mock_response(None, tool_calls=[tool_call])

    # Second call: model produces final output
    second_response = _make_mock_response('{"result": "done"}')

    client.chat.completions.create.side_effect = [first_response, second_response]

    agent = AgentRuntime(
        name="test_agent",
        system_prompt="You are a test agent.",
        tools=[mock_tool],
        client=client,
        model="test-model",
        max_iterations=5,
    )
    result = agent.run(user_message="Do a search.")
    assert result.output == '{"result": "done"}'
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "mock_tool"
    assert result.iterations == 2


def test_agent_max_iterations():
    """Agent stops after max_iterations and returns best effort."""
    client = MagicMock()

    # Every call requests another tool call (infinite loop scenario)
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "mock_tool"
    tool_call.function.arguments = '{"query": "loop"}'
    looping_response = _make_mock_response(None, tool_calls=[tool_call])

    client.chat.completions.create.return_value = looping_response

    agent = AgentRuntime(
        name="test_agent",
        system_prompt="You are a test agent.",
        tools=[mock_tool],
        client=client,
        model="test-model",
        max_iterations=3,
    )
    result = agent.run(user_message="Loop forever.")
    assert result.iterations == 3
    assert result.hit_max_iterations is True


def test_agent_tracks_token_usage():
    """Agent accumulates token usage across iterations."""
    client = MagicMock()
    output_json = '{"result": "ok"}'
    client.chat.completions.create.return_value = _make_mock_response(output_json)

    agent = AgentRuntime(
        name="test_agent",
        system_prompt="Test.",
        tools=[],
        client=client,
        model="test-model",
        max_iterations=5,
    )
    result = agent.run(user_message="Test.")
    assert result.token_usage["prompt"] == 100
    assert result.token_usage["completion"] == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_agent.py -v`
Expected: FAIL — cannot import AgentRuntime

- [ ] **Step 3: Implement agent.py**

`AgentRuntime` class with:
- `__init__(self, name, system_prompt, tools, client, model, max_iterations)` — stores config, builds OpenAI tool schemas from the tools list
- `run(self, user_message) -> AgentResult` — the ReAct loop:
  1. Build messages list: system prompt + user message
  2. Call `client.chat.completions.create(model=..., messages=..., tools=...)`
  3. If response has tool_calls: execute each tool via `execute_tool`, append tool results to messages, increment iteration, loop
  4. If response has content and no tool_calls: return the content as final output
  5. If max_iterations hit: return last content (or empty string) with `hit_max_iterations=True`
  6. Track token_usage by summing across all API calls

`AgentResult` dataclass with: `output: str`, `tool_calls: list[dict]`, `iterations: int`, `token_usage: dict`, `hit_max_iterations: bool`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_agent.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent.py tests/test_agent.py
git commit -m "feat: add generic agent runtime with ReAct loop"
```

---

### Task 6: Agent Prompts

**Files:**
- Create: `src/prompts/__init__.py`, `src/prompts/series_producer.py`, `src/prompts/producer.py`, `src/prompts/researcher.py`, `src/prompts/director.py`, `src/prompts/production_manager.py`, `src/prompts/evidence.py`

No separate test file — prompt builders are pure functions that return strings. They'll be validated through the integration tests in Task 8.

- [ ] **Step 1: Create `src/prompts/__init__.py`**

Empty file.

- [ ] **Step 2: Implement `src/prompts/series_producer.py`**

Two functions:
- `build_phase_a_prompt() -> str` — SP receives a one-line brief, outputs a `ProducerBrief` JSON. Identity, context, task, output format (include the JSON schema), constraints.
- `build_phase_b_prompt() -> str` — SP receives an `EpisodePackage`, reviews it, uses `approve()` or `request_rework()` tools, and if approving produces a `PitchDeck` JSON. Include the PitchDeck schema in the prompt.

Key prompt elements per the blueprint:
- Identity: Most senior editorial voice. Direct, experienced, commercially-minded.
- Context: Runs a factual TV production company.
- Constraints: Never invent research. Never do others' work. Brief, review, and unify only.

- [ ] **Step 3: Implement `src/prompts/producer.py`**

Two functions:
- `build_briefing_prompt() -> str` — Receives SP's `ProducerBrief`, decomposes into three specialist briefs (`ResearchBrief`, `DirectorBrief`, `PMBrief`). Output is a JSON object with keys `research_brief`, `director_brief`, `pm_brief`.
- `build_collation_prompt() -> str` — Receives all specialist outputs, collates into `EpisodePackage`. Can use `flag_gap()` tool. Adds editorial narrative.

Key prompt elements:
- Identity: Creative coordinator, headset, coffee. Manages the team.
- Constraints: Doesn't do the research/directing/budgeting — delegates and collates.

- [ ] **Step 4: Implement `src/prompts/researcher.py`**

`build_prompt() -> str` — Receives `ResearchBrief`, outputs `ResearchPack`. Has access to `web_search` tool. Must use web_search to find real information. Must cite sources and rate confidence on every `FactEntry` (confidence assessment is a prompt instruction, not a separate tool).

Key prompt elements:
- Identity: Thorough, methodical, evidence-based.
- Constraints: Must cite or note confidence. Never fabricate sources.

- [ ] **Step 5: Implement `src/prompts/director.py`**

`build_prompt() -> str` — Receives `DirectorBrief` + `ResearchPack`, outputs `CreativeTreatment`. Has access to `reference_research` tool. Shapes narrative arc, visual style, key sequences.

Key prompt elements:
- Identity: Creative visionary. Orange scarf, beret. Thinks in sequences and images.
- Constraints: This is a creative vision doc, NOT a shooting script.

- [ ] **Step 6: Implement `src/prompts/production_manager.py`**

`build_prompt() -> str` — Receives `PMBrief` + `ResearchPack` + `CreativeTreatment`, outputs `FeasibilityAssessment`. Has access to `lookup_rates` tool. Reality check on budget, logistics, crew.

Key prompt elements:
- Identity: Practical, detail-oriented. Calculator in hand.
- Constraints: Feasibility assessment, not a line-by-line budget.

- [ ] **Step 7: Implement `src/prompts/evidence.py`**

`build_prompt() -> str` — Receives the serialised orchestration log (list of LogEntry dicts as JSON). Outputs `EvidencePack` JSON. Prompt instructs the model to: summarise the pipeline run in 2-3 sentences, list each step with what was received/produced, total up duration and tokens, and summarise any rework that occurred.

Key prompt elements:
- Identity: A production coordinator compiling the paper trail.
- Task: Summarise, don't analyse. Factual, concise.
- Output format: Include the `EvidencePack` JSON schema.

The log entries are serialised as `json.dumps([entry.model_dump() for entry in log], default=str)` and passed as the user message.

- [ ] **Step 8: Commit**

```bash
git add src/prompts/
git commit -m "feat: add all agent system prompt builders"
```

---

### Task 7: Orchestrator

**Files:**
- Create: `src/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_orchestrator.py
import json
import pytest
from unittest.mock import MagicMock, patch
from src.orchestrator import Orchestrator, PipelineResult
from src.schemas import ProducerBrief, FormatSpec


def _mock_agent_result(output_dict: dict, tool_calls=None):
    """Create a mock AgentResult."""
    from src.agent import AgentResult
    return AgentResult(
        output=json.dumps(output_dict),
        tool_calls=tool_calls or [],
        iterations=1,
        token_usage={"prompt": 100, "completion": 50},
        hit_max_iterations=False,
    )


def _make_orchestrator(mock_config):
    """Helper to create an Orchestrator with mocked config."""
    with patch("src.orchestrator.create_client"), \
         patch("src.orchestrator.load_config") as mock_load:
        mock_load.return_value = mock_config
        return Orchestrator(config_path="config.yaml")


def test_orchestrator_init(mock_config):
    """Orchestrator loads config and creates a client."""
    orch = _make_orchestrator(mock_config)
    assert orch is not None


def test_orchestrator_log_entry(mock_config):
    """Orchestrator records log entries correctly."""
    orch = _make_orchestrator(mock_config)
    result = _mock_agent_result({"test": "output"})
    orch._log_step("test_agent", "test_phase", "test input", result)
    assert len(orch.log) == 1
    assert orch.log[0].agent_name == "test_agent"


def test_rework_detection(mock_config):
    """Orchestrator detects rework requests in agent tool calls."""
    orch = _make_orchestrator(mock_config)
    tool_calls = [
        {"name": "request_rework", "args": {"agent": "researcher",
         "notes": "Need more competitors"}}
    ]
    result = _mock_agent_result({"test": "output"}, tool_calls=tool_calls)
    rework = orch._detect_rework(result)
    assert rework is not None
    assert rework["agent"] == "researcher"


def test_rework_cap_enforced(mock_config):
    """Orchestrator refuses rework after hitting global cap."""
    orch = _make_orchestrator(mock_config)
    orch.rework_count = 2  # already at cap
    tool_calls = [
        {"name": "request_rework", "args": {"agent": "researcher",
         "notes": "More detail"}}
    ]
    result = _mock_agent_result({"test": "output"}, tool_calls=tool_calls)
    # Should return None (no rework) when cap is reached
    rework = orch._detect_rework(result)
    assert rework is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL — cannot import Orchestrator

- [ ] **Step 3: Implement orchestrator.py**

`Orchestrator` class:
- `__init__(self, config_path)` — loads config, creates client, initialises empty log
- `run(self, brief: str) -> PipelineResult` — the full pipeline:
  1. SP Phase A: create AgentRuntime with SP Phase A prompt, run with brief, parse ProducerBrief
  2. Producer Briefing: run with SP brief, parse three specialist briefs
  3. Researcher: run with research brief + web_search/assess_confidence tools
  4. Director: run with director brief + research pack + reference_research tool
  5. PM: run with PM brief + research + treatment + lookup_rates tool
  6. Producer Collation: run with all outputs + flag_gap tool
  7. SP Phase B: run with episode package + request_rework/approve tools
  8. Check for rework: if `request_rework` in tool_calls, re-run target agent (+ cascade), loop back to SP Phase B (max 2 cycles)
  9. Evidence generation: single model call with utility tier to summarise log
  10. Return PipelineResult with PitchDeck + EvidencePack + log
- `_run_agent(self, name, prompt, user_msg, tools, model_tier) -> AgentResult` — creates AgentRuntime and runs it, with timeout and error handling per spec
- `_log_step(self, agent_name, phase, input_summary, result)` — appends LogEntry to self.log
- `_detect_rework(self, result) -> dict | None` — checks result.tool_calls for request_rework
- `_handle_rework(self, rework, current_outputs) -> dict` — re-runs the target agent + cascades per the dependency graph below

**Cascade dependency graph** (when agent X is reworked, also re-run these):
```
researcher → [director, production_manager, producer_collation]
director → [producer_collation]
production_manager → [producer_collation]
```
Cascaded agents receive updated inputs (e.g., Director gets the reworked research pack). The cascade always ends with Producer collation re-running with the latest outputs. The orchestrator tracks `self.rework_count` (global counter) and refuses rework when it hits `max_rework_cycles`.

`PipelineResult` dataclass: `pitch_deck: dict | None`, `evidence: dict | None`, `log: list`, `success: bool`, `error: str | None`

**Schema validation:** try `json.loads(result.output)` then validate with the expected Pydantic model. On failure, retry once with a correction prompt that includes the validation error message. If the second attempt also fails, accept the raw JSON dict and log a warning.

**Error handling:**
- Wrap each `_run_agent` call in try/except. On API failure, retry once with 1s then 2s backoff. On second failure, log error and return a placeholder result with `success=False`.
- Tavily failures are handled inside `web_search` tool (returns empty results + error string).
- Agent timeout: use `signal.alarm` (Unix) or threading timeout to cap at `agent_timeout_seconds`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add orchestrator with rework loops and logging"
```

---

### Task 8: CLI Entry Point

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: Implement main.py**

```python
# src/main.py
"""CLI entry point for the Agentic Production Company pipeline."""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.orchestrator import Orchestrator


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="The Agentic Production Company — turn a one-line idea into a pitch deck"
    )
    parser.add_argument("brief", help="One-line show idea (e.g. 'A 3x60 doc about...')")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--output", default=None, help="Output directory for results")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("THE AGENTIC PRODUCTION COMPANY")
    print(f"{'='*60}")
    print(f"\nBrief: {args.brief}\n")

    orchestrator = Orchestrator(config_path=args.config)
    result = orchestrator.run(args.brief)

    if result.success:
        print(f"\n{'='*60}")
        print("PITCH DECK COMPLETE")
        print(f"{'='*60}\n")
        print(json.dumps(result.pitch_deck, indent=2))

        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "pitch_deck.json").write_text(
                json.dumps(result.pitch_deck, indent=2)
            )
            (out_dir / "evidence.json").write_text(
                json.dumps(result.evidence, indent=2)
            )
            (out_dir / "log.json").write_text(
                json.dumps([entry.model_dump() for entry in result.log],
                           indent=2, default=str)
            )
            print(f"\nResults saved to {out_dir}/")
    else:
        print(f"\nPipeline failed: {result.error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it runs (will fail without API keys, but should parse args)**

Run: `python -m src.main --help`
Expected: Shows help text with brief, --config, --output arguments

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add CLI entry point"
```

---

### Task 9: End-to-End Integration Test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write the integration test**

This test mocks the OpenAI client to return valid JSON for each pipeline stage, then verifies the full pipeline produces a PitchDeck and EvidencePack.

```python
# tests/test_integration.py
"""End-to-end pipeline test with mocked API responses."""
import json
import pytest
from unittest.mock import MagicMock, patch
from src.orchestrator import Orchestrator


# Pre-baked valid JSON responses for each agent
SP_PHASE_A_RESPONSE = json.dumps({
    "working_title": "The Last Lighthouse Keeper",
    "format": {"series_length": "3x60", "genre": "factual", "tone": "warm and observational"},
    "target_broadcaster": "BBC Two",
    "creative_steer": "An intimate portrait of a vanishing way of life.",
    "sample_episode_focus": "The daily routine and history of Lundy Island.",
    "assumptions": ["Access to Lundy Island is feasible"],
})

PRODUCER_BRIEFS_RESPONSE = json.dumps({
    "research_brief": {
        "topic": "Lighthouse keepers in the UK",
        "angles_to_explore": ["History", "Current keepers", "Automation"],
        "deliverables": ["competitive_landscape", "characters", "facts",
                         "archive_sources", "locations", "risks"],
        "quality_bar": "Broadcast-standard research pack",
    },
    "director_brief": {
        "topic": "The Last Lighthouse Keeper",
        "creative_steer": "Intimate, observational",
        "tone_guidance": "Warm, cinematic, unhurried",
        "key_questions": ["What does a day look like?", "What's being lost?"],
        "quality_bar": "Visually compelling treatment",
    },
    "pm_brief": {
        "topic": "The Last Lighthouse Keeper",
        "format": {"series_length": "3x60", "genre": "factual", "tone": "warm"},
        "known_requirements": ["Remote island location", "Weather dependent"],
        "quality_bar": "Realistic feasibility assessment",
    },
})

RESEARCH_RESPONSE = json.dumps({
    "competitive_landscape": [
        {"title": "Rock Lighthouse", "broadcaster": "BBC Four",
         "year": "2019", "relevance": "Similar remote lighthouse setting"},
    ],
    "characters": [
        {"name": "Gerald Williams", "role": "Last keeper at Lundy",
         "access_notes": "Lives in Devon, willing to participate",
         "story_angle": "30 years of service before automation"},
    ],
    "key_facts": [
        {"fact": "Lundy lighthouse was automated in 1994",
         "source": "Trinity House records", "confidence": "high"},
    ],
    "archive_sources": [
        {"type": "photo", "description": "Historical keeper photos",
         "access": "public"},
    ],
    "locations": [
        {"name": "Lundy Island", "rationale": "Primary location",
         "logistics_note": "Ferry from Bideford, weather dependent"},
    ],
    "risks_and_sensitivities": ["Weather-dependent access to Lundy"],
})

DIRECTOR_RESPONSE = json.dumps({
    "episode_title": "The Light on the Rock",
    "narrative_arc": {
        "opening": "Dawn breaks over the Bristol Channel.",
        "development": "Gerald walks us through his daily routine.",
        "climax": "The moment the light was switched to automatic.",
        "resolution": "Gerald visits the lighthouse one last time.",
    },
    "key_sequences": [
        {"name": "The Crossing", "description": "Ferry to Lundy in rough seas.",
         "visual_style": "Handheld, immersive", "duration_mins": 8},
    ],
    "overall_tone": "Warm, elegiac, observational",
    "visual_approach": "Natural light, long takes, intimate close-ups",
    "contributor_usage": [
        {"character_name": "Gerald Williams", "role_in_episode": "Main contributor"},
    ],
    "special_requirements": ["Drone for aerial lighthouse shots"],
})

PM_RESPONSE = json.dumps({
    "shooting_days": {"estimate": 12, "breakdown": "4 days per episode"},
    "budget_bracket": {"low": 150000, "high": 250000, "currency": "GBP",
                       "notes": "Excludes presenter fees"},
    "crew_requirements": [
        {"role": "Camera operator", "reason": "Remote single-camera shoot"},
    ],
    "logistics": [
        {"item": "Ferry access", "challenge": "Weather dependent",
         "mitigation": "Build 3 contingency days into schedule"},
    ],
    "feasibility_rating": "amber",
    "cost_saving_opportunities": ["Combine drone days across episodes"],
})

COLLATION_RESPONSE = json.dumps({
    "sp_brief": json.loads(SP_PHASE_A_RESPONSE),
    "research": json.loads(RESEARCH_RESPONSE),
    "treatment": json.loads(DIRECTOR_RESPONSE),
    "feasibility": json.loads(PM_RESPONSE),
    "editorial_narrative": "This show works because lighthouse keepers are a vanishing breed.",
    "gaps_and_conflicts": [],
})

SP_PHASE_B_RESPONSE = json.dumps({
    "title_page": {"working_title": "The Last Lighthouse Keeper",
                   "genre": "factual", "format": "3x60",
                   "target_broadcaster": "BBC Two"},
    "logline": "A vanishing way of life, told through the last men to keep the light.",
    "format_and_tone": {"series_length": "3x60", "genre": "factual",
                        "tone": "warm and observational"},
    "target_audience": "Adults 25-54, BBC Two viewers",
    "competitive_landscape": json.loads(RESEARCH_RESPONSE)["competitive_landscape"],
    "key_characters": json.loads(RESEARCH_RESPONSE)["characters"],
    "episode_breakdown": json.loads(DIRECTOR_RESPONSE),
    "feasibility_summary": {
        "feasibility_rating": "amber",
        "budget_bracket": {"low": 150000, "high": 250000, "currency": "GBP",
                           "notes": "Excludes presenter fees"},
        "shooting_days": 12,
        "key_risks": ["Weather-dependent island access"],
    },
    "why_now": "The last generation of keepers is aging. Their stories will be lost.",
    "sp_review_notes": "Strong package. Amber on feasibility is acceptable.",
    "unresolved_concerns": [],
})

EVIDENCE_RESPONSE = json.dumps({
    "pipeline_summary": "Pipeline completed successfully in one pass.",
    "steps": [
        {"agent_name": "series_producer", "phase": "sp_phase_a",
         "what_received": "One-line brief", "what_produced": "Structured producer brief",
         "tools_used": [], "duration_ms": 2000},
    ],
    "total_duration_ms": 15000,
    "total_tokens": {"prompt": 5000, "completion": 3000},
    "rework_count": 0,
    "rework_details": [],
})


def _make_approve_response():
    """SP Phase B response that includes an approve tool call."""
    msg = MagicMock()
    msg.content = SP_PHASE_B_RESPONSE
    tool_call = MagicMock()
    tool_call.id = "call_approve"
    tool_call.function.name = "approve"
    tool_call.function.arguments = "{}"
    msg.tool_calls = [tool_call]
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls"
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=500, completion_tokens=300)
    return response


def _make_simple_response(content: str):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=200, completion_tokens=150)
    return response


def _make_rework_response(agent: str, notes: str):
    """SP Phase B response that requests rework on an agent."""
    msg = MagicMock()
    msg.content = '{"status": "requesting rework"}'
    tool_call = MagicMock()
    tool_call.id = "call_rework"
    tool_call.function.name = "request_rework"
    tool_call.function.arguments = json.dumps({"agent": agent, "notes": notes})
    msg.tool_calls = [tool_call]
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls"
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=500, completion_tokens=300)
    return response


@patch("src.orchestrator.create_client")
@patch("src.orchestrator.load_config")
def test_full_pipeline_no_rework(mock_load_config, mock_create_client, mock_config):
    """Full pipeline runs end-to-end without rework."""
    mock_load_config.return_value = mock_config

    client = MagicMock()
    mock_create_client.return_value = client

    # Sequence: SP-A, Producer, Researcher, Director, PM,
    # Producer-collation, SP-B (approve + deck), SP-B (final after approve),
    # Evidence
    responses = [
        _make_simple_response(SP_PHASE_A_RESPONSE),
        _make_simple_response(PRODUCER_BRIEFS_RESPONSE),
        _make_simple_response(RESEARCH_RESPONSE),
        _make_simple_response(DIRECTOR_RESPONSE),
        _make_simple_response(PM_RESPONSE),
        _make_simple_response(COLLATION_RESPONSE),
        _make_approve_response(),
        _make_simple_response(SP_PHASE_B_RESPONSE),
        _make_simple_response(EVIDENCE_RESPONSE),
    ]
    client.chat.completions.create.side_effect = responses

    orch = Orchestrator(config_path="config.yaml")
    result = orch.run("A 3x60 documentary about the last lighthouse keepers in Britain")

    assert result.success is True
    assert result.pitch_deck is not None
    assert "The Last Lighthouse Keeper" in json.dumps(result.pitch_deck)
    assert len(orch.log) >= 7  # At least 7 pipeline steps logged


@patch("src.orchestrator.create_client")
@patch("src.orchestrator.load_config")
def test_full_pipeline_with_rework(mock_load_config, mock_create_client, mock_config):
    """Pipeline handles SP requesting rework on Researcher, then approving."""
    mock_load_config.return_value = mock_config

    client = MagicMock()
    mock_create_client.return_value = client

    # Sequence:
    # 1. SP-A, Producer, Researcher, Director, PM, Producer-collation
    # 2. SP-B: requests rework on researcher
    # 3. SP-B: rework tool result fed back, SP produces interim output
    # 4. Researcher re-run (rework), Director re-run (cascade),
    #    PM re-run (cascade), Producer re-collation
    # 5. SP-B again: approves this time
    # 6. SP-B: final output after approve
    # 7. Evidence
    responses = [
        # Initial pipeline
        _make_simple_response(SP_PHASE_A_RESPONSE),
        _make_simple_response(PRODUCER_BRIEFS_RESPONSE),
        _make_simple_response(RESEARCH_RESPONSE),
        _make_simple_response(DIRECTOR_RESPONSE),
        _make_simple_response(PM_RESPONSE),
        _make_simple_response(COLLATION_RESPONSE),
        # SP-B first pass: requests rework
        _make_rework_response("researcher", "Competitive landscape is thin"),
        _make_simple_response('{"status": "awaiting rework"}'),  # after tool
        # Rework cascade: re-run Researcher, Director, PM, Producer-collation
        _make_simple_response(RESEARCH_RESPONSE),   # reworked researcher
        _make_simple_response(DIRECTOR_RESPONSE),    # cascade: director
        _make_simple_response(PM_RESPONSE),           # cascade: PM
        _make_simple_response(COLLATION_RESPONSE),    # cascade: producer
        # SP-B second pass: approves
        _make_approve_response(),
        _make_simple_response(SP_PHASE_B_RESPONSE),
        # Evidence
        _make_simple_response(EVIDENCE_RESPONSE),
    ]
    client.chat.completions.create.side_effect = responses

    orch = Orchestrator(config_path="config.yaml")
    result = orch.run("A 3x60 documentary about the last lighthouse keepers in Britain")

    assert result.success is True
    assert result.pitch_deck is not None
    assert orch.rework_count == 1
    # Should have more log entries than the no-rework path
    assert len(orch.log) >= 11
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py -v`
Expected: FAIL — depends on Tasks 1–7 being implemented

- [ ] **Step 3: Run test after all prior tasks are complete**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "feat: add end-to-end integration test with mocked API"
```

---

### Task 10: Live Smoke Test

**Files:** None — this is a manual verification step.

- [ ] **Step 1: Set up environment**

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 2: Configure .env**

Copy `.env.example` to `.env` and fill in `NEBIUS_API_KEY` and `TAVILY_API_KEY`.

- [ ] **Step 3: Run the pipeline with a test brief**

```bash
python -m src.main "A 3x60 documentary about the last lighthouse keepers in Britain" --output output/test1
```

Expected: Pipeline runs end-to-end, prints pitch deck JSON, saves files to `output/test1/`.

- [ ] **Step 4: Review the output**

Check:
- `output/test1/pitch_deck.json` — has all PitchDeck fields populated with coherent content
- `output/test1/evidence.json` — shows all pipeline steps
- `output/test1/log.json` — has entries for every agent invocation
- Researcher output references real shows/people (from Tavily search)

- [ ] **Step 5: Run two more test briefs**

```bash
python -m src.main "A show about water" --output output/test2
python -m src.main "A 1x30 about the last lighthouse keeper on Lundy Island" --output output/test3
```

Check that the pipeline handles both a vague brief and a specific brief gracefully.

- [ ] **Step 6: Commit any fixes needed, then final commit**

```bash
git add -A
git commit -m "feat: Phase 1 engine complete — pipeline tested with 3 briefs"
```
