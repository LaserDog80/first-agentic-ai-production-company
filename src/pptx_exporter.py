"""Convert PitchDeck JSON to PowerPoint (.pptx) files."""
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN


# Slide dimensions (standard 16:9)
SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)

# Colors
DARK_BLUE = RGBColor(0x1B, 0x3A, 0x5C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_GREY = RGBColor(0xF2, 0xF2, 0xF2)
BLACK = RGBColor(0x00, 0x00, 0x00)
DARK_GREY = RGBColor(0x33, 0x33, 0x33)

# Font sizes
TITLE_SIZE = Pt(32)
SUBTITLE_SIZE = Pt(18)
HEADING_SIZE = Pt(28)
BODY_SIZE = Pt(16)
SMALL_SIZE = Pt(12)
TABLE_SIZE = Pt(10)

# Layout margins
LEFT_MARGIN = Inches(0.8)
TOP_MARGIN = Inches(1.2)
CONTENT_WIDTH = Inches(11.7)
CONTENT_HEIGHT = Inches(5.5)

MAX_CELL_CHARS = 150


def export_pitch_deck(pitch_deck: dict, output_path: str) -> Path:
    """Convert a PitchDeck dict to a .pptx file.

    Args:
        pitch_deck: The PitchDeck dict (same structure as pitch_deck.json).
        output_path: File path for the output .pptx file.

    Returns:
        Path to the written .pptx file.
    """
    path = Path(output_path)
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    _add_title_slide(prs, pitch_deck.get("title_page", {}))

    prs.save(str(path))
    return path


def _add_text_box(
    slide,
    left: int,
    top: int,
    width: int,
    height: int,
    text: str,
    font_size: Pt = BODY_SIZE,
    bold: bool = False,
    color: RGBColor = DARK_GREY,
    alignment: int = PP_ALIGN.LEFT,
) -> None:
    """Add a text box to a slide."""
    txbox = slide.shapes.add_textbox(left, top, width, height)
    tf = txbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = font_size
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = alignment


def _add_title_slide(prs: Presentation, title_page: dict) -> None:
    """Slide 1: Title page with working title, genre, format, broadcaster."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout

    title = title_page.get("working_title", "Untitled")
    genre = title_page.get("genre", "")
    fmt = title_page.get("format", "")
    broadcaster = title_page.get("target_broadcaster", "")

    # Title — centered, large
    _add_text_box(
        slide,
        left=LEFT_MARGIN,
        top=Inches(2.0),
        width=CONTENT_WIDTH,
        height=Inches(1.5),
        text=title,
        font_size=TITLE_SIZE,
        bold=True,
        color=DARK_BLUE,
        alignment=PP_ALIGN.CENTER,
    )

    # Subtitle line: genre | format | broadcaster
    subtitle_parts = [p for p in [genre, fmt, broadcaster] if p]
    subtitle = "  |  ".join(subtitle_parts)
    _add_text_box(
        slide,
        left=LEFT_MARGIN,
        top=Inches(3.8),
        width=CONTENT_WIDTH,
        height=Inches(0.8),
        text=subtitle,
        font_size=SUBTITLE_SIZE,
        color=DARK_GREY,
        alignment=PP_ALIGN.CENTER,
    )
