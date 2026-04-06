"""Tools specific to the TV Production pipeline."""

from src.tools import tool


# --- Rate lookup ---

RATES = {
    "UK": {
        "camera operator": 450, "sound recordist": 400, "director": 600,
        "producer": 550, "researcher": 300, "editor": 400,
        "production manager": 450, "runner": 150, "presenter": 800,
        "_default": 350, "_currency": "GBP",
    },
    "US": {
        "camera operator": 600, "sound recordist": 500, "director": 800,
        "producer": 700, "researcher": 400, "editor": 550,
        "production manager": 600, "runner": 200, "presenter": 1000,
        "_default": 450, "_currency": "USD",
    },
    "_default_region": "UK",
}


@tool
def lookup_rates(role: str, region: str) -> dict:
    """Look up approximate daily rates for a TV production role in a region."""
    region_key = region.upper() if region.upper() in RATES else RATES["_default_region"]
    region_data = RATES[region_key]
    role_lower = role.lower()
    daily_rate = region_data.get(role_lower, region_data["_default"])
    currency = region_data["_currency"]
    return {
        "role": role,
        "region": region_key,
        "daily_rate": daily_rate,
        "currency": currency,
        "note": "Estimate only — actual rates vary by experience and availability",
    }


# --- Rework / approval tools ---

@tool
def request_rework(agent: str, notes: str) -> dict:
    """Request that a specific agent redo their work with additional guidance."""
    return {"status": "rework_requested", "agent": agent, "notes": notes}


@tool
def approve() -> dict:
    """Approve the current episode package. Signals review is complete."""
    return {"status": "approved"}


@tool
def flag_gap(description: str) -> dict:
    """Flag a gap or conflict in the collated outputs for SP visibility."""
    return {"status": "gap_flagged", "description": description}


# --- Research reference closure factory ---

def create_reference_research(research_pack: dict):
    """Factory: returns a @tool-decorated function bound to a research pack."""

    @tool
    def reference_research(section: str) -> dict:
        """Look up a specific section from the research pack."""
        if section in research_pack:
            return {"section": section, "data": research_pack[section]}
        return {
            "error": f"Section '{section}' not found. "
                     f"Available: {list(research_pack.keys())}"
        }

    return reference_research
