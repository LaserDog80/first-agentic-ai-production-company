from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, field_validator


# --- Nested/shared types ---

class FormatSpec(BaseModel):
    series_length: str  # e.g. "3x60", "6x30"
    genre: str
    tone: str


class CompetitorEntry(BaseModel):
    title: str
    broadcaster: str
    year: str  # LLMs may return int; validator coerces
    relevance: str

    @field_validator("year", mode="before")
    @classmethod
    def coerce_year_to_str(cls, v: Any) -> str:
        return str(v)


class CharacterEntry(BaseModel):
    name: str
    role: str
    access_notes: str
    story_angle: str


class FactEntry(BaseModel):
    fact: str
    source: str
    confidence: Literal["high", "medium", "low"]


class ArchiveEntry(BaseModel):
    type: str
    description: str
    access: str


class LocationEntry(BaseModel):
    name: str
    rationale: str
    logistics_note: str


class DeckImageEntry(BaseModel):
    slot: str  # e.g. "title_background", "narrative_arc", "visual_approach"
    concept: str  # e.g. "aerial view of Scottish highlands at dawn"
    elements: list[str]  # e.g. ["mountains", "heather", "mist"]
    mood: str  # e.g. "epic", "intimate", "dark"


class NarrativeArc(BaseModel):
    opening: str
    development: str
    climax: str
    resolution: str


class SequenceEntry(BaseModel):
    name: str
    description: str
    visual_style: str
    duration_mins: int


class ContributorEntry(BaseModel):
    character_name: str
    role_in_episode: str


class ShootingEstimate(BaseModel):
    estimate: int
    breakdown: str


class BudgetBracket(BaseModel):
    low: int
    high: int
    currency: str
    notes: str


class CrewEntry(BaseModel):
    role: str
    reason: str


class LogisticsEntry(BaseModel):
    item: str
    challenge: str
    mitigation: str


# --- Agent I/O types ---

class ProducerBrief(BaseModel):
    working_title: str
    format: FormatSpec
    target_broadcaster: str
    creative_steer: str
    sample_episode_focus: str
    assumptions: list[str]


class ResearchBrief(BaseModel):
    topic: str
    angles_to_explore: list[str]
    deliverables: list[str]
    quality_bar: str


class DirectorBrief(BaseModel):
    topic: str
    creative_steer: str
    tone_guidance: str
    key_questions: list[str]
    quality_bar: str


class PMBrief(BaseModel):
    topic: str
    format: FormatSpec
    known_requirements: list[str]
    quality_bar: str


class SpecialistBriefs(BaseModel):
    research_brief: ResearchBrief
    director_brief: DirectorBrief
    pm_brief: PMBrief


class ResearchPack(BaseModel):
    competitive_landscape: list[CompetitorEntry]
    characters: list[CharacterEntry]
    key_facts: list[FactEntry]
    archive_sources: list[ArchiveEntry]
    locations: list[LocationEntry]
    risks_and_sensitivities: list[str]
    deck_imagery: list[DeckImageEntry] = []


class CreativeTreatment(BaseModel):
    episode_title: str
    narrative_arc: NarrativeArc
    key_sequences: list[SequenceEntry]
    overall_tone: str
    visual_approach: str
    contributor_usage: list[ContributorEntry]
    special_requirements: list[str]


class FeasibilityAssessment(BaseModel):
    shooting_days: ShootingEstimate
    budget_bracket: BudgetBracket
    crew_requirements: list[CrewEntry]
    logistics: list[LogisticsEntry]
    feasibility_rating: Literal["green", "amber", "red"]
    cost_saving_opportunities: list[str]


class EditorialContribution(BaseModel):
    """The Producer's actual contribution to the EpisodePackage.

    Kept separate from EpisodePackage so the Producer LLM is only asked to
    generate its own additions, not echo back the (large) specialist outputs.
    """
    editorial_narrative: str
    gaps_and_conflicts: list[str]


class EpisodePackage(BaseModel):
    sp_brief: ProducerBrief
    research: ResearchPack
    treatment: CreativeTreatment
    feasibility: FeasibilityAssessment
    editorial_narrative: str
    gaps_and_conflicts: list[str]


# --- Final output types ---

class TitlePage(BaseModel):
    working_title: str
    genre: str
    format: str
    target_broadcaster: str


class FeasibilitySummary(BaseModel):
    feasibility_rating: Literal["green", "amber", "red"]
    budget_bracket: BudgetBracket
    shooting_days: int
    key_risks: list[str]


class PitchDeck(BaseModel):
    title_page: TitlePage
    logline: str
    format_and_tone: FormatSpec
    target_audience: str
    competitive_landscape: list[CompetitorEntry]
    key_characters: list[CharacterEntry]
    episode_breakdown: CreativeTreatment
    feasibility_summary: FeasibilitySummary
    why_now: str
    sp_review_notes: str
    unresolved_concerns: list[str]
    deck_imagery: list[DeckImageEntry] = []


# --- Logging types ---

class ToolCallLog(BaseModel):
    tool_name: str
    args_summary: str
    result_summary: str


class LogEntry(BaseModel):
    agent_name: str
    phase: str
    timestamp: datetime
    input_summary: str
    output_summary: str
    token_usage: dict
    duration_ms: int
    tool_calls: list[ToolCallLog]
    rework_requested: bool
    rework_target: str | None
    rework_notes: str | None


class EvidenceStep(BaseModel):
    agent_name: str
    phase: str
    what_received: str
    what_produced: str
    tools_used: list[str]
    duration_ms: int


class EvidencePack(BaseModel):
    pipeline_summary: str
    steps: list[EvidenceStep]
    total_duration_ms: int
    total_tokens: dict
    rework_count: int
    rework_details: list[str]
