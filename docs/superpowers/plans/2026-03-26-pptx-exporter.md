# PPTX Exporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert PitchDeck JSON output into a PowerPoint (.pptx) file with 12 structured slides.

**Architecture:** A single module `src/pptx_exporter.py` with one public function `export_pitch_deck(pitch_deck, output_path)`. It consumes the existing PitchDeck dict and produces a .pptx file. Integration into CLI (`src/main.py`) and web app (`app.py`) as a post-processing step.

**Tech Stack:** python-pptx, pydantic (existing), pytest (existing)

**Spec:** `docs/superpowers/specs/2026-03-26-pptx-exporter-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/pptx_exporter.py` | Create | All PPTX generation logic |
| `tests/test_pptx_exporter.py` | Create | Unit tests for the exporter |
| `requirements.txt` | Modify | Add python-pptx dependency |
| `src/main.py` | Modify | Call exporter after pipeline completes |
| `app.py` | Modify | Add download endpoint + trigger export |

---

### Task 1: Add dependency and write core exporter with title slide

**Files:**
- Modify: `requirements.txt:9` (add python-pptx)
- Create: `src/pptx_exporter.py`
- Create: `tests/test_pptx_exporter.py`

- [ ] **Step 1: Add python-pptx to requirements.txt**

Add to the end of `requirements.txt`:
```
python-pptx>=0.6.21
```

- [ ] **Step 2: Install the new dependency**

Run: `pip install python-pptx>=0.6.21`

- [ ] **Step 3: Write the failing test for title slide**

Create `tests/test_pptx_exporter.py`:

```python
"""Tests for the PPTX exporter."""
import json
from pathlib import Path

import pytest
from pptx import Presentation

from src.pptx_exporter import export_pitch_deck


@pytest.fixture
def sample_pitch_deck() -> dict:
    """Load the test fixture pitch deck."""
    fixture = Path("output/test1/pitch_deck.json")
    return json.loads(fixture.read_text())


def test_export_creates_file(sample_pitch_deck, tmp_path):
    """Exporter creates a valid .pptx file."""
    output = tmp_path / "deck.pptx"
    result = export_pitch_deck(sample_pitch_deck, str(output))
    assert result == output
    assert output.exists()
    # Verify it's a valid PPTX by opening it
    prs = Presentation(str(output))
    assert len(prs.slides) > 0


def test_title_slide_content(sample_pitch_deck, tmp_path):
    """Title slide contains the working title."""
    output = tmp_path / "deck.pptx"
    export_pitch_deck(sample_pitch_deck, str(output))
    prs = Presentation(str(output))
    first_slide = prs.slides[0]
    texts = [shape.text for shape in first_slide.shapes if shape.has_text_frame]
    all_text = " ".join(texts)
    assert sample_pitch_deck["title_page"]["working_title"] in all_text
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_pptx_exporter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.pptx_exporter'`

- [ ] **Step 5: Write the core exporter with title slide**

Create `src/pptx_exporter.py`:

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_pptx_exporter.py -v`
Expected: 2 PASS

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src/pptx_exporter.py tests/test_pptx_exporter.py
git commit -m "feat: add PPTX exporter with title slide generation"
```

---

### Task 2: Add text-based slides (logline, format, audience, why now)

**Files:**
- Modify: `src/pptx_exporter.py`
- Modify: `tests/test_pptx_exporter.py`

- [ ] **Step 1: Write the failing test for slide count with text slides**

Add to `tests/test_pptx_exporter.py`:

```python
def test_text_slides_present(sample_pitch_deck, tmp_path):
    """Slides 2-4 and 11 contain logline, format, audience, and why_now text."""
    output = tmp_path / "deck.pptx"
    export_pitch_deck(sample_pitch_deck, str(output))
    prs = Presentation(str(output))

    def slide_text(index):
        return " ".join(
            shape.text for shape in prs.slides[index].shapes if shape.has_text_frame
        )

    # Slide 2: logline
    assert sample_pitch_deck["logline"][:50] in slide_text(1)
    # Slide 3: format_and_tone
    assert sample_pitch_deck["format_and_tone"]["genre"] in slide_text(2)
    # Slide 4: target_audience
    assert sample_pitch_deck["target_audience"][:50] in slide_text(3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pptx_exporter.py::test_text_slides_present -v`
