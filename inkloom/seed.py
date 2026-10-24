"""Demo workspace for Lumen & Grove, the brand Inkloom is governing."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from inkloom.db import uploads_dir
from inkloom.workflow import (
    add_comment,
    apply_finding,
    create_submission,
    decide,
    dismiss_finding,
    publish,
)

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

USERS = [
    ("usr_maya", "Maya Chen", "maya@lumenandgrove.example", "creator", "Content designer"),
    ("usr_leo", "Leo Park", "leo@lumenandgrove.example", "creator", "Lifecycle writer"),
    ("usr_priya", "Priya Nair", "priya@lumenandgrove.example", "reviewer", "Brand reviewer"),
    ("usr_alex", "Alex Okonkwo", "alex@lumenandgrove.example", "reviewer", "Claims reviewer"),
    ("usr_jordan", "Jordan Hale", "jordan@lumenandgrove.example", "manager", "Brand manager"),
    ("usr_sam", "Sam Rivera", "sam@lumenandgrove.example", "admin", "Workspace admin"),
]

GUIDELINES = [
    (
        "gdl_tone",
        "TONE-01",
        "Voice",
        "tone",
        """Grove sounds calm, specific, and adult. Write as if you are sitting with a member, not selling at them.

Use short sentences. Prefer concrete nouns (evening, tea, practitioner, sleep regularity) over hype. One exclamation mark is enough in a social post; use none in email, on the web, or in documents. Emoji are not part of the voice except a single mark in a social post when it adds tone a word cannot.

Do not shout in capitals. Emphasis belongs in the wording.""",
        0,
    ),
    (
        "gdl_lexicon",
        "TONE-02",
        "Words we don't use",
        "tone",
        """Avoid hype and combat metaphors. They make wellness sound like a stunt.

Prefer: a meaningful shift, a different approach, a daily ritual, support.
Avoid: game-changing, revolutionary, insane, crush, dominate, supercharge, amazing, epic, unlock, magic.

If a campaign name collides with this list, a reviewer can dismiss the flag and record the exception.""",
        0,
    ),
    (
        "gdl_term",
        "TERM-01",
        "Vocabulary",
        "terminology",
        """Say members, not users or customers.
Say practitioners, not doctors or therapists, unless you are quoting a named licensed clinician.
Say Grove, not “the Grove App” or “the Lumen app”.
Say daily ritual, not biohack.
Say wellness plan, not treatment.

The product does not diagnose, prescribe, or treat.""",
        0,
    ),
    (
        "gdl_msg",
        "MSG-01",
        "Messaging pillars",
        "messaging",
        """Every customer-facing piece connects to at least one pillar:

1. Evidence — the approved public study, and only that study.
2. Everyday ritual — a small practice that fits an ordinary evening.
3. Human support — practitioners who coach, and who are not physicians.

Do not invent a fourth promise (speed, dominance, transformation of the body).""",
        0,
    ),
    (
        "gdl_fear",
        "MSG-02",
        "No fear or pressure",
        "messaging",
        "Don't scare people.",
        0,
    ),
    (
        "gdl_claims",
        "CLM-01",
        "Promotional claims",
        "claims",
        """Do not claim that Grove cures, treats, guarantees, or clinically proves a health outcome.
Do not mention the FDA. Grove is not a medical device.
Do not use 100%, “#1”, “the best”, or weight-loss promises.
The only quantitative health result approved for publication is the public sleep study on the fact sheet.

If a sentence needs proof, quote that study with its sample size and its date. Do not round it into a bigger story.""",
        0,
    ),
    (
        "gdl_embargo",
        "CLM-02",
        "Restricted evidence",
        "claims",
        """A follow-up study is in medical review and is not cleared for any public channel, partner deck, or agency brief.

Internal protocol: LG-SR-26.
Unreleased result: 62% improvement in a draft analysis. Do not quote, round, or hint at this figure.
Public substitute: 18% improvement in self-reported sleep regularity, 12-week study, n=214, ledger dated March 2026.

Creators see that this record is restricted. They do not see this paragraph unless their role is reviewer, manager, or admin. Reading it is audited.""",
        1,
    ),
    (
        "gdl_facts",
        "FACT-01",
        "Public numbers",
        "facts",
        """Use only figures from the approved fact sheet, with their as-of date.

