"""Research Report pipeline — full implementation.

Transforms a research topic into a structured, sourced research report
through planning, investigation, analysis, writing, and review.
"""

import json
import logging
from typing import Any

from src.core.pipeline import BasePipeline, PipelineDefinition, PipelineResult, _strip_markdown_json
from src.core.schemas import EvidencePack
from src.pipelines.research_report import prompts
from src.pipelines.research_report.schemas import (
    ResearchPlan, EvidenceFile, Analysis, ResearchReport, ReviewedReport,
)
from src.tools.search import web_search

logger = logging.getLogger(__name__)


class ResearchReportPipeline(BasePipeline):
    """Research Report pipeline: topic -> structured report.

    Steps:
    1. Research Director: topic -> ResearchPlan
    2. Investigator: ResearchPlan -> EvidenceFile (web_search)
    3. Analyst: EvidenceFile -> Analysis
    4. Writer: all inputs -> ResearchReport
    5. Reviewer: report -> approve or rework
    """

    def __init__(
        self,
        definition: PipelineDefinition,
        global_config_path: str = "config.yaml",
    ) -> None:
        super().__init__(definition, global_config_path)
        self._total_steps = 5

    def execute(self, input_text: str) -> PipelineResult:
        """Execute the research report pipeline."""
        outputs: dict[str, Any] = {"topic": input_text}

        # Step 1 — Research Director: plan the research
        _, research_plan = self.run_agent_step(
            name="research_director", phase="planning",
            system_prompt=prompts.research_director(),
            user_message=input_text,
            model_tier=self._agent_tier("research_director"),
            step_num=1, total_steps=self._total_steps,
            start_message="Scoping the research and defining key questions...",
            done_message="Research plan ready.",
            validate_schema=ResearchPlan,
        )
        outputs["research_plan"] = research_plan

        # Step 2 — Investigator: conduct web research
        _, evidence_file = self.run_agent_step(
            name="investigator", phase="investigation",
            system_prompt=prompts.investigator(),
            user_message=json.dumps(research_plan),
            tools=[web_search],
            model_tier=self._agent_tier("investigator"),
            step_num=2, total_steps=self._total_steps,
            start_message="Investigating — running web searches across all angles...",
            done_message="Evidence file compiled.",
            validate_schema=EvidenceFile,
        )
        outputs["evidence_file"] = evidence_file

        # Step 3 — Analyst: synthesise findings
        analyst_input = json.dumps({
            "research_plan": research_plan,
            "evidence_file": evidence_file,
        })
        _, analysis = self.run_agent_step(
            name="analyst", phase="analysis",
            system_prompt=prompts.analyst(),
            user_message=analyst_input,
            model_tier=self._agent_tier("analyst"),
            step_num=3, total_steps=self._total_steps,
            start_message="Analysing evidence and identifying themes...",
            done_message="Analysis complete.",
            validate_schema=Analysis,
        )
        outputs["analysis"] = analysis

        # Step 4 — Writer: produce the report
        writer_input = json.dumps({
            "research_plan": research_plan,
            "evidence_file": evidence_file,
            "analysis": analysis,
        })
        _, report = self.run_agent_step(
            name="writer", phase="writing",
            system_prompt=prompts.writer(),
            user_message=writer_input,
            model_tier=self._agent_tier("writer"),
            step_num=4, total_steps=self._total_steps,
            start_message="Writing the research report...",
            done_message="Draft report complete.",
            validate_schema=ResearchReport,
        )
        outputs["report"] = report

        # Step 5 — Reviewer: quality check with optional rework
        outputs = self._run_review_loop(outputs)

        return PipelineResult(
            output=outputs.get("final_report"),
            evidence=outputs.get("review_notes"),
        )

    def _run_review_loop(self, outputs: dict) -> dict:
        """Reviewer checks the report, optionally sends back for rework."""
        review_input = json.dumps({
            "research_plan": outputs["research_plan"],
            "report": outputs["report"],
        })

        while True:
            result, validated = self.run_agent_step(
                name="reviewer", phase="review",
                system_prompt=prompts.reviewer(),
                user_message=review_input,
                model_tier=self._agent_tier("reviewer"),
                step_num=5, total_steps=self._total_steps,
                start_message="Reviewing report for quality and accuracy...",
                done_message="Review complete.",
                validate_schema=ReviewedReport,
            )

            if validated and validated.get("approved"):
                outputs["final_report"] = validated.get("report", outputs["report"])
                outputs["review_notes"] = {
                    "review_notes": validated.get("review_notes", ""),
                    "quality_rating": validated.get("quality_rating", ""),
                    "strengths": validated.get("strengths", []),
                    "minor_concerns": validated.get("minor_concerns", []),
                }
                break
            elif validated and validated.get("rework_request"):
                if self.rework_count < self.max_rework_cycles:
                    self.rework_count += 1
                    rework = validated["rework_request"]
                    target = rework.get("agent", "writer")
                    notes = rework.get("notes", "")
                    self.emit({
                        "type": "rework",
                        "target": target,
                        "notes": notes,
                        "cycle": self.rework_count,
                        "message": f"Reviewer requests rework from {target}: {notes[:80]}",
                    })
                    outputs = self._handle_rework(target, notes, outputs)
                    review_input = json.dumps({
                        "research_plan": outputs["research_plan"],
                        "report": outputs["report"],
                    })
                    continue
                else:
                    outputs["final_report"] = outputs["report"]
                    outputs["review_notes"] = {"note": "Max rework cycles reached."}
                    break
            else:
                outputs["final_report"] = outputs["report"]
                outputs["review_notes"] = {}
                break

        return outputs

    def _handle_rework(self, target: str, notes: str, outputs: dict) -> dict:
        """Re-run the target agent with feedback, then cascade."""
        if target == "investigator":
            augmented_plan = dict(outputs["research_plan"])
            augmented_plan["rework_notes"] = notes
            _, evidence_file = self.run_agent_step(
                name="investigator", phase="investigation_rework",
                system_prompt=prompts.investigator(),
                user_message=json.dumps(augmented_plan),
                tools=[web_search],
                model_tier=self._agent_tier("investigator"),
                start_message="Re-investigating with reviewer feedback...",
                done_message="Updated evidence file ready.",
                validate_schema=EvidenceFile,
            )
            outputs["evidence_file"] = evidence_file
            # Cascade: analyst and writer
            outputs = self._rerun_analyst(outputs)
            outputs = self._rerun_writer(outputs)
        elif target == "analyst":
            outputs = self._rerun_analyst(outputs, notes)
            outputs = self._rerun_writer(outputs)
        elif target == "writer":
            outputs = self._rerun_writer(outputs, notes)
        return outputs

    def _rerun_analyst(self, outputs: dict, notes: str = "") -> dict:
        analyst_input = json.dumps({
            "research_plan": outputs["research_plan"],
            "evidence_file": outputs["evidence_file"],
            **({"rework_notes": notes} if notes else {}),
        })
        _, analysis = self.run_agent_step(
            name="analyst", phase="analysis_rework",
            system_prompt=prompts.analyst(),
            user_message=analyst_input,
            model_tier=self._agent_tier("analyst"),
            start_message="Re-analysing with feedback...",
            done_message="Updated analysis ready.",
            validate_schema=Analysis,
        )
        outputs["analysis"] = analysis
        return outputs

    def _rerun_writer(self, outputs: dict, notes: str = "") -> dict:
        writer_input = json.dumps({
            "research_plan": outputs["research_plan"],
            "evidence_file": outputs["evidence_file"],
            "analysis": outputs["analysis"],
            **({"rework_notes": notes} if notes else {}),
        })
        _, report = self.run_agent_step(
            name="writer", phase="writing_rework",
            system_prompt=prompts.writer(),
            user_message=writer_input,
            model_tier=self._agent_tier("writer"),
            start_message="Rewriting report with feedback...",
            done_message="Updated report ready.",
            validate_schema=ResearchReport,
        )
        outputs["report"] = report
        return outputs

    def _agent_tier(self, name: str) -> str:
        return self.definition.agents.get(name, {}).get("model_tier", "strong")
