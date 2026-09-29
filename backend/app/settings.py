"""Local settings. Nothing here is sent off the machine."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .paths import data_root


class Settings(BaseModel):
    theme: str = "graphite"
    font_size: int = Field(default=13, ge=11, le=20)
    tab_size: int = Field(default=4, ge=2, le=8)
    minimap: bool = True
    word_wrap: bool = False
    engineering_mode: str = "professional"
    temperature: float = Field(default=0.2, ge=0, le=2)
    context_size: int = Field(default=8192, ge=1024, le=32768)
    backend_preference: str = "auto"
    allow_cloud: bool = False
    telemetry: bool = False
    crash_reports: bool = False
    icarus_path: str = ""
    verilator_path: str = ""
    yosys_path: str = ""
    autosave: bool = True
    workspace: str = ""


def settings_path() -> Path:
    return data_root() / "settings.json"


def load_settings() -> Settings:
    path = settings_path()
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return Settings()
    return Settings.model_validate(data)


def save_settings(settings: Settings) -> Settings:
    path = settings_path()
    path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    return settings
