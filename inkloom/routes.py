"""HTTP API. Drafts stay in this workspace; publication is a human decision."""

from __future__ import annotations

import json
import re
import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from inkloom.auth import new_token, verify_password
from inkloom.db import UPLOADS, audit, dumps, loads, now_iso, one, rows, transaction
from inkloom.engine import analyze_image
from inkloom.extract import extract_upload
from inkloom.importer import parse_import
from inkloom.samples import SAMPLES
from inkloom.seed import ACCOUNTS
from inkloom.workflow import (
    WorkflowError,
    add_revision,
    apply_suggestion,
    can_view,
    comment,
    create_submission,
    decide,
    insights,
    lead,
    list_submissions,
    now,
    public_user,
    rerun,
    staff,
    submission_detail,
    transition,
)

router = APIRouter()
COOKIE = "inkloom_session"
HEADER = "x-inkloom-request"
MAX_BYTES = 5_000_000
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
SEVERITIES = {"info", "low", "medium", "high", "critical"}


def disclosure() -> dict:
    return {
        "product": "Inkloom",
        "workspace": "Vela Collective",
        "fictional": True,
        "analysis": "On-platform rules engine (inkloom-rules-1)",
        "external_services": [],
        "ai_disclosure": (
            "Inkloom does not send drafts, guidelines, facts, or assets to an external AI service. "
            "Findings are produced in this workspace by named checks against the approved sources you can open. "
            "Each finding explains the match and cites the guideline, fact, term, or asset involved. "
            "If a draft was written with an AI tool, the author marks that origin. A person still has to approve it, "
            "and the approver cannot be the author."
        ),
        "confidentiality": (
            "Confidential guidelines, facts, and assets are stored in this workspace. "
            "Creator accounts are told that a confidential source matched, without the confidential text or its id. "
            "Reviewers, managers, and admins can open those sources, and each opening is written to the audit log. "
            "Uploads are not placed on a public URL. Remote images in a draft are not loaded by the preview."
        ),
        "human_control": (
            "A suggestion changes nothing until someone saves it as a new revision. "
            "High and critical findings stay open until a reviewer decides them or records an override. "
            "Publishing is a separate step, available only to a manager who did not write the draft."
        ),
        "demo_accounts": [
            {"name": item["name"], "role": item["role"], "email": item["email"], "password": item["password"], "affiliation": item["affiliation"]}
            for item in ACCOUNTS
        ],
    }


class LoginIn(BaseModel):
    email: str
    password: str


class SubmissionIn(BaseModel):
    title: str
    format: str
    channel: str
    purpose: str
    origin: str = "employee"
    body: str = ""
    alt_text: str = ""
    placement_notes: str = ""
    decorative: bool = False
    asset_id: int | None = None


class RevisionIn(BaseModel):
    body: str | None = None
    alt_text: str | None = None
    placement_notes: str | None = None
    decorative: bool | None = None
    asset_id: int | None = None
    note: str = ""


class TransitionIn(BaseModel):
    action: str
    note: str = ""
    assignee_id: int | None = None
    override_reason: str = ""


class DecisionIn(BaseModel):
    action: str
    note: str = ""


class ApplyIn(BaseModel):
    suggestion: str | None = None


class CommentIn(BaseModel):
    body: str
    finding_id: int | None = None


class GuidelineIn(BaseModel):
    category: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=8)
    severity: str
    match_type: str
    match_value: str = ""
    suggestion: str = ""
    good_example: str = ""
    bad_example: str = ""
    confidential: bool = False
    status: str = "draft"


class FactIn(BaseModel):
    topic: str = Field(min_length=3, max_length=160)
    statement: str = Field(min_length=8)
    source_label: str = Field(min_length=2, max_length=160)
    severity: str = "high"
    contradicts: list = []
    supports: list[str] = []
    covers: list[str] = []
    suggested: str = ""
    replacement: str = ""
    confidential: bool = False
    status: str = "draft"
    effective_on: str = ""
    review_after: str = ""


class TermIn(BaseModel):
    preferred: str = Field(min_length=2, max_length=120)
    avoid: list[str]
    definition: str = ""
    context: str = ""
    severity: str = "medium"
    confidential: bool = False
    status: str = "draft"


class AssetIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: str
    description: str = ""
    usage_rules: str = ""
    color_hex: str = ""
    do_not: list[str] = []
    allow_natural_color: bool = False
    confidential: bool = False
    status: str = "draft"


class ImportIn(BaseModel):
    kind: str
    text: str


class ImportCommit(BaseModel):
    kind: str
    items: list[dict]


class RoleIn(BaseModel):
    role: str