Expected: FAIL with `IndexError` (only 1 slide exists)

- [ ] **Step 3: Add slide heading helper and text slides to exporter**

Add to `src/pptx_exporter.py`:

```python
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
```

Update `export_pitch_deck` to call these after the title slide:

```python
def export_pitch_deck(pitch_deck: dict, output_path: str) -> Path:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pptx_exporter.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/pptx_exporter.py tests/test_pptx_exporter.py
git commit -m "feat: add logline, format, and audience slides"
```

---

### Task 3: Add table-based slides (competitors, characters)

**Files:**
- Modify: `src/pptx_exporter.py`
- Modify: `tests/test_pptx_exporter.py`

- [ ] **Step 1: Write the failing test for table slides**

Add to `tests/test_pptx_exporter.py`:

```python
def test_competitor_table_slide(sample_pitch_deck, tmp_path):
    """Slide 5 contains a table with competitor data."""
    output = tmp_path / "deck.pptx"
    export_pitch_deck(sample_pitch_deck, str(output))
    prs = Presentation(str(output))
    slide = prs.slides[4]  # 0-indexed, slide 5
    tables = [s for s in slide.shapes if s.has_table]
    assert len(tables) == 1
    table = tables[0].table
    # Header row + data rows
    expected_rows = 1 + len(sample_pitch_deck["competitive_landscape"])
    assert len(table.rows) == expected_rows
    # 4 columns: title, broadcaster, year, relevance
    assert len(table.columns) == 4


def test_characters_table_slide(sample_pitch_deck, tmp_path):
    """Slide 6 contains a table with character data."""
    output = tmp_path / "deck.pptx"
    export_pitch_deck(sample_pitch_deck, str(output))
    prs = Presentation(str(output))
    slide = prs.slides[5]  # 0-indexed, slide 6
    tables = [s for s in slide.shapes if s.has_table]
    assert len(tables) == 1
    table = tables[0].table
    expected_rows = 1 + len(sample_pitch_deck["key_characters"])
    assert len(table.rows) == expected_rows
    assert len(table.columns) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pptx_exporter.py::test_competitor_table_slide tests/test_pptx_exporter.py::test_characters_table_slide -v`
Expected: FAIL with `IndexError`

- [ ] **Step 3: Add table helper and table slides**

Add to `src/pptx_exporter.py`:

```python
def _truncate(text: str, max_chars: int = MAX_CELL_CHARS) -> str:
    """Truncate text with ellipsis if over max length."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


def _add_table_slide(
    prs: Presentation,
    heading: str,
    headers: list[str],
    rows: list[list[str]],
) -> None:
    """Add a slide with a heading and a styled table."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_slide_heading(slide, heading)

    num_rows = len(rows) + 1  # +1 for header
    num_cols = len(headers)
    table_shape = slide.shapes.add_table(
        num_rows, num_cols,
        LEFT_MARGIN, TOP_MARGIN, CONTENT_WIDTH, CONTENT_HEIGHT,
    )
    table = table_shape.table

    # Header row
    for col_idx, header_text in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.text = header_text
        for paragraph in cell.text_frame.paragraphs:
            paragraph.font.size = TABLE_SIZE
            paragraph.font.bold = True
            paragraph.font.color.rgb = WHITE
        cell.fill.solid()
        cell.fill.fore_color.rgb = DARK_BLUE

    # Data rows
    for row_idx, row_data in enumerate(rows):
        for col_idx, cell_text in enumerate(row_data):
            cell = table.cell(row_idx + 1, col_idx)
            cell.text = _truncate(cell_text)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.size = TABLE_SIZE
                paragraph.font.color.rgb = BLACK
            # Alternating row color
            if row_idx % 2 == 1:
                cell.fill.solid()
                cell.fill.fore_color.rgb = LIGHT_GREY


def _add_competitors_slide(prs: Presentation, competitors: list[dict]) -> None:
    """Slide 5: Competitive Landscape — table."""
    rows = [
        [
            c.get("title", ""),
            c.get("broadcaster", ""),
            c.get("year", ""),
            c.get("relevance", ""),
        ]
        for c in competitors
    ]
    _add_table_slide(
        prs, "Competitive Landscape",
        ["Title", "Broadcaster", "Year", "Relevance"],
        rows,
    )


def _add_characters_slide(prs: Presentation, characters: list[dict]) -> None:
    """Slide 6: Key Characters — table."""
    rows = [
        [
            c.get("name", ""),
            c.get("role", ""),
            c.get("access_notes", ""),
            c.get("story_angle", ""),
        ]
        for c in characters
    ]
    _add_table_slide(
        prs, "Key Characters",
        ["Name", "Role", "Access", "Story Angle"],
        rows,
    )
```

