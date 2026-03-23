# Agentic Production Company — Phase 1 Engine Design

**Date:** 2026-03-23
**Status:** Draft
**Author:** Colin Byrne + Claude

---

## Overview

A multi-agent pipeline that takes a one-line TV show idea and produces a structured pitch deck. Five agents (Series Producer, Producer, Researcher, Director, Production Manager) collaborate through a sequential orchestration with real tool use and feedback loops — making this genuinely agentic rather than a simple prompt chain.

## Architecture

### Core Principle: Agent = Model + Loop + Tools

Each agent runs the same generic runtime. What differentiates them is their system prompt, available tools, and I/O schema. The runtime handles the execution loop, tool dispatch, schema validation, and retry logic.

### Three Layers

```
┌──────────────────────────────────────────────┐
│              Orchestrator                     │
│  Sequential pipeline with decision points    │
│  Manages rework loops (max 2 per agent)      │
│  Writes orchestration log at every step      │
└──────────────┬───────────────────────────────┘
               │
         ┌─────┴─────┐
         │   Agent    │  ← generic, reusable
         │  Runtime   │
         │            │
         │  • system prompt + context injection │
         │  • tool registry per agent           │
         │  • ReAct execution loop              │
         │  • structured I/O via Pydantic       │
         │  • max 5 iterations per invocation   │
         └─────┬─────┘
               │
         ┌─────┴─────┐
         │  Provider  │  ← config-driven
         │  Client    │
         │            │
         │  • OpenAI-compatible SDK             │
         │  • base_url + api_key from config    │
         │  • model name from config            │
         └───────────┘
```

### Provider Configuration

All OpenAI-compatible. Swapping providers = config change, not code change.

```yaml
providers:
  primary:
    base_url: "https://api.tokenfactory.nebius.com/v1"
    api_key: "${NEBIUS_API_KEY}"
    models:
      strong: "Qwen3-235B-A22B-Instruct-2507"
      research: "DeepSeek-V3-0324"
      utility: "Qwen3-30B-A3B-Instruct-2507"

tools:
  search:
    provider: "tavily"
    api_key: "${TAVILY_API_KEY}"
```

Model assignment per agent:

| Agent | Model Tier | Rationale |
|-------|-----------|-----------|
| Series Producer | strong | Best editorial judgement for orchestration and review |
| Producer | strong | Creative coordination, instruction-following |
| Researcher | research | Factual density, structured output |
| Director | strong | Nuanced, imaginative language |
| Production Manager | strong | Reasoning capability for budget/logistics |
| Evidence Pack | utility | Simple summarisation — cheaper model is fine |

## Agent Execution Loop

```
Agent receives input
    │
    ▼
Model called with: system prompt + input + available tools
    │
    ▼
┌─→ Model responds
│       │
│   Tool call? ──yes──→ Execute tool → Feed result back ─┐
│       │                                                  │
│       no                                                 │
│       ▼                                                  │
│   Final structured output                                │
│       │                                                  │
│   Schema valid? ──no──→ Retry with correction prompt ────┘
│       │
│       yes
│       ▼
│   Return output
│
└── Max iterations (5) hit → Return best effort + warning
```

## Tool Registry

| Agent | Tools | Purpose |
|-------|-------|---------|
| Series Producer | `request_rework(agent, notes)`, `approve(section)` | Supervisory — can send work back with feedback |
| Producer | `request_rework(agent, notes)`, `flag_gap(description)` | Coordination — flags issues for SP visibility |
| Researcher | `web_search(query)`, `assess_confidence(claim)` | Research — actually searches the web via Tavily |
| Director | `reference_research(section)` | Creative — pulls specific research sections on demand |
| Production Manager | `lookup_rates(role, region)` | Logistics — rough cost lookups (static table in v1) |

### Tool Design

- Tools are plain Python functions with type hints and docstrings
- The agent runtime auto-generates OpenAI tool schemas from function signatures
- `web_search` is the only external tool; everything else operates on pipeline data
- `request_rework` is what makes supervisory agents genuinely agentic

## Orchestration Flow

