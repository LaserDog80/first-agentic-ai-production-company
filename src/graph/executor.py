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
import threading
from typing import Any, Callable

from src.agent import AgentRuntime, RunCancelled
from src.graph.schema import Edge, Graph, Node
from src.graph.skills import _slug, build_skill_tool
from src.provider import get_model_name
from src.tools import tool

DEFAULT_MAX_ITERATIONS = 5


class GraphExecutor:
    """Run an agent graph against a brief and stream events."""

    def __init__(
        self,
        graph: Graph,
        client: Any,
        config: dict,
        emit: Callable[[dict], None] | None = None,
        run_id: str = "",
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.graph = graph
        self.client = client
        self.config = config
        self.emit = emit or (lambda _ev: None)
        self.run_id = run_id
        self.cancel_event = cancel_event
        self.nodes_by_id: dict[str, Node] = {n.id: n for n in graph.nodes}
        # Final output of every agent node that ran (last run wins if a node
        # is delegated to more than once). Lets the output edge mean what it
        # says: the graph result is the output of the node wired to OUTPUT.
        self.node_outputs: dict[str, str] = {}
        self.total_usage: dict = {"prompt": 0, "completion": 0}
        self.total_cost_usd: float = 0.0
        self._has_pricing = bool(config.get("pricing"))

    # ── edge index helpers ──────────────────────────────────────────────────
    def _edges(self, kind: str) -> list[Edge]:
        return [e for e in self.graph.edges if e.kind == kind]

    def _delegate_children(self, parent_id: str) -> list[str]:
        return [e.to for e in self._edges("delegate") if e.from_ == parent_id]

    def _skill_sources_for(self, agent_id: str) -> list[str]:
        return [e.from_ for e in self._edges("skill") if e.to == agent_id]

    def _input_targets(self) -> list[str]:
        return [e.to for e in self._edges("input")]

    def _output_edge(self) -> Edge | None:
        outs = self._edges("output")
        return outs[0] if outs else None

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
            f"Delegate a task to {child.label}.\n\n"
            "Args:\n"
            "    message: A clear, self-contained description of what you "
            "need them to do. Their full response is returned to you."
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
        except RunCancelled:
            self.emit({
                "type": "graph_run_error",
                "error": "Run stopped.",
                "cancelled": True,
            })
            return {"ok": False, "error": "Run stopped.", "cancelled": True}
        except Exception as exc:
            self.emit({
                "type": "graph_run_error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return {"ok": False, "error": str(exc)}

        # The graph result is the output of the agent wired to the OUTPUT
        # node. If that agent never ran (disconnected wiring), fall back to
        # the entry agent's output rather than failing the whole run.
        out_edge = self._output_edge()
        final_output = output
        out_subtype = ""
        if out_edge is not None:
            final_output = self.node_outputs.get(out_edge.from_, output)
            out_node = self.nodes_by_id.get(out_edge.to)
            if out_node is not None:
                out_subtype = out_node.subtype

        complete = {
            "type": "graph_run_complete",
            "output": final_output,
            "output_subtype": out_subtype,
            "tokens": dict(self.total_usage),
        }
        if self._has_pricing:
            complete["cost_usd"] = round(self.total_cost_usd, 6)
        self.emit(complete)
        return {
            "ok": True,
            "output": final_output,
            "output_subtype": out_subtype,
            "tokens": dict(self.total_usage),
            "cost_usd": round(self.total_cost_usd, 6) if self._has_pricing else None,
        }

    def _max_iterations_for(self, node: Node) -> int:
        limit = (
            self.config.get("limits", {}).get("max_iterations_per_node", 15)
        )
        wanted = node.max_iterations or DEFAULT_MAX_ITERATIONS
        return max(1, min(wanted, limit))

    def _cost_usd(self, tier: str, usage: dict) -> float | None:
        """Estimated cost of a node run from the per-tier pricing config."""
        pricing = self.config.get("pricing", {}).get(tier)
        if not pricing:
            return None
        return (
            usage.get("prompt", 0) / 1e6 * pricing.get("prompt", 0.0)
            + usage.get("completion", 0) / 1e6 * pricing.get("completion", 0.0)
        )

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

        pipeline_cfg = self.config.get("pipeline", {})
        runtime = AgentRuntime(
            name=node.label or node.id,
            system_prompt=node.system_prompt or "You are a helpful assistant.",
            tools=tools,
            client=self.client,
            model=get_model_name(self.config, node.model_tier),
            max_iterations=self._max_iterations_for(node),
            timeout=pipeline_cfg.get("agent_timeout_seconds"),
            event_callback=per_node_event,
            max_tokens=pipeline_cfg.get("agent_max_tokens"),
            tool_result_max_chars=(
                self.config.get("limits", {}).get("tool_result_max_chars")
            ),
            cancel_event=self.cancel_event,
        )
        result = runtime.run(message)
        self.node_outputs[node_id] = result.output

        usage = result.token_usage
        self.total_usage["prompt"] += usage.get("prompt", 0)
        self.total_usage["completion"] += usage.get("completion", 0)
        cost = self._cost_usd(node.model_tier, usage)
        if cost is not None:
            self.total_cost_usd += cost

        finished = {
            "type": "node_finished",
            "node_id": node_id,
            "output_preview": (result.output or "")[:200],
            "tokens": usage,
            "iterations": result.iterations,
            "hit_max_iterations": result.hit_max_iterations,
            "model_tier": node.model_tier,
        }
        if cost is not None:
            finished["cost_usd"] = round(cost, 6)
        self.emit(finished)
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
