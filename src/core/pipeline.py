"""Pipeline definition, base class, and discovery system.

Each pipeline is a Python class inheriting from BasePipeline, paired with
a pipeline.yaml that describes its metadata, agents, and steps. The framework
discovers pipelines automatically from the src/pipelines/ directory.
"""

import importlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.core.agent import AgentRuntime, AgentResult
from src.core.schemas import LogEntry, ToolCallLog
from src.provider import create_client, get_model_name, load_config

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Pipeline definition (loaded from YAML)
# ------------------------------------------------------------------

@dataclass
class StepDefinition:
    """A single step in the pipeline, as declared in pipeline.yaml."""

    id: str
    agent: str
    label: str
    description: str = ""
    phase: str = ""
    tools: list[str] = field(default_factory=list)


@dataclass
class InputConfig:
    """Describes the expected user input for a pipeline."""

    type: str = "text"  # text, structured
    label: str = "Input"
    placeholder: str = ""
    max_length: int = 2000


@dataclass
class ReviewConfig:
    """Configuration for review/rework loops."""

    enabled: bool = False
    max_rework_cycles: int = 2
    reviewer_agent: str = ""
    cascade_graph: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class PipelineDefinition:
    """Complete metadata for a pipeline, loaded from pipeline.yaml."""

    id: str
    name: str
    description: str
    category: str = "General"
    version: str = "1.0"
    input_config: InputConfig = field(default_factory=InputConfig)
    agents: dict[str, dict] = field(default_factory=dict)
    steps: list[StepDefinition] = field(default_factory=list)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    output_format: str = "json"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PipelineDefinition":
        """Load a pipeline definition from a YAML file."""
        path = Path(path)
        with open(path) as f:
            data = yaml.safe_load(f)

        input_cfg = InputConfig(**data.get("input", {}))
        review_cfg = ReviewConfig(**data.get("review", {}))
        steps = [StepDefinition(**s) for s in data.get("steps", [])]

        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            category=data.get("category", "General"),
            version=data.get("version", "1.0"),
            input_config=input_cfg,
            agents=data.get("agents", {}),
            steps=steps,
            review=review_cfg,
            output_format=data.get("output_format", "json"),
        )


# ------------------------------------------------------------------
# Pipeline result
# ------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Final result of a pipeline run."""

    output: dict | None = None
    evidence: dict | None = None
    log: list = field(default_factory=list)
    success: bool = False
    error: str | None = None
    output_files: dict[str, Path] = field(default_factory=dict)


# ------------------------------------------------------------------
# Base pipeline class
# ------------------------------------------------------------------

