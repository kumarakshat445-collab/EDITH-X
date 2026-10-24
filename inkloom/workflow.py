"""Review workflow: versions, human decisions, and library access.

Automation proposes findings. Status changes that publish or approve content
always require a person, and nobody can approve their own draft.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from inkloom.db import connect, uploads_dir
from inkloom.engine import (
    FactCheck,
    Guideline,
    Library,
    PaletteColor,
    ReviewInput,
    Term,
    review_content,
)

FORMATS = {"social", "email", "web", "document", "image", "ad"}
INTENTS = {"none", "logo", "graphic", "photo", "decorative"}
CATEGORIES = {
    "tone",
    "terminology",
    "messaging",
    "visual",
    "accessibility",
    "claims",
    "facts",
}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def can_see_confidential(user: dict) -> bool:
    return user["role"] in {"reviewer", "manager", "admin"}


def can_manage_library(user: dict) -> bool:
    return user["role"] in {"manager", "admin"}


def can_view_audit(user: dict) -> bool:
    return user["role"] in {"manager", "admin"}


def audit(con, user: dict, action: str, target_type: str, target_id: str, detail: str) -> None:
    con.execute(
        """
        INSERT INTO audit_log (at, actor_id, action, target_type, target_id, detail)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (now(), user["id"], action, target_type, target_id, detail),
    )


def row_dict(row) -> dict:
    return dict(row) if row is not None else {}


def load_library(con) -> Library:
    guidelines = [
        Guideline(
            id=row["id"],
            code=row["code"],
            title=row["title"],
            body=row["body"],
            category=row["category"],
            confidential=bool(row["confidential"]),
        )
        for row in con.execute("SELECT * FROM guidelines")
    ]
    terms = [
        Term(
            id=row["id"],
            phrase=row["phrase"],
            replacement=row["replacement"],
            kind=row["kind"],
            severity=row["severity"],
            rationale=row["rationale"],
            guideline_code=row["guideline_code"],
        )
        for row in con.execute("SELECT * FROM terms")
    ]
    checks: list[FactCheck] = []
    for row in con.execute("SELECT * FROM facts WHERE status = 'approved'"):
        payload = json.loads(row["checks_json"])
        for check in payload.get("checks", []):
            checks.append(
                FactCheck(
                    fact_id=row["id"],
                    title=row["title"],
                    statement=row["statement"],
                    source=row["source"],
                    as_of=row["as_of"],
                    confidential=bool(row["confidential"]),
                    guideline_code=row["guideline_code"],
                    label=check["label"],
                    value=float(check["value"]),
                    tolerance=float(check.get("tolerance") or 0),
                    terms=list(check.get("terms") or []),
                    unit=check.get("unit"),
                    min_abs=check.get("min_abs"),
                    max_abs=check.get("max_abs"),
                    counterpart=check.get("counterpart"),
                )
            )
    palette = [
        PaletteColor(row["id"], row["name"], row["hex"], row["role"] or "")
        for row in con.execute(
            "SELECT * FROM assets WHERE kind = 'color' AND approved = 1 AND hex IS NOT NULL"
        )
    ]
    return Library(terms=terms, checks=checks, guidelines=guidelines, palette=palette)


def _public_guideline_map(con) -> dict[str, sqlite3_row]:
    return {row["id"]: row for row in con.execute("SELECT * FROM guidelines")}


def redact_source_body(con, finding: dict, user: dict, seen: set | None = None) -> dict:
    """Attach the cited source, hiding confidential bodies from creators."""
    allowed = can_see_confidential(user)
    source_body = None
    restricted = False
    confidential = False
    source_key = None
    if finding["source_type"] == "guideline":
        row = con.execute("SELECT * FROM guidelines WHERE id = ?", (finding["source_id"],)).fetchone()
        if row is None:
            row = con.execute("SELECT * FROM guidelines WHERE code = ?", (finding["source_id"],)).fetchone()
        if row is not None:
            confidential = bool(row["confidential"])
            restricted = confidential and not allowed
            source_body = None if restricted else row["body"]
            source_key = ("guideline", row["id"])
    elif finding["source_type"] == "fact":
        row = con.execute("SELECT * FROM facts WHERE id = ?", (finding["source_id"],)).fetchone()
        if row is not None:
            confidential = bool(row["confidential"])
            restricted = confidential and not allowed
            source_body = None if restricted else row["statement"]
            source_key = ("fact", row["id"])
    if confidential and source_key is not None and seen is not None and source_key not in seen:
        seen.add(source_key)
        action = "confidential.read" if allowed else "confidential.blocked"
        audit(con, user, action, source_key[0], source_key[1], finding["source_label"])
    explanation = finding["explanation"]
    if restricted and finding.get("public_explanation"):
        explanation = finding["public_explanation"]
    return {
        **finding,
        "explanation": explanation,
        "source_body": source_body,
        "source_restricted": restricted,
        "source_confidential": confidential,
    }


