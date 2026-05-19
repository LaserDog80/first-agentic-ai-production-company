"""Tests for the cd_artist preset, generate_image skill, and the CD↔Artist loop."""
import json
from types import SimpleNamespace

import pytest

from src.graph.executor import GraphExecutor
from src.graph.presets import load_preset
from src.graph.schema import Graph, Node, validate_graph
from src.graph.skills import (
    SKILL_REGISTRY,
    build_skill_tool,
    list_available_skills,
)


def test_cd_artist_preset_exists_and_validates():
    data = load_preset("cd_artist")
    assert data is not None
    g = Graph.model_validate(data)
    assert validate_graph(g) == []


def test_cd_artist_preset_shape():
    data = load_preset("cd_artist")
    by_type = {n["type"] for n in data["nodes"]}
    assert by_type == {"input", "agent", "skill", "output"}
    # Exactly one output node, subtype "image".
    outs = [n for n in data["nodes"] if n["type"] == "output"]
    assert len(outs) == 1 and outs[0]["subtype"] == "image"
    # The skill node uses the generate_image skill.
    skills = [n for n in data["nodes"] if n["type"] == "skill"]
    assert any(n["skill_id"] == "generate_image" for n in skills)
    # CD has a delegate edge to the Artist; Artist has a skill edge from the
    # generate_image node.
    kinds = {(e["from"], e["to"], e["kind"]) for e in data["edges"]}
    delegate_edges = [k for k in kinds if k[2] == "delegate"]
    skill_edges = [k for k in kinds if k[2] == "skill"]
    assert len(delegate_edges) == 1
    assert len(skill_edges) == 1


def test_generate_image_registered_in_skill_registry():
    assert "generate_image" in SKILL_REGISTRY
    assert any(
        s["skill_id"] == "generate_image" for s in list_available_skills()
    )


def test_build_skill_tool_for_generate_image_returns_callable():
    node = Node(id="s", type="skill", skill_id="generate_image")
    fn = build_skill_tool(node, run_id="deadbeef0001")
    assert callable(fn)
    assert fn.__name__ == "generate_image"


def test_generate_image_uses_run_id_for_persistence(monkeypatch, tmp_path):
    """Tool should call fal, save to output/web/<run_id>/<seq>.png, and return URL."""
    from src.tools import generate_image as gi

    # Redirect the output directory into the tmp_path.
    monkeypatch.setattr(gi, "_OUTPUT_DIR", tmp_path / "web")
    monkeypatch.setattr(
        gi, "_call_fal",
        lambda prompt: {"url": f"https://stub.example/{prompt[:10]}.png"},
    )
    # Bypass the network download; just write a tiny file.
    def fake_save(image_url, run_id, seq):
        run_dir = tmp_path / "web" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        out = run_dir / f"{seq}.png"
        out.write_bytes(b"\x89PNG\r\n\x1a\n")
        return out
    monkeypatch.setattr(gi, "_save_image", fake_save)

    tool = gi.build_generate_image_tool(run_id="abc123def456")
    r1 = tool("a lighthouse on a cliff")
    r2 = tool("the same, with stormier sky")
    assert r1["image_url"] == "/output-image/abc123def456/1.png"
    assert r1["attempt"] == 1
    assert r2["image_url"] == "/output-image/abc123def456/2.png"
    assert r2["attempt"] == 2
    assert (tmp_path / "web" / "abc123def456" / "1.png").exists()
    assert (tmp_path / "web" / "abc123def456" / "2.png").exists()


def test_generate_image_surfaces_fal_errors(monkeypatch, tmp_path):
    """If fal.ai raises, the tool should return a structured error dict rather than crash."""
    from src.tools import generate_image as gi

    monkeypatch.setattr(gi, "_OUTPUT_DIR", tmp_path / "web")
    def boom(prompt):
        raise RuntimeError("fal exploded")
    monkeypatch.setattr(gi, "_call_fal", boom)

    tool = gi.build_generate_image_tool(run_id="abc123def456")
    r = tool("anything")
    assert "error" in r
    assert "fal exploded" in r["error"]
    assert r["attempt"] == 1


# ── full-loop smoke test with mocked LLM + mocked fal ────────────────────
def _stub_client(scripted_responses):
    """Scripted LLM responses: list of (content_or_None, tool_calls_or_None)."""
    iterator = iter(scripted_responses)

    def create(*, model, messages, tools=None, **kw):
        content, tool_calls = next(iterator)
        msg = SimpleNamespace(content=content, tool_calls=tool_calls)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )


def _tool_call(name, args, call_id="x"):
    return SimpleNamespace(
        id=call_id, type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def test_cd_artist_loop_runs_end_to_end(monkeypatch, tmp_path):
    """End-to-end: CD delegates → Artist calls generate_image → CD finalises."""
    from src.tools import generate_image as gi
    monkeypatch.setattr(gi, "_OUTPUT_DIR", tmp_path / "web")
    monkeypatch.setattr(
        gi, "_call_fal",
        lambda prompt: {"url": f"https://stub.example/{prompt[:6]}.png"},
    )
    def fake_save(image_url, run_id, seq):
        run_dir = tmp_path / "web" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        out = run_dir / f"{seq}.png"
        out.write_bytes(b"\x89PNG")
        return out
    monkeypatch.setattr(gi, "_save_image", fake_save)

    data = load_preset("cd_artist")
    g = Graph.model_validate(data)

    artist_label = next(
        n["label"] for n in data["nodes"]
        if n["type"] == "agent" and n["label"].lower() == "artist"
    )
    delegate_tool_name = "delegate_to_" + artist_label.lower()

    # CD: delegate once → finalize.
    # Artist: call generate_image → reply.
    script = [
        # CD turn 1: delegate to artist.
        (None, [_tool_call(delegate_tool_name, {"message": "a lighthouse at dusk"})]),
        # Artist turn 1: call generate_image.
        (None, [_tool_call("generate_image", {"prompt": "lighthouse at dusk, oil painting"})]),
        # Artist turn 2: respond to CD with URL + description.
        ("/output-image/<...>/1.png\nA moody oil painting of a lighthouse at dusk.", None),
        # CD turn 2: final answer.
        ("Final image looks great.\n/output-image/<...>/1.png", None),
    ]
    client = _stub_client(script)
    cfg = {
        "providers": {
            "primary": {"models": {"strong": "m", "research": "m", "utility": "m"}}
        }
    }

    events: list[dict] = []
    res = GraphExecutor(
        g, client, cfg, emit=events.append, run_id="abc123def456",
    ).run("Make me a moody lighthouse image.")

    assert res["ok"] is True
    assert res["output_subtype"] == "image"
    # The image was written under the run-id directory.
    assert (tmp_path / "web" / "abc123def456" / "1.png").exists()
    types = [e["type"] for e in events]
    assert "edge_fired" in types  # CD → Artist delegation fired