Update `export_pitch_deck` to call these after slide 4:

```python
    _add_audience_slide(prs, pitch_deck.get("target_audience", ""))
    _add_competitors_slide(prs, pitch_deck.get("competitive_landscape", []))
    _add_characters_slide(prs, pitch_deck.get("key_characters", []))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pptx_exporter.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/pptx_exporter.py tests/test_pptx_exporter.py
git commit -m "feat: add competitor and character table slides"
```

---

### Task 4: Add episode breakdown slides (narrative arc, sequences, visual approach)

**Files:**
- Modify: `src/pptx_exporter.py`
- Modify: `tests/test_pptx_exporter.py`

- [ ] **Step 1: Write the failing test for episode slides**

Add to `tests/test_pptx_exporter.py`:

```python
def test_narrative_arc_slide(sample_pitch_deck, tmp_path):
    """Slide 7 contains narrative arc sections."""
    output = tmp_path / "deck.pptx"
    export_pitch_deck(sample_pitch_deck, str(output))
    prs = Presentation(str(output))
    slide = prs.slides[6]
    slide_text = " ".join(
        shape.text for shape in slide.shapes if shape.has_text_frame
    )
    arc = sample_pitch_deck["episode_breakdown"]["narrative_arc"]
    # Check that at least the opening is present
    assert arc["opening"][:40] in slide_text


def test_sequences_table_slide(sample_pitch_deck, tmp_path):
    """Slide 8 contains a table of key sequences."""
    output = tmp_path / "deck.pptx"
    export_pitch_deck(sample_pitch_deck, str(output))
    prs = Presentation(str(output))
    slide = prs.slides[7]
    tables = [s for s in slide.shapes if s.has_table]
    assert len(tables) == 1
    table = tables[0].table
    sequences = sample_pitch_deck["episode_breakdown"]["key_sequences"]
    assert len(table.rows) == 1 + len(sequences)
    assert len(table.columns) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pptx_exporter.py::test_narrative_arc_slide tests/test_pptx_exporter.py::test_sequences_table_slide -v`
Expected: FAIL with `IndexError`

- [ ] **Step 3: Add episode breakdown slides**

Add to `src/pptx_exporter.py`:

```python
def _add_narrative_arc_slide(prs: Presentation, episode: dict) -> None:
    """Slide 7: Narrative Arc — four labelled text blocks."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ep_title = episode.get("episode_title", "Episode Breakdown")
    _add_slide_heading(slide, f"Narrative Arc: {ep_title}")

    arc = episode.get("narrative_arc", {})
    sections = [
        ("Opening", arc.get("opening", "")),
        ("Development", arc.get("development", "")),
        ("Climax", arc.get("climax", "")),
        ("Resolution", arc.get("resolution", "")),
    ]

    txbox = slide.shapes.add_textbox(
        LEFT_MARGIN, TOP_MARGIN, CONTENT_WIDTH, CONTENT_HEIGHT
    )
    tf = txbox.text_frame
    tf.word_wrap = True

    for i, (label, content) in enumerate(sections):
        # Label paragraph (bold)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = label
        p.font.size = SMALL_SIZE
        p.font.bold = True
        p.font.color.rgb = DARK_BLUE
        p.space_before = Pt(8) if i > 0 else Pt(0)

        # Content paragraph
        p2 = tf.add_paragraph()
        p2.text = _truncate(content, 300)
        p2.font.size = SMALL_SIZE
        p2.font.color.rgb = DARK_GREY
        p2.space_after = Pt(6)


def _add_sequences_slide(prs: Presentation, sequences: list[dict]) -> None:
    """Slide 8: Key Sequences — table."""
    rows = [
        [
            s.get("name", ""),
            s.get("description", ""),
            s.get("visual_style", ""),
            str(s.get("duration_mins", "")),
        ]
        for s in sequences
    ]
    _add_table_slide(
        prs, "Key Sequences",
        ["Name", "Description", "Visual Style", "Duration (min)"],
        rows,
    )


def _add_visual_approach_slide(prs: Presentation, episode: dict) -> None:
    """Slide 9: Visual Approach — tone + visual approach text."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_slide_heading(slide, "Visual Approach")

    tone = episode.get("overall_tone", "")
    approach = episode.get("visual_approach", "")

    txbox = slide.shapes.add_textbox(
        LEFT_MARGIN, TOP_MARGIN, CONTENT_WIDTH, CONTENT_HEIGHT
    )
    tf = txbox.text_frame
    tf.word_wrap = True

    # Tone
    p = tf.paragraphs[0]
    p.text = "Overall Tone"
    p.font.size = BODY_SIZE
    p.font.bold = True
    p.font.color.rgb = DARK_BLUE

    p2 = tf.add_paragraph()
    p2.text = tone
    p2.font.size = BODY_SIZE
    p2.font.color.rgb = DARK_GREY
    p2.space_after = Pt(18)

    # Visual approach
    p3 = tf.add_paragraph()
    p3.text = "Visual Approach"
    p3.font.size = BODY_SIZE
    p3.font.bold = True
    p3.font.color.rgb = DARK_BLUE

    p4 = tf.add_paragraph()
    p4.text = approach
    p4.font.size = BODY_SIZE
    p4.font.color.rgb = DARK_GREY
```

