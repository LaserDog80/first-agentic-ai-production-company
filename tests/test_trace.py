"""Tests for the trace package: transcript adapter, live hooks, API routes."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.trace.claude_adapter import (
    humanize_tool,
    load_transcript,
    normalize_transcript,
)
from src.trace.live import LiveBroker, LiveSession, normalize_hook_event

DEMO_PATH = Path(__file__).resolve().parent.parent / "static" / "demo" / "demo_session.jsonl"


@pytest.fixture()
def demo_text() -> str:
    return DEMO_PATH.read_text(encoding="utf-8")


@pytest.fixture()
def demo_trace(demo_text) -> dict:
    return normalize_transcript(demo_text)


# ── adapter: parsing ─────────────────────────────────────────────────────────

def test_load_transcript_ignores_junk_lines():
    text = "\n".join([
        "not json at all",
        json.dumps({"type": "queue-operation", "operation": "enqueue"}),
        json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
        json.dumps({"type": "mode", "mode": "normal"}),
        json.dumps([1, 2, 3]),
        json.dumps({"type": "assistant"}),  # no message dict → skipped
    ])
    records = load_transcript(text)
    assert len(records) == 1
    assert records[0]["type"] == "user"


def test_demo_trace_shape(demo_trace):
    assert demo_trace["version"] == 1
    assert demo_trace["title"].startswith("Our checkout tests")
    assert demo_trace["duration_s"] > 100
    ids = [a["id"] for a in demo_trace["agents"]]
    assert ids == ["main", "a1", "a2"]
    assert all(a["parent"] == "main" for a in demo_trace["agents"][1:])


def test_demo_trace_events_ordered_and_terminated(demo_trace):
    events = demo_trace["events"]
    ts = [ev["t"] for ev in events]
    assert ts == sorted(ts)
    assert events[0]["type"] == "user_message"
    assert events[-1]["type"] == "done"


def test_spawn_and_return_pair_up(demo_trace):
    events = demo_trace["events"]
    spawns = [ev for ev in events if ev["type"] == "spawn"]
    returns = [ev for ev in events if ev["type"] == "return"]
    assert {s["child"] for s in spawns} == {"a1", "a2"}
    assert {r["child"] for r in returns} == {"a1", "a2"}
    for s in spawns:  # every spawn precedes its matching return
        r = next(r for r in returns if r["child"] == s["child"])
        assert s["t"] < r["t"]


def test_sidechain_tools_attributed_to_subagent(demo_trace):
    events = demo_trace["events"]
    a1_tools = [ev for ev in events if ev["agent"] == "a1" and ev["type"] == "tool_start"]
    assert len(a1_tools) >= 2
    # tool_end for a subagent's call carries the subagent id, not main.
    a1_call_ids = {ev["call_id"] for ev in a1_tools}
    ends = [ev for ev in events if ev["type"] == "tool_end" and ev.get("call_id") in a1_call_ids]
    assert ends and all(ev["agent"] == "a1" for ev in ends)


def test_todo_and_error_results(demo_trace):
    events = demo_trace["events"]
    todos = [ev for ev in events if ev["type"] == "todo"]
    assert len(todos) == 2
    assert todos[0]["items"][0]["status"] == "in_progress"
    assert todos[-1]["items"][-1]["status"] == "completed"
    failures = [ev for ev in events if ev["type"] == "tool_end" and not ev["ok"]]
    assert len(failures) == 1
    assert failures[0]["summary"].startswith("failed:")


def test_token_accounting(demo_trace):
    totals = demo_trace["totals"]
    assert totals["out"] > 0 and totals["ctx_peak"] > 0
    per_agent = {a["id"]: a["tokens_out"] for a in demo_trace["agents"]}
    assert per_agent["a1"] > 0 and per_agent["a2"] > 0
    assert sum(per_agent.values()) == totals["out"]


def test_usage_deduped_by_request_id():
    """One API request emitting two transcript lines must count tokens once."""
    usage = {"input_tokens": 100, "output_tokens": 50,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    lines = [
        json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:00Z", "uuid": "u1",
                    "message": {"role": "user", "content": "go"}}),
        json.dumps({"type": "assistant", "timestamp": "2026-01-01T00:00:05Z",
                    "uuid": "u2", "requestId": "req_1",
                    "message": {"role": "assistant", "model": "m", "usage": usage,
                                "content": [{"type": "text", "text": "part one"}]}}),
        json.dumps({"type": "assistant", "timestamp": "2026-01-01T00:00:06Z",
                    "uuid": "u3", "requestId": "req_1",
                    "message": {"role": "assistant", "model": "m", "usage": usage,
                                "content": [{"type": "text", "text": "part two"}]}}),
    ]
    trace = normalize_transcript("\n".join(lines))
    assert trace["totals"]["out"] == 50


def test_command_wrapper_user_messages_skipped():
    lines = [
        json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:00Z", "uuid": "u1",
                    "message": {"role": "user", "content": "<command-name>/clear</command-name>"}}),
        json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:01Z", "uuid": "u2",
                    "message": {"role": "user", "content": "real question"}}),
    ]
    trace = normalize_transcript("\n".join(lines))
    msgs = [ev for ev in trace["events"] if ev["type"] == "user_message"]
    assert len(msgs) == 1
    assert msgs[0]["text"] == "real question"
    assert trace["title"] == "real question"


def test_humanize_tool_common_cases():
    assert humanize_tool("Read", {"file_path": "/a/b/app.py"})[0] == "Reading app.py"
    assert "pytest" in humanize_tool("Bash", {"command": "pytest -q"})[0]
    assert humanize_tool("WebSearch", {"query": "uk seaside towns"})[0].startswith("Searching the web")
    assert "mytool" in humanize_tool("mcp__server__my_tool", {})[0].replace(" ", "")


# ── live hooks ───────────────────────────────────────────────────────────────

def _hook(name: str, **extra) -> dict:
    return {"session_id": "s1", "hook_event_name": name, "cwd": "/w", **extra}


def test_hook_prompt_and_tool_flow():
    state = LiveSession("s1")
    evs = normalize_hook_event(state, _hook("UserPromptSubmit", prompt="fix the bug"))
    assert evs[0]["type"] == "user_message"

    evs = normalize_hook_event(state, _hook("PreToolUse", tool_name="Read",
                                            tool_input={"file_path": "/x/y.py"}))
    assert evs[0]["type"] == "tool_start" and evs[0]["agent"] == "main"

    evs = normalize_hook_event(state, _hook("PostToolUse", tool_name="Read",
                                            tool_input={"file_path": "/x/y.py"},
                                            tool_response={"stdout": "ok"}))
    assert evs[0]["type"] == "tool_end" and evs[0]["ok"] is True

    evs = normalize_hook_event(state, _hook("Stop"))
    assert evs[0]["type"] == "done"


def test_hook_task_attribution():
    state = LiveSession("s1")
    spawn = normalize_hook_event(state, _hook(
        "PreToolUse", tool_name="Task",
        tool_input={"description": "scan logs", "prompt": "p", "subagent_type": "Explore"}))
    assert spawn[0]["type"] == "spawn"
    child = spawn[0]["child"]

    # While the Task is open, tool events attribute to the subagent.
    evs = normalize_hook_event(state, _hook("PreToolUse", tool_name="Grep",
                                            tool_input={"pattern": "retry"}))
    assert evs[0]["agent"] == child

    ret = normalize_hook_event(state, _hook(
        "PostToolUse", tool_name="Task",
        tool_input={"description": "scan logs"},
        tool_response={"content": "found it"}))
    assert ret[0]["type"] == "return" and ret[0]["child"] == child

    evs = normalize_hook_event(state, _hook("PreToolUse", tool_name="Grep",
                                            tool_input={"pattern": "x"}))
    assert evs[0]["agent"] == "main"


def test_broker_buffers_and_lists():
    broker = LiveBroker()
    broker.ingest(_hook("UserPromptSubmit", prompt="hello"))
    broker.ingest(_hook("PreToolUse", tool_name="Bash", tool_input={"command": "ls"}))
    active = broker.list_active()
    assert active[0]["session_id"] == "s1"
    assert broker.session("s1").events[0]["type"] == "user_message"


# ── API routes ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from app import app
    return TestClient(app)


def test_theatre_route(client):
    resp = client.get("/theatre")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_demo_trace_endpoint(client):
    resp = client.get("/api/trace/demo")
    assert resp.status_code == 200
    trace = resp.json()
    assert [a["id"] for a in trace["agents"]] == ["main", "a1", "a2"]


def test_sessions_listing_and_trace(client, demo_text, tmp_path, monkeypatch):
    proj = tmp_path / "-home-demo-shop-backend"
    proj.mkdir(parents=True)
    (proj / "abc.jsonl").write_text(demo_text, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(tmp_path))

    resp = client.get("/api/sessions")
    sessions = resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["snippet"].startswith("Our checkout tests")

    resp = client.get(f"/api/sessions/{sessions[0]['id']}/trace")
    assert resp.status_code == 200
    assert resp.json()["title"].startswith("Our checkout tests")

    assert client.get("/api/sessions/ffffffffffff/trace").status_code == 404
    assert client.get("/api/sessions/NOT-VALID/trace").status_code == 400


def test_trace_upload(client, demo_text):
    resp = client.post("/api/trace/upload", content=demo_text.encode())
    assert resp.status_code == 200
    assert resp.json()["source"] == "claude-code-upload"

    resp = client.post("/api/trace/upload", content=b"garbage\nnot a transcript")
    assert resp.status_code == 400


def test_ingest_and_live_websocket(client):
    session = {"session_id": "livetest"}
    resp = client.post("/ingest", json={**session, "hook_event_name": "UserPromptSubmit",
                                        "prompt": "build me a thing"})
    assert resp.status_code == 200 and resp.json()["events"] == 1

    with client.websocket_connect("/ws/live?session=livetest") as ws:
        backlog = ws.receive_json()
        assert backlog["type"] == "backlog"
        assert backlog["events"][0]["type"] == "user_message"

        client.post("/ingest", json={**session, "hook_event_name": "PreToolUse",
                                     "tool_name": "Bash", "tool_input": {"command": "ls"}})
        msg = ws.receive_json()
        assert msg["type"] == "trace_event"
        assert msg["event"]["type"] == "tool_start"


def test_ingest_rejects_bad_payloads(client):
    assert client.post("/ingest", content=b"{not json").status_code == 400
    assert client.post("/ingest", json=[1, 2]).status_code == 400
