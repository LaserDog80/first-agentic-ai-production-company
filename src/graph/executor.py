"""Execute an agent graph by driving AgentRuntime per node.

Edge semantics:
- delegate (agent -> agent): parent gets a tool `delegate_to_<child>` that
  invokes the child agent synchronously and returns the child's output.
- skill   (skill/source -> agent): the skill becomes a tool on the agent.
- input   (input -> agent): the entry brief is passed to that agent.
- output  (agent -> output): that agent's final response is the graph result.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from src.agent import AgentRuntime
from src.graph.schema import Edge, Graph, Node
from src.graph.skills import build_skill_tool
from src.provider import get_model_name
from src.tools import tool


def _slug(s: str) -> str:
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_") or "x"


class GraphExecutor:
    """Run an agent graph against a brief and stream events."""

    def __init__(
        self,
        graph: Graph,
        client: Any,
        config: dict,
        emit: Callable[[dict], None] | None = None,
        run_id: str = "",
    ) -> None:
        self.graph = graph
        self.client = client
        self.config = config
        self.emit = emit or (lambda _ev: None)
        self.run_id = run_id
        self.nodes_by_id: dict[str, Node] = {n.id: n for n in graph.nodes}

    # ── edge index helpers ──────────────────────────────────────────────────
    def _edges(self, kind: str) -> list[Edge]:
        return [e for e in self.graph.edges if e.kind == kind]

    def _delegate_children(self, parent_id: str) -> list[str]:
        return [e.to for e in self._edges("delegate") if e.from_ == parent_id]

    def _skill_sources_for(self, agent_id: str) -> list[str]:
        return [e.from_ for e in self._edges("skill") if e.to == agent_id]

    def _input_targets(self) -> list[str]:
        return [e.to for e in self._edges("input")]

    def _output_source(self) -> str | None:
        outs = self._edges("output")
        return outs[0].from_ if outs else None

    # ── tool factories ──────────────────────────────────────────────────────
    def _delegate_tool(self, parent_id: str, child_id: str, parents: list[str]) -> Callable:
        child = self.nodes_by_id[child_id]
        emit = self.emit
        run_node = self._run_node

        @tool
        def fn(message: str) -> dict:
            emit({
                "type": "edge_fired",
                "from": parent_id,
                "to": child_id,
                "kind": "delegate",
            })
            out = run_node(child_id, message, parents + [parent_id])
            return {"agent": child.label, "response": out}

        fn.__name__ = f"delegate_to_{_slug(child.label or child.id)}"
        fn.__doc__ = (
            f"Delegate a task to {child.label}. "
            "Pass a clear, self-contained message describing what you need them to do. "
            "Their full response is returned to you."
        )
        return fn

    # ── execution ───────────────────────────────────────────────────────────
    def run(self, brief: str) -> dict:
        self.emit({
            "type": "graph_run_start",
            "graph_id": self.graph.id,
            "graph_name": self.graph.name,
            "brief": brief,
        })

        targets = self._input_targets()
        if not targets:
            err = "Graph has no input edge — connect the input to an agent."
            self.emit({"type": "graph_run_error", "error": err})
            return {"ok": False, "error": err}
        entry_id = targets[0]

        try:
            output = self._run_node(entry_id, brief, parents=[])
        except Exception as exc:
            self.emit({
                "type": "graph_run_error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return {"ok": False, "error": str(exc)}

        # Determine the graph-level output: prefer node feeding the output edge.
        out_src = self._output_source()
        final_output = output
        out_subtype = ""
        if out_src is not None:
            # If the output-feeding agent ran on the entry path, its return is
            # already in `output`. Otherwise, fall back to the entry output.
            if out_src == entry_id:
                final_output = output
            outs = [n for n in self.graph.nodes if n.type == "output"]
            if outs:
                out_subtype = outs[0].subtype

        self.emit({
            "type": "graph_run_complete",
            "output": final_output,
            "output_subtype": out_subtype,
        })
        return {
            "ok": True,
            "output": final_output,
            "output_subtype": out_subtype,
        }

    def _run_node(self, node_id: str, message: str, parents: list[str]) -> str:
        if node_id in parents:
            return f"[cycle to {node_id} suppressed]"
        node = self.nodes_by_id[node_id]
        if node.type != "agent":
            raise ValueError(
                f"Cannot execute non-agent node '{node_id}' (type={node.type})"
            )

        # Build the tool list: skills + delegations.
        tools: list[Callable] = []
        for src_id in self._skill_sources_for(node_id):
            src = self.nodes_by_id[src_id]
            tools.append(build_skill_tool(src, run_id=self.run_id))
        for child_id in self._delegate_children(node_id):
            tools.append(self._delegate_tool(node_id, child_id, parents))

        self.emit({
            "type": "node_started",
            "node_id": node_id,
            "label": node.label,
            "model_tier": node.model_tier,
        })

        emit = self.emit

        def per_node_event(ev: dict) -> None:
            ev = {**ev, "node_id": node_id}
            emit(ev)

        agent_max_tokens = (
            self.config.get("pipeline", {}).get("agent_max_tokens")
        )
        runtime = AgentRuntime(
            name=node.label or node.id,
            system_prompt=node.system_prompt or "You are a helpful assistant.",
            tools=tools,
            client=self.client,
            model=get_model_name(self.config, node.model_tier),
            max_iterations=node.max_iterations or 5,
            event_callback=per_node_event,
            max_tokens=agent_max_tokens,
        )
        result = runtime.run(message)

        self.emit({
            "type": "node_finished",
            "node_id": node_id,
            "output_preview": (result.output or "")[:200],
            "tokens": result.token_usage,
            "iterations": result.iterations,
            "hit_max_iterations": result.hit_max_iterations,
        })
        return result.output


def try_parse_pitch_deck(output: str) -> dict | None:
    """If output is a JSON object with the pitch-deck shape, return it; else None."""
    try:
        # Tolerate fenced code blocks.
        s = output.strip()
        if s.startswith("```"):
            s = s.strip("`")
            if s.lower().startswith("json"):
                s = s[4:]
            s = s.strip()
        obj = json.loads(s)
        if isinstance(obj, dict) and "title_page" in obj and "logline" in obj:
            return obj
    except Exception:
        pass
    return None