Member count, price, founding year, and the public study each have a source. If a draft number disagrees, the fact sheet wins. Outdated campaign numbers are still wrong.""",
        0,
    ),
    (
        "gdl_visual",
        "VIS-01",
        "Color and the wordmark",
        "visual",
        """Approved colors: Forest #1B4332, Moss #2D6A4F, Cream #F4F1EA, Ink #1A1A1A, Clay #C4744A.

The wordmark is horizontal, about 3.6:1, used whole, on cream or forest. Do not stretch, squash, rotate, recolor, or trap it in a tight square.

Graphics are built from the palette. Photographs of real places are not recolored to match, and they are not neon.""",
        0,
    ),
    (
        "gdl_photo",
        "VIS-02",
        "Photography",
        "visual",
        """Use natural light and ordinary scenes: kitchens, walks, hands around a cup.

No before-and-after body imagery. No clinical settings staged to look like a hospital. No stock “transformation” arcs.""",
        0,
    ),
    (
        "gdl_a11y",
        "A11Y-01",
        "Accessible content",
        "accessibility",
        """Write link text that names the destination. Never “click here”.

Alt text says what the picture shows and why it is there. Decorative images use an empty alt and must actually be decorative.

Body text on cream needs a contrast ratio of at least 4.5:1. Ink and Forest pass. Clay is for shapes, not paragraphs.

