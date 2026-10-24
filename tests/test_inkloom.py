"""Workflow and review-engine tests for Inkloom."""

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INKLOOM_DB", str(tmp_path / "inkloom.db"))
    monkeypatch.setenv("INKLOOM_UPLOADS", str(tmp_path / "uploads"))
    from inkloom.main import app

    with TestClient(app) as test_client:
        yield test_client


def sign_in(client, user_id="usr_maya"):
    response = client.post("/api/session", json={"user_id": user_id})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    response = client.get("/health")
    assert response.json()["service"] == "inkloom"
    assert response.headers["x-inkloom-disclosure"] == "local-rules-engine; no-external-ai"


def test_bad_caption_is_explained_and_not_auto_changed(client):
    headers = sign_in(client, "usr_maya")
    review = client.get("/api/reviews/sub_ig_spring", headers=headers)
    assert review.status_code == 200, review.text
    body = review.json()
    text = body["versions"][0]["body"]
    assert "game-changing" in text
    rules = {item["rule_id"] for item in body["findings"] if item["status"] == "open"}
    assert "claim.unsupported" in rules
    assert "fact.mismatch" in rules
    assert "term.vocabulary" in rules
    assert "a11y.link" in rules
    assert "tone.lexicon" in rules
    fact = next(item for item in body["findings"] if item["rule_id"] == "fact.mismatch")
    assert "48,000" in fact["suggestion"]
    assert fact["source_label"]
    assert body["submission"]["status"] == "in_review"
    assert text.startswith("Grove is FINALLY")


def test_approved_numbers_do_not_false_flag(client):
    headers = sign_in(client, "usr_priya")
    review = client.get("/api/reviews/sub_practitioner", headers=headers)
    assert review.status_code == 200, review.text
    payload = review.json()
    open_findings = [item for item in payload["findings"] if item["status"] == "open"]
    assert open_findings == []
    assert payload["submission"]["status"] == "approved"


def test_creator_cannot_approve_or_read_embargo(client):
    headers = sign_in(client, "usr_maya")
    denied = client.post(
        "/api/reviews/sub_ig_spring/decision",
        headers=headers,
        json={"action": "approve", "note": "Shipping it anyway today."},
    )
    assert denied.status_code == 403
    review = client.get("/api/reviews/sub_embargo_note", headers=headers)
    embargo = next(item for item in review.json()["findings"] if item["rule_id"] == "fact.embargo")
    assert embargo["source_restricted"] is True
    assert embargo["source_body"] is None
    assert "LG-SR-26" not in embargo["explanation"]
    library = client.get("/api/library", headers=headers).json()
    secret = next(item for item in library["guidelines"] if item["code"] == "CLM-02")
    assert secret["body"] is None
    joined = json.dumps(library)
    assert "LG-SR-26" not in joined


def test_reviewer_sees_embargo_source_and_it_is_audited(client):
    headers = sign_in(client, "usr_alex")
    review = client.get("/api/reviews/sub_embargo_note", headers=headers)
    embargo = next(item for item in review.json()["findings"] if item["rule_id"] == "fact.embargo")
    assert embargo["source_restricted"] is False
    assert "62%" in embargo["explanation"]
    audit = client.get("/api/audit", headers=sign_in(client, "usr_jordan")).json()
    assert any(entry["action"] == "confidential.read" and entry["actor_name"] == "Alex Okonkwo" for entry in audit["entries"])


def test_critical_blocks_approval_until_a_person_dismisses(client):
    reviewer = sign_in(client, "usr_alex")
    blocked = client.post(
        "/api/reviews/sub_letter_april/decision",
        headers=reviewer,
        json={"action": "approve", "note": "Looks close enough to me."},
    )
    assert blocked.status_code == 400
    findings = client.get("/api/reviews/sub_letter_april", headers=reviewer).json()["findings"]
    critical = next(item for item in findings if item["status"] == "open" and item["severity"] == "critical")
    dismissed = client.post(
        f"/api/reviews/sub_letter_april/findings/{critical['id']}/dismiss",
        headers=reviewer,
        json={"reason": "Holding this open would be wrong; recording why we keep it."},
    )
    assert dismissed.status_code == 200
    still = client.post(
        "/api/reviews/sub_letter_april/decision",
        headers=reviewer,
        json={"action": "approve", "note": "Trying again after one dismissal."},
    )
    assert still.status_code == 400