Update `export_pitch_deck` to call these:

```python
    _add_characters_slide(prs, pitch_deck.get("key_characters", []))
    episode = pitch_deck.get("episode_breakdown", {})
    _add_narrative_arc_slide(prs, episode)
    _add_sequences_slide(prs, episode.get("key_sequences", []))
    _add_visual_approach_slide(prs, episode)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pptx_exporter.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/pptx_exporter.py tests/test_pptx_exporter.py
git commit -m "feat: add narrative arc, sequences, and visual approach slides"
```

---

### Task 5: Add feasibility and closing slides

**Files:**
- Modify: `src/pptx_exporter.py`
- Modify: `tests/test_pptx_exporter.py`

- [ ] **Step 1: Write the failing test for full slide count**

Add to `tests/test_pptx_exporter.py`:

```python
def test_full_slide_count(sample_pitch_deck, tmp_path):
    """Complete export produces exactly 12 slides."""
    output = tmp_path / "deck.pptx"
    export_pitch_deck(sample_pitch_deck, str(output))
    prs = Presentation(str(output))
    assert len(prs.slides) == 12


def test_feasibility_slide(sample_pitch_deck, tmp_path):
    """Slide 10 contains feasibility rating."""
    output = tmp_path / "deck.pptx"
    export_pitch_deck(sample_pitch_deck, str(output))
    prs = Presentation(str(output))
    slide = prs.slides[9]
    slide_text = " ".join(
        shape.text for shape in slide.shapes if shape.has_text_frame
    )
    rating = sample_pitch_deck["feasibility_summary"]["feasibility_rating"]
    assert rating.upper() in slide_text.upper()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pptx_exporter.py::test_full_slide_count tests/test_pptx_exporter.py::test_feasibility_slide -v`
Expected: FAIL

- [ ] **Step 3: Add feasibility, why now, and review slides**

Add to `src/pptx_exporter.py`:

