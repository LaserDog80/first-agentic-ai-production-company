"""Discover Claude Code session transcripts on the local machine.

Claude Code stores one JSONL transcript per session under
``~/.claude/projects/<munged-project-path>/<session-uuid>.jsonl``. When the
Theatre server runs on the same machine, these can be listed and replayed
directly — "load one of Claude's previous runs".

The scan root is overridable via the ``CLAUDE_PROJECTS_DIR`` environment
variable. Session ids exposed to the client are content hashes of the file
path, so no filesystem paths leak into the API.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_SNIPPET_SCAN_LINES = 400
_MAX_SESSIONS = 200

# id -> path, refreshed on every list_sessions() call.
_session_paths: dict[str, Path] = {}


def projects_root() -> Path:
    root = os.environ.get("CLAUDE_PROJECTS_DIR")
    return Path(root) if root else Path.home() / ".claude" / "projects"


def _session_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()[:12]


def _first_prompt(path: Path) -> str:
    """Best-effort first human prompt from a transcript, for the picker."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for _ in range(_SNIPPET_SCAN_LINES):
                line = fh.readline()
                if not line:
                    break
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "user" or obj.get("isSidechain"):
                    continue
                content = (obj.get("message") or {}).get("content")
                if isinstance(content, str):
                    text = content.strip()
                    if text and not text.startswith(("<command-", "<local-command-", "<system-reminder")):
                        return text.splitlines()[0][:120]
    except OSError:
        pass
    return ""


def list_sessions() -> list[dict]:
    """Scan the projects root and return session metadata, newest first."""
    root = projects_root()
    _session_paths.clear()
    sessions: list[dict] = []
    if not root.is_dir():
        return sessions
    for path in root.glob("*/*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        sid = _session_id(path)
        _session_paths[sid] = path
        sessions.append({
            "id": sid,
            "project": path.parent.name.lstrip("-").replace("-", "/"),
            "filename": path.name,
            "mtime": stat.st_mtime,
            "size_kb": round(stat.st_size / 1024, 1),
            "snippet": _first_prompt(path),
        })
    sessions.sort(key=lambda s: -s["mtime"])
    return sessions[:_MAX_SESSIONS]


def read_session(session_id: str) -> str | None:
    """Return the raw transcript text for a previously listed session id."""
    path = _session_paths.get(session_id)
    if path is None:
        list_sessions()
        path = _session_paths.get(session_id)
    if path is None or not path.is_file():
        return None
    try:
        if not path.resolve().is_relative_to(projects_root().resolve()):
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
