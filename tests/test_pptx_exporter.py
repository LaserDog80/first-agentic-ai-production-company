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
