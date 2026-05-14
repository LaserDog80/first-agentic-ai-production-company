"""Generic ReAct agent runtime for tool-augmented LLM calls."""
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from src.tools import execute_tool, get_openai_tools_schema


@dataclass
class AgentResult:
    """Result returned by AgentRuntime.run()."""

    output: str
    tool_calls: list[dict] = field(default_factory=list)
    iterations: int = 0
    token_usage: dict = field(default_factory=lambda: {"prompt": 0, "completion": 0})
    hit_max_iterations: bool = False


class AgentRuntime:
    """Generic ReAct loop that drives a single agent.

    Calls the LLM, executes any requested tools, feeds results back, and
    repeats until the model returns a final text response or max_iterations
    is reached.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        tools: list[Callable],
        client: Any,
        model: str,
        max_iterations: int,
        timeout: int | None = None,
        event_callback: Any = None,
        max_tokens: int | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.client = client
        self.model = model
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.tool_schemas = get_openai_tools_schema(tools) if tools else []
        self._event_callback = event_callback
        self.max_tokens = max_tokens

    def run(self, user_message: str) -> AgentResult:
        """Execute the ReAct loop for the given user message.

        Returns an AgentResult with the final output, tool call history,
        iteration count, token usage, and whether max iterations was hit.
        """
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        tool_calls_log: list[dict] = []
        token_usage: dict = {"prompt": 0, "completion": 0}
        iterations = 0
        last_content = ""

        while iterations < self.max_iterations:
            iterations += 1

            # Build API call kwargs — only include tools when there are schemas
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
            }
            if self.tool_schemas:
                kwargs["tools"] = self.tool_schemas
            if self.timeout is not None:
                kwargs["timeout"] = self.timeout
            if self.max_tokens is not None:
                kwargs["max_tokens"] = self.max_tokens

            response = self.client.chat.completions.create(**kwargs)

            # Accumulate token usage
            token_usage["prompt"] += response.usage.prompt_tokens
            token_usage["completion"] += response.usage.completion_tokens

            choice = response.choices[0]
            message = choice.message

            if message.tool_calls:
                # Append the assistant turn (with tool_calls) to history
                messages.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ],
                })

                # Execute each tool and append results
                for tc in message.tool_calls:
                    tool_name = tc.function.name
                    tool_args = json.loads(tc.function.arguments)
                    if self._event_callback:
                        try:
                            self._event_callback({
                                "type": "tool_call",
                                "agent": self.name,
                                "tool": tool_name,
                                "args": tool_args,
                                "message": f"Using {tool_name}...",
                            })
                        except Exception:
                            pass
                    tool_result = execute_tool(tool_name, tool_args, self.tools)

                    tool_calls_log.append({
                        "name": tool_name,
                        "args": tool_args,
                        "result": tool_result,
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result),
                    })

            else:
                # Model produced a final text response
                return AgentResult(
                    output=message.content or "",
                    tool_calls=tool_calls_log,
                    iterations=iterations,
                    token_usage=token_usage,
                    hit_max_iterations=False,
                )

            last_content = message.content or ""

        # max_iterations reached without a final text response
        return AgentResult(
            output=last_content,
            tool_calls=tool_calls_log,
            iterations=iterations,
            token_usage=token_usage,
            hit_max_iterations=True,
        )
