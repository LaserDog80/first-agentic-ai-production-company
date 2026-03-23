"""Static rate lookup for TV production roles."""
from src.tools import tool

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
