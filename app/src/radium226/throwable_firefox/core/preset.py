import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .bookmark import BookmarkItem


class Preset(BaseModel):
    name: str
    default: bool = False
    private: bool | None = None
    marionette: bool | None = None
    bookmarks: list[BookmarkItem] = Field(default_factory=list)


def _presets_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "throwable-firefox" / "presets"


def load_preset_from_path(path: Path) -> Preset:
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Preset file {path} must contain a YAML mapping")
    raw.setdefault("name", path.stem)
    return Preset.model_validate(raw)


def resolve_preset(value: str) -> Preset:
    candidate = Path(value)
    if candidate.is_file():
        return load_preset_from_path(candidate)
    named = _presets_dir() / f"{value}.yaml"
    if named.is_file():
        return load_preset_from_path(named)
    raise FileNotFoundError(f"Preset {value!r} not found (looked at {candidate} and {named})")


def find_default_preset() -> Preset | None:
    directory = _presets_dir()
    if not directory.is_dir():
        return None
    defaults: list[Preset] = []
    for yaml_path in sorted(directory.glob("*.yaml")):
        preset = load_preset_from_path(yaml_path)
        if preset.default:
            defaults.append(preset)
    if len(defaults) > 1:
        names = ", ".join(p.name for p in defaults)
        raise ValueError(f"Multiple default presets found: {names}")
    return defaults[0] if defaults else None
