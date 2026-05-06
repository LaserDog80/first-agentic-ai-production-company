"""Pydantic models + validation for agent graphs."""
from typing import Literal

from pydantic import BaseModel, Field


NodeType = Literal["agent", "skill", "source", "input", "output"]
EdgeKind = Literal["delegate", "skill", "input", "output"]


class Position(BaseModel):
    x: float = 0.0
    y: float = 0.0


class Node(BaseModel):
    """A node in an agent graph."""

    id: str
    type: NodeType
    label: str = ""
    position: Position = Field(default_factory=Position)

    # Agent-only fields
    system_prompt: str = ""
    model_tier: str = "strong"
    max_iterations: int = 5
    tier: int = 0  # vertical layer hint for layout

    # Skill node
    skill_id: str = ""
    params: dict = Field(default_factory=dict)

    # Source node
    source_kind: str = ""  # e.g. "text"
    source_value: str = ""

    # Output node
    subtype: str = ""  # e.g. "pitch_deck" triggers PPTX export


class Edge(BaseModel):
    id: str = ""
    from_: str = Field(alias="from")
    to: str
    kind: EdgeKind

    model_config = {"populate_by_name": True}


class Graph(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    entry_node_id: str
    nodes: list[Node]
    edges: list[Edge]


def validate_graph(graph: Graph) -> list[str]:
    """Return a list of validation errors. Empty list = valid."""
    errors: list[str] = []
    ids = {n.id for n in graph.nodes}
    by_id = {n.id: n for n in graph.nodes}

    if len(ids) != len(graph.nodes):
        errors.append("Duplicate node ids.")

    inputs = [n for n in graph.nodes if n.type == "input"]
    outputs = [n for n in graph.nodes if n.type == "output"]
    if len(inputs) != 1:
        errors.append(f"Expected exactly 1 input node, got {len(inputs)}.")
    if len(outputs) < 1:
        errors.append("At least one output node required.")

    for e in graph.edges:
        if e.from_ not in ids:
            errors.append(f"Edge '{e.id}' from unknown node '{e.from_}'.")
            continue
        if e.to not in ids:
            errors.append(f"Edge '{e.id}' to unknown node '{e.to}'.")
            continue
        src, dst = by_id[e.from_], by_id[e.to]
        if e.kind == "skill":
            if src.type not in ("skill", "source"):
                errors.append(
                    f"Skill edge '{e.id}': source must be skill or source node."
                )
            if dst.type != "agent":
                errors.append(f"Skill edge '{e.id}': target must be an agent.")
        elif e.kind == "delegate":
            if src.type != "agent" or dst.type != "agent":
                errors.append(f"Delegate edge '{e.id}': both ends must be agents.")
        elif e.kind == "input":
            if src.type != "input":
                errors.append(f"Input edge '{e.id}': source must be input node.")
            if dst.type != "agent":
                errors.append(f"Input edge '{e.id}': target must be an agent.")
        elif e.kind == "output":
            if dst.type != "output":
                errors.append(f"Output edge '{e.id}': target must be output node.")
            if src.type != "agent":
                errors.append(f"Output edge '{e.id}': source must be an agent.")

    if graph.entry_node_id not in ids:
        errors.append(f"entry_node_id '{graph.entry_node_id}' not in graph.")

    if not errors:
        # Cycle check on delegate edges (DFS).
        adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for e in graph.edges:
            if e.kind == "delegate":
                adj[e.from_].append(e.to)

        WHITE, GRAY, BLACK = 0, 1, 2
        colour: dict[str, int] = {nid: WHITE for nid in ids}

        def dfs(u: str) -> bool:
            colour[u] = GRAY
            for v in adj[u]:
                if colour[v] == GRAY:
                    return True
                if colour[v] == WHITE and dfs(v):
                    return True
            colour[u] = BLACK
            return False

        for nid in ids:
            if colour[nid] == WHITE and dfs(nid):
                errors.append("Cycle detected in delegate edges.")
                break

    return errors
