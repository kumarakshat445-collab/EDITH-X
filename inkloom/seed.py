"""Fictional Vela Collective workspace. Nothing here is a real brand."""

from __future__ import annotations

from inkloom.auth import hash_password
from inkloom.db import dumps
from inkloom.samples import AI_BLOG, GOOD_FAQ, LAUNCH, RETAILER
from inkloom.workflow import _add_event, create_submission, now, shift

ACCOUNTS = [
    {
        "email": "maya.chen@vela.example",
        "password": "draft-well",
        "name": "Maya Chen",
        "role": "creator",
        "affiliation": "Vela Collective",
    },
    {
        "email": "leah.north@northco.example",
        "password": "agency-well",
        "name": "Leah North",
        "role": "creator",
        "affiliation": "North & Co (agency)",
    },
    {
        "email": "jules.okafor@vela.example",
        "password": "review-well",
        "name": "Jules Okafor",
        "role": "reviewer",
        "affiliation": "Vela Collective",
    },
    {
        "email": "samira.dal@vela.example",
        "password": "manage-well",
        "name": "Samira Dal",
        "role": "manager",
        "affiliation": "Vela Collective",
    },
    {
        "email": "adrian.cole@vela.example",
        "password": "admin-well",
        "name": "Adrian Cole",
        "role": "admin",
        "affiliation": "Vela Collective",
    },
]