Keep sentences readable, generally under 32 words, and do not set headings in a run of capitals.""",
        0,
    ),
]

TERMS = [
    ("users", "members", "banned", "warning", "Grove has members, not users of a funnel.", "TERM-01"),
    ("customers", "members", "banned", "warning", "Say members. “Customers” frames the relationship as a transaction.", "TERM-01"),
    ("doctors", "practitioners", "banned", "critical", "Practitioners are coaches. Calling them doctors implies a clinical license they are not using here.", "TERM-01"),
    ("therapists", "practitioners", "banned", "critical", "Do not borrow a clinical title. Say practitioners unless you are quoting a named licensed clinician.", "TERM-01"),
    ("treatment", "wellness plan", "banned", "critical", "Grove does not treat a condition. Say wellness plan.", "TERM-01"),
    ("biohack", "daily ritual", "banned", "warning", "“Biohack” is off-voice. The approved phrase is daily ritual.", "TERM-01"),
    ("The Grove App", "Grove", "banned", "warning", "The product name is Grove.", "TERM-01"),
    ("Grove App", "Grove", "banned", "warning", "The product name is Grove, without “App”.", "TERM-01"),
    ("Lumen app", "Grove", "banned", "warning", "Lumen & Grove is the company. The product is Grove.", "TERM-01"),
    ("game-changing", "a meaningful shift", "avoid", "warning", "TONE-02 drops hype adjectives.", "TONE-02"),
    ("revolutionary", "different", "avoid", "warning", "TONE-02 prefers a plain description of what changed.", "TONE-02"),
    ("insane", "notable", "avoid", "warning", "TONE-02 avoids intensity slang.", "TONE-02"),
    ("crush", "stay with", "avoid", "warning", "Combat metaphors fight the calm voice.", "TONE-02"),
    ("dominate", "focus on", "avoid", "warning", "TONE-02 bans dominance language.", "TONE-02"),
    ("supercharge", "support", "avoid", "warning", "Prefer support over amplification slang.", "TONE-02"),
    ("amazing", "quiet", "avoid", "warning", "“Amazing” is hype unless a reviewer has recorded a proper-noun exception.", "TONE-02"),
    ("epic", "memorable", "avoid", "warning", "TONE-02 prefers a specific adjective.", "TONE-02"),
    ("unlock", "start", "avoid", "warning", "“Unlock” promises a hidden transformation.", "TONE-02"),
    ("magic", "simple", "avoid", "warning", "Magic overclaims the ritual.", "TONE-02"),
    ("don't get left behind", "join when you are ready", "fear", "warning", "MSG-02 forbids scarcity pressure.", "MSG-02"),
    ("before it's too late", "when it is useful", "fear", "warning", "Do not threaten the reader with a deadline on their health.", "MSG-02"),
    ("last chance", "still open", "fear", "warning", "Countdown language is off-brand.", "MSG-02"),
]

FACTS = [
    (
        "fct_members",
        "Member count",
        "Grove has 48,000 members as of March 2026.",
        "Member ledger, finance ops",
        "2026-03-01",
        0,
        "FACT-01",
        [
            {
                "label": "member count",
                "value": 48000,
                "tolerance": 0,
                "terms": ["re:\\bmembers\\b", "re:\\busers\\b", "re:\\bcustomers\\b"],
                "unit": None,
                "min_abs": 1000,
                "max_abs": 50000000,
            }
        ],
    ),
    (
        "fct_study",
        "Public sleep study",
        "In a 12-week study of 214 participants, members reported an 18% improvement in self-reported sleep regularity.",
        "Independent study notes, published March 2026",
        "2026-03-01",
        0,
        "FACT-01",
        [
            {
                "label": "study improvement",
                "value": 18,
                "tolerance": 0,
                "terms": ["re:\\bimprovement\\b", "re:\\bsleep regularity\\b"],
                "unit": "%",
                "min_abs": 0,
                "max_abs": 100,
            },
            {
                "label": "study size",
                "value": 214,
                "tolerance": 0,
                "terms": ["re:\\bparticipants?\\b", "re:\\bsample\\b"],
                "unit": None,
                "min_abs": 50,
                "max_abs": 5000,
            },
        ],
    ),
    (
        "fct_founded",
        "Founding year",
        "Lumen & Grove was founded in 2019 in Portland.",
        "Company register",
        "2019-04-12",
        0,
        "FACT-01",
        [
            {
                "label": "founding year",
                "value": 2019,
                "tolerance": 0,
                "terms": ["re:\\bfounded\\b"],
                "unit": None,
                "min_abs": 1900,
                "max_abs": 2035,
            }
        ],
    ),
    (
        "fct_price",
        "Membership price",
        "Grove membership is $18 per month.",
        "Pricing desk",
        "2026-01-15",
        0,
        "FACT-01",
        [
            {
                "label": "monthly price",
                "value": 18,
                "tolerance": 0,
                "terms": ["re:\\bper month\\b", "re:/month\\b", "re:\\ba month\\b"],
                "unit": None,
                "min_abs": 1,
                "max_abs": 500,
            }
        ],
    ),
    (
        "fct_embargo",
        "Unreleased study — do not publish",
        "Draft analysis LG-SR-26 shows a 62% improvement. Medical review has not released it. Do not publish this figure or describe it as the current result.",
        "Medical review board, embargoed",
        "2026-04-02",
        1,
        "CLM-02",
        [
            {
                "label": "embargoed improvement",
                "value": 62,
                "tolerance": 0,
                "terms": ["re:\\bimprovement\\b"],
                "unit": "%",
                "min_abs": 50,
                "max_abs": 100,
                "counterpart": "study improvement",
            }
        ],
    ),
]

ASSETS = [
    ("ast_forest", "Forest", "color", "Primary brand color for wordmark and text on cream.", "#1B4332", "ink", 0),
    ("ast_moss", "Moss", "color", "Secondary green for charts and quiet fills.", "#2D6A4F", "accent", 0),
    ("ast_cream", "Cream", "color", "Page and packaging ground. Text on cream must clear 4.5:1.", "#F4F1EA", "background", 0),
    ("ast_ink", "Ink", "color", "Body text when Forest is too present.", "#1A1A1A", "ink", 0),
    ("ast_clay", "Clay", "color", "Small shapes and dividers. Not for paragraphs.", "#C4744A", "accent", 0),
    (
        "ast_wordmark",
        "Horizontal wordmark",
        "logo",
        "Use the master file. Clear space equals the height of the letter G. Do not stretch. Natural proportion is about 3.6:1.",
        None,
        None,
        0,
    ),
    (
        "ast_photo",
        "Dawn kitchen stills",
        "photography",
        "Natural light, no retouching toward neon, no body comparisons. Alt text required when the photo carries the story.",
        None,
        None,
        0,
    ),
    (
        "ast_dieline",
        "Unreleased packaging dieline",
        "packaging",
        "Printer spec and unreleased autumn carton. Do not send to agencies. Restricted to reviewers and managers.",
        None,
        None,
        1,
    ),
]


def _user(con, user_id: str) -> dict:
    return dict(con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def _finding(con, submission_id: str, excerpt_contains: str, rule_id: str | None = None) -> dict:
    rows = con.execute(
        """
        SELECT f.* FROM findings f
        JOIN submissions s ON s.id = f.submission_id AND s.current_version = f.version
        WHERE f.submission_id = ? AND f.status = 'open' AND f.excerpt LIKE ?
        """,
        (submission_id, f"%{excerpt_contains}%"),
    ).fetchall()
    if rule_id:
        rows = [row for row in rows if row["rule_id"] == rule_id]
    if not rows:
        raise RuntimeError(f"Seed could not find an open finding '{excerpt_contains}' on {submission_id}")
    return dict(rows[0])


def _png(path, paint) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", paint["size"], paint["ground"])
    draw = ImageDraw.Draw(image)
    for rect, color in paint["rects"]:
        draw.rectangle(rect, fill=color)
    image.save(path, "PNG")


def seed(con) -> None:
    existing = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if existing:
        return
    for user in USERS:
        con.execute("INSERT INTO users (id, name, email, role, title) VALUES (?, ?, ?, ?, ?)", user)
    for item in GUIDELINES:
        con.execute(
            """
            INSERT INTO guidelines (id, code, title, category, body, confidential, version, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (*item, NOW, "usr_sam"),
        )
    for index, term in enumerate(TERMS):
        con.execute(
            """
            INSERT INTO terms (id, phrase, replacement, kind, severity, rationale, guideline_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"trm_{index:02d}", *term),
        )
    for fact in FACTS:
        con.execute(
            """
            INSERT INTO facts (id, title, statement, source, as_of, confidential, status, guideline_code, checks_json)
            VALUES (?, ?, ?, ?, ?, ?, 'approved', ?, ?)
            """,
            (*fact[:7], json.dumps({"checks": fact[7]})),
        )
    for asset in ASSETS:
        con.execute(
            """
            INSERT INTO assets (id, name, kind, usage_text, hex, role, approved, confidential)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            asset,
        )
    _seed_reviews(con)
    con.commit()


