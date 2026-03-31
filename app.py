"""FastAPI web server with WebSocket for real-time pipeline updates."""
import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.commentary import CommentaryEngine
from src.orchestrator import Orchestrator
from src.provider import create_client, get_model_name, load_config
from src.pptx_exporter import export_pitch_deck

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="The Agentic Production Company")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Track generated PPTX files by run ID
_generated_files: dict[str, Path] = {}


@app.get("/download/{run_id}")
async def download_pptx(run_id: str):
    """Download a generated PPTX file."""
    path = _generated_files.get(run_id)
    if not path or not path.exists():
        return JSONResponse(status_code=404, content={"error": "File not found"})
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="pitch_deck.pptx",
    )


@app.get("/")
async def index():
    """Serve the main frontend page."""
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for running the pipeline with live updates."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "run":
                brief = message.get("brief", "")
                if not brief:
                    await websocket.send_json({"type": "error", "message": "No brief provided"})
                    continue

                await _run_pipeline(websocket, brief)

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
            import hashlib
            run_id = hashlib.md5(brief.encode()).hexdigest()[:12]
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
        await emit({
            "type": "pipeline_error",
            "error": str(exc),
        })
    finally:
        commentary.shutdown()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