def seed_if_empty(conn) -> None:
    existing = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if existing:
        return
    moment = now()
    users = {}
    for account in ACCOUNTS:
        cur = conn.execute(
            """
            INSERT INTO users (email, name, role, affiliation, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                account["email"],
                account["name"],
                account["role"],
                account["affiliation"],
                hash_password(account["password"]),
                moment,
            ),
        )
        users[account["email"]] = cur.lastrowid
    conn.execute(
        """
        INSERT INTO brand (id, name, legal_name, voice, audience, reading_grades_json, seed_version)
        VALUES (1, ?, ?, ?, ?, ?, 1)
        """,
        (
            "Vela Collective",
            "Vela Studio Ltd",
            "Calm, precise, and warm. Say what the formula does. Do not shout, promise a cure, or invent a ranking.",
            "People who already buy Vela and want a clear description before they repurchase.",
            dumps({"social": 8, "email": 9, "web": 12, "document": 12, "image": 8}),
        ),
    )
    admin = users["adrian.cole@vela.example"]
    _guidelines(conn, admin, moment)
    _facts(conn, admin, moment)
    _terms(conn, admin, moment)
    logo_id = _assets(conn, admin, moment)
    maya = _user(conn, users["maya.chen@vela.example"])
    leah = _user(conn, users["leah.north@northco.example"])
    jules = users["jules.okafor@vela.example"]
    _history(conn, maya, leah, jules)
    _queue(conn, maya, leah, jules, logo_id)


def _user(conn, user_id: int) -> dict:
    return dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def _guidelines(conn, admin: int, moment: str) -> None:
    items = [
        (
            "tone",
            "Calm and precise",
            "Write in a calm, precise, warm voice. Do not hype, shout, or talk down to the reader.",
            "medium",
            "keywords",
            dumps(
                [
                    "you won't believe",
                    "insane",
                    "cheap",
                    "amazing",
                    "literally",
                    "game-changer",
                    "game changer",
                    "supercharge",
                    "hack",
                ]
            ),
            "Keep the product fact and drop the hype word.",
            "Vela Bare Serum uses 5% niacinamide to support the skin barrier.",
            "You won't believe this insane serum.",
            0,
            "approved",
        ),
        (
            "claims",
            "No unsupported promotional claims",
            "Do not claim a ranking, a guarantee, a cure, a certification, or a timed result unless an approved fact says those exact words.",
            "critical",
            "claims",
            dumps({}),
            "Delete the claim or replace it with an approved fact.",
            "In a 4-week study of 32 people, instrument readings showed barrier improvement. Results vary.",
            "Clinically proven to cure acne overnight.",
            0,
            "approved",
        ),
        (
            "messaging",
            "Show that results vary",
            "When copy mentions a study, a result, or an improvement, include the words “results vary”.",
            "medium",
            "required_when",
            dumps(
                {
                    "trigger": r"\b(study|improvement|proven|clinical)\b",
                    "required": "results vary",
                    "addition": "Results vary.",
                }
            ),
            "Add “Results vary.”",
            "Barrier improvement was measured. Results vary.",
            "Clinically proven improvement.",
            0,
            "approved",
        ),
        (
            "accessibility",
            "Readable and described",
            "Give images a real text alternative, keep body type at least 14px, keep text contrast at 4.5:1 or better, and do not use “click here” or color as the only cue.",
            "high",
            "accessibility",
            dumps(
                {
                    "require_alt": True,
                    "max_grade_buffer": 1.5,
                    "min_contrast": 4.5,
                    "min_font_px": 14,
                    "flag_click_here": True,
                    "flag_all_caps": True,
                }
            ),
            "Describe the information. Do not say click here.",
            "Alt text: Amber glass bottle of Vela Bare Serum on a paper background.",
            "Alt text: image1.png. Link: click here.",
            0,
            "approved",
        ),
        (
            "visual",
            "Use the Vela palette",
            "Ink, paper, copper, grove, and clay are the approved colors. Logos are not recolored, stretched, or set in neon.",
            "medium",
            "visual",
            dumps({"max_delta_e": 40, "min_width": 600}),
            "Move the image toward an approved color, or attach an asset that allows natural color.",
            "A packshot on the paper background with a copper rule.",
            "A neon purple logo stretched over a photograph.",
            0,
            "approved",
        ),
        (
            "tone",
            "Avoid the word really",
            "Avoid “really”. It weakens an otherwise specific sentence.",
            "low",
            "keywords",
            dumps(["really"]),
            "Delete “really”.",
            "The cloth is soft.",
            "The cloth is really soft.",
            0,
            "approved",
        ),
        (
            "messaging",
            "Be distinctive",
            "Sound like Vela and not like a generic campaign line.",
            "low",
            "keywords",
            dumps(["synergy"]),
            "",
            "",
            "",
            0,
            "approved",
        ),
        (
            "tone",
            "Emoji policy",
            "Do not use an emoji as a substitute for a word in product claims or instructions.",
            "low",
            "keywords",
            dumps(["🔥"]),
            "Replace the emoji with the approved word.",
            "Limited shade.",
            "Limited shade 🔥",
            0,
            "draft",
        ),
    ]
    for item in items:
        conn.execute(
            """
            INSERT INTO guidelines (
              category, title, body, severity, match_type, match_value, suggestion,
              good_example, bad_example, confidential, status, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*item, admin, moment, moment),
        )