def _seed_reviews(con) -> None:
    maya = _user(con, "usr_maya")
    leo = _user(con, "usr_leo")
    priya = _user(con, "usr_priya")
    alex = _user(con, "usr_alex")
    jordan = _user(con, "usr_jordan")

    instagram = {
        "id": "sub_ig_spring",
        "title": "Spring launch caption",
        "format": "social",
        "channel": "Instagram",
        "purpose": "Announce that the spring Grove ritual is open to new members",
        "assignee_id": "usr_alex",
        "asset_intent": "none",
        "submit": True,
        "body": (
            "Grove is FINALLY here and it is a game-changing miracle for your sleep. "
            "Join 100,000 users who cured insomnia in 2 weeks — guaranteed. "
            "Doctors say it's the #1 biohack on the market. "
            "Don't get left behind. Click here. 🔥🔥🔥"
        ),
    }
    create_submission(con, maya, instagram)
    add_comment(
        con,
        alex,
        "sub_ig_spring",
        "I can't approve the cure claim or the member count. If we need proof, use the 18% study wording and keep the spring announcement.",
        None,
    )

    letter = {
        "id": "sub_letter_april",
        "title": "April member letter",
        "format": "email",
        "channel": "Lifecycle email",
        "purpose": "Tell members the spring ritual is available and point them to the study notes",
        "assignee_id": "usr_priya",
        "submit": True,
        "body": (
            "Hello,\n\n"
            "Last spring we wrote to our users about a quieter daily ritual. "
            "Grove now supports 100,000 members worldwide, and our practitioners "
            "still begin with the same question: what would make tonight easier?\n\n"
            "The 12-week study of 214 participants found an 18% improvement in "
            "self-reported sleep regularity. That is the figure we stand behind.\n\n"
            "If you want the detailed notes, click here.\n\n"
            "Warmly,\nThe Grove team"
        ),
    }
    create_submission(con, maya, letter)
    decide(
        con,
        priya,
        "sub_letter_april",
        "request_changes",
        "The member count has to match the March ledger (48,000). Please also replace “click here” and say members.",
    )

    homepage = {
        "id": "sub_homepage",
        "title": "Homepage hero",
        "format": "web",
        "channel": "Marketing site",
        "purpose": "Explain Grove to a new visitor and invite them into the daily ritual",
        "assignee_id": "usr_alex",
        "submit": True,
        "body": (
            "WAKE UP A NEW PERSON.\n"
            "Last chance. Our revolutionary platform guarantees you will lose 10 pounds and "
            "fixes your health forever. Button color #FF2E93 on cream. "
            "Before and after photos available on request. "
            "The Grove App is FDA approved and clinically proven."
        ),
    }
    create_submission(con, maya, homepage)
    add_comment(
        con,
        priya,
        "sub_homepage",
        "The hero can still invite people into the ritual. It cannot promise weight loss, name the FDA, or use that pink.",
        None,
    )

    embargo = {
        "id": "sub_embargo_note",
        "title": "Blog desk note",
        "format": "document",
        "channel": "Internal brief that may be forwarded",
        "purpose": "Stop the blog team from publishing an unreleased study figure",
        "assignee_id": "usr_alex",
        "submit": True,
        "body": (
            "Internal note for the blog team.\n\n"
            "Please do not put the 62% improvement figure in the customer letter. "
            "The only sleep result we can publish is the approved public study."
        ),
    }
    create_submission(con, maya, embargo)

    practitioner = {
        "id": "sub_practitioner",
        "title": "Practitioner briefing",
        "format": "document",
        "channel": "Internal enablement",
        "purpose": "Remind practitioners how to describe Grove without making medical claims",
        "assignee_id": "usr_priya",
        "submit": True,
        "body": (
            "Practitioners,\n\n"
            "Please describe Grove as a daily ritual, not a treatment. "
            "Members (48,000 as of March 2026) may ask about the public study: "
            "214 participants and an 18% improvement in self-reported sleep regularity. "
            "We do not diagnose, and Grove is not a medical device.\n\n"
            "Use the forest and cream palette. Write alt text for every meaningful image."
        ),
    }
    create_submission(con, leo, practitioner)
    decide(
        con,
        priya,
        "sub_practitioner",
        "approve",
        "Matches the vocabulary and the public study. Approved for the enablement folder.",
    )

    uploads = uploads_dir()
    good_path = uploads / "sub_logo_master.png"
    bad_path = uploads / "sub_launch_graphic.png"
    _png(
        good_path,
        {
            "size": (720, 200),
            "ground": (244, 241, 234),
            "rects": [((36, 48, 420, 152), (27, 67, 50)), ((450, 78, 680, 122), (45, 106, 79))],
        },
    )
    _png(
        bad_path,
        {
            "size": (640, 640),
            "ground": (255, 46, 147),
            "rects": [((40, 40, 600, 220), (0, 240, 255))],
        },
    )
    create_submission(
        con,
        leo,
        {
            "id": "sub_logo_master",
            "title": "Wordmark for the spring post",
            "format": "image",
            "channel": "Instagram",
            "purpose": "Place the approved wordmark at the end of the spring announcement",
            "assignee_id": "usr_priya",
            "asset_intent": "logo",
            "alt_text": "Lumen and Grove wordmark in forest green on a cream field",
            "submit": True,
            "body": "Wordmark lockup for the spring post.",
        },
        image_bytes=good_path.read_bytes(),
        image_name="wordmark.png",
    )
    # create_submission stores its own file; the preview master can stay as well.
    decide(
        con,
        alex,
        "sub_logo_master",
        "approve",
        "Alt text is specific and the mark stays on palette. Approved to publish when the caption is ready.",
    )

    create_submission(
        con,
        leo,
        {
            "id": "sub_launch_graphic",
            "title": "Launch graphic",
            "format": "image",
            "channel": "Paid social",
            "purpose": "A square graphic to announce the spring ritual in paid social",
            "assignee_id": "usr_priya",
            "asset_intent": "graphic",
            "alt_text": "image",
            "submit": True,
            "body": "Neon launch tile",
        },
        image_bytes=bad_path.read_bytes(),
        image_name="launch.png",
    )

    ad_id = "sub_quiet_ad"
    create_submission(
        con,
        leo,
        {
            "id": ad_id,
            "title": "Quiet evenings ad",
            "format": "ad",
            "channel": "Paid social",
            "purpose": "Invite people who want a quieter evening to look at Grove",
            "assignee_id": "usr_priya",
            "submit": True,
            "body": (
                "Grove is an amazing daily ritual for our users who want a quieter evening. "
                "Membership stays at $18/month."
            ),
        },
    )
    amazing = _finding(con, ad_id, "amazing", "tone.lexicon")
    dismiss_finding(
        con,
        priya,
        ad_id,
        amazing["id"],
        "“Amazing Quiet” was cleared as a campaign name in March. Keeping this one use.",
    )
    users = _finding(con, ad_id, "users", "term.vocabulary")
    apply_finding(con, leo, ad_id, users["id"])
    decide(
        con,
        priya,
        ad_id,
        "approve",
        "Vocabulary is corrected. The campaign-name exception is on the record.",
    )
    publish(con, jordan, ad_id, "Published to paid social after brand approval.")

    create_submission(
        con,
        maya,
        {
            "id": "sub_autumn_notes",
            "title": "Autumn campaign notes",
            "format": "document",
            "channel": "Working doc",
            "purpose": "Capture early lines for the autumn ritual before they are edited",
            "submit": False,
            "body": "Autumn notes: maybe say our users will love this.",
        },
    )
