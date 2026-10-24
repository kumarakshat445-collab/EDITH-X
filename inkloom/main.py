"""Inkloom brand-governance app."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from inkloom import __version__
from inkloom.db import init_db
from inkloom.routes import HEADER, router
from inkloom.workflow import WorkflowError

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Inkloom",
    version=__version__,
    description="Brand governance. Reviews stay in this workspace, and a person approves publication.",
    lifespan=lifespan,
)
app.include_router(router)


class QuietStatic(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", QuietStatic(directory=STATIC), name="static")


@app.middleware("http")
async def protect(request: Request, call_next):
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.url.path.startswith("/api"):
        if request.headers.get(HEADER) != "1":
            return JSONResponse({"detail": "Missing Inkloom request header."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; frame-src 'self'; "
        "base-uri 'self'; form-action 'self'; object-src 'none'"
    )
    return response


@app.exception_handler(WorkflowError)
async def workflow_error(_request: Request, exc: WorkflowError):
    return JSONResponse({"detail": exc.detail, **exc.extra}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    parts = []
    for item in exc.errors():
        loc = " ".join(str(part) for part in item["loc"] if part != "body")
        parts.append(f"{loc}: {item['msg']}" if loc else item["msg"])
    return JSONResponse({"detail": "; ".join(parts) or "Check the form and try again."}, status_code=422)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "inkloom"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
