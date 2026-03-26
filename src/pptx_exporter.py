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
    _add_logline_slide(prs, pitch_deck.get("logline", ""))
    _add_format_slide(prs, pitch_deck.get("format_and_tone", {}))
    _add_audience_slide(prs, pitch_deck.get("target_audience", ""))

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


def _add_slide_heading(slide, text: str) -> None:
    """Add a heading at the top of a content slide."""
    _add_text_box(
        slide,
        left=LEFT_MARGIN,
        top=Inches(0.4),
        width=CONTENT_WIDTH,
        height=Inches(0.7),
        text=text,
        font_size=HEADING_SIZE,
        bold=True,
        color=DARK_BLUE,
    )


def _add_logline_slide(prs: Presentation, logline: str) -> None:
    """Slide 2: Logline — prominent centered text."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_slide_heading(slide, "Logline")
    _add_text_box(
        slide,
        left=LEFT_MARGIN,
        top=Inches(2.0),
        width=CONTENT_WIDTH,
        height=Inches(4.0),
        text=logline,
        font_size=SUBTITLE_SIZE,
        color=DARK_GREY,
        alignment=PP_ALIGN.CENTER,
    )


def _add_format_slide(prs: Presentation, format_and_tone: dict) -> None:
    """Slide 3: Format & Tone — bullet list."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_slide_heading(slide, "Format & Tone")

    items = [
        f"Series Length: {format_and_tone.get('series_length', 'N/A')}",
        f"Genre: {format_and_tone.get('genre', 'N/A')}",
        f"Tone: {format_and_tone.get('tone', 'N/A')}",
    ]

    txbox = slide.shapes.add_textbox(
        LEFT_MARGIN, TOP_MARGIN, CONTENT_WIDTH, CONTENT_HEIGHT
    )
    tf = txbox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = item
        p.font.size = BODY_SIZE
        p.font.color.rgb = DARK_GREY
        p.space_after = Pt(12)


def _add_audience_slide(prs: Presentation, target_audience: str) -> None:
    """Slide 4: Target Audience — text block."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_slide_heading(slide, "Target Audience")
    _add_text_box(
        slide,
        left=LEFT_MARGIN,
        top=TOP_MARGIN,
        width=CONTENT_WIDTH,
        height=CONTENT_HEIGHT,
        text=target_audience,
        font_size=BODY_SIZE,
    )


def _add_why_now_slide(prs: Presentation, why_now: str) -> None:
    """Slide 11: Why Now — text block."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_slide_heading(slide, "Why Now")
    _add_text_box(
        slide,
        left=LEFT_MARGIN,
        top=TOP_MARGIN,
        width=CONTENT_WIDTH,
        height=CONTENT_HEIGHT,
        text=why_now,
        font_size=BODY_SIZE,
    )


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
