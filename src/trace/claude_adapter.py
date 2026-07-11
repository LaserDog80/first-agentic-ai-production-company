"""Normalize Claude Code session transcripts into theatre traces.

A Claude Code session transcript is a JSONL file (one JSON object per line)
found under ``~/.claude/projects/<project>/<session>.jsonl``. Lines of type
``user`` / ``assistant`` carry Anthropic-API-shaped messages; everything
else (queue-operation, attachment, last-prompt, mode…) is bookkeeping.

This adapter reduces a transcript to a **trace**: a JSON document with a
cast of ``agents`` and a chronological list of ``events`` that the Theatre
frontend can animate. The normalized event vocabulary:

- ``user_message``  {text}               — the human gave a brief
- ``thinking``      {}                   — the agent is reasoning privately
- ``say``           {text}               — the agent spoke to the user
- ``tool_start``    {tool, call_id, summary, detail}
- ``tool_end``      {tool, call_id, ok, summary}
- ``todo``          {items: [{text, status}]} — the agent updated its plan
- ``spawn``         {child, task, agent_type} — the agent hired a subagent
- ``return``        {child, summary}     — the subagent reported back
- ``done``          {}                   — end of the run

Every event has ``t`` (seconds from trace start) and ``agent`` (the id of
the acting agent, ``"main"`` for the orchestrator). Assistant events may
carry ``tokens: {ctx, out}`` — context size and output tokens for the API
request that produced them (deduped by requestId, since one request can
emit several transcript lines).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

_TEXT_CLIP = 400
_DETAIL_CLIP = 240
_SUMMARY_CLIP = 120

TRACE_VERSION = 1


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _basename(path: str) -> str:
    return str(path).rstrip("/").rsplit("/", 1)[-1] or str(path)


def humanize_tool(name: str, tool_input: dict) -> tuple[str, str]:
    """Return (summary, detail) describing a tool call in plain English."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    detail = _clip(json.dumps(ti, ensure_ascii=False), _DETAIL_CLIP)
    if name == "Read":
        return f"Reading {_basename(ti.get('file_path', 'a file'))}", detail
    if name == "Write":
        return f"Writing {_basename(ti.get('file_path', 'a file'))}", detail
    if name in ("Edit", "MultiEdit", "NotebookEdit"):
        return f"Editing {_basename(ti.get('file_path', 'a file'))}", detail
    if name == "Bash":
        desc = ti.get("description") or _clip(str(ti.get("command", "")), 60)
        return f"Running: {desc}" if desc else "Running a shell command", detail
    if name == "Grep":
        return f"Searching code for “{_clip(str(ti.get('pattern', '')), 40)}”", detail
    if name == "Glob":
        return f"Scanning files: {_clip(str(ti.get('pattern', '')), 40)}", detail
    if name == "WebSearch":
        return f"Searching the web: “{_clip(str(ti.get('query', '')), 60)}”", detail
    if name == "WebFetch":
        return f"Fetching {_clip(str(ti.get('url', 'a page')), 60)}", detail
    if name == "TodoWrite":
        return "Updating the plan", detail
    if name in ("Task", "Agent"):
        return f"Delegating: {_clip(str(ti.get('description', 'a task')), 60)}", detail
    if name.startswith("mcp__"):
        parts = name.split("__")
        tool = parts[-1] if parts else name
        return f"Using {tool.replace('_', ' ')}", detail
    return f"Using {name}", detail


def summarize_result(block: dict, tool_use_result: Any) -> tuple[bool, str]:
    """Return (ok, summary) for a tool_result block."""
    if isinstance(block, dict) and block.get("is_error"):
        return False, "failed: " + _clip(_result_text(block), _SUMMARY_CLIP)
    tur = tool_use_result if isinstance(tool_use_result, dict) else {}
    if "stdout" in tur:
        out = (tur.get("stdout") or "").strip()
        if tur.get("stderr") and not out:
            return True, _clip(tur["stderr"].splitlines()[0], _SUMMARY_CLIP)
        if not out:
            return True, "done (no output)"
        lines = out.splitlines()
        first = _clip(lines[0], _SUMMARY_CLIP)
        return True, first if len(lines) == 1 else f"{first} (+{len(lines) - 1} lines)"
    if tur.get("type") == "file":
        n = (tur.get("file") or {}).get("numLines")
        return True, f"read {n} lines" if n else "file read"
    text = _result_text(block)
    return True, _clip(text, _SUMMARY_CLIP) if text else "done"


def _result_text(block: dict) -> str:
    content = block.get("content") if isinstance(block, dict) else ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content
                 if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(parts)
    return ""


def load_transcript(text: str) -> list[dict]:
    """Parse transcript JSONL text into user/assistant records, in order."""
    records: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") in ("user", "assistant") and isinstance(obj.get("message"), dict):
            records.append(obj)
    return records


