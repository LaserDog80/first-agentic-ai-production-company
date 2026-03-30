"""Orchestrator — runs the full multi-agent pipeline from brief to pitch deck."""
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

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
from src.pixel_art_llm import render_deck_imagery


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


def _strip_markdown_json(text: str) -> str:
    """Strip markdown code fences from JSON output."""
    text = text.strip()
    if text.startswith("```"):
        # Remove first line (```json or ```)
        lines = text.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # remove closing fence
        text = "\n".join(lines)
    return text.strip()


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
        self.agent_timeout: int = self.config["pipeline"].get(
            "agent_timeout_seconds", 60
        )
        self._event_callback: Any = None

    def set_event_callback(self, callback: Any) -> None:
        """Set a callback function for real-time pipeline events."""
        self._event_callback = callback

    def _emit(self, event: dict) -> None:
        """Emit an event to the callback if set."""
        if self._event_callback:
            try:
                self._event_callback(event)
            except Exception:
                pass

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
        self._emit({
            "type": "agent_start",
            "agent": "series_producer",
            "phase": "phase_a",
            "step": 1,
            "total_steps": 9,
            "message": "Reading the brief and shaping editorial vision...",
        })
        start = time.time()
        sp_a_result = self._run_agent(
            name="series_producer",
            system_prompt=series_producer.build_phase_a_prompt(),
            user_message=brief,
            tools=[],
            model_tier=self.config["agents"]["series_producer"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self._log_step("series_producer", "phase_a", brief, sp_a_result,
                        duration_ms=duration_ms)
        producer_brief = self._parse_and_validate(
            sp_a_result.output, ProducerBrief, "series_producer",
            system_prompt=series_producer.build_phase_a_prompt(),
            user_message=brief,
            tools=[],
            model_tier=self.config["agents"]["series_producer"]["model_tier"],
        )
        outputs["producer_brief"] = producer_brief
        self._emit({
            "type": "agent_done",
            "agent": "series_producer",
            "phase": "phase_a",
            "message": "Editorial vision set. Producer brief ready.",
        })

        # Step 2 — Producer Briefing: ProducerBrief -> 3 specialist briefs
        self._emit({
            "type": "agent_start",
            "agent": "producer",
            "phase": "briefing",
            "step": 2,
            "total_steps": 9,
            "message": "Creating briefs for the specialist team...",
        })
        start = time.time()
        briefing_result = self._run_agent(
            name="producer",
            system_prompt=producer.build_briefing_prompt(),
            user_message=json.dumps(producer_brief),
            tools=[],
            model_tier=self.config["agents"]["producer"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self._log_step(
            "producer", "briefing",
            json.dumps(producer_brief)[:200], briefing_result,
            duration_ms=duration_ms,
        )
        specialist_briefs = json.loads(
            _strip_markdown_json(briefing_result.output)
        )
        outputs["research_brief"] = specialist_briefs["research_brief"]
        outputs["director_brief"] = specialist_briefs["director_brief"]
        outputs["pm_brief"] = specialist_briefs["pm_brief"]
        self._emit({
            "type": "agent_done",
            "agent": "producer",
            "phase": "briefing",
            "message": "Specialist briefs dispatched to the team.",
        })

        # Step 3 — Researcher: ResearchBrief -> ResearchPack
        self._emit({
            "type": "agent_start",
            "agent": "researcher",
            "phase": "research",
            "step": 3,
            "total_steps": 9,
            "message": "Searching the web for facts, competitors, and locations...",
        })
        outputs = self._run_researcher(outputs)
        self._emit({
            "type": "agent_done",
            "agent": "researcher",
            "phase": "research",
            "message": "Research pack compiled.",
        })

        # Step 3b — Artist: deck_imagery -> rendered pixel art (invisible to user)
        outputs = self._run_artist(outputs)

        # Step 4 — Director: DirectorBrief + ResearchPack -> CreativeTreatment
        self._emit({
            "type": "agent_start",
            "agent": "director",
            "phase": "treatment",
            "step": 4,
            "total_steps": 9,
            "message": "Crafting the narrative arc and visual style...",
        })
        outputs = self._run_director(outputs)
        self._emit({
            "type": "agent_done",
            "agent": "director",
            "phase": "treatment",
            "message": "Creative treatment complete.",
        })

        # Step 5 — PM: PMBrief + ResearchPack + CreativeTreatment -> Feasibility
        self._emit({
            "type": "agent_start",
            "agent": "production_manager",
            "phase": "feasibility",
            "step": 5,
            "total_steps": 9,
            "message": "Calculating budget, crew, and logistics...",
        })
        outputs = self._run_production_manager(outputs)
        self._emit({
            "type": "agent_done",
            "agent": "production_manager",
            "phase": "feasibility",
            "message": "Feasibility assessment done.",
        })

        # Step 6 — Producer Collation: all outputs -> EpisodePackage
        self._emit({
            "type": "agent_start",
            "agent": "producer",
            "phase": "collation",
            "step": 6,
            "total_steps": 9,
            "message": "Collating all outputs into episode package...",
        })
        outputs = self._run_producer_collation(outputs)
        self._emit({
            "type": "agent_done",
            "agent": "producer",
            "phase": "collation",
            "message": "Episode package assembled.",
        })

        # Step 7 — SP Phase B (with rework loop)
        self._emit({
            "type": "agent_start",
            "agent": "series_producer",
            "phase": "phase_b",
            "step": 7,
            "total_steps": 9,
            "message": "Reviewing the episode package...",
        })
        outputs = self._run_sp_phase_b_loop(outputs)
        self._emit({
            "type": "agent_done",
            "agent": "series_producer",
            "phase": "phase_b",
            "message": "Pitch deck approved!",
        })

        # Step 9 — Evidence: Log -> EvidencePack
        self._emit({
            "type": "status",
            "step": 9,
            "total_steps": 9,
            "message": "Generating evidence trail...",
        })
        outputs = self._run_evidence(outputs)

        return outputs

    def _run_researcher(self, outputs: dict) -> dict:
        """Step 3: Researcher produces a ResearchPack."""
        start = time.time()
        research_result = self._run_agent(
            name="researcher",
            system_prompt=researcher.build_prompt(),
            user_message=json.dumps(outputs["research_brief"]),
            tools=[web_search],
            model_tier=self.config["agents"]["researcher"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self._log_step(
            "researcher", "research",
            json.dumps(outputs["research_brief"])[:200], research_result,
            duration_ms=duration_ms,
        )
        research_pack = self._parse_and_validate(
            research_result.output, ResearchPack, "researcher",
            system_prompt=researcher.build_prompt(),
            user_message=json.dumps(outputs["research_brief"]),
            tools=[web_search],
            model_tier=self.config["agents"]["researcher"]["model_tier"],
        )
        outputs["research_pack"] = research_pack
        return outputs

    def _run_artist(self, outputs: dict) -> dict:
        """Step 3b: Artist renders deck imagery as pixel art.

        Runs silently — no step counter increment, invisible to the user.
        Falls back to procedural rendering if LLM fails.
        """
        research_pack = outputs.get("research_pack", {})
        deck_imagery = research_pack.get("deck_imagery", [])
        if not deck_imagery:
            outputs["rendered_imagery"] = {}
            return outputs

        self._emit({
            "type": "agent_start",
            "agent": "artist",
            "phase": "rendering",
            "message": "Rendering bespoke pixel art for the deck...",
        })

        # Get genre/tone from the producer brief
        producer_brief = outputs.get("producer_brief", {})
        fmt = producer_brief.get("format", {})
        genre = fmt.get("genre", "") if isinstance(fmt, dict) else ""
        tone = fmt.get("tone", "") if isinstance(fmt, dict) else ""

        artist_model = get_model_name(
            self.config,
            self.config["agents"].get("artist", {}).get("model_tier", "utility"),
        )

        rendered = render_deck_imagery(
            deck_imagery=deck_imagery,
            genre=genre,
            tone=tone,
            client=self.client,
            model=artist_model,
            timeout=self.agent_timeout,
            event_callback=self._event_callback,
        )

        outputs["rendered_imagery"] = rendered
        self._emit({
            "type": "agent_done",
            "agent": "artist",
            "phase": "rendering",
            "message": f"Pixel art complete — {len(rendered)} scenes rendered.",
        })
        return outputs

    def _run_director(self, outputs: dict) -> dict:
        """Step 4: Director produces a CreativeTreatment."""
        ref_research = create_reference_research(outputs["research_pack"])
        director_input = json.dumps({
            "director_brief": outputs["director_brief"],
            "research_pack": outputs["research_pack"],
        })
        start = time.time()
        director_result = self._run_agent(
            name="director",
            system_prompt=director.build_prompt(),
            user_message=director_input,
            tools=[ref_research],
            model_tier=self.config["agents"]["director"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self._log_step(
            "director", "treatment",
            director_input[:200], director_result,
            duration_ms=duration_ms,
        )
        treatment = self._parse_and_validate(
            director_result.output, CreativeTreatment, "director",
            system_prompt=director.build_prompt(),
            user_message=director_input,
            tools=[ref_research],
            model_tier=self.config["agents"]["director"]["model_tier"],
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
        start = time.time()
        pm_result = self._run_agent(
            name="production_manager",
            system_prompt=production_manager.build_prompt(),
            user_message=pm_input,
            tools=[lookup_rates],
            model_tier=self.config["agents"]["production_manager"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self._log_step(
            "production_manager", "feasibility",
            pm_input[:200], pm_result,
            duration_ms=duration_ms,
        )
        feasibility = self._parse_and_validate(
            pm_result.output, FeasibilityAssessment, "production_manager",
            system_prompt=production_manager.build_prompt(),
            user_message=pm_input,
            tools=[lookup_rates],
            model_tier=self.config["agents"]["production_manager"]["model_tier"],
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
        start = time.time()
        collation_result = self._run_agent(
            name="producer",
            system_prompt=producer.build_collation_prompt(),
            user_message=collation_input,
            tools=[flag_gap],
            model_tier=self.config["agents"]["producer"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self._log_step(
            "producer", "collation",
            collation_input[:200], collation_result,
            duration_ms=duration_ms,
        )
        episode_package = self._parse_and_validate(
            collation_result.output, EpisodePackage, "producer",
            system_prompt=producer.build_collation_prompt(),
            user_message=collation_input,
            tools=[flag_gap],
            model_tier=self.config["agents"]["producer"]["model_tier"],
        )
        outputs["episode_package"] = episode_package
        return outputs

    def _run_sp_phase_b_loop(self, outputs: dict) -> dict:
        """Step 7-8: SP reviews, possibly requests rework, produces PitchDeck.

        SP Phase B uses no tools — the model outputs either a PitchDeck JSON
        (= approval) or a rework request JSON with a 'rework_request' key.
        This avoids tool-calling compatibility issues across models.
        """
        rework_exhausted = False
        while True:
            # Build user message — add constraint if rework cap is hit
            user_msg = json.dumps(outputs["episode_package"])
            if rework_exhausted:
                user_msg += (
                    "\n\nIMPORTANT: You have used all available rework cycles. "
                    "You MUST produce a PitchDeck JSON now with the best "
                    "available material. Note any remaining concerns in the "
                    "'unresolved_concerns' field."
                )

            start = time.time()
            sp_b_result = self._run_agent(
                name="series_producer",
                system_prompt=series_producer.build_phase_b_prompt(),
                user_message=user_msg,
                tools=[],
                model_tier=self.config["agents"]["series_producer"][
                    "model_tier"
                ],
            )
            duration_ms = int((time.time() - start) * 1000)
            self._log_step(
                "series_producer", "phase_b",
                json.dumps(outputs["episode_package"])[:200], sp_b_result,
                duration_ms=duration_ms,
            )

            # Parse the output to check for rework request
            try:
                cleaned = _strip_markdown_json(sp_b_result.output)
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                parsed = {}

            # Check if this is a rework request (has 'rework_request' key)
            if "rework_request" in parsed:
                if self.rework_count < self.max_rework_cycles:
                    rework = parsed["rework_request"]
                    self.rework_count += 1
                    outputs = self._handle_rework(rework, outputs)
                    continue
                else:
                    # Cap hit — force the SP to produce a PitchDeck
                    rework_exhausted = True
                    continue

            # Treat as approval — validate as PitchDeck
            pitch_deck = self._parse_and_validate(
                sp_b_result.output, PitchDeck, "series_producer",
                system_prompt=series_producer.build_phase_b_prompt(),
                user_message=json.dumps(outputs["episode_package"]),
                tools=[],
                model_tier=self.config["agents"]["series_producer"][
                    "model_tier"
                ],
            )
            # Inject deck_imagery and pre-rendered pixel art from earlier steps
            research_pack = outputs.get("research_pack", {})
            imagery = research_pack.get("deck_imagery", [])
            if imagery:
                pitch_deck["deck_imagery"] = imagery
            rendered = outputs.get("rendered_imagery", {})
            if rendered:
                pitch_deck["rendered_imagery"] = rendered
            outputs["pitch_deck"] = pitch_deck
            break

        return outputs

    def _run_evidence(self, outputs: dict) -> dict:
        """Step 9: Evidence generator summarises the pipeline log."""
        log_data = [entry.model_dump(mode="json") for entry in self.log]
        start = time.time()
        evidence_result = self._run_agent(
            name="series_producer",  # utility model, uses SP config as fallback
            system_prompt=evidence.build_prompt(),
            user_message=json.dumps(log_data),
            tools=[],
            model_tier="utility",
        )
        duration_ms = int((time.time() - start) * 1000)
        self._log_step(
            "evidence_generator", "evidence",
            f"Pipeline log ({len(self.log)} entries)", evidence_result,
            duration_ms=duration_ms,
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
        self._emit({
            "type": "rework",
            "target": target,
            "notes": notes,
            "cycle": self.rework_count,
            "message": f"Series Producer requests rework from {target}: {notes[:80]}",
        })

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

        On failure, retries once with a correction prompt that includes the
        validation error. If the second attempt also fails, returns the raw
        dict (or empty dict) and logs a warning.
        """
        cleaned = _strip_markdown_json(output)
        error_msg: str | None = None

        # First attempt
        try:
            data = json.loads(cleaned)
            model_class.model_validate(data)
            return data
        except (json.JSONDecodeError, Exception) as exc:
            error_msg = str(exc)

        # Retry with correction prompt if we have context to re-run
        if system_prompt and user_message and model_tier:
            correction = (
                f"Your previous output failed validation with this error:\n"
                f"{error_msg}\n\n"
                f"Please return ONLY valid JSON matching the required schema."
            )
            retry_result = self._run_agent(
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
                    "%s: retry also failed validation (%s). "
                    "Accepting raw output.",
                    agent_name, exc2,
                )
                try:
                    return json.loads(retry_cleaned)
                except json.JSONDecodeError:
                    return {}

        # No retry context — fall back to raw/empty
        logger.warning(
            "%s: parse/validation failed (%s) and no retry context. "
            "Accepting raw output.",
            agent_name, error_msg,
        )
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}
