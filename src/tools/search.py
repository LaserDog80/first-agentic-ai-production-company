"""Web search tool using Tavily API with Linkup fallback."""
import logging
import os

import yaml

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


def _get_search_provider() -> str:
    """Return the active search provider setting.

    Resolution order: SEARCH_PROVIDER env var > config.yaml > 'auto'.
    """
    env_val = os.environ.get("SEARCH_PROVIDER", "").strip().lower()
    if env_val in ("tavily", "linkup", "auto"):
        return env_val

    # Fall back to config.yaml
    try:
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config.yaml"
        )
        with open(config_path, "r") as fh:
            cfg = yaml.safe_load(fh) or {}
        cfg_val = (
            cfg.get("tools", {})
            .get("search_provider", "")
            .strip()
            .lower()
        )
        if cfg_val in ("tavily", "linkup", "auto"):
            return cfg_val
    except Exception:
        pass

    return "auto"


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
    provider = _get_search_provider()
    logger.info("Search provider resolved to '%s'", provider)

    if provider == "tavily":
        return _search_tavily(query)

    if provider == "linkup":
        return _search_linkup(query)

    # provider == "auto": try Tavily first, fall back to Linkup
    tavily_err: Exception | None = None
    try:
        return _search_tavily(query)
    except Exception as exc:
        tavily_err = exc
        logger.warning(
            "Tavily search failed (%s), trying Linkup fallback",
            tavily_err,
        )
    try:
        return _search_linkup(query)
    except Exception as linkup_err:
        logger.error("Linkup fallback also failed: %s", linkup_err)
        return {
            "results": [],
            "error": (
                f"All search providers failed. "
                f"Tavily: {tavily_err}, Linkup: {linkup_err}"
            ),
        }