class _TraceBuilder:
    """Accumulates normalized events while walking transcript records."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.agents: dict[str, dict] = {
            "main": {"id": "main", "name": "CLAUDE", "agent_type": "orchestrator",
                     "parent": None, "spawned_t": 0.0, "tokens_out": 0, "tool_calls": 0},
        }
        # Task tool_use calls in order of appearance, for sidechain matching.
        self.task_calls: list[dict] = []
        self.call_agent: dict[str, str] = {}   # tool call_id -> acting agent id
        self.task_child: dict[str, str] = {}   # Task call_id -> child agent id
        self.seen_requests: set[str] = set()
        self.totals = {"ctx_peak": 0, "out": 0, "tool_calls": 0}
        self.t0: float | None = None
        self.last_t: float = 0.0
        self.model = ""
        self.title = ""
        self.cwd = ""
        self.session_id = ""
        self.started_at = ""

    # ── time ────────────────────────────────────────────────────────────
    def t_for(self, rec: dict) -> float:
        ts = _parse_ts(rec.get("timestamp"))
        if ts is None:
            return self.last_t
        if self.t0 is None:
            self.t0 = ts
            self.started_at = rec.get("timestamp", "")
        self.last_t = max(0.0, ts - self.t0)
        return self.last_t

    def add(self, t: float, agent: str, etype: str, **payload: Any) -> dict:
        ev = {"t": round(t, 3), "agent": agent, "type": etype, **payload}
        self.events.append(ev)
        return ev

    # ── record handlers ──────────────────────────────────────────────────
    def handle_assistant(self, rec: dict, agent: str) -> None:
        t = self.t_for(rec)
        msg = rec["message"]
        self.model = self.model or msg.get("model", "")
        tokens = self._usage_tokens(rec)
        first_ev: dict | None = None
        for block in msg.get("content") or []:
            if not isinstance(block, dict):
                continue
            ev = self._handle_block(t, agent, block)
            if ev is not None and first_ev is None:
                first_ev = ev
        if tokens:
            target = first_ev or self.add(t, agent, "thinking")
            target["tokens"] = tokens
            self.agents[agent]["tokens_out"] += tokens["out"]
            self.totals["out"] += tokens["out"]
            self.totals["ctx_peak"] = max(self.totals["ctx_peak"], tokens["ctx"])

    def _handle_block(self, t: float, agent: str, block: dict) -> dict | None:
        btype = block.get("type")
        if btype == "thinking":
            return self.add(t, agent, "thinking")
        if btype == "text":
            text = (block.get("text") or "").strip()
            return self.add(t, agent, "say", text=_clip(text, _TEXT_CLIP)) if text else None
        if btype == "tool_use":
            return self._handle_tool_use(t, agent, block)
        return None

    def _handle_tool_use(self, t: float, agent: str, block: dict) -> dict:
        name = str(block.get("name", "tool"))
        call_id = str(block.get("id", ""))
        tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
        self.call_agent[call_id] = agent
        self.agents[agent]["tool_calls"] += 1
        self.totals["tool_calls"] += 1
        if name in ("Task", "Agent"):
            child = self._spawn_child(t, agent, call_id, tool_input)
            return self.add(
                t, agent, "spawn",
                child=child,
                task=_clip(str(tool_input.get("description", "a task")), 80),
                agent_type=str(tool_input.get("subagent_type", "agent")),
                prompt=_clip(str(tool_input.get("prompt", "")), _TEXT_CLIP),
            )
        if name == "TodoWrite":
            items = [
                {"text": _clip(str(td.get("content", "")), 80),
                 "status": str(td.get("status", "pending"))}
                for td in (tool_input.get("todos") or []) if isinstance(td, dict)
            ]
            return self.add(t, agent, "todo", items=items, call_id=call_id)
        summary, detail = humanize_tool(name, tool_input)
        return self.add(t, agent, "tool_start", tool=name, call_id=call_id,
                        summary=summary, detail=detail)

    def _spawn_child(self, t: float, parent: str, call_id: str, tool_input: dict) -> str:
        child_id = f"a{len(self.agents)}"
        desc = str(tool_input.get("description") or "").strip()
        self.agents[child_id] = {
            "id": child_id,
            "name": _clip(desc or "AGENT", 40).upper(),
            "agent_type": str(tool_input.get("subagent_type", "agent")),
            "parent": parent,
            "spawned_t": round(t, 3),
            "tokens_out": 0,
            "tool_calls": 0,
        }
        self.task_child[call_id] = child_id
        self.task_calls.append({
            "call_id": call_id,
            "child": child_id,
            "prompt": str(tool_input.get("prompt", "")),
            "matched": False,
        })
        return child_id

    def handle_user(self, rec: dict, agent: str) -> None:
        t = self.t_for(rec)
        msg = rec["message"]
        content = msg.get("content")
        self.cwd = self.cwd or rec.get("cwd", "")
        self.session_id = self.session_id or rec.get("sessionId", "")
        if isinstance(content, str):
            self._handle_user_text(t, agent, content)
            return
        if not isinstance(content, list):
            return
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                self._handle_tool_result(t, block, rec.get("toolUseResult"))
            elif isinstance(block, dict) and block.get("type") == "text":
                self._handle_user_text(t, agent, block.get("text", ""))

    def _handle_user_text(self, t: float, agent: str, text: str) -> None:
        text = (text or "").strip()
        # Skip slash-command wrappers and injected reminders — not human words.
        if not text or text.startswith(("<command-", "<local-command-", "<system-reminder")):
            return
        if not self.title and agent == "main":
            self.title = _clip(text.splitlines()[0], 90)
        self.add(t, agent, "user_message", text=_clip(text, _TEXT_CLIP))

    def _handle_tool_result(self, t: float, block: dict, tur: Any) -> None:
        call_id = str(block.get("tool_use_id", ""))
        agent = self.call_agent.get(call_id, "main")
        child = self.task_child.get(call_id)
        if child:
            ok, _ = summarize_result(block, tur)
            summary = _clip(_result_text(block), _TEXT_CLIP) or ("done" if ok else "failed")
            self.add(t, agent, "return", child=child, summary=summary, ok=ok)
            return
        ok, summary = summarize_result(block, tur)
        self.add(t, agent, "tool_end", call_id=call_id, ok=ok, summary=summary)

    def _usage_tokens(self, rec: dict) -> dict | None:
        usage = rec["message"].get("usage")
        if not isinstance(usage, dict):
            return None
        req = rec.get("requestId") or rec.get("uuid", "")
        if req in self.seen_requests:
            return None
        self.seen_requests.add(req)
        ctx = (
            usage.get("input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0)
        )
        return {"ctx": int(ctx), "out": int(usage.get("output_tokens", 0))}


def _sidechain_chains(records: list[dict]) -> list[list[dict]]:
    """Group sidechain records into per-subagent chains via parentUuid links."""
    side = [r for r in records if r.get("isSidechain")]
    if not side:
        return []
    by_uuid = {r.get("uuid"): r for r in side if r.get("uuid")}
    roots: dict[str, list[dict]] = {}
    for rec in side:
        cur = rec
        for _ in range(len(side)):
            parent = by_uuid.get(cur.get("parentUuid"))
            if parent is None:
                break
            cur = parent
        roots.setdefault(cur.get("uuid") or id(cur), []).append(rec)
    def ts_key(rec: dict) -> float:
        return _parse_ts(rec.get("timestamp")) or 0.0

    chains = list(roots.values())
    for chain in chains:
        chain.sort(key=ts_key)
    chains.sort(key=lambda c: ts_key(c[0]))
    return chains


def _match_chain(chain: list[dict], builder: _TraceBuilder) -> str | None:
    """Find which spawned child a sidechain belongs to."""
    root_text = ""
    for rec in chain:
        if rec.get("type") == "user":
            content = rec["message"].get("content")
            if isinstance(content, str):
                root_text = content.strip()
            elif isinstance(content, list):
                root_text = "\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ).strip()
            break
    for call in builder.task_calls:
        if not call["matched"] and root_text and call["prompt"].strip() == root_text:
            call["matched"] = True
            return call["child"]
    for call in builder.task_calls:  # fallback: first unmatched, in order
        if not call["matched"]:
            call["matched"] = True
            return call["child"]
    return None


def normalize_transcript(text: str, source: str = "claude-code-transcript") -> dict:
    """Convert raw transcript JSONL text into a normalized trace document."""
    records = load_transcript(text)
    builder = _TraceBuilder()

    main = [r for r in records if not r.get("isSidechain")]
    for rec in main:
        if rec.get("type") == "assistant":
            builder.handle_assistant(rec, "main")
        else:
            builder.handle_user(rec, "main")

    for chain in _sidechain_chains(records):
        child = _match_chain(chain, builder)
        if child is None:
            continue
        for rec in chain:
            if rec.get("type") == "assistant":
                builder.handle_assistant(rec, child)
            else:
                # The chain root repeats the Task prompt — skip echoing it.
                content = rec["message"].get("content")
                if isinstance(content, str) and rec is chain[0]:
                    continue
                builder.handle_user(rec, child)

    builder.events.sort(key=lambda ev: ev["t"])
    duration = builder.events[-1]["t"] if builder.events else 0.0
    builder.add(duration, "main", "done")
    return {
        "version": TRACE_VERSION,
        "source": source,
        "session_id": builder.session_id,
        "title": builder.title or "Untitled run",
        "cwd": builder.cwd,
        "model": builder.model,
        "started_at": builder.started_at,
        "duration_s": round(duration, 3),
        "totals": builder.totals,
        "agents": list(builder.agents.values()),
        "events": builder.events,
    }
