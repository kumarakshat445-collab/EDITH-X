"""Workspace paths and filesystem guards."""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"
MODEL_MANIFEST = REPO_ROOT / "models" / "manifest.json"


def data_root() -> Path:
    raw = os.environ.get("HEXA_DATA")
    root = Path(raw) if raw else REPO_ROOT / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def projects_root() -> Path:
    path = data_root() / "projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


_SLUG = re.compile(r"[^a-z0-9_-]+")


def slugify(name: str) -> str:
    slug = _SLUG.sub("-", name.strip().lower()).strip("-")
    if not slug or slug in {".", ".."}:
        raise ValueError("Project name is empty.")
    return slug[:64]


def safe_project(project_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", project_id or ""):
        raise ValueError("Unknown project.")
    root = projects_root()
    path = (root / project_id).resolve()
    if path.parent != root:
        raise ValueError("Unknown project.")
    return path


def safe_rel(project: Path, relative: str) -> Path:
    if relative is None or relative.strip() == "":
        raise ValueError("Path is required.")
    rel = Path(relative)
    if rel.is_absolute() or any(part in {"..", ""} for part in rel.parts):
        raise ValueError("Path escapes the project workspace.")
    project = project.resolve()
    target = (project / rel).resolve()
    if target != project and project not in target.parents:
        raise ValueError("Path escapes the project workspace.")
    return target
