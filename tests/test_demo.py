"""Tests for demo mode — fixture data, demo runner, and CLI flag."""
import asyncio
import json

import pytest

from src.demo_data import get_demo_result
from src.demo_runner import run_demo_pipeline
from src.schemas import PitchDeck, EvidencePack


# ── Demo data fixtures ──

def test_get_demo_result_returns_expected_keys():
    """get_demo_result returns pitch_deck, evidence, and log."""
    result = get_demo_result()
    assert "pitch_deck" in result
    assert "evidence" in result
    assert "log" in result


def test_demo_pitch_deck_validates():
    """Demo pitch deck passes PitchDeck schema validation."""
    result = get_demo_result()
    validated = PitchDeck.model_validate(result["pitch_deck"])
    assert validated.title_page.working_title == "The Last Beekeeper"


def test_demo_evidence_validates():
    """Demo evidence pack passes EvidencePack schema validation."""
    result = get_demo_result()
    validated = EvidencePack.model_validate(result["evidence"])
    assert validated.total_duration_ms > 0
    assert len(validated.steps) > 0


def test_demo_pitch_deck_has_realistic_content():
    """Demo fixture contains detailed, non-placeholder content."""
    result = get_demo_result()
    deck = result["pitch_deck"]
    # Has characters
    assert len(deck["key_characters"]) >= 3
    # Has competitors
    assert len(deck["competitive_landscape"]) >= 2
    # Logline is substantial
    assert len(deck["logline"]) > 50
    # Has episode breakdown with sequences
    assert len(deck["episode_breakdown"]["key_sequences"]) >= 2


# ── Demo runner ──

@pytest.mark.anyio
async def test_run_demo_pipeline_emits_expected_events():
    """Demo runner emits the standard pipeline event sequence."""
    events: list[dict] = []

    async def capture(event: dict) -> None:
        events.append(event)

    result = await run_demo_pipeline(capture, "test brief")

    # Check result
    assert "pitch_deck" in result
    assert "evidence" in result

    # Extract event types
    types = [e["type"] for e in events]

    # Must have pipeline_start
    assert types[0] == "pipeline_start"

    # Must have at least one of each key event type
    assert "agent_start" in types
    assert "agent_done" in types
    assert "tool_call" in types
    assert "commentary" in types
    assert "outro" in types

    # agent_start events should have step/total_steps
    starts = [e for e in events if e["type"] == "agent_start"]
    for s in starts:
        assert "step" in s
        assert "total_steps" in s
        assert s["total_steps"] == 9


@pytest.mark.anyio
async def test_run_demo_pipeline_uses_brief_in_start_event():
    """The brief text appears in the pipeline_start event."""
    events: list[dict] = []

    async def capture(event: dict) -> None:
        events.append(event)

    await run_demo_pipeline(capture, "My custom brief")

    start = events[0]
    assert start["type"] == "pipeline_start"
    assert "My custom brief" in start["brief"]


# ── CLI --demo flag ──

def test_cli_demo_flag(capsys):
    """--demo flag prints pitch deck JSON without running orchestrator."""
    import sys
    from unittest.mock import patch

    test_args = ["main.py", "--demo"]
    with patch.object(sys, "argv", test_args):
        from src.main import main
        main()

    captured = capsys.readouterr()
    assert "DEMO MODE" in captured.out
    assert "The Last Beekeeper" in captured.out
    # Should be valid JSON in the output
    # Find the JSON portion (after the header lines)
    lines = captured.out.split("\n")
    json_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            json_start = i
            break
    assert json_start is not None
    json_text = "\n".join(lines[json_start:])
    parsed = json.loads(json_text)
    assert parsed["title_page"]["working_title"] == "The Last Beekeeper"