def test_apply_suggestion_keeps_history_and_purpose(client):
    creator = sign_in(client, "usr_maya")
    before = client.get("/api/reviews/sub_letter_april", headers=creator).json()
    original = before["versions"][-1]["body"]
    finding = next(item for item in before["findings"] if item["excerpt"].lower() == "users" and item["status"] == "open")
    applied = client.post(
        f"/api/reviews/sub_letter_april/findings/{finding['id']}/accept",
        headers=creator,
    )
    assert applied.status_code == 200, applied.text
    after = applied.json()
    assert len(after["versions"]) == 2
    assert "users" not in after["versions"][-1]["body"].lower()
    assert "members" in after["versions"][-1]["body"].lower()
    assert original in after["versions"][0]["body"]
    assert after["submission"]["purpose"].startswith("Tell members")
    reviewer = sign_in(client, "usr_priya")
    instagram = client.get("/api/reviews/sub_ig_spring", headers=reviewer).json()
    swappable = next(
        item for item in instagram["findings"] if item["status"] == "open" and item["apply_mode"] == "replace"
    )
    cannot = client.post(
        f"/api/reviews/sub_ig_spring/findings/{swappable['id']}/accept",
        headers=reviewer,
    )
    assert cannot.status_code == 403


def test_publish_requires_manager_after_approval(client):
    creator = sign_in(client, "usr_leo")
    reviewer = sign_in(client, "usr_priya")
    manager = sign_in(client, "usr_jordan")
    created = client.post(
        "/api/reviews",
        headers=creator,
        json={
            "title": "Quiet note",
            "format": "email",
            "channel": "Lifecycle email",
            "purpose": "Remind members that the evening ritual is still $18 a month",
            "submit": True,
            "body": "Members can keep the evening ritual. Membership stays at $18/month.",
        },
    )
    assert created.status_code == 200, created.text
    submission_id = created.json()["submission"]["id"]
    assert created.json()["submission"]["status"] == "in_review"
    too_soon = client.post(
        f"/api/reviews/{submission_id}/publish",
        headers=manager,
        json={"note": "Publishing without a review."},
    )
    assert too_soon.status_code == 400
    approved = client.post(
        f"/api/reviews/{submission_id}/decision",
        headers=reviewer,
        json={"action": "approve", "note": "Facts and voice match the sheet."},
    )
    assert approved.status_code == 200, approved.text
    creator_publish = client.post(
        f"/api/reviews/{submission_id}/publish",
        headers=creator,
        json={"note": "I'll put it live myself."},
    )
    assert creator_publish.status_code == 403
    published = client.post(
        f"/api/reviews/{submission_id}/publish",
        headers=manager,
        json={"note": "Approved copy can go out."},
    )
    assert published.status_code == 200, published.text
    assert published.json()["submission"]["status"] == "published"


def test_creator_cannot_see_another_creators_draft(client):
    maya = sign_in(client)
    hidden = client.get("/api/reviews/sub_autumn_notes", headers=sign_in(client, "usr_leo"))
    assert hidden.status_code == 403
    visible = client.get("/api/reviews/sub_autumn_notes", headers=maya)
    assert visible.status_code == 200
    queue = client.get("/api/reviews", headers=sign_in(client, "usr_priya")).json()["reviews"]
    assert all(item["id"] != "sub_autumn_notes" for item in queue)


