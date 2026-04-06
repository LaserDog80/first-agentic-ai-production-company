"""Generic logging and evidence schemas used across all pipelines."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class ToolCallLog(BaseModel):
    """Record of a single tool invocation."""

    tool_name: str
    args_summary: str
    result_summary: str


class LogEntry(BaseModel):
    """Record of a single pipeline step execution."""

    agent_name: str
    phase: str
    timestamp: datetime
    input_summary: str
    output_summary: str
    token_usage: dict
    duration_ms: int
    tool_calls: list[ToolCallLog]
    rework_requested: bool = False
    rework_target: str | None = None
    rework_notes: str | None = None


class EvidenceStep(BaseModel):
    """Summary of a single step in the evidence trail."""

    agent_name: str
    phase: str
    what_received: str
    what_produced: str
    tools_used: list[str]
    duration_ms: int


class EvidencePack(BaseModel):
    """Full evidence trail for pipeline auditability."""

    pipeline_summary: str
    steps: list[EvidenceStep]
    total_duration_ms: int
    total_tokens: dict
    rework_count: int
    rework_details: list[str]