def _strip_markdown_json(text: str) -> str:
    """Strip markdown code fences from JSON output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


class BasePipeline(ABC):
    """Base class for all agent pipelines.

    Provides generic infrastructure: agent execution, logging, event
    emission, JSON parsing/validation, and rework loop support.

    Subclasses implement execute() with their specific step logic.
    """

    def __init__(
        self,
        definition: PipelineDefinition,
        global_config_path: str = "config.yaml",
    ) -> None:
        self.definition = definition
        self.global_config: dict = load_config(global_config_path)
        self.client: Any = create_client(self.global_config)
        self.log: list[LogEntry] = []
        self.rework_count: int = 0
        self._event_callback: Any = None

    @property
    def max_rework_cycles(self) -> int:
        return self.definition.review.max_rework_cycles

    @property
    def agent_timeout(self) -> int:
        return self.global_config.get("pipeline", {}).get(
            "agent_timeout_seconds", 300
        )

    def set_event_callback(self, callback: Any) -> None:
        """Set a callback function for real-time pipeline events."""
        self._event_callback = callback

    def emit(self, event: dict) -> None:
        """Emit an event to the callback if set."""
        if self._event_callback:
            try:
                self._event_callback(event)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, input_text: str) -> PipelineResult:
        """Execute the pipeline. Wraps execute() with error handling."""
        try:
            result = self.execute(input_text)
            result.log = [entry.model_dump() for entry in self.log]
            result.success = True
            return result
        except Exception as exc:
            logger.exception("Pipeline %s failed: %s", self.definition.id, exc)
            return PipelineResult(
                log=[entry.model_dump() for entry in self.log],
                success=False,
                error=str(exc),
            )

    @abstractmethod
    def execute(self, input_text: str) -> PipelineResult:
        """Execute the pipeline steps. Subclasses must implement this.

        Should populate PipelineResult.output and optionally .evidence
        and .output_files. Should NOT set .log or .success (handled by run()).
        """
        ...

    # ------------------------------------------------------------------
    # Agent execution
    # ------------------------------------------------------------------

    def run_agent(
        self,
        name: str,
        system_prompt: str,
        user_message: str,
        tools: list | None = None,
        model_tier: str = "strong",
        max_iterations: int | None = None,
    ) -> AgentResult:
        """Create an AgentRuntime and run it. Retries once on failure."""
        tools = tools or []
        model = get_model_name(self.global_config, model_tier)
        agent_config = self.definition.agents.get(name, {})
        if max_iterations is None:
            max_iterations = agent_config.get("max_iterations", 5)

        for attempt in range(2):
            try:
                runtime = AgentRuntime(
                    name=name,
                    system_prompt=system_prompt,
                    tools=tools,
                    client=self.client,
                    model=model,
                    max_iterations=max_iterations,
                    timeout=self.agent_timeout,
                    event_callback=self._event_callback,
                )
                return runtime.run(user_message)
            except Exception as exc:
                logger.warning(
                    "%s: agent call failed (attempt %d): %s",
                    name, attempt + 1, exc,
                )
                if attempt == 0:
                    time.sleep(1)
                    continue
                return AgentResult(
                    output="{}",
                    tool_calls=[],
                    iterations=0,
                    token_usage={"prompt": 0, "completion": 0},
                    hit_max_iterations=False,
                )

        return AgentResult(  # pragma: no cover
            output="{}",
            tool_calls=[],
            iterations=0,
            token_usage={"prompt": 0, "completion": 0},
            hit_max_iterations=False,
        )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_step(
        self,
        agent_name: str,
        phase: str,
        input_summary: str,
        result: AgentResult,
        duration_ms: int = 0,
    ) -> None:
        """Record a log entry for a completed agent step."""
        tool_call_logs = [
            ToolCallLog(
                tool_name=tc.get("name", "unknown"),
                args_summary=str(tc.get("args", {}))[:200],
                result_summary=str(tc.get("result", {}))[:200],
            )
            for tc in result.tool_calls
        ]

        entry = LogEntry(
            agent_name=agent_name,
            phase=phase,
            timestamp=datetime.now(timezone.utc),
            input_summary=input_summary[:200],
            output_summary=(result.output or "")[:200],
            token_usage=result.token_usage,
            duration_ms=duration_ms,
            tool_calls=tool_call_logs,
            rework_requested=any(
                tc.get("name") == "request_rework" for tc in result.tool_calls
            ),
            rework_target=next(
                (
                    tc.get("args", {}).get("agent")
                    for tc in result.tool_calls
                    if tc.get("name") == "request_rework"
                ),
                None,
            ),
            rework_notes=next(
                (
                    tc.get("args", {}).get("notes")
                    for tc in result.tool_calls
                    if tc.get("name") == "request_rework"
                ),
                None,
            ),
        )
        self.log.append(entry)

    # ------------------------------------------------------------------
    # Parsing and validation
    # ------------------------------------------------------------------

    def parse_and_validate(
        self,
        output: str,
        model_class: type,
        agent_name: str,
        system_prompt: str | None = None,
        user_message: str | None = None,
        tools: list | None = None,
        model_tier: str | None = None,
    ) -> dict:
        """Parse JSON output and validate against a Pydantic model.

        On failure, retries once with a correction prompt. If that also fails,
        returns the raw dict (or empty dict) and logs a warning.
        """
        cleaned = _strip_markdown_json(output)
        error_msg: str | None = None

        try:
            data = json.loads(cleaned)
            model_class.model_validate(data)
            return data
        except (json.JSONDecodeError, Exception) as exc:
            error_msg = str(exc)

        if system_prompt and user_message and model_tier:
            correction = (
                f"Your previous output failed validation with this error:\n"
                f"{error_msg}\n\n"
                f"Please return ONLY valid JSON matching the required schema."
            )
            retry_result = self.run_agent(
                name=agent_name,
                system_prompt=system_prompt,
                user_message=f"{user_message}\n\n{correction}",
                tools=tools or [],
                model_tier=model_tier,
            )
            retry_cleaned = _strip_markdown_json(retry_result.output)
            try:
                data = json.loads(retry_cleaned)
                model_class.model_validate(data)
                return data
            except (json.JSONDecodeError, Exception) as exc2:
                logger.warning(
                    "%s: retry also failed validation (%s). Accepting raw output.",
                    agent_name, exc2,
                )
                try:
                    return json.loads(retry_cleaned)
                except json.JSONDecodeError:
                    return {}

        logger.warning(
            "%s: parse/validation failed (%s) and no retry context. "
            "Accepting raw output.",
            agent_name, error_msg,
        )
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

    # ------------------------------------------------------------------
    # Utility: timed agent step
    # ------------------------------------------------------------------

    def run_agent_step(
        self,
        name: str,
        phase: str,
        system_prompt: str,
        user_message: str,
        tools: list | None = None,
        model_tier: str = "strong",
        step_num: int | None = None,
        total_steps: int | None = None,
        start_message: str = "",
        done_message: str = "",
        validate_schema: type | None = None,
    ) -> tuple[AgentResult, dict | None]:
        """Run an agent step with timing, logging, events, and optional validation.

        Returns (AgentResult, validated_dict or None).
        """
        if start_message:
            event = {
                "type": "agent_start",
                "agent": name,
                "phase": phase,
                "message": start_message,
            }
            if step_num is not None:
                event["step"] = step_num
            if total_steps is not None:
                event["total_steps"] = total_steps
            self.emit(event)

        start = time.time()
        result = self.run_agent(
            name=name,
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
            model_tier=model_tier,
        )
        duration_ms = int((time.time() - start) * 1000)
        self.log_step(name, phase, user_message[:200], result, duration_ms)

        validated = None
        if validate_schema:
            validated = self.parse_and_validate(
                result.output, validate_schema, name,
                system_prompt=system_prompt,
                user_message=user_message,
                tools=tools,
                model_tier=model_tier,
            )

        if done_message:
            self.emit({
                "type": "agent_done",
                "agent": name,
                "phase": phase,
                "message": done_message,
            })

        return result, validated


# ------------------------------------------------------------------
# Pipeline discovery
# ------------------------------------------------------------------

_pipeline_cache: dict[str, tuple[PipelineDefinition, type]] = {}


def discover_pipelines() -> dict[str, PipelineDefinition]:
    """Discover all available pipelines from src/pipelines/.

    Each pipeline directory must contain pipeline.yaml and pipeline.py
    with a class inheriting from BasePipeline.
    """
    pipelines_dir = Path(__file__).parent.parent / "pipelines"
    results: dict[str, PipelineDefinition] = {}

    if not pipelines_dir.exists():
        return results

    for subdir in sorted(pipelines_dir.iterdir()):
        if not subdir.is_dir():
            continue
        yaml_path = subdir / "pipeline.yaml"
        if not yaml_path.exists():
            continue

        try:
            definition = PipelineDefinition.from_yaml(yaml_path)
            results[definition.id] = definition

            # Also cache the pipeline class
            module_name = f"src.pipelines.{subdir.name}.pipeline"
            module = importlib.import_module(module_name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePipeline)
                    and attr is not BasePipeline
                ):
                    _pipeline_cache[definition.id] = (definition, attr)
                    break
        except Exception as exc:
            logger.warning("Failed to load pipeline from %s: %s", subdir, exc)

    return results


def create_pipeline(
    pipeline_id: str,
    global_config_path: str = "config.yaml",
) -> BasePipeline:
    """Create an instance of the specified pipeline.

    Raises KeyError if the pipeline ID is not found.
    """
    if not _pipeline_cache:
        discover_pipelines()

    if pipeline_id not in _pipeline_cache:
        raise KeyError(
            f"Unknown pipeline: {pipeline_id}. "
            f"Available: {list(_pipeline_cache.keys())}"
        )

    definition, pipeline_class = _pipeline_cache[pipeline_id]
    return pipeline_class(
        definition=definition,
        global_config_path=global_config_path,
    )
