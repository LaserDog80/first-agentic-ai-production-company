"""Global tool registry for pipeline agent orchestration.

Tools are registered by name and can be looked up by pipelines at runtime.
Each pipeline declares which tools its agents need; the registry resolves them.
"""

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Singleton-style registry for tools available to pipelines.

    Tools are registered with a unique name and can be retrieved individually
    or in bulk. Pipelines reference tools by name in their configs.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}

    def register(self, name: str, func: Callable) -> None:
        """Register a tool function under the given name."""
        if name in self._tools:
            logger.warning("Overwriting existing tool: %s", name)
        self._tools[name] = func

    def get(self, name: str) -> Callable:
        """Retrieve a tool by name. Raises KeyError if not found."""
        if name not in self._tools:
            raise KeyError(
                f"Unknown tool: {name}. Available: {list(self._tools.keys())}"
            )
        return self._tools[name]

    def get_many(self, names: list[str]) -> list[Callable]:
        """Retrieve multiple tools by name."""
        return [self.get(name) for name in names]

    def list_tools(self) -> list[str]:
        """Return names of all registered tools."""
        return list(self._tools.keys())

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools


# Global registry instance
global_registry = ToolRegistry()


def register_tool(name: str | None = None):
    """Decorator to register a function in the global tool registry.

    Can be used as @register_tool() or @register_tool("custom_name").
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        global_registry.register(tool_name, func)
        return func

    if callable(name):
        # Used as @register_tool without parentheses
        func = name
        global_registry.register(func.__name__, func)
        return func

    return decorator
