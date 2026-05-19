"""Text-to-image skill backed by fal.ai's flux-schnell endpoint.

The skill is factory-built per agent because each generated image is
persisted under `output/web/<run_id>/<seq>.png` and the run_id is only
known at graph-execution time. The factory closes over run_id and a
per-call counter so successive invocations land on distinct filenames.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

import httpx

from src.tools import tool

logger = logging.getLogger(__name__)

FAL_MODEL = "fal-ai/flux/schnell"
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


def _call_fal(prompt: str) -> dict:
    """Invoke fal.ai flux/schnell and return the first image dict."""
    import fal_client  # local import so test envs without the package still load

    if not os.environ.get("FAL_KEY"):
        raise RuntimeError(
            "FAL_KEY environment variable is not set. The generate_image skill "
            "needs a fal.ai API key — see https://fal.ai/dashboard/keys."
        )
    result = fal_client.subscribe(
        FAL_MODEL,
        arguments={
            "prompt": prompt,
            "image_size": "landscape_16_9",
        },
    )
    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"fal.ai returned no images for prompt: {prompt!r}")
    return images[0]


def build_generate_image_tool(run_id: str) -> Callable:
    """Return a `generate_image` tool bound to `run_id`.

    The tool downloads each image and exposes it at /output-image/<run_id>/<n>.png.
    Successive calls within the same run increment a counter so each attempt
    has a distinct URL the UI can render.
    """
    counter = {"n": 0}

    @tool
    def generate_image(prompt: str) -> dict:
        """Generate an image from a text prompt using fal.ai (flux-schnell).

        Use this when you need to produce a visual. Pass a vivid, specific
        description — composition, subject, lighting, mood, medium. The tool
        returns a URL the user can view; pass it back to whoever asked you
        for the image along with a one-line description of what you made.
        """
        counter["n"] += 1
        seq = counter["n"]
        try:
            image = _call_fal(prompt)
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
            }
        return {
            "image_url": f"/output-image/{run_id}/{seq}.png",
            "attempt": seq,
            "prompt": prompt,
        }

    return generate_image
