"""Project files stay under the workspace directory."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .paths import TEMPLATE_ROOT, projects_root, safe_project, safe_rel, slugify

IGNORE = {".hexa", "__pycache__"}


def seed() -> None:
    root = projects_root()
    dest = root / "uart"
    if dest.exists():
        return
    _copy_template("uart", dest)


def list_projects() -> list[dict]:
    seed()
    items = []
    for path in sorted(projects_root().iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        meta = _read_meta(path)
        counts = _counts(path)
        items.append({"id": path.name, **meta, **counts})
    return items


def create_project(name: str, template: str) -> dict:
    project_id = slugify(name)
    dest = projects_root() / project_id
    if dest.exists():
        raise FileExistsError(f"Project {project_id} already exists.")
    if template == "empty":
        dest.mkdir(parents=True)
        for folder in ("rtl", "tb", "tests", "reports"):
            (dest / folder).mkdir()
        meta = {"name": name.strip() or project_id, "template": "empty", "description": "Empty RTL workspace."}
        _write_meta(dest, meta)
    elif template in {"uart", "counter"}:
        _copy_template(template, dest)
        meta = _read_meta(dest)
        if name.strip() and template == "counter":
            meta["name"] = name.strip()
            _write_meta(dest, meta)
    else:
        raise ValueError("Unknown template.")
    return {"id": project_id, **_read_meta(dest), **_counts(dest)}


def restore_demo(project_id: str) -> dict:
    project = safe_project(project_id)
    if not project.is_dir():
        raise FileNotFoundError("Project was not found.")
    meta = _read_meta(project)
    template = meta.get("template")
    if template not in {"uart", "counter"}:
        raise ValueError("This project has no demo source to restore.")
    for folder in ("rtl", "tb"):
        target = project / folder
        if target.exists():
            shutil.rmtree(target)
    source = TEMPLATE_ROOT / template
    for folder in ("rtl", "tb"):
        src = source / folder
        if src.exists():
            shutil.copytree(src, project / folder)
    hexa = project / ".hexa"
    if hexa.exists():
        shutil.rmtree(hexa)
    reports = project / "reports"
    for name in ("verification.json", "verification.md"):
        stale = reports / name
        if stale.is_file():
            stale.unlink()
    return {"id": project_id, "restored": template}


def tree(project_id: str) -> dict:
    project = _require(project_id)
    return {"id": project_id, "name": _read_meta(project)["name"], "tree": _walk(project, project)}


def read_file(project_id: str, relative: str) -> dict:
    project = _require(project_id)
    path = safe_rel(project, relative)
    if not path.is_file():
        raise FileNotFoundError("File was not found.")
    return {"path": relative, "content": path.read_text(encoding="utf-8")}


def write_file(project_id: str, relative: str, content: str) -> dict:
    project = _require(project_id)
    path = safe_rel(project, relative)
    if path.suffix.lower() not in {".sv", ".v", ".vh", ".md", ".json", ".txt", ".svh"}:
        raise ValueError("Only RTL, testbench, markdown, and text files can be written.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": relative, "bytes": len(content.encode("utf-8"))}


def delete_file(project_id: str, relative: str) -> dict:
    project = _require(project_id)
    path = safe_rel(project, relative)
    if path.is_dir():
        raise ValueError("Refusing to delete a directory.")
    if not path.is_file():
        raise FileNotFoundError("File was not found.")
    path.unlink()
    return {"path": relative, "deleted": True}


def design_sources(project: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE or part.startswith(".") for part in path.relative_to(project).parts):
            continue
        if path.suffix.lower() not in {".sv", ".v", ".vh"}:
            continue
        files[path.relative_to(project).as_posix()] = path.read_text(encoding="utf-8")
    return files


def _require(project_id: str) -> Path:
    seed()
    project = safe_project(project_id)
    if not project.is_dir():
        raise FileNotFoundError("Project was not found.")
    return project


def _copy_template(template: str, dest: Path) -> None:
    source = TEMPLATE_ROOT / template
    if not source.is_dir():
        raise FileNotFoundError(f"Template {template} is missing.")
    shutil.copytree(source, dest)


def _read_meta(project: Path) -> dict:
    path = project / "project.json"
    if not path.is_file():
        return {"name": project.name, "template": "empty", "description": ""}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_meta(project: Path, meta: dict) -> None:
    (project / "project.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def _counts(project: Path) -> dict:
    rtl = tb = 0
    for path in project.rglob("*"):
        if not path.is_file() or any(part.startswith(".") for part in path.parts):
            continue
        rel = path.relative_to(project).as_posix()
        if path.suffix.lower() not in {".sv", ".v"}:
            continue
        if rel.startswith("tb/") or path.name.endswith("_tb.sv"):
            tb += 1
        elif rel.startswith("rtl/"):
            rtl += 1
    report = _last_report(project)
    return {
        "rtl_files": rtl,
        "testbenches": tb,
        "tests": report.get("tests"),
        "passing": report.get("passed"),
        "failing": report.get("failed"),
        "synthesizability": report.get("synthesizability"),
        "simulation": report.get("simulation"),
        "updated": report.get("generated_at"),
    }


def _last_report(project: Path) -> dict:
    path = project / "reports" / "verification.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _walk(root: Path, project: Path) -> list[dict]:
    nodes = []
    for path in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if path.name.startswith(".") or path.name in IGNORE:
            continue
        rel = path.relative_to(project).as_posix()
        if path.is_dir():
            nodes.append({"type": "dir", "name": path.name, "path": rel, "children": _walk(path, project)})
        else:
            if path.suffix.lower() in {".vvp", ".vcd", ".out"}:
                continue
            nodes.append({"type": "file", "name": path.name, "path": rel})
    return nodes
