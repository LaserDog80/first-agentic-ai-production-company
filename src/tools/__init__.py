"""Tool registry with auto-schema generation for OpenAI tool calling."""
import inspect
import re
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


def _parse_docstring(doc: str | None) -> tuple[str, dict[str, str]]:
    """Split a docstring into (description, {param: description}).

    Understands a Google-style ``Args:`` section; the section is removed
    from the main description and each ``name: text`` entry (including
    indented continuation lines) becomes that parameter's description.
    """
    if not doc:
        return "", {}
    lines = doc.strip().splitlines()
    desc_lines: list[str] = []
    param_descs: dict[str, str] = {}
    in_args = False
    current: str | None = None
    param_indent: int | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.lower() in ("args:", "arguments:"):
            in_args = True
            current = None
            param_indent = None
            continue
        if in_args and stripped.lower() in ("returns:", "raises:", "yields:"):
            in_args = False
            current = None
            continue
        if in_args:
            if not stripped:
                continue
            indent = len(line) - len(line.lstrip())
            match = re.match(r"^([A-Za-z_]\w*)\s*:\s*(.*)$", stripped)
            # A new `name: text` entry sits at the params' own indent level;
            # anything indented deeper continues the previous description.
            if match and (param_indent is None or indent <= param_indent):
                if param_indent is None:
                    param_indent = indent
                current = match.group(1)
                param_descs[current] = match.group(2).strip()
            elif current:
                param_descs[current] = (
                    param_descs[current] + " " + stripped
                ).strip()
            continue
        desc_lines.append(line)
    return "\n".join(desc_lines).strip(), param_descs


def get_openai_tools_schema(tools: list[Callable]) -> list[dict]:
    """Generate OpenAI-compatible tool schemas from decorated functions.

    Parameter descriptions come from the function docstring's ``Args:``
    section — models call tools far more reliably when each argument says
    what it expects rather than leaving semantics to the name alone.
    """
    schemas = []
    for fn in tools:
        description, param_descs = _parse_docstring(fn.__doc__)
        sig = inspect.signature(fn)
        properties = {}
        required = []
        for name, param in sig.parameters.items():
            annotation = param.annotation
            json_type = _TYPE_MAP.get(annotation, "string")
            prop: dict = {"type": json_type}
            if name in param_descs:
                prop["description"] = param_descs[name]
            properties[name] = prop
            if param.default is inspect.Parameter.empty:
                required.append(name)

        schemas.append({
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": description,
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
