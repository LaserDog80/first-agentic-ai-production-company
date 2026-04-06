"""Startup Pitch pipeline — full implementation.

Transforms a business idea into an investor-ready pitch through
strategic framing, market research, business modelling, financial
projections, and investor review.
"""

import json
import logging
from typing import Any

from src.core.pipeline import BasePipeline, PipelineDefinition, PipelineResult
from src.pipelines.startup_pitch import prompts
from src.pipelines.startup_pitch.schemas import (
    StrategicFrame, MarketResearch, BusinessModel,
    Financials, InvestorPitch, ReviewedPitch,
)
from src.tools.search import web_search

logger = logging.getLogger(__name__)

# Rework cascades
CASCADE_GRAPH: dict[str, list[str]] = {
    "market_researcher": ["business_architect", "financial_modeller", "pitch_writer"],
    "business_architect": ["financial_modeller", "pitch_writer"],
    "financial_modeller": ["pitch_writer"],
}


class StartupPitchPipeline(BasePipeline):
    """Startup Pitch pipeline: idea -> investor-ready pitch.

    Steps:
    1. Strategist: idea -> StrategicFrame
    2. Market Researcher: StrategicFrame -> MarketResearch (web_search)
    3. Business Architect: frame + research -> BusinessModel
    4. Financial Modeller: all -> Financials
    5. Pitch Writer: all -> InvestorPitch
    6. Investor Reviewer: review + approve/rework
    """

    def __init__(
        self,
        definition: PipelineDefinition,
        global_config_path: str = "config.yaml",
    ) -> None:
        super().__init__(definition, global_config_path)
        self._total_steps = 6

    def execute(self, input_text: str) -> PipelineResult:
        """Execute the startup pitch pipeline."""
        outputs: dict[str, Any] = {"idea": input_text}

        # Step 1 — Strategic Framing
        _, strategic_frame = self.run_agent_step(
            name="strategist", phase="framing",
            system_prompt=prompts.strategist(),
            user_message=input_text,
            model_tier=self._agent_tier("strategist"),
            step_num=1, total_steps=self._total_steps,
            start_message="Framing the business opportunity...",
            done_message="Strategic frame ready.",
            validate_schema=StrategicFrame,
        )
        outputs["strategic_frame"] = strategic_frame

        # Step 2 — Market Research
        _, market_research = self.run_agent_step(
            name="market_researcher", phase="research",
            system_prompt=prompts.market_researcher(),
            user_message=json.dumps(strategic_frame),
            tools=[web_search],
            model_tier=self._agent_tier("market_researcher"),
            step_num=2, total_steps=self._total_steps,
            start_message="Researching market size, competitors, and trends...",
            done_message="Market research compiled.",
            validate_schema=MarketResearch,
        )
        outputs["market_research"] = market_research

        # Step 3 — Business Model
        model_input = json.dumps({
            "strategic_frame": strategic_frame,
            "market_research": market_research,
        })
        _, business_model = self.run_agent_step(
            name="business_architect", phase="modelling",
            system_prompt=prompts.business_architect(),
            user_message=model_input,
            model_tier=self._agent_tier("business_architect"),
            step_num=3, total_steps=self._total_steps,
            start_message="Designing the business model and go-to-market...",
            done_message="Business model designed.",
            validate_schema=BusinessModel,
        )
        outputs["business_model"] = business_model

        # Step 4 — Financial Projections
        fin_input = json.dumps({
            "strategic_frame": strategic_frame,
            "market_research": market_research,
            "business_model": business_model,
        })
        _, financials = self.run_agent_step(
            name="financial_modeller", phase="financials",
            system_prompt=prompts.financial_modeller(),
            user_message=fin_input,
            model_tier=self._agent_tier("financial_modeller"),
            step_num=4, total_steps=self._total_steps,
            start_message="Building 3-year financial projections...",
            done_message="Financial model complete.",
            validate_schema=Financials,
        )
        outputs["financials"] = financials

        # Step 5 — Pitch Assembly
        pitch_input = json.dumps({
            "strategic_frame": strategic_frame,
            "market_research": market_research,
            "business_model": business_model,
            "financials": financials,
        })
        _, pitch = self.run_agent_step(
            name="pitch_writer", phase="assembly",
            system_prompt=prompts.pitch_writer(),
            user_message=pitch_input,
            model_tier=self._agent_tier("pitch_writer"),
            step_num=5, total_steps=self._total_steps,
            start_message="Assembling the investor pitch...",
            done_message="Draft pitch assembled.",
            validate_schema=InvestorPitch,
        )
        outputs["pitch"] = pitch

        # Step 6 — Investor Review
        outputs = self._run_review_loop(outputs)

        return PipelineResult(
            output=outputs.get("final_pitch"),
            evidence=outputs.get("investor_notes"),
        )

    def _run_review_loop(self, outputs: dict) -> dict:
        """Investor reviewer checks the pitch, optionally requests rework."""
        review_input = json.dumps({
            "strategic_frame": outputs["strategic_frame"],
            "pitch": outputs["pitch"],
            "market_research": outputs["market_research"],
            "financials": outputs["financials"],
        })

        while True:
            result, validated = self.run_agent_step(
                name="investor_reviewer", phase="review",
                system_prompt=prompts.investor_reviewer(),
                user_message=review_input,
                model_tier=self._agent_tier("investor_reviewer"),
                step_num=6, total_steps=self._total_steps,
                start_message="Reviewing from an investor perspective...",
                done_message="Investor review complete.",
                validate_schema=ReviewedPitch,
            )

            if validated and validated.get("approved"):
                outputs["final_pitch"] = validated.get("pitch", outputs["pitch"])
                outputs["investor_notes"] = {
                    "investor_notes": validated.get("investor_notes", ""),
                    "strengths": validated.get("strengths", []),
                    "risks": validated.get("risks", []),
                    "questions_to_expect": validated.get("questions_to_expect", []),
                }
                break
            elif validated and validated.get("rework_request"):
                if self.rework_count < self.max_rework_cycles:
                    self.rework_count += 1
                    rework = validated["rework_request"]
                    target = rework.get("agent", "pitch_writer")
                    notes = rework.get("notes", "")
                    self.emit({
                        "type": "rework",
                        "target": target,
                        "notes": notes,
                        "cycle": self.rework_count,
                        "message": f"Investor reviewer requests rework from {target}: {notes[:80]}",
                    })
                    outputs = self._handle_rework(target, notes, outputs)
                    review_input = json.dumps({
                        "strategic_frame": outputs["strategic_frame"],
                        "pitch": outputs["pitch"],
                        "market_research": outputs["market_research"],
                        "financials": outputs["financials"],
                    })
                    continue
                else:
                    outputs["final_pitch"] = outputs["pitch"]
                    outputs["investor_notes"] = {"note": "Max rework cycles reached."}
                    break
            else:
                outputs["final_pitch"] = outputs["pitch"]
                outputs["investor_notes"] = {}
                break

        return outputs

    def _handle_rework(self, target: str, notes: str, outputs: dict) -> dict:
        """Re-run target agent, then cascade downstream."""
        if target == "market_researcher":
            augmented = dict(outputs["strategic_frame"])
            augmented["rework_notes"] = notes
            _, market_research = self.run_agent_step(
                name="market_researcher", phase="research_rework",
                system_prompt=prompts.market_researcher(),
                user_message=json.dumps(augmented),
                tools=[web_search],
                model_tier=self._agent_tier("market_researcher"),
                start_message="Re-researching market with feedback...",
                done_message="Updated market research ready.",
                validate_schema=MarketResearch,
            )
            outputs["market_research"] = market_research

        if target in ("market_researcher", "business_architect"):
            model_input = json.dumps({
                "strategic_frame": outputs["strategic_frame"],
                "market_research": outputs["market_research"],
                **({"rework_notes": notes} if target == "business_architect" else {}),
            })
            _, business_model = self.run_agent_step(
                name="business_architect", phase="modelling_rework",
                system_prompt=prompts.business_architect(),
                user_message=model_input,
                model_tier=self._agent_tier("business_architect"),
                start_message="Redesigning business model...",
                done_message="Updated business model ready.",
                validate_schema=BusinessModel,
            )
            outputs["business_model"] = business_model

        if target in ("market_researcher", "business_architect", "financial_modeller"):
            fin_input = json.dumps({
                "strategic_frame": outputs["strategic_frame"],
                "market_research": outputs["market_research"],
                "business_model": outputs["business_model"],
                **({"rework_notes": notes} if target == "financial_modeller" else {}),
            })
            _, financials = self.run_agent_step(
                name="financial_modeller", phase="financials_rework",
                system_prompt=prompts.financial_modeller(),
                user_message=fin_input,
                model_tier=self._agent_tier("financial_modeller"),
                start_message="Updating financial projections...",
                done_message="Updated financials ready.",
                validate_schema=Financials,
            )
            outputs["financials"] = financials

        # Always re-run pitch writer after any rework
        pitch_input = json.dumps({
            "strategic_frame": outputs["strategic_frame"],
            "market_research": outputs["market_research"],
            "business_model": outputs["business_model"],
            "financials": outputs["financials"],
            **({"rework_notes": notes} if target == "pitch_writer" else {}),
        })
        _, pitch = self.run_agent_step(
            name="pitch_writer", phase="assembly_rework",
            system_prompt=prompts.pitch_writer(),
            user_message=pitch_input,
            model_tier=self._agent_tier("pitch_writer"),
            start_message="Re-assembling pitch...",
            done_message="Updated pitch ready.",
            validate_schema=InvestorPitch,
        )
        outputs["pitch"] = pitch
        return outputs

    def _agent_tier(self, name: str) -> str:
        return self.definition.agents.get(name, {}).get("model_tier", "strong")
