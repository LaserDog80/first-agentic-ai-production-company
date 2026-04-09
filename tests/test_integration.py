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


def _make_approve_response() -> MagicMock:
    """Create a mock API response that calls the approve tool + returns pitch deck."""
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
        """Run the happy-path pipeline end-to-end with mocked API responses.

        Call sequence (9 API calls total):
          1. SP Phase A (no tools)         -> simple response
          2. Producer Briefing (no tools)  -> simple response
          3. Researcher (has web_search)   -> simple response (no tool use)
          4. Director (has ref_research)   -> simple response (no tool use)
          5. PM (has lookup_rates)         -> simple response (no tool use)
          6. Producer Collation (flag_gap) -> simple response (no tool use)
          7. SP Phase B (no tools)         -> PitchDeck JSON (implicit approval)
          8. Evidence (no tools)           -> simple response
        """
        mock_responses = [
            _make_simple_response(SP_PHASE_A_RESPONSE),         # 1 SP Phase A
            _make_simple_response(PRODUCER_BRIEFS_RESPONSE),    # 2 Producer Briefing
            _make_simple_response(RESEARCH_RESPONSE),           # 3 Researcher
            _make_simple_response(DIRECTOR_RESPONSE),           # 4 Director
            _make_simple_response(PM_RESPONSE),                 # 5 PM
            _make_simple_response(COLLATION_RESPONSE),          # 6 Producer Collation
            _make_simple_response(SP_PHASE_B_RESPONSE),         # 7 SP Phase B (PitchDeck)
            _make_simple_response(EVIDENCE_RESPONSE),           # 8 Evidence
        ]

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_responses

        with patch("src.orchestrator.load_config", return_value=mock_config), \
             patch("src.orchestrator.create_client", return_value=mock_client), \
             patch("time.sleep"):
            orch = Orchestrator(config_path="fake.yaml")
            result = orch.run("A documentary about lighthouse keepers")

        # Pipeline should succeed
        assert result.success is True, f"Pipeline failed: {result.error}"

        # Pitch deck should be populated
        assert result.pitch_deck is not None
        assert result.pitch_deck["title_page"]["working_title"] == (
            "The Last Lighthouse Keeper"
        )
        assert result.pitch_deck["logline"] == (
            "A vanishing way of life, told through the last men to keep the light."
        )

        # Log should have entries for all pipeline steps
        # Steps: sp_phase_a, briefing, research, treatment, feasibility,
        #        collation, phase_b, evidence = 8 log entries
        assert len(result.log) == 8

        # Verify agent names in log
        agent_phases = [(e["agent_name"], e["phase"]) for e in result.log]
        assert ("series_producer", "phase_a") in agent_phases
        assert ("producer", "briefing") in agent_phases
        assert ("researcher", "research") in agent_phases
        assert ("director", "treatment") in agent_phases
        assert ("production_manager", "feasibility") in agent_phases
        assert ("producer", "collation") in agent_phases
        assert ("series_producer", "phase_b") in agent_phases
        assert ("evidence_generator", "evidence") in agent_phases

        # No rework should have occurred
        assert orch.rework_count == 0

        # All 8 API calls should have been made
        assert mock_client.chat.completions.create.call_count == 8


