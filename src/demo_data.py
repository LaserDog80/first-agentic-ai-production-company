"""Hardcoded demo fixture data for testing the UI without API calls."""
from src.schemas import PitchDeck, EvidencePack


# -- Realistic pitch deck fixture --
_PITCH_DECK: dict = {
    "title_page": {
        "working_title": "The Last Beekeeper",
        "genre": "Documentary",
        "format": "3x60",
        "target_broadcaster": "BBC Two",
    },
    "logline": (
        "Deep in the mountains of Georgia, Turkey, and Slovenia, "
        "the world's oldest beekeepers guard ancient techniques that "
        "modern science is only now beginning to understand — but "
        "their way of life is vanishing with every passing season."
    ),
    "format_and_tone": {
        "series_length": "3x60",
        "genre": "Documentary",
        "tone": "Warm, cinematic, elegiac",
    },
    "target_audience": (
        "Adults 35-65 with an interest in nature, food provenance, "
        "and disappearing traditions. Strong BBC Two / PBS / Arte "
        "crossover audience."
    ),
    "competitive_landscape": [
        {
            "title": "Honeyland",
            "broadcaster": "Sundance / NEON",
            "year": "2019",
            "relevance": (
                "Oscar-nominated doc about a Macedonian beekeeper; "
                "proved global appetite for intimate apiculture stories."
            ),
        },
        {
            "title": "Biggest Little Farm",
            "broadcaster": "Neon / Hulu",
            "year": "2018",
            "relevance": (
                "Sustainable farming doc that crossed over to mainstream "
                "audiences; similar themes of tradition vs. modernity."
            ),
        },
        {
            "title": "Tales from the Hive",
            "broadcaster": "PBS Nature",
            "year": "2007",
            "relevance": (
                "Classic blue-chip bee doc; our series differentiates "
                "by centering human characters, not the insects."
            ),
        },
    ],
    "key_characters": [
        {
            "name": "Dato Gorgadze",
            "role": "Master beekeeper, Tusheti region, Georgia",
            "access_notes": (
                "Contact via Georgian Beekeepers Association. "
                "Speaks Georgian; fixer/translator required."
            ),
            "story_angle": (
                "At 82, Dato still hikes to cliff-edge hives his "
                "grandfather built. His grandson wants to leave for "
                "Tbilisi — succession is uncertain."
            ),
        },
        {
            "name": "Mustafa Eris",
            "role": "Cliff-honey harvester, Artvin Province, Turkey",
            "access_notes": (
                "Accessed through Kaçkar Mountains trekking network. "
                "Turkish and some English."
            ),
            "story_angle": (
                "Mustafa rappels down 300-foot cliffs to harvest wild "
                "honey — a tradition that earns a premium but is "
                "increasingly dangerous as climate change shifts bee "
                "patterns."
            ),
        },
        {
            "name": "Ana Rojnik",
            "role": "Fourth-generation apiarist, Carniola, Slovenia",
            "access_notes": (
                "Runs an agritourism farm open to filming. "
                "Fluent in English and Slovenian."
            ),
            "story_angle": (
                "Ana is crossbreeding heritage Carniolan bees with "
                "disease-resistant strains — tradition meets science "
                "in real time."
            ),
        },
    ],
    "episode_breakdown": {
        "episode_title": "The Mountain Hives",
        "narrative_arc": {
            "opening": (
                "Pre-dawn in the Caucasus mountains. Dato Gorgadze, "
                "82, loads a wooden pack frame with hand-woven straw "
                "skeps and begins the two-hour climb to his cliff hives."
            ),
            "development": (
                "We follow Dato through a full harvest cycle while "
                "inter-cutting with Mustafa's cliff-honey expedition "
                "in Turkey. Both men face a season of diminishing "
                "returns as wildflower bloom shifts earlier each year."
            ),
            "climax": (
                "A late frost kills a third of Dato's colony. His "
                "grandson, Luka, returns from Tbilisi to help — but "
                "makes clear this will be his last season. Meanwhile "
                "Mustafa suffers a near-miss on the cliffs when an "
                "anchor bolt fails."
            ),
            "resolution": (
                "Dato and Luka sit by the fire, jars of golden honey "
                "between them. Dato recites a Tushetian blessing over "
                "the hives. The bees survive. The question of who "
                "comes next remains unanswered."
            ),
        },
        "key_sequences": [
            {
                "name": "The Cliff Harvest",
                "description": (
                    "Mustafa's team ascends the rock face at dawn; "
                    "macro-lens footage captures bees entering comb "
                    "crevices 300 feet above the valley floor."
                ),
                "visual_style": "Drone + helmet-cam, desaturated dawn palette",
                "duration_mins": 12,
            },
            {
                "name": "The Blessing of the Hives",
                "description": (
                    "Dato performs a centuries-old Tushetian ritual, "
                    "smoking herbs around each hive as he chants."
                ),
                "visual_style": (
                    "Steady handheld, warm amber grade, shallow DOF"
                ),
                "duration_mins": 6,
            },
            {
                "name": "Lab vs. Lore",
                "description": (
                    "Ana tests her crossbred queens in a university "
                    "lab while explaining how folk knowledge maps onto "
                    "modern genetics."
                ),
                "visual_style": "Clean, clinical whites contrasting with lush meadow exteriors",
                "duration_mins": 8,
            },
        ],
        "overall_tone": (
            "Warm and cinematic with an elegiac undercurrent. "
            "The beauty of these landscapes and traditions is "
            "inseparable from the threat of their disappearance."
        ),
        "visual_approach": (
            "Anamorphic lenses for landscape work; macro probe "
            "lenses for hive interiors. Natural light wherever "
            "possible, with golden-hour bookends on each episode."
        ),
        "contributor_usage": [
            {
                "character_name": "Dato Gorgadze",
                "role_in_episode": "Primary subject — episode 1",
            },
            {
                "character_name": "Mustafa Eris",
                "role_in_episode": "Secondary subject — episode 1, primary in episode 2",
            },
            {
                "character_name": "Ana Rojnik",
                "role_in_episode": "Intercut segments — episode 1, primary in episode 3",
            },
        ],
        "special_requirements": [
            "Mountain safety crew and climbing permits for cliff sequences",
            "Macro probe lens rig (Laowa 24mm) for hive interiors",
            "Georgian and Turkish language fixers/translators",
        ],
    },
    "feasibility_summary": {
        "feasibility_rating": "amber",
        "budget_bracket": {
            "low": 450000,
            "high": 620000,
            "currency": "GBP",
            "notes": (
                "Range reflects uncertainty around cliff-access "
                "insurance and multi-country travel logistics."
            ),
        },
        "shooting_days": 45,
        "key_risks": [
            "Cliff-honey sequences require specialist safety crew and insurance",
            "Seasonal dependency — bee activity peaks May-July only",
            "Georgian mountain roads may be impassable in early spring",
            "Currency fluctuation across three countries",
        ],
    },
    "why_now": (
        "Colony collapse disorder and climate change are accelerating "
        "the loss of traditional beekeeping worldwide. The UN declared "
        "2025 the International Year of Biodiversity, and pollinator "
        "decline is a top-line story. These characters won't be "
        "practising much longer — this is a closing window."
    ),
    "sp_review_notes": (
        "Strong triple-strand structure across three countries. "
        "Dato is a magnetic lead character. Budget sits at the top "
        "end for BBC Two factual but the international scope and "
        "visual ambition justify it. Cliff sequences are the USP — "
        "don't dilute them. Recommend securing Mustafa access early."
    ),
    "unresolved_concerns": [
        "Dato's health is fragile — contingency plan needed if he can't film",
        "Turkish cliff-access permissions not yet confirmed",
        "Ep 3 (Ana / Slovenia) needs a stronger dramatic engine",
    ],
    "deck_imagery": [
        {
            "slot": "title_background",
            "concept": "Misty mountain valley at dawn with wooden beehives",
            "elements": ["mountains", "mist", "beehives", "wildflowers"],
            "mood": "epic",
        },
        {
            "slot": "narrative_arc",
            "concept": "Beekeeper silhouette against golden sunset with smoke",
            "elements": ["beekeeper", "smoke", "sunset", "hive"],
            "mood": "warm",
        },
        {
            "slot": "visual_approach",
            "concept": "Close-up of honeycomb with bees and golden light",
            "elements": ["honeycomb", "bees", "golden_light", "macro"],
            "mood": "intimate",
        },
    ],
}

