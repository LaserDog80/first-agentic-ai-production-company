"""Text-to-image skill backed by fal.ai.

The skill is factory-built per agent because each generated image is
persisted under `output/web/<run_id>/<seq>.png` and the run_id is only
known at graph-execution time. The factory closes over run_id, model,
image_size, and a per-call counter so successive invocations land on
distinct filenames.
"""
from __future__ import annotations

import itertools
import logging
import os
from pathlib import Path
from typing import Callable

import httpx

from src.tools import tool

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "fal-ai/flux/schnell"
DEFAULT_IMAGE_SIZE = "landscape_16_9"
_OUTPUT_DIR = Path("output/web")


def _save_image(image_url: str, run_id: str, seq: int) -> Path:
    """Download `image_url` and write it to output/web/<run_id>/<seq>.png."""
    run_dir = _OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / f"{seq}.png"
    with httpx.stream("GET", image_url, timeout=30.0) as resp:
        resp.raise_for_status()
        with out.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    return out


def _call_fal(prompt: str, model: str, image_size: str) -> dict:
    """Invoke fal.ai and return the first image dict."""
    import fal_client  # local import so test envs without the package still load

    if not os.environ.get("FAL_KEY"):
        raise RuntimeError(
            "FAL_KEY environment variable is not set. The generate_image skill "
            "needs a fal.ai API key — see https://fal.ai/dashboard/keys."
        )
    result = fal_client.subscribe(
        model,
        arguments={
            "prompt": prompt,
            "image_size": image_size,
        },
    )
    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"fal.ai returned no images for prompt: {prompt!r}")
    return images[0]


def build_generate_image_tool(
    run_id: str,
    model: str = DEFAULT_MODEL,
    image_size: str = DEFAULT_IMAGE_SIZE,
) -> Callable:
    """Return a `generate_image` tool bound to `run_id` and the configured model.

    The tool downloads each image and exposes it at /output-image/<run_id>/<n>.png.
    Successive calls within the same run increment a counter so each attempt
    has a distinct URL the UI can render.
    """
    # itertools.count is safe to share across the worker threads used for
    # parallel tool calls, unlike a bare dict increment.
    counter = itertools.count(1)
    cfg_model = model or DEFAULT_MODEL
    cfg_size = image_size or DEFAULT_IMAGE_SIZE

    @tool
    def generate_image(prompt: str) -> dict:
        """Generate an image from a text prompt using fal.ai.

        Use this when you need to produce a visual. The tool returns a URL
        the user can view; pass it back to whoever asked you for the image
        along with a one-line description of what you made.

        Args:
            prompt: A vivid, specific description of the image —
                composition, subject, lighting, mood, medium.
        """
        seq = next(counter)
        try:
            image = _call_fal(prompt, cfg_model, cfg_size)
        except Exception as exc:
            logger.warning("generate_image failed for run %s seq %d: %s",
                           run_id, seq, exc)
            return {
                "error": f"Image generation failed: {exc}",
                "attempt": seq,
            }
        try:
            _save_image(image["url"], run_id, seq)
        except Exception as exc:
            logger.warning("Failed to persist image for run %s seq %d: %s",
                           run_id, seq, exc)
            return {
                "image_url": image["url"],
                "attempt": seq,
                "warning": f"Could not cache locally: {exc}",
                "model": cfg_model,
            }
        return {
            "image_url": f"/output-image/{run_id}/{seq}.png",
            "attempt": seq,
            "prompt": prompt,
            "model": cfg_model,
        }

    return generate_image