class TestFullPipelineWithRework:
    """Full pipeline where SP requests rework on the researcher, then approves."""

    def test_full_pipeline_with_rework(self, mock_config: dict) -> None:
        """Run pipeline where SP Phase B requests researcher rework.

        Rework on researcher cascades to: director, PM, producer_collation.
        Then SP Phase B runs again and approves.

        Call sequence (15 API calls total):
          1.  SP Phase A                     -> simple
          2.  Producer Briefing              -> simple
          3.  Researcher                     -> simple
          4.  Director                       -> simple
          5.  PM                             -> simple
          6.  Producer Collation             -> simple
          7.  SP Phase B call 1 (rework)     -> rework tool call
          8.  SP Phase B call 2 (after tool) -> final content
          --- rework cascade ---
          9.  Researcher (re-run)            -> simple
          10. Director (cascade)             -> simple
          11. PM (cascade)                   -> simple
          12. Producer Collation (cascade)   -> simple
          --- second SP Phase B ---
          13. SP Phase B call 1 (approve)    -> approve tool call
          14. SP Phase B call 2 (final)      -> simple
          15. Evidence                       -> simple
        """
        mock_responses = [
            # Initial pipeline (steps 1-6)
            _make_simple_response(SP_PHASE_A_RESPONSE),         # 1
            _make_simple_response(PRODUCER_BRIEFS_RESPONSE),    # 2
            _make_simple_response(RESEARCH_RESPONSE),           # 3
            _make_simple_response(DIRECTOR_RESPONSE),           # 4
            _make_simple_response(PM_RESPONSE),                 # 5
            _make_simple_response(COLLATION_RESPONSE),          # 6
            # SP Phase B - rework (JSON-based, 1 call)
            _make_rework_response(
                "researcher", "Need more detail on automation history",
            ),                                                  # 7
            # Rework cascade (calls 8-11)
            _make_simple_response(RESEARCH_RESPONSE),           # 8
            _make_simple_response(DIRECTOR_RESPONSE),           # 9
            _make_simple_response(PM_RESPONSE),                 # 10
            _make_simple_response(COLLATION_RESPONSE),          # 11
            # SP Phase B - approve (JSON PitchDeck, 1 call)
            _make_simple_response(SP_PHASE_B_RESPONSE),         # 12
            # Evidence (call 13)
            _make_simple_response(EVIDENCE_RESPONSE),           # 13
        ]

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_responses

        with patch("src.orchestrator.load_config", return_value=mock_config), \
             patch("src.orchestrator.create_client", return_value=mock_client), \
             patch("time.sleep"):
            orch = Orchestrator(config_path="fake.yaml")
            result = orch.run("A documentary about lighthouse keepers")

        # Pipeline should succeed
        assert result.success is True, f"Pipeline failed: {result.error}"

        # Pitch deck should be populated
        assert result.pitch_deck is not None
        assert result.pitch_deck["title_page"]["working_title"] == (
            "The Last Lighthouse Keeper"
        )

        # Rework should have happened once
        assert orch.rework_count == 1

        # More log entries than no-rework path
        assert len(result.log) > 8

        # All 15 API calls should have been made
        assert mock_client.chat.completions.create.call_count == 13


class TestProducerBriefingValidation:
    """Producer briefing step is resilient to malformed LLM output."""

    def test_producer_briefing_retries_on_missing_key(
        self, mock_config: dict
    ) -> None:
        """Regression test: if the Producer's first response is missing the
        required `research_brief` key, the pipeline should retry via
        `_parse_and_validate` rather than crashing with KeyError.

        This reproduces the intermittent `Pipeline error: 'research_brief'`
        crash that occurred when the LLM occasionally deviated from the
        required JSON schema.
        """
        # Malformed first response: missing the `research_brief` key entirely.
        malformed = json.dumps({
            "director_brief": {
                "topic": "The Last Lighthouse Keeper",
                "creative_steer": "Intimate, observational",
                "tone_guidance": "Warm, cinematic, unhurried",
                "key_questions": ["What does a day look like?"],
                "quality_bar": "Visually compelling treatment",
            },
            "pm_brief": {
                "topic": "The Last Lighthouse Keeper",
                "format": {
                    "series_length": "3x60",
                    "genre": "factual",
                    "tone": "warm",
                },
                "known_requirements": ["Remote island location"],
                "quality_bar": "Realistic feasibility assessment",
            },
        })

        mock_responses = [
            _make_simple_response(SP_PHASE_A_RESPONSE),         # 1 SP Phase A
            _make_simple_response(malformed),                   # 2 Producer (bad)
            _make_simple_response(PRODUCER_BRIEFS_RESPONSE),    # 2b Producer retry
            _make_simple_response(RESEARCH_RESPONSE),           # 3 Researcher
            _make_simple_response(DIRECTOR_RESPONSE),           # 4 Director
            _make_simple_response(PM_RESPONSE),                 # 5 PM
            _make_simple_response(COLLATION_RESPONSE),          # 6 Collation
            _make_simple_response(SP_PHASE_B_RESPONSE),         # 7 SP Phase B
            _make_simple_response(EVIDENCE_RESPONSE),           # 8 Evidence
        ]

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_responses

        with patch("src.orchestrator.load_config", return_value=mock_config), \
             patch("src.orchestrator.create_client", return_value=mock_client), \
             patch("time.sleep"):
            orch = Orchestrator(config_path="fake.yaml")
            result = orch.run("A documentary about lighthouse keepers")

        # Pipeline should recover via retry, not crash with KeyError.
        assert result.success is True, f"Pipeline failed: {result.error}"
        assert result.pitch_deck is not None

        # The retry should have caused one extra Producer call (9 total).
        assert mock_client.chat.completions.create.call_count == 9