# -- Realistic evidence pack fixture --
_EVIDENCE: dict = {
    "pipeline_summary": (
        "Full 9-step pipeline completed in demo mode. "
        "Five AI agents — Series Producer, Producer, Researcher, "
        "Director, and Production Manager — collaborated to "
        "transform a one-line brief into a broadcast-ready pitch deck."
    ),
    "steps": [
        {
            "agent_name": "series_producer",
            "phase": "phase_a",
            "what_received": "One-line commissioning brief",
            "what_produced": "Structured ProducerBrief with editorial vision",
            "tools_used": [],
            "duration_ms": 3200,
        },
        {
            "agent_name": "producer",
            "phase": "briefing",
            "what_received": "ProducerBrief",
            "what_produced": (
                "Three specialist briefs (research, director, PM)"
            ),
            "tools_used": [],
            "duration_ms": 2800,
        },
        {
            "agent_name": "researcher",
            "phase": "research",
            "what_received": "ResearchBrief with topic and angles",
            "what_produced": (
                "ResearchPack with competitors, characters, facts, "
                "locations, and deck imagery concepts"
            ),
            "tools_used": ["web_search"],
            "duration_ms": 8500,
        },
        {
            "agent_name": "director",
            "phase": "treatment",
            "what_received": "DirectorBrief + ResearchPack",
            "what_produced": (
                "CreativeTreatment with narrative arc, sequences, "
                "and visual approach"
            ),
            "tools_used": ["reference_research"],
            "duration_ms": 4100,
        },
        {
            "agent_name": "production_manager",
            "phase": "feasibility",
            "what_received": "PMBrief + ResearchPack + CreativeTreatment",
            "what_produced": (
                "FeasibilityAssessment with budget, crew, logistics"
            ),
            "tools_used": ["lookup_rates"],
            "duration_ms": 3600,
        },
        {
            "agent_name": "producer",
            "phase": "collation",
            "what_received": "All specialist outputs",
            "what_produced": (
                "EpisodePackage with editorial narrative and gap flags"
            ),
            "tools_used": ["flag_gap"],
            "duration_ms": 3900,
        },
        {
            "agent_name": "series_producer",
            "phase": "phase_b",
            "what_received": "EpisodePackage for review",
            "what_produced": "Approved PitchDeck with review notes",
            "tools_used": [],
            "duration_ms": 4200,
        },
        {
            "agent_name": "evidence_generator",
            "phase": "evidence",
            "what_received": "Pipeline log (7 entries)",
            "what_produced": "EvidencePack summarising the full run",
            "tools_used": [],
            "duration_ms": 1800,
        },
    ],
    "total_duration_ms": 32100,
    "total_tokens": {
        "prompt": 24500,
        "completion": 8200,
    },
    "rework_count": 0,
    "rework_details": [],
}


def get_demo_result() -> dict:
    """Return a complete demo pipeline result.

    The returned dict has the same shape as a successful
    PipelineResult: pitch_deck, evidence, and log.
    """
    # Validate fixtures against schemas to catch drift
    PitchDeck.model_validate(_PITCH_DECK)
    EvidencePack.model_validate(_EVIDENCE)

    return {
        "pitch_deck": dict(_PITCH_DECK),
        "evidence": dict(_EVIDENCE),
        "log": [],
    }
