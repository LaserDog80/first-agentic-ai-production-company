"""Demo pipeline runner — simulates the real pipeline with fixture data."""
import asyncio
from typing import Callable

from src.demo_data import get_demo_result


# Event sequence mimicking the real orchestrator's 9 steps.
_DEMO_EVENTS: list[dict] = [
    # Step 1 — SP Phase A
    {
        "type": "agent_start",
        "agent": "series_producer",
        "phase": "phase_a",
        "step": 1,
        "total_steps": 9,
        "message": "Reading the brief and shaping editorial vision...",
    },
    {
        "type": "agent_done",
        "agent": "series_producer",
        "phase": "phase_a",
        "message": "Editorial vision set. Producer brief ready.",
    },
    # Step 2 — Producer Briefing
    {
        "type": "agent_start",
        "agent": "producer",
        "phase": "briefing",
        "step": 2,
        "total_steps": 9,
        "message": "Creating briefs for the specialist team...",
    },
    {
        "type": "agent_done",
        "agent": "producer",
        "phase": "briefing",
        "message": "Specialist briefs dispatched to the team.",
    },
    # Step 3 — Researcher
    {
        "type": "agent_start",
        "agent": "researcher",
        "phase": "research",
        "step": 3,
        "total_steps": 9,
        "message": (
            "Searching the web for facts, competitors, "
            "and locations..."
        ),
    },
    {
        "type": "tool_call",
        "agent": "researcher",
        "tool": "web_search",
        "args": {"query": "traditional beekeeping endangered practices"},
        "message": "Using web_search...",
    },
    {
        "type": "tool_call",
        "agent": "researcher",
        "tool": "web_search",
        "args": {"query": "Honeyland documentary box office"},
        "message": "Using web_search...",
    },
    {
        "type": "agent_done",
        "agent": "researcher",
        "phase": "research",
        "message": "Research pack compiled.",
    },
    # Commentary 1
    {
        "type": "commentary",
        "text": (
            "The researcher has been digging into traditional "
            "beekeeping across three countries — fascinating "
            "material coming in on cliff-honey harvesting in Turkey."
        ),
    },
    # Step 4 — Director
    {
        "type": "agent_start",
        "agent": "director",
        "phase": "treatment",
        "step": 4,
        "total_steps": 9,
        "message": "Crafting the narrative arc and visual style...",
    },
    {
        "type": "tool_call",
        "agent": "director",
        "tool": "reference_research",
        "args": {"section": "characters"},
        "message": "Using reference_research...",
    },
    {
        "type": "agent_done",
        "agent": "director",
        "phase": "treatment",
        "message": "Creative treatment complete.",
    },
    # Step 5 — PM
    {
        "type": "agent_start",
        "agent": "production_manager",
        "phase": "feasibility",
        "step": 5,
        "total_steps": 9,
        "message": "Calculating budget, crew, and logistics...",
    },
    {
        "type": "tool_call",
        "agent": "production_manager",
        "tool": "lookup_rates",
        "args": {"role": "camera_operator", "region": "Eastern Europe"},
        "message": "Using lookup_rates...",
    },
    {
        "type": "agent_done",
        "agent": "production_manager",
        "phase": "feasibility",
        "message": "Feasibility assessment done.",
    },
    # Commentary 2
    {
        "type": "commentary",
        "text": (
            "Budget is landing around the 450-620k GBP range. "
            "The cliff sequences push costs up but they are the "
            "visual centrepiece — worth every penny."
        ),
    },
    # Step 6 — Producer Collation
    {
        "type": "agent_start",
        "agent": "producer",
        "phase": "collation",
        "step": 6,
        "total_steps": 9,
        "message": "Collating all outputs into episode package...",
    },
    {
        "type": "agent_done",
        "agent": "producer",
        "phase": "collation",
        "message": "Episode package assembled.",
    },
    # Step 7 — SP Phase B
    {
        "type": "agent_start",
        "agent": "series_producer",
        "phase": "phase_b",
        "step": 7,
        "total_steps": 9,
        "message": "Reviewing the episode package...",
    },
    {
        "type": "agent_done",
        "agent": "series_producer",
        "phase": "phase_b",
        "message": "Pitch deck approved!",
    },
    # Commentary 3 (outro-style)
    {
        "type": "commentary",
        "text": (
            "All five agents have had their say. The Series "
            "Producer is satisfied — pitch deck approved on "
            "first pass. Assembling the final output now."
        ),
    },
]


async def run_demo_pipeline(
    emit: Callable,
    brief: str,
) -> dict:
    """Simulate the full pipeline with realistic timing.

    Emits the same event types as the real orchestrator so the
    frontend renders identically. Total runtime ~10-15 seconds.

    Args:
        emit: Async callable that sends an event dict to the client.
        brief: The brief text (used in pipeline_start event only).

    Returns:
        Demo fixture result dict with pitch_deck, evidence, and log.
    """
    await emit({
        "type": "pipeline_start",
        "brief": brief or "Demo: The Last Beekeeper",
    })

    for event in _DEMO_EVENTS:
        etype = event.get("type", "")

        # Vary delays by event type for realism
        if etype == "agent_start":
            await asyncio.sleep(1.2)
        elif etype == "agent_done":
            await asyncio.sleep(0.8)
        elif etype == "tool_call":
            await asyncio.sleep(0.5)
        elif etype == "commentary":
            await asyncio.sleep(1.0)
        else:
            await asyncio.sleep(0.4)

        await emit(event)

    # Outro
    await asyncio.sleep(0.8)
    await emit({
        "type": "outro",
        "text": (
            "Five AI agents just turned a single sentence into a "
            "broadcast-ready pitch deck — no APIs were harmed in "
            "the making of this demo.\n\n"
            "In a real run, each agent calls live LLMs and web "
            "search tools. This demo proves the UI works end-to-end."
        ),
    })

    result = get_demo_result()

    await asyncio.sleep(0.5)
    # pipeline_complete is emitted by the caller (app.py) with
    # download_url attached, so we just return the data here.
    return result
