"""FastAPI server for the Agentic Playground.

Serves the node-based playground UI and runs user-built graphs over a
WebSocket. Runs execute as background tasks so the socket stays
responsive — a `stop_run` message (or the client disconnecting) sets a
cancel event that the executor checks between LLM iterations.
"""
import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.graph.executor import GraphExecutor, try_parse_pitch_deck
from src.graph.presets import list_presets, load_preset
from src.graph.schema import Graph, validate_graph
from src.graph.skills import list_available_skills
from src.pptx_exporter import export_pitch_deck
from src.provider import create_client, load_config

load_dotenv()
logger = logging.getLogger(__name__)


class RateLimiter:
    """Global in-memory rate limiter tracking graph runs per hour and day."""

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
        hourly = sum(1 for t in self._timestamps if t > one_hour_ago)
        if hourly >= self.hourly_limit:
            return f"Rate limit reached: {self.hourly_limit} runs per hour."
        if len(self._timestamps) >= self.daily_limit:
            return f"Daily limit reached: {self.daily_limit} runs per day."
        return None

    def record(self) -> None:
        self._timestamps.append(time.monotonic())


_config = load_config("config.yaml")
_rl_cfg = _config.get("rate_limiting", {})
rate_limiter = RateLimiter(
    hourly_limit=_rl_cfg.get("hourly_limit", 10),
    daily_limit=_rl_cfg.get("daily_limit", 50),
)

app = FastAPI(title="Agentic Playground")
app.mount("/static", StaticFiles(directory="static"), name="static")

_generated_files: dict[str, Path] = {}
_RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{12}$")
_IMAGE_NAME_PATTERN = re.compile(r"^[0-9]+\.png$")
_OUTPUT_ROOT = Path("output/web")
_KEEP_RUN_ARTEFACTS = 40


_NO_STORE = {"Cache-Control": "no-store, must-revalidate"}


@app.get("/")
async def index():
    return FileResponse("static/chooser.html", headers=_NO_STORE)


@app.get("/playground")
async def playground():
    return FileResponse("static/playground.html", headers=_NO_STORE)


@app.get("/present")
async def present():
    return FileResponse("static/presentation.html", headers=_NO_STORE)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.get("/download/{run_id}")
async def download_pptx(run_id: str):
    if not _RUN_ID_PATTERN.match(run_id):
        return JSONResponse(status_code=400, content={"error": "Invalid run ID"})
    path = _generated_files.get(run_id)
    if not path or not path.exists():
        return JSONResponse(status_code=404, content={"error": "File not found"})
    if not path.resolve().is_relative_to(_OUTPUT_ROOT.resolve()):
        return JSONResponse(status_code=400, content={"error": "Invalid path"})
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="pitch_deck.pptx",
    )


@app.get("/output-image/{run_id}/{name}")
async def output_image(run_id: str, name: str):
    if not _RUN_ID_PATTERN.match(run_id):
        return JSONResponse(status_code=400, content={"error": "Invalid run ID"})
    if not _IMAGE_NAME_PATTERN.match(name):
        return JSONResponse(status_code=400, content={"error": "Invalid image name"})
    path = _OUTPUT_ROOT / run_id / name
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Image not found"})
    if not path.resolve().is_relative_to(_OUTPUT_ROOT.resolve()):
        return JSONResponse(status_code=400, content={"error": "Invalid path"})
    return FileResponse(str(path), media_type="image/png")


