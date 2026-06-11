"""Tests for the graph schema, validator, executor, and presets."""
import json
from types import SimpleNamespace

import pytest

from src.graph.executor import GraphExecutor, try_parse_pitch_deck
from src.graph.presets import list_presets, load_preset
from src.graph.schema import Graph, Node, Edge, validate_graph
from src.graph.skills import build_skill_tool, list_available_skills


# ── schema/validator ──────────────────────────────────────────────────────
def _minimal():
    return {
        "id": "g", "name": "g", "entry_node_id": "n_in",
        "nodes": [
            {"id": "n_in",  "type": "input",  "label": "Brief"},
            {"id": "n_a",   "type": "agent",  "label": "A", "system_prompt": "."},
            {"id": "n_out", "type": "output", "label": "Out"},
        ],
        "edges": [
            {"id": "e1", "from": "n_in", "to": "n_a", "kind": "input"},
            {"id": "e2", "from": "n_a",  "to": "n_out", "kind": "output"},
        ],
    }


def test_minimal_graph_is_valid():
    g = Graph.model_validate(_minimal())
    assert validate_graph(g) == []


def test_rejects_missing_input():
    d = _minimal()
    d["nodes"] = [n for n in d["nodes"] if n["type"] != "input"]
    d["edges"] = [e for e in d["edges"] if e["from"] != "n_in"]
    g = Graph.model_validate(d)
    assert any("input" in e for e in validate_graph(g))


def test_rejects_skill_edge_to_non_agent():
    d = _minimal()
    d["nodes"].append({"id": "n_skill", "type": "skill", "skill_id": "web_search"})
    d["edges"].append({"id": "e3", "from": "n_skill", "to": "n_out", "kind": "skill"})
    g = Graph.model_validate(d)
    errs = validate_graph(g)
    assert any("must be an agent" in e for e in errs)


def test_rejects_cycle_in_delegation():
    d = _minimal()
    d["nodes"].append({"id": "n_b", "type": "agent", "system_prompt": "."})
    d["edges"].append({"id": "ed1", "from": "n_a", "to": "n_b", "kind": "delegate"})
    d["edges"].append({"id": "ed2", "from": "n_b", "to": "n_a", "kind": "delegate"})
    g = Graph.model_validate(d)
    errs = validate_graph(g)
    assert any("Cycle" in e for e in errs)


# ── presets ───────────────────────────────────────────────────────────────
def test_presets_listing():
    ids = {p["id"] for p in list_presets()}
    assert "pitch_deck" in ids
    assert "research_assistant" in ids


def test_all_presets_validate():
    for p in list_presets():
        raw = load_preset(p["id"])
        g = Graph.model_validate(raw)
        assert validate_graph(g) == [], f"{p['id']} failed: {validate_graph(g)}"


def test_load_preset_path_traversal_blocked():
    assert load_preset("../../etc/passwd") is None
    assert load_preset("..") is None


# ── skills ────────────────────────────────────────────────────────────────
def test_list_available_skills():
    skills = list_available_skills()
    assert {s["skill_id"] for s in skills} >= {"web_search", "lookup_rates"}


def test_build_skill_tool_for_text_source():
    node = Node(id="s", type="source", label="Memo", source_value="hello world")
    tool_fn = build_skill_tool(node)
    res = tool_fn()
    assert res["text"] == "hello world"
    assert tool_fn.__name__.startswith("read_source_")