```
User submits one-line brief
        │
        ▼
   SP Phase A ─────→ Structured producer brief
        │
        ▼
   Producer ───────→ 3 specialist briefs
        │
        ▼ (sequential in v1)
   Researcher ─────→ Research pack (with real web search)
        │
        ▼
   Director ───────→ Creative treatment (informed by research)
        │
        ▼
   PM ─────────────→ Feasibility assessment
        │
        ▼
   Producer Phase B → Collated episode package
        │
        ▼
   SP Phase B ─────→ Review → approve or request_rework
        │                         │
        │            ┌────────────┘
        │            ▼
        │      Re-run agent with SP notes
        │      (max 2 rework cycles per agent)
        │            │
        │            ▼
        │      Back to SP for re-review
        │
        ▼
   Evidence Generator → Evidence pack from orchestration log
        │
        ▼
   Final pitch deck + evidence pack
```

### Rework Mechanism — Control Flow Semantics

`request_rework` is not a normal tool — it is a **control flow signal**. When an agent calls it:

1. The tool returns `{"status": "rework_requested", "agent": "<name>", "notes": "<notes>"}` to the calling agent
2. The calling agent **must then produce its final output** (it cannot keep looping after requesting rework)
3. The orchestrator inspects the agent's output for rework requests
4. If rework was requested, the orchestrator **re-runs the named agent** with: original brief + rework notes appended to the user message
5. **Cascade rule:** if the Researcher is reworked, the orchestrator also re-runs Director and PM (since they consumed Researcher output). Producer collation then re-runs with updated inputs. This cascade is automatic.
6. The reworked outputs feed back to SP Phase B for re-review
7. Capped at **2 rework cycles total** (not per agent) to keep runtime bounded
8. After cap: SP must work with what it has and note any remaining concerns in the final deck

### `approve` Tool Semantics

SP calls `approve()` (no arguments) to signal that the full `EpisodePackage` passes review. This terminates the SP Phase B loop and the orchestrator proceeds to evidence generation. If SP neither approves nor requests rework within its iteration limit, the orchestrator treats it as implicit approval with a warning logged.

### `flag_gap` Tool Semantics

Producer calls `flag_gap(description)` during collation. Each call appends to the `EpisodePackage.gaps_and_conflicts` list. These are informational — they do not block the pipeline but are visible to SP during review, giving SP the information needed to decide whether to approve or request rework.

### Logging

Every agent invocation logs:
- Agent name, timestamp
- Input summary (first 200 chars)
- Output summary (first 200 chars)
- Token usage (prompt + completion)
- Duration (ms)
- Tool calls made (name + args summary)
- Rework requests (if any)

Log entries are stored as an in-memory list of `LogEntry` objects during a pipeline run, and serialised to JSON on completion.

```python
class ToolCallLog(BaseModel):
    tool_name: str
    args_summary: str  # first 100 chars of args
    result_summary: str  # first 100 chars of result

class LogEntry(BaseModel):
    agent_name: str
    phase: str  # e.g. "sp_phase_a", "researcher", "sp_phase_b_rework_1"
    timestamp: datetime
    input_summary: str  # first 200 chars
    output_summary: str  # first 200 chars
    token_usage: dict  # {"prompt": int, "completion": int}
    duration_ms: int
    tool_calls: list[ToolCallLog]
    rework_requested: bool
    rework_target: str | None  # agent name if rework requested
    rework_notes: str | None
```

This log feeds the evidence pack and will drive the Phase 2 visual evidence trail.

### Evidence Generator

The Evidence Generator is a **post-processing step, not a sixth agent**. It uses the utility model to summarise the orchestration log into a human-readable evidence pack. It receives the full `list[LogEntry]` and produces:

```python
class EvidencePack(BaseModel):
    pipeline_summary: str  # 2-3 sentence overview of the run
    steps: list[EvidenceStep]
    total_duration_ms: int
    total_tokens: dict  # {"prompt": int, "completion": int}
    rework_count: int
    rework_details: list[str]  # human-readable rework summaries

class EvidenceStep(BaseModel):
    agent_name: str
    phase: str
    what_received: str  # one-line summary
    what_produced: str  # one-line summary
    tools_used: list[str]
    duration_ms: int
```

