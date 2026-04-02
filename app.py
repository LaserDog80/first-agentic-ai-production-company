"""FastAPI web server with WebSocket for real-time pipeline updates."""
import asyncio
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.commentary import CommentaryEngine
from src.demo_runner import run_demo_pipeline
from src.orchestrator import Orchestrator
from src.provider import create_client, get_model_name, load_config
from src.pptx_exporter import export_pitch_deck

load_dotenv()
logger = logging.getLogger(__name__)

DEMO_ENABLED = os.environ.get("ENABLE_DEMO", "").lower() in ("true", "1", "yes")


class RateLimiter:
    """Global in-memory rate limiter tracking pipeline runs per hour and day."""

    def __init__(self, hourly_limit: int = 10, daily_limit: int = 50) -> None:
        self.hourly_limit = hourly_limit
        self.daily_limit = daily_limit
        self._timestamps: list[float] = []

    def _prune(self, now: float) -> None:
        """Remove timestamps older than 24 hours."""
        cutoff = now - 86_400
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def check(self) -> str | None:
        """Return an error message if rate limited, or None if allowed."""
        now = time.monotonic()
        self._prune(now)

        one_hour_ago = now - 3_600
        hourly_count = sum(1 for t in self._timestamps if t > one_hour_ago)
        if hourly_count >= self.hourly_limit:
            return (
                f"Rate limit reached: {self.hourly_limit} runs per hour. "
                "Please try again later."
            )

        if len(self._timestamps) >= self.daily_limit:
            return (
                f"Daily limit reached: {self.daily_limit} runs per day. "
                "Please try again tomorrow."
            )

        return None

    def record(self) -> None:
        """Record a pipeline run."""
        self._timestamps.append(time.monotonic())


# Initialise rate limiter from config
_config = load_config("config.yaml")
_rl_cfg = _config.get("rate_limiting", {})
rate_limiter = RateLimiter(
    hourly_limit=_rl_cfg.get("hourly_limit", 10),
    daily_limit=_rl_cfg.get("daily_limit", 50),
)

app = FastAPI(title="The Agentic Production Company")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Track generated PPTX files by run ID
_generated_files: dict[str, Path] = {}


_RUN_ID_PATTERN = re.compile(r"^(demo-)?[a-f0-9]{12}$")


@app.get("/download/{run_id}")
async def download_pptx(run_id: str):
    """Download a generated PPTX file."""
    if not _RUN_ID_PATTERN.match(run_id):
        return JSONResponse(status_code=400, content={"error": "Invalid run ID"})
    path = _generated_files.get(run_id)
    if not path or not path.exists():
        return JSONResponse(status_code=404, content={"error": "File not found"})
    # Verify path is under the expected output directory
    if not path.resolve().is_relative_to(Path("output/web").resolve()):
        return JSONResponse(status_code=400, content={"error": "Invalid path"})
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="pitch_deck.pptx",
    )


@app.get("/")
async def index():
    """Serve the main frontend page."""
    return FileResponse("static/index.html")