# ── executor ──────────────────────────────────────────────────────────────
def _stub_client(scripted_responses):
    """scripted_responses: list of (content_or_None, tool_calls_or_None)."""
    iterator = iter(scripted_responses)

    def create(*, model, messages, tools=None, **kw):
        content, tool_calls = next(iterator)
        msg = SimpleNamespace(content=content, tool_calls=tool_calls)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _tool_call(name, args, call_id="x"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def test_executor_runs_simple_agent_and_emits_events():
    """research_assistant preset structure: input -> agent (with skill) -> output."""
    g = Graph.model_validate({
        "id": "t", "name": "t", "entry_node_id": "in",
        "nodes": [
            {"id": "in",  "type": "input"},
            {"id": "a",   "type": "agent", "label": "A", "system_prompt": "."},
            {"id": "out", "type": "output"},
        ],
        "edges": [
            {"id": "e1", "from": "in", "to": "a",   "kind": "input"},
            {"id": "e2", "from": "a",  "to": "out", "kind": "output"},
        ],
    })
    client = _stub_client([("hello world", None)])
    cfg = {"providers": {"primary": {"models": {"strong": "m", "research": "m", "utility": "m"}}}}

    events = []
    res = GraphExecutor(g, client, cfg, emit=events.append).run("brief")
    assert res["ok"] is True
    assert res["output"] == "hello world"
    types = [e["type"] for e in events]
    assert types[0] == "graph_run_start"
    assert "node_started" in types
    assert "node_finished" in types
    assert types[-1] == "graph_run_complete"


def test_executor_delegation_fires_edges():
    g = Graph.model_validate({
        "id": "t", "name": "t", "entry_node_id": "in",
        "nodes": [
            {"id": "in",  "type": "input"},
            {"id": "a",   "type": "agent", "label": "A", "system_prompt": "."},
            {"id": "b",   "type": "agent", "label": "B", "system_prompt": "."},
            {"id": "out", "type": "output"},
        ],
        "edges": [
            {"id": "e1", "from": "in", "to": "a",   "kind": "input"},
            {"id": "e2", "from": "a",  "to": "b",   "kind": "delegate"},
            {"id": "e3", "from": "a",  "to": "out", "kind": "output"},
        ],
    })
    # A: call delegate_to_b, then return final.
    # B: final immediately.
    client = _stub_client([
        (None, [_tool_call("delegate_to_b", {"message": "hi"})]),
        ("B response", None),
        ("A final", None),
    ])
    cfg = {"providers": {"primary": {"models": {"strong": "m", "research": "m", "utility": "m"}}}}

    events = []
    res = GraphExecutor(g, client, cfg, emit=events.append).run("brief")
    assert res["ok"] is True
    types = [e["type"] for e in events]
    assert "edge_fired" in types
    assert types.count("node_started") == 2  # A and B
    assert types.count("node_finished") == 2


def test_try_parse_pitch_deck_rejects_garbage():
    assert try_parse_pitch_deck("nope") is None
    assert try_parse_pitch_deck("{}") is None


def test_try_parse_pitch_deck_accepts_minimal():
    obj = {"title_page": {"working_title": "X"}, "logline": "L"}
    assert try_parse_pitch_deck(json.dumps(obj)) == obj
    fenced = "```json\n" + json.dumps(obj) + "\n```"
    assert try_parse_pitch_deck(fenced) == obj


def test_executor_output_edge_selects_feeding_node():
    """The graph result must be the output of the agent wired to OUTPUT,
    not whatever the entry agent happened to return (v3 fix)."""
    g = Graph.model_validate({
        "id": "t", "name": "t", "entry_node_id": "in",
        "nodes": [
            {"id": "in",  "type": "input"},
            {"id": "a",   "type": "agent", "label": "A", "system_prompt": "."},
            {"id": "b",   "type": "agent", "label": "B", "system_prompt": "."},
            {"id": "out", "type": "output", "subtype": "pitch_deck"},
        ],
        "edges": [
            {"id": "e1", "from": "in", "to": "a",   "kind": "input"},
            {"id": "e2", "from": "a",  "to": "b",   "kind": "delegate"},
            {"id": "e3", "from": "b",  "to": "out", "kind": "output"},
        ],
    })
    client = _stub_client([
        (None, [_tool_call("delegate_to_b", {"message": "hi"})]),
        ("B response", None),
        ("A final", None),
    ])
    cfg = {"providers": {"primary": {"models": {"strong": "m", "research": "m", "utility": "m"}}}}
    res = GraphExecutor(g, client, cfg, emit=lambda e: None).run("brief")
    assert res["ok"] is True
    assert res["output"] == "B response"
    assert res["output_subtype"] == "pitch_deck"


def test_executor_output_subtype_from_connected_node():
    """output_subtype comes from the node the output edge actually targets,
    not from whichever output node happens to be first in the list."""
    g = Graph.model_validate({
        "id": "t", "name": "t", "entry_node_id": "in",
        "nodes": [
            {"id": "in",  "type": "input"},
            {"id": "a",   "type": "agent", "label": "A", "system_prompt": "."},
            {"id": "out_decoy", "type": "output", "subtype": "pitch_deck"},
            {"id": "out_real",  "type": "output", "subtype": "image"},
        ],
        "edges": [
            {"id": "e1", "from": "in", "to": "a",        "kind": "input"},
            {"id": "e2", "from": "a",  "to": "out_real", "kind": "output"},
        ],
    })
    client = _stub_client([("done", None)])
    cfg = {"providers": {"primary": {"models": {"strong": "m", "research": "m", "utility": "m"}}}}
    res = GraphExecutor(g, client, cfg, emit=lambda e: None).run("brief")
    assert res["output_subtype"] == "image"


def test_executor_clamps_max_iterations():
    g = Graph.model_validate(_minimal())
    cfg = {
        "providers": {"primary": {"models": {"strong": "m"}}},
        "limits": {"max_iterations_per_node": 3},
    }
    ex = GraphExecutor(g, _stub_client([]), cfg)
    node = ex.nodes_by_id["n_a"]
    node.max_iterations = 99
    assert ex._max_iterations_for(node) == 3
    node.max_iterations = 2
    assert ex._max_iterations_for(node) == 2
    node.max_iterations = 0  # unset -> default, still within limit
    assert ex._max_iterations_for(node) == 3


def test_executor_passes_timeout_from_config():
    g = Graph.model_validate(_minimal())
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        from types import SimpleNamespace as NS
        return NS(
            choices=[NS(message=NS(content="ok", tool_calls=None))],
            usage=NS(prompt_tokens=1, completion_tokens=1),
        )

    from types import SimpleNamespace as NS
    client = NS(chat=NS(completions=NS(create=create)))
    cfg = {
        "providers": {"primary": {"models": {"strong": "m"}}},
        "pipeline": {"agent_timeout_seconds": 123},
    }
    GraphExecutor(g, client, cfg).run("brief")
    assert seen.get("timeout") == 123


def test_executor_cancellation():
    import threading
    g = Graph.model_validate(_minimal())
    cfg = {"providers": {"primary": {"models": {"strong": "m"}}}}
    cancel = threading.Event()
    cancel.set()
    events = []
    res = GraphExecutor(
        g, _stub_client([("never", None)]), cfg,
        emit=events.append, cancel_event=cancel,
    ).run("brief")
    assert res["ok"] is False
    assert res.get("cancelled") is True
    assert any(
        e["type"] == "graph_run_error" and e.get("cancelled") for e in events
    )


def test_executor_reports_token_totals_and_cost():
    g = Graph.model_validate(_minimal())
    cfg = {
        "providers": {"primary": {"models": {"strong": "m"}}},
        "pricing": {"strong": {"prompt": 1.0, "completion": 2.0}},
    }
    events = []
    res = GraphExecutor(
        g, _stub_client([("ok", None)]), cfg, emit=events.append,
    ).run("brief")
    assert res["tokens"] == {"prompt": 1, "completion": 1}
    # 1 prompt tok @ $1/1M + 1 completion tok @ $2/1M
    assert res["cost_usd"] == pytest.approx(3e-6)
    finished = [e for e in events if e["type"] == "node_finished"][0]
    assert finished["model_tier"] == "strong"
    assert finished["cost_usd"] == pytest.approx(3e-6)


# ── validator limits ──────────────────────────────────────────────────────
def test_validator_rejects_excessive_max_iterations():
    d = _minimal()
    d["nodes"][1]["max_iterations"] = 999
    g = Graph.model_validate(d)
    errs = validate_graph(g, limits={"max_iterations_per_node": 15})
    assert any("max_iterations" in e for e in errs)


def test_validator_rejects_too_many_agents():
    d = _minimal()
    for i in range(20):
        d["nodes"].append({"id": f"extra_{i}", "type": "agent", "system_prompt": "."})
    g = Graph.model_validate(d)
    errs = validate_graph(g, limits={"max_agent_nodes": 12})
    assert any("Too many agent nodes" in e for e in errs)


def test_validator_rejects_multiple_input_edges():
    d = _minimal()
    d["nodes"].append({"id": "n_b", "type": "agent", "system_prompt": "."})
    d["edges"].append({"id": "e9", "from": "n_in", "to": "n_b", "kind": "input"})
    g = Graph.model_validate(d)
    errs = validate_graph(g)
    assert any("input edge" in e for e in errs)
