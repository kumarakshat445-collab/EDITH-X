import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from inkloom.main import app
from inkloom.samples import CAREFUL_SOCIAL, GOOD_FAQ, LAUNCH, WEB_PAGE

H = {"X-Inkloom-Request": "1"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password}, headers=H)
    assert response.status_code == 200, response.text
    return response.json()["user"]


def auth(client, email, password):
    login(client, email, password)
    return client


def test_health(client):
    assert client.get("/health").json()["service"] == "inkloom"


def test_disclosure_names_no_external_ai(client):
    body = client.get("/api/disclosure").json()
    assert body["external_services"] == []
    assert "does not send" in body["ai_disclosure"].lower() or "does not send" in body["ai_disclosure"]


def test_login_requires_header(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "maya.chen@vela.example", "password": "draft-well"},
    )
    assert response.status_code == 403


def test_good_faq_has_no_high_findings(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    response = client.post(
        "/api/submissions",
        json={
            "title": "Clear FAQ",
            "format": "web",
            "channel": "Product FAQ",
            "purpose": "Explain the SPF and serum facts on the product page",
            "origin": "employee",
            "body": GOOD_FAQ,
        },
        headers=H,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["submission"]["status"] == "draft"
    highs = [item for item in payload["findings"] if item["severity"] in {"high", "critical"}]
    assert highs == []
    assert payload["review"]["external_services"] == []


def test_careful_social_is_usable(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    response = client.post(
        "/api/submissions",
        json={
            "title": "Careful caption",
            "format": "social",
            "channel": "Instagram",
            "purpose": "Announce Vela Bare Serum to people who already buy it",
            "body": CAREFUL_SOCIAL,
        },
        headers=H,
    )
    assert response.status_code == 200, response.text
    blocked = [item["category"] for item in response.json()["findings"] if item["severity"] in {"high", "critical"}]
    assert blocked == []


def test_launch_explains_claims_facts_terms_and_tone(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    response = client.post(
        "/api/submissions",
        json={
            "title": "Problem caption",
            "format": "social",
            "channel": "Instagram",
            "purpose": "Announce Vela Bare Serum to people who already buy it",
            "body": LAUNCH,
        },
        headers=H,
    )
    assert response.status_code == 200, response.text
    findings = response.json()["findings"]
    categories = {item["category"] for item in findings}
    assert {"claims", "facts", "terminology", "tone", "messaging", "visual"} <= categories
    fact = next(item for item in findings if item["category"] == "facts" and "SPF 50" in item["excerpt"])
    assert "SPF 30" in fact["explanation"]
    assert fact["source_label"] == "Daily Mineral SPF"
    assert fact["suggestion_mode"] == "replace"
    assert "approved" in fact["explanation"].lower() or "contradicts" in fact["explanation"].lower()


def test_web_accessibility(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    response = client.post(
        "/api/submissions",
        json={
            "title": "Landing",
            "format": "web",
            "channel": "Website",
            "purpose": "Send readers to the spring offer",
            "origin": "agency",
            "body": WEB_PAGE,
        },
        headers=H,
    )
    keys = {item["pattern_key"] for item in response.json()["findings"]}
    assert "a11y:img-alt" in keys
    assert "a11y:contrast" in keys
    assert "a11y:click-here" in keys
    assert "a11y:font-size" in keys
    assert "a11y:color-only" in keys


def test_confidential_fact_is_hidden_from_creators(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    listing = client.get("/api/facts", headers=H).json()["items"]
    assert all("AX-17" not in item["statement"] for item in listing)
    assert all(not item["confidential"] for item in listing)
    created = client.post(
        "/api/submissions",
        json={
            "title": "Leak check",
            "format": "document",
            "channel": "Blog",
            "purpose": "Invite readers to the studio",
            "origin": "ai_tool",
            "body": "Our new Amberline oil uses AX-17.",
        },
        headers=H,
    )
    finding = next(item for item in created.json()["findings"] if item["confidential_source"])
    assert finding["source_id"] is None
    assert finding["source_excerpt"] == ""
    assert "supplier" not in finding["explanation"].lower()
    assert finding["source_label"] == "Confidential approved source"
    client.post("/api/auth/logout", headers=H)
    auth(client, "jules.okafor@vela.example", "review-well")
    hidden = client.get("/api/facts", headers=H).json()["items"]
    secret = next(item for item in hidden if item["confidential"])
    opened = client.get(f"/api/facts/{secret['id']}", headers=H)
    assert opened.status_code == 200
    assert "AX-17" in opened.json()["statement"]
    audit = client.get("/api/audit", headers=H)
    assert audit.status_code == 403
    client.post("/api/auth/logout", headers=H)
    auth(client, "samira.dal@vela.example", "manage-well")
    audit = client.get("/api/audit", headers=H)
    assert audit.status_code == 200
    assert any(item["action"] == "view_confidential" for item in audit.json()["items"])


def test_creator_cannot_approve_or_publish_own_work(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    created = client.post(
        "/api/submissions",
        json={
            "title": "Own work",
            "format": "web",
            "channel": "Product FAQ",
            "purpose": "Explain the SPF and serum facts on the product page",
            "body": GOOD_FAQ,
        },
        headers=H,
    ).json()
    submission_id = created["submission"]["id"]
    submitted = client.post(f"/api/submissions/{submission_id}/transition", json={"action": "submit"}, headers=H)
    assert submitted.status_code == 200
    assert submitted.json()["submission"]["status"] == "in_review"
    blocked = client.post(f"/api/submissions/{submission_id}/transition", json={"action": "approve"}, headers=H)
    assert blocked.status_code == 403
    client.post("/api/auth/logout", headers=H)
    auth(client, "jules.okafor@vela.example", "review-well")
    approved = client.post(f"/api/submissions/{submission_id}/transition", json={"action": "approve"}, headers=H)
    assert approved.status_code == 200, approved.text
    assert approved.json()["submission"]["status"] == "approved"
    publisher = client.post(f"/api/submissions/{submission_id}/transition", json={"action": "publish"}, headers=H)
    assert publisher.status_code == 403
    client.post("/api/auth/logout", headers=H)
    auth(client, "samira.dal@vela.example", "manage-well")
    published = client.post(f"/api/submissions/{submission_id}/transition", json={"action": "publish"}, headers=H)
    assert published.status_code == 200, published.text
    assert published.json()["submission"]["status"] == "published"
    assert any(item["action"] == "published" for item in published.json()["events"])


def test_critical_blocks_approval_until_a_person_overrides(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    created = client.post(
        "/api/submissions",
        json={
            "title": "Needs a person",
            "format": "social",
            "channel": "Instagram",
            "purpose": "Announce Vela Bare Serum to people who already buy it",
            "body": "This miracle serum is guaranteed.",
        },
        headers=H,
    ).json()
    submission_id = created["submission"]["id"]
    assert created["blocking_ids"]
    client.post(f"/api/submissions/{submission_id}/transition", json={"action": "submit"}, headers=H)
    client.post("/api/auth/logout", headers=H)
    auth(client, "jules.okafor@vela.example", "review-well")
    denied = client.post(f"/api/submissions/{submission_id}/transition", json={"action": "approve"}, headers=H)
    assert denied.status_code == 409
    assert denied.json()["blocking_ids"]
    allowed = client.post(
        f"/api/submissions/{submission_id}/transition",
        json={"action": "approve", "override_reason": "Legal confirmed this quote stays in a complaint response."},
        headers=H,
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["submission"]["status"] == "approved"


def test_apply_suggestion_creates_revision_and_does_not_publish(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    created = client.post(
        "/api/submissions",
        json={
            "title": "Term fix",
            "format": "email",
            "channel": "Retailer email",
            "purpose": "Tell retailers the serum is back in the catalogue",
            "body": "The unscented Vela Bare Serum is in stock. It uses 5% niacinamide to support the skin barrier.",
        },
        headers=H,
    ).json()
    finding = next(item for item in created["findings"] if item["suggestion_mode"] == "replace" and "unscented" in item["excerpt"].lower())
    applied = client.post(
        f"/api/findings/{finding['id']}/apply",
        json={"suggestion": "fragrance-free"},
        headers=H,
    )
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["submission"]["status"] == "draft"
    assert "fragrance-free" in body["revision"]["body"]
    assert "unscented" not in body["revision"]["body"].lower()
    assert len(body["revisions"]) == 2
    assert body["diff"]


def test_dismiss_needs_a_reason_and_creators_cannot_clear_critical(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    created = client.post(
        "/api/submissions",
        json={
            "title": "Dismiss me",
            "format": "social",
            "channel": "Instagram",
            "purpose": "Describe a studio product in a short caption",
            "body": "A really soft cloth.",
        },
        headers=H,
    ).json()
    really = next(item for item in created["findings"] if "really" in item["excerpt"].lower())
    missing = client.post(f"/api/findings/{really['id']}/decision", json={"action": "dismiss", "note": "no"}, headers=H)
    assert missing.status_code == 422
    dismissed = client.post(
        f"/api/findings/{really['id']}/decision",
        json={"action": "dismiss", "note": "This still sounds like the brand."},
        headers=H,
    )
    assert dismissed.status_code == 200
    critical = client.post(
        "/api/submissions",
        json={
            "title": "Critical dismiss",
            "format": "social",
            "channel": "Instagram",
            "purpose": "Announce Vela Bare Serum to people who already buy it",
            "body": "A guaranteed result.",
        },
        headers=H,
    ).json()
    blocker = next(item for item in critical["findings"] if item["severity"] == "critical")
    denied = client.post(
        f"/api/findings/{blocker['id']}/decision",
        json={"action": "dismiss", "note": "I do not think this is a problem."},
        headers=H,
    )
    assert denied.status_code == 403


def test_import_stays_draft_until_a_person_approves_it(client):
    auth(client, "samira.dal@vela.example", "manage-well")
    preview = client.post(
        "/api/import/preview",
        json={"kind": "guidelines", "text": "## Quiet claims\nCategory: claims\nSeverity: high\nDo not invent a study.\n"},
        headers=H,
    )
    assert preview.status_code == 200, preview.text
    committed = client.post(
        "/api/import/commit",
        json={"kind": "guidelines", "items": preview.json()["items"]},
        headers=H,
    )
    assert committed.json()["created"] == 1
    guidelines = client.get("/api/guidelines", headers=H).json()["items"]
    imported = next(item for item in guidelines if item["title"] == "Quiet claims")
    assert imported["status"] == "draft"
    auth(client, "maya.chen@vela.example", "draft-well")
    before = client.post(
        "/api/submissions",
        json={
            "title": "Import check",
            "format": "social",
            "channel": "Instagram",
            "purpose": "Describe a studio product in a short caption",
            "body": "A zigzag cloth for travel.",
        },
        headers=H,
    ).json()
    assert all(item["source_label"] != "Quiet claims" for item in before["findings"])
    client.post("/api/auth/logout", headers=H)
    auth(client, "samira.dal@vela.example", "manage-well")
    imported["match_value"] = "zigzag"
    imported["status"] = "approved"
    saved = client.patch(f"/api/guidelines/{imported['id']}", json=imported, headers=H)
    assert saved.status_code == 200, saved.text
    client.post("/api/auth/logout", headers=H)
    auth(client, "maya.chen@vela.example", "draft-well")
    after = client.post(
        "/api/submissions",
        json={
            "title": "Import check after approval",
            "format": "social",
            "channel": "Instagram",
            "purpose": "Describe a studio product in a short caption",
            "body": "A zigzag cloth for travel.",
        },
        headers=H,
    ).json()
    assert any(item["source_label"] == "Quiet claims" for item in after["findings"])


def test_docx_upload_is_reviewed(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    buffer = io.BytesIO()
    xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        "<w:body><w:p><w:r><w:t>This miracle cure is chemical-free.</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    response = client.post(
        "/api/submissions/upload",
        data={
            "title": "Agency doc",
            "format": "document",
            "channel": "Brief",
            "purpose": "Share a campaign line with retailers",
            "origin": "agency",
        },
        files={"file": ("brief.docx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=H,
    )
    assert response.status_code == 200, response.text
    assert "miracle" in response.json()["revision"]["body"].lower()
    assert any(item["category"] in {"claims", "terminology", "facts"} for item in response.json()["findings"])


def test_creator_cannot_see_another_creators_draft(client):
    auth(client, "leah.north@northco.example", "agency-well")
    created = client.post(
        "/api/submissions",
        json={
            "title": "Agency private",
            "format": "social",
            "channel": "Instagram",
            "purpose": "Describe a studio product in a short caption",
            "origin": "agency",
            "body": "A calm note from the agency.",
        },
        headers=H,
    ).json()
    client.post("/api/auth/logout", headers=H)
    auth(client, "maya.chen@vela.example", "draft-well")
    hidden = client.get(f"/api/submissions/{created['submission']['id']}", headers=H)
    assert hidden.status_code == 404


def test_insights_surface_repeated_and_unclear_rules(client):
    auth(client, "samira.dal@vela.example", "manage-well")
    payload = client.get("/api/insights?days=90", headers=H).json()
    assert payload["recurring"]
    assert payload["unclear_guidelines"]
    assert any("unclear" in line.lower() or "dismissed" in line.lower() for line in payload["summary"])
    assert payload["draft_guidelines"] >= 1
    assert any("example" in " ".join(item["reasons"]) for item in payload["gaps"])


def test_comment_and_changes_round_trip(client):
    auth(client, "maya.chen@vela.example", "draft-well")
    created = client.post(
        "/api/submissions",
        json={
            "title": "Comment path",
            "format": "email",
            "channel": "Retailer email",
            "purpose": "Tell retailers the serum is back in the catalogue",
            "body": GOOD_FAQ,
        },
        headers=H,
    ).json()
    submission_id = created["submission"]["id"]
    client.post(f"/api/submissions/{submission_id}/transition", json={"action": "submit", "note": "Ready for a look."}, headers=H)
    client.post("/api/auth/logout", headers=H)
    auth(client, "jules.okafor@vela.example", "review-well")
    commented = client.post(
        f"/api/submissions/{submission_id}/comments",
        json={"body": "Please name the study size in the first sentence."},
        headers=H,
    )
    assert commented.status_code == 200
    changed = client.post(
        f"/api/submissions/{submission_id}/transition",
        json={"action": "request_changes", "note": "Add the study size before this can be approved."},
        headers=H,
    )
    assert changed.json()["submission"]["status"] == "changes_requested"
    assert changed.json()["comments"]
