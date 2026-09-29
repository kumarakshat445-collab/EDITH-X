"""HEXA-R local API. RTL does not leave the process."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .copilot import answer, explain_change
from .generate import generate_rtl, generate_testbench
from .inference import engine_status, model_rows, timed
from .paths import REPO_ROOT
from .pipeline import (
    analyze_project,
    compile_project,
    ensure_testbench,
    read_report,
    simulate_project,
    synth_project,
    verify_project,
    waveform,
)
from .projects import (
    create_project,
    delete_file,
    design_sources,
    list_projects,
    read_file,
    restore_demo,
    seed,
    tree,
    write_file,
)
from .settings import Settings, load_settings, save_settings
from .tools import ToolError, run_user_command, tool_status

app = FastAPI(title="HEXA-R", version=__version__, description="On-device RTL copilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    template: str = "empty"


class FileWrite(BaseModel):
    path: str
    content: str


class Focus(BaseModel):
    path: str | None = None


class Prompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    mode: str = "professional"


class CopilotRequest(BaseModel):
    project: str
    message: str = Field(min_length=1, max_length=4000)
    file: str | None = None
    selection: str | None = None
    mode: str = "professional"


class ApplyRequest(BaseModel):
    path: str
    content: str


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=500)


class ExplainDiff(BaseModel):
    diff: str = Field(max_length=20000)
    mode: str = "professional"


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, FileExistsError):
        return HTTPException(409, str(exc))
    if isinstance(exc, (ValueError, ToolError)):
        return HTTPException(400, str(exc))
    return HTTPException(500, str(exc))


@app.on_event("startup")
def _startup() -> None:
    seed()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "hexa-r", "version": __version__}


@app.get("/api/engine")
def engine() -> dict:
    return engine_status(load_settings()).as_dict()


@app.get("/api/models")
def models() -> dict:
    return {"models": model_rows(), "engine": engine_status(load_settings()).as_dict()}


@app.get("/api/tools")
def tools() -> dict:
    return tool_status(load_settings())


@app.get("/api/settings")
def get_settings() -> dict:
    return load_settings().model_dump()


@app.put("/api/settings")
def put_settings(payload: Settings) -> dict:
    if payload.engineering_mode not in {"beginner", "student", "professional"}:
        raise HTTPException(400, "Engineering mode must be beginner, student, or professional.")
    if payload.backend_preference not in {"auto", "rules", "onnx", "qnn"}:
        raise HTTPException(400, "Unknown backend preference.")
    if payload.theme not in {"graphite", "contrast"}:
        raise HTTPException(400, "Unknown theme.")
    return save_settings(payload).model_dump()


@app.get("/api/projects")
def projects() -> dict:
    return {"projects": list_projects()}


@app.post("/api/projects")
def post_project(body: ProjectCreate) -> dict:
    try:
        return create_project(body.name, body.template)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.get("/api/projects/{project_id}")
def project_tree(project_id: str) -> dict:
    try:
        return tree(project_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/restore")
def post_restore(project_id: str) -> dict:
    try:
        return restore_demo(project_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.get("/api/projects/{project_id}/file")
def get_file(project_id: str, path: str) -> dict:
    try:
        return read_file(project_id, path)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.put("/api/projects/{project_id}/file")
def put_file(project_id: str, body: FileWrite) -> dict:
    try:
        return write_file(project_id, body.path, body.content)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.delete("/api/projects/{project_id}/file")
def remove_file(project_id: str, path: str) -> dict:
    try:
        return delete_file(project_id, path)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/analyze")
def post_analyze(project_id: str, body: Focus | None = None) -> dict:
    try:
        return analyze_project(project_id, load_settings(), body.path if body else None)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/generate/rtl")
def post_rtl(project_id: str, body: Prompt) -> dict:
    del project_id
    with timed():
        return generate_rtl(body.prompt).as_dict()


@app.post("/api/projects/{project_id}/generate/testbench")
def post_tb(project_id: str, body: Focus) -> dict:
    try:
        files = design_sources_for(project_id)
        with timed():
            generated = generate_testbench(files, body.path)
        return generated.as_dict()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/testbench/write")
def post_tb_write(project_id: str, body: Focus) -> dict:
    try:
        with timed():
            return ensure_testbench(project_id, body.path)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/compile")
def post_compile(project_id: str) -> dict:
    try:
        return compile_project(project_id, load_settings())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/simulate")
def post_sim(project_id: str) -> dict:
    try:
        return simulate_project(project_id, load_settings())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/synth")
def post_synth(project_id: str) -> dict:
    try:
        return synth_project(project_id, load_settings())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/verify")
def post_verify(project_id: str) -> dict:
    try:
        settings = load_settings()
        with timed():
            return verify_project(project_id, settings, settings.engineering_mode)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/debug")
def post_debug(project_id: str) -> dict:
    try:
        from .debug import propose as propose_fix
        from .pipeline import load_sim_log

        files = design_sources_for(project_id)
        with timed():
            return propose_fix(files, load_sim_log(project_id), load_settings().engineering_mode).as_dict()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/apply")
def post_apply(project_id: str, body: ApplyRequest) -> dict:
    try:
        current = read_file(project_id, body.path)
        backup = safe_backup(project_id, body.path, current["content"])
        written = write_file(project_id, body.path, body.content)
        written["backup"] = backup
        return written
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.get("/api/projects/{project_id}/waveform")
def get_wave(project_id: str) -> dict:
    try:
        return waveform(project_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.get("/api/projects/{project_id}/report")
def get_report(project_id: str) -> dict:
    try:
        return read_report(project_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/projects/{project_id}/command")
def post_command(project_id: str, body: CommandRequest) -> dict:
    try:
        from .paths import safe_project

        return run_user_command(body.command, safe_project(project_id), load_settings())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@app.post("/api/copilot")
def copilot(body: CopilotRequest) -> StreamingResponse:
    settings = load_settings()

    def chunks():
        try:
            with timed():
                result = answer(body.project, body.message, body.file, body.selection, body.mode or settings.engineering_mode, settings)
        except Exception as exc:  # noqa: BLE001
            payload = {"type": "error", "detail": str(exc)}
            yield f"data: {json.dumps(payload)}\n\n"
            return
        text = result["text"]
        step = 80
        for index in range(0, len(text), step):
            yield f"data: {json.dumps({'type': 'chunk', 'text': text[index:index + step]})}\n\n"
        yield f"data: {json.dumps({'type': 'done', **result})}\n\n"

    return StreamingResponse(chunks(), media_type="text/event-stream")


@app.post("/api/explain-diff")
def post_explain(body: ExplainDiff) -> dict:
    with timed():
        return {"backend": "rule-engine", "text": explain_change(body.diff, body.mode)}


def design_sources_for(project_id: str) -> dict[str, str]:
    from .paths import safe_project

    project = safe_project(project_id)
    if not project.is_dir():
        raise FileNotFoundError("Project was not found.")
    return design_sources(project)


def safe_backup(project_id: str, relative: str, content: str) -> str:
    from .paths import safe_project, safe_rel

    project = safe_project(project_id)
    target = safe_rel(project, relative)
    backup_dir = project / ".hexa" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    name = target.name + ".bak"
    path = backup_dir / name
    path.write_text(content, encoding="utf-8")
    return path.relative_to(project).as_posix()


dist = REPO_ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
