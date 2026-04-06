"""Tests for the core framework: pipeline discovery, registry, and schemas."""
import json
from pathlib import Path

import pytest

from src.core.pipeline import (
    PipelineDefinition, PipelineResult, StepDefinition, InputConfig,
    ReviewConfig, discover_pipelines, create_pipeline, _pipeline_cache,
)
from src.core.registry import ToolRegistry, global_registry, register_tool
from src.core.schemas import LogEntry, ToolCallLog, EvidencePack, EvidenceStep
from src.core.agent import AgentRuntime, AgentResult


# --- Pipeline Definition ---

def test_pipeline_definition_from_yaml():
    """Load a pipeline definition from the TV production YAML."""
    path = Path("src/pipelines/tv_production/pipeline.yaml")
    defn = PipelineDefinition.from_yaml(path)
    assert defn.id == "tv_production"
    assert defn.name == "TV Production"
    assert len(defn.steps) > 0
    assert len(defn.agents) > 0
    assert defn.review.enabled is True
    assert defn.review.max_rework_cycles == 2


def test_pipeline_definition_has_input_config():
    """Pipeline definition includes input configuration."""
    path = Path("src/pipelines/tv_production/pipeline.yaml")
    defn = PipelineDefinition.from_yaml(path)
    assert defn.input_config.label == "Commissioning Brief"
    assert defn.input_config.max_length == 2000


def test_step_definition_has_required_fields():
    """StepDefinition has id, agent, and label."""
    step = StepDefinition(id="test", agent="agent1", label="Test Step")
    assert step.id == "test"
    assert step.agent == "agent1"
    assert step.label == "Test Step"


# --- Pipeline Discovery ---

def test_discover_pipelines_finds_all():
    """discover_pipelines() finds all pipeline directories."""
    pipelines = discover_pipelines()
    assert "tv_production" in pipelines
    assert "research_report" in pipelines
    assert "startup_pitch" in pipelines


def test_discover_pipelines_returns_definitions():
    """Each discovered pipeline has a valid PipelineDefinition."""
    pipelines = discover_pipelines()
    for pid, defn in pipelines.items():
        assert isinstance(defn, PipelineDefinition)
        assert defn.id == pid
        assert len(defn.name) > 0
        assert len(defn.description) > 0


# --- Pipeline Result ---

def test_pipeline_result_defaults():
    """PipelineResult has sensible defaults."""
    result = PipelineResult()
    assert result.output is None
    assert result.success is False
    assert result.error is None
    assert result.log == []


# --- Tool Registry ---

def test_tool_registry_register_and_get():
    """Register and retrieve a tool."""
    reg = ToolRegistry()
    def my_tool(x: str) -> dict:
        return {"result": x}
    reg.register("my_tool", my_tool)
    assert reg.has("my_tool")
    assert reg.get("my_tool") is my_tool


def test_tool_registry_get_many():
    """Retrieve multiple tools at once."""
    reg = ToolRegistry()
    def tool_a(): pass
    def tool_b(): pass
    reg.register("a", tool_a)
    reg.register("b", tool_b)
    tools = reg.get_many(["a", "b"])
    assert len(tools) == 2


def test_tool_registry_raises_on_unknown():
    """Unknown tool raises KeyError."""
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.get("nonexistent")


def test_tool_registry_list():
    """list_tools() returns registered names."""
    reg = ToolRegistry()
    reg.register("x", lambda: None)
    reg.register("y", lambda: None)
    assert set(reg.list_tools()) == {"x", "y"}


# --- Core Schemas ---

def test_log_entry_model():
    """LogEntry validates correctly."""
    from datetime import datetime, timezone
    entry = LogEntry(
        agent_name="test",
        phase="test_phase",
        timestamp=datetime.now(timezone.utc),
        input_summary="test input",
        output_summary="test output",
        token_usage={"prompt": 100, "completion": 50},
        duration_ms=1000,
        tool_calls=[],
    )
    assert entry.agent_name == "test"
    assert entry.rework_requested is False


def test_evidence_pack_model():
    """EvidencePack validates correctly."""
    pack = EvidencePack(
        pipeline_summary="Test pipeline",
        steps=[],
        total_duration_ms=5000,
        total_tokens={"prompt": 1000, "completion": 500},
        rework_count=0,
        rework_details=[],
    )
    assert pack.total_duration_ms == 5000


# --- Agent Result ---

def test_agent_result_defaults():
    """AgentResult has sensible defaults."""
    result = AgentResult(output="test")
    assert result.output == "test"
    assert result.tool_calls == []
    assert result.iterations == 0
    assert result.hit_max_iterations is False
