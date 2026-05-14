"""Tool registry with auto-schema generation for OpenAI tool calling."""
import inspect
import json
from typing import Callable

# Type mapping from Python types to JSON schema types
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
}


def tool(func: Callable) -> Callable:
    """Decorator that marks a function as a tool."""
    func._is_tool = True
    return func


def get_openai_tools_schema(tools: list[Callable]) -> list[dict]:
    """Generate OpenAI-compatible tool schemas from decorated functions."""
    schemas = []
    for fn in tools:
        sig = inspect.signature(fn)
        properties = {}
        required = []
        for name, param in sig.parameters.items():
            annotation = param.annotation
            json_type = _TYPE_MAP.get(annotation, "string")
            properties[name] = {"type": json_type}
            if param.default is inspect.Parameter.empty:
                required.append(name)

        schemas.append({
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": (fn.__doc__ or "").strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return schemas


def execute_tool(name: str, args: dict, tools: list[Callable]) -> dict:
    """Execute a tool by name with the given arguments.

    Resilient to model-side malformed tool calls: unknown tool names and
    unexpected/missing kwargs are returned as structured error dicts rather
    than raised, so the ReAct loop can recover instead of crashing.
    """
    tool_map = {fn.__name__: fn for fn in tools}
    if name not in tool_map:
        return {
            "error": (
                f"Unknown tool: {name}. Available: {list(tool_map.keys())}"
            ),
        }
    fn = tool_map[name]
    sig = inspect.signature(fn)
    accepts_any_kwargs = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if accepts_any_kwargs:
        filtered = dict(args)
        ignored: list[str] = []
    else:
        allowed = {
            n for n, p in sig.parameters.items()
            if p.kind is not inspect.Parameter.VAR_POSITIONAL
        }
        filtered = {k: v for k, v in args.items() if k in allowed}
        ignored = [k for k in args.keys() if k not in allowed]
    try:
        result = fn(**filtered)
    except TypeError as exc:
        return {
            "error": (
                f"Tool {name} call failed: {exc}. "
                f"Provided args: {list(args.keys())}."
            ),
        }
    if ignored and isinstance(result, dict):
        result = {
            **result,
            "_warning": (
                f"Ignored unexpected args for {name}: {ignored}"
            ),
        }
    return result