It runs as a single model call (no tools, no loop) — just summarisation and formatting.

## I/O Schemas

All defined as Pydantic models. Directly from the blueprint with minor adjustments.

### SP → Producer Brief

```python
class ProducerBrief(BaseModel):
    working_title: str
    format: FormatSpec  # series_length, genre, tone
    target_broadcaster: str
    creative_steer: str  # 2-3 sentences
    sample_episode_focus: str
    assumptions: list[str]  # if brief was vague
```

### Producer → Researcher Brief

```python
class ResearchBrief(BaseModel):
    topic: str
    angles_to_explore: list[str]
    deliverables: list[str]
    quality_bar: str
```

### Researcher → Research Pack

```python
class ResearchPack(BaseModel):
    competitive_landscape: list[CompetitorEntry]
    characters: list[CharacterEntry]
    key_facts: list[FactEntry]  # each with confidence: high|medium|low
    archive_sources: list[ArchiveEntry]
    locations: list[LocationEntry]
    risks_and_sensitivities: list[str]
```

### Director → Creative Treatment

```python
class CreativeTreatment(BaseModel):
    episode_title: str
    narrative_arc: NarrativeArc  # opening, development, climax, resolution
    key_sequences: list[SequenceEntry]  # 3-4 set pieces
    overall_tone: str
    visual_approach: str
    contributor_usage: list[ContributorEntry]
    special_requirements: list[str]
```

### PM → Feasibility Assessment

```python
class FeasibilityAssessment(BaseModel):
    shooting_days: ShootingEstimate
    budget_bracket: BudgetBracket  # low, high, currency, notes
    crew_requirements: list[CrewEntry]
    logistics: list[LogisticsEntry]
    feasibility_rating: Literal["green", "amber", "red"]
    cost_saving_opportunities: list[str]
```

### Producer → SP (Collated Package)

Combines all specialist outputs plus:
```python
class EpisodePackage(BaseModel):
    sp_brief: ProducerBrief
    research: ResearchPack
    treatment: CreativeTreatment
    feasibility: FeasibilityAssessment
    editorial_narrative: str  # Producer's "why this works"
    gaps_and_conflicts: list[str]
```

### Nested Schema Definitions

```python
class FormatSpec(BaseModel):
    series_length: str  # e.g. "3x60", "6x30"
    genre: str
    tone: str

class CompetitorEntry(BaseModel):
    title: str
    broadcaster: str
    year: str
    relevance: str  # why this matters to our show

class CharacterEntry(BaseModel):
    name: str
    role: str  # their role in the story
    access_notes: str  # how easy to get them on camera
    story_angle: str

class FactEntry(BaseModel):
    fact: str
    source: str
    confidence: Literal["high", "medium", "low"]

class ArchiveEntry(BaseModel):
    type: str  # photo, video, document, etc.
    description: str
    access: str  # public, restricted, unknown

class LocationEntry(BaseModel):
    name: str
    rationale: str
    logistics_note: str

class NarrativeArc(BaseModel):
    opening: str
    development: str
    climax: str
    resolution: str

class SequenceEntry(BaseModel):
    name: str
    description: str
    visual_style: str
    duration_mins: int

class ContributorEntry(BaseModel):
    character_name: str
    role_in_episode: str

class ShootingEstimate(BaseModel):
    estimate: int  # days
    breakdown: str

class BudgetBracket(BaseModel):
    low: int
    high: int
    currency: str  # default "GBP"
    notes: str

class CrewEntry(BaseModel):
    role: str
    reason: str

class LogisticsEntry(BaseModel):
    item: str
    challenge: str
    mitigation: str
```

### Producer → Specialist Briefs

The Producer outputs three briefs (one per specialist). `ResearchBrief` is defined above. The other two:

```python
class DirectorBrief(BaseModel):
    topic: str
    creative_steer: str  # from SP brief
    tone_guidance: str
    key_questions: list[str]  # what the Director should answer
    quality_bar: str

class PMBrief(BaseModel):
    topic: str
    format: FormatSpec
    known_requirements: list[str]  # anything already flagged
    quality_bar: str
```