@app.get("/config")
async def get_config():
    """Return frontend configuration flags."""
    return JSONResponse({"demo_enabled": DEMO_ENABLED})


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return JSONResponse({"status": "ok"})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for running the pipeline with live updates."""
    await websocket.accept()
    _MAX_MESSAGE_BYTES = 16_384  # 16 KB max WebSocket message
    _MAX_BRIEF_LENGTH = 2_000   # 2000 chars max brief

    try:
        while True:
            data = await websocket.receive_text()
            if len(data) > _MAX_MESSAGE_BYTES:
                await websocket.send_json(
                    {"type": "error", "message": "Message too large"}
                )
                continue

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "message": "Invalid JSON"}
                )
                continue

            msg_type = message.get("type")
            brief = str(message.get("brief", ""))[:_MAX_BRIEF_LENGTH]

            if msg_type == "demo":
                if not DEMO_ENABLED:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Demo mode is disabled. Set ENABLE_DEMO=true to enable.",
                    })
                    continue
                await _run_demo(websocket, brief)

            elif msg_type == "run":
                if not brief:
                    await websocket.send_json(
                        {"type": "error", "message": "No brief provided"}
                    )
                    continue

                # Check global rate limit before running
                limit_msg = rate_limiter.check()
                if limit_msg:
                    await websocket.send_json(
                        {"type": "error", "message": limit_msg}
                    )
                    continue

                rate_limiter.record()
                await _run_pipeline(websocket, brief)

            else:
                await websocket.send_json(
                    {"type": "error", "message": "Unknown message type"}
                )

    except WebSocketDisconnect:
        logger.info("Client disconnected")


async def _run_pipeline(websocket: WebSocket, brief: str) -> None:
    """Run the pipeline in a thread, emitting events over WebSocket."""
    loop = asyncio.get_event_loop()

    async def emit(event: dict) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    def sync_emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(emit(event), loop)

    # Set up live commentary engine (utility-tier LLM)
    config = load_config("config.yaml")
    commentary = CommentaryEngine(
        client=create_client(config),
        model=get_model_name(config, "utility"),
        emit_callback=sync_emit,
    )

    def sync_emit_with_commentary(event: dict) -> None:
        """Emit event to client AND feed it to the commentary engine."""
        sync_emit(event)
        commentary.ingest(event)

    await emit({"type": "pipeline_start", "brief": brief})

    def run_blocking():
        orchestrator = Orchestrator(config_path="config.yaml")
        orchestrator.set_event_callback(sync_emit_with_commentary)
        return orchestrator.run(brief)

    try:
        result = await loop.run_in_executor(None, run_blocking)

        if result.success:
            # Generate PPTX first (needs rendered_imagery bytes)
            run_id = secrets.token_hex(6)
            pptx_dir = Path("output/web")
            pptx_dir.mkdir(parents=True, exist_ok=True)
            pptx_path = pptx_dir / f"{run_id}.pptx"
            if result.pitch_deck:
                export_pitch_deck(result.pitch_deck, str(pptx_path))
                _generated_files[run_id] = pptx_path

            # Strip binary rendered_imagery before JSON serialization
            deck_for_json = {
                k: v for k, v in (result.pitch_deck or {}).items()
                if k != "rendered_imagery"
            } if result.pitch_deck else None

            # Generate outro commentary
            if deck_for_json:
                outro_text = await loop.run_in_executor(
                    None, commentary.generate_outro, deck_for_json
                )
                await emit({"type": "outro", "text": outro_text})

            await emit({
                "type": "pipeline_complete",
                "pitch_deck": deck_for_json,
                "evidence": result.evidence,
                "download_url": f"/download/{run_id}" if result.pitch_deck else None,
            })
        else:
            await emit({
                "type": "pipeline_error",
                "error": result.error,
            })
    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        await emit({
            "type": "pipeline_error",
            "error": "An error occurred processing your brief. Please try again.",
        })
    finally:
        commentary.shutdown()


async def _run_demo(websocket: WebSocket, brief: str) -> None:
    """Run the demo pipeline, emitting events over WebSocket."""

    async def emit(event: dict) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    try:
        result = await run_demo_pipeline(emit, brief)
        pitch_deck = result.get("pitch_deck")

        # Generate PPTX from demo data, same as the real pipeline
        run_id = "demo-" + secrets.token_hex(6)
        pptx_dir = Path("output/web")
        pptx_dir.mkdir(parents=True, exist_ok=True)
        pptx_path = pptx_dir / f"{run_id}.pptx"
        download_url = None
        if pitch_deck:
            export_pitch_deck(pitch_deck, str(pptx_path))
            _generated_files[run_id] = pptx_path
            download_url = f"/download/{run_id}"

        await emit({
            "type": "pipeline_complete",
            "pitch_deck": pitch_deck,
            "evidence": result.get("evidence"),
            "download_url": download_url,
        })
    except Exception as exc:
        logger.exception("Demo pipeline error: %s", exc)
        await emit({
            "type": "pipeline_error",
            "error": "An error occurred running the demo. Please try again.",
        })


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