class BrandIn(BaseModel):
    name: str
    legal_name: str
    voice: str
    audience: str
    reading_grades: dict


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    with transaction() as conn:
        row = one(
            conn,
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, now_iso()),
        )
    if not row:
        raise HTTPException(401, "Sign in to continue.")
    return row


def _guard(user: dict, allowed: set[str]) -> None:
    if user["role"] not in allowed:
        raise HTTPException(403, "Your role cannot do that.")


def _detail(conn, user: dict, submission_id: int, revision_id: int | None = None) -> dict:
    payload = submission_detail(conn, user, submission_id, revision_id)
    if not payload:
        raise HTTPException(404, "That draft is not in your queue.")
    return payload


@router.get("/api/disclosure")
def get_disclosure() -> dict:
    return disclosure()


@router.post("/api/auth/login")
def login(payload: LoginIn, response: Response) -> dict:
    email = payload.email.strip().lower()
    with transaction() as conn:
        user = one(conn, "SELECT * FROM users WHERE lower(email) = ?", (email,))
        if not user or not verify_password(payload.password, user["password_hash"]):
            audit(conn, None, "login_failed", email[:160], "session")
            token = None
            public = None
        else:
            token = new_token()
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user["id"], now(), now_iso_plus()),
            )
            audit(conn, user["id"], "login", user["email"], "session")
            public = public_user(user)
    if not token:
        raise HTTPException(401, "Email or password does not match.")
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", path="/", max_age=60 * 60 * 24 * 7)
    return {"user": public}


def now_iso_plus() -> str:
    from datetime import datetime, timezone

    moment = datetime.now(timezone.utc) + timedelta(days=7)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@router.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(COOKIE)
    if token:
        with transaction() as conn:
            row = one(conn, "SELECT user_id FROM sessions WHERE token = ?", (token,))
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            if row:
                audit(conn, row["user_id"], "logout", "", "session")
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/api/me")
def me(request: Request) -> dict:
    token = request.cookies.get(COOKIE)
    if not token:
        return {"user": None}
    try:
        return {"user": public_user(current_user(request))}
    except HTTPException:
        return {"user": None}


@router.get("/api/samples")
def samples(request: Request) -> dict:
    current_user(request)
    return {"items": SAMPLES}


@router.get("/api/submissions")
def submissions(request: Request, status: str | None = None, q: str | None = None, mine: bool = False, assigned: bool = False) -> dict:
    user = current_user(request)
    with transaction() as conn:
        return list_submissions(conn, user, status, q, mine, assigned)


