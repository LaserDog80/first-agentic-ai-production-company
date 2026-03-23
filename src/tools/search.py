"""Web search tool using Tavily API."""
import os
from src.tools import tool

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore


@tool
def web_search(query: str) -> dict:
    """Search the web for information relevant to the research brief."""
    try:
        if TavilyClient is None:
            raise ImportError("tavily-python is not installed")
        api_key = os.environ.get("TAVILY_API_KEY", "")
        client = TavilyClient(api_key=api_key)
        return client.search(query, search_depth="advanced")
    except Exception as e:
        return {"results": [], "error": str(e)}
