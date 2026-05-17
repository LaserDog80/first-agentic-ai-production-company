"""FastAPI server for the Agentic Playground.

Serves the node-based playground UI and runs user-built graphs over a
WebSocket. The legacy linear pitch-deck pipeline is kept available as
the `pitch_deck` preset graph; the graph executor is the only runtime.
"""
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

from src.graph.executor import GraphExecutor, try_parse_pitch_deck
from src.graph.presets import list_presets, load_preset
from src.graph.schema import Graph, validate_graph
from src.graph.skills import list_available_skills
from src.pptx_exporter import export_pitch_deck
from src.provider import create_client, get_model_name, load_config

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


@app.get("/")
async def index():
    return FileResponse("static/chooser.html")


@app.get("/playground")
async def playground():
    return FileResponse("static/playground.html")


@app.get("/present")
async def present():
    return FileResponse("static/presentation.html")


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
    if not path.resolve().is_relative_to(Path("output/web").resolve()):
        return JSONResponse(status_code=400, content={"error": "Invalid path"})
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="pitch_deck.pptx",
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _MAX_BYTES = 65_536
    _MAX_BRIEF = 4_000

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
                await _run_graph(websocket, graph_dict, brief)

            else:
                await websocket.send_json({
                    "type": "error", "message": f"Unknown message type: {mtype}"
                })

    except WebSocketDisconnect:
        logger.info("Client disconnected")


def _validate(graph_dict: dict) -> tuple[bool, list[str]]:
    try:
        graph = Graph.model_validate(graph_dict)
    except Exception as exc:
        return False, [f"Schema parse error: {exc}"]
    errors = validate_graph(graph)
    return (not errors), errors


async def _run_graph(websocket: WebSocket, graph_dict: dict, brief: str) -> None:
    loop = asyncio.get_event_loop()

    async def emit(event: dict) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    def sync_emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(emit(event), loop)

    config = load_config("config.yaml")

    def run_blocking():
        client = create_client(config)
        graph = Graph.model_validate(graph_dict)
        executor = GraphExecutor(graph, client, config, emit=sync_emit)
        return executor.run(brief), graph

    try:
        result, graph = await loop.run_in_executor(None, run_blocking)
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
            run_id = secrets.token_hex(6)
            pptx_dir = Path("output/web")
            pptx_dir.mkdir(parents=True, exist_ok=True)
            pptx_path = pptx_dir / f"{run_id}.pptx"
            try:
                export_pitch_deck(pitch_deck_obj, str(pptx_path))
                _generated_files[run_id] = pptx_path
                download_url = f"/download/{run_id}"
            except Exception as exc:
                logger.warning("PPTX export failed: %s", exc)

    await emit({
        "type": "run_summary",
        "ok": result.get("ok", False),
        "output_subtype": result.get("output_subtype", ""),
        "pitch_deck": pitch_deck_obj,
        "download_url": download_url,
    })


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