@router.post("/api/submissions")
def post_submission(payload: SubmissionIn, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        submission_id = create_submission(conn, user, payload.model_dump())
        return _detail(conn, user, submission_id)


@router.post("/api/submissions/upload")
async def post_upload(
    request: Request,
    title: str = Form(...),
    format: str = Form(...),
    channel: str = Form(...),
    purpose: str = Form(...),
    origin: str = Form("employee"),
    body: str = Form(""),
    alt_text: str = Form(""),
    placement_notes: str = Form(""),
    decorative: bool = Form(False),
    asset_id: int | None = Form(None),
    file: UploadFile | None = File(None),
) -> dict:
    user = current_user(request)
    fields = {
        "title": title,
        "format": format,
        "channel": channel,
        "purpose": purpose,
        "origin": origin,
        "body": body,
        "alt_text": alt_text,
        "placement_notes": placement_notes,
        "decorative": decorative,
        "asset_id": asset_id,
    }
    warnings = []
    if file and file.filename:
        saved = _save_upload(file, "image" if format == "image" else "document")
        fields.update(saved["fields"])
        warnings = saved["warnings"]
        if format != "image" and not body.strip() and saved.get("text"):
            fields["body"] = saved["text"]
    with transaction() as conn:
        submission_id = create_submission(conn, user, fields)
        payload = _detail(conn, user, submission_id)
    payload["extract_warnings"] = warnings
    return payload


@router.get("/api/submissions/{submission_id}")
def get_submission(submission_id: int, request: Request, revision_id: int | None = None) -> dict:
    user = current_user(request)
    with transaction() as conn:
        return _detail(conn, user, submission_id, revision_id)


@router.post("/api/submissions/{submission_id}/revisions")
def post_revision(submission_id: int, payload: RevisionIn, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        add_revision(conn, user, submission_id, payload.model_dump(exclude_unset=True), payload.note)
        return _detail(conn, user, submission_id)


@router.post("/api/submissions/{submission_id}/review")
def post_review(submission_id: int, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        rerun(conn, user, submission_id)
        return _detail(conn, user, submission_id)


@router.post("/api/submissions/{submission_id}/transition")
def post_transition(submission_id: int, payload: TransitionIn, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        transition(
            conn,
            user,
            submission_id,
            payload.action,
            payload.note,
            payload.assignee_id,
            payload.override_reason,
        )
        return _detail(conn, user, submission_id)


@router.post("/api/findings/{finding_id}/decision")
def post_decision(finding_id: int, payload: DecisionIn, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        decide(conn, user, finding_id, payload.action, payload.note)
        finding = one(conn, "SELECT submission_id FROM findings WHERE id = ?", (finding_id,))
        return _detail(conn, user, finding["submission_id"])


@router.post("/api/findings/{finding_id}/apply")
def post_apply(finding_id: int, payload: ApplyIn, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        apply_suggestion(conn, user, finding_id, payload.suggestion)
        finding = one(conn, "SELECT submission_id FROM findings WHERE id = ?", (finding_id,))
        return _detail(conn, user, finding["submission_id"])


@router.post("/api/submissions/{submission_id}/comments")
def post_comment(submission_id: int, payload: CommentIn, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        comment(conn, user, submission_id, payload.body, payload.finding_id)
        return _detail(conn, user, submission_id)


@router.get("/api/revisions/{revision_id}/file")
def revision_file(revision_id: int, request: Request):
    user = current_user(request)
    with transaction() as conn:
        revision = one(conn, "SELECT * FROM revisions WHERE id = ?", (revision_id,))
        if not revision or not revision["file_path"]:
            raise HTTPException(404, "That file is not on the draft.")
        submission = one(conn, "SELECT * FROM submissions WHERE id = ?", (revision["submission_id"],))
        if not submission or not can_view(user, submission):
            raise HTTPException(404, "That file is not on the draft.")
        path = _safe_upload(revision["file_path"])
        filename = _safe_name(revision["file_name"] or "file")
        mime = revision["mime"] or "application/octet-stream"
    return FileResponse(path, media_type=mime, filename=filename)


@router.get("/api/insights")
def get_insights(request: Request, days: int = 90) -> dict:
    user = current_user(request)
    with transaction() as conn:
        return insights(conn, user, days)


@router.get("/api/team")
def team(request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        people = rows(conn, "SELECT id, name, email, role, affiliation FROM users ORDER BY name")
    if not staff(user):
        for person in people:
            if person["id"] != user["id"]:
                person["email"] = ""
    return {"items": people}


@router.patch("/api/team/{user_id}")
def patch_role(user_id: int, payload: RoleIn, request: Request) -> dict:
    user = current_user(request)
    _guard(user, {"admin"})
    if payload.role not in {"creator", "reviewer", "manager", "admin"}:
        raise HTTPException(422, "Unknown role.")
    if user_id == user["id"]:
        raise HTTPException(409, "Ask another admin to change your role.")
    with transaction() as conn:
        target = one(conn, "SELECT * FROM users WHERE id = ?", (user_id,))
        if not target:
            raise HTTPException(404, "That person is not in the workspace.")
        if target["role"] == "admin" and payload.role != "admin":
            count = one(conn, "SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")["c"]
            if count <= 1:
                raise HTTPException(409, "The workspace needs one admin.")
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (payload.role, user_id))
        audit(conn, user["id"], "role_change", f"{target['email']} is now {payload.role}.", "user", user_id)
        people = rows(conn, "SELECT id, name, email, role, affiliation FROM users ORDER BY name")
    return {"items": people}


@router.get("/api/audit")
def audit_log(request: Request) -> dict:
    user = current_user(request)
    _guard(user, {"manager", "admin"})
    with transaction() as conn:
        items = rows(
            conn,
            """
            SELECT a.*, u.name AS actor_name, u.role AS actor_role
            FROM audit a LEFT JOIN users u ON u.id = a.actor_id
            ORDER BY a.id DESC LIMIT 200
            """,
        )
    return {
        "items": [
            {
                "id": item["id"],
                "action": item["action"],
                "detail": item["detail"],
                "target_type": item["target_type"],
                "target_id": item["target_id"],
                "created_at": item["created_at"],
                "actor": None if not item["actor_id"] else {"id": item["actor_id"], "name": item["actor_name"], "role": item["actor_role"]},
            }
            for item in items
        ]
    }


@router.get("/api/brand")
def get_brand(request: Request) -> dict:
    current_user(request)
    with transaction() as conn:
        brand = one(conn, "SELECT * FROM brand WHERE id = 1")
    return {
        "name": brand["name"],
        "legal_name": brand["legal_name"],
        "voice": brand["voice"],
        "audience": brand["audience"],
        "reading_grades": loads(brand["reading_grades_json"], {}),
    }


@router.patch("/api/brand")
def patch_brand(payload: BrandIn, request: Request) -> dict:
    user = current_user(request)
    _guard(user, {"admin"})
    with transaction() as conn:
        conn.execute(
            """
            UPDATE brand SET name = ?, legal_name = ?, voice = ?, audience = ?, reading_grades_json = ?
            WHERE id = 1
            """,
            (payload.name.strip(), payload.legal_name.strip(), payload.voice.strip(), payload.audience.strip(), dumps(payload.reading_grades)),
        )
        audit(conn, user["id"], "brand_change", "Updated the brand profile.", "brand", 1)
        brand = one(conn, "SELECT * FROM brand WHERE id = 1")
    return {
        "name": brand["name"],
        "legal_name": brand["legal_name"],
        "voice": brand["voice"],
        "audience": brand["audience"],
        "reading_grades": loads(brand["reading_grades_json"], {}),
    }


def _library_guard(user: dict, write: bool = False) -> None:
    if write and not lead(user):
        raise HTTPException(403, "A manager maintains the approved sources.")


def _confidential_guard(user: dict, confidential: bool, existing: bool = False) -> None:
    if confidential and user["role"] != "admin":
        raise HTTPException(403, "Only an admin can store or edit a confidential source.")
    if existing and user["role"] != "admin":
        raise HTTPException(403, "Only an admin can edit a confidential source.")


def _visible(row: dict, user: dict) -> bool:
    if row["confidential"] and not staff(user):
        return False
    if not staff(user) and row["status"] not in {"approved", "expired"}:
        return False
    return True


@router.get("/api/guidelines")
def get_guidelines(request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        items = [row for row in rows(conn, "SELECT * FROM guidelines ORDER BY status, category, title") if _visible(row, user)]
    return {"items": [_guideline(row) for row in items]}


@router.get("/api/guidelines/{item_id}")
def get_guideline(item_id: int, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        row = one(conn, "SELECT * FROM guidelines WHERE id = ?", (item_id,))
        if not row or not _visible(row, user):
            raise HTTPException(404, "That guideline is not available to you.")
        if row["confidential"]:
            audit(conn, user["id"], "view_confidential", f"Opened guideline {row['title']}.", "guideline", item_id)
    return _guideline(row)


@router.post("/api/guidelines")
def post_guideline(payload: GuidelineIn, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    _confidential_guard(user, payload.confidential)
    match_value = _clean_match(payload.match_type, payload.match_value)
    _check_severity(payload.severity)
    _check_status(payload.status)
    with transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO guidelines (
              category, title, body, severity, match_type, match_value, suggestion,
              good_example, bad_example, confidential, status, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.category.strip().lower(),
                payload.title.strip(),
                payload.body.strip(),
                payload.severity,
                payload.match_type,
                match_value,
                payload.suggestion.strip(),
                payload.good_example.strip(),
                payload.bad_example.strip(),
                1 if payload.confidential else 0,
                payload.status,
                user["id"],
                now(),
                now(),
            ),
        )
        audit(conn, user["id"], "guideline_change", f"Created {payload.title}.", "guideline", cur.lastrowid)
        row = one(conn, "SELECT * FROM guidelines WHERE id = ?", (cur.lastrowid,))
    return _guideline(row)


@router.patch("/api/guidelines/{item_id}")
def patch_guideline(item_id: int, payload: GuidelineIn, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    with transaction() as conn:
        existing = one(conn, "SELECT * FROM guidelines WHERE id = ?", (item_id,))
        if not existing:
            raise HTTPException(404, "That guideline is not in the library.")
        _confidential_guard(user, payload.confidential or bool(existing["confidential"]), existing=bool(existing["confidential"]))
        match_value = _clean_match(payload.match_type, payload.match_value)
        _check_severity(payload.severity)
        _check_status(payload.status)
        conn.execute(
            """
            UPDATE guidelines SET
              category = ?, title = ?, body = ?, severity = ?, match_type = ?, match_value = ?,
              suggestion = ?, good_example = ?, bad_example = ?, confidential = ?, status = ?,
              updated_by = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.category.strip().lower(),
                payload.title.strip(),
                payload.body.strip(),
                payload.severity,
                payload.match_type,
                match_value,
                payload.suggestion.strip(),
                payload.good_example.strip(),
                payload.bad_example.strip(),
                1 if payload.confidential else 0,
                payload.status,
                user["id"],
                now(),
                item_id,
            ),
        )
        audit(conn, user["id"], "guideline_change", f"Updated {payload.title}.", "guideline", item_id)
        row = one(conn, "SELECT * FROM guidelines WHERE id = ?", (item_id,))
    return _guideline(row)


@router.delete("/api/guidelines/{item_id}")
def delete_guideline(item_id: int, request: Request) -> dict:
    user = current_user(request)
    _guard(user, {"admin"})
    with transaction() as conn:
        row = one(conn, "SELECT * FROM guidelines WHERE id = ?", (item_id,))
        if not row:
            raise HTTPException(404, "That guideline is not in the library.")
        conn.execute("DELETE FROM guidelines WHERE id = ?", (item_id,))
        audit(conn, user["id"], "guideline_change", f"Deleted {row['title']}.", "guideline", item_id)
    return {"ok": True}


@router.get("/api/facts")
def get_facts(request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        items = [row for row in rows(conn, "SELECT * FROM facts ORDER BY status, topic") if _visible(row, user)]
    return {"items": [_fact(row) for row in items]}


@router.get("/api/facts/{item_id}")
def get_fact(item_id: int, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        row = one(conn, "SELECT * FROM facts WHERE id = ?", (item_id,))
        if not row or not _visible(row, user):
            raise HTTPException(404, "That fact is not available to you.")
        if row["confidential"]:
            audit(conn, user["id"], "view_confidential", f"Opened fact {row['topic']}.", "fact", item_id)
    return _fact(row)


@router.post("/api/facts")
def post_fact(payload: FactIn, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    _confidential_guard(user, payload.confidential)
    _check_severity(payload.severity)
    _check_status(payload.status, extra={"expired"})
    with transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO facts (
              topic, statement, source_label, severity, contradicts_json, supports_json, covers_json,
              suggested, replacement, confidential, status, effective_on, review_after, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.topic.strip(),
                payload.statement.strip(),
                payload.source_label.strip(),
                payload.severity,
                dumps(payload.contradicts),
                dumps(payload.supports),
                dumps(payload.covers),
                payload.suggested.strip(),
                payload.replacement.strip(),
                1 if payload.confidential else 0,
                payload.status,
                payload.effective_on,
                payload.review_after,
                user["id"],
                now(),
                now(),
            ),
        )
        audit(conn, user["id"], "fact_change", f"Created {payload.topic}.", "fact", cur.lastrowid)
        row = one(conn, "SELECT * FROM facts WHERE id = ?", (cur.lastrowid,))
    return _fact(row)


@router.patch("/api/facts/{item_id}")
def patch_fact(item_id: int, payload: FactIn, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    _check_severity(payload.severity)
    _check_status(payload.status, extra={"expired"})
    with transaction() as conn:
        existing = one(conn, "SELECT * FROM facts WHERE id = ?", (item_id,))
        if not existing:
            raise HTTPException(404, "That fact is not in the library.")
        _confidential_guard(user, payload.confidential or bool(existing["confidential"]), existing=bool(existing["confidential"]))
        conn.execute(
            """
            UPDATE facts SET
              topic = ?, statement = ?, source_label = ?, severity = ?, contradicts_json = ?, supports_json = ?,
              covers_json = ?, suggested = ?, replacement = ?, confidential = ?, status = ?, effective_on = ?,
              review_after = ?, updated_by = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.topic.strip(),
                payload.statement.strip(),
                payload.source_label.strip(),
                payload.severity,
                dumps(payload.contradicts),
                dumps(payload.supports),
                dumps(payload.covers),
                payload.suggested.strip(),
                payload.replacement.strip(),
                1 if payload.confidential else 0,
                payload.status,
                payload.effective_on,
                payload.review_after,
                user["id"],
                now(),
                item_id,
            ),
        )
        audit(conn, user["id"], "fact_change", f"Updated {payload.topic}.", "fact", item_id)
        row = one(conn, "SELECT * FROM facts WHERE id = ?", (item_id,))
    return _fact(row)


@router.get("/api/terms")
def get_terms(request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        items = [row for row in rows(conn, "SELECT * FROM terms ORDER BY preferred") if _visible(row, user)]
    return {"items": [_term(row) for row in items]}


@router.post("/api/terms")
def post_term(payload: TermIn, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    _confidential_guard(user, payload.confidential)
    _check_severity(payload.severity)
    _check_status(payload.status)
    avoid = [part.strip() for part in payload.avoid if part.strip()]
    if not avoid:
        raise HTTPException(422, "Add at least one word to avoid.")
    with transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO terms (
              preferred, avoid_json, definition, context, severity, confidential, status, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.preferred.strip(),
                dumps(avoid),
                payload.definition.strip(),
                payload.context.strip(),
                payload.severity,
                1 if payload.confidential else 0,
                payload.status,
                user["id"],
                now(),
                now(),
            ),
        )
        audit(conn, user["id"], "term_change", f"Created {payload.preferred}.", "term", cur.lastrowid)
        row = one(conn, "SELECT * FROM terms WHERE id = ?", (cur.lastrowid,))
    return _term(row)


@router.patch("/api/terms/{item_id}")
def patch_term(item_id: int, payload: TermIn, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    _check_severity(payload.severity)
    _check_status(payload.status)
    avoid = [part.strip() for part in payload.avoid if part.strip()]
    if not avoid:
        raise HTTPException(422, "Add at least one word to avoid.")
    with transaction() as conn:
        existing = one(conn, "SELECT * FROM terms WHERE id = ?", (item_id,))
        if not existing:
            raise HTTPException(404, "That term is not in the library.")
        _confidential_guard(user, payload.confidential or bool(existing["confidential"]), existing=bool(existing["confidential"]))
        conn.execute(
            """
            UPDATE terms SET preferred = ?, avoid_json = ?, definition = ?, context = ?, severity = ?,
              confidential = ?, status = ?, updated_by = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.preferred.strip(),
                dumps(avoid),
                payload.definition.strip(),
                payload.context.strip(),
                payload.severity,
                1 if payload.confidential else 0,
                payload.status,
                user["id"],
                now(),
                item_id,
            ),
        )
        audit(conn, user["id"], "term_change", f"Updated {payload.preferred}.", "term", item_id)
        row = one(conn, "SELECT * FROM terms WHERE id = ?", (item_id,))
    return _term(row)


@router.get("/api/assets")
def get_assets(request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        items = [row for row in rows(conn, "SELECT * FROM assets ORDER BY kind, name") if _visible(row, user)]
    return {"items": [_asset(row) for row in items]}


@router.get("/api/assets/{item_id}")
def get_asset(item_id: int, request: Request) -> dict:
    user = current_user(request)
    with transaction() as conn:
        row = one(conn, "SELECT * FROM assets WHERE id = ?", (item_id,))
        if not row or not _visible(row, user):
            raise HTTPException(404, "That asset is not available to you.")
        if row["confidential"]:
            audit(conn, user["id"], "view_confidential", f"Opened asset {row['name']}.", "asset", item_id)
    return _asset(row)


@router.post("/api/assets")
def post_asset(payload: AssetIn, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    _confidential_guard(user, payload.confidential)
    _check_status(payload.status)
    if payload.kind not in {"color", "logo", "photo", "font", "layout"}:
        raise HTTPException(422, "Kind must be color, logo, photo, font, or layout.")
    with transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO assets (
              name, kind, description, usage_rules, color_hex, rules_json, confidential, status, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _asset_values(payload, user["id"]),
        )
        audit(conn, user["id"], "asset_change", f"Created {payload.name}.", "asset", cur.lastrowid)
        row = one(conn, "SELECT * FROM assets WHERE id = ?", (cur.lastrowid,))
    return _asset(row)


@router.patch("/api/assets/{item_id}")
def patch_asset(item_id: int, payload: AssetIn, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    _check_status(payload.status)
    with transaction() as conn:
        existing = one(conn, "SELECT * FROM assets WHERE id = ?", (item_id,))
        if not existing:
            raise HTTPException(404, "That asset is not in the library.")
        _confidential_guard(user, payload.confidential or bool(existing["confidential"]), existing=bool(existing["confidential"]))
        name, kind, description, usage, color, rules, confidential, status, updated_by, _created, updated = _asset_values(payload, user["id"])
        conn.execute(
            """
            UPDATE assets SET name = ?, kind = ?, description = ?, usage_rules = ?, color_hex = ?, rules_json = ?,
              confidential = ?, status = ?, updated_by = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, kind, description, usage, color, rules, confidential, status, updated_by, updated, item_id),
        )
        audit(conn, user["id"], "asset_change", f"Updated {payload.name}.", "asset", item_id)
        row = one(conn, "SELECT * FROM assets WHERE id = ?", (item_id,))
    return _asset(row)


@router.get("/api/assets/{item_id}/file")
def asset_file(item_id: int, request: Request):
    user = current_user(request)
    with transaction() as conn:
        row = one(conn, "SELECT * FROM assets WHERE id = ?", (item_id,))
        if not row or not row["file_path"] or not _visible(row, user):
            raise HTTPException(404, "That file is not available to you.")
        if row["confidential"]:
            audit(conn, user["id"], "view_confidential", f"Downloaded asset {row['name']}.", "asset", item_id)
        path = _safe_upload(row["file_path"])
        filename = _safe_name(row["file_name"] or row["name"])
        mime = row["mime"] or "application/octet-stream"
    return FileResponse(path, media_type=mime, filename=filename)


@router.post("/api/import/preview")
def import_preview(payload: ImportIn, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    try:
        items = parse_import(payload.kind, payload.text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"items": items}


@router.post("/api/import/commit")
def import_commit(payload: ImportCommit, request: Request) -> dict:
    user = current_user(request)
    _library_guard(user, write=True)
    if payload.kind not in {"guidelines", "facts", "terms", "assets"}:
        raise HTTPException(422, "Unknown library.")
    created = 0
    with transaction() as conn:
        for item in payload.items:
            confidential = bool(item.get("confidential")) and user["role"] == "admin"
            if payload.kind == "guidelines":
                post_like = GuidelineIn(
                    category=item.get("category") or "messaging",
                    title=item.get("title") or "Imported guideline",
                    body=item.get("body") or "Imported draft. Add the rule before approving.",
                    severity=item.get("severity") if item.get("severity") in SEVERITIES else "medium",
                    match_type="keywords",
                    match_value=item.get("match_value") or "",
                    suggestion=item.get("suggestion") or "",
                    good_example=item.get("good_example") or "",
                    bad_example=item.get("bad_example") or "",
                    confidential=confidential,
                    status="draft",
                )
                match_value = _clean_match(post_like.match_type, post_like.match_value)
                conn.execute(
                    """
                    INSERT INTO guidelines (
                      category, title, body, severity, match_type, match_value, suggestion,
                      good_example, bad_example, confidential, status, updated_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
                    """,
                    (
                        post_like.category,
                        post_like.title,
                        post_like.body,
                        post_like.severity,
                        post_like.match_type,
                        match_value,
                        post_like.suggestion,
                        post_like.good_example,
                        post_like.bad_example,
                        1 if confidential else 0,
                        user["id"],
                        now(),
                        now(),
                    ),
                )
            elif payload.kind == "facts":
                conn.execute(
                    """
                    INSERT INTO facts (
                      topic, statement, source_label, severity, contradicts_json, supports_json, covers_json,
                      suggested, replacement, confidential, status, updated_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, 'draft', ?, ?, ?)
                    """,
                    (
                        item.get("topic") or "Imported fact",
                        item.get("statement") or "",
                        item.get("source_label") or "Imported source",
                        item.get("severity") if item.get("severity") in SEVERITIES else "high",
                        dumps([{"phrase": phrase} for phrase in item.get("contradicts") or []]),
                        dumps(item.get("supports") or []),
                        item.get("suggested") or "",
                        item.get("replacement") or "",
                        1 if confidential else 0,
                        user["id"],
                        now(),
                        now(),
                    ),
                )
            elif payload.kind == "terms":
                avoid = item.get("avoid") or []
                if not avoid:
                    continue
                conn.execute(
                    """
                    INSERT INTO terms (
                      preferred, avoid_json, definition, context, severity, confidential, status, updated_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
                    """,
                    (
                        item.get("preferred"),
                        dumps(avoid),
                        item.get("definition") or "",
                        item.get("context") or "",
                        item.get("severity") if item.get("severity") in SEVERITIES else "medium",
                        1 if confidential else 0,
                        user["id"],
                        now(),
                        now(),
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO assets (
                      name, kind, description, usage_rules, color_hex, rules_json, confidential, status, updated_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
                    """,
                    (
                        item.get("name") or "Imported asset",
                        item.get("kind") if item.get("kind") in {"color", "logo", "photo", "font", "layout"} else "layout",
                        item.get("description") or "",
                        item.get("usage_rules") or "",
                        item.get("color_hex") or "",
                        dumps({"do_not": item.get("do_not") or [], "allow_natural_color": False}),
                        1 if confidential else 0,
                        user["id"],
                        now(),
                        now(),
                    ),
                )
            created += 1
        audit(conn, user["id"], "import", f"Imported {created} draft {payload.kind}.", payload.kind)
    return {"created": created}


@router.post("/api/extract")
async def extract(request: Request, file: UploadFile = File(...)) -> dict:
    current_user(request)
    saved = _save_upload(file, "document")
    (UPLOADS / saved["fields"]["file_path"]).unlink(missing_ok=True)
    return {"text": saved.get("text") or "", "warnings": saved["warnings"], "file_name": saved["fields"].get("file_name")}


def _guideline(row: dict) -> dict:
    return {
        "id": row["id"],
        "category": row["category"],
        "title": row["title"],
        "body": row["body"],
        "severity": row["severity"],
        "match_type": row["match_type"],
        "match_value": row["match_value"],
        "suggestion": row["suggestion"],
        "good_example": row["good_example"],
        "bad_example": row["bad_example"],
        "confidential": bool(row["confidential"]),
        "status": row["status"],
        "updated_at": row["updated_at"],
    }


def _fact(row: dict) -> dict:
    return {
        "id": row["id"],
        "topic": row["topic"],
        "statement": row["statement"],
        "source_label": row["source_label"],
        "severity": row["severity"],
        "contradicts": loads(row["contradicts_json"], []),
        "supports": loads(row["supports_json"], []),
        "covers": loads(row["covers_json"], []),
        "suggested": row["suggested"],
        "replacement": row["replacement"],
        "confidential": bool(row["confidential"]),
        "status": row["status"],
        "effective_on": row["effective_on"],
        "review_after": row["review_after"],
        "updated_at": row["updated_at"],
    }


def _term(row: dict) -> dict:
    return {
        "id": row["id"],
        "preferred": row["preferred"],
        "avoid": loads(row["avoid_json"], []),
        "definition": row["definition"],
        "context": row["context"],
        "severity": row["severity"],
        "confidential": bool(row["confidential"]),
        "status": row["status"],
        "updated_at": row["updated_at"],
    }


def _asset(row: dict) -> dict:
    rules = loads(row["rules_json"], {})
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "description": row["description"],
        "usage_rules": row["usage_rules"],
        "color_hex": row["color_hex"],
        "do_not": rules.get("do_not") or [],
        "allow_natural_color": bool(rules.get("allow_natural_color")),
        "confidential": bool(row["confidential"]),
        "status": row["status"],
        "file_url": f"/api/assets/{row['id']}/file" if row["file_path"] else None,
        "updated_at": row["updated_at"],
    }


def _asset_values(payload: AssetIn, user_id: int) -> tuple:
    moment = now()
    return (
        payload.name.strip(),
        payload.kind,
        payload.description.strip(),
        payload.usage_rules.strip(),
        payload.color_hex.strip(),
        dumps({"do_not": payload.do_not, "allow_natural_color": payload.allow_natural_color}),
        1 if payload.confidential else 0,
        payload.status,
        user_id,
        moment,
        moment,
    )


def _check_severity(value: str) -> None:
    if value not in SEVERITIES:
        raise HTTPException(422, "Severity must be info, low, medium, high, or critical.")


def _check_status(value: str, extra: set[str] | None = None) -> None:
    allowed = {"draft", "approved", "retired"} | (extra or set())
    if value not in allowed:
        raise HTTPException(422, "That status is not available.")


def _clean_match(match_type: str, match_value: str) -> str:
    allowed = {"keywords", "regex", "claims", "accessibility", "visual", "required_when"}
    if match_type not in allowed:
        raise HTTPException(422, "Unknown match type.")
    text = (match_value or "").strip()
    if match_type == "keywords":
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise HTTPException(422, "Keyword patterns must be a JSON list or one phrase per line.") from exc
            if not isinstance(parsed, list):
                raise HTTPException(422, "Keyword patterns must be a list.")
            return dumps([str(item).strip() for item in parsed if str(item).strip()])
        phrases = [part.strip() for part in re.split(r"[\n|]", text) if part.strip()]
        return dumps(phrases)
    if match_type == "regex":
        if text:
            if len(text) > 180:
                raise HTTPException(422, "Keep a pattern under 180 characters.")
            try:
                re.compile(text)
            except re.error as exc:
                raise HTTPException(422, f"That pattern is not valid: {exc}") from exc
        return text
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(422, "This match type expects a JSON object.") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(422, "This match type expects a JSON object.")
        return dumps(parsed)
    return dumps({})


def _save_upload(upload: UploadFile, kind: str) -> dict:
    filename = upload.filename or "upload"
    suffix = Path(filename).suffix.lower()
    data = upload.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Files are limited to 5 MB.")
    if not data:
        raise HTTPException(422, "That file is empty.")
    warnings: list[str] = []
    text = ""
    image = None
    if kind == "image":
        if suffix not in IMAGE_TYPES:
            raise HTTPException(422, "Use a PNG, JPEG, WebP, or GIF. SVG files are not accepted.")
        mime = IMAGE_TYPES[suffix]
    else:
        if suffix not in {".txt", ".md", ".markdown", ".html", ".htm", ".docx", ".pdf"}:
            raise HTTPException(422, "Use a .txt, .md, .html, .docx, or .pdf file.")
        try:
            text, warnings = extract_upload(filename, data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        mime = "application/octet-stream"
    stored = secrets.token_hex(16) + suffix
    path = UPLOADS / stored
    path.write_bytes(data)
    if kind == "image":
        try:
            image = analyze_image(str(path))
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(422, "That image could not be read.") from exc
    return {
        "fields": {
            "file_path": stored,
            "file_name": Path(filename).name[-120:],
            "mime": mime,
            "image": image,
        },
        "warnings": warnings,
        "text": text,
    }


def _safe_upload(stored: str) -> Path:
    if not stored or "/" in stored or "\\" in stored or stored.startswith("."):
        raise HTTPException(404, "That file is not available.")
    path = (UPLOADS / stored).resolve()
    if not path.is_relative_to(UPLOADS.resolve()) or not path.is_file():
        raise HTTPException(404, "That file is not available.")
    return path


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80]
    return cleaned or "file"
