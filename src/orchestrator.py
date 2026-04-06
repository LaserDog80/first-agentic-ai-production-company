"""Backward compatibility — wraps TVProductionPipeline as the original Orchestrator.

Existing code that imports from src.orchestrator will continue to work.
"""
from dataclasses import dataclass, field
from typing import Any

from src.core.pipeline import discover_pipelines, create_pipeline, PipelineResult as _PipelineResult


@dataclass
class PipelineResult:
    """Legacy result format for backward compatibility."""

    pitch_deck: dict | None = None
    evidence: dict | None = None
    log: list = field(default_factory=list)
    success: bool = False
    error: str | None = None


class Orchestrator:
    """Legacy orchestrator wrapping TVProductionPipeline."""

    def __init__(self, config_path: str = "config.yaml") -> None:
        self._config_path = config_path
        self._event_callback: Any = None

    def set_event_callback(self, callback: Any) -> None:
        self._event_callback = callback

    def run(self, brief: str) -> PipelineResult:
        pipeline = create_pipeline("tv_production", global_config_path=self._config_path)
        if self._event_callback:
            pipeline.set_event_callback(self._event_callback)
        result = pipeline.run(brief)
        return PipelineResult(
            pitch_deck=result.output,
            evidence=result.evidence,
            log=result.log,
            success=result.success,
            error=result.error,
        )
