"""Inkloom HTTP API and workspace UI."""

from __future__ import annotations

import html
import json
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from inkloom import __version__
from inkloom.db import connect, init_db
from inkloom.seed import seed
from inkloom.workflow import (
    IMAGE_EXTENSIONS,
    TEXT_EXTENSIONS,
    add_asset,
    add_comment,
    add_fact,
    add_guideline,
    add_term,
    apply_finding,
    assign,
    can_view_audit,
    create_submission,
    decide,
    disclosure,
    dismiss_finding,
    get_submission,
    import_bundle,
    insights,
    library_payload,
    list_submissions,
    publish,
    rerun,
    save_revision,
    withdraw,
)

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    con = connect()
    try:
        seed(con)
    finally:
        con.close()
    yield


app = FastAPI(
    title="Inkloom",
    description="Brand governance before publication. Reviews stay in this workspace.",
    version=__version__,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC), name="static")


class SessionIn(BaseModel):
    user_id: str


class GuidelineIn(BaseModel):
    code: str
    title: str = Field(min_length=3)
    category: str
    body: str
    confidential: bool = False


class TermIn(BaseModel):
    phrase: str
    replacement: str = ""
    kind: str
    severity: str
    rationale: str = Field(min_length=8)
    guideline_code: str


class FactIn(BaseModel):
    title: str
    statement: str = Field(min_length=8)
    source: str
    as_of: str
    confidential: bool = False
    guideline_code: str
    checks: list[dict]


class AssetIn(BaseModel):
    name: str
    kind: str
    usage: str = Field(min_length=8)
    hex: str | None = None
    role: str | None = None
    approved: bool = True
    confidential: bool = False


class ReviewIn(BaseModel):
    title: str
    format: str
    channel: str = ""
    purpose: str
    body: str = ""
    alt_text: str = ""
    asset_intent: str = "none"
    assignee_id: str | None = None
    submit: bool = False


class RevisionIn(BaseModel):
    body: str
    alt_text: str | None = None
    note: str = ""
    submit: bool = False


class DismissIn(BaseModel):
    reason: str = Field(min_length=8)


class CommentIn(BaseModel):
    body: str
    finding_id: str | None = None


class DecisionIn(BaseModel):
    action: str
    note: str = ""


class PublishIn(BaseModel):
    note: str = ""


class AssignIn(BaseModel):
    assignee_id: str


def _fail(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _user(authorization: str | None) -> tuple:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in with a workspace role.")
    token = authorization.split(" ", 1)[1].strip()
    con = connect()
    row = con.execute(
        """
        SELECT u.* FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ?
        """,
        (token,),
    ).fetchone()
    if row is None:
        con.close()
        raise HTTPException(status_code=401, detail="That session has ended. Sign in again.")
    return con, dict(row)


def html_to_text(raw: str) -> str:
    without_blocks = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    with_breaks = re.sub(r"(?i)<br\s*/?>", "\n", without_blocks)
    with_paragraphs = re.sub(r"(?i)</p>", "\n\n", with_breaks)
    text = re.sub(r"<[^>]+>", " ", with_paragraphs)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


@app.middleware("http")
async def disclose(request, call_next):
    response = await call_next(request)
    response.headers["X-Inkloom-Disclosure"] = "local-rules-engine; no-external-ai"
    return response


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "inkloom", "version": __version__}


@app.get("/api/disclosure")
def get_disclosure() -> dict:
    return disclosure()


@app.get("/api/users")
def users() -> dict:
    con = connect()
    try:
        rows = [
            dict(row)
            for row in con.execute("SELECT id, name, email, role, title FROM users ORDER BY name")
        ]
        return {"users": rows}
    finally:
        con.close()


@app.post("/api/session")
def start_session(body: SessionIn) -> dict:
    con = connect()
    try:
        row = con.execute("SELECT * FROM users WHERE id = ?", (body.user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="That person isn't in this workspace.")
        token = secrets.token_urlsafe(24)
        from inkloom.workflow import now

        con.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, body.user_id, now()),
        )
        con.commit()
        return {"token": token, "user": dict(row)}
    finally:
        con.close()


