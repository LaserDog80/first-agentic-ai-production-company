"""Pydantic schemas for the TV Production pipeline."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, field_validator


# --- Nested/shared types ---

class FormatSpec(BaseModel):
    series_length: str
    genre: str
    tone: str


class CompetitorEntry(BaseModel):
    title: str
    broadcaster: str
    year: str
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
    slot: str
    concept: str
    elements: list[str]
    mood: str


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
