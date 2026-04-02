"""Tests for the FastAPI web server."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_index_serves_html(client):
    """GET / returns the frontend HTML page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AGENTIC PRODUCTION" in response.text


def test_static_files(client):
    """Static file route is mounted."""
    response = client.get("/static/index.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_websocket_rejects_empty_brief(client):
    """WebSocket rejects a run request with no brief."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "run", "brief": ""})
        data = ws.receive_json()
        assert data["type"] == "error"
        assert "No brief" in data["message"]


def test_download_returns_400_for_invalid_run_id():
    """Download endpoint returns 400 for malformed run IDs."""
    client = TestClient(app)
    response = client.get("/download/nonexistent-run")
    assert response.status_code == 400


def test_download_returns_404_when_no_file():
    """Download endpoint returns 404 for valid but unknown run ID."""
    client = TestClient(app)
    response = client.get("/download/aabbccddeeff")
    assert response.status_code == 404


def test_health_endpoint(client):
    """GET /health returns ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_endpoint_demo_disabled_by_default(client):
    """GET /config returns demo_enabled=false by default."""
    response = client.get("/config")
    assert response.status_code == 200
    assert response.json()["demo_enabled"] is False


def test_config_endpoint_demo_enabled():
    """GET /config reflects DEMO_ENABLED flag."""
    with patch.object(app_module, "DEMO_ENABLED", True):
        c = TestClient(app)
        response = c.get("/config")
        assert response.json()["demo_enabled"] is True


def test_websocket_rejects_demo_when_disabled(client):
    """WebSocket rejects demo requests when ENABLE_DEMO is not set."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "demo"})
        data = ws.receive_json()
        assert data["type"] == "error"
        assert "disabled" in data["message"].lower()


# -- Rate limiter tests --

from app import RateLimiter


def test_rate_limiter_allows_within_limits():
    """Requests within limits are allowed."""
    rl = RateLimiter(hourly_limit=3, daily_limit=5)
    assert rl.check() is None
    rl.record()
    rl.record()
    assert rl.check() is None  # 2 of 3 hourly used


def test_rate_limiter_blocks_at_hourly_limit():
    """Requests are blocked once the hourly limit is hit."""
    rl = RateLimiter(hourly_limit=2, daily_limit=100)
    rl.record()
    rl.record()
    msg = rl.check()
    assert msg is not None
    assert "2 runs per hour" in msg


def test_rate_limiter_blocks_at_daily_limit():
    """Requests are blocked once the daily limit is hit."""
    rl = RateLimiter(hourly_limit=100, daily_limit=3)
    rl.record()
    rl.record()
    rl.record()
    msg = rl.check()
    assert msg is not None
    assert "3 runs per day" in msg


def test_rate_limiter_hourly_window_expires(monkeypatch):
    """Old timestamps outside the hourly window don't count."""
    import time as _time

    rl = RateLimiter(hourly_limit=1, daily_limit=100)
    # Manually insert an old timestamp (2 hours ago)
    now = _time.monotonic()
    rl._timestamps = [now - 7_200]
    assert rl.check() is None  # Old entry shouldn't block


def test_websocket_rate_limits_pipeline_runs(client):
    """WebSocket returns error when global rate limit is exceeded."""
    # Temporarily lower the limit
    original_limit = app_module.rate_limiter.hourly_limit
    app_module.rate_limiter.hourly_limit = 0
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "run", "brief": "A test show"})
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "rate limit" in data["message"].lower()
    finally:
        app_module.rate_limiter.hourly_limit = original_limit
