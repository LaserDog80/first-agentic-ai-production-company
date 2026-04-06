"""End-to-end integration tests for the full pipeline with mocked OpenAI client."""
import json
from unittest.mock import MagicMock, patch

import pytest

from src.orchestrator import Orchestrator, PipelineResult


# ---------------------------------------------------------------------------
# Pre-baked mock responses (valid against Pydantic schemas)
# ---------------------------------------------------------------------------

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
        "deliverables": [
            "competitive_landscape", "characters", "facts",
            "archive_sources", "locations", "risks",
        ],
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
        {
            "title": "Rock Lighthouse",
            "broadcaster": "BBC Four",
            "year": "2019",
            "relevance": "Similar remote lighthouse setting",
        },
    ],
    "characters": [
        {
            "name": "Gerald Williams",
            "role": "Last keeper at Lundy",
            "access_notes": "Lives in Devon",
            "story_angle": "30 years of service before automation",
        },
    ],
    "key_facts": [
        {
            "fact": "Lundy lighthouse was automated in 1994",
            "source": "Trinity House records",
            "confidence": "high",
        },
    ],
    "archive_sources": [
        {"type": "photo", "description": "Historical keeper photos", "access": "public"},
    ],
    "locations": [
        {
            "name": "Lundy Island",
            "rationale": "Primary location",
            "logistics_note": "Ferry from Bideford, weather dependent",
        },
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
        {
            "name": "The Crossing",
            "description": "Ferry to Lundy in rough seas.",
            "visual_style": "Handheld, immersive",
            "duration_mins": 8,
        },
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
    "budget_bracket": {
        "low": 150000,
        "high": 250000,
        "currency": "GBP",
        "notes": "Excludes presenter fees",
    },
    "crew_requirements": [
        {"role": "Camera operator", "reason": "Remote single-camera shoot"},
    ],
    "logistics": [
        {
            "item": "Ferry access",
            "challenge": "Weather dependent",
            "mitigation": "Build 3 contingency days into schedule",
        },
    ],
    "feasibility_rating": "amber",
    "cost_saving_opportunities": ["Combine drone days across episodes"],
})

COLLATION_RESPONSE = json.dumps({
    "sp_brief": json.loads(SP_PHASE_A_RESPONSE),
    "research": json.loads(RESEARCH_RESPONSE),
    "treatment": json.loads(DIRECTOR_RESPONSE),
    "feasibility": json.loads(PM_RESPONSE),
    "editorial_narrative": (
        "This show works because lighthouse keepers are a vanishing breed."
    ),
    "gaps_and_conflicts": [],
})

SP_PHASE_B_RESPONSE = json.dumps({
    "title_page": {
        "working_title": "The Last Lighthouse Keeper",
        "genre": "factual",
        "format": "3x60",
        "target_broadcaster": "BBC Two",
    },
    "logline": (
        "A vanishing way of life, told through the last men to keep the light."
    ),
    "format_and_tone": {
        "series_length": "3x60",
        "genre": "factual",
        "tone": "warm and observational",
    },
    "target_audience": "Adults 25-54, BBC Two viewers",
    "competitive_landscape": json.loads(RESEARCH_RESPONSE)["competitive_landscape"],
    "key_characters": json.loads(RESEARCH_RESPONSE)["characters"],
    "episode_breakdown": json.loads(DIRECTOR_RESPONSE),
    "feasibility_summary": {
        "feasibility_rating": "amber",
        "budget_bracket": {
            "low": 150000,
            "high": 250000,
            "currency": "GBP",
            "notes": "Excludes presenter fees",
        },
        "shooting_days": 12,
        "key_risks": ["Weather-dependent island access"],
    },
    "why_now": "The last generation of keepers is aging.",
    "sp_review_notes": "Strong package. Amber on feasibility is acceptable.",
    "unresolved_concerns": [],
})

