# tests/test_tools.py
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from src.tools import tool, get_openai_tools_schema, execute_tool
from src.tools.search import web_search
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
    """Unknown tool names return a structured error instead of raising,
    so the ReAct loop can recover. See src/tools/__init__.py."""
    result = execute_tool("nonexistent", {}, [])
    assert "error" in result
    assert "nonexistent" in result["error"]


def test_execute_tool_ignores_unexpected_kwargs():
    """Models sometimes emit extra args (e.g. web_search(query=..., title=...)).
    The runtime should drop unknown kwargs and call the tool successfully
    rather than crashing the ReAct loop with a TypeError."""
    @tool
    def search(query: str) -> dict:
        """Search."""
        return {"query": query}

    result = execute_tool(
        "search", {"query": "hi", "title": "junk", "extra": 1}, [search],
    )
    assert result["query"] == "hi"
    assert "_warning" in result
    assert "title" in result["_warning"]
    assert "extra" in result["_warning"]


def test_execute_tool_missing_required_kwarg_returns_error():
    """Missing required args should be reported, not raised."""
    @tool
    def search(query: str) -> dict:
        """Search."""
        return {"query": query}

    result = execute_tool("search", {}, [search])
    assert "error" in result


# --- web_search (mocked) ---

TAVILY_RESULT = {
    "results": [
        {"title": "Test", "url": "http://test.com", "content": "Tavily"}
    ]
}

LINKUP_RESULT = MagicMock()
LINKUP_RESULT.results = [
    MagicMock(name="LinkItem", url="http://link.com", content="Linkup")
]
LINKUP_RESULT.results[0].name = "LinkItem"


@patch.dict(
    os.environ, {"SEARCH_PROVIDER": "tavily", "TAVILY_API_KEY": "test-key"}
)
@patch("src.tools.search.TavilyClient")
def test_web_search(mock_tavily_class):
    # Pin to tavily so this baseline test isn't affected by which provider
    # is primary in "auto" mode (see test_web_search_provider_auto_fallback).
    mock_client = MagicMock()
    mock_client.search.return_value = TAVILY_RESULT
    mock_tavily_class.return_value = mock_client

    result = web_search("lighthouse documentaries")
    assert "results" in result
    assert len(result["results"]) == 1


@patch.dict(os.environ, {"SEARCH_PROVIDER": "tavily", "TAVILY_API_KEY": "k"})
@patch("src.tools.search.TavilyClient")
def test_web_search_provider_tavily(mock_tavily_class):
    """SEARCH_PROVIDER=tavily should only call Tavily."""
    mock_client = MagicMock()
    mock_client.search.return_value = TAVILY_RESULT
    mock_tavily_class.return_value = mock_client

    result = web_search("query")
    assert result == TAVILY_RESULT
    mock_client.search.assert_called_once()


@patch.dict(
    os.environ, {"SEARCH_PROVIDER": "linkup", "LINKUP_API_KEY": "k"}
)
@patch("src.tools.search.LinkupClient")
def test_web_search_provider_linkup(mock_linkup_class):
    """SEARCH_PROVIDER=linkup should only call Linkup."""
    mock_client = MagicMock()
    mock_client.search.return_value = LINKUP_RESULT
    mock_linkup_class.return_value = mock_client

    result = web_search("query")
    assert "results" in result
    assert result["results"][0]["url"] == "http://link.com"
    mock_client.search.assert_called_once()


@patch.dict(
    os.environ,
    {"SEARCH_PROVIDER": "auto", "TAVILY_API_KEY": "k", "LINKUP_API_KEY": "k"},
)
@patch("src.tools.search.LinkupClient")
@patch("src.tools.search.TavilyClient")
def test_web_search_provider_auto_fallback(
    mock_tavily_class, mock_linkup_class
):
    """SEARCH_PROVIDER=auto should fall back to Tavily on Linkup failure."""
    mock_linkup_client = MagicMock()
    mock_linkup_client.search.side_effect = RuntimeError("boom")
    mock_linkup_class.return_value = mock_linkup_client

    mock_tavily_client = MagicMock()
    mock_tavily_client.search.return_value = TAVILY_RESULT
    mock_tavily_class.return_value = mock_tavily_client

    result = web_search("query")
    assert result == TAVILY_RESULT
    mock_linkup_client.search.assert_called_once()
    mock_tavily_client.search.assert_called_once()


@patch.dict(
    os.environ, {"LINKUP_API_KEY": "k", "TAVILY_API_KEY": "k"}, clear=False
)
@patch("src.tools.search.LinkupClient")
def test_web_search_provider_unset_defaults_auto(mock_linkup_class):
    """When SEARCH_PROVIDER is unset it should behave like 'auto' — Linkup first."""
    os.environ.pop("SEARCH_PROVIDER", None)
    mock_client = MagicMock()
    mock_client.search.return_value = LINKUP_RESULT
    mock_linkup_class.return_value = mock_client

    result = web_search("query")
    assert result["results"][0]["url"] == "http://link.com"


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


# --- docstring Args -> parameter descriptions (v3) ---

def test_schema_includes_param_descriptions_from_docstring():
    @tool
    def documented(query: str, region: str = "UK") -> dict:
        """Search for something.

        More detail on a second line.

        Args:
            query: What to search for, one topic per call.
            region: Region code, e.g. "UK" or "US".

        Returns:
            A dict.
        """
        return {}

    schema = get_openai_tools_schema([documented])[0]["function"]
    assert schema["description"].startswith("Search for something.")
    assert "Args:" not in schema["description"]
    assert "Returns:" not in schema["description"]
    props = schema["parameters"]["properties"]
    assert props["query"]["description"] == "What to search for, one topic per call."
    assert props["region"]["description"].startswith("Region code")
    assert schema["parameters"]["required"] == ["query"]


def test_schema_without_args_section_unchanged():
    @tool
    def plain(query: str) -> dict:
        """Just a description."""
        return {}

    schema = get_openai_tools_schema([plain])[0]["function"]
    assert schema["description"] == "Just a description."
    assert "description" not in schema["parameters"]["properties"]["query"]
