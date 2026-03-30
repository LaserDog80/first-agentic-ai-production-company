"""LLM-driven pixel art renderer.

Calls the Pixel Artist agent to generate bespoke pixel art scenes from
researcher imagery descriptions. Falls back to the procedural scene_renderer
if the LLM call fails or produces invalid output.

Pipeline: deck_imagery dict → artist LLM → palette + grid → Pillow image → PNG bytes
"""
import io
import json
import logging
import re
import time
from typing import Any

from PIL import Image, ImageDraw

from src.agent import AgentResult, AgentRuntime
from src.prompts import artist
from src.scene_renderer import render_scene_for_slot

logger = logging.getLogger(__name__)

# Canvas dimensions the artist LLM produces
GRID_COLS = 60
GRID_ROWS = 25
PALETTE_SIZE = 16


def _parse_artist_output(raw: str) -> tuple[list[str], list[str]] | None:
    """Parse the artist LLM output into (palette, rows).

    Returns None if the output is invalid.
    """
    # Strip markdown code fences if present
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Artist output is not valid JSON")
        return None

    palette = data.get("palette")
    rows = data.get("rows")

    if not isinstance(palette, list) or len(palette) != PALETTE_SIZE:
        logger.warning("Artist palette invalid: expected %d entries, got %s",
                        PALETTE_SIZE, len(palette) if isinstance(palette, list) else type(palette))
        return None

    # Validate palette entries are hex colors
    hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
    for i, color in enumerate(palette):
        if not isinstance(color, str) or not hex_pattern.match(color):
            logger.warning("Artist palette[%d] invalid: %s", i, color)
            return None

    if not isinstance(rows, list):
        logger.warning("Artist rows is not a list")
        return None

    # Tolerate minor row count variations — trim or warn
    if len(rows) < GRID_ROWS - 2 or len(rows) > GRID_ROWS + 2:
        logger.warning("Artist rows count %d too far from expected %d",
                        len(rows), GRID_ROWS)
        return None

    hex_chars = set("0123456789abcdefABCDEF")
    cleaned_rows: list[str] = []
    for i, row in enumerate(rows):
        if not isinstance(row, str):
            logger.warning("Artist row %d is not a string", i)
            return None
        # Strip any spaces or non-hex chars at edges
        row = row.strip()
        # Filter to only hex chars
        row = "".join(c for c in row if c in hex_chars)
        # Trim or pad to exact width
        if len(row) > GRID_COLS:
            row = row[:GRID_COLS]
        elif len(row) < GRID_COLS - 15:
            logger.warning("Artist row %d too short (%d chars)", i, len(row))
            return None
        elif len(row) < GRID_COLS:
            row = row + row[-1] * (GRID_COLS - len(row))  # pad with last color
        cleaned_rows.append(row)

    # Trim or pad row count
    if len(cleaned_rows) > GRID_ROWS:
        cleaned_rows = cleaned_rows[:GRID_ROWS]
    elif len(cleaned_rows) < GRID_ROWS:
        # Duplicate last row to fill
        while len(cleaned_rows) < GRID_ROWS:
            cleaned_rows.append(cleaned_rows[-1])

    return palette, cleaned_rows


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to (r, g, b)."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _render_grid_to_image(
    palette: list[str],
    rows: list[str],
    target_width: int = 960,
    target_height: int = 400,
) -> bytes:
    """Render a palette-indexed grid to a PNG image.

    Upscales the GRID_COLS x GRID_ROWS grid to the target dimensions.
    """
    # Convert palette to RGB
    rgb_palette = [_hex_to_rgb(c) for c in palette]

    # Calculate pixel scale
    px_w = target_width // GRID_COLS
    px_h = target_height // GRID_ROWS

    # Actual image size (may be slightly different from target due to rounding)
    img_w = px_w * GRID_COLS
    img_h = px_h * GRID_ROWS

    img = Image.new("RGB", (img_w, img_h))
    draw = ImageDraw.Draw(img)

    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            color_idx = int(ch, 16)
            color = rgb_palette[color_idx]
            x0 = x * px_w
            y0 = y * px_h
            draw.rectangle([x0, y0, x0 + px_w - 1, y0 + px_h - 1], fill=color)

    # Resize to exact target if needed
    if img.size != (target_width, target_height):
        img = img.resize((target_width, target_height), Image.NEAREST)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_user_message(imagery: dict, genre: str, tone: str) -> str:
    """Build the user message for the artist agent."""
    return json.dumps({
        "scene": {
            "concept": imagery.get("concept", ""),
            "elements": imagery.get("elements", []),
            "mood": imagery.get("mood", ""),
            "slot": imagery.get("slot", ""),
        },
        "show": {
            "genre": genre,
            "tone": tone,
        },
    })


