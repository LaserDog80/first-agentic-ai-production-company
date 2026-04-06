"""TV Production pipeline — full implementation.

Transforms a one-line TV show brief into a broadcast-ready pitch deck
through a multi-agent workflow with research, creative treatment,
feasibility assessment, and editorial review with rework loops.
"""

import json
import logging
from typing import Any

from src.core.pipeline import BasePipeline, PipelineDefinition, PipelineResult, _strip_markdown_json
from src.core.schemas import EvidencePack
from src.pipelines.tv_production import prompts
from src.pipelines.tv_production.schemas import (
    ProducerBrief, ResearchPack, CreativeTreatment,
    FeasibilityAssessment, EpisodePackage, PitchDeck,
)
from src.pipelines.tv_production.tools import (
    lookup_rates, flag_gap, create_reference_research,
)
from src.provider import get_model_name
from src.tools.search import web_search

logger = logging.getLogger(__name__)

# Cascade dependency graph: re-running an agent triggers downstream re-runs.
CASCADE_GRAPH: dict[str, list[str]] = {
    "researcher": ["director", "production_manager", "producer_collation"],
    "director": ["producer_collation"],
    "production_manager": ["producer_collation"],
}


class TVProductionPipeline(BasePipeline):
    """TV Production pipeline: brief -> pitch deck.

    Steps:
    1. SP Phase A: brief -> ProducerBrief
    2. Producer Briefing: ProducerBrief -> 3 specialist briefs
    3. Researcher: ResearchBrief -> ResearchPack (web_search)
    3b. Artist: deck_imagery -> rendered pixel art
    4. Director: DirectorBrief + ResearchPack -> CreativeTreatment
    5. PM: PMBrief + ResearchPack + CreativeTreatment -> Feasibility
    6. Producer Collation: all outputs -> EpisodePackage
    7-8. SP Phase B: review + rework loop -> PitchDeck
    9. Evidence: log -> EvidencePack
    """

    def __init__(
        self,
        definition: PipelineDefinition,
        global_config_path: str = "config.yaml",
    ) -> None:
        super().__init__(definition, global_config_path)
        self._total_steps = 9

    def execute(self, input_text: str) -> PipelineResult:
        """Execute the full TV production pipeline."""
        outputs: dict[str, Any] = {"brief": input_text}

        # Step 1 — SP Phase A
        _, producer_brief = self.run_agent_step(
            name="series_producer", phase="phase_a",
            system_prompt=prompts.series_producer_phase_a(),
            user_message=input_text,
            model_tier=self.definition.agents["series_producer"]["model_tier"],
            step_num=1, total_steps=self._total_steps,
            start_message="Reading the brief and shaping editorial vision...",
            done_message="Editorial vision set. Producer brief ready.",
            validate_schema=ProducerBrief,
        )
        outputs["producer_brief"] = producer_brief

        # Step 2 — Producer Briefing
        result, _ = self.run_agent_step(
            name="producer", phase="briefing",
            system_prompt=prompts.producer_briefing(),
            user_message=json.dumps(producer_brief),
            model_tier=self.definition.agents["producer"]["model_tier"],
            step_num=2, total_steps=self._total_steps,
            start_message="Creating briefs for the specialist team...",
            done_message="Specialist briefs dispatched to the team.",
        )
        specialist_briefs = json.loads(_strip_markdown_json(result.output))
        outputs["research_brief"] = specialist_briefs["research_brief"]
        outputs["director_brief"] = specialist_briefs["director_brief"]
        outputs["pm_brief"] = specialist_briefs["pm_brief"]

        # Step 3 — Researcher
        self.emit({
            "type": "agent_start", "agent": "researcher", "phase": "research",
            "step": 3, "total_steps": self._total_steps,
            "message": "Searching the web for facts, competitors, and locations...",
        })
        outputs = self._run_researcher(outputs)
        self.emit({
            "type": "agent_done", "agent": "researcher", "phase": "research",
            "message": "Research pack compiled.",
        })

        # Step 3b — Artist (pixel art rendering)
        outputs = self._run_artist(outputs)

        # Step 4 — Director
        self.emit({
            "type": "agent_start", "agent": "director", "phase": "treatment",
            "step": 4, "total_steps": self._total_steps,
            "message": "Crafting the narrative arc and visual style...",
        })
        outputs = self._run_director(outputs)
        self.emit({
            "type": "agent_done", "agent": "director", "phase": "treatment",
            "message": "Creative treatment complete.",
        })

        # Step 5 — Production Manager
        self.emit({
            "type": "agent_start", "agent": "production_manager",
            "phase": "feasibility", "step": 5, "total_steps": self._total_steps,
            "message": "Calculating budget, crew, and logistics...",
        })
        outputs = self._run_production_manager(outputs)
        self.emit({
            "type": "agent_done", "agent": "production_manager",
            "phase": "feasibility", "message": "Feasibility assessment done.",
        })

        # Step 6 — Producer Collation
        self.emit({
            "type": "agent_start", "agent": "producer", "phase": "collation",
            "step": 6, "total_steps": self._total_steps,
            "message": "Collating all outputs into episode package...",
        })
        outputs = self._run_producer_collation(outputs)
        self.emit({
            "type": "agent_done", "agent": "producer", "phase": "collation",
            "message": "Episode package assembled.",
        })

        # Step 7-8 — SP Phase B (review + rework loop)
        self.emit({
            "type": "agent_start", "agent": "series_producer",
            "phase": "phase_b", "step": 7, "total_steps": self._total_steps,
            "message": "Reviewing the episode package...",
        })
        outputs = self._run_sp_phase_b_loop(outputs)
        self.emit({
            "type": "agent_done", "agent": "series_producer",
            "phase": "phase_b", "message": "Pitch deck approved!",
        })

        # Step 9 — Evidence
        self.emit({
            "type": "status", "step": 9, "total_steps": self._total_steps,
            "message": "Generating evidence trail...",
        })
        outputs = self._run_evidence(outputs)

        return PipelineResult(
            output=outputs.get("pitch_deck"),
            evidence=outputs.get("evidence"),
        )

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _run_researcher(self, outputs: dict) -> dict:
        """Step 3: Researcher produces a ResearchPack."""
        import time
        start = time.time()
        research_result = self.run_agent(
            name="researcher",
            system_prompt=prompts.researcher(),
            user_message=json.dumps(outputs["research_brief"]),
            tools=[web_search],
            model_tier=self.definition.agents["researcher"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self.log_step(
            "researcher", "research",
            json.dumps(outputs["research_brief"])[:200], research_result,
            duration_ms=duration_ms,
        )
        research_pack = self.parse_and_validate(
            research_result.output, ResearchPack, "researcher",
            system_prompt=prompts.researcher(),
            user_message=json.dumps(outputs["research_brief"]),
            tools=[web_search],
            model_tier=self.definition.agents["researcher"]["model_tier"],
        )
        outputs["research_pack"] = research_pack
        return outputs

    def _run_artist(self, outputs: dict) -> dict:
        """Step 3b: Artist renders deck imagery as pixel art."""
        research_pack = outputs.get("research_pack", {})
        deck_imagery = research_pack.get("deck_imagery", [])
        if not deck_imagery:
            outputs["rendered_imagery"] = {}
            return outputs

        self.emit({
            "type": "agent_start", "agent": "artist", "phase": "rendering",
            "message": "Rendering bespoke pixel art for the deck...",
        })

        producer_brief = outputs.get("producer_brief", {})
        fmt = producer_brief.get("format", {})
        genre = fmt.get("genre", "") if isinstance(fmt, dict) else ""
        tone = fmt.get("tone", "") if isinstance(fmt, dict) else ""

        artist_model = get_model_name(
            self.global_config,
            self.definition.agents.get("artist", {}).get("model_tier", "utility"),
        )

        try:
            from src.pixel_art_llm import render_deck_imagery
            rendered = render_deck_imagery(
                deck_imagery=deck_imagery,
                genre=genre, tone=tone,
                client=self.client, model=artist_model,
                timeout=self.agent_timeout,
                event_callback=self._event_callback,
            )
        except ImportError:
            rendered = {}

        outputs["rendered_imagery"] = rendered
        self.emit({
            "type": "agent_done", "agent": "artist", "phase": "rendering",
            "message": f"Pixel art complete — {len(rendered)} scenes rendered.",
        })
        return outputs

    def _run_director(self, outputs: dict) -> dict:
        """Step 4: Director produces a CreativeTreatment."""
        import time
        ref_research = create_reference_research(outputs["research_pack"])
        director_input = json.dumps({
            "director_brief": outputs["director_brief"],
            "research_pack": outputs["research_pack"],
        })
        start = time.time()
        director_result = self.run_agent(
            name="director",
            system_prompt=prompts.director(),
            user_message=director_input,
            tools=[ref_research],
            model_tier=self.definition.agents["director"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self.log_step(
            "director", "treatment",
            director_input[:200], director_result,
            duration_ms=duration_ms,
        )
        treatment = self.parse_and_validate(
            director_result.output, CreativeTreatment, "director",
            system_prompt=prompts.director(),
            user_message=director_input,
            tools=[ref_research],
            model_tier=self.definition.agents["director"]["model_tier"],
        )
        outputs["treatment"] = treatment
        return outputs

    def _run_production_manager(self, outputs: dict) -> dict:
        """Step 5: PM produces a FeasibilityAssessment."""
        import time
        pm_input = json.dumps({
            "pm_brief": outputs["pm_brief"],
            "research_pack": outputs["research_pack"],
            "creative_treatment": outputs["treatment"],
        })
        start = time.time()
        pm_result = self.run_agent(
            name="production_manager",
            system_prompt=prompts.production_manager(),
            user_message=pm_input,
            tools=[lookup_rates],
            model_tier=self.definition.agents["production_manager"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self.log_step(
            "production_manager", "feasibility",
            pm_input[:200], pm_result,
            duration_ms=duration_ms,
        )
        feasibility = self.parse_and_validate(
            pm_result.output, FeasibilityAssessment, "production_manager",
            system_prompt=prompts.production_manager(),
            user_message=pm_input,
            tools=[lookup_rates],
            model_tier=self.definition.agents["production_manager"]["model_tier"],
        )
        outputs["feasibility"] = feasibility
        return outputs

    def _run_producer_collation(self, outputs: dict) -> dict:
        """Step 6: Producer collates everything into EpisodePackage."""
        import time
        collation_input = json.dumps({
            "sp_brief": outputs["producer_brief"],
            "research": outputs["research_pack"],
            "treatment": outputs["treatment"],
            "feasibility": outputs["feasibility"],
        })
        start = time.time()
        collation_result = self.run_agent(
            name="producer",
            system_prompt=prompts.producer_collation(),
            user_message=collation_input,
            tools=[flag_gap],
            model_tier=self.definition.agents["producer"]["model_tier"],
        )
        duration_ms = int((time.time() - start) * 1000)
        self.log_step(
            "producer", "collation",
            collation_input[:200], collation_result,
            duration_ms=duration_ms,
        )
        episode_package = self.parse_and_validate(
            collation_result.output, EpisodePackage, "producer",
            system_prompt=prompts.producer_collation(),
            user_message=collation_input,
            tools=[flag_gap],
            model_tier=self.definition.agents["producer"]["model_tier"],
        )
        outputs["episode_package"] = episode_package
        return outputs

    def _run_sp_phase_b_loop(self, outputs: dict) -> dict:
        """Step 7-8: SP reviews, possibly requests rework, produces PitchDeck."""
        import time
        rework_exhausted = False
        while True:
            user_msg = json.dumps(outputs["episode_package"])
            if rework_exhausted:
                user_msg += (
                    "\n\nIMPORTANT: You have used all available rework cycles. "
                    "You MUST produce a PitchDeck JSON now with the best "
                    "available material. Note any remaining concerns in the "
                    "'unresolved_concerns' field."
                )

            start = time.time()
            sp_b_result = self.run_agent(
                name="series_producer",
                system_prompt=prompts.series_producer_phase_b(),
                user_message=user_msg,
                tools=[],
                model_tier=self.definition.agents["series_producer"]["model_tier"],
            )
            duration_ms = int((time.time() - start) * 1000)
            self.log_step(
                "series_producer", "phase_b",
                json.dumps(outputs["episode_package"])[:200], sp_b_result,
                duration_ms=duration_ms,
            )

            try:
                cleaned = _strip_markdown_json(sp_b_result.output)
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                parsed = {}

            if "rework_request" in parsed:
                if self.rework_count < self.max_rework_cycles:
                    rework = parsed["rework_request"]
                    self.rework_count += 1
                    outputs = self._handle_rework(rework, outputs)
                    continue
                else:
                    rework_exhausted = True
                    continue

            pitch_deck = self.parse_and_validate(
                sp_b_result.output, PitchDeck, "series_producer",
                system_prompt=prompts.series_producer_phase_b(),
                user_message=json.dumps(outputs["episode_package"]),
                tools=[],
                model_tier=self.definition.agents["series_producer"]["model_tier"],
            )
            # Inject deck_imagery and pre-rendered pixel art
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
        import time
        log_data = [entry.model_dump(mode="json") for entry in self.log]
        start = time.time()
        evidence_result = self.run_agent(
            name="series_producer",
            system_prompt=prompts.evidence(),
            user_message=json.dumps(log_data),
            tools=[],
            model_tier="utility",
        )
        duration_ms = int((time.time() - start) * 1000)
        self.log_step(
            "evidence_generator", "evidence",
            f"Pipeline log ({len(self.log)} entries)", evidence_result,
            duration_ms=duration_ms,
        )
        try:
            evidence_pack = self.parse_and_validate(
                evidence_result.output, EvidencePack, "evidence_generator",
            )
            outputs["evidence"] = evidence_pack
        except Exception:
            outputs["evidence"] = None
        return outputs

    def _handle_rework(self, rework: dict, outputs: dict) -> dict:
        """Re-run the target agent with rework notes, then cascade."""
        target = rework.get("agent", "")
        notes = rework.get("notes", "")
        self.emit({
            "type": "rework",
            "target": target,
            "notes": notes,
            "cycle": self.rework_count,
            "message": f"Series Producer requests rework from {target}: {notes[:80]}",
        })

        if target == "researcher":
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
            outputs = self._run_producer_collation(outputs)

        cascades = CASCADE_GRAPH.get(target, [])
        for cascade_agent in cascades:
            if cascade_agent == "director" and target != "director":
                outputs = self._run_director(outputs)
            elif cascade_agent == "production_manager" and target != "production_manager":
                outputs = self._run_production_manager(outputs)
            elif cascade_agent == "producer_collation":
                outputs = self._run_producer_collation(outputs)

        return outputs
