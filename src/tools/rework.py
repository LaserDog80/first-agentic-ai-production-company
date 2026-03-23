"""Supervisory tools for rework and approval control flow."""
from src.tools import tool


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