### Final Pitch Deck

```python
class PitchDeck(BaseModel):
    title_page: TitlePage
    logline: str  # one-sentence hook
    format_and_tone: FormatSpec
    target_audience: str
    competitive_landscape: list[CompetitorEntry]
    key_characters: list[CharacterEntry]
    episode_breakdown: CreativeTreatment
    feasibility_summary: FeasibilitySummary
    why_now: str  # editorial argument for timeliness
    sp_review_notes: str  # SP's sign-off comments
    unresolved_concerns: list[str]  # anything SP flagged but accepted

class TitlePage(BaseModel):
    working_title: str
    genre: str
    format: str  # e.g. "3x60"
    target_broadcaster: str

class FeasibilitySummary(BaseModel):
    feasibility_rating: Literal["green", "amber", "red"]
    budget_bracket: BudgetBracket
    shooting_days: int
    key_risks: list[str]
```

## Project Structure

```
agentic-production-company/
├── .env.example
├── .gitignore
├── config.yaml
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── main.py           # Entry point — accepts brief, runs pipeline
│   ├── provider.py       # OpenAI-compatible client, config-driven
│   ├── agent.py          # Generic agent runtime
│   ├── orchestrator.py   # Pipeline sequencing, rework loops, logging
│   ├── schemas.py        # Pydantic models for all I/O
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── search.py     # Tavily web_search
│   │   ├── rework.py     # request_rework, approve
│   │   ├── research.py   # assess_confidence, reference_research
│   │   └── rates.py      # lookup_rates
│   └── prompts/
│       ├── series_producer.py
│       ├── producer.py
│       ├── researcher.py
│       ├── director.py
│       └── production_manager.py
├── tests/
│   ├── test_agent.py
│   ├── test_orchestrator.py
│   ├── test_schemas.py
│   └── test_tools.py
└── docs/
    └── superpowers/
        └── specs/
```

### Design Decisions

- **Prompts as Python files:** Each exports `build_system_prompt(context)`. Allows runtime context injection (brief, previous outputs) via f-strings. Cleaner than loading/templating text files.
- **Pydantic for schemas:** Validation, serialization, and auto-generation of JSON schemas for the models.
- **Single OpenAI SDK:** One client, pointed at whatever base_url config says. No multi-SDK abstraction needed.

## Secrets & Safety

- `.env` in `.gitignore` — never committed
- `.env.example` ships with blank keys so contributors know what's needed
- All outputs go to stdout or a designated output directory
- No file writes outside the project directory
- Agent loop capped at 5 iterations; rework capped at 2 cycles

## Phase 1 Definition of Done

- All five agents produce valid, schema-conformant output
- Pipeline runs end-to-end from a one-line brief without human intervention
- Researcher performs real web searches via Tavily
- SP can request rework and the pipeline responds correctly
- Evidence log accurately records every step
- Full pipeline completes in under 3 minutes without rework (aspirational: 5 minutes with rework)
- Successfully tested with at least 3 different briefs

## Error Handling

- **Model API failures:** Retry once with exponential backoff (1s, then 2s). If both fail, log the error and skip the agent — the orchestrator surfaces the gap to the user rather than crashing the pipeline.
- **Tavily search failures:** The Researcher logs the failed query and continues without that search result. The `assess_confidence` tool should reflect reduced confidence when search data is missing.
- **Schema validation failures:** Retry once with a correction prompt that includes the validation error. If the second attempt also fails, accept the raw output and log a warning. Downstream agents receive what they can parse.
- **Timeout:** Individual agent calls timeout at 60 seconds. The orchestrator logs a timeout and moves on.

## Roadmap (Not Phase 1)

- **Kimi K2.5:** Evaluate for Director (multimodal creative vision) and Researcher (agentic tuning)
- **Exa semantic search:** Secondary search tool for "find similar" research queries
- **Parallel specialist execution:** Run Researcher/Director/PM concurrently (requires decoupling Director/PM from each other)
- **Phase 2:** Pixel-art visual layer (full blueprint Phase 2)
