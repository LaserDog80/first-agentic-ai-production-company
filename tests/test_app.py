"""Tests for the FastAPI web server."""
import pytest
from fastapi.testclient import TestClient

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