```python
def _add_feasibility_slide(prs: Presentation, feasibility: dict) -> None:
    """Slide 10: Feasibility — rating, budget, days, risks."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_slide_heading(slide, "Feasibility")

    rating = feasibility.get("feasibility_rating", "N/A").upper()
    budget = feasibility.get("budget_bracket", {})
    low = budget.get("low", "?")
    high = budget.get("high", "?")
    currency = budget.get("currency", "")
    days = feasibility.get("shooting_days", "N/A")
    risks = feasibility.get("key_risks", [])

    txbox = slide.shapes.add_textbox(
        LEFT_MARGIN, TOP_MARGIN, CONTENT_WIDTH, CONTENT_HEIGHT
    )
    tf = txbox.text_frame
    tf.word_wrap = True

    items = [
        f"Rating: {rating}",
        f"Budget: {currency} {low:,} - {high:,}" if isinstance(low, int) else f"Budget: {currency} {low} - {high}",
        f"Shooting Days: {days}",
    ]
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = item
        p.font.size = BODY_SIZE
        p.font.bold = True
        p.font.color.rgb = DARK_GREY
        p.space_after = Pt(8)

    # Risks
    if risks:
        p_label = tf.add_paragraph()
        p_label.text = "Key Risks:"
        p_label.font.size = BODY_SIZE
        p_label.font.bold = True
        p_label.font.color.rgb = DARK_BLUE
        p_label.space_before = Pt(12)

        for risk in risks:
            p_risk = tf.add_paragraph()
            p_risk.text = f"  \u2022  {_truncate(risk)}"
            p_risk.font.size = SMALL_SIZE
            p_risk.font.color.rgb = DARK_GREY


def _add_review_slide(
    prs: Presentation, review_notes: str, concerns: list[str]
) -> None:
    """Slide 12: SP Review Notes & Unresolved Concerns."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_slide_heading(slide, "Review Notes & Concerns")

    txbox = slide.shapes.add_textbox(
        LEFT_MARGIN, TOP_MARGIN, CONTENT_WIDTH, CONTENT_HEIGHT
    )
    tf = txbox.text_frame
    tf.word_wrap = True

    # Review notes
    p = tf.paragraphs[0]
    p.text = review_notes
    p.font.size = SMALL_SIZE
    p.font.color.rgb = DARK_GREY
    p.space_after = Pt(14)

    # Concerns
    if concerns:
        p_label = tf.add_paragraph()
        p_label.text = "Unresolved Concerns:"
        p_label.font.size = BODY_SIZE
        p_label.font.bold = True
        p_label.font.color.rgb = DARK_BLUE
        p_label.space_before = Pt(12)

        for concern in concerns:
            p_c = tf.add_paragraph()
            p_c.text = f"  \u2022  {_truncate(concern)}"
            p_c.font.size = SMALL_SIZE
            p_c.font.color.rgb = DARK_GREY
```

Update `export_pitch_deck` to the final version with all 12 slides:

```python
def export_pitch_deck(pitch_deck: dict, output_path: str) -> Path:
    path = Path(output_path)
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    # Slide 1: Title
    _add_title_slide(prs, pitch_deck.get("title_page", {}))
    # Slide 2: Logline
    _add_logline_slide(prs, pitch_deck.get("logline", ""))
    # Slide 3: Format & Tone
    _add_format_slide(prs, pitch_deck.get("format_and_tone", {}))
    # Slide 4: Target Audience
    _add_audience_slide(prs, pitch_deck.get("target_audience", ""))
    # Slide 5: Competitive Landscape
    _add_competitors_slide(prs, pitch_deck.get("competitive_landscape", []))
    # Slide 6: Key Characters
    _add_characters_slide(prs, pitch_deck.get("key_characters", []))
    # Slides 7-9: Episode breakdown
    episode = pitch_deck.get("episode_breakdown", {})
    _add_narrative_arc_slide(prs, episode)
    _add_sequences_slide(prs, episode.get("key_sequences", []))
    _add_visual_approach_slide(prs, episode)
    # Slide 10: Feasibility
    _add_feasibility_slide(prs, pitch_deck.get("feasibility_summary", {}))
    # Slide 11: Why Now
    _add_why_now_slide(prs, pitch_deck.get("why_now", ""))
    # Slide 12: Review Notes & Concerns
    _add_review_slide(
        prs,
        pitch_deck.get("sp_review_notes", ""),
        pitch_deck.get("unresolved_concerns", []),
    )

    prs.save(str(path))
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pptx_exporter.py -v`
Expected: 9 PASS

- [ ] **Step 5: Commit**

```bash
git add src/pptx_exporter.py tests/test_pptx_exporter.py
git commit -m "feat: add feasibility, why now, and review slides — complete 12-slide deck"
```

---

### Task 6: Add empty/minimal data safety test

**Files:**
- Modify: `tests/test_pptx_exporter.py`

- [ ] **Step 1: Write the test for minimal data**

Add to `tests/test_pptx_exporter.py`:

