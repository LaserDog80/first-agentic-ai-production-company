"""Composable pixel art scene renderer for pitch deck imagery.

Takes keyword-based scene descriptions from the researcher and renders
recognizable pixel art scenes at medium-high definition. No external APIs —
everything is procedural using Pillow.

Scene composition:
1. Parse concept keywords to select a scene template + elements
2. Render background layer (sky gradient, ground, water)
3. Place mid-ground elements (mountains, buildings, trees)
4. Place foreground elements (people, vehicles, objects)
5. Apply genre-based color grading
"""
import hashlib
import io
import math
from typing import Any

from PIL import Image, ImageDraw

from src.pixel_art import _get_palette, _hex_to_rgb, _seed_rng, _lcg


# ── ELEMENT SPRITE DATA ──
# Each sprite is a list of (relative_x, relative_y, color_index) or row-based
# pixel maps. color_index maps into the scene palette at render time.

# Sprite definitions: each is a 2D grid where values are palette indices
# 0 = transparent, 1-5 = palette colors (bg, text, accent1, accent2, accent3)

def _draw_pixel_block(
    draw: ImageDraw.Draw, x: int, y: int, size: int,
    color: tuple[int, int, int],
) -> None:
    """Draw a single pixel block."""
    draw.rectangle([x, y, x + size - 1, y + size - 1], fill=color)


def _lerp_color(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float,
) -> tuple[int, int, int]:
    """Linear interpolate between two RGB colors."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Darken a color by a factor (0.0 = black, 1.0 = unchanged)."""
    return tuple(max(0, int(c * factor)) for c in color)


def _lighten(
    color: tuple[int, int, int], factor: float,
) -> tuple[int, int, int]:
    """Lighten a color toward white by factor (0.0 = unchanged, 1.0 = white)."""
    return tuple(min(255, int(c + (255 - c) * factor)) for c in color)


# ── SKY RENDERERS ──

def _draw_sky_gradient(
    draw: ImageDraw.Draw, width: int, height: int, ps: int,
    top_color: tuple[int, int, int], bottom_color: tuple[int, int, int],
    state: int,
) -> int:
    """Draw a vertical gradient sky."""
    cols = width // ps
    rows = height // ps
    for y in range(rows):
        t = y / max(rows - 1, 1)
        base = _lerp_color(top_color, bottom_color, t)
        for x in range(cols):
            state, r = _lcg(state)
            # Subtle dither
            v = int((r - 0.5) * 6)
            color = tuple(max(0, min(255, c + v)) for c in base)
            _draw_pixel_block(draw, x * ps, y * ps, ps, color)
    return state


