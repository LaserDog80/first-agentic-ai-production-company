"""Built-in graph presets shipped with the playground."""
import json
from pathlib import Path


_PRESETS_DIR = Path(__file__).parent


def list_presets() -> list[dict]:
    """Return summary metadata for every shipped preset."""
    out: list[dict] = []
    for path in sorted(_PRESETS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        out.append({
            "id": data.get("id", path.stem),
            "name": data.get("name", path.stem),
            "description": data.get("description", ""),
        })
    return out


def load_preset(preset_id: str) -> dict | None:
    """Load a preset by id; returns the parsed JSON or None if not found."""
    safe = "".join(c for c in preset_id if c.isalnum() or c in ("_", "-"))
    if not safe:
        return None
    path = _PRESETS_DIR / f"{safe}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
