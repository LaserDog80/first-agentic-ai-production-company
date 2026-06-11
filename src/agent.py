"""Generic ReAct agent runtime for tool-augmented LLM calls."""
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from src.tools import execute_tool, get_openai_tools_schema

logger = logging.getLogger(__name__)


class RunCancelled(Exception):
    """Raised when a run is stopped via its cancel event."""


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
        tool_result_max_chars: int | None = None,
        cancel_event: threading.Event | None = None,
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
        self.tool_result_max_chars = tool_result_max_chars
        self.cancel_event = cancel_event

    def _check_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise RunCancelled(f"{self.name}: run stopped")

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
            self._check_cancelled()
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

                # Execute the requested tools (concurrently when the model
                # asked for several in one turn) and append results in order.
                results = self._execute_tool_calls(message.tool_calls)
                for tc, (tool_args, tool_result) in zip(message.tool_calls, results):
                    tool_calls_log.append({
                        "name": tc.function.name,
                        "args": tool_args,
                        "result": tool_result,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": self._serialise_result(tool_result),
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

        # max_iterations reached without a final text response. The model
        # may have been chaining tool_calls forever with no text. Make one
        # last call WITHOUT tools to force a synthesis from accumulated
        # tool results — otherwise the loop returns "" and any downstream
        # parse blows up.
        synthesis_output = self._force_synthesis(messages, token_usage)
        final_output = synthesis_output or last_content
        logger.warning(
            "%s: hit max_iterations=%d. last_content_len=%d, "
            "synthesis_len=%d, tool_calls_run=%d",
            self.name, self.max_iterations, len(last_content),
            len(synthesis_output or ""), len(tool_calls_log),
        )
        return AgentResult(
            output=final_output,
            tool_calls=tool_calls_log,
            iterations=iterations,
            token_usage=token_usage,
            hit_max_iterations=True,
        )

    def _serialise_result(self, result: dict) -> str:
        """JSON-encode a tool result, truncating oversized payloads.

        Raw search responses can run to tens of KB; feeding them whole into
        the message history balloons prompt tokens for every subsequent
        iteration. The truncation marker tells the model content was cut.
        """
        content = json.dumps(result)
        limit = self.tool_result_max_chars
        if limit and len(content) > limit:
            content = content[:limit] + f" ... [tool result truncated at {limit} chars]"
        return content

    def _execute_one_tool_call(self, tc: Any) -> tuple[dict, dict]:
        """Run a single tool call; returns (parsed_args, result).

        Malformed arguments JSON from the model is reported back as a
        structured error so the loop can recover instead of crashing.
        """
        self._check_cancelled()
        tool_name = tc.function.name
        try:
            tool_args = json.loads(tc.function.arguments or "{}")
            if not isinstance(tool_args, dict):
                raise ValueError("tool arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("%s: malformed args for %s: %s", self.name, tool_name, exc)
            return {}, {
                "error": (
                    f"Malformed arguments for {tool_name}: {exc}. "
                    "Re-issue the call with a valid JSON object."
                ),
            }
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
        return tool_args, execute_tool(tool_name, tool_args, self.tools)

    def _execute_tool_calls(self, tool_calls: list) -> list[tuple[dict, dict]]:
        """Execute tool calls, in parallel when there is more than one.

        Models often request independent calls in one turn (e.g. a parent
        delegating to three specialists); running them concurrently turns
        that into real wall-clock parallelism.
        """
        if len(tool_calls) == 1:
            return [self._execute_one_tool_call(tool_calls[0])]
        with ThreadPoolExecutor(max_workers=min(4, len(tool_calls))) as pool:
            return list(pool.map(self._execute_one_tool_call, tool_calls))

    def _force_synthesis(
        self, messages: list[dict], token_usage: dict
    ) -> str:
        """Make one tools-disabled call to coax a final text response.

        Used when the ReAct loop exits without the model ever producing a
        text turn. Appends a stern instruction and re-calls the model with
        no tools available, so it has to write final content.
        """
        synthesis_messages = list(messages) + [{
            "role": "user",
            "content": (
                "You have reached the maximum number of tool calls. "
                "Stop searching and synthesise everything you have learned "
                "into the final required output now. Do not call any tools. "
                "Return ONLY the final content — no prose preamble, no code "
                "fences, no <tool_call> tags."
            ),
        }]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": synthesis_messages,
        }
        if self.timeout is not None:
            kwargs["timeout"] = self.timeout
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.warning(
                "%s: forced synthesis call failed: %s", self.name, exc,
            )
            return ""
        token_usage["prompt"] += response.usage.prompt_tokens
        token_usage["completion"] += response.usage.completion_tokens
        return response.choices[0].message.content or ""
