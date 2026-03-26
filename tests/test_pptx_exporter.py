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
