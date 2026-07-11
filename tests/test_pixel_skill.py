"""Guard the pixel-art-animator skill's scripts and example against rot."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "pixel-art-animator"
RENDER = SKILL / "scripts" / "render.py"
EXAMPLE = SKILL / "examples" / "courier.json"

sys.path.insert(0, str(SKILL / "scripts"))
import render  # noqa: E402


def test_example_spec_validates():
    spec = render.load_spec(EXAMPLE)
    assert set(spec["animations"]) == {"idle", "walk", "jump", "laugh"}
    # every frame same size
    sizes = set()
    for fname in spec["frames"]:
        rows = render.resolve_frame(spec, fname)
        sizes.add((len(rows[0]), len(rows)))
    assert sizes == {(16, 22)}


def test_flip_h_resolves_to_mirror():
    spec = render.load_spec(EXAMPLE)
    w1 = render.resolve_frame(spec, "walk1")
    w3 = render.resolve_frame(spec, "walk3")
    assert w3 == [row[::-1] for row in w1]


def test_validate_catches_broken_specs():
    assert render.validate_spec({"frames": {}}) == ["no frames defined"]
    bad = {
        "palette": {"a": "#fff"},
        "frames": {"f1": ["aa", "a"]},                      # ragged
        "animations": {"x": {"frames": ["missing"]}},
    }
    problems = "\n".join(render.validate_spec(bad))
    assert "ragged" in problems and "unknown frame" in problems

    unknown_char = {"palette": {"a": "#fff"}, "frames": {"f1": ["ab"]}, "animations": {}}
    assert any("not in palette" in p for p in render.validate_spec(unknown_char))


def test_render_cli_produces_outputs(tmp_path):
    result = subprocess.run(
        [sys.executable, str(RENDER), str(EXAMPLE), "--out", str(tmp_path),
         "--scale", "4", "--anim", "walk", "--export-groups"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "courier_walk_sheet.png").is_file()
    assert (tmp_path / "courier_walk.gif").is_file()
    groups = json.loads((tmp_path / "courier_groups.json").read_text())
    frame0 = groups["animations"]["walk"]["frames"][0]
    # theatre-sprites.js drawSprite shape: [{color, coords: [[x,y],…]}]
    assert all({"color", "coords"} <= set(g) for g in frame0["pixels"])


def test_ground_anchor_rule():
    """Grounded frames keep boots on the bottom row (animation.md rule 0)."""
    spec = render.load_spec(EXAMPLE)
    for fname in ("base", "breathe", "blink", "walk1", "walk2", "jump_crouch"):
        rows = render.resolve_frame(spec, fname)
        assert "x" in rows[-1], f"{fname}: no boot pixels on the ground row"
    for fname in ("jump_apex", "jump_fall"):
        rows = render.resolve_frame(spec, fname)
        assert set(rows[-1]) == {"."}, f"{fname}: should be airborne"


@pytest.mark.parametrize("anim", ["idle", "walk", "jump", "laugh"])
def test_no_dead_frames(anim):
    """Consecutive frames must differ (validate's diff would show 0)."""
    spec = render.load_spec(EXAMPLE)
    seq = spec["animations"][anim]["frames"]
    for a, b in zip(seq, seq[1:]):
        if a == b:  # deliberate holds (e.g. idle base,base) are allowed
            continue
        ra, rb = render.resolve_frame(spec, a), render.resolve_frame(spec, b)
        assert ra != rb, f"{anim}: {a} and {b} are identical"