def run_review(con, submission: dict, version: dict, actor: dict) -> list[dict]:
    library = load_library(con)
    produced = review_content(
        ReviewInput(
            body=version["body"],
            fmt=submission["format"],
            purpose=submission["purpose"],
            alt_text=version["alt_text"] or "",
            asset_intent=submission["asset_intent"] or "none",
            image_path=version["image_path"],
        ),
        library,
    )
    prior = con.execute(
        """
        SELECT rule_id, excerpt, status, decision_note, decided_by, decided_at
        FROM findings
        WHERE submission_id = ? AND status = 'dismissed'
        """,
        (submission["id"],),
    ).fetchall()
    carried = {(row["rule_id"], row["excerpt"]): row for row in prior}
    con.execute(
        "DELETE FROM findings WHERE submission_id = ? AND version = ? AND status = 'open'",
        (submission["id"], version["version"]),
    )
    saved = []
    for item in produced:
        key = (item.rule_id, item.excerpt)
        status = "open"
        note = None
        decided_by = None
        decided_at = None
        if key in carried:
            status = "dismissed"
            previous = carried[key]
            note = previous["decision_note"]
            decided_by = previous["decided_by"]
            decided_at = previous["decided_at"]
        finding_id = new_id("fnd")
        con.execute(
            """
            INSERT INTO findings (
              id, submission_id, version, rule_id, category, severity, title, excerpt,
              explanation, public_explanation, suggestion, replacement, apply_mode,
              source_type, source_id, source_label, confidence, span_start, span_end,
              status, decision_note, decided_by, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                submission["id"],
                version["version"],
                item.rule_id,
                item.category,
                item.severity,
                item.title,
                item.excerpt,
                item.explanation,
                item.public_explanation,
                item.suggestion,
                item.replacement,
                item.apply_mode,
                item.source_type,
                item.source_id,
                item.source_label,
                item.confidence,
                item.span_start,
                item.span_end,
                status,
                note,
                decided_by,
                decided_at,
            ),
        )
        saved.append(finding_id)
    audit(
        con,
        actor,
        "review.run",
        "submission",
        submission["id"],
        f"Version {version['version']}: {len(produced)} findings",
    )
    return saved


def _submission(con, submission_id: str) -> dict:
    row = con.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    if row is None:
        raise LookupError("Review not found")
    return row_dict(row)


def _version(con, submission_id: str, version: int) -> dict:
    row = con.execute(
        "SELECT * FROM versions WHERE submission_id = ? AND version = ?",
        (submission_id, version),
    ).fetchone()
    if row is None:
        raise LookupError("Version not found")
    return row_dict(row)


def can_read(user: dict, submission: dict) -> bool:
    if user["role"] in {"manager", "admin"}:
        return True
    if user["role"] == "reviewer":
        return submission["status"] != "draft" or submission["owner_id"] == user["id"]
    return submission["owner_id"] == user["id"]


def list_submissions(con, user: dict) -> list[dict]:
    rows = con.execute(
        """
        SELECT s.*, u.name AS owner_name, a.name AS assignee_name
        FROM submissions s
        JOIN users u ON u.id = s.owner_id
        LEFT JOIN users a ON a.id = s.assignee_id
        ORDER BY s.updated_at DESC
        """
    ).fetchall()
    visible = []
    for row in rows:
        item = row_dict(row)
        if not can_read(user, item):
            continue
        counts = con.execute(
            """
            SELECT severity, COUNT(*) AS n FROM findings
            WHERE submission_id = ? AND version = ? AND status = 'open'
            GROUP BY severity
            """,
            (item["id"], item["current_version"]),
        ).fetchall()
        item["open_counts"] = {entry["severity"]: entry["n"] for entry in counts}
        visible.append(item)
    return visible


def get_submission(con, user: dict, submission_id: str) -> dict:
    submission = _submission(con, submission_id)
    if not can_read(user, submission):
        raise PermissionError("You can't open this review.")
    owner = con.execute("SELECT name, role, title FROM users WHERE id = ?", (submission["owner_id"],)).fetchone()
    assignee = None
    if submission["assignee_id"]:
        assignee = con.execute(
            "SELECT id, name, role, title FROM users WHERE id = ?",
            (submission["assignee_id"],),
        ).fetchone()
    versions = [
        row_dict(row)
        for row in con.execute(
            """
            SELECT v.*, u.name AS author_name
            FROM versions v JOIN users u ON u.id = v.author_id
            WHERE v.submission_id = ?
            ORDER BY v.version
            """,
            (submission_id,),
        )
    ]
    findings = []
    seen_sources: set = set()
    for row in con.execute(
        """
        SELECT * FROM findings WHERE submission_id = ? ORDER BY version, severity
        """,
        (submission_id,),
    ):
        findings.append(redact_source_body(con, row_dict(row), user, seen_sources))
    comments = []
    for row in con.execute(
        """
        SELECT c.*, u.name AS author_name, u.role AS author_role
        FROM comments c JOIN users u ON u.id = c.author_id
        WHERE c.submission_id = ? ORDER BY c.created_at
        """,
        (submission_id,),
    ):
        comments.append(row_dict(row))
    decisions = []
    for row in con.execute(
        """
        SELECT d.*, u.name AS actor_name, u.role AS actor_role
        FROM decisions d JOIN users u ON u.id = d.actor_id
        WHERE d.submission_id = ? ORDER BY d.created_at
        """,
        (submission_id,),
    ):
        decisions.append(row_dict(row))
    open_critical = con.execute(
        """
        SELECT COUNT(*) AS n FROM findings
        WHERE submission_id = ? AND version = ? AND status = 'open' AND severity = 'critical'
        """,
        (submission_id, submission["current_version"]),
    ).fetchone()["n"]
    open_warning = con.execute(
        """
        SELECT COUNT(*) AS n FROM findings
        WHERE submission_id = ? AND version = ? AND status = 'open' AND severity = 'warning'
        """,
        (submission_id, submission["current_version"]),
    ).fetchone()["n"]
    return {
        "submission": {
            **submission,
            "owner_name": owner["name"],
            "owner_title": owner["title"],
            "assignee_name": assignee["name"] if assignee else None,
        },
        "versions": versions,
        "findings": findings,
        "comments": comments,
        "decisions": decisions,
        "permissions": permissions(user, submission, open_critical, open_warning),
        "open_critical": open_critical,
        "open_warning": open_warning,
    }


def permissions(user: dict, submission: dict, open_critical: int, open_warning: int) -> dict:
    owner = submission["owner_id"] == user["id"]
    role = user["role"]
    editable_status = submission["status"] in {"draft", "changes_requested", "in_review", "approved"}
    return {
        "can_edit": editable_status and (owner or role in {"manager", "admin"}),
        "can_submit": submission["status"] in {"draft", "changes_requested"} and (owner or role in {"manager", "admin"}),
        "can_comment": True,
        "can_apply": editable_status and (owner or role in {"manager", "admin"}),
        "can_dismiss": role in {"reviewer", "manager", "admin"} and not owner,
        "can_decide": role in {"reviewer", "manager", "admin"} and not owner and submission["status"] in {"in_review", "changes_requested"},
        "can_publish": role in {"manager", "admin"} and not owner and submission["status"] == "approved" and open_critical == 0,
        "can_withdraw": owner and submission["status"] in {"draft", "in_review", "changes_requested"},
        "can_see_confidential": can_see_confidential(user),
        "needs_warning_note": open_warning > 0,
        "blocked_by_critical": open_critical > 0,
    }


def _write_version(con, submission_id: str, number: int, body: str, alt_text: str, image_path: str | None, note: str, author_id: str) -> dict:
    version_id = new_id("ver")
    created = now()
    con.execute(
        """
        INSERT INTO versions (
          id, submission_id, version, body, alt_text, image_path, note, author_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (version_id, submission_id, number, body, alt_text or "", image_path, note, author_id, created),
    )
    return _version(con, submission_id, number)


def create_submission(con, user: dict, data: dict, image_bytes: bytes | None = None, image_name: str | None = None) -> str:
    fmt = data["format"]
    if fmt not in FORMATS:
        raise ValueError("Choose a supported format.")
    intent = data.get("asset_intent") or "none"
    if intent not in INTENTS:
        raise ValueError("Unknown asset intent.")
    if fmt == "image" and intent == "none":
        raise ValueError("Say whether this image is a logo, graphic, photo, or decorative.")
    purpose = (data.get("purpose") or "").strip()
    if len(purpose) < 8:
        raise ValueError("Add a purpose of at least a short sentence so suggestions can protect it.")
    title = (data.get("title") or "").strip()
    if len(title) < 3:
        raise ValueError("Give the review a title.")
    body = data.get("body") or ""
    alt_text = data.get("alt_text") or ""
    if fmt != "image" and not body.strip():
        raise ValueError("Add the content to review.")
    submission_id = data.get("id") or new_id("sub")
    created = now()
    image_path = _store_image(submission_id, image_bytes, image_name) if image_bytes else None
    if fmt == "image" and not image_path and not data.get("allow_missing_file"):
        raise ValueError("Upload an image file.")
    submit = bool(data.get("submit"))
    status = "in_review" if submit else "draft"
    con.execute(
        """
        INSERT INTO submissions (
          id, title, format, channel, purpose, status, owner_id, assignee_id, asset_intent,
          current_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            submission_id,
            title,
            fmt,
            (data.get("channel") or "").strip(),
            purpose,
            status,
            user["id"],
            data.get("assignee_id") or None,
            intent,
            created,
            created,
        ),
    )
    note = "Submitted for review" if submit else "Draft saved"
    version = _write_version(con, submission_id, 1, body, alt_text, image_path, note, user["id"])
    submission = _submission(con, submission_id)
    run_review(con, submission, version, user)
    if submit:
        _decide_row(con, submission_id, user, "submit", note)
    audit(con, user, "submission.create", "submission", submission_id, title)
    return submission_id


def _store_image(submission_id: str, image_bytes: bytes, image_name: str | None) -> str:
    suffix = Path(image_name or "image.png").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".png"
    filename = f"{submission_id}{suffix}"
    path = uploads_dir() / filename
    path.write_bytes(image_bytes)
    return str(path)


def save_revision(con, user: dict, submission_id: str, body: str, alt_text: str | None, note: str, submit: bool) -> int:
    submission = _submission(con, submission_id)
    perms = permissions(user, submission, 0, 0)
    if not perms["can_edit"]:
        raise PermissionError("You can't edit this review.")
    current = _version(con, submission_id, submission["current_version"])
    number = submission["current_version"] + 1
    version = _write_version(
        con,
        submission_id,
        number,
        body,
        current["alt_text"] if alt_text is None else alt_text,
        current["image_path"],
        note.strip() or "Edited",
        user["id"],
    )
    previous = submission["status"]
    status = "in_review" if submit or previous == "approved" else previous
    con.execute(
        "UPDATE submissions SET current_version = ?, status = ?, updated_at = ? WHERE id = ?",
        (number, status, now(), submission_id),
    )
    submission = _submission(con, submission_id)
    run_review(con, submission, version, user)
    if previous == "approved":
        _decide_row(con, submission_id, user, "revision", "A new version cleared the earlier approval.")
    if submit:
        _decide_row(con, submission_id, user, "submit", note.strip() or "Resubmitted")
    return number


def apply_finding(con, user: dict, submission_id: str, finding_id: str) -> int:
    submission = _submission(con, submission_id)
    finding = con.execute("SELECT * FROM findings WHERE id = ? AND submission_id = ?", (finding_id, submission_id)).fetchone()
    if finding is None:
        raise LookupError("Finding not found")
    if finding["version"] != submission["current_version"]:
        raise ValueError("Apply suggestions on the current version.")
    if finding["status"] != "open":
        raise ValueError("This finding is no longer open.")
    perms = permissions(user, submission, 0, 0)
    if not perms["can_apply"]:
        raise PermissionError("Only the creator or a manager can apply a suggestion, and it is never applied on its own.")
    if finding["apply_mode"] == "advisory" or finding["replacement"] is None and finding["apply_mode"] != "replace":
        if finding["apply_mode"] != "replace":
            raise ValueError("This suggestion needs a manual edit so the original purpose stays intact.")
    current = _version(con, submission_id, submission["current_version"])
    body = current["body"]
    alt_text = current["alt_text"]
    if finding["apply_mode"] == "set_alt":
        if not finding["replacement"]:
            raise ValueError("Write the alt text yourself. There isn't a safe automatic line.")
        alt_text = finding["replacement"]
    elif finding["apply_mode"] == "replace":
        start, end = finding["span_start"], finding["span_end"]
        excerpt = finding["excerpt"]
        replacement = finding["replacement"] if finding["replacement"] is not None else ""
        if start is not None and end is not None and body[start:end] == excerpt:
            body = body[:start] + replacement + body[end:]
        else:
            index = body.find(excerpt) if excerpt else -1
            if index < 0:
                raise ValueError("The wording has moved. Edit the draft directly.")
            body = body[:index] + replacement + body[index + len(excerpt) :]
    else:
        raise ValueError("This suggestion needs a manual edit so the original purpose stays intact.")
    number = save_revision(
        con,
        user,
        submission_id,
        body,
        alt_text,
        f"Applied suggestion: {finding['title']}",
        submit=False,
    )
    con.execute(
        """
        UPDATE findings SET status = 'accepted', decided_by = ?, decided_at = ?, decision_note = ?
        WHERE id = ?
        """,
        (user["id"], now(), "Suggestion applied by a person", finding_id),
    )
    audit(con, user, "finding.accept", "finding", finding_id, finding["title"])
    return number


def dismiss_finding(con, user: dict, submission_id: str, finding_id: str, reason: str) -> None:
    reason = reason.strip()
    if len(reason) < 8:
        raise ValueError("Give a reason a later reviewer can understand.")
    submission = _submission(con, submission_id)
    if not can_read(user, submission):
        raise PermissionError("You can't open this review.")
    finding = con.execute(
        "SELECT * FROM findings WHERE id = ? AND submission_id = ?",
        (finding_id, submission_id),
    ).fetchone()
    if finding is None:
        raise LookupError("Finding not found")
    if finding["status"] != "open":
        raise ValueError("This finding is no longer open.")
    if user["role"] not in {"reviewer", "manager", "admin"} or submission["owner_id"] == user["id"]:
        raise PermissionError("Another reviewer records the dismissal so the exception stays accountable.")
    con.execute(
        """
        UPDATE findings
        SET status = 'dismissed', decision_note = ?, decided_by = ?, decided_at = ?
        WHERE id = ?
        """,
        (reason, user["id"], now(), finding_id),
    )
    con.execute("UPDATE submissions SET updated_at = ? WHERE id = ?", (now(), submission_id))
    audit(con, user, "finding.dismiss", "finding", finding_id, reason)


def add_comment(con, user: dict, submission_id: str, body: str, finding_id: str | None) -> str:
    submission = _submission(con, submission_id)
    if not can_read(user, submission):
        raise PermissionError("You can't comment on this review.")
    text = body.strip()
    if len(text) < 2:
        raise ValueError("Write a comment.")
    if finding_id:
        found = con.execute(
            "SELECT id FROM findings WHERE id = ? AND submission_id = ?",
            (finding_id, submission_id),
        ).fetchone()
        if found is None:
            raise LookupError("Finding not found")
    comment_id = new_id("cmt")
    con.execute(
        """
        INSERT INTO comments (id, submission_id, author_id, body, finding_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (comment_id, submission_id, user["id"], text, finding_id, now()),
    )
    con.execute("UPDATE submissions SET updated_at = ? WHERE id = ?", (now(), submission_id))
    audit(con, user, "comment.add", "submission", submission_id, text[:140])
    return comment_id


def _decide_row(con, submission_id: str, user: dict, action: str, note: str) -> None:
    con.execute(
        """
        INSERT INTO decisions (id, submission_id, actor_id, action, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (new_id("dec"), submission_id, user["id"], action, note, now()),
    )


def _open_counts(con, submission_id: str, version: int) -> tuple[int, int]:
    critical = con.execute(
        """
        SELECT COUNT(*) AS n FROM findings
        WHERE submission_id = ? AND version = ? AND status = 'open' AND severity = 'critical'
        """,
        (submission_id, version),
    ).fetchone()["n"]
    warning = con.execute(
        """
        SELECT COUNT(*) AS n FROM findings
        WHERE submission_id = ? AND version = ? AND status = 'open' AND severity = 'warning'
        """,
        (submission_id, version),
    ).fetchone()["n"]
    return critical, warning


def decide(con, user: dict, submission_id: str, action: str, note: str) -> str:
    submission = _submission(con, submission_id)
    critical, warning = _open_counts(con, submission_id, submission["current_version"])
    perms = permissions(user, submission, critical, warning)
    if not perms["can_decide"]:
        if submission["owner_id"] == user["id"]:
            raise PermissionError("You can't approve your own work. Ask a reviewer or manager.")
        raise PermissionError("You can't make that decision on this review.")
    text = (note or "").strip()
    if action == "approve":
        if critical:
            raise ValueError(
                "Open critical findings still need a correction or a recorded dismissal before approval."
            )
        if warning and len(text) < 8:
            raise ValueError("Acknowledge the open warnings in the approval note.")
        status = "approved"
    elif action == "request_changes":
        if len(text) < 8:
            raise ValueError("Tell the creator what still needs to change.")
        status = "changes_requested"
    elif action == "reject":
        if len(text) < 8:
            raise ValueError("Record why this was rejected.")
        status = "rejected"
    else:
        raise ValueError("Unknown decision.")
    con.execute(
        "UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?",
        (status, now(), submission_id),
    )
    _decide_row(con, submission_id, user, action, text)
    audit(con, user, f"review.{action}", "submission", submission_id, text[:180])
    return status


def publish(con, user: dict, submission_id: str, note: str) -> str:
    submission = _submission(con, submission_id)
    critical, warning = _open_counts(con, submission_id, submission["current_version"])
    perms = permissions(user, submission, critical, warning)
    if submission["owner_id"] == user["id"]:
        raise PermissionError("A different manager has to publish this.")
    if user["role"] not in {"manager", "admin"}:
        raise PermissionError("Only a manager can publish.")
    if submission["status"] != "approved":
        raise ValueError("Publish only after a person has approved the current version.")
    if critical:
        raise ValueError("Critical findings are still open.")
    text = (note or "").strip() or "Published"
    con.execute(
        "UPDATE submissions SET status = 'published', updated_at = ? WHERE id = ?",
        (now(), submission_id),
    )
    _decide_row(con, submission_id, user, "publish", text)
    audit(con, user, "review.publish", "submission", submission_id, text[:180])
    return "published"


def withdraw(con, user: dict, submission_id: str) -> str:
    submission = _submission(con, submission_id)
    if submission["owner_id"] != user["id"]:
        raise PermissionError("Only the creator can withdraw this draft.")
    if submission["status"] not in {"draft", "in_review", "changes_requested"}:
        raise ValueError("This review can no longer be withdrawn.")
    con.execute(
        "UPDATE submissions SET status = 'withdrawn', updated_at = ? WHERE id = ?",
        (now(), submission_id),
    )
    _decide_row(con, submission_id, user, "withdraw", "Withdrawn by the creator")
    return "withdrawn"


def assign(con, user: dict, submission_id: str, assignee_id: str) -> None:
    if user["role"] not in {"manager", "admin", "reviewer"}:
        raise PermissionError("Only reviewers and managers assign work.")
    submission = _submission(con, submission_id)
    if not can_read(user, submission):
        raise PermissionError("You can't open this review.")
    assignee = con.execute("SELECT * FROM users WHERE id = ?", (assignee_id,)).fetchone()
    if assignee is None:
        raise LookupError("That person isn't in this workspace.")
    con.execute(
        "UPDATE submissions SET assignee_id = ?, updated_at = ? WHERE id = ?",
        (assignee_id, now(), submission_id),
    )
    audit(con, user, "review.assign", "submission", submission_id, assignee["name"])


def rerun(con, user: dict, submission_id: str) -> int:
    submission = _submission(con, submission_id)
    if not can_read(user, submission):
        raise PermissionError("You can't open this review.")
    if user["role"] == "creator" and submission["owner_id"] != user["id"]:
        raise PermissionError("You can rerun reviews on your own drafts.")
    version = _version(con, submission_id, submission["current_version"])
    run_review(con, submission, version, user)
    con.execute("UPDATE submissions SET updated_at = ? WHERE id = ?", (now(), submission_id))
    return submission["current_version"]


def library_payload(con, user: dict, *, record_reads: bool = True) -> dict:
    allowed = can_see_confidential(user)
    guidelines = []
    for row in con.execute("SELECT * FROM guidelines ORDER BY code"):
        item = row_dict(row)
        item["confidential"] = bool(item["confidential"])
        if item["confidential"] and not allowed:
            item["body"] = None
            item["redacted"] = True
            if record_reads:
                audit(con, user, "confidential.blocked", "guideline", item["id"], item["code"])
        else:
            item["redacted"] = False
            if item["confidential"] and record_reads:
                audit(con, user, "confidential.read", "guideline", item["id"], item["code"])
        guidelines.append(item)
    facts = []
    for row in con.execute("SELECT * FROM facts ORDER BY title"):
        item = row_dict(row)
        item["confidential"] = bool(item["confidential"])
        if item["confidential"] and not allowed:
            item["statement"] = None
            item["source"] = "Restricted source"
            item["checks_json"] = "[]"
            item["redacted"] = True
            if record_reads:
                audit(con, user, "confidential.blocked", "fact", item["id"], item["title"])
        else:
            item["redacted"] = False
            if item["confidential"] and record_reads:
                audit(con, user, "confidential.read", "fact", item["id"], item["title"])
        facts.append(item)
    terms = [row_dict(row) for row in con.execute("SELECT * FROM terms ORDER BY phrase")]
    assets = []
    for row in con.execute("SELECT * FROM assets ORDER BY kind, name"):
        item = row_dict(row)
        item["confidential"] = bool(item["confidential"])
        item["approved"] = bool(item["approved"])
        if item["confidential"] and not allowed:
            item["usage_text"] = None
            item["redacted"] = True
        else:
            item["redacted"] = False
        assets.append(item)
    return {"guidelines": guidelines, "facts": facts, "terms": terms, "assets": assets}


def add_guideline(con, user: dict, data: dict) -> str:
    if not can_manage_library(user):
        raise PermissionError("Managers maintain the guideline library.")
    code = data["code"].strip().upper()
    if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", code):
        raise ValueError("Use a code like VOICE-04.")
    if data["category"] not in CATEGORIES:
        raise ValueError("Unknown guideline category.")
    if len(data["body"].strip()) < 20:
        raise ValueError("Write the guideline so a reviewer can cite it.")
    guideline_id = new_id("gdl")
    con.execute(
        """
        INSERT INTO guidelines (id, code, title, category, body, confidential, version, updated_at, updated_by)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            guideline_id,
            code,
            data["title"].strip(),
            data["category"],
            data["body"].strip(),
            1 if data.get("confidential") else 0,
            now(),
            user["id"],
        ),
    )
    audit(con, user, "library.guideline", "guideline", guideline_id, code)
    return guideline_id


def add_term(con, user: dict, data: dict) -> str:
    if not can_manage_library(user):
        raise PermissionError("Managers maintain terminology.")
    phrase = data["phrase"].strip()
    if len(phrase) < 2:
        raise ValueError("Enter the term.")
    if data["kind"] not in {"banned", "avoid", "fear"}:
        raise ValueError("Kind must be banned, avoid, or fear.")
    if data["severity"] not in {"critical", "warning", "note"}:
        raise ValueError("Unknown severity.")
    guideline = con.execute("SELECT code FROM guidelines WHERE code = ?", (data["guideline_code"].strip(),)).fetchone()
    if guideline is None:
        raise ValueError("Cite an existing guideline code.")
    term_id = new_id("trm")
    con.execute(
        """
        INSERT INTO terms (id, phrase, replacement, kind, severity, rationale, guideline_code)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            term_id,
            phrase,
            (data.get("replacement") or "").strip(),
            data["kind"],
            data["severity"],
            data["rationale"].strip(),
            data["guideline_code"].strip(),
        ),
    )
    audit(con, user, "library.term", "term", term_id, phrase)
    return term_id


def add_fact(con, user: dict, data: dict) -> str:
    if not can_manage_library(user):
        raise PermissionError("Managers maintain approved facts.")
    checks = data["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError("Add at least one numeric check, or store the fact and a check that names its terms.")
    for check in checks:
        if "label" not in check or "value" not in check:
            raise ValueError("Each check needs a label and a value.")
        float(check["value"])
    fact_id = new_id("fct")
    con.execute(
        """
        INSERT INTO facts (id, title, statement, source, as_of, confidential, status, guideline_code, checks_json)
        VALUES (?, ?, ?, ?, ?, ?, 'approved', ?, ?)
        """,
        (
            fact_id,
            data["title"].strip(),
            data["statement"].strip(),
            data["source"].strip(),
            data["as_of"].strip(),
            1 if data.get("confidential") else 0,
            data["guideline_code"].strip(),
            json.dumps({"checks": checks}),
        ),
    )
    audit(con, user, "library.fact", "fact", fact_id, data["title"].strip())
    return fact_id


def add_asset(con, user: dict, data: dict) -> str:
    if not can_manage_library(user):
        raise PermissionError("Managers maintain approved assets.")
    hex_value = (data.get("hex") or "").strip() or None
    if hex_value and not re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_value):
        raise ValueError("Colors use a #RRGGBB value.")
    asset_id = new_id("ast")
    con.execute(
        """
        INSERT INTO assets (id, name, kind, usage_text, hex, role, approved, confidential)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            data["name"].strip(),
            data["kind"].strip(),
            data["usage"].strip(),
            hex_value.upper() if hex_value else None,
            (data.get("role") or "").strip() or None,
            0 if data.get("approved") is False else 1,
            1 if data.get("confidential") else 0,
        ),
    )
    audit(con, user, "library.asset", "asset", asset_id, data["name"].strip())
    return asset_id


