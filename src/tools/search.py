"""Web search tool using Linkup API with Tavily fallback."""
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


_TOOLS_CONFIG: dict | None = None


def _tools_config() -> dict:
    """Read (and cache) the `tools:` section of config.yaml.

    Cached because every web_search call needs it and the file does not
    change while the server is running.
    """
    global _TOOLS_CONFIG
    if _TOOLS_CONFIG is None:
        try:
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "config.yaml"
            )
            with open(config_path, "r") as fh:
                cfg = yaml.safe_load(fh) or {}
            _TOOLS_CONFIG = cfg.get("tools", {}) or {}
        except Exception:
            _TOOLS_CONFIG = {}
    return _TOOLS_CONFIG


def _get_search_provider() -> str:
    """Return the active search provider setting.

    Resolution order: SEARCH_PROVIDER env var > config.yaml > 'auto'.
    """
    env_val = os.environ.get("SEARCH_PROVIDER", "").strip().lower()
    if env_val in ("tavily", "linkup", "auto"):
        return env_val

    cfg_val = str(_tools_config().get("search_provider", "")).strip().lower()
    if cfg_val in ("tavily", "linkup", "auto"):
        return cfg_val

    return "auto"


def _search_tavily(query: str) -> dict:
    """Search using Tavily API."""
    if TavilyClient is None:
        raise ImportError("tavily-python is not installed")
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not set")
    client = TavilyClient(api_key=api_key)
    depth = _tools_config().get("tavily", {}).get("search_depth", "advanced")
    return client.search(query, search_depth=depth)


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
        depth=_tools_config().get("linkup", {}).get("search_depth", "standard"),
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
    """Search the web for information relevant to the research brief.

    Args:
        query: A focused search query — one topic per call, like you would
            type into a search engine.
    """
    provider = _get_search_provider()
    logger.info("Search provider resolved to '%s'", provider)

    if provider == "tavily":
        return _search_tavily(query)

    if provider == "linkup":
        return _search_linkup(query)

    # provider == "auto": try Linkup first, fall back to Tavily
    linkup_err: Exception | None = None
    try:
        return _search_linkup(query)
    except Exception as exc:
        linkup_err = exc
        logger.warning(
            "Linkup search failed (%s), trying Tavily fallback",
            linkup_err,
        )
    try:
        return _search_tavily(query)
    except Exception as tavily_err:
        logger.error("Tavily fallback also failed: %s", tavily_err)
        return {
            "results": [],
            "error": (
                f"All search providers failed. "
                f"Linkup: {linkup_err}, Tavily: {tavily_err}"
            ),
        }
