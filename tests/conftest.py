# tests/conftest.py
"""Shared test fixtures."""
import pytest


@pytest.fixture
def mock_config():
    """Standard mock config dict for testing."""
    return {
        "providers": {"primary": {
            "base_url": "http://test", "api_key_env": "TEST_KEY",
            "models": {"strong": "m1", "research": "m2", "utility": "m3"},
        }},
        "agents": {
            "series_producer": {"model_tier": "strong", "max_iterations": 5},
            "producer": {"model_tier": "strong", "max_iterations": 5},
            "researcher": {"model_tier": "research", "max_iterations": 5},
            "director": {"model_tier": "strong", "max_iterations": 5},
            "production_manager": {"model_tier": "strong", "max_iterations": 5},
        },
        "pipeline": {"max_rework_cycles": 2, "agent_timeout_seconds": 60},
        "tools": {"tavily": {"api_key_env": "TAVILY_KEY", "search_depth": "advanced"}},
    }
