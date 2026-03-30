"""Procedural pixel art generator for pitch deck visuals.

Generates title cards and abstract mood art based on genre/tone metadata.
No external APIs — everything is algorithmic using Pillow.
"""
import hashlib
import io
from typing import Any

from PIL import Image, ImageDraw

# ── 5x7 PIXEL FONT ──
# Each glyph is 7 rows of 5-bit integers (MSB = leftmost pixel)
PIXEL_FONT: dict[str, list[int]] = {
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "B": [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    "D": [0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F],
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "J": [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "N": [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    "Q": [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "S": [0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E],
    "T": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "V": [0x11, 0x11, 0x11, 0x11, 0x0A, 0x0A, 0x04],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "Y": [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    "Z": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    "3": [0x0E, 0x11, 0x01, 0x06, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "6": [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    "7": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    "8": [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    " ": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    ":": [0x00, 0x04, 0x04, 0x00, 0x04, 0x04, 0x00],
    "-": [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
    "'": [0x04, 0x04, 0x08, 0x00, 0x00, 0x00, 0x00],
    ".": [0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x04],
    ",": [0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x08],
    "!": [0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04],
    "?": [0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04],
    "&": [0x0C, 0x12, 0x0C, 0x1A, 0x13, 0x13, 0x0D],
    "/": [0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10],
    "(": [0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02],
    ")": [0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08],
}


# ── GENRE → PALETTE MAPPING ──
# Each palette: (background, text, accent1, accent2, accent3)
PALETTES: dict[str, tuple[str, ...]] = {
    "documentary": ("#1a2632", "#d4c5a9", "#8b7355", "#5c6b4f", "#3d5a80"),
    "observational": ("#1c2333", "#b0c4de", "#6b8cae", "#4a6670", "#8898aa"),
    "entertainment": ("#1a1a2e", "#f0c987", "#e86833", "#4ecca3", "#3d5a80"),
    "factual": ("#1a2632", "#d4c5a9", "#8b7355", "#5c6b4f", "#3d5a80"),
    "comedy": ("#2d1b3d", "#f5e663", "#e94560", "#4ecca3", "#ff9a3c"),
    "drama": ("#1a1a2e", "#e8d5b7", "#c45b3e", "#6b3a5c", "#2a4a6b"),
    "reality": ("#2a1f2e", "#f0c987", "#e86833", "#c43a6b", "#4a9080"),
    "true_crime": ("#0d0d0d", "#c0392b", "#e74c3c", "#7f8c8d", "#2c3e50"),
    "nature": ("#0f2419", "#a8d08d", "#5b8a3c", "#3d6b4f", "#7eb89a"),
    "travel": ("#162447", "#e8a87c", "#d4956b", "#41729f", "#5c8a97"),
    "history": ("#1a1410", "#d4a76a", "#8b6914", "#5c4033", "#3a2820"),
}

DEFAULT_PALETTE = ("#16213e", "#eaeaea", "#f5c542", "#4ecca3", "#e94560")


def _get_palette(genre: str, tone: str) -> tuple[str, ...]:
    """Match genre text to a color palette."""
    genre_lower = (genre or "").lower()
    for key, palette in PALETTES.items():
        if key in genre_lower:
            return palette
    # Try tone as fallback
    tone_lower = (tone or "").lower()
    if "warm" in tone_lower or "intimate" in tone_lower:
        return PALETTES["documentary"]
    if "dark" in tone_lower or "gritty" in tone_lower:
        return PALETTES["true_crime"]
    if "light" in tone_lower or "funny" in tone_lower:
        return PALETTES["comedy"]
    return DEFAULT_PALETTE


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to (r, g, b)."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _seed_rng(seed_str: str) -> int:
    """Create a deterministic seed from a string."""
    return int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)


def _lcg(state: int) -> tuple[int, float]:
    """Simple linear congruential generator. Returns (next_state, 0.0-1.0)."""
    state = (state * 1103515245 + 12345) & 0x7FFFFFFF
    return state, state / 0x7FFFFFFF


# ── TITLE CARD GENERATOR ──

def generate_title_card(
    title: str, genre: str = "", tone: str = "",
    max_width: int = 640, padding: int = 24, scale: int = 4,
) -> bytes:
    """Render a show title as pixel-art text on a genre-colored background.

    Returns PNG bytes.
    """
    palette = _get_palette(genre, tone)
    bg_rgb = _hex_to_rgb(palette[0])
    text_rgb = _hex_to_rgb(palette[1])
    accent_rgb = _hex_to_rgb(palette[2])

    title_upper = title.upper()

    # Calculate text dimensions with word wrapping
    glyph_w = 5 * scale
    glyph_h = 7 * scale
    space_w = 2 * scale  # gap between chars
    line_gap = 3 * scale  # gap between lines
    content_width = max_width - 2 * padding

    # Word wrap
    words = title_upper.split()
    lines: list[str] = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip() if current_line else word
        test_width = len(test) * (glyph_w + space_w) - space_w
        if test_width > content_width and current_line:
            lines.append(current_line)
            current_line = word
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    # Image dimensions
    total_text_h = len(lines) * glyph_h + (len(lines) - 1) * line_gap
    img_height = total_text_h + 2 * padding + 8 * scale  # extra for accent bar

    img = Image.new("RGB", (max_width, img_height), bg_rgb)
    draw = ImageDraw.Draw(img)

    # Draw accent bar at top
    for x in range(0, max_width, scale * 2):
        draw.rectangle(
            [x, 0, x + scale - 1, scale - 1],
            fill=accent_rgb,
        )

    # Draw accent bar at bottom
    bottom_y = img_height - scale
    for x in range(scale, max_width, scale * 2):
        draw.rectangle(
            [x, bottom_y, x + scale - 1, img_height - 1],
            fill=accent_rgb,
        )

    # Draw text lines (centered)
    y_offset = padding + 4 * scale
    for line in lines:
        line_width = len(line) * (glyph_w + space_w) - space_w
        x_offset = (max_width - line_width) // 2

        for ch in line:
            glyph = PIXEL_FONT.get(ch)
            if glyph is None:
                x_offset += glyph_w + space_w
                continue
            for row_idx, row_bits in enumerate(glyph):
                for col in range(5):
                    if row_bits & (0x10 >> col):
                        px = x_offset + col * scale
                        py = y_offset + row_idx * scale
                        draw.rectangle(
                            [px, py, px + scale - 1, py + scale - 1],
                            fill=text_rgb,
                        )
            x_offset += glyph_w + space_w

        y_offset += glyph_h + line_gap

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── MOOD ART GENERATOR ──

def generate_mood_art(
    genre: str = "", tone: str = "", width: int = 640, height: int = 120,
    seed: int = 0, pixel_size: int = 8,
) -> bytes:
    """Generate abstract pixel art patterns based on genre/tone.

    Pattern types:
    - documentary/factual/observational: horizontal strata (geological layers)
    - comedy/reality: scattered bright blocks
    - drama/true_crime: diagonal bands
    - nature/travel: gradient waves
    - default: horizontal gradient with accent dots

    Returns PNG bytes.
    """
    palette = _get_palette(genre, tone)
    colors = [_hex_to_rgb(c) for c in palette]

    cols = width // pixel_size
    rows = height // pixel_size
    img = Image.new("RGB", (width, height), colors[0])
    draw = ImageDraw.Draw(img)

    genre_lower = (genre or "").lower()
    state = _seed_rng(f"{genre}{tone}{seed}")

    if any(k in genre_lower for k in ("documentary", "factual", "observational", "history")):
        # Horizontal strata — layered bands with slight variation
        for y in range(rows):
            band = (y * len(colors)) // rows
            base_color = colors[min(band, len(colors) - 1)]
            for x in range(cols):
                state, r = _lcg(state)
                # Slight color variation
                variation = int((r - 0.5) * 20)
                color = tuple(max(0, min(255, c + variation)) for c in base_color)
                draw.rectangle(
                    [x * pixel_size, y * pixel_size,
                     (x + 1) * pixel_size - 1, (y + 1) * pixel_size - 1],
                    fill=color,
                )

    elif any(k in genre_lower for k in ("comedy", "reality")):
        # Scattered bright blocks on dark background
        draw.rectangle([0, 0, width, height], fill=colors[0])
        for _ in range(cols * rows // 3):
            state, rx = _lcg(state)
            state, ry = _lcg(state)
            state, rc = _lcg(state)
            x = int(rx * cols)
            y = int(ry * rows)
            color = colors[1 + int(rc * (len(colors) - 1))]
            block_size = pixel_size
            state, rs = _lcg(state)
            if rs > 0.7:
                block_size = pixel_size * 2
            draw.rectangle(
                [x * pixel_size, y * pixel_size,
                 x * pixel_size + block_size - 1, y * pixel_size + block_size - 1],
                fill=color,
            )

    elif any(k in genre_lower for k in ("drama", "true_crime", "crime")):
        # Diagonal bands with high contrast
        for y in range(rows):
            for x in range(cols):
                band = ((x + y) * len(colors)) // (cols + rows)
                state, r = _lcg(state)
                variation = int((r - 0.5) * 15)
                base = colors[min(band, len(colors) - 1)]
                color = tuple(max(0, min(255, c + variation)) for c in base)
                draw.rectangle(
                    [x * pixel_size, y * pixel_size,
                     (x + 1) * pixel_size - 1, (y + 1) * pixel_size - 1],
                    fill=color,
                )

    elif any(k in genre_lower for k in ("nature", "travel")):
        # Gradient waves
        for y in range(rows):
            for x in range(cols):
                state, r = _lcg(state)
                # Sine-ish wave pattern
                wave = ((x + int(r * 3)) % (cols // 2)) / max(cols // 2, 1)
                idx = int(wave * (len(colors) - 1))
                base = colors[min(idx, len(colors) - 1)]
                variation = int((r - 0.5) * 25)
                color = tuple(max(0, min(255, c + variation)) for c in base)
                draw.rectangle(
                    [x * pixel_size, y * pixel_size,
                     (x + 1) * pixel_size - 1, (y + 1) * pixel_size - 1],
                    fill=color,
                )

    else:
        # Default: horizontal gradient with accent dots
        for y in range(rows):
            blend = y / max(rows - 1, 1)
            base = tuple(
                int(colors[0][i] * (1 - blend) + colors[3][i] * blend)
                for i in range(3)
            )
            for x in range(cols):
                state, r = _lcg(state)
                if r > 0.92:
                    color = colors[2]  # accent dot
                else:
                    variation = int((r - 0.5) * 12)
                    color = tuple(max(0, min(255, c + variation)) for c in base)
                draw.rectangle(
                    [x * pixel_size, y * pixel_size,
                     (x + 1) * pixel_size - 1, (y + 1) * pixel_size - 1],
                    fill=color,
                )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
