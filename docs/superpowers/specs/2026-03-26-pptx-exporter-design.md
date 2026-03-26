# PPTX Exporter Design Spec

**Date:** 2026-03-26
**Status:** Approved
**Purpose:** Convert PitchDeck JSON output into a PowerPoint (.pptx) file

---

## Overview

The pipeline currently outputs a `PitchDeck` as a JSON dict. This feature adds a post-processing step that converts that dict into a real `.pptx` file using `python-pptx`. The output is functional and clean — suitable for an educational tool, not a broadcaster-ready pitch.

## Architecture

A single new module: `src/pptx_exporter.py`

### Public API

```python
def export_pitch_deck(pitch_deck: dict, output_path: str) -> Path:
    """Convert a PitchDeck dict to a .pptx file.

    Args:
        pitch_deck: The PitchDeck dict (same structure as pitch_deck.json).
        output_path: File path for the output .pptx file.

    Returns:
        Path to the written .pptx file.
    """
```

The exporter has no knowledge of the pipeline. It takes a dict and a path. This keeps it testable in isolation.

## Integration Points

### 1. CLI (`src/cli.py`)

After the pipeline writes `pitch_deck.json`, also write `pitch_deck.pptx` to the same output directory.

### 2. Web app (`app.py`)

After pipeline completes, generate the PPTX and provide a download link — either via a `/download` endpoint or by sending a download URL over the existing WebSocket.

## Slide Map

| # | Slide | Source Field | Layout |
|---|-------|-------------|--------|
| 1 | **Title** | `title_page` (title, genre, format, broadcaster) | Title slide layout |
| 2 | **Logline** | `logline` | Section header — one prominent text block |
| 3 | **Format & Tone** | `format_and_tone` (series_length, genre, tone) | Bullet list |
| 4 | **Target Audience** | `target_audience` | Text block |
| 5 | **Competitive Landscape** | `competitive_landscape[]` | Table (title, broadcaster, year, relevance) |
| 6 | **Key Characters** | `key_characters[]` | Table (name, role, access, story angle) |
| 7 | **Episode: Narrative Arc** | `episode_breakdown.narrative_arc` | 4 labelled text blocks (opening, development, climax, resolution) |
| 8 | **Episode: Key Sequences** | `episode_breakdown.key_sequences[]` | Table (name, description, visual style, duration) |
| 9 | **Visual Approach** | `episode_breakdown.overall_tone` + `visual_approach` | Two text blocks |
| 10 | **Feasibility** | `feasibility_summary` | Bullet list (rating, budget range, shooting days, risks) |
| 11 | **Why Now** | `why_now` | Text block |
| 12 | **Review Notes & Concerns** | `sp_review_notes` + `unresolved_concerns[]` | Text block + bullet list |

## Styling

- Use built-in PowerPoint slide layouts (title slide, blank with text boxes)
- Font: Calibri (PowerPoint default), title text 28-32pt, body 14-18pt, table text 10-12pt
- Tables: header row in dark blue with white text, alternating light grey rows
- Auto-size table text to ~10pt minimum to fit long content
- Truncate fields over ~150 chars in table cells with ellipsis
- No images, no custom templates, no external assets

## Dependencies

- `python-pptx>=0.6.21` — added to `requirements.txt`

## Testing

File: `tests/test_pptx_exporter.py`

Tests use the existing `output/test1/pitch_deck.json` as a fixture.

1. **File creation** — verify `.pptx` is written and is a valid PPTX (opens without error via `python-pptx`)
2. **Slide count** — verify 12 slides are generated
3. **Title slide content** — verify title text matches input `title_page.working_title`
4. **Empty/minimal fields** — pass a PitchDeck with empty lists and missing optional data; verify no crashes
5. **Output path** — verify the returned Path matches the requested output path

No mocks needed. `python-pptx` creates real files; tests write to a temp directory.

## Out of Scope

- Custom branded templates
- Image/logo insertion
- Slide animations or transitions
- PDF export
- Editable template system