def _facts(conn, admin: int, moment: str) -> None:
    records = [
        {
            "topic": "Daily Mineral SPF",
            "statement": "Vela Daily Mineral is SPF 30.",
            "source_label": "Formula card, Daily Mineral, 2026",
            "severity": "high",
            "contradicts": [
                {"phrase": "SPF 50", "replacement": "SPF 30"},
                {"phrase": "SPF50", "replacement": "SPF 30"},
                {"phrase": "SPF 15", "replacement": "SPF 30"},
            ],
            "supports": ["SPF 30"],
            "suggested": "Vela Daily Mineral is SPF 30.",
            "status": "approved",
        },
        {
            "topic": "Bare Serum strength",
            "statement": "Vela Bare Serum contains 5% niacinamide.",
            "source_label": "Formula card, Bare Serum, 2026",
            "severity": "high",
            "contradicts": [
                {"phrase": "10% niacinamide", "replacement": "5% niacinamide"},
                {"phrase": "20% niacinamide", "replacement": "5% niacinamide"},
            ],
            "supports": ["5% niacinamide"],
            "suggested": "Vela Bare Serum uses 5% niacinamide.",
            "status": "approved",
        },
        {
            "topic": "No treatment claims",
            "statement": "Vela does not treat or cure acne, eczema, rosacea, or wrinkles.",
            "source_label": "Claims register, 2026",
            "severity": "critical",
            "contradicts": [
                {"phrase": "cure for acne"},
                {"phrase": "cure acne"},
                {"phrase": "cure for eczema"},
                {"phrase": "erase wrinkles"},
                {"phrase": "treat eczema"},
            ],
            "supports": [],
            "suggested": "Vela does not treat or cure acne, eczema, rosacea, or wrinkles.",
            "status": "approved",
        },
        {
            "topic": "Not organic",
            "statement": "Vela is not certified organic.",
            "source_label": "Certification file, 2026",
            "severity": "high",
            "contradicts": [
                {"phrase": "100% organic", "replacement": "not certified organic"},
                {"phrase": "certified organic", "replacement": "not certified organic"},
            ],
            "supports": ["not certified organic"],
            "covers": ["organic"],
            "suggested": "Vela is not certified organic.",
            "status": "approved",
        },
        {
            "topic": "Clinical evidence",
            "statement": "Evidence is a 4-week study of 32 people measuring barrier improvement. It is not a medical trial and is not described as clinically proven.",
            "source_label": "Study note V-32",
            "severity": "critical",
            "contradicts": [
                {"phrase": "clinically proven", "replacement": "measured in a 4-week study of 32 people"},
                {"phrase": "medically proven", "replacement": "measured in a 4-week study of 32 people"},
            ],
            "supports": ["4-week study of 32 people"],
            "covers": ["clinical"],
            "suggested": "In a 4-week study of 32 people, instrument readings showed barrier improvement. Results vary.",
            "status": "approved",
        },
        {
            "topic": "Made in Portugal",
            "statement": "Vela skincare is made in Portugal.",
            "source_label": "Origin declaration, 2026",
            "severity": "high",
            "contradicts": [
                {"phrase": "made in Spain", "replacement": "made in Portugal"},
                {"phrase": "made in France", "replacement": "made in Portugal"},
                {"phrase": "made in China", "replacement": "made in Portugal"},
            ],
            "supports": ["made in Portugal"],
            "suggested": "Made in Portugal.",
            "status": "approved",
        },
        {
            "topic": "No money-back guarantee",
            "statement": "Vela does not offer a money-back guarantee.",
            "source_label": "Commercial terms, 2026",
            "severity": "critical",
            "contradicts": [
                {"phrase": "money-back"},
                {"phrase": "money back guarantee"},
                {"phrase": "guaranteed"},
            ],
            "supports": [],
            "suggested": "Remove the guarantee. Vela does not offer one.",
            "status": "approved",
        },
        {
            "topic": "Leaping Bunny",
            "statement": "Vela is Leaping Bunny certified.",
            "source_label": "Leaping Bunny certificate",
            "severity": "medium",
            "contradicts": [{"phrase": "PETA approved", "replacement": "Leaping Bunny certified"}],
            "supports": ["Leaping Bunny"],
            "suggested": "Vela is Leaping Bunny certified.",
            "status": "approved",
        },
        {
            "topic": "Former studio address",
            "statement": "14 King Street is the former studio and is not a current visit address. Visits are by appointment at the Riverside atelier.",
            "source_label": "Studio note, expired March 2026",
            "severity": "high",
            "contradicts": [],
            "supports": ["14 King Street"],
            "replacement": "the Riverside atelier",
            "suggested": "Visits are by appointment at the Riverside atelier.",
            "status": "expired",
            "review_after": "2026-03-01",
        },
        {
            "topic": "Unreleased Amberline",
            "statement": "The unreleased Amberline oil and the supplier code AX-17 are confidential and must not appear in public copy.",
            "source_label": "Unreleased formula note",
            "severity": "critical",
            "contradicts": [{"phrase": "AX-17"}, {"phrase": "Amberline"}],
            "supports": [],
            "suggested": "",
            "confidential": 1,
            "status": "approved",
        },
    ]
    for record in records:
        conn.execute(
            """
            INSERT INTO facts (
              topic, statement, source_label, severity, contradicts_json, supports_json, covers_json,
              suggested, replacement, confidential, status, effective_on, review_after, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["topic"],
                record["statement"],
                record["source_label"],
                record["severity"],
                dumps(record.get("contradicts") or []),
                dumps(record.get("supports") or []),
                dumps(record.get("covers") or []),
                record.get("suggested") or "",
                record.get("replacement") or "",
                record.get("confidential", 0),
                record["status"],
                record.get("effective_on", "2026-01-01"),
                record.get("review_after", "2027-01-01"),
                admin,
                moment,
                moment,
            ),
        )


def _terms(conn, admin: int, moment: str) -> None:
    records = [
        ("fragrance-free", ["unscented", "chemical-free"], "No fragrance is added to the formula. Unscented can mean a masking fragrance is present.", "Product descriptions", "high"),
        ("skin barrier", ["moisture lock", "moisture barrier hack"], "Use the plain name of the thing the formula supports.", "Product descriptions", "medium"),
        ("Vela Bare Serum", ["Vela Bare Plus", "Bare+"], "The product name is Vela Bare Serum. There is no Plus version.", "Names", "high"),
        ("Leaping Bunny certified", ["cruelty-free certified", "PETA approved"], "Name the certification Vela actually holds.", "Certifications", "medium"),
    ]
    for preferred, avoid, definition, context, severity in records:
        conn.execute(
            """
            INSERT INTO terms (
              preferred, avoid_json, definition, context, severity, confidential, status, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, 'approved', ?, ?, ?)
            """,
            (preferred, dumps(avoid), definition, context, severity, admin, moment, moment),
        )


def _assets(conn, admin: int, moment: str) -> int:
    from PIL import Image, ImageDraw

    from inkloom.db import UPLOADS

    logo_path = UPLOADS / "seed-logo.png"
    neon_path = UPLOADS / "seed-neon.png"
    logo = Image.new("RGB", (800, 360), "#F3EFE6")
    draw = ImageDraw.Draw(logo)
    draw.rectangle((36, 36, 764, 324), outline="#B5522A", width=6)
    draw.text((70, 150), "VELA", fill="#1C2421")
    logo.save(logo_path, "PNG")
    neon = Image.new("RGB", (900, 900), "#C026D3")
    draw = ImageDraw.Draw(neon)
    draw.rectangle((70, 70, 830, 830), fill="#7C3AED")
    neon.save(neon_path, "PNG")
    colors = [
        ("Vela Ink", "#1C2421"),
        ("Vela Paper", "#F3EFE6"),
        ("Vela Copper", "#B5522A"),
        ("Vela Grove", "#1E6B4F"),
        ("Vela Clay", "#E4D3C4"),
    ]
    for name, hex_value in colors:
        conn.execute(
            """
            INSERT INTO assets (
              name, kind, description, usage_rules, color_hex, rules_json, confidential, status, updated_by, created_at, updated_at
            ) VALUES (?, 'color', ?, ?, ?, '{}', 0, 'approved', ?, ?, ?)
            """,
            (
                name,
                f"Approved brand color {hex_value}.",
                "Use the approved colors for graphic elements. Photography may use natural color only when the asset allows it.",
                hex_value,
                admin,
                moment,
                moment,
            ),
        )
    cur = conn.execute(
        """
        INSERT INTO assets (
          name, kind, description, usage_rules, color_hex, rules_json, file_path, file_name, mime,
          confidential, status, updated_by, created_at, updated_at
        ) VALUES (?, 'logo', ?, ?, '', ?, ?, ?, 'image/png', 0, 'approved', ?, ?, ?)
        """,
        (
            "Vela wordmark",
            "The primary wordmark, set in ink on paper.",
            "Do not recolor, stretch, rotate, add a drop shadow, or place the wordmark in neon.",
            dumps({"do_not": ["recolor", "neon", "stretch", "rotate", "drop shadow"], "allow_natural_color": False}),
            "seed-logo.png",
            "vela-wordmark.png",
            admin,
            moment,
            moment,
        ),
    )
    logo_id = cur.lastrowid
    conn.execute(
        """
        INSERT INTO assets (
          name, kind, description, usage_rules, rules_json, confidential, status, updated_by, created_at, updated_at
        ) VALUES (?, 'photo', ?, ?, ?, 0, 'approved', ?, ?, ?)
        """,
        (
            "Approved packshot",
            "Product photography on the paper background.",
            "Natural color is allowed. Do not add graphics that fight the palette.",
            dumps({"do_not": [], "allow_natural_color": True}),
            admin,
            moment,
            moment,
        ),
    )
    conn.execute(
        """
        INSERT INTO assets (
          name, kind, description, usage_rules, rules_json, confidential, status, updated_by, created_at, updated_at
        ) VALUES (?, 'photo', ?, ?, ?, 1, 'approved', ?, ?, ?)
        """,
        (
            "Amberline pack",
            "Reference for an unreleased product. The name and the pack are confidential.",
            "Do not place this pack in public channels.",
            dumps({"do_not": ["instagram", "public", "launch"], "allow_natural_color": True}),
            admin,
            moment,
            moment,
        ),
    )
    return logo_id


def _history(conn, maya: dict, leah: dict, jules: int) -> None:
    pieces = [
        (maya, "Cotton tote line", "A really soft cotton tote for the studio visit.", -40, "dismissed"),
        (maya, "Travel cloth", "It is really gentle on dry days.", -32, "dismissed"),
        (leah, "Counter card", "Customers say it feels really light.", -24, "dismissed"),
        (maya, "Daily cloth", "A really quiet formula for every day.", -18, "dismissed"),
        (maya, "Hand feel", "The cloth is really soft in the hand.", -12, "accepted"),
        (maya, "Cloth set", "The chemical-free cloth set is back on the counter.", -36, "accepted"),
        (leah, "Travel tin", "Ask for the chemical-free travel tin.", -20, "accepted"),
        (maya, "Retailer minis", "We packed the chemical-free minis for the retailer.", -8, "accepted"),
        (maya, "Travel ranking", "This is the best cloth in the travel set.", -15, "accepted"),
        (leah, "Season note", "The finish is guaranteed for the season.", -6, "accepted"),
    ]
    for author, title, body, days, decision in pieces:
        submission_id = create_submission(
            conn,
            author,
            {
                "title": title,
                "format": "social",
                "channel": "Instagram",
                "purpose": "Describe a studio product in a short caption",
                "origin": "agency" if author["id"] == leah["id"] else "employee",
                "body": body,
            },
        )
        _decide_all(conn, submission_id, decision, jules if decision == "dismissed" else author["id"])
        conn.execute("UPDATE submissions SET status = 'published' WHERE id = ?", (submission_id,))
        _add_event(conn, submission_id, jules, "published", "Seeded as an already published caption.", "approved", "published")
        _backdate(conn, submission_id, shift(days=days))


def _queue(conn, maya: dict, leah: dict, jules: int, logo_id: int) -> None:
    launch = create_submission(
        conn,
        maya,
        {
            "title": "Launch day caption",
            "format": "social",
            "channel": "Instagram",
            "purpose": "Announce Vela Bare Serum to people who already buy it",
            "origin": "employee",
            "body": LAUNCH,
        },
    )
    conn.execute(
        "UPDATE submissions SET status = 'in_review', assignee_id = ? WHERE id = ?",
        (jules, launch),
    )
    _add_event(conn, launch, maya["id"], "submitted", "Sent for human review.", "draft", "in_review")
    _add_event(conn, launch, jules, "assigned", "Assigned to Jules Okafor.")
    conn.execute(
        "INSERT INTO comments (submission_id, finding_id, author_id, body, created_at) VALUES (?, NULL, ?, ?, ?)",
        (
            launch,
            jules,
            "The launch can stay warm without a cure claim or a ranking. I left the findings open so you can choose the wording.",
            now(),
        ),
    )
    retailer = create_submission(
        conn,
        maya,
        {
            "title": "Retailer note",
            "format": "email",
            "channel": "Retailer email",
            "purpose": "Tell retailers the serum is back in the catalogue",
            "origin": "employee",
            "body": RETAILER,
        },
    )
    conn.execute("UPDATE submissions SET status = 'changes_requested', assignee_id = ? WHERE id = ?", (jules, retailer))
    _add_event(conn, retailer, jules, "changes_requested", "Please use the approved term before this goes out.", "in_review", "changes_requested")
    conn.execute(
        "INSERT INTO comments (submission_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
        (
            retailer,
            jules,
            "Unscented is on the avoid list. Fragrance-free is the approved term, because unscented can mean a fragrance was masked.",
            now(),
        ),
    )
    faq = create_submission(
        conn,
        maya,
        {
            "title": "SPF and serum FAQ",
            "format": "web",
            "channel": "Product FAQ",
            "purpose": "Explain the SPF and serum facts on the product page",
            "origin": "employee",
            "body": GOOD_FAQ,
        },
    )
    conn.execute("UPDATE submissions SET status = 'approved', assignee_id = ? WHERE id = ?", (jules, faq))
    _add_event(conn, faq, jules, "approved", "Approved by a person who did not write the draft.", "in_review", "approved")
    from inkloom.engine import analyze_image
    from inkloom.db import UPLOADS

    neon = analyze_image(str(UPLOADS / "seed-neon.png"))
    create_submission(
        conn,
        leah,
        {
            "title": "Story frame",
            "format": "image",
            "channel": "Paid social",
            "purpose": "Show the wordmark in a paid story",
            "origin": "agency",
            "body": "",
            "alt_text": "",
            "placement_notes": "Recolor the logo in neon purple and stretch it across the story frame.",
            "asset_id": logo_id,
            "file_path": "seed-neon.png",
            "file_name": "story-frame.png",
            "mime": "image/png",
            "image": neon,
        },
    )
    create_submission(
        conn,
        maya,
        {
            "title": "Welcome post from an AI draft",
            "format": "document",
            "channel": "Blog",
            "purpose": "Invite readers to the studio",
            "origin": "ai_tool",
            "body": AI_BLOG,
        },
    )


def _decide_all(conn, submission_id: int, status: str, actor_id: int) -> None:
    note = (
        "The line still sounds like us. This rule is unclear."
        if status == "dismissed"
        else "Rewritten against the approved source before publication."
    )
    conn.execute(
        """
        UPDATE findings
        SET status = ?, decision_note = ?, decision_by = ?, decided_at = ?
        WHERE submission_id = ? AND status = 'open'
        """,
        (status, note, actor_id, now(), submission_id),
    )


def _backdate(conn, submission_id: int, when: str) -> None:
    conn.execute("UPDATE submissions SET created_at = ?, updated_at = ? WHERE id = ?", (when, when, submission_id))
    conn.execute("UPDATE revisions SET created_at = ? WHERE submission_id = ?", (when, submission_id))
    conn.execute("UPDATE findings SET created_at = ?, decided_at = ? WHERE submission_id = ?", (when, when, submission_id))
    conn.execute("UPDATE events SET created_at = ? WHERE submission_id = ?", (when, submission_id))
