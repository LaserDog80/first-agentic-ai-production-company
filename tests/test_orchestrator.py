# tests/test_orchestrator.py
"""Tests for the orchestrator (backward compat) and core pipeline classes."""
import json
import pytest
from unittest.mock import MagicMock, patch
from src.orchestrator import Orchestrator, PipelineResult


def _mock_agent_result(output_dict: dict, tool_calls=None):
    """Create a mock AgentResult."""
    from src.core.agent import AgentResult
    return AgentResult(
        output=json.dumps(output_dict),
        tool_calls=tool_calls or [],
        iterations=1,
        token_usage={"prompt": 100, "completion": 50},
        hit_max_iterations=False,
    )


def _make_orchestrator(mock_config):
    """Helper to create an Orchestrator with mocked config."""
    with patch("src.core.pipeline.create_client"), \
         patch("src.core.pipeline.load_config") as mock_load:
        mock_load.return_value = mock_config
        return Orchestrator(config_path="config.yaml")


def test_orchestrator_init(mock_config):
    """Orchestrator loads config and creates a client."""
    orch = _make_orchestrator(mock_config)
    assert orch is not None


def test_pipeline_result_dataclass():
    """PipelineResult has expected fields."""
    result = PipelineResult()
    assert result.pitch_deck is None
    assert result.success is False
    assert result.log == []