```python
def test_minimal_pitch_deck_no_crash(tmp_path):
    """Exporter handles a near-empty PitchDeck dict without crashing."""
    minimal = {
        "title_page": {"working_title": "Test"},
        "logline": "",
        "format_and_tone": {},
        "target_audience": "",
        "competitive_landscape": [],
        "key_characters": [],
        "episode_breakdown": {
            "narrative_arc": {},
            "key_sequences": [],
        },
        "feasibility_summary": {},
        "why_now": "",
        "sp_review_notes": "",
        "unresolved_concerns": [],
    }
    output = tmp_path / "minimal.pptx"
    result = export_pitch_deck(minimal, str(output))
    assert result == output
    prs = Presentation(str(output))
    assert len(prs.slides) == 12
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_pptx_exporter.py::test_minimal_pitch_deck_no_crash -v`
Expected: PASS (if it fails, fix the exporter to handle missing keys gracefully)

- [ ] **Step 3: Commit**

```bash
git add tests/test_pptx_exporter.py
git commit -m "test: add minimal data safety test for PPTX exporter"
```

---

### Task 7: Integrate into CLI

**Files:**
- Modify: `src/main.py:38-57`

- [ ] **Step 1: Write the failing test for CLI PPTX output**

Add to `tests/test_pptx_exporter.py`:

```python
def test_cli_integration_writes_pptx(sample_pitch_deck, tmp_path):
    """Verify export_pitch_deck works with a real output directory path."""
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    pptx_path = out_dir / "pitch_deck.pptx"
    result = export_pitch_deck(sample_pitch_deck, str(pptx_path))
    assert result == pptx_path
    assert pptx_path.exists()
    assert pptx_path.stat().st_size > 0
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_pptx_exporter.py::test_cli_integration_writes_pptx -v`
Expected: PASS

- [ ] **Step 3: Add PPTX export to CLI**

In `src/main.py`, add import at top:

```python
from src.pptx_exporter import export_pitch_deck
```

After line 46 (`(out_dir / "evidence.json").write_text(...)`), add:

```python
            # Generate PPTX
            if result.pitch_deck:
                pptx_path = export_pitch_deck(
                    result.pitch_deck, str(out_dir / "pitch_deck.pptx")
                )
                print(f"PowerPoint saved to {pptx_path}")
```

- [ ] **Step 4: Run all tests**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_pptx_exporter.py
git commit -m "feat: integrate PPTX export into CLI"
```

---

### Task 8: Integrate into web app

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Write the failing test for download endpoint**

Add to `tests/test_app.py` (or create if needed — check existing file first):

```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app


def test_download_returns_404_when_no_file():
    """Download endpoint returns 404 when no PPTX exists."""
    client = TestClient(app)
    response = client.get("/download/nonexistent-run")
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app.py::test_download_returns_404_when_no_file -v`
Expected: FAIL with 404 (route not found returns different error) or similar

- [ ] **Step 3: Add download endpoint and PPTX generation to app.py**

Add import at top of `app.py`:

```python
from fastapi.responses import FileResponse, JSONResponse
from src.pptx_exporter import export_pitch_deck
```

Add a module-level dict to track generated files and a download endpoint:

```python
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
```

In the `_run_pipeline` function, after `pipeline_complete` event, add PPTX generation:

```python
        if result.success:
            # Generate PPTX
            run_id = str(hash(brief))[:12]
            pptx_dir = Path("output/web")
            pptx_dir.mkdir(parents=True, exist_ok=True)
            pptx_path = pptx_dir / f"{run_id}.pptx"
            if result.pitch_deck:
                export_pitch_deck(result.pitch_deck, str(pptx_path))
                _generated_files[run_id] = pptx_path

            await emit({
                "type": "pipeline_complete",
                "pitch_deck": result.pitch_deck,
                "evidence": result.evidence,
                "download_url": f"/download/{run_id}" if result.pitch_deck else None,
            })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add PPTX download endpoint to web app"
```

---

### Task 9: Final verification and cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 2: Test with real fixture data manually**

Run:
```bash
python -c "
import json
from src.pptx_exporter import export_pitch_deck
deck = json.loads(open('output/test1/pitch_deck.json').read())
export_pitch_deck(deck, 'output/test1/pitch_deck.pptx')
print('Generated output/test1/pitch_deck.pptx')
"
```

Open `output/test1/pitch_deck.pptx` in PowerPoint/Keynote/LibreOffice to visually verify.

- [ ] **Step 3: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: final cleanup for PPTX exporter"
```
