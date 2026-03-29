"""Live commentary engine — fixed-interval LLM narration of pipeline events."""
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from src.prompts.commentary import build_live_prompt, build_outro_prompt

logger = logging.getLogger(__name__)

# How often (seconds) to poll the buffer and generate commentary
POLL_INTERVAL = 12.0

# Hard character limits on LLM output
MAX_LIVE_CHARS = 500
MAX_OUTRO_CHARS = 300


class CommentaryEngine:
    """Collects pipeline events and generates LLM commentary on a fixed interval.

    A background timer polls the event buffer every POLL_INTERVAL seconds.
    If meaningful events have accumulated, it fires an LLM call to narrate.
    This keeps commentary in step with a readable pace regardless of event timing.
    """

    def __init__(
        self,
        client: Any,
        model: str,
        emit_callback: Callable[[dict], None],
    ) -> None:
        self._client = client
        self._model = model
        self._emit = emit_callback
        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._live_prompt = build_live_prompt()
        self._outro_prompt = build_outro_prompt()
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def ingest(self, event: dict) -> None:
        """Buffer a pipeline event for the next poll cycle."""
        with self._lock:
            self._buffer.append(event)

    def _poll_loop(self) -> None:
        """Background loop that checks for events every POLL_INTERVAL."""
        while self._running:
            time.sleep(POLL_INTERVAL)
            if not self._running:
                break

            with self._lock:
                if not self._buffer:
                    continue
                # Check if there's anything meaningful to narrate
                has_meaningful = any(
                    e.get("type") in {"agent_start", "agent_done", "rework"}
                    for e in self._buffer
                )
                if not has_meaningful:
                    continue
                snapshot = list(self._buffer)
                self._buffer.clear()

            # Fire LLM call in executor (won't pile up — max_workers=1)
            self._executor.submit(self._generate_live, snapshot)

    def generate_outro(self, pitch_deck: dict) -> str:
        """Generate closing reflection. Returns the outro text."""
        try:
            deck_json = json.dumps(pitch_deck, default=str)[:2000]
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._outro_prompt},
                    {"role": "user", "content": deck_json},
                ],
                max_tokens=120,
                temperature=0.7,
            )
            text = response.choices[0].message.content.strip()
            # Convert ||BREAK|| marker to actual paragraph break
            text = text.replace("||BREAK||", "\n\n")
            # If no double newline, try to insert one before common phrases
            if "\n\n" not in text:
                for marker in ["This is early", "It handles", "It automates",
                               "Early work", "Not perfect"]:
                    if marker in text:
                        text = text.replace(marker, "\n\n" + marker)
                        break
            return text[:MAX_OUTRO_CHARS]
        except Exception:
            logger.exception("Outro generation failed")
            return (
                "Five independent AI agents just turned a single sentence "
                "into a pitch deck. Not perfect yet — but a glimpse of "
                "where the industry is heading."
            )

    def _generate_live(self, events: list[dict]) -> None:
        """Generate live commentary from a batch of events (runs in thread)."""
        try:
            summary_lines = []
            for e in events:
                etype = e.get("type", "")
                agent = e.get("agent", e.get("target", ""))
                msg = e.get("message", "")
                phase = e.get("phase", "")
                if etype == "agent_start":
                    summary_lines.append(f"{agent} started ({phase}): {msg}")
                elif etype == "agent_done":
                    summary_lines.append(f"{agent} finished ({phase}): {msg}")
                elif etype == "tool_call":
                    tool = e.get("tool", "")
                    summary_lines.append(f"{agent} used tool: {tool}")
                elif etype == "rework":
                    summary_lines.append(f"Rework requested: {msg}")
                elif etype == "status":
                    summary_lines.append(f"Status: {msg}")

            if not summary_lines:
                return

            user_msg = "\n".join(summary_lines)
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._live_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=150,
                temperature=0.7,
            )
            text = response.choices[0].message.content.strip()
            text = text[:MAX_LIVE_CHARS]
            if text:
                self._emit({"type": "commentary", "text": text})
        except Exception:
            logger.exception("Live commentary generation failed")

    def shutdown(self) -> None:
        """Stop the poll loop and clean up."""
        self._running = False
        self._executor.shutdown(wait=False)
