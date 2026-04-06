"""FastAPI web server with WebSocket for real-time multi-pipeline updates."""
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
from src.core.pipeline import discover_pipelines, create_pipeline, PipelineDefinition
from src.demo_runner import run_demo_pipeline
from src.provider import create_client, get_model_name, load_config

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
        cutoff = now - 86_400
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def check(self) -> str | None:
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
        self._timestamps.append(time.monotonic())


# Initialise rate limiter from config
_config = load_config("config.yaml")
_rl_cfg = _config.get("rate_limiting", {})
rate_limiter = RateLimiter(
    hourly_limit=_rl_cfg.get("hourly_limit", 10),
    daily_limit=_rl_cfg.get("daily_limit", 50),
)

app = FastAPI(title="Multi-Agent Orchestration Framework")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Track generated files by run ID
_generated_files: dict[str, Path] = {}

_RUN_ID_PATTERN = re.compile(r"^(demo-)?[a-f0-9]{12}$")


@app.get("/download/{run_id}")
async def download_file(run_id: str):
    """Download a generated file."""
    if not _RUN_ID_PATTERN.match(run_id):
        return JSONResponse(status_code=400, content={"error": "Invalid run ID"})
    path = _generated_files.get(run_id)
    if not path or not path.exists():
        return JSONResponse(status_code=404, content={"error": "File not found"})
    if not path.resolve().is_relative_to(Path("output/web").resolve()):
        return JSONResponse(status_code=400, content={"error": "Invalid path"})
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=path.name,
    )


@app.get("/")
async def index():
    """Serve the main frontend page."""
    return FileResponse("static/index.html")


@app.get("/config")
async def get_config():
    """Return frontend configuration flags."""
    return JSONResponse({"demo_enabled": DEMO_ENABLED})


@app.get("/api/pipelines")
async def list_pipelines():
    """Return all available pipelines and their metadata."""
    pipelines = discover_pipelines()
    result = []
    for pid, defn in pipelines.items():
        result.append({
            "id": defn.id,
            "name": defn.name,
            "description": defn.description,
            "category": defn.category,
            "version": defn.version,
            "input": {
                "type": defn.input_config.type,
                "label": defn.input_config.label,
                "placeholder": defn.input_config.placeholder,
                "max_length": defn.input_config.max_length,
            },
            "agents": {
                name: {"role": cfg.get("role", name)}
                for name, cfg in defn.agents.items()
            },
            "steps": [
                {"id": s.id, "label": s.label, "description": s.description, "agent": s.agent}
                for s in defn.steps
            ],
            "has_review": defn.review.enabled,
        })
    return JSONResponse(result)


@app.get("/health")
async def health_check():
    return JSONResponse({"status": "ok"})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for running pipelines with live updates."""
    await websocket.accept()
    _MAX_MESSAGE_BYTES = 16_384
    _MAX_INPUT_LENGTH = 2_000

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
            input_text = str(message.get("brief", message.get("input", "")))[:_MAX_INPUT_LENGTH]
            pipeline_id = message.get("pipeline", "tv_production")

            if msg_type == "demo":
                if not DEMO_ENABLED:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Demo mode is disabled. Set ENABLE_DEMO=true.",
                    })
                    continue
                await _run_demo(websocket, input_text)

            elif msg_type == "run":
                if not input_text:
                    await websocket.send_json(
                        {"type": "error", "message": "No input provided"}
                    )
                    continue

                limit_msg = rate_limiter.check()
                if limit_msg:
                    await websocket.send_json(
                        {"type": "error", "message": limit_msg}
                    )
                    continue

                rate_limiter.record()
                await _run_pipeline(websocket, input_text, pipeline_id)

            else:
                await websocket.send_json(
                    {"type": "error", "message": "Unknown message type"}
                )

    except WebSocketDisconnect:
        logger.info("Client disconnected")


async def _run_pipeline(websocket: WebSocket, input_text: str, pipeline_id: str) -> None:
    """Run a pipeline in a thread, emitting events over WebSocket."""
    loop = asyncio.get_event_loop()

    async def emit(event: dict) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    def sync_emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(emit(event), loop)

    # Set up live commentary engine
    config = load_config("config.yaml")
    commentary = CommentaryEngine(
        client=create_client(config),
        model=get_model_name(config, "utility"),
        emit_callback=sync_emit,
    )

    def sync_emit_with_commentary(event: dict) -> None:
        sync_emit(event)
        commentary.ingest(event)

    await emit({"type": "pipeline_start", "brief": input_text, "pipeline": pipeline_id})

    def run_blocking():
        pipeline = create_pipeline(pipeline_id, global_config_path="config.yaml")
        pipeline.set_event_callback(sync_emit_with_commentary)
        return pipeline.run(input_text)

    try:
        result = await loop.run_in_executor(None, run_blocking)

        if result.success:
            run_id = secrets.token_hex(6)
            download_url = None

            # TV Production: generate PPTX
            if pipeline_id == "tv_production" and result.output:
                try:
                    from src.pptx_exporter import export_pitch_deck
                    pptx_dir = Path("output/web")
                    pptx_dir.mkdir(parents=True, exist_ok=True)
                    pptx_path = pptx_dir / f"{run_id}.pptx"
                    export_pitch_deck(result.output, str(pptx_path))
                    _generated_files[run_id] = pptx_path
                    download_url = f"/download/{run_id}"
                except Exception:
                    pass

            # Strip binary data before JSON serialization
            output_for_json = {
                k: v for k, v in (result.output or {}).items()
                if k != "rendered_imagery"
            } if result.output else None

            # Generate outro commentary
            if output_for_json:
                outro_text = await loop.run_in_executor(
                    None, commentary.generate_outro, output_for_json
                )
                await emit({"type": "outro", "text": outro_text})

            await emit({
                "type": "pipeline_complete",
                "pipeline": pipeline_id,
                "output": output_for_json,
                "evidence": result.evidence,
                "download_url": download_url,
                # Backward compat for TV production frontend
                "pitch_deck": output_for_json if pipeline_id == "tv_production" else None,
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
            "error": "An error occurred. Please try again.",
        })
    finally:
        commentary.shutdown()


async def _run_demo(websocket: WebSocket, brief: str) -> None:
    """Run the demo pipeline (TV Production fixture data)."""

    async def emit(event: dict) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    try:
        result = await run_demo_pipeline(emit, brief)
        pitch_deck = result.get("pitch_deck")

        run_id = "demo-" + secrets.token_hex(6)
        pptx_dir = Path("output/web")
        pptx_dir.mkdir(parents=True, exist_ok=True)
        pptx_path = pptx_dir / f"{run_id}.pptx"
        download_url = None
        if pitch_deck:
            from src.pptx_exporter import export_pitch_deck
            export_pitch_deck(pitch_deck, str(pptx_path))
            _generated_files[run_id] = pptx_path
            download_url = f"/download/{run_id}"

        await emit({
            "type": "pipeline_complete",
            "pipeline": "tv_production",
            "output": pitch_deck,
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