def _draw_clouds(
    draw: ImageDraw.Draw, width: int, sky_height: int, ps: int,
    cloud_color: tuple[int, int, int], count: int, state: int,
) -> int:
    """Draw fluffy pixel clouds."""
    cols = width // ps
    for _ in range(count):
        state, rx = _lcg(state)
        state, ry = _lcg(state)
        state, rw = _lcg(state)
        cx = int(rx * (cols - 12))
        cy = int(ry * (sky_height // ps * 0.5)) + 2
        cloud_w = int(rw * 6) + 5
        # Cloud body — elliptical cluster of blocks
        for dx in range(cloud_w):
            # Height varies across cloud width to make it puffy
            t = dx / max(cloud_w - 1, 1)
            h = int(math.sin(t * math.pi) * 3) + 1
            for dy in range(-h, 1):
                px, py = cx + dx, cy + dy
                if 0 <= px < cols and 0 <= py < sky_height // ps:
                    state, rv = _lcg(state)
                    shade = _lighten(cloud_color, 0.1 + rv * 0.15)
                    _draw_pixel_block(draw, px * ps, py * ps, ps, shade)
    return state


def _draw_stars(
    draw: ImageDraw.Draw, width: int, sky_height: int, ps: int,
    star_color: tuple[int, int, int], density: int, state: int,
) -> int:
    """Draw stars for night scenes."""
    cols = width // ps
    rows = sky_height // ps
    for _ in range(density):
        state, rx = _lcg(state)
        state, ry = _lcg(state)
        state, rb = _lcg(state)
        x = int(rx * cols)
        y = int(ry * rows)
        brightness = 0.5 + rb * 0.5
        color = _lighten(star_color, brightness)
        _draw_pixel_block(draw, x * ps, y * ps, ps, color)
    return state


# ── TERRAIN RENDERERS ──

def _draw_mountains(
    draw: ImageDraw.Draw, width: int, base_y: int, ps: int,
    color: tuple[int, int, int], snow_color: tuple[int, int, int],
    count: int, state: int,
) -> int:
    """Draw mountain silhouettes with snow caps."""
    cols = width // ps
    for _ in range(count):
        state, rx = _lcg(state)
        state, rh = _lcg(state)
        state, rw = _lcg(state)
        peak_x = int(rx * cols)
        peak_h = int(rh * 18) + 10
        half_w = int(rw * 12) + 8
        peak_y = base_y // ps - peak_h

        for dx in range(-half_w, half_w + 1):
            x = peak_x + dx
            if x < 0 or x >= cols:
                continue
            # Height at this x follows triangle slope
            dist = abs(dx) / max(half_w, 1)
            col_h = int(peak_h * (1.0 - dist))
            for dy in range(col_h):
                py = base_y // ps - col_h + dy
                if py < 0:
                    continue
                # Snow on top 25%
                snow_t = dy / max(col_h - 1, 1)
                if snow_t < 0.25:
                    state, rv = _lcg(state)
                    c = _lighten(snow_color, rv * 0.2)
                else:
                    shade = 0.6 + 0.4 * (1.0 - dist)
                    state, rv = _lcg(state)
                    c = _darken(color, shade + (rv - 0.5) * 0.1)
                _draw_pixel_block(draw, x * ps, py * ps, ps, c)
    return state


def _draw_hills(
    draw: ImageDraw.Draw, width: int, base_y: int, ps: int,
    color: tuple[int, int, int], count: int, state: int,
) -> int:
    """Draw rolling hills using sine-ish curves."""
    cols = width // ps
    # Build a height map by adding sine waves
    heights = [0.0] * cols
    for _ in range(count):
        state, rp = _lcg(state)
        state, ra = _lcg(state)
        state, rf = _lcg(state)
        phase = rp * math.pi * 2
        amplitude = ra * 8 + 3
        freq = rf * 0.08 + 0.03
        for x in range(cols):
            heights[x] += math.sin(x * freq + phase) * amplitude

    for x in range(cols):
        h = int(heights[x])
        for dy in range(abs(h) + 4):
            py = base_y // ps - h + dy if h > 0 else base_y // ps + dy
            if py < 0:
                continue
            state, rv = _lcg(state)
            shade = 0.8 + (rv - 0.5) * 0.15
            c = _darken(color, shade)
            _draw_pixel_block(draw, x * ps, py * ps, ps, c)
    return state


def _draw_ground(
    draw: ImageDraw.Draw, width: int, ground_y: int, height: int,
    ps: int, color: tuple[int, int, int], state: int,
) -> int:
    """Draw flat ground with texture variation."""
    cols = width // ps
    rows = (height - ground_y) // ps
    for y in range(rows):
        depth_t = y / max(rows - 1, 1)
        base = _darken(color, 0.85 + depth_t * 0.15)
        for x in range(cols):
            state, rv = _lcg(state)
            v = int((rv - 0.5) * 18)
            c = tuple(max(0, min(255, ch + v)) for ch in base)
            _draw_pixel_block(draw, x * ps, (ground_y // ps + y) * ps, ps, c)
    return state


def _draw_water(
    draw: ImageDraw.Draw, width: int, water_y: int, height: int,
    ps: int, color: tuple[int, int, int], highlight: tuple[int, int, int],
    state: int,
) -> int:
    """Draw water with wave reflections."""
    cols = width // ps
    rows = (height - water_y) // ps
    for y in range(rows):
        depth_t = y / max(rows - 1, 1)
        base = _darken(color, 0.7 + depth_t * 0.3)
        for x in range(cols):
            state, rv = _lcg(state)
            # Horizontal wave highlight
            wave = math.sin(x * 0.3 + y * 0.8 + rv * 2) * 0.5 + 0.5
            if wave > 0.85 and depth_t < 0.6:
                c = _lighten(highlight, 0.3 + rv * 0.2)
            else:
                v = int((rv - 0.5) * 12)
                c = tuple(max(0, min(255, ch + v)) for ch in base)
            _draw_pixel_block(draw, x * ps, (water_y // ps + y) * ps, ps, c)
    return state


# ── OBJECT RENDERERS ──

def _draw_tree_pine(
    draw: ImageDraw.Draw, x: int, base_y: int, ps: int,
    trunk_color: tuple[int, int, int],
    leaf_color: tuple[int, int, int], height: int, state: int,
) -> int:
    """Draw a pine/conifer tree."""
    # Trunk
    for dy in range(3):
        _draw_pixel_block(draw, x * ps, (base_y - dy) * ps, ps, trunk_color)

    # Triangular canopy layers
    tip_y = base_y - height
    for layer in range(3):
        layer_base = base_y - 3 - layer * (height // 4)
        layer_top = layer_base - height // 3
        for dy in range(layer_base - layer_top):
            row_y = layer_top + dy
            half_w = (dy * 2) // max(layer_base - layer_top, 1) + 1
            for dx in range(-half_w, half_w + 1):
                state, rv = _lcg(state)
                shade = 0.7 + rv * 0.3
                c = _darken(leaf_color, shade)
                _draw_pixel_block(draw, (x + dx) * ps, row_y * ps, ps, c)
    return state


def _draw_tree_deciduous(
    draw: ImageDraw.Draw, x: int, base_y: int, ps: int,
    trunk_color: tuple[int, int, int],
    leaf_color: tuple[int, int, int], size: int, state: int,
) -> int:
    """Draw a round deciduous tree."""
    # Trunk
    for dy in range(4):
        _draw_pixel_block(draw, x * ps, (base_y - dy) * ps, ps, trunk_color)

    # Round canopy
    center_y = base_y - 4 - size // 2
    radius = size // 2 + 1
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= radius:
                state, rv = _lcg(state)
                if dist > radius - 0.8 and rv > 0.5:
                    continue  # Irregular edge
                shade = 0.6 + (1.0 - dist / radius) * 0.4
                c = _darken(leaf_color, shade + (rv - 0.5) * 0.15)
                _draw_pixel_block(
                    draw, (x + dx) * ps, (center_y + dy) * ps, ps, c,
                )
    return state


def _draw_building(
    draw: ImageDraw.Draw, x: int, base_y: int, ps: int,
    wall_color: tuple[int, int, int],
    window_color: tuple[int, int, int],
    bw: int, bh: int, state: int,
) -> int:
    """Draw a rectangular building with windows."""
    # Wall
    for dy in range(bh):
        for dx in range(bw):
            state, rv = _lcg(state)
            v = int((rv - 0.5) * 10)
            c = tuple(max(0, min(255, ch + v)) for ch in wall_color)
            _draw_pixel_block(draw, (x + dx) * ps, (base_y - bh + dy) * ps, ps, c)

    # Windows — grid pattern
    win_margin = 1
    win_spacing = 3
    for wy in range(win_margin + 1, bh - 1, win_spacing):
        for wx in range(win_margin, bw - win_margin, win_spacing):
            state, rv = _lcg(state)
            lit = rv > 0.3  # 70% chance window is lit
            c = window_color if lit else _darken(wall_color, 0.7)
            py = base_y - bh + wy
            px = x + wx
            _draw_pixel_block(draw, px * ps, py * ps, ps, c)
            # Window is 2px wide
            if wx + 1 < bw - win_margin:
                _draw_pixel_block(draw, (px + 1) * ps, py * ps, ps, c)
    return state


def _draw_person_silhouette(
    draw: ImageDraw.Draw, x: int, base_y: int, ps: int,
    color: tuple[int, int, int], height: int, state: int,
) -> int:
    """Draw a simple person silhouette."""
    # Head (2x2 circle)
    head_y = base_y - height
    _draw_pixel_block(draw, x * ps, head_y * ps, ps, color)
    _draw_pixel_block(draw, (x + 1) * ps, head_y * ps, ps, color)
    _draw_pixel_block(draw, x * ps, (head_y + 1) * ps, ps, color)
    _draw_pixel_block(draw, (x + 1) * ps, (head_y + 1) * ps, ps, color)

    # Body
    body_h = height - 4
    for dy in range(body_h):
        _draw_pixel_block(draw, x * ps, (head_y + 2 + dy) * ps, ps, color)
        _draw_pixel_block(draw, (x + 1) * ps, (head_y + 2 + dy) * ps, ps, color)

    # Legs
    leg_y = head_y + 2 + body_h
    for dy in range(2):
        _draw_pixel_block(draw, (x - 1) * ps, (leg_y + dy) * ps, ps, color)
        _draw_pixel_block(draw, (x + 2) * ps, (leg_y + dy) * ps, ps, color)

    return state


def _draw_boat(
    draw: ImageDraw.Draw, x: int, water_y: int, ps: int,
    hull_color: tuple[int, int, int],
    sail_color: tuple[int, int, int], size: int, state: int,
) -> int:
    """Draw a simple sailboat."""
    # Hull — trapezoid shape
    hull_y = water_y // ps - 2
    for dy in range(2):
        half_w = size // 2 + 1 - dy
        for dx in range(-half_w, half_w + 1):
            _draw_pixel_block(draw, (x + dx) * ps, (hull_y + dy) * ps, ps, hull_color)

    # Mast
    mast_h = size + 2
    for dy in range(mast_h):
        _draw_pixel_block(draw, x * ps, (hull_y - dy) * ps, ps, hull_color)

    # Sail — triangle
    sail_top = hull_y - mast_h
    for dy in range(mast_h - 1):
        sw = (dy * size) // max(mast_h - 1, 1) // 2 + 1
        for dx in range(1, sw + 1):
            state, rv = _lcg(state)
            c = _lighten(sail_color, rv * 0.2)
            _draw_pixel_block(draw, (x + dx) * ps, (sail_top + dy) * ps, ps, c)
    return state


def _draw_sun(
    draw: ImageDraw.Draw, x: int, y: int, ps: int,
    color: tuple[int, int, int], radius: int,
) -> None:
    """Draw a sun disc."""
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                glow = 1.0 - math.sqrt(dx * dx + dy * dy) / radius * 0.3
                c = _lighten(color, glow * 0.3)
                _draw_pixel_block(draw, (x + dx) * ps, (y + dy) * ps, ps, c)


def _draw_moon(
    draw: ImageDraw.Draw, x: int, y: int, ps: int,
    color: tuple[int, int, int], radius: int,
) -> None:
    """Draw a crescent moon."""
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            dist = math.sqrt(dx * dx + dy * dy)
            # Carve crescent by subtracting offset circle
            offset_dist = math.sqrt((dx - 2) ** 2 + dy * dy)
            if dist <= radius and offset_dist > radius - 1:
                c = _lighten(color, 0.3)
                _draw_pixel_block(draw, (x + dx) * ps, (y + dy) * ps, ps, c)


def _draw_camera(
    draw: ImageDraw.Draw, x: int, base_y: int, ps: int,
    color: tuple[int, int, int],
) -> None:
    """Draw a simple camera/film equipment icon."""
    # Camera body
    for dy in range(3):
        for dx in range(5):
            _draw_pixel_block(draw, (x + dx) * ps, (base_y - 3 + dy) * ps, ps, color)
    # Lens
    _draw_pixel_block(draw, (x + 5) * ps, (base_y - 2) * ps, ps, color)
    _draw_pixel_block(draw, (x + 6) * ps, (base_y - 2) * ps, ps, color)
    # Tripod legs
    _draw_pixel_block(draw, (x + 1) * ps, base_y * ps, ps, color)
    _draw_pixel_block(draw, (x + 3) * ps, base_y * ps, ps, color)
    _draw_pixel_block(draw, x * ps, (base_y + 1) * ps, ps, color)
    _draw_pixel_block(draw, (x + 4) * ps, (base_y + 1) * ps, ps, color)


def _draw_fish(
    draw: ImageDraw.Draw, x: int, y: int, ps: int,
    color: tuple[int, int, int],
) -> None:
    """Draw a simple fish."""
    # Body — diamond shape
    body = [(0, 0), (1, -1), (1, 0), (1, 1), (2, -1), (2, 0), (2, 1), (3, 0)]
    for dx, dy in body:
        _draw_pixel_block(draw, (x + dx) * ps, (y + dy) * ps, ps, color)
    # Tail
    _draw_pixel_block(draw, (x - 1) * ps, (y - 1) * ps, ps, color)
    _draw_pixel_block(draw, (x - 1) * ps, (y + 1) * ps, ps, color)


# ── SCENE KEYWORD MAPPING ──

# Map keywords to scene composition instructions
KEYWORD_ELEMENTS = {
    # Nature / landscape
    "mountain": "mountains", "mountains": "mountains", "highland": "mountains",
    "alps": "mountains", "peak": "mountains", "summit": "mountains",
    "hill": "hills", "hills": "hills", "rolling": "hills", "valley": "hills",
    "forest": "trees_pine", "woodland": "trees_pine", "pine": "trees_pine",
    "jungle": "trees_deciduous", "rainforest": "trees_deciduous",
    "tree": "trees_deciduous", "trees": "trees_deciduous", "park": "trees_deciduous",
    "ocean": "water", "sea": "water", "coast": "water", "beach": "water",
    "river": "water", "lake": "water", "harbor": "water", "harbour": "water",
    "underwater": "water_deep", "marine": "water_deep", "reef": "water_deep",
    # Urban
    "city": "cityscape", "urban": "cityscape", "skyline": "cityscape",
    "town": "buildings_small", "village": "buildings_small", "street": "buildings_small",
    "building": "buildings_small", "house": "buildings_small",
    "skyscraper": "cityscape", "tower": "cityscape",
    # Sky / atmosphere
    "sunset": "sunset_sky", "sunrise": "sunrise_sky", "dawn": "sunrise_sky",
    "dusk": "sunset_sky", "twilight": "sunset_sky",
    "night": "night_sky", "dark": "night_sky", "midnight": "night_sky",
    "stars": "night_sky", "moon": "night_sky",
    "storm": "storm_sky", "rain": "storm_sky", "cloudy": "cloudy_sky",
    "cloud": "cloudy_sky", "overcast": "cloudy_sky",
    # People / activity
    "people": "people", "person": "people", "crowd": "people",
    "crew": "people", "team": "people", "worker": "people",
    "filmmaker": "camera", "camera": "camera", "filming": "camera",
    "production": "camera", "documentary": "camera",
    # Vehicles / transport
    "boat": "boat", "ship": "boat", "sailing": "boat", "fishing": "boat",
    "vehicle": "vehicle", "car": "vehicle", "truck": "vehicle",
    # Animals
    "fish": "fish", "whale": "fish", "marine_life": "fish",
    "bird": "bird", "wildlife": "bird",
    # Misc
    "desert": "desert", "sand": "desert", "arid": "desert",
    "snow": "snow", "ice": "snow", "arctic": "snow", "winter": "snow",
    "fire": "fire", "flame": "fire", "volcano": "fire",
    "ruin": "ruins", "ancient": "ruins", "historic": "ruins",
    "castle": "ruins", "monument": "ruins",
}

# Scene templates — define the layer composition for common scene types
SCENE_TEMPLATES = {
    "landscape": {
        "sky_ratio": 0.5,
        "ground_color_idx": 3,  # accent2
        "default_elements": ["hills"],
    },
    "seascape": {
        "sky_ratio": 0.45,
        "water_ratio": 0.55,
        "ground_color_idx": 4,  # accent3
        "default_elements": ["water"],
    },
    "cityscape": {
        "sky_ratio": 0.4,
        "ground_color_idx": 2,  # accent1
        "default_elements": ["cityscape"],
    },
    "underwater": {
        "sky_ratio": 0.0,
        "water_ratio": 1.0,
        "ground_color_idx": 4,
        "default_elements": ["water_deep", "fish"],
    },
    "night": {
        "sky_ratio": 0.55,
        "ground_color_idx": 3,
        "default_elements": ["night_sky"],
    },
    "interior": {
        "sky_ratio": 0.0,
        "ground_color_idx": 2,
        "default_elements": [],
    },
}


def _classify_scene(concept: str, elements: list[str]) -> str:
    """Determine scene template from concept text and element keywords."""
    text = concept.lower()
    all_kw = text.split() + [e.lower() for e in elements]

    if any(w in all_kw for w in ("underwater", "reef", "marine", "submersible")):
        return "underwater"
    if any(w in all_kw for w in ("ocean", "sea", "coast", "beach", "harbor",
                                  "harbour", "boat", "ship", "sailing", "fishing")):
        return "seascape"
    if any(w in all_kw for w in ("city", "urban", "skyline", "skyscraper", "tower")):
        return "cityscape"
    if any(w in all_kw for w in ("night", "dark", "midnight", "stars", "moon")):
        return "night"
    if any(w in all_kw for w in ("indoor", "interior", "studio", "room", "office")):
        return "interior"
    return "landscape"


def _resolve_elements(concept: str, element_keywords: list[str]) -> list[str]:
    """Map concept + keywords to element render instructions."""
    all_words = concept.lower().split() + [e.lower() for e in element_keywords]
    resolved = []
    seen = set()
    for word in all_words:
        elem = KEYWORD_ELEMENTS.get(word)
        if elem and elem not in seen:
            resolved.append(elem)
            seen.add(elem)
    return resolved


def _sky_colors_for_mood(
    mood: str, palette_colors: list[tuple[int, int, int]],
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Return (top_color, horizon_color) for sky based on mood."""
    mood_lower = (mood or "").lower()
    if any(w in mood_lower for w in ("dark", "gritty", "tense", "mysterious")):
        return (10, 10, 25), _darken(palette_colors[0], 0.6)
    if any(w in mood_lower for w in ("warm", "intimate", "hopeful")):
        return (40, 60, 100), (180, 120, 80)
    if any(w in mood_lower for w in ("bright", "cheerful", "fun", "energetic")):
        return (60, 120, 200), (140, 180, 220)
    if any(w in mood_lower for w in ("epic", "grand", "vast")):
        return (20, 30, 80), (80, 60, 120)
    if any(w in mood_lower for w in ("calm", "peaceful", "serene")):
        return (70, 130, 190), (160, 200, 230)
    # Default — genre palette derived
    return _darken(palette_colors[0], 0.8), palette_colors[0]


def render_scene(
    concept: str,
    element_keywords: list[str],
    genre: str = "",
    tone: str = "",
    mood: str = "",
    width: int = 960,
    height: int = 400,
    pixel_size: int = 4,
    seed: int = 0,
) -> bytes:
    """Render a pixel art scene from a concept description.

    Args:
        concept: Natural language scene description (e.g. "Scottish highlands at dawn")
        element_keywords: List of element keywords (e.g. ["mountains", "heather", "mist"])
        genre: Show genre for palette selection
        tone: Show tone for palette selection
        mood: Scene mood (e.g. "epic", "intimate", "dark")
        width: Output image width in pixels
        height: Output image height in pixels
        pixel_size: Size of each "pixel" block (higher = more chunky)
        seed: RNG seed for deterministic output

    Returns:
        PNG image bytes.
    """
    from src.pixel_art import _get_palette, _hex_to_rgb

    palette = _get_palette(genre, tone)
    colors = [_hex_to_rgb(c) for c in palette]
    # colors: [bg, text, accent1, accent2, accent3]

    scene_type = _classify_scene(concept, element_keywords)
    template = SCENE_TEMPLATES.get(scene_type, SCENE_TEMPLATES["landscape"])
    elements = _resolve_elements(concept, element_keywords)
    if not elements:
        elements = template["default_elements"]

    state = _seed_rng(f"{concept}{genre}{tone}{seed}")

    img = Image.new("RGB", (width, height), colors[0])
    draw = ImageDraw.Draw(img)
    ps = pixel_size
    cols = width // ps
    rows = height // ps

    sky_ratio = template.get("sky_ratio", 0.5)
    water_ratio = template.get("water_ratio", 0.0)
    sky_h = int(height * sky_ratio)
    ground_y = sky_h
    water_y = int(height * (1.0 - water_ratio)) if water_ratio > 0 else height

    # ── Layer 1: Sky ──
    if sky_ratio > 0:
        sky_top, sky_bottom = _sky_colors_for_mood(mood, colors)

        # Detect sunset/sunrise
        concept_lower = concept.lower()
        if any(w in concept_lower for w in ("sunset", "dusk", "twilight")):
            sky_top = (40, 20, 60)
            sky_bottom = (220, 120, 50)
        elif any(w in concept_lower for w in ("sunrise", "dawn")):
            sky_top = (30, 40, 80)
            sky_bottom = (200, 150, 80)

        if "night_sky" in elements:
            sky_top = (5, 5, 15)
            sky_bottom = (15, 15, 40)

        state = _draw_sky_gradient(draw, width, sky_h, ps, sky_top, sky_bottom, state)

        # Celestial objects
        if "night_sky" in elements:
            state = _draw_stars(draw, width, sky_h, ps, (220, 220, 255), 40, state)
            _draw_moon(draw, cols - 10, 5, ps, (230, 230, 200), 3)
        elif "sunset_sky" not in elements and "storm_sky" not in elements:
            sun_x = cols - 12
            sun_y = sky_h // ps // 3
            _draw_sun(draw, sun_x, sun_y, ps, (255, 220, 100), 3)

        # Clouds
        if "storm_sky" in elements:
            state = _draw_clouds(draw, width, sky_h, ps, (60, 60, 70), 6, state)
        elif "cloudy_sky" in elements:
            state = _draw_clouds(draw, width, sky_h, ps, (200, 200, 210), 4, state)
        elif "night_sky" not in elements:
            state = _draw_clouds(
                draw, width, sky_h, ps, (230, 235, 240), 2, state,
            )

    # ── Layer 2: Terrain background ──
    ground_color = colors[template.get("ground_color_idx", 3)]

    if "mountains" in elements:
        mt_color = _darken(colors[4], 0.7)
        snow_color = (220, 225, 230)
        state, rc = _lcg(state)
        count = int(rc * 2) + 2
        state = _draw_mountains(
            draw, width, ground_y, ps, mt_color, snow_color, count, state,
        )

    if "hills" in elements:
        hill_color = _darken(colors[3], 0.8)
        state = _draw_hills(draw, width, ground_y, ps, hill_color, 4, state)

    # ── Layer 3: Ground / Water ──
    if water_ratio > 0 or "water" in elements:
        actual_water_y = min(water_y, ground_y)
        water_color = (30, 80, 130)
        highlight = (100, 160, 210)
        if "water_deep" in elements:
            water_color = (10, 30, 60)
            highlight = (30, 80, 120)
            actual_water_y = 0
        state = _draw_water(
            draw, width, actual_water_y, height, ps,
            water_color, highlight, state,
        )
    elif scene_type != "interior":
        # Ground plane
        if "desert" in elements:
            ground_color = (180, 150, 90)
        elif "snow" in elements:
            ground_color = (220, 225, 235)
        state = _draw_ground(draw, width, ground_y, height, ps, ground_color, state)

    # ── Layer 4: Mid-ground objects ──
    if "cityscape" in elements:
        state, rb = _lcg(state)
        num_buildings = int(rb * 4) + 4
        for i in range(num_buildings):
            state, rx = _lcg(state)
            state, rh = _lcg(state)
            state, rw = _lcg(state)
            bx = int(rx * (cols - 10)) + 2
            bh = int(rh * 20) + 8
            bw = int(rw * 4) + 3
            wall = _darken(colors[2], 0.5 + i * 0.05)
            window = (255, 230, 150)
            state = _draw_building(
                draw, bx, ground_y // ps, ps, wall, window, bw, bh, state,
            )

    if "buildings_small" in elements:
        state, rb = _lcg(state)
        num_buildings = int(rb * 3) + 2
        for i in range(num_buildings):
            state, rx = _lcg(state)
            state, rh = _lcg(state)
            state, rw = _lcg(state)
            bx = int(rx * (cols - 8)) + 2
            bh = int(rh * 8) + 5
            bw = int(rw * 3) + 3
            wall = _lerp_color(colors[2], colors[3], i / max(num_buildings - 1, 1))
            window = (255, 240, 180)
            state = _draw_building(
                draw, bx, ground_y // ps, ps, wall, window, bw, bh, state,
            )

    if "trees_pine" in elements:
        state, rt = _lcg(state)
        num_trees = int(rt * 6) + 4
        trunk_c = (80, 50, 30)
        leaf_c = (30, 90, 40)
        for _ in range(num_trees):
            state, rx = _lcg(state)
            state, rh = _lcg(state)
            tx = int(rx * (cols - 4)) + 2
            th = int(rh * 8) + 8
            state = _draw_tree_pine(
                draw, tx, ground_y // ps - 1, ps, trunk_c, leaf_c, th, state,
            )

    if "trees_deciduous" in elements:
        state, rt = _lcg(state)
        num_trees = int(rt * 5) + 3
        trunk_c = (90, 60, 30)
        leaf_c = (50, 120, 50)
        for _ in range(num_trees):
            state, rx = _lcg(state)
            state, rs = _lcg(state)
            tx = int(rx * (cols - 6)) + 3
            sz = int(rs * 4) + 4
            state = _draw_tree_deciduous(
                draw, tx, ground_y // ps - 1, ps, trunk_c, leaf_c, sz, state,
            )

    if "ruins" in elements:
        # Draw broken columns / wall fragments
        state, rn = _lcg(state)
        num_ruins = int(rn * 3) + 2
        stone_c = (140, 130, 110)
        for _ in range(num_ruins):
            state, rx = _lcg(state)
            state, rh = _lcg(state)
            state, rw = _lcg(state)
            rx_pos = int(rx * (cols - 6)) + 2
            rh_val = int(rh * 10) + 5
            rw_val = int(rw * 2) + 2
            for dy in range(rh_val):
                for dx in range(rw_val):
                    state, rv = _lcg(state)
                    if rv > 0.15:  # Gaps for ruined look
                        v = int((rv - 0.5) * 20)
                        c = tuple(max(0, min(255, ch + v)) for ch in stone_c)
                        py = ground_y // ps - rh_val + dy
                        _draw_pixel_block(draw, (rx_pos + dx) * ps, py * ps, ps, c)

    # ── Layer 5: Foreground objects ──
    if "boat" in elements:
        state, rx = _lcg(state)
        bx = int(rx * (cols // 2)) + cols // 4
        hull_c = (100, 50, 30)
        sail_c = (230, 230, 220)
        actual_wy = water_y if water_ratio > 0 else ground_y
        state = _draw_boat(draw, bx, actual_wy, ps, hull_c, sail_c, 5, state)

    if "fish" in elements and ("water" in elements or "water_deep" in elements):
        state, rn = _lcg(state)
        num_fish = int(rn * 5) + 3
        for _ in range(num_fish):
            state, rx = _lcg(state)
            state, ry = _lcg(state)
            state, rc = _lcg(state)
            fx = int(rx * (cols - 6)) + 2
            fy_start = water_y // ps if water_ratio > 0 else ground_y // ps
            fy = fy_start + int(ry * (rows - fy_start - 2)) + 1
            fish_c = _lerp_color(colors[1], colors[2], rc)
            _draw_fish(draw, fx, fy, ps, fish_c)

    if "people" in elements:
        state, rn = _lcg(state)
        num_people = int(rn * 4) + 2
        for _ in range(num_people):
            state, rx = _lcg(state)
            state, rh = _lcg(state)
            state, rc = _lcg(state)
            px = int(rx * (cols - 4)) + 2
            ph = int(rh * 3) + 6
            person_c = _lerp_color(colors[1], colors[4], rc)
            state = _draw_person_silhouette(
                draw, px, ground_y // ps - 1, ps, person_c, ph, state,
            )

    if "camera" in elements:
        state, rx = _lcg(state)
        cx = int(rx * (cols // 3)) + cols // 3
        cam_c = colors[1]
        _draw_camera(draw, cx, ground_y // ps - 1, ps, cam_c)

    # ── Layer 6: Atmospheric overlay ──
    # Apply a subtle genre-tinted vignette
    vignette_color = colors[0]
    for y in range(rows):
        for x in range(cols):
            # Distance from center (normalized 0-1)
            cx_norm = (x - cols / 2) / (cols / 2)
            cy_norm = (y - rows / 2) / (rows / 2)
            dist = math.sqrt(cx_norm * cx_norm + cy_norm * cy_norm)
            if dist > 0.85:
                # Darken edges
                alpha = min((dist - 0.85) / 0.4, 0.35)
                px = x * ps
                py = y * ps
                # Read existing pixel and blend
                existing = img.getpixel((px + ps // 2, py + ps // 2))
                blended = _lerp_color(existing, vignette_color, alpha)
                _draw_pixel_block(draw, px, py, ps, blended)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_scene_for_slot(
    imagery: dict,
    genre: str = "",
    tone: str = "",
    width: int = 960,
    height: int = 400,
    pixel_size: int = 4,
) -> bytes:
    """Convenience wrapper: render a scene from a deck_imagery dict entry.

    Args:
        imagery: Dict with keys: concept, elements, mood, slot
        genre: Show genre
        tone: Show tone
        width: Image width
        height: Image height
        pixel_size: Pixel block size

    Returns:
        PNG bytes.
    """
    return render_scene(
        concept=imagery.get("concept", ""),
        element_keywords=imagery.get("elements", []),
        genre=genre,
        tone=tone,
        mood=imagery.get("mood", ""),
        width=width,
        height=height,
        pixel_size=pixel_size,
        seed=hash(imagery.get("slot", "")) & 0xFFFF,
    )