def import_bundle(con, user: dict, bundle: dict) -> dict:
    if not can_manage_library(user):
        raise PermissionError("Managers import library material.")
    created = {"guidelines": 0, "facts": 0, "terms": 0, "assets": 0}
    for item in bundle.get("guidelines") or []:
        add_guideline(con, user, item)
        created["guidelines"] += 1
    for item in bundle.get("facts") or []:
        add_fact(con, user, item)
        created["facts"] += 1
    for item in bundle.get("terms") or []:
        add_term(con, user, item)
        created["terms"] += 1
    for item in bundle.get("assets") or []:
        add_asset(con, user, item)
        created["assets"] += 1
    if sum(created.values()) == 0:
        raise ValueError("The file didn't include guidelines, facts, terms, or assets.")
    return created


def insights(con, user: dict) -> dict:
    if user["role"] == "creator":
        scope_sql = "AND s.owner_id = ?"
        scope = (user["id"],)
    else:
        scope_sql = ""
        scope = ()
    fetched = [
        row_dict(row)
        for row in con.execute(
            f"""
            SELECT f.*, s.owner_id, s.format, s.status AS submission_status, s.title AS submission_title
            FROM findings f
            JOIN submissions s ON s.id = f.submission_id
            WHERE 1 = 1 {scope_sql}
            ORDER BY f.version DESC
            """,
            scope,
        )
    ]
    findings = []
    seen_keys = set()
    for finding in fetched:
        key = (finding["submission_id"], finding["rule_id"], finding["excerpt"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        findings.append(finding)
    by_category: dict[str, int] = {}
    by_rule: dict[str, dict] = {}
    by_guideline: dict[str, dict] = {}
    for finding in findings:
        by_category[finding["category"]] = by_category.get(finding["category"], 0) + 1
        rule = by_rule.setdefault(
            finding["rule_id"],
            {
                "rule_id": finding["rule_id"],
                "category": finding["category"],
                "title": finding["title"],
                "count": 0,
                "dismissed": 0,
                "accepted": 0,
                "open": 0,
            },
        )
        rule["count"] += 1
        if finding["status"] in rule:
            rule[finding["status"]] += 1
        label = finding["source_label"]
        guide = by_guideline.setdefault(
            label,
            {"source_label": label, "source_id": finding["source_id"], "count": 0, "dismissed": 0},
        )
        guide["count"] += 1
        if finding["status"] == "dismissed":
            guide["dismissed"] += 1
    guidelines = {
        row["id"]: row_dict(row)
        for row in con.execute("SELECT id, code, title, body, confidential FROM guidelines")
    }
    unclear = []
    for guide in by_guideline.values():
        row = guidelines.get(guide["source_id"])
        body_len = len(row["body"]) if row else 0
        dismiss_rate = guide["dismissed"] / guide["count"] if guide["count"] else 0
        reasons = []
        if guide["count"] >= 2 and dismiss_rate >= 0.34:
            reasons.append(
                "People often override this source. The rule may be too blunt, or the guideline needs a clearer example."
            )
        if row and body_len < 220 and guide["count"] >= 2:
            reasons.append(
                "This guideline is brief and already being cited. Add an example of what to write instead."
            )
        if reasons:
            unclear.append(
                {
                    **guide,
                    "body_length": body_len,
                    "dismiss_rate": round(dismiss_rate, 2),
                    "reasons": reasons,
                    "code": row["code"] if row else guide["source_label"],
                }
            )
    unclear.sort(key=lambda item: item["count"], reverse=True)
    rules = sorted(by_rule.values(), key=lambda item: item["count"], reverse=True)
    submissions = [
        row_dict(row)
        for row in con.execute(
            f"SELECT status, format FROM submissions s WHERE 1 = 1 {scope_sql}",
            scope,
        )
    ]
    by_status: dict[str, int] = {}
    for submission in submissions:
        by_status[submission["status"]] = by_status.get(submission["status"], 0) + 1
    accepted = sum(1 for finding in findings if finding["status"] == "accepted")
    dismissed = sum(1 for finding in findings if finding["status"] == "dismissed")
    decided = accepted + dismissed
    repeated = [rule for rule in rules if rule["count"] >= 2]
    top_rule = repeated[0]["title"] if repeated else None
    if user["role"] == "creator":
        lede = (
            "These patterns are from your own drafts. "
            "Repeated flags usually mean a guideline example would save the next round."
        )
    elif top_rule:
        lede = (
            f"The most repeated signal is “{top_rule}”. "
            "That is the first place to clarify the guideline or coach the team."
        )
    else:
        lede = "There isn't a repeated pattern yet. Insights appear as more reviews are run."
    people = []
    if user["role"] in {"manager", "admin"}:
        rows = con.execute(
            """
            SELECT u.name AS name, f.rule_id AS rule_id,
                   COUNT(DISTINCT s.id || ':' || f.excerpt) AS n
            FROM findings f
            JOIN submissions s ON s.id = f.submission_id
            JOIN users u ON u.id = s.owner_id
            GROUP BY u.name, f.rule_id
            HAVING n >= 2
            ORDER BY n DESC
            LIMIT 6
            """
        ).fetchall()
        people = [row_dict(row) for row in rows]
    return {
        "lede": lede,
        "by_category": [{"category": key, "count": value} for key, value in sorted(by_category.items(), key=lambda item: -item[1])],
        "rules": rules[:8],
        "unclear_guidelines": unclear[:6],
        "by_status": [{"status": key, "count": value} for key, value in by_status.items()],
        "suggestion_acceptance": {
            "accepted": accepted,
            "dismissed": dismissed,
            "rate": round(accepted / decided, 2) if decided else None,
        },
        "repeated_by_author": people,
        "totals": {
            "findings": len(findings),
            "reviews": len(submissions),
            "open": sum(1 for finding in findings if finding["status"] == "open"),
        },
    }


def disclosure() -> dict:
    return {
        "product": "Inkloom",
        "automation": (
            "Reviews run with a local rules engine inside this workspace. "
            "Each finding names the rule and the guideline, fact, term, or asset that triggered it."
        ),
        "external_services": (
            "Drafts, guidelines, facts, and assets are stored in this workspace database. "
            "They are not sent to an external AI service or any other third party by the review engine."
        ),
        "human_control": (
            "Suggestions are proposals. Nothing is rewritten, approved, or published until a person does it. "
            "Creators cannot approve their own work. Critical findings block approval until they are corrected "
            "or dismissed with a written reason."
        ),
        "confidentiality": (
            "Library records can be marked confidential. Creators see that a restricted source exists and "
            "the safe public correction, not the restricted text. Reviewers, managers, and admins can open it, "
            "and those reads are written to the audit log."
        ),
        "identity": (
            "This demo workspace uses named roles so the workflow can be tried end to end. "
            "It is not an enterprise identity provider."
        ),
        "formats": [
            {"id": "social", "label": "Social post", "input": "Text"},
            {"id": "email", "label": "Email", "input": "Text"},
            {"id": "web", "label": "Web page", "input": "Text"},
            {"id": "ad", "label": "Advertisement", "input": "Text"},
            {"id": "document", "label": "Document", "input": ".txt, .md, or .html"},
            {"id": "image", "label": "Image", "input": "PNG, JPEG, WEBP, or GIF, plus alt text"},
        ],
        "not_supported": "PDF and Office files are not decoded. Paste the text or export to .txt, .md, or .html.",
    }
