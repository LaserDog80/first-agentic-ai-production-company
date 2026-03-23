# tests/test_tools.py
import json
import pytest
from unittest.mock import patch, MagicMock
from src.tools import tool, get_openai_tools_schema, execute_tool
from src.tools.search import web_search
from src.tools.rework import request_rework, approve, flag_gap
from src.tools.research import create_reference_research
from src.tools.rates import lookup_rates


# --- Tool registry ---

def test_tool_decorator_registers():
    """The @tool decorator should make a function discoverable."""
    @tool
    def sample_tool(query: str) -> dict:
        """A sample tool for testing."""
        return {"result": query}

    schema = get_openai_tools_schema([sample_tool])
    assert len(schema) == 1
    assert schema[0]["type"] == "function"
    assert schema[0]["function"]["name"] == "sample_tool"


def test_execute_tool():
    @tool
    def add(a: int, b: int) -> dict:
        """Add two numbers."""
        return {"sum": a + b}

    result = execute_tool("add", {"a": 2, "b": 3}, [add])
    assert result == {"sum": 5}


def test_execute_tool_unknown():
    with pytest.raises(KeyError):
        execute_tool("nonexistent", {}, [])


# --- request_rework ---

def test_request_rework():
    result = request_rework(agent="researcher", notes="Thin competitive landscape")
    assert result["status"] == "rework_requested"
    assert result["agent"] == "researcher"


# --- approve ---

def test_approve():
    result = approve()
    assert result["status"] == "approved"


# --- flag_gap ---

def test_flag_gap():
    result = flag_gap(description="No archive sources identified")
    assert result["status"] == "gap_flagged"
    assert "No archive" in result["description"]


# --- web_search (mocked) ---

@patch("src.tools.search.TavilyClient")
def test_web_search(mock_tavily_class):
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [{"title": "Test", "url": "http://test.com", "content": "Test content"}]
    }
    mock_tavily_class.return_value = mock_client

    result = web_search("lighthouse documentaries")
    assert "results" in result
    assert len(result["results"]) == 1


# --- reference_research (closure — model only sees `section` param) ---

def test_reference_research():
    mock_research = {
        "competitive_landscape": [{"title": "Test Show"}],
        "characters": [{"name": "Test Person"}],
    }
    ref_tool = create_reference_research(mock_research)
    result = ref_tool(section="competitive_landscape")
    assert result["section"] == "competitive_landscape"
    assert len(result["data"]) == 1


def test_reference_research_invalid_section():
    ref_tool = create_reference_research({})
    result = ref_tool(section="nonexistent")
    assert "error" in result


# --- lookup_rates ---

def test_lookup_rates():
    result = lookup_rates(role="camera operator", region="UK")
    assert "daily_rate" in result
    assert result["currency"] == "GBP"


def test_lookup_rates_unknown_role():
    result = lookup_rates(role="underwater basket weaver", region="UK")
    assert "daily_rate" in result  # returns a default/estimate
