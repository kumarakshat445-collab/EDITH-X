"""Review persistence, roles, and the human approval workflow."""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta, timezone

from inkloom.db import audit, dumps, loads, now_iso, one, rows
from inkloom.engine import review

STATUSES = ("draft", "in_review", "changes_requested", "approved", "rejected", "published")
FORMATS = ("social", "email", "web", "document", "image")
ORIGINS = ("employee", "agency", "ai_tool")
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class WorkflowError(Exception):
    def __init__(self, status: int, detail: str, extra: dict | None = None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.extra = extra or {}


def now() -> str:
    return now_iso()


def shift(days: int = 0, hours: int = 0) -> str:
    moment = datetime.now(timezone.utc) + timedelta(days=days, hours=hours)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def staff(user: dict) -> bool:
    return user["role"] in {"reviewer", "manager", "admin"}


def lead(user: dict) -> bool:
    return user["role"] in {"manager", "admin"}


def can_view(user: dict, submission: dict) -> bool:
    if staff(user):
        return True
    return user["id"] in {submission["author_id"], submission.get("assignee_id")}


def public_user(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "affiliation": row["affiliation"],
    }


def load_corpus(conn) -> dict:
    guidelines = []
    for row in rows(conn, "SELECT * FROM guidelines WHERE status = 'approved'"):
        item = dict(row)
        item["confidential"] = bool(item["confidential"])
        guidelines.append(item)
    facts = []
    for row in rows(conn, "SELECT * FROM facts WHERE status IN ('approved', 'expired')"):
        facts.append(
            {
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
            }
        )
    terms = []
    for row in rows(conn, "SELECT * FROM terms WHERE status = 'approved'"):
        terms.append(
            {
                "id": row["id"],
                "preferred": row["preferred"],
                "avoid": loads(row["avoid_json"], []),
                "definition": row["definition"],
                "context": row["context"],
                "severity": row["severity"],
                "confidential": bool(row["confidential"]),
                "status": row["status"],
            }
        )
    assets = []
    for row in rows(conn, "SELECT * FROM assets WHERE status = 'approved'"):
        assets.append(_asset_dict(row))
    brand = one(conn, "SELECT * FROM brand WHERE id = 1")
    grades = loads(brand["reading_grades_json"], {}) if brand else {}
    return {"guidelines": guidelines, "facts": facts, "terms": terms, "assets": assets, "reading_grades": grades}


def _asset_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "description": row["description"],
        "usage_rules": row["usage_rules"],
        "color_hex": row["color_hex"],
        "rules": loads(row["rules_json"], {}),
        "confidential": bool(row["confidential"]),
        "status": row["status"],
    }


