"""Orchestrator — runs the full multi-agent pipeline from brief to pitch deck."""
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.provider import load_config, create_client, get_model_name
from src.agent import AgentRuntime, AgentResult
from src.schemas import (
    ProducerBrief, ResearchPack, CreativeTreatment, FeasibilityAssessment,
    EpisodePackage, PitchDeck, LogEntry, ToolCallLog, EvidencePack,
)
from src.tools import get_openai_tools_schema, execute_tool
from src.tools.search import web_search
from src.tools.rework import request_rework, approve, flag_gap
from src.tools.research import create_reference_research
from src.tools.rates import lookup_rates
from src.prompts import (
    series_producer, producer, researcher, director,
    production_manager, evidence,
)


@dataclass
class PipelineResult:
    """Final result of a full pipeline run."""

    pitch_deck: dict | None = None
    evidence: dict | None = None
    log: list = field(default_factory=list)
    success: bool = False
    error: str | None = None


# Cascade dependency graph: re-running an agent triggers downstream re-runs.
CASCADE_GRAPH: dict[str, list[str]] = {
    "researcher": ["director", "production_manager", "producer_collation"],
    "director": ["producer_collation"],
    "production_manager": ["producer_collation"],
}


class Orchestrator:
    """Runs the full multi-agent pipeline: brief in, pitch deck out.

    Steps:
    1. SP Phase A: one-line brief -> ProducerBrief
    2. Producer Briefing: ProducerBrief -> 3 specialist briefs
    3. Researcher: ResearchBrief -> ResearchPack (web_search)
    4. Director: DirectorBrief + ResearchPack -> CreativeTreatment
    5. PM: PMBrief + ResearchPack + CreativeTreatment -> FeasibilityAssessment
    6. Producer Collation: all outputs -> EpisodePackage (flag_gap)
    7. SP Phase B: EpisodePackage -> approve/request_rework -> PitchDeck
    8. If rework: re-run target + cascades, loop back to SP Phase B (max 2)
    9. Evidence: Log -> EvidencePack
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        self.config: dict = load_config(config_path)
        self.client: Any = create_client(self.config)
        self.log: list[LogEntry] = []
        self.rework_count: int = 0
        self.max_rework_cycles: int = self.config["pipeline"]["max_rework_cycles"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, brief: str) -> PipelineResult:
        """Execute the full pipeline for a one-line commissioning brief."""
        try:
            outputs = self._run_pipeline(brief)
            return PipelineResult(
                pitch_deck=outputs.get("pitch_deck"),
                evidence=outputs.get("evidence"),
                log=[entry.model_dump() for entry in self.log],
                success=True,
            )
        except Exception as exc:
            return PipelineResult(
                log=[entry.model_dump() for entry in self.log],
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _run_pipeline(self, brief: str) -> dict:
        """Internal pipeline implementation."""
        outputs: dict[str, Any] = {"brief": brief}

        # Step 1 — SP Phase A: brief -> ProducerBrief
        sp_a_result = self._run_agent(
            name="series_producer",
            system_prompt=series_producer.build_phase_a_prompt(),
            user_message=brief,
            tools=[],
            model_tier=self.config["agents"]["series_producer"]["model_tier"],
        )
        self._log_step("series_producer", "phase_a", brief, sp_a_result)
        producer_brief = self._parse_and_validate(
            sp_a_result.output, ProducerBrief, "series_producer",
        )
        outputs["producer_brief"] = producer_brief

        # Step 2 — Producer Briefing: ProducerBrief -> 3 specialist briefs
        briefing_result = self._run_agent(
            name="producer",
            system_prompt=producer.build_briefing_prompt(),
            user_message=json.dumps(producer_brief),
            tools=[],
            model_tier=self.config["agents"]["producer"]["model_tier"],
        )
        self._log_step(
            "producer", "briefing",
            json.dumps(producer_brief)[:200], briefing_result,
        )
        specialist_briefs = json.loads(briefing_result.output)
        outputs["research_brief"] = specialist_briefs["research_brief"]
        outputs["director_brief"] = specialist_briefs["director_brief"]
        outputs["pm_brief"] = specialist_briefs["pm_brief"]

        # Step 3 — Researcher: ResearchBrief -> ResearchPack
        outputs = self._run_researcher(outputs)

        # Step 4 — Director: DirectorBrief + ResearchPack -> CreativeTreatment
        outputs = self._run_director(outputs)

        # Step 5 — PM: PMBrief + ResearchPack + CreativeTreatment -> Feasibility
        outputs = self._run_production_manager(outputs)

        # Step 6 — Producer Collation: all outputs -> EpisodePackage
        outputs = self._run_producer_collation(outputs)

        # Step 7 — SP Phase B (with rework loop)
        outputs = self._run_sp_phase_b_loop(outputs)

        # Step 9 — Evidence: Log -> EvidencePack
        outputs = self._run_evidence(outputs)

        return outputs

    def _run_researcher(self, outputs: dict) -> dict:
        """Step 3: Researcher produces a ResearchPack."""
        research_result = self._run_agent(
            name="researcher",
            system_prompt=researcher.build_prompt(),
            user_message=json.dumps(outputs["research_brief"]),
            tools=[web_search],
            model_tier=self.config["agents"]["researcher"]["model_tier"],
        )
        self._log_step(
            "researcher", "research",
            json.dumps(outputs["research_brief"])[:200], research_result,
        )
        research_pack = self._parse_and_validate(
            research_result.output, ResearchPack, "researcher",
        )
        outputs["research_pack"] = research_pack
        return outputs

    def _run_director(self, outputs: dict) -> dict:
        """Step 4: Director produces a CreativeTreatment."""
        ref_research = create_reference_research(outputs["research_pack"])
        director_input = json.dumps({
            "director_brief": outputs["director_brief"],
            "research_pack": outputs["research_pack"],
        })
        director_result = self._run_agent(
            name="director",
            system_prompt=director.build_prompt(),
            user_message=director_input,
            tools=[ref_research],
            model_tier=self.config["agents"]["director"]["model_tier"],
        )
        self._log_step(
            "director", "treatment",
            director_input[:200], director_result,
        )
        treatment = self._parse_and_validate(
            director_result.output, CreativeTreatment, "director",
        )
        outputs["treatment"] = treatment
        return outputs

    def _run_production_manager(self, outputs: dict) -> dict:
        """Step 5: PM produces a FeasibilityAssessment."""
        pm_input = json.dumps({
            "pm_brief": outputs["pm_brief"],
            "research_pack": outputs["research_pack"],
            "creative_treatment": outputs["treatment"],
        })
        pm_result = self._run_agent(
            name="production_manager",
            system_prompt=production_manager.build_prompt(),
            user_message=pm_input,
            tools=[lookup_rates],
            model_tier=self.config["agents"]["production_manager"]["model_tier"],
        )
        self._log_step(
            "production_manager", "feasibility",
            pm_input[:200], pm_result,
        )
        feasibility = self._parse_and_validate(
            pm_result.output, FeasibilityAssessment, "production_manager",
        )
        outputs["feasibility"] = feasibility
        return outputs

    def _run_producer_collation(self, outputs: dict) -> dict:
        """Step 6: Producer collates all outputs into an EpisodePackage."""
        collation_input = json.dumps({
            "sp_brief": outputs["producer_brief"],
            "research": outputs["research_pack"],
            "treatment": outputs["treatment"],
            "feasibility": outputs["feasibility"],
        })
        collation_result = self._run_agent(
            name="producer",
            system_prompt=producer.build_collation_prompt(),
            user_message=collation_input,
            tools=[flag_gap],
            model_tier=self.config["agents"]["producer"]["model_tier"],
        )
        self._log_step(
            "producer", "collation",
            collation_input[:200], collation_result,
        )
        episode_package = self._parse_and_validate(
            collation_result.output, EpisodePackage, "producer",
        )
        outputs["episode_package"] = episode_package
        return outputs

    def _run_sp_phase_b_loop(self, outputs: dict) -> dict:
        """Step 7-8: SP reviews, possibly requests rework, produces PitchDeck."""
        while True:
            sp_b_result = self._run_agent(
                name="series_producer",
                system_prompt=series_producer.build_phase_b_prompt(),
                user_message=json.dumps(outputs["episode_package"]),
                tools=[approve, request_rework],
                model_tier=self.config["agents"]["series_producer"]["model_tier"],
            )
            self._log_step(
                "series_producer", "phase_b",
                json.dumps(outputs["episode_package"])[:200], sp_b_result,
            )

            rework = self._detect_rework(sp_b_result)
            if rework is not None:
                self.rework_count += 1
                outputs = self._handle_rework(rework, outputs)
                # Loop back to SP Phase B
                continue

            # Approved — parse the PitchDeck
            pitch_deck = self._parse_and_validate(
                sp_b_result.output, PitchDeck, "series_producer",
            )
            outputs["pitch_deck"] = pitch_deck
            break

        return outputs

    def _run_evidence(self, outputs: dict) -> dict:
        """Step 9: Evidence generator summarises the pipeline log."""
        log_data = [entry.model_dump(mode="json") for entry in self.log]
        evidence_result = self._run_agent(
            name="series_producer",  # utility model, uses SP config as fallback
            system_prompt=evidence.build_prompt(),
            user_message=json.dumps(log_data),
            tools=[],
            model_tier="utility",
        )
        self._log_step(
            "evidence_generator", "evidence",
            f"Pipeline log ({len(self.log)} entries)", evidence_result,
        )
        try:
            evidence_pack = self._parse_and_validate(
                evidence_result.output, EvidencePack, "evidence_generator",
            )
            outputs["evidence"] = evidence_pack
        except Exception:
            # Evidence is non-critical; don't fail the pipeline
            outputs["evidence"] = None
        return outputs

    # ------------------------------------------------------------------
    # Agent execution
    # ------------------------------------------------------------------

    def _run_agent(
        self,
        name: str,
        system_prompt: str,
        user_message: str,
        tools: list,
        model_tier: str,
    ) -> AgentResult:
        """Create an AgentRuntime and run it. Retries once on failure."""
        model = get_model_name(self.config, model_tier)
        agent_config = self.config["agents"].get(name, {})
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
                )
                return runtime.run(user_message)
            except Exception:
                if attempt == 0:
                    time.sleep(1)
                    continue
                # Second failure — return placeholder
                return AgentResult(
                    output="{}",
                    tool_calls=[],
                    iterations=0,
                    token_usage={"prompt": 0, "completion": 0},
                    hit_max_iterations=False,
                )
        # Should not reach here, but satisfy type checker
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

    def _log_step(
        self,
        agent_name: str,
        phase: str,
        input_summary: str,
        result: AgentResult,
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
            duration_ms=0,  # Not tracked per-step in this implementation
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
    # Rework detection and handling
    # ------------------------------------------------------------------

    def _detect_rework(self, result: AgentResult) -> dict | None:
        """Check if the SP requested rework. Returns rework dict or None."""
        for tc in result.tool_calls:
            if tc.get("name") == "request_rework":
                if self.rework_count < self.max_rework_cycles:
                    return tc.get("args", {})
                # Cap hit — ignore the rework request
                return None
        return None

    def _handle_rework(self, rework: dict, outputs: dict) -> dict:
        """Re-run the target agent with rework notes, then cascade."""
        target = rework.get("agent", "")
        notes = rework.get("notes", "")

        # Re-run the target agent
        if target == "researcher":
            # Append rework notes to the research brief
            augmented_brief = dict(outputs["research_brief"])
            augmented_brief["rework_notes"] = notes
            outputs["research_brief"] = augmented_brief
            outputs = self._run_researcher(outputs)
        elif target == "director":
            augmented_brief = dict(outputs["director_brief"])
            augmented_brief["rework_notes"] = notes
            outputs["director_brief"] = augmented_brief
            outputs = self._run_director(outputs)
        elif target == "production_manager":
            augmented_brief = dict(outputs["pm_brief"])
            augmented_brief["rework_notes"] = notes
            outputs["pm_brief"] = augmented_brief
            outputs = self._run_production_manager(outputs)
        elif target == "producer":
            # Re-run collation with notes
            outputs = self._run_producer_collation(outputs)

        # Run cascaded agents
        cascades = CASCADE_GRAPH.get(target, [])
        for cascade_agent in cascades:
            if cascade_agent == "director" and target != "director":
                outputs = self._run_director(outputs)
            elif cascade_agent == "production_manager" and target != "production_manager":
                outputs = self._run_production_manager(outputs)
            elif cascade_agent == "producer_collation":
                outputs = self._run_producer_collation(outputs)

        return outputs

    # ------------------------------------------------------------------
    # Parsing and validation
    # ------------------------------------------------------------------

    def _parse_and_validate(
        self, output: str, model_class: type, agent_name: str,
    ) -> dict:
        """Parse JSON output and validate against a Pydantic model.

        Returns the validated dict. On validation failure, raises ValueError
        (caller may retry with a correction prompt).
        """
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{agent_name} returned invalid JSON: {exc}"
            ) from exc

        # Validate with Pydantic (raises ValidationError on failure)
        model_class.model_validate(data)
        return data
