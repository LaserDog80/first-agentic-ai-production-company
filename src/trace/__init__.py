"""Trace normalization: turn real agentic runs into theatre-playable traces.

Adapters convert external agent formats (Claude Code session transcripts,
Claude Code hook events) into one normalized event vocabulary that the
Theatre frontend renders. See `claude_adapter.py` for the schema.
"""
from src.trace.claude_adapter import load_transcript, normalize_transcript
from src.trace.live import LiveBroker, normalize_hook_event

__all__ = [
    "load_transcript",
    "normalize_transcript",
    "LiveBroker",
    "normalize_hook_event",
]