EVIDENCE_RESPONSE = json.dumps({
    "pipeline_summary": "Pipeline completed successfully.",
    "steps": [
        {
            "agent_name": "series_producer",
            "phase": "sp_phase_a",
            "what_received": "One-line brief",
            "what_produced": "Structured producer brief",
            "tools_used": [],
            "duration_ms": 2000,
        },
    ],
    "total_duration_ms": 15000,
    "total_tokens": {"prompt": 5000, "completion": 3000},
    "rework_count": 0,
    "rework_details": [],
})


# ---------------------------------------------------------------------------
# Mock response helpers
# ---------------------------------------------------------------------------

def _make_simple_response(content: str) -> MagicMock:
    """Create a mock API response with content only (no tool calls)."""
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


def _make_rework_response(agent: str, notes: str) -> MagicMock:
    """Create a mock API response with a JSON rework request (no tools)."""
    rework_json = json.dumps({"rework_request": {"agent": agent, "notes": notes}})
    return _make_simple_response(rework_json)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFullPipelineNoRework:
    """Full pipeline where SP approves on first review (no rework)."""

    def test_full_pipeline_no_rework(self, mock_config: dict) -> None:
        """Run the happy-path pipeline end-to-end with mocked API responses."""
        mock_responses = [
            _make_simple_response(SP_PHASE_A_RESPONSE),
            _make_simple_response(PRODUCER_BRIEFS_RESPONSE),
            _make_simple_response(RESEARCH_RESPONSE),
            _make_simple_response(DIRECTOR_RESPONSE),
            _make_simple_response(PM_RESPONSE),
            _make_simple_response(COLLATION_RESPONSE),
            _make_simple_response(SP_PHASE_B_RESPONSE),
            _make_simple_response(EVIDENCE_RESPONSE),
        ]

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_responses

        with patch("src.core.pipeline.load_config", return_value=mock_config), \
             patch("src.core.pipeline.create_client", return_value=mock_client), \
             patch("time.sleep"):
            orch = Orchestrator(config_path="fake.yaml")
            result = orch.run("A documentary about lighthouse keepers")

        assert result.success is True, f"Pipeline failed: {result.error}"
        assert result.pitch_deck is not None
        assert result.pitch_deck["title_page"]["working_title"] == (
            "The Last Lighthouse Keeper"
        )
        assert len(result.log) == 8

        agent_phases = [(e["agent_name"], e["phase"]) for e in result.log]
        assert ("series_producer", "phase_a") in agent_phases
        assert ("producer", "briefing") in agent_phases
        assert ("researcher", "research") in agent_phases

        assert mock_client.chat.completions.create.call_count == 8


class TestFullPipelineWithRework:
    """Full pipeline where SP requests rework on the researcher, then approves."""

    def test_full_pipeline_with_rework(self, mock_config: dict) -> None:
        """Run pipeline where SP Phase B requests researcher rework."""
        mock_responses = [
            _make_simple_response(SP_PHASE_A_RESPONSE),
            _make_simple_response(PRODUCER_BRIEFS_RESPONSE),
            _make_simple_response(RESEARCH_RESPONSE),
            _make_simple_response(DIRECTOR_RESPONSE),
            _make_simple_response(PM_RESPONSE),
            _make_simple_response(COLLATION_RESPONSE),
            _make_rework_response("researcher", "Need more detail on automation"),
            _make_simple_response(RESEARCH_RESPONSE),
            _make_simple_response(DIRECTOR_RESPONSE),
            _make_simple_response(PM_RESPONSE),
            _make_simple_response(COLLATION_RESPONSE),
            _make_simple_response(SP_PHASE_B_RESPONSE),
            _make_simple_response(EVIDENCE_RESPONSE),
        ]

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_responses

        with patch("src.core.pipeline.load_config", return_value=mock_config), \
             patch("src.core.pipeline.create_client", return_value=mock_client), \
             patch("time.sleep"):
            orch = Orchestrator(config_path="fake.yaml")
            result = orch.run("A documentary about lighthouse keepers")

        assert result.success is True, f"Pipeline failed: {result.error}"
        assert result.pitch_deck is not None
        assert len(result.log) > 8
        assert mock_client.chat.completions.create.call_count == 13