def _prune_run_artefacts(keep: int = _KEEP_RUN_ARTEFACTS) -> None:
    """Delete the oldest run artefacts so output/web doesn't grow forever."""
    if not _OUTPUT_ROOT.is_dir():
        return
    try:
        entries = sorted(
            _OUTPUT_ROOT.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for stale in entries[keep:]:
        try:
            if stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)
            else:
                stale.unlink(missing_ok=True)
        except OSError:
            pass
    for rid, path in list(_generated_files.items()):
        if not path.exists():
            _generated_files.pop(rid, None)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _MAX_BYTES = 65_536
    _MAX_BRIEF = 4_000

    run_task: asyncio.Task | None = None
    cancel_event: threading.Event | None = None

    try:
        while True:
            data = await websocket.receive_text()
            if len(data) > _MAX_BYTES:
                await websocket.send_json({"type": "error", "message": "Message too large"})
                continue
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            mtype = msg.get("type")

            if mtype == "list_presets":
                await websocket.send_json({
                    "type": "presets",
                    "presets": list_presets(),
                    "skills": list_available_skills(),
                })

            elif mtype == "load_preset":
                preset_id = str(msg.get("id", ""))
                data = load_preset(preset_id)
                if not data:
                    await websocket.send_json({
                        "type": "error", "message": f"Unknown preset '{preset_id}'."
                    })
                    continue
                await websocket.send_json({"type": "graph", "graph": data})

            elif mtype == "validate_graph":
                graph_dict = msg.get("graph") or {}
                ok, errors = _validate(graph_dict)
                await websocket.send_json({
                    "type": "validation", "ok": ok, "errors": errors,
                })

            elif mtype == "run_graph":
                if run_task is not None and not run_task.done():
                    await websocket.send_json({
                        "type": "error",
                        "message": "A run is already in progress — stop it first.",
                    })
                    continue
                graph_dict = msg.get("graph") or {}
                brief = str(msg.get("brief", ""))[:_MAX_BRIEF]
                if not brief:
                    await websocket.send_json({"type": "error", "message": "No brief provided"})
                    continue
                ok, errors = _validate(graph_dict)
                if not ok:
                    await websocket.send_json({
                        "type": "error", "message": "Invalid graph: " + "; ".join(errors),
                    })
                    continue
                limit_msg = rate_limiter.check()
                if limit_msg:
                    await websocket.send_json({"type": "error", "message": limit_msg})
                    continue
                rate_limiter.record()
                cancel_event = threading.Event()
                run_task = asyncio.create_task(
                    _run_graph(websocket, graph_dict, brief, cancel_event)
                )

            elif mtype == "stop_run":
                if run_task is not None and not run_task.done() and cancel_event:
                    cancel_event.set()
                else:
                    await websocket.send_json({
                        "type": "error", "message": "No run in progress.",
                    })

            else:
                await websocket.send_json({
                    "type": "error", "message": f"Unknown message type: {mtype}"
                })

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        # Don't keep burning tokens for a client that is gone.
        if cancel_event is not None:
            cancel_event.set()


def _validate(graph_dict: dict) -> tuple[bool, list[str]]:
    try:
        graph = Graph.model_validate(graph_dict)
    except Exception as exc:
        return False, [f"Schema parse error: {exc}"]
    errors = validate_graph(graph, limits=_config.get("limits"))
    return (not errors), errors


async def _run_graph(
    websocket: WebSocket,
    graph_dict: dict,
    brief: str,
    cancel_event: threading.Event,
) -> None:
    loop = asyncio.get_event_loop()

    async def emit(event: dict) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    def sync_emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(emit(event), loop)

    run_id = secrets.token_hex(6)
    _prune_run_artefacts()

    def run_blocking():
        client = create_client(_config)
        graph = Graph.model_validate(graph_dict)
        executor = GraphExecutor(
            graph, client, _config, emit=sync_emit, run_id=run_id,
            cancel_event=cancel_event,
        )
        return executor.run(brief)

    try:
        result = await loop.run_in_executor(None, run_blocking)
    except Exception as exc:
        logger.exception("Graph run error: %s", exc)
        await emit({"type": "graph_run_error",
                    "error": "An error occurred. Please try again."})
        return

    # Pitch-deck post-run hook: if any output node is a pitch_deck and the
    # final output parses as a pitch deck, generate a PPTX.
    download_url = None
    pitch_deck_obj = None
    if result.get("ok") and result.get("output_subtype") == "pitch_deck":
        pitch_deck_obj = try_parse_pitch_deck(result.get("output", ""))
        if pitch_deck_obj:
            _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
            pptx_path = _OUTPUT_ROOT / f"{run_id}.pptx"
            try:
                export_pitch_deck(pitch_deck_obj, str(pptx_path))
                _generated_files[run_id] = pptx_path
                download_url = f"/download/{run_id}"
            except Exception as exc:
                logger.warning("PPTX export failed: %s", exc)

    # Image-output post-run hook: surface any images the generate_image
    # skill persisted under output/web/<run_id>/, in iteration order.
    images: list[dict] = []
    if result.get("ok") and result.get("output_subtype") == "image":
        run_dir = _OUTPUT_ROOT / run_id
        if run_dir.is_dir():
            for path in sorted(
                run_dir.glob("*.png"),
                key=lambda p: int(p.stem) if p.stem.isdigit() else 0,
            ):
                images.append({
                    "url": f"/output-image/{run_id}/{path.name}",
                    "attempt": int(path.stem) if path.stem.isdigit() else 0,
                })

    await emit({
        "type": "run_summary",
        "ok": result.get("ok", False),
        "output_subtype": result.get("output_subtype", ""),
        "pitch_deck": pitch_deck_obj,
        "download_url": download_url,
        "images": images,
        "tokens": result.get("tokens"),
        "cost_usd": result.get("cost_usd"),
    })


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
