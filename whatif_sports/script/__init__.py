"""Script models and loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from whatif_sports import config
from whatif_sports.script.schema import Script


def resolve_script_path(ref: str) -> Path:
    """Accept a YAML path or an item id (data/<id>/script.yaml, then examples/<id>.yaml)."""
    p = Path(ref)
    if p.suffix in {".yaml", ".yml"} and p.exists():
        return p
    for candidate in (config.DATA_DIR / ref / "script.yaml", config.EXAMPLES_DIR / f"{ref}.yaml"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No script found for {ref!r}")


def load_script(ref: str | Path) -> Script:
    path = resolve_script_path(str(ref))
    with path.open(encoding="utf-8") as f:
        return Script.model_validate(yaml.safe_load(f))


__all__ = ["Script", "load_script", "resolve_script_path"]
