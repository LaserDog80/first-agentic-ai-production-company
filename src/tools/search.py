"""Web search tool using Tavily API with Linkup fallback."""
import logging
import os
from src.tools import tool

logger = logging.getLogger(__name__)

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore

try:
    from linkup import LinkupClient
except ImportError:
    LinkupClient = None  # type: ignore


def _search_tavily(query: str) -> dict:
    """Search using Tavily API."""
    if TavilyClient is None:
        raise ImportError("tavily-python is not installed")
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not set")
    client = TavilyClient(api_key=api_key)
    return client.search(query, search_depth="advanced")


def _search_linkup(query: str) -> dict:
    """Search using Linkup API, returning Tavily-compatible format."""
    if LinkupClient is None:
        raise ImportError("linkup-sdk is not installed")
    api_key = os.environ.get("LINKUP_API_KEY", "")
    if not api_key:
        raise ValueError("LINKUP_API_KEY not set")
    client = LinkupClient(api_key=api_key)
    response = client.search(
        query=query,
        depth="standard",
        output_type="searchResults",
    )
    # Normalize to Tavily-compatible format
    results = []
    for item in response.results:
        results.append({
            "title": item.name,
            "url": item.url,
            "content": item.content,
        })
    return {"results": results}


@tool
def web_search(query: str) -> dict:
    """Search the web for information relevant to the research brief."""
    # Try Tavily first, fall back to Linkup
    try:
        return _search_tavily(query)
    except Exception as tavily_err:
        logger.warning("Tavily search failed (%s), trying Linkup fallback", tavily_err)
    try:
        return _search_linkup(query)
    except Exception as linkup_err:
        logger.error("Linkup fallback also failed: %s", linkup_err)
        return {"results": [], "error": f"All search providers failed. Tavily: {tavily_err}, Linkup: {linkup_err}"}
