"""Pydantic schemas for the Research Report pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ResearchPlan(BaseModel):
    core_question: str
    sub_questions: list[str]
    angles: list[str]
    methodology_notes: str
    quality_bar: str
    expected_sections: list[str]


class EvidenceItem(BaseModel):
    claim: str
    source: str
    confidence: Literal["high", "medium", "low"]
    notes: str = ""


class FindingGroup(BaseModel):
    sub_question: str
    evidence: list[EvidenceItem]
    gaps: list[str] = []


class KeySource(BaseModel):
    name: str
    type: str
    reliability: str


class EvidenceFile(BaseModel):
    findings: list[FindingGroup]
    cross_cutting_themes: list[str] = []
    contradictions: list[str] = []
    key_sources: list[KeySource] = []


class Theme(BaseModel):
    title: str
    summary: str
    evidence_strength: Literal["strong", "moderate", "weak"]
    key_data_points: list[str]


class Conclusion(BaseModel):
    statement: str
    confidence: Literal["high", "medium", "low"]
    supporting_evidence: str
    caveats: str = ""


class Recommendation(BaseModel):
    action: str
    rationale: str
    priority: Literal["high", "medium", "low"]


class Analysis(BaseModel):
    executive_summary: str
    themes: list[Theme]
    conclusions: list[Conclusion]
    uncertainties: list[str] = []
    recommendations: list[Recommendation]


class ReportSection(BaseModel):
    heading: str
    content: str
    key_findings: list[str] = []
    sources_cited: list[str] = []


class ResearchReport(BaseModel):
    title: str
    executive_summary: str
    sections: list[ReportSection]
    conclusions: str
    recommendations: list[Recommendation]
    methodology_note: str = ""
    limitations: list[str] = []


class ReviewedReport(BaseModel):
    approved: bool
    report: ResearchReport | None = None
    review_notes: str = ""
    quality_rating: str = ""
    strengths: list[str] = []
    minor_concerns: list[str] = []
    rework_request: dict | None = None
