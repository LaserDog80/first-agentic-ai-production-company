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


def test_agent_recovers_from_malformed_tool_args():
    """Malformed arguments JSON from the model must surface as a tool-result
    error the loop can recover from, not crash the whole run (v3 fix)."""
    client = MagicMock()

    bad_call = MagicMock()
    bad_call.id = "call_1"
    bad_call.function.name = "mock_tool"
    bad_call.function.arguments = '{"query": broken'
    first = _make_mock_response(None, tool_calls=[bad_call])
    second = _make_mock_response("recovered")
    client.chat.completions.create.side_effect = [first, second]

    agent = AgentRuntime(
        name="t", system_prompt=".", tools=[mock_tool],
        client=client, model="m", max_iterations=5,
    )
    result = agent.run("go")
    assert result.output == "recovered"
    assert "error" in result.tool_calls[0]["result"]
    assert "Malformed" in result.tool_calls[0]["result"]["error"]


def test_agent_executes_parallel_tool_calls_in_order():
    """Several tool calls in one assistant turn all execute, and their
    results land in the message history in request order."""
    calls = []

    @tool
    def slow_tool(query: str) -> dict:
        """Slow.

        Args:
            query: q.
        """
        import time as _t
        if query == "first":
            _t.sleep(0.05)  # finishes last despite being requested first
        calls.append(query)
        return {"echo": query}

    client = MagicMock()
    tc1 = MagicMock(); tc1.id = "c1"
    tc1.function.name = "slow_tool"; tc1.function.arguments = '{"query": "first"}'
    tc2 = MagicMock(); tc2.id = "c2"
    tc2.function.name = "slow_tool"; tc2.function.arguments = '{"query": "second"}'
    first = _make_mock_response(None, tool_calls=[tc1, tc2])
    second = _make_mock_response("done")
    client.chat.completions.create.side_effect = [first, second]

    agent = AgentRuntime(
        name="t", system_prompt=".", tools=[slow_tool],
        client=client, model="m", max_iterations=5,
    )
    result = agent.run("go")
    assert result.output == "done"
    assert [t["result"]["echo"] for t in result.tool_calls] == ["first", "second"]
    # Both actually ran (order of *execution* may interleave).
    assert sorted(calls) == ["first", "second"]
    # Tool messages in history are in request order with the right ids.
    second_call_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2"]


def test_agent_truncates_oversized_tool_results():
    @tool
    def big_tool(query: str) -> dict:
        """Big.

        Args:
            query: q.
        """
        return {"blob": "x" * 5000}

    client = MagicMock()
    tc = MagicMock(); tc.id = "c1"
    tc.function.name = "big_tool"; tc.function.arguments = '{"query": "q"}'
    client.chat.completions.create.side_effect = [
        _make_mock_response(None, tool_calls=[tc]),
        _make_mock_response("done"),
    ]
    agent = AgentRuntime(
        name="t", system_prompt=".", tools=[big_tool],
        client=client, model="m", max_iterations=5,
        tool_result_max_chars=200,
    )
    result = agent.run("go")
    messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_msg = [m for m in messages if m["role"] == "tool"][0]
    assert len(tool_msg["content"]) < 300
    assert "truncated" in tool_msg["content"]
    # The full result is still available in the log.
    assert len(result.tool_calls[0]["result"]["blob"]) == 5000


def test_agent_cancellation_raises():
    import threading
    from src.agent import RunCancelled

    client = MagicMock()
    client.chat.completions.create.return_value = _make_mock_response("never")
    cancel = threading.Event()
    cancel.set()
    agent = AgentRuntime(
        name="t", system_prompt=".", tools=[], client=client,
        model="m", max_iterations=5, cancel_event=cancel,
    )
    with pytest.raises(RunCancelled):
        agent.run("go")
    client.chat.completions.create.assert_not_called()
