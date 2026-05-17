"""Registry mapping skill_id -> tool factory.

A skill node connected to an agent is materialised as a callable @tool
function during graph execution. Some skills (e.g. text_source) are
parameterised by node config; the factory takes the node so the closure
can capture those params.
"""
from typing import Callable

from src.graph.schema import Node
from src.tools import tool
from src.tools.rates import lookup_rates
from src.tools.search import web_search


def _web_search_factory(node: Node) -> Callable:
    return web_search


def _lookup_rates_factory(node: Node) -> Callable:
    return lookup_rates


def _text_source_factory(node: Node) -> Callable:
    """Expose this source node's text as a tool the agent can read."""
    label = node.label or node.id
    text = node.source_value or ""
    fn_name = "read_source_" + _slug(label)

    @tool
    def _read_source() -> dict:
        """Read the contents of the connected information source."""
        return {"label": label, "text": text}

    _read_source.__name__ = fn_name
    return _read_source


def _slug(s: str) -> str:
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_") or "x"


SKILL_REGISTRY: dict[str, Callable[[Node], Callable]] = {
    "web_search": _web_search_factory,
    "lookup_rates": _lookup_rates_factory,
    "text_source": _text_source_factory,
}


def build_skill_tool(node: Node) -> Callable:
    """Build the @tool callable for a skill or source node."""
    if node.type == "source":
        # Sources currently always become a text-read tool.
        return _text_source_factory(node)
    if node.skill_id not in SKILL_REGISTRY:
        raise KeyError(f"Unknown skill_id: {node.skill_id}")
    return SKILL_REGISTRY[node.skill_id](node)


def list_available_skills() -> list[dict]:
    """Return metadata about skills available in the library panel."""
    return [
        {
            "skill_id": "web_search",
            "label": "Web Search",
            "description": "Live web search. Give to any agent that needs current facts.",
        },
        {
            "skill_id": "lookup_rates",
            "label": "Rate Lookup",
            "description": "Look up a day rate for a role in a region. Ships with a sample dataset — swap in your own.",
        },
    ]
