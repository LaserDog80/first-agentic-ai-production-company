# tests/test_orchestrator.py
import json
import pytest
from unittest.mock import MagicMock, patch
from src.orchestrator import Orchestrator, PipelineResult


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
    rework = orch._detect_rework(result)
    assert rework is None


# --- Research-pack guardrail (issue #26) ---

def test_research_pack_is_usable_empty():
    """An empty pack is not usable."""
    assert Orchestrator._research_pack_is_usable({}) is False


def test_research_pack_is_usable_all_empty_lists():
    """Pack with all-empty lists is not usable."""
    pack = {
        "competitive_landscape": [],
        "characters": [],
        "key_facts": [],
        "archive_sources": [],
        "locations": [],
        "risks_and_sensitivities": [],
    }
    assert Orchestrator._research_pack_is_usable(pack) is False


def test_research_pack_is_usable_one_field_populated():
    """A single non-empty core list makes the pack usable."""
    pack = {
        "competitive_landscape": [],
        "characters": [{"name": "X", "role": "y", "access_notes": "",
                        "story_angle": ""}],
        "key_facts": [],
    }
    assert Orchestrator._research_pack_is_usable(pack) is True


def test_research_pack_assert_halts_on_empty(mock_config):
    """_assert_research_pack_usable raises RuntimeError on empty pack."""
    orch = _make_orchestrator(mock_config)
    with pytest.raises(RuntimeError, match="empty/unusable ResearchPack"):
        orch._assert_research_pack_usable({})
