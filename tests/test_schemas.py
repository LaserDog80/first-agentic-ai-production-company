# tests/test_schemas.py
import pytest
from src.schemas import (
    FormatSpec, ProducerBrief, ResearchBrief, DirectorBrief, PMBrief,
    CompetitorEntry, CharacterEntry, FactEntry, ArchiveEntry, LocationEntry,
    ResearchPack, NarrativeArc, SequenceEntry, ContributorEntry,
    CreativeTreatment, ShootingEstimate, BudgetBracket, CrewEntry,
    LogisticsEntry, FeasibilityAssessment, EpisodePackage,
    TitlePage, FeasibilitySummary, PitchDeck,
    ToolCallLog, LogEntry, EvidenceStep, EvidencePack,
)


def test_format_spec_valid():
    fs = FormatSpec(series_length="3x60", genre="factual", tone="warm and observational")
    assert fs.series_length == "3x60"


def test_producer_brief_valid():
    brief = ProducerBrief(
        working_title="The Last Lighthouse Keeper",
        format=FormatSpec(series_length="3x60", genre="factual", tone="warm"),
        target_broadcaster="BBC Two",
        creative_steer="An intimate portrait of solitude and duty.",
        sample_episode_focus="The daily routine and history of Lundy Island.",
        assumptions=["Access to Lundy Island is feasible"],
    )
    assert brief.working_title == "The Last Lighthouse Keeper"


def test_research_pack_valid():
    pack = ResearchPack(
        competitive_landscape=[
            CompetitorEntry(title="Lighthouse", broadcaster="BBC Four",
                            year="2019", relevance="Similar tone")
        ],
        characters=[
            CharacterEntry(name="John Smith", role="Keeper",
                           access_notes="Lives locally", story_angle="30 years of service")
        ],
        key_facts=[
            FactEntry(fact="Lundy has one lighthouse", source="Trinity House",
                      confidence="high")
        ],
        archive_sources=[
            ArchiveEntry(type="photo", description="Historical keeper photos",
                         access="public")
        ],
        locations=[
            LocationEntry(name="Lundy Island", rationale="Primary location",
                          logistics_note="Ferry access only")
        ],
        risks_and_sensitivities=["Weather dependent access"],
    )
    assert len(pack.competitive_landscape) == 1


def test_fact_entry_confidence_validation():
    with pytest.raises(Exception):
        FactEntry(fact="test", source="test", confidence="maybe")


def test_feasibility_rating_validation():
    with pytest.raises(Exception):
        FeasibilityAssessment(
            shooting_days=ShootingEstimate(estimate=10, breakdown="test"),
            budget_bracket=BudgetBracket(low=100000, high=200000,
                                         currency="GBP", notes=""),
            crew_requirements=[],
            logistics=[],
            feasibility_rating="purple",
            cost_saving_opportunities=[],
        )


def test_pitch_deck_valid():
    deck = PitchDeck(
        title_page=TitlePage(working_title="Test", genre="factual",
                             format="3x60", target_broadcaster="BBC"),
        logline="A show about testing.",
        format_and_tone=FormatSpec(series_length="3x60", genre="factual",
                                   tone="warm"),
        target_audience="Adults 25-54",
        competitive_landscape=[],
        key_characters=[],
        episode_breakdown=CreativeTreatment(
            episode_title="Pilot",
            narrative_arc=NarrativeArc(opening="", development="",
                                       climax="", resolution=""),
            key_sequences=[],
            overall_tone="warm",
            visual_approach="observational",
            contributor_usage=[],
            special_requirements=[],
        ),
        feasibility_summary=FeasibilitySummary(
            feasibility_rating="green",
            budget_bracket=BudgetBracket(low=100000, high=200000,
                                         currency="GBP", notes=""),
            shooting_days=10,
            key_risks=[],
        ),
        why_now="Testing is timely.",
        sp_review_notes="Approved.",
        unresolved_concerns=[],
    )
    assert deck.title_page.working_title == "Test"


def test_episode_package_valid():
    brief = ProducerBrief(
        working_title="Test", format=FormatSpec(series_length="1x60",
                                                 genre="factual", tone="warm"),
        target_broadcaster="BBC", creative_steer="Test",
        sample_episode_focus="Test", assumptions=[],
    )
    pack = ResearchPack(
        competitive_landscape=[], characters=[], key_facts=[],
        archive_sources=[], locations=[], risks_and_sensitivities=[],
    )
    treatment = CreativeTreatment(
        episode_title="Test",
        narrative_arc=NarrativeArc(opening="", development="",
                                    climax="", resolution=""),
        key_sequences=[], overall_tone="warm", visual_approach="obs",
        contributor_usage=[], special_requirements=[],
    )
    feasibility = FeasibilityAssessment(
        shooting_days=ShootingEstimate(estimate=5, breakdown="5 days"),
        budget_bracket=BudgetBracket(low=50000, high=100000,
                                     currency="GBP", notes=""),
        crew_requirements=[], logistics=[],
        feasibility_rating="green", cost_saving_opportunities=[],
    )
    ep = EpisodePackage(
        sp_brief=brief, research=pack, treatment=treatment,
        feasibility=feasibility,
        editorial_narrative="This works because...",
        gaps_and_conflicts=[],
    )
    assert ep.editorial_narrative == "This works because..."


def test_log_entry_valid():
    from datetime import datetime
    entry = LogEntry(
        agent_name="researcher", phase="researcher",
        timestamp=datetime.now(), input_summary="test input",
        output_summary="test output",
        token_usage={"prompt": 100, "completion": 200},
        duration_ms=1500, tool_calls=[],
        rework_requested=False, rework_target=None, rework_notes=None,
    )
    assert entry.agent_name == "researcher"