def render_with_llm(
    imagery: dict,
    genre: str,
    tone: str,
    client: Any,
    model: str,
    width: int = 960,
    height: int = 400,
    timeout: int = 120,
    event_callback: Any = None,
) -> bytes | None:
    """Generate pixel art for a single deck imagery slot using the LLM artist.

    Args:
        imagery: deck_imagery entry dict (concept, elements, mood, slot)
        genre: Show genre
        tone: Show tone
        client: OpenAI-compatible client
        model: Model name to use
        width: Target image width
        height: Target image height
        timeout: LLM call timeout in seconds
        event_callback: Optional event callback for pipeline events

    Returns:
        PNG bytes if successful, None if the LLM fails or output is invalid.
    """
    slot = imagery.get("slot", "unknown")
    concept = imagery.get("concept", "")

    if event_callback:
        try:
            event_callback({
                "type": "tool_call",
                "agent": "artist",
                "tool": "render_scene",
                "args": {"slot": slot, "concept": concept[:60]},
                "message": f"Painting {slot}: {concept[:50]}...",
            })
        except Exception:
            pass

    user_message = _build_user_message(imagery, genre, tone)

    try:
        runtime = AgentRuntime(
            name="artist",
            system_prompt=artist.build_prompt(),
            tools=[],
            client=client,
            model=model,
            max_iterations=1,  # No tool loop needed — single shot
            timeout=timeout,
            event_callback=event_callback,
        )
        result = runtime.run(user_message)
    except Exception as exc:
        logger.warning("Artist agent call failed for slot '%s': %s", slot, exc)
        return None

    # Parse output
    parsed = _parse_artist_output(result.output)
    if parsed is None:
        logger.warning("Artist output invalid for slot '%s', falling back", slot)
        return None

    palette, rows = parsed

    try:
        return _render_grid_to_image(palette, rows, width, height)
    except Exception as exc:
        logger.warning("Artist grid render failed for slot '%s': %s", slot, exc)
        return None


def render_deck_imagery(
    deck_imagery: list[dict],
    genre: str,
    tone: str,
    client: Any,
    model: str,
    width: int = 960,
    height: int = 400,
    timeout: int = 120,
    event_callback: Any = None,
) -> dict[str, bytes]:
    """Render all deck imagery slots using the LLM artist.

    Falls back to procedural scene_renderer for any slot that fails.

    Args:
        deck_imagery: List of deck_imagery dicts from the researcher
        genre: Show genre
        tone: Show tone
        client: OpenAI-compatible client
        model: Model name
        width: Target image width
        height: Target image height
        timeout: Per-image LLM timeout
        event_callback: Optional pipeline event callback

    Returns:
        Dict mapping slot name → PNG bytes for each imagery entry.
    """
    rendered: dict[str, bytes] = {}

    for imagery in deck_imagery:
        slot = imagery.get("slot", "unknown")

        # Try LLM artist first
        img_bytes = render_with_llm(
            imagery, genre, tone, client, model,
            width=width, height=height, timeout=timeout,
            event_callback=event_callback,
        )

        if img_bytes is not None:
            rendered[slot] = img_bytes
            logger.info("Artist rendered slot '%s' via LLM", slot)
        else:
            # Fall back to procedural renderer
            try:
                img_bytes = render_scene_for_slot(
                    imagery, genre=genre, tone=tone,
                    width=width, height=height, pixel_size=4,
                )
                rendered[slot] = img_bytes
                logger.info("Artist fell back to procedural for slot '%s'", slot)
            except Exception as exc:
                logger.warning("Both LLM and procedural failed for '%s': %s",
                                slot, exc)

    return rendered