def _add_event(conn, submission_id: int, actor_id: int | None, action: str, detail: str = "", from_status: str | None = None, to_status: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO events (submission_id, actor_id, action, detail, from_status, to_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (submission_id, actor_id, action, detail, from_status, to_status, now()),
    )


def _store_findings(conn, submission_id: int, revision_id: int, findings: list[dict]) -> None:
    conn.execute("DELETE FROM findings WHERE revision_id = ?", (revision_id,))
    for finding in findings:
        conn.execute(
            """
            INSERT INTO findings (
              submission_id, revision_id, category, severity, status, excerpt, explanation,
              suggestion, suggestion_mode, replaces, replace_start, replace_end, replace_text,
              source_type, source_id, source_label, source_excerpt, confidential_source,
              pattern_key, start_pos, end_pos, decision_note, created_at
            ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?)
            """,
            (
                submission_id,
                revision_id,
                finding["category"],
                finding["severity"],
                (finding.get("excerpt") or "")[:500],
                finding.get("explanation") or "",
                finding.get("suggestion") or "",
                finding.get("suggestion_mode") or "advice",
                finding.get("replaces") or "",
                finding.get("replace_start"),
                finding.get("replace_end"),
                finding.get("replace_text"),
                finding.get("source_type") or "policy",
                finding.get("source_id"),
                finding.get("source_label") or "",
                (finding.get("source_excerpt") or "")[:2000],
                1 if finding.get("confidential_source") else 0,
                finding.get("pattern_key") or "",
                finding.get("start_pos"),
                finding.get("end_pos"),
                now(),
            ),
        )


def run_review(conn, submission: dict, revision: dict) -> dict:
    corpus = load_corpus(conn)
    asset = None
    if revision.get("asset_id"):
        row = one(conn, "SELECT * FROM assets WHERE id = ?", (revision["asset_id"],))
        if row:
            asset = _asset_dict(row)
    image = loads(revision.get("image_json"), None)
    result = review(
        body=revision.get("body") or "",
        fmt=submission["format"],
        channel=submission["channel"],
        purpose=submission["purpose"],
        alt_text=revision.get("alt_text") or "",
        placement_notes=revision.get("placement_notes") or "",
        decorative=bool(revision.get("decorative")),
        asset=asset,
        image=image,
        **corpus,
    )
    _store_findings(conn, submission["id"], revision["id"], result["findings"])
    conn.execute("UPDATE revisions SET review_json = ? WHERE id = ?", (dumps(result["meta"]), revision["id"]))
    return result


def _require_fields(fields: dict) -> None:
    title = (fields.get("title") or "").strip()
    purpose = (fields.get("purpose") or "").strip()
    channel = (fields.get("channel") or "").strip()
    if len(title) < 3 or len(title) > 160:
        raise WorkflowError(422, "Give the draft a title of at least 3 characters.")
    if fields.get("format") not in FORMATS:
        raise WorkflowError(422, "Choose a format: social, email, web, document, or image.")
    if len(channel) < 2 or len(channel) > 80:
        raise WorkflowError(422, "Name the channel this draft is for.")
    if len(purpose) < 8 or len(purpose) > 400:
        raise WorkflowError(422, "Describe the purpose in a sentence so suggestions can keep it.")
    if fields.get("origin") not in ORIGINS:
        raise WorkflowError(422, "Say whether this draft came from an employee, an agency, or an AI tool.")
    body = fields.get("body") or ""
    if len(body) > 50000:
        raise WorkflowError(422, "Drafts are limited to 50,000 characters.")
    has_image = bool(fields.get("file_path"))
    if not body.strip() and not (fields.get("alt_text") or "").strip() and not (fields.get("placement_notes") or "").strip() and not has_image:
        raise WorkflowError(422, "Add the draft, an image, or placement notes before running a review.")


def _checked_asset(conn, user: dict, asset_id: int | None) -> dict | None:
    if not asset_id:
        return None
    row = one(conn, "SELECT * FROM assets WHERE id = ?", (asset_id,))
    if not row or row["status"] == "retired":
        raise WorkflowError(422, "That asset is not in the library.")
    if row["confidential"] and not staff(user):
        raise WorkflowError(403, "That asset is confidential. A reviewer has to attach it.")
    if row["status"] != "approved":
        raise WorkflowError(422, "Only an approved asset can be attached. Approve it in the library first.")
    return row


def create_submission(conn, user: dict, fields: dict) -> int:
    _require_fields(fields)
    _checked_asset(conn, user, fields.get("asset_id"))
    moment = now()
    cur = conn.execute(
        """
        INSERT INTO submissions (
          title, format, channel, purpose, origin, status, author_id, assignee_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'draft', ?, NULL, ?, ?)
        """,
        (
            fields["title"].strip(),
            fields["format"],
            fields["channel"].strip(),
            fields["purpose"].strip(),
            fields["origin"],
            user["id"],
            moment,
            moment,
        ),
    )
    submission_id = cur.lastrowid
    revision_id = _insert_revision(conn, user, submission_id, fields, "First review")
    conn.execute(
        "UPDATE submissions SET current_revision_id = ? WHERE id = ?",
        (revision_id, submission_id),
    )
    submission = one(conn, "SELECT * FROM submissions WHERE id = ?", (submission_id,))
    revision = one(conn, "SELECT * FROM revisions WHERE id = ?", (revision_id,))
    run_review(conn, submission, revision)
    _add_event(conn, submission_id, user["id"], "reviewed", "On-platform review ran. Nothing was published.", "draft", "draft")
    return submission_id


def _insert_revision(conn, user: dict, submission_id: int, fields: dict, note: str) -> int:
    cur = conn.execute(
        """
        INSERT INTO revisions (
          submission_id, body, alt_text, placement_notes, decorative, asset_id,
          file_path, file_name, mime, image_json, created_by, note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            submission_id,
            fields.get("body") or "",
            fields.get("alt_text") or "",
            fields.get("placement_notes") or "",
            1 if fields.get("decorative") else 0,
            fields.get("asset_id"),
            fields.get("file_path"),
            fields.get("file_name"),
            fields.get("mime"),
            dumps(fields["image"]) if fields.get("image") else None,
            user["id"],
            note,
            now(),
        ),
    )
    return cur.lastrowid


def add_revision(conn, user: dict, submission_id: int, fields: dict, note: str) -> int:
    submission = _writable(conn, user, submission_id)
    current = one(conn, "SELECT * FROM revisions WHERE id = ?", (submission["current_revision_id"],))

    def pick(key, current_value):
        return fields[key] if key in fields else current_value

    merged = {
        "body": pick("body", current["body"]),
        "alt_text": pick("alt_text", current["alt_text"]),
        "placement_notes": pick("placement_notes", current["placement_notes"]),
        "decorative": pick("decorative", current["decorative"]),
        "asset_id": pick("asset_id", current["asset_id"]),
        "file_path": fields.get("file_path") or current["file_path"],
        "file_name": fields.get("file_name") or current["file_name"] if not fields.get("file_path") else fields.get("file_name"),
        "mime": fields.get("mime") or current["mime"] if not fields.get("file_path") else fields.get("mime"),
        "image": fields.get("image") if fields.get("file_path") else loads(current["image_json"], None),
        "format": submission["format"],
        "title": submission["title"],
        "channel": submission["channel"],
        "purpose": submission["purpose"],
        "origin": submission["origin"],
    }
    _require_fields(merged)
    if merged["asset_id"]:
        _checked_asset(conn, user, merged["asset_id"])
    revision_id = _insert_revision(conn, user, submission_id, merged, note or "Edited draft")
    conn.execute(
        "UPDATE submissions SET current_revision_id = ?, updated_at = ?, status = ? WHERE id = ?",
        (revision_id, now(), "draft" if submission["status"] == "rejected" else submission["status"], submission_id),
    )
    submission = one(conn, "SELECT * FROM submissions WHERE id = ?", (submission_id,))
    revision = one(conn, "SELECT * FROM revisions WHERE id = ?", (revision_id,))
    run_review(conn, submission, revision)
    _add_event(conn, submission_id, user["id"], "revised", note or "Edited draft and ran the review again.")
    return revision_id


def _writable(conn, user: dict, submission_id: int) -> dict:
    submission = one(conn, "SELECT * FROM submissions WHERE id = ?", (submission_id,))
    if not submission or not can_view(user, submission):
        raise WorkflowError(404, "That draft is not in your queue.")
    if submission["status"] not in {"draft", "changes_requested", "rejected"}:
        raise WorkflowError(409, "This draft is locked for review. Ask for changes before editing it.")
    author = submission["author_id"] == user["id"]
    if not author and not lead(user):
        raise WorkflowError(403, "Only the author or a manager can edit this draft.")
    return submission


def rerun(conn, user: dict, submission_id: int) -> None:
    submission = one(conn, "SELECT * FROM submissions WHERE id = ?", (submission_id,))
    if not submission or not can_view(user, submission):
        raise WorkflowError(404, "That draft is not in your queue.")
    if submission["status"] in {"approved", "published"}:
        raise WorkflowError(409, "Pull the piece back to a draft before reviewing a new version.")
    if submission["status"] == "in_review" and not staff(user):
        raise WorkflowError(403, "A reviewer owns this pass. You can comment, and edit after they request changes.")
    revision = one(conn, "SELECT * FROM revisions WHERE id = ?", (submission["current_revision_id"],))
    run_review(conn, submission, revision)
    conn.execute("UPDATE submissions SET updated_at = ? WHERE id = ?", (now(), submission_id))
    _add_event(conn, submission_id, user["id"], "rereviewed", "The current revision was checked again against the approved sources.")


def apply_suggestion(conn, user: dict, finding_id: int, suggestion: str | None) -> int:
    finding = one(conn, "SELECT * FROM findings WHERE id = ?", (finding_id,))
    if not finding:
        raise WorkflowError(404, "That finding is not on this draft.")
    submission = _writable(conn, user, finding["submission_id"])
    if finding["revision_id"] != submission["current_revision_id"]:
        raise WorkflowError(409, "That finding belongs to an older revision. Open the current one.")
    if finding["suggestion_mode"] != "replace" or finding["replace_start"] is None:
        raise WorkflowError(409, "This finding is guidance. Edit the draft yourself, then mark it resolved.")
    revision = one(conn, "SELECT * FROM revisions WHERE id = ?", (finding["revision_id"],))
    body = revision["body"] or ""
    start, end = finding["replace_start"], finding["replace_end"]
    expected = finding["replace_text"] if finding["replace_text"] is not None else ""
    if start < 0 or end > len(body) or body[start:end] != expected:
        raise WorkflowError(409, "That suggestion no longer matches the draft. Run the review again.")
    replacement = finding["suggestion"] if suggestion is None else suggestion
    if len(replacement) > 4000:
        raise WorkflowError(422, "Keep the suggested wording under 4,000 characters.")
    new_body = body[:start] + replacement + body[end:]
    conn.execute(
        """
        UPDATE findings
        SET status = 'accepted', decision_note = ?, decision_by = ?, decided_at = ?
        WHERE id = ?
        """,
        ("Saved as a new revision.", user["id"], now(), finding_id),
    )
    fields = {
        "body": new_body,
        "alt_text": revision["alt_text"],
        "placement_notes": revision["placement_notes"],
        "decorative": revision["decorative"],
        "asset_id": revision["asset_id"],
        "file_path": revision["file_path"],
        "file_name": revision["file_name"],
        "mime": revision["mime"],
        "image": loads(revision["image_json"], None),
    }
    note = f"Applied a suggestion for “{finding['excerpt'][:80]}”."
    revision_id = _insert_revision(conn, user, submission["id"], fields, note)
    next_status = "draft" if submission["status"] == "rejected" else submission["status"]
    conn.execute(
        "UPDATE submissions SET current_revision_id = ?, updated_at = ?, status = ? WHERE id = ?",
        (revision_id, now(), next_status, submission["id"]),
    )
    submission = one(conn, "SELECT * FROM submissions WHERE id = ?", (submission["id"],))
    created = one(conn, "SELECT * FROM revisions WHERE id = ?", (revision_id,))
    run_review(conn, submission, created)
    _add_event(conn, submission["id"], user["id"], "applied_suggestion", note)
    return revision_id


def decide(conn, user: dict, finding_id: int, action: str, note: str) -> None:
    finding = one(conn, "SELECT * FROM findings WHERE id = ?", (finding_id,))
    if not finding:
        raise WorkflowError(404, "That finding is not on this draft.")
    submission = one(conn, "SELECT * FROM submissions WHERE id = ?", (finding["submission_id"],))
    if not submission or not can_view(user, submission):
        raise WorkflowError(404, "That draft is not in your queue.")
    note = (note or "").strip()
    if action == "reopen":
        if finding["status"] == "open":
            return
        if not staff(user) and submission["author_id"] != user["id"]:
            raise WorkflowError(403, "You cannot reopen this finding.")
        conn.execute(
            "UPDATE findings SET status = 'open', decision_note = '', decision_by = NULL, decided_at = NULL WHERE id = ?",
            (finding_id,),
        )
        _add_event(conn, submission["id"], user["id"], "reopened_finding", finding["excerpt"][:160])
        return
    if action not in {"dismiss", "resolve"}:
        raise WorkflowError(422, "Choose dismiss, resolve, or reopen.")
    if finding["status"] != "open":
        raise WorkflowError(409, "That finding already has a decision.")
    high = finding["severity"] in {"high", "critical"}
    if high and not staff(user):
        raise WorkflowError(403, "A reviewer has to decide high and critical findings. You can edit the draft or apply a suggestion.")
    if action == "dismiss" and len(note) < 8:
        raise WorkflowError(422, "A dismissal needs a short reason so the rule can be improved.")
    if action == "resolve" and high and len(note) < 8:
        raise WorkflowError(422, "Closing a high or critical finding needs a note that says why.")
    conn.execute(
        """
        UPDATE findings
        SET status = ?, decision_note = ?, decision_by = ?, decided_at = ?
        WHERE id = ?
        """,
        ("dismissed" if action == "dismiss" else "resolved", note, user["id"], now(), finding_id),
    )
    conn.execute("UPDATE submissions SET updated_at = ? WHERE id = ?", (now(), submission["id"]))
    _add_event(conn, submission["id"], user["id"], action, note or finding["excerpt"][:160])


def comment(conn, user: dict, submission_id: int, body: str, finding_id: int | None = None) -> None:
    submission = one(conn, "SELECT * FROM submissions WHERE id = ?", (submission_id,))
    if not submission or not can_view(user, submission):
        raise WorkflowError(404, "That draft is not in your queue.")
    body = (body or "").strip()
    if len(body) < 1 or len(body) > 4000:
        raise WorkflowError(422, "Write a comment before sending it.")
    if finding_id:
        finding = one(conn, "SELECT id FROM findings WHERE id = ? AND submission_id = ?", (finding_id, submission_id))
        if not finding:
            raise WorkflowError(404, "That finding is not on this draft.")
    conn.execute(
        "INSERT INTO comments (submission_id, finding_id, author_id, body, created_at) VALUES (?, ?, ?, ?, ?)",
        (submission_id, finding_id, user["id"], body, now()),
    )
    conn.execute("UPDATE submissions SET updated_at = ? WHERE id = ?", (now(), submission_id))
    _add_event(conn, submission_id, user["id"], "commented", body[:240])


def _blocking(conn, revision_id: int) -> list[dict]:
    return rows(
        conn,
        """
        SELECT id, severity, excerpt, category FROM findings
        WHERE revision_id = ? AND status = 'open' AND severity IN ('high', 'critical')
        ORDER BY id
        """,
        (revision_id,),
    )


def transition(conn, user: dict, submission_id: int, action: str, note: str = "", assignee_id: int | None = None, override_reason: str = "") -> None:
    submission = one(conn, "SELECT * FROM submissions WHERE id = ?", (submission_id,))
    if not submission or not can_view(user, submission):
        raise WorkflowError(404, "That draft is not in your queue.")
    note = (note or "").strip()
    override_reason = (override_reason or "").strip()
    author = submission["author_id"] == user["id"]
    previous = submission["status"]

    if action == "submit":
        if not author and not lead(user):
            raise WorkflowError(403, "Only the author or a manager can send this to review.")
        if previous not in {"draft", "changes_requested", "rejected"}:
            raise WorkflowError(409, "This draft is already with a reviewer or has a decision.")
        revision = one(conn, "SELECT review_json FROM revisions WHERE id = ?", (submission["current_revision_id"],))
        if not revision or not revision["review_json"]:
            raise WorkflowError(409, "Run a review before sending this to a person.")
        _set_status(conn, submission_id, "in_review")
        _add_event(conn, submission_id, user["id"], "submitted", note or "Sent for human review.", previous, "in_review")
        return

    if action == "request_changes":
        _require_reviewer(user, author)
        if previous != "in_review":
            raise WorkflowError(409, "Changes can be requested while the draft is in review.")
        if len(note) < 8:
            raise WorkflowError(422, "Tell the author what still needs a human decision.")
        _set_status(conn, submission_id, "changes_requested")
        _add_event(conn, submission_id, user["id"], "changes_requested", note, previous, "changes_requested")
        return

    if action == "reject":
        _require_reviewer(user, author)
        if previous != "in_review":
            raise WorkflowError(409, "Only a draft that is in review can be rejected.")
        if len(note) < 8:
            raise WorkflowError(422, "A rejection needs a reason the author can act on.")
        _set_status(conn, submission_id, "rejected")
        _add_event(conn, submission_id, user["id"], "rejected", note, previous, "rejected")
        return

    if action == "approve":
        _require_reviewer(user, author)
        if previous != "in_review":
            raise WorkflowError(409, "Only a draft that is in review can be approved.")
        blocking = _blocking(conn, submission["current_revision_id"])
        if blocking and len(override_reason) < 12:
            raise WorkflowError(
                409,
                "High or critical findings are still open. Decide them, or record an override reason if a person is accepting the risk.",
                {"blocking_ids": [item["id"] for item in blocking]},
            )
        detail = "Approved by a person who did not write the draft."
        if blocking:
            detail = f"Approved with an override. {override_reason}"
            audit(conn, user["id"], "approve_override", detail, "submission", submission_id)
        _set_status(conn, submission_id, "approved")
        _add_event(conn, submission_id, user["id"], "approved", detail, previous, "approved")
        return

    if action == "publish":
        if not lead(user) or author:
            raise WorkflowError(403, "A manager who did not write the draft publishes it.")
        if previous != "approved":
            raise WorkflowError(409, "Publish only happens after a person has approved the current version.")
        blocking = _blocking(conn, submission["current_revision_id"])
        if blocking:
            raise WorkflowError(409, "This approval is out of date because high findings are open again. Send it back to review.")
        _set_status(conn, submission_id, "published")
        detail = "A person published this approved version. Inkloom did not change the copy or call an external AI service."
        audit(conn, user["id"], "publish", detail, "submission", submission_id)
        _add_event(conn, submission_id, user["id"], "published", detail, previous, "published")
        return

    if action == "assign":
        if not lead(user):
            raise WorkflowError(403, "A manager assigns reviewers.")
        assignee = one(conn, "SELECT * FROM users WHERE id = ?", (assignee_id,))
        if not assignee or not staff(assignee):
            raise WorkflowError(422, "Assign a reviewer, manager, or admin.")
        conn.execute(
            "UPDATE submissions SET assignee_id = ?, updated_at = ? WHERE id = ?",
            (assignee_id, now(), submission_id),
        )
        _add_event(conn, submission_id, user["id"], "assigned", f"Assigned to {assignee['name']}.")
        return

    if action == "retract":
        if user["role"] != "admin":
            raise WorkflowError(403, "An admin pulls a published piece back.")
        if previous != "published":
            raise WorkflowError(409, "Only a published piece can be pulled back.")
        if len(note) < 8:
            raise WorkflowError(422, "Say why this published piece is returning to draft.")
        _set_status(conn, submission_id, "draft")
        _add_event(conn, submission_id, user["id"], "retracted", note, previous, "draft")
        return

    raise WorkflowError(422, "That action is not part of the workflow.")


def _require_reviewer(user: dict, author: bool) -> None:
    if not staff(user) or author:
        raise WorkflowError(403, "A reviewer who did not write the draft has to make this decision.")


def _set_status(conn, submission_id: int, status: str) -> None:
    conn.execute(
        "UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?",
        (status, now(), submission_id),
    )


def list_submissions(conn, user: dict, status: str | None, query: str | None, mine: bool, assigned: bool) -> dict:
    where = []
    params: list = []
    if not staff(user):
        where.append("(s.author_id = ? OR s.assignee_id = ?)")
        params.extend([user["id"], user["id"]])
    if mine:
        where.append("s.author_id = ?")
        params.append(user["id"])
    if assigned:
        where.append("s.assignee_id = ?")
        params.append(user["id"])
    if status:
        if status not in STATUSES:
            raise WorkflowError(422, "Unknown status.")
        where.append("s.status = ?")
        params.append(status)
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("(s.title LIKE ? ESCAPE '\\' OR r.body LIKE ? ESCAPE '\\')")
        like = f"%{escaped}%"
        params.extend([like, like])
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    items = rows(
        conn,
        f"""
        SELECT s.*, u.name AS author_name, u.affiliation AS author_affiliation, u.role AS author_role,
               a.name AS assignee_name, a.role AS assignee_role,
               (SELECT COUNT(*) FROM revisions rv WHERE rv.submission_id = s.id) AS revision_count
        FROM submissions s
        JOIN users u ON u.id = s.author_id
        LEFT JOIN users a ON a.id = s.assignee_id
        JOIN revisions r ON r.id = s.current_revision_id
        {clause}
        ORDER BY s.updated_at DESC
        LIMIT 100
        """,
        tuple(params),
    )
    revision_ids = [item["current_revision_id"] for item in items]
    open_map: dict[int, list[str]] = {}
    if revision_ids:
        marks = ",".join("?" * len(revision_ids))
        for row in rows(
            conn,
            f"SELECT revision_id, severity FROM findings WHERE status = 'open' AND revision_id IN ({marks})",
            tuple(revision_ids),
        ):
            open_map.setdefault(row["revision_id"], []).append(row["severity"])
    shaped = []
    for item in items:
        severities = open_map.get(item["current_revision_id"], [])
        highest = max(severities, key=lambda value: SEVERITY_RANK[value]) if severities else None
        shaped.append(_card(item, len(severities), highest))
    count_where = []
    count_params: list = []
    if not staff(user):
        count_where.append("(author_id = ? OR assignee_id = ?)")
        count_params.extend([user["id"], user["id"]])
    count_clause = f"WHERE {' AND '.join(count_where)}" if count_where else ""
    counts = {name: 0 for name in STATUSES}
    for row in rows(conn, f"SELECT status, COUNT(*) AS c FROM submissions {count_clause} GROUP BY status", tuple(count_params)):
        counts[row["status"]] = row["c"]
    return {"items": shaped, "counts": counts}


def _card(item: dict, open_findings: int, highest: str | None) -> dict:
    return {
        "id": item["id"],
        "title": item["title"],
        "format": item["format"],
        "channel": item["channel"],
        "purpose": item["purpose"],
        "origin": item["origin"],
        "status": item["status"],
        "updated_at": item["updated_at"],
        "created_at": item["created_at"],
        "revision_count": item["revision_count"],
        "open_findings": open_findings,
        "highest_severity": highest,
        "author": {
            "id": item["author_id"],
            "name": item["author_name"],
            "affiliation": item["author_affiliation"],
            "role": item["author_role"],
        },
        "assignee": None
        if not item["assignee_id"]
        else {"id": item["assignee_id"], "name": item["assignee_name"], "role": item["assignee_role"]},
    }


def redact_finding(row: dict, user: dict) -> dict:
    confidential = bool(row["confidential_source"])
    hide = confidential and user["role"] == "creator"
    return {
        "id": row["id"],
        "revision_id": row["revision_id"],
        "category": row["category"],
        "severity": row["severity"],
        "status": row["status"],
        "excerpt": row["excerpt"],
        "explanation": row["explanation"],
        "suggestion": row["suggestion"],
        "suggestion_mode": row["suggestion_mode"],
        "replaces": row["replaces"],
        "source_type": row["source_type"],
        "source_id": None if hide else row["source_id"],
        "source_label": "Confidential approved source" if hide else row["source_label"],
        "source_excerpt": "" if hide else row["source_excerpt"],
        "confidential_source": confidential,
        "pattern_key": row["pattern_key"],
        "start_pos": row["start_pos"],
        "end_pos": row["end_pos"],
        "decision_note": row["decision_note"],
        "decision_by": row["decision_by"],
        "created_at": row["created_at"],
        "decided_at": row["decided_at"],
    }


def abilities(user: dict, submission: dict) -> dict:
    author = submission["author_id"] == user["id"]
    status = submission["status"]
    return {
        "edit": status in {"draft", "changes_requested", "rejected"} and (author or lead(user)),
        "submit": status in {"draft", "changes_requested", "rejected"} and (author or lead(user)),
        "approve": status == "in_review" and staff(user) and not author,
        "request_changes": status == "in_review" and staff(user) and not author,
        "reject": status == "in_review" and staff(user) and not author,
        "publish": status == "approved" and lead(user) and not author,
        "comment": True,
        "apply": status in {"draft", "changes_requested", "rejected"} and (author or lead(user)),
        "decide_high": staff(user),
        "assign": lead(user),
        "retract": status == "published" and user["role"] == "admin",
        "rereview": status not in {"approved", "published"} and (staff(user) or status != "in_review"),
    }


def submission_detail(conn, user: dict, submission_id: int, revision_id: int | None = None) -> dict | None:
    submission = one(
        conn,
        """
        SELECT s.*, u.name AS author_name, u.email AS author_email, u.affiliation AS author_affiliation, u.role AS author_role,
               a.name AS assignee_name, a.role AS assignee_role, a.email AS assignee_email
        FROM submissions s
        JOIN users u ON u.id = s.author_id
        LEFT JOIN users a ON a.id = s.assignee_id
        WHERE s.id = ?
        """,
        (submission_id,),
    )
    if not submission or not can_view(user, submission):
        return None
    revisions = rows(
        conn,
        """
        SELECT r.*, u.name AS author_name
        FROM revisions r JOIN users u ON u.id = r.created_by
        WHERE r.submission_id = ? ORDER BY r.id
        """,
        (submission_id,),
    )
    selected = revision_id or submission["current_revision_id"]
    current = next((item for item in revisions if item["id"] == selected), None)
    if not current:
        return None
    findings = [
        redact_finding(row, user)
        for row in rows(conn, "SELECT * FROM findings WHERE revision_id = ? ORDER BY id", (current["id"],))
    ]
    if any(item["confidential_source"] and user["role"] != "creator" for item in findings):
        audit(
            conn,
            user["id"],
            "view_confidential",
            f"Opened submission {submission_id}, which cites confidential sources.",
            "submission",
            submission_id,
        )
    comments = rows(
        conn,
        """
        SELECT c.*, u.name AS author_name, u.role AS author_role
        FROM comments c JOIN users u ON u.id = c.author_id
        WHERE c.submission_id = ? ORDER BY c.id
        """,
        (submission_id,),
    )
    events = rows(
        conn,
        """
        SELECT e.*, u.name AS actor_name, u.role AS actor_role
        FROM events e LEFT JOIN users u ON u.id = e.actor_id
        WHERE e.submission_id = ? ORDER BY e.id
        """,
        (submission_id,),
    )
    previous = None
    for item in revisions:
        if item["id"] == current["id"]:
            break
        previous = item
    diff = word_diff(previous["body"], current["body"]) if previous else []
    open_high = [item["id"] for item in findings if item["status"] == "open" and item["severity"] in {"high", "critical"}]
    return {
        "submission": _card(
            {**submission, "revision_count": len(revisions)},
            sum(1 for item in findings if item["status"] == "open"),
            _highest(findings),
        ),
        "revision": _revision_public(current),
        "revisions": [_revision_public(item) for item in revisions],
        "findings": findings,
        "comments": [
            {
                "id": item["id"],
                "finding_id": item["finding_id"],
                "body": item["body"],
                "created_at": item["created_at"],
                "author": {"id": item["author_id"], "name": item["author_name"], "role": item["author_role"]},
            }
            for item in comments
        ],
        "events": [
            {
                "id": item["id"],
                "action": item["action"],
                "detail": item["detail"],
                "from_status": item["from_status"],
                "to_status": item["to_status"],
                "created_at": item["created_at"],
                "actor": None if not item["actor_id"] else {"id": item["actor_id"], "name": item["actor_name"], "role": item["actor_role"]},
            }
            for item in events
        ],
        "diff": diff,
        "diff_from": previous["id"] if previous else None,
        "can": abilities(user, submission),
        "blocking_ids": open_high,
        "review": loads(current.get("review_json"), {}),
    }


def _highest(findings: list[dict]) -> str | None:
    open_items = [item["severity"] for item in findings if item["status"] == "open"]
    if not open_items:
        return None
    return max(open_items, key=lambda value: SEVERITY_RANK[value])


def _revision_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "body": row["body"],
        "alt_text": row["alt_text"],
        "placement_notes": row["placement_notes"],
        "decorative": bool(row["decorative"]),
        "asset_id": row["asset_id"],
        "file_name": row["file_name"],
        "mime": row["mime"],
        "has_file": bool(row["file_path"]),
        "image": loads(row.get("image_json"), None),
        "note": row["note"],
        "created_at": row["created_at"],
        "author_name": row.get("author_name"),
        "file_url": f"/api/revisions/{row['id']}/file" if row["file_path"] else None,
    }


def word_diff(before: str, after: str) -> list[dict]:
    left = re.findall(r"\s+|\S+", before or "")
    right = re.findall(r"\s+|\S+", after or "")
    matcher = difflib.SequenceMatcher(a=left, b=right)
    chunks = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            chunks.append({"op": "equal", "text": "".join(left[i1:i2])})
        elif op == "delete":
            chunks.append({"op": "delete", "text": "".join(left[i1:i2])})
        elif op == "insert":
            chunks.append({"op": "insert", "text": "".join(right[j1:j2])})
        else:
            chunks.append({"op": "delete", "text": "".join(left[i1:i2])})
            chunks.append({"op": "insert", "text": "".join(right[j1:j2])})
    return chunks


def insights(conn, user: dict, days: int) -> dict:
    days = min(max(days, 7), 365)
    since = shift(days=-days)
    author_only = not staff(user)
    author_clause = "AND s.author_id = ?" if author_only else ""
    params: tuple = (since, user["id"]) if author_only else (since,)
    grouped = rows(
        conn,
        f"""
        SELECT f.pattern_key AS pattern_key, COUNT(*) AS c
        FROM findings f
        JOIN submissions s ON s.id = f.submission_id
        WHERE f.created_at >= ? {author_clause}
        GROUP BY f.pattern_key
        HAVING COUNT(*) >= 2
        ORDER BY c DESC
        LIMIT 12
        """,
        params,
    )
    # SQLite allows bare columns in GROUP BY queries. Pull a stable example explicitly.
    recurring = []
    for row in grouped:
        example = one(
            conn,
            f"""
            SELECT f.excerpt, f.source_label, f.confidential_source, f.category
            FROM findings f JOIN submissions s ON s.id = f.submission_id
            WHERE f.pattern_key = ? AND f.created_at >= ? {author_clause}
            ORDER BY f.id DESC LIMIT 1
            """,
            (row["pattern_key"], since, user["id"]) if author_only else (row["pattern_key"], since),
        )
        hide = bool(example["confidential_source"]) and user["role"] == "creator"
        recurring.append(
            {
                "pattern_key": row["pattern_key"],
                "category": example["category"],
                "label": "Confidential approved source" if hide else example["source_label"],
                "excerpt": example["excerpt"],
                "count": row["c"],
            }
        )
    unclear_rows = rows(
        conn,
        f"""
        SELECT f.source_id,
               SUM(CASE WHEN f.status = 'dismissed' THEN 1 ELSE 0 END) AS dismissed,
               COUNT(*) AS total
        FROM findings f
        JOIN submissions s ON s.id = f.submission_id
        WHERE f.source_type = 'guideline' AND f.created_at >= ? {author_clause}
        GROUP BY f.source_id
        HAVING total >= 4 AND dismissed * 1.0 / total >= 0.6
        ORDER BY dismissed DESC
        """,
        params,
    )
    unclear = []
    for row in unclear_rows:
        guide = one(conn, "SELECT * FROM guidelines WHERE id = ?", (row["source_id"],))
        if not guide:
            continue
        if guide["confidential"] and user["role"] == "creator":
            continue
        unclear.append(
            {
                "id": guide["id"],
                "title": guide["title"],
                "dismissed": row["dismissed"],
                "total": row["total"],
                "dismiss_rate": round(row["dismissed"] / row["total"], 2),
                "body": guide["body"],
            }
        )
    by_category = rows(
        conn,
        f"""
        SELECT f.category AS category, COUNT(*) AS c
        FROM findings f JOIN submissions s ON s.id = f.submission_id
        WHERE f.created_at >= ? {author_clause}
        GROUP BY f.category ORDER BY c DESC
        """,
        params,
    )
    by_channel = rows(
        conn,
        f"""
        SELECT s.channel AS channel, COUNT(*) AS c
        FROM findings f JOIN submissions s ON s.id = f.submission_id
        WHERE f.created_at >= ? {author_clause}
        GROUP BY s.channel ORDER BY c DESC
        """,
        params,
    )
    by_origin = rows(
        conn,
        f"""
        SELECT s.origin AS origin, COUNT(DISTINCT s.id) AS submissions, COUNT(f.id) AS findings
        FROM submissions s LEFT JOIN findings f ON f.submission_id = s.id AND f.created_at >= ?
        WHERE s.created_at >= ? {('AND s.author_id = ?' if author_only else '')}
        GROUP BY s.origin
        """,
        (since, since, user["id"]) if author_only else (since, since),
    )
    decisions = rows(
        conn,
        f"""
        SELECT f.status AS status, COUNT(*) AS c
        FROM findings f JOIN submissions s ON s.id = f.submission_id
        WHERE f.created_at >= ? {author_clause}
        GROUP BY f.status
        """,
        params,
    )
    gaps = []
    if staff(user):
        for guide in rows(conn, "SELECT * FROM guidelines WHERE status = 'approved'"):
            missing = []
            if not guide["good_example"] or not guide["bad_example"]:
                missing.append("missing a good or bad example")
            if guide["match_type"] in {"keywords", "regex"} and guide["match_value"].strip() in {"", "[]"}:
                missing.append("has no match pattern, so reviews never use it")
            if missing:
                gaps.append({"id": guide["id"], "title": guide["title"], "reasons": missing})
        draft_count = one(conn, "SELECT COUNT(*) AS c FROM guidelines WHERE status = 'draft'")["c"]
    else:
        draft_count = 0
    authors = []
    if staff(user):
        repeated = rows(
            conn,
            """
            SELECT u.name AS name, u.affiliation AS affiliation, f.pattern_key, f.source_label, COUNT(*) AS c
            FROM findings f
            JOIN submissions s ON s.id = f.submission_id
            JOIN users u ON u.id = s.author_id
            WHERE f.created_at >= ?
            GROUP BY u.id, f.pattern_key
            HAVING c >= 2
            ORDER BY c DESC
            LIMIT 8
            """,
            (since,),
        )
        authors = [
            {
                "name": row["name"],
                "affiliation": row["affiliation"],
                "label": row["source_label"],
                "count": row["c"],
            }
            for row in repeated
        ]
    summary = _summaries(recurring, unclear, by_category, gaps, draft_count, author_only)
    return {
        "window_days": days,
        "since": since,
        "scope": "yours" if author_only else "workspace",
        "summary": summary,
        "recurring": recurring,
        "unclear_guidelines": unclear,
        "by_category": [{"category": row["category"], "count": row["c"]} for row in by_category],
        "by_channel": [{"channel": row["channel"], "count": row["c"]} for row in by_channel],
        "by_origin": [dict(row) for row in by_origin],
        "decisions": {row["status"]: row["c"] for row in decisions},
        "gaps": gaps,
        "draft_guidelines": draft_count,
        "repeated_by_author": authors,
    }


def _summaries(recurring, unclear, by_category, gaps, draft_count, author_only) -> list[str]:
    lines = []
    if recurring:
        top = recurring[0]
        whose = "Your drafts repeat" if author_only else "The most repeated flag is"
        lines.append(f"{whose} “{top['excerpt']}” ({top['count']} times), from {top['label']}.")
    elif by_category:
        lines.append(f"Most flags in this window are {by_category[0]['category'].replace('_', ' ')} issues.")
    else:
        lines.append("No findings in this window yet. New reviews will collect here.")
    if unclear:
        rule = unclear[0]
        lines.append(
            f"“{rule['title']}” was dismissed {rule['dismissed']} of {rule['total']} times. "
            "The wording may be unclear, so people are learning to ignore it."
        )
    if gaps:
        count = len(gaps)
        noun = "guideline lacks" if count == 1 else "guidelines lack"
        lines.append(f"{count} approved {noun} examples or a match pattern, so reviewers cannot tell what “good” means.")
    if draft_count:
        lines.append(f"{draft_count} guideline{'s are' if draft_count != 1 else ' is'} still a draft and {'are' if draft_count != 1 else 'is'} not used in reviews.")
    if not lines:
        lines.append("Reviews will summarize repeated mistakes once a few drafts have been checked.")
    return lines
