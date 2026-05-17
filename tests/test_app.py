"""Tests for the playground FastAPI server."""
import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app, RateLimiter


@pytest.fixture
def client():
    return TestClient(app)


def test_index_serves_chooser(client):
    """GET / returns the mode-chooser HTML linking to /playground and /present."""
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'href="/playground"' in r.text
    assert 'href="/present"' in r.text


def test_playground_route(client):
    r = client.get("/playground")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "editor.js" in r.text


def test_present_route(client):
    r = client.get("/present")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "/static/js/sprites.js" in r.text


def test_sprites_module(client):
    r = client.get("/static/js/sprites.js")
    assert r.status_code == 200
    for cid in (
        "series_producer", "producer", "researcher",
        "director", "production_manager",
    ):
        assert f"id: '{cid}'" in r.text


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_static_editor_js(client):
    r = client.get("/static/js/editor.js")
    assert r.status_code == 200
    assert "NodeEditor" in r.text


def test_download_invalid_id(client):
    r = client.get("/download/nope")
    assert r.status_code == 400


def test_download_unknown_id(client):
    r = client.get("/download/aabbccddeeff")
    assert r.status_code == 404


def test_ws_list_presets(client):
    """list_presets returns the shipped presets and skill metadata."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "list_presets"})
        resp = ws.receive_json()
        assert resp["type"] == "presets"
        ids = {p["id"] for p in resp["presets"]}
        assert "pitch_deck" in ids
        assert "research_assistant" in ids
        assert any(s["skill_id"] == "web_search" for s in resp["skills"])


def test_ws_load_preset(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "load_preset", "id": "research_assistant"})
        resp = ws.receive_json()
        assert resp["type"] == "graph"
        assert resp["graph"]["id"] == "research_assistant"
        assert any(n["type"] == "agent" for n in resp["graph"]["nodes"])


def test_ws_load_unknown_preset(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "load_preset", "id": "does_not_exist"})
        resp = ws.receive_json()
        assert resp["type"] == "error"


def test_ws_validate_graph_ok(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "load_preset", "id": "research_assistant"})
        graph = ws.receive_json()["graph"]
        ws.send_json({"type": "validate_graph", "graph": graph})
        resp = ws.receive_json()
        assert resp["type"] == "validation"
        assert resp["ok"] is True


def test_ws_validate_graph_rejects_bad(client):
    bad = {"id": "x", "name": "x", "entry_node_id": "missing", "nodes": [], "edges": []}
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "validate_graph", "graph": bad})
        resp = ws.receive_json()
        assert resp["type"] == "validation"
        assert resp["ok"] is False
        assert resp["errors"]


def test_ws_run_graph_requires_brief(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "run_graph", "brief": "", "graph": {}})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "brief" in resp["message"].lower()


def test_ws_unknown_message_type(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "frobnicate"})
        resp = ws.receive_json()
        assert resp["type"] == "error"


def test_rate_limiter_allows_within_limits():
    rl = RateLimiter(hourly_limit=3, daily_limit=5)
    assert rl.check() is None
    rl.record(); rl.record()
    assert rl.check() is None


def test_rate_limiter_blocks_at_hourly_limit():
    rl = RateLimiter(hourly_limit=2, daily_limit=100)
    rl.record(); rl.record()
    msg = rl.check()
    assert msg is not None
    assert "per hour" in msg


def test_rate_limiter_window_expires():
    import time as _time
    rl = RateLimiter(hourly_limit=1, daily_limit=100)
    rl._timestamps = [_time.monotonic() - 7_200]
    assert rl.check() is None


def test_ws_run_graph_blocked_by_rate_limit(client):
    original = app_module.rate_limiter.hourly_limit
    app_module.rate_limiter.hourly_limit = 0
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "load_preset", "id": "research_assistant"})
            graph = ws.receive_json()["graph"]
            ws.send_json({"type": "run_graph", "brief": "test", "graph": graph})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "limit" in resp["message"].lower()
    finally:
        app_module.rate_limiter.hourly_limit = original
