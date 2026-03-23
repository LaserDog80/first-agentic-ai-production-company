"""Research tools — reference_research is a closure factory."""
from src.tools import tool


def create_reference_research(research_pack: dict):
    """Factory: returns a @tool-decorated function bound to a research pack.

    The model only sees reference_research(section: str), not the research_pack.
    """
    @tool
    def reference_research(section: str) -> dict:
        """Look up a specific section from the research pack."""
        if section in research_pack:
            return {"section": section, "data": research_pack[section]}
        return {"error": f"Section '{section}' not found. Available: {list(research_pack.keys())}"}

    return reference_research
