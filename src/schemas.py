"""Backward compatibility — re-exports from core and TV production schemas.

Existing code that imports from src.schemas will continue to work.
"""
# Core logging schemas
from src.core.schemas import LogEntry, ToolCallLog, EvidencePack, EvidenceStep  # noqa: F401

# TV production schemas (backward compat)
from src.pipelines.tv_production.schemas import (  # noqa: F401
    FormatSpec, CompetitorEntry, CharacterEntry, FactEntry,
    ArchiveEntry, LocationEntry, DeckImageEntry, NarrativeArc,
    SequenceEntry, ContributorEntry, ShootingEstimate, BudgetBracket,
    CrewEntry, LogisticsEntry,
    ProducerBrief, ResearchBrief, DirectorBrief, PMBrief,
    ResearchPack, CreativeTreatment, FeasibilityAssessment,
    EpisodePackage, TitlePage, FeasibilitySummary, PitchDeck,
)
