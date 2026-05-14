# tests/test_agent.py
import json
import pytest
from unittest.mock import MagicMock, patch
from src.agent import AgentRuntime, AgentResult
from src.tools import tool


@tool
def mock_tool(query: str) -> dict:
    """A mock tool for testing."""
    return {"answer": f"Result for {query}"}


def _make_mock_response(content: str, tool_calls=None):
    """Create a mock OpenAI chat completion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop" if not tool_calls else "tool_calls"
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    return response


def test_agent_simple_response():
    """Agent returns structured output on first call, no tool use."""
    client = MagicMock()
    output_json = '{"working_title": "Test Show"}'
    client.chat.completions.create.return_value = _make_mock_response(output_json)

    agent = AgentRuntime(
        name="test_agent",
        system_prompt="You are a test agent.",
        tools=[],
        client=client,
        model="test-model",
        max_iterations=5,
    )
    result = agent.run(user_message="Create a show.")
    assert result.output == output_json
    assert result.tool_calls == []
    assert result.iterations == 1


def test_agent_uses_tool_then_responds():
    """Agent calls a tool, gets result, then produces final output."""
    client = MagicMock()

    # First call: model requests a tool call
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "mock_tool"
    tool_call.function.arguments = '{"query": "test"}'
    first_response = _make_mock_response(None, tool_calls=[tool_call])

    # Second call: model produces final output
    second_response = _make_mock_response('{"result": "done"}')

    client.chat.completions.create.side_effect = [first_response, second_response]

    agent = AgentRuntime(
        name="test_agent",
        system_prompt="You are a test agent.",
        tools=[mock_tool],
        client=client,
        model="test-model",
        max_iterations=5,
    )
    result = agent.run(user_message="Do a search.")
    assert result.output == '{"result": "done"}'
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "mock_tool"
    assert result.iterations == 2


def test_agent_max_iterations():
    """Agent stops after max_iterations and returns best effort."""
    client = MagicMock()

    # Every call requests another tool call (infinite loop scenario)
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "mock_tool"
    tool_call.function.arguments = '{"query": "loop"}'
    looping_response = _make_mock_response(None, tool_calls=[tool_call])

    client.chat.completions.create.return_value = looping_response

    agent = AgentRuntime(
        name="test_agent",
        system_prompt="You are a test agent.",
        tools=[mock_tool],
        client=client,
        model="test-model",
        max_iterations=3,
    )
    result = agent.run(user_message="Loop forever.")
    assert result.iterations == 3
    assert result.hit_max_iterations is True


def test_agent_synthesises_on_max_iter_when_empty(monkeypatch):
    """When the ReAct loop exits at max_iterations with no final text,
    AgentRuntime should make one tools-disabled call to coax a final
    response — otherwise downstream JSON parse blows up (issue #23)."""
    client = MagicMock()

    # Every iteration: model emits tool_calls, no text content.
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "mock_tool"
    tool_call.function.arguments = '{"query": "loop"}'
    looping_response = _make_mock_response(None, tool_calls=[tool_call])

    # Synthesis call (the +1 after the loop): final JSON.
    synthesis_response = _make_mock_response('{"final": "answer"}')

    client.chat.completions.create.side_effect = (
        [looping_response] * 3 + [synthesis_response]
    )

    agent = AgentRuntime(
        name="test_agent",
        system_prompt="Test.",
        tools=[mock_tool],
        client=client,
        model="test-model",
        max_iterations=3,
    )
    result = agent.run(user_message="Loop.")
    assert result.hit_max_iterations is True
    assert result.output == '{"final": "answer"}'
    # Synthesis call should NOT have included tools kwarg
    last_call_kwargs = client.chat.completions.create.call_args_list[-1].kwargs
    assert "tools" not in last_call_kwargs


def test_agent_tracks_token_usage():
    """Agent accumulates token usage across iterations."""
    client = MagicMock()
    output_json = '{"result": "ok"}'
    client.chat.completions.create.return_value = _make_mock_response(output_json)

    agent = AgentRuntime(
        name="test_agent",
        system_prompt="Test.",
        tools=[],
        client=client,
        model="test-model",
        max_iterations=5,
    )
    result = agent.run(user_message="Test.")
    assert result.token_usage["prompt"] == 100
    assert result.token_usage["completion"] == 50