@app.get("/api/me")
def me(authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    con.close()
    return {"user": user}


@app.get("/api/reviews")
def reviews(authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        return {"reviews": list_submissions(con, user)}
    finally:
        con.close()


@app.post("/api/reviews")
def create_review(body: ReviewIn, authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        try:
            submission_id = create_submission(con, user, body.model_dump())
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return get_submission(con, user, submission_id)
    finally:
        con.close()


@app.post("/api/reviews/upload")
async def upload_review(
    authorization: str | None = Header(default=None),
    title: str = Form(...),
    format: str = Form(...),
    purpose: str = Form(...),
    channel: str = Form(""),
    alt_text: str = Form(""),
    asset_intent: str = Form("none"),
    assignee_id: str = Form(""),
    submit: str = Form("true"),
    file: UploadFile = File(...),
) -> dict:
    con, user = _user(authorization)
    try:
        raw = await file.read()
        if len(raw) > 5_000_000:
            raise HTTPException(status_code=400, detail="Files need to be 5 MB or smaller.")
        name = file.filename or "upload.txt"
        suffix = Path(name).suffix.lower()
        data = {
            "title": title,
            "format": format,
            "purpose": purpose,
            "channel": channel,
            "alt_text": alt_text,
            "asset_intent": asset_intent or "none",
            "assignee_id": assignee_id or None,
            "submit": submit.lower() != "false",
        }
        image_bytes = None
        if suffix in IMAGE_EXTENSIONS:
            data["format"] = "image"
            image_bytes = raw
            data["body"] = data.get("body") or ""
        elif suffix in TEXT_EXTENSIONS:
            text = raw.decode("utf-8", errors="replace")
            data["body"] = html_to_text(text) if suffix in {".html", ".htm"} else text
            if suffix in {".html", ".htm"}:
                data["channel"] = data["channel"] or "Imported HTML"
        else:
            raise HTTPException(
                status_code=400,
                detail="Upload .txt, .md, .html, or a PNG, JPEG, WEBP, or GIF. PDF isn't decoded.",
            )
        try:
            submission_id = create_submission(
                con,
                user,
                data,
                image_bytes=image_bytes,
                image_name=name,
            )
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return get_submission(con, user, submission_id)
    finally:
        con.close()


@app.get("/api/reviews/{submission_id}")
def review_detail(submission_id: str, authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        try:
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.get("/api/reviews/{submission_id}/image")
def review_image(
    submission_id: str,
    version: int | None = None,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    con, user = _user(authorization)
    try:
        try:
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        versions = payload["versions"]
        chosen = versions[-1]
        if version is not None:
            match = [item for item in versions if item["version"] == version]
            if not match:
                raise HTTPException(status_code=404, detail="Version not found")
            chosen = match[0]
        path = chosen.get("image_path")
        if not path or not Path(path).exists():
            raise HTTPException(status_code=404, detail="This version has no image.")
        return FileResponse(path)
    finally:
        con.close()


@app.post("/api/reviews/{submission_id}/revisions")
def revise(
    submission_id: str,
    body: RevisionIn,
    authorization: str | None = Header(default=None),
) -> dict:
    con, user = _user(authorization)
    try:
        try:
            save_revision(con, user, submission_id, body.body, body.alt_text, body.note, body.submit)
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.post("/api/reviews/{submission_id}/findings/{finding_id}/accept")
def accept(
    submission_id: str,
    finding_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    con, user = _user(authorization)
    try:
        try:
            apply_finding(con, user, submission_id, finding_id)
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.post("/api/reviews/{submission_id}/findings/{finding_id}/dismiss")
def dismiss(
    submission_id: str,
    finding_id: str,
    body: DismissIn,
    authorization: str | None = Header(default=None),
) -> dict:
    con, user = _user(authorization)
    try:
        try:
            dismiss_finding(con, user, submission_id, finding_id, body.reason)
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.post("/api/reviews/{submission_id}/comments")
def comment(
    submission_id: str,
    body: CommentIn,
    authorization: str | None = Header(default=None),
) -> dict:
    con, user = _user(authorization)
    try:
        try:
            add_comment(con, user, submission_id, body.body, body.finding_id)
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.post("/api/reviews/{submission_id}/decision")
def decision(
    submission_id: str,
    body: DecisionIn,
    authorization: str | None = Header(default=None),
) -> dict:
    con, user = _user(authorization)
    try:
        try:
            decide(con, user, submission_id, body.action, body.note)
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.post("/api/reviews/{submission_id}/publish")
def publish_review(
    submission_id: str,
    body: PublishIn,
    authorization: str | None = Header(default=None),
) -> dict:
    con, user = _user(authorization)
    try:
        try:
            publish(con, user, submission_id, body.note)
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.post("/api/reviews/{submission_id}/withdraw")
def withdraw_review(submission_id: str, authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        try:
            withdraw(con, user, submission_id)
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.post("/api/reviews/{submission_id}/assign")
def assign_review(
    submission_id: str,
    body: AssignIn,
    authorization: str | None = Header(default=None),
) -> dict:
    con, user = _user(authorization)
    try:
        try:
            assign(con, user, submission_id, body.assignee_id)
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.post("/api/reviews/{submission_id}/rerun")
def rerun_review(submission_id: str, authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        try:
            rerun(con, user, submission_id)
            payload = get_submission(con, user, submission_id)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return payload
    finally:
        con.close()


@app.get("/api/library")
def library(authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        payload = library_payload(con, user)
        con.commit()
        return payload
    finally:
        con.close()


@app.post("/api/library/guidelines")
def create_guideline(body: GuidelineIn, authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        try:
            add_guideline(con, user, body.model_dump())
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return library_payload(con, user, record_reads=False)
    finally:
        con.close()


@app.post("/api/library/terms")
def create_term(body: TermIn, authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        try:
            add_term(con, user, body.model_dump())
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return library_payload(con, user, record_reads=False)
    finally:
        con.close()


@app.post("/api/library/facts")
def create_fact(body: FactIn, authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        try:
            add_fact(con, user, body.model_dump())
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return library_payload(con, user, record_reads=False)
    finally:
        con.close()


@app.post("/api/library/assets")
def create_asset(body: AssetIn, authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        try:
            add_asset(con, user, body.model_dump())
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return library_payload(con, user, record_reads=False)
    finally:
        con.close()


@app.post("/api/library/import")
async def import_library(
    authorization: str | None = Header(default=None),
    file: UploadFile = File(...),
) -> dict:
    con, user = _user(authorization)
    try:
        raw = await file.read()
        try:
            bundle = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Import a JSON bundle.") from exc
        if not isinstance(bundle, dict):
            raise HTTPException(status_code=400, detail="The bundle should be a JSON object.")
        try:
            created = import_bundle(con, user, bundle)
        except (PermissionError, LookupError, ValueError) as exc:
            _fail(exc)
        con.commit()
        return {"created": created, **library_payload(con, user, record_reads=False)}
    finally:
        con.close()


@app.get("/api/library/template")
def library_template() -> dict:
    return {
        "guidelines": [
            {
                "code": "VOICE-09",
                "title": "Example guideline",
                "category": "tone",
                "body": "Describe the rule, who it is for, and what to write instead.",
                "confidential": False,
            }
        ],
        "terms": [
            {
                "phrase": "synergy",
                "replacement": "working together",
                "kind": "avoid",
                "severity": "warning",
                "rationale": "Synergy is vague. Name the actual collaboration.",
                "guideline_code": "TONE-02",
            }
        ],
        "facts": [],
        "assets": [],
    }


@app.get("/api/insights")
def insight_report(authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        return insights(con, user)
    finally:
        con.close()


@app.get("/api/audit")
def audit_log(authorization: str | None = Header(default=None)) -> dict:
    con, user = _user(authorization)
    try:
        if not can_view_audit(user):
            raise HTTPException(status_code=403, detail="Managers and admins can read the audit log.")
        rows = [
            dict(row)
            for row in con.execute(
                """
                SELECT a.*, u.name AS actor_name
                FROM audit_log a JOIN users u ON u.id = a.actor_id
                ORDER BY a.id DESC
                LIMIT 80
                """
            )
        ]
        return {"entries": rows}
    finally:
        con.close()