def test_new_term_is_picked_up_on_rerun(client):
    manager = sign_in(client, "usr_jordan")
    creator = sign_in(client, "usr_leo")
    created = client.post(
        "/api/reviews",
        headers=creator,
        json={
            "title": "Partner line",
            "format": "ad",
            "purpose": "Describe how practitioners and members work together",
            "submit": False,
            "body": "Practitioners and members build synergy in the evening ritual.",
        },
    )
    assert created.status_code == 200, created.text
    submission_id = created.json()["submission"]["id"]
    assert all(item["excerpt"].lower() != "synergy" for item in created.json()["findings"])
    added = client.post(
        "/api/library/terms",
        headers=manager,
        json={
            "phrase": "synergy",
            "replacement": "a shared practice",
            "kind": "avoid",
            "severity": "warning",
            "rationale": "Name the practice instead of using a vague business word.",
            "guideline_code": "TONE-02",
        },
    )
    assert added.status_code == 200, added.text
    rerun = client.post(f"/api/reviews/{submission_id}/rerun", headers=creator)
    assert rerun.status_code == 200, rerun.text
    assert any(item["excerpt"].lower() == "synergy" and item["status"] == "open" for item in rerun.json()["findings"])


def test_image_alt_and_palette(client):
    headers = sign_in(client, "usr_priya")
    graphic = client.get("/api/reviews/sub_launch_graphic", headers=headers).json()
    rules = {item["rule_id"] for item in graphic["findings"] if item["status"] == "open"}
    assert "a11y.alt" in rules
    assert "visual.image" in rules
    logo = client.get("/api/reviews/sub_logo_master", headers=headers).json()
    assert [item for item in logo["findings"] if item["status"] == "open"] == []
    image = client.get("/api/reviews/sub_logo_master/image", headers=headers)
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/")


def test_upload_and_import_and_insights(client):
    creator = sign_in(client, "usr_maya")
    upload = client.post(
        "/api/reviews/upload",
        headers=creator,
        data={
            "title": "Notes file",
            "format": "document",
            "purpose": "Share the public study wording with the blog desk",
            "submit": "true",
        },
        files={"file": ("notes.md", b"Members reported an 18% improvement in sleep regularity.", "text/markdown")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["submission"]["status"] == "in_review"
    manager = sign_in(client, "usr_jordan")
    imported = client.post(
        "/api/library/import",
        headers=manager,
        files={
            "file": (
                "bundle.json",
                json.dumps(
                    {
                        "guidelines": [
                            {
                                "code": "VOICE-09",
                                "title": "Partner tone",
                                "category": "tone",
                                "body": "Partner notes stay as calm as member-facing copy and cite a guideline.",
                                "confidential": False,
                            }
                        ]
                    }
                ),
                "application/json",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    assert any(item["code"] == "VOICE-09" for item in imported.json()["guidelines"])
    denied = client.post(
        "/api/library/guidelines",
        headers=creator,
        json={
            "code": "VOICE-10",
            "title": "Nope",
            "category": "tone",
            "body": "Creators do not rewrite the brand system from a draft.",
        },
    )
    assert denied.status_code == 403
    report = client.get("/api/insights", headers=manager).json()
    assert report["totals"]["findings"] > 0
    assert any(item["category"] == "claims" for item in report["by_category"])
    assert any(item["code"] == "MSG-02" for item in report["unclear_guidelines"])
    creator_report = client.get("/api/insights", headers=creator).json()
    assert creator_report["repeated_by_author"] == []


def test_pdf_rejected_and_comment_roundtrip(client):
    headers = sign_in(client, "usr_maya")
    rejected = client.post(
        "/api/reviews/upload",
        headers=headers,
        data={"title": "Deck", "format": "document", "purpose": "Share the launch story with the agency"},
        files={"file": ("deck.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert rejected.status_code == 400
    comment = client.post(
        "/api/reviews/sub_homepage/comments",
        headers=headers,
        json={"body": "I can keep the invitation and drop the weight-loss line."},
    )
    assert comment.status_code == 200
    assert any("weight-loss" in item["body"] for item in comment.json()["comments"])


def test_engine_negation_and_contrast_helpers():
    from inkloom.engine import contrast_ratio

    assert contrast_ratio((27, 67, 50), (244, 241, 234)) >= 4.5
    assert contrast_ratio((255, 46, 147), (244, 241, 234)) < 4.5
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, "PNG")
    assert buffer.getvalue().startswith(b"\x89PNG")
