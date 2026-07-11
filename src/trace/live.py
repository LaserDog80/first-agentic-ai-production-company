"""Live ingestion of Claude Code hook events for the Theatre.

Claude Code hooks (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`,
`SubagentStop`, `SessionStart`…) can POST their stdin JSON payload to this
server's ``/ingest`` endpoint. Each payload is normalized into the same
event vocabulary the transcript adapter produces (see
``claude_adapter.py``), buffered per session, and broadcast to any Theatre
clients subscribed on the ``/ws/live`` WebSocket.

Attribution caveat: hook payloads carry no agent identity, so while a
Task (subagent) is in flight, tool events are attributed to the most
recently spawned open subagent. Parallel tool use by the parent during a
delegation can therefore be mis-badged — acceptable for a live show, and
replay-from-transcript is exact.
"""
from __future__ import annotations

import time
from typing import Any

from src.trace.claude_adapter import humanize_tool, _clip

_MAX_BUFFERED_EVENTS = 5_000
_MAX_SESSIONS = 20


class LiveSession:
    """Per-session live state: event buffer, cast, delegation stack."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.t0 = time.time()
        self.last_seen = self.t0
        self.events: list[dict] = []
        self.agent_count = 1  # "main" exists implicitly
        self.open_children: list[str] = []
        self.task_children: dict[str, str] = {}  # tool call keying is unavailable; keyed by description
        self.subscribers: set[Any] = set()

    def now(self) -> float:
        return round(time.time() - self.t0, 3)

    def current_agent(self) -> str:
        return self.open_children[-1] if self.open_children else "main"


class LiveBroker:
    """Holds live sessions and fans events out to WebSocket subscribers."""

    def __init__(self) -> None:
        self.sessions: dict[str, LiveSession] = {}

    def session(self, session_id: str) -> LiveSession:
        state = self.sessions.get(session_id)
        if state is None:
            if len(self.sessions) >= _MAX_SESSIONS:
                oldest = min(self.sessions.values(), key=lambda s: s.last_seen)
                self.sessions.pop(oldest.session_id, None)
            state = LiveSession(session_id)
            self.sessions[session_id] = state
        state.last_seen = time.time()
        return state

    def ingest(self, payload: dict) -> list[dict]:
        """Normalize one hook payload; buffer and return the new events."""
        session_id = str(payload.get("session_id") or "unknown")
        state = self.session(session_id)
        events = normalize_hook_event(state, payload)
        state.events.extend(events)
        if len(state.events) > _MAX_BUFFERED_EVENTS:
            del state.events[: len(state.events) - _MAX_BUFFERED_EVENTS]
        return events

    def list_active(self) -> list[dict]:
        return [
            {
                "session_id": s.session_id,
                "events": len(s.events),
                "last_seen_s_ago": round(time.time() - s.last_seen, 1),
            }
            for s in sorted(self.sessions.values(), key=lambda s: -s.last_seen)
        ]


def normalize_hook_event(state: LiveSession, payload: dict) -> list[dict]:
    """Map one Claude Code hook payload to normalized trace events."""
    hook = str(payload.get("hook_event_name", ""))
    t = state.now()

    if hook == "SessionStart":
        return [_ev(t, "main", "session_start",
                    cwd=str(payload.get("cwd", "")))]

    if hook == "UserPromptSubmit":
        text = _clip(str(payload.get("prompt", "")), 400)
        return [_ev(t, "main", "user_message", text=text)] if text else []

    if hook == "PreToolUse":
        return _pre_tool_use(state, t, payload)

    if hook == "PostToolUse":
        return _post_tool_use(state, t, payload)

    if hook == "SubagentStop":
        if state.open_children:
            child = state.open_children.pop()
            return [_ev(t, "main", "return", child=child,
                        summary="finished and reported back", ok=True)]
        return []

    if hook == "Stop":
        return [_ev(t, "main", "done")]

    if hook == "Notification":
        msg = _clip(str(payload.get("message", "")), 200)
        return [_ev(t, "main", "say", text=msg)] if msg else []

    return []


def _pre_tool_use(state: LiveSession, t: float, payload: dict) -> list[dict]:
    name = str(payload.get("tool_name", "tool"))
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}

    if name in ("Task", "Agent"):
        state.agent_count += 1
        child = f"a{state.agent_count - 1}"
        desc = _clip(str(tool_input.get("description", "a task")), 80)
        state.open_children.append(child)
        state.task_children[desc] = child
        return [_ev(t, "main", "spawn", child=child, task=desc,
                    agent_type=str(tool_input.get("subagent_type", "agent")),
                    prompt=_clip(str(tool_input.get("prompt", "")), 400))]

    if name == "TodoWrite":
        items = [
            {"text": _clip(str(td.get("content", "")), 80),
             "status": str(td.get("status", "pending"))}
            for td in (tool_input.get("todos") or []) if isinstance(td, dict)
        ]
        return [_ev(t, state.current_agent(), "todo", items=items)]

    summary, detail = humanize_tool(name, tool_input)
    return [_ev(t, state.current_agent(), "tool_start", tool=name,
                call_id="", summary=summary, detail=detail)]


def _post_tool_use(state: LiveSession, t: float, payload: dict) -> list[dict]:
    name = str(payload.get("tool_name", "tool"))
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}

    if name in ("Task", "Agent"):
        desc = _clip(str(tool_input.get("description", "a task")), 80)
        child = state.task_children.pop(desc, None)
        if child and child in state.open_children:
            state.open_children.remove(child)
        if child:
            resp = payload.get("tool_response")
            summary = _clip(_response_text(resp), 400) or "reported back"
            return [_ev(t, "main", "return", child=child, summary=summary, ok=True)]
        return []

    if name == "TodoWrite":
        return []

    resp = payload.get("tool_response")
    ok, summary = _response_summary(resp)
    return [_ev(t, state.current_agent(), "tool_end", tool=name,
                call_id="", ok=ok, summary=summary)]


def _response_text(resp: Any) -> str:
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        for key in ("stdout", "content", "text", "result", "output"):
            val = resp.get(key)
            if isinstance(val, str) and val.strip():
                return val
    if isinstance(resp, list):
        return "\n".join(_response_text(r) for r in resp)
    return ""


def _response_summary(resp: Any) -> tuple[bool, str]:
    if isinstance(resp, dict) and (resp.get("is_error") or resp.get("error")):
        return False, "failed: " + _clip(_response_text(resp) or str(resp.get("error", "")), 120)
    text = _response_text(resp).strip()
    if not text:
        return True, "done"
    lines = text.splitlines()
    first = _clip(lines[0], 120)
    return True, first if len(lines) == 1 else f"{first} (+{len(lines) - 1} lines)"


def _ev(t: float, agent: str, etype: str, **payload: Any) -> dict:
    return {"t": t, "agent": agent, "type": etype, **payload}
