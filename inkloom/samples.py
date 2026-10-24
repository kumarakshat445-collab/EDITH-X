"""Canonical drafts used by the demo workspace, the API, and the tests."""

GOOD_FAQ = (
    "Vela Daily Mineral is SPF 30. Vela Bare Serum uses 5% niacinamide to support the skin barrier. "
    "It is fragrance-free and made in Portugal. Vela is Leaping Bunny certified. "
    "In a 4-week study of 32 people, instrument readings showed barrier improvement. Results vary."
)

CAREFUL_SOCIAL = (
    "Vela Bare Serum is fragrance-free and made in Portugal. "
    "It uses 5% niacinamide to support the skin barrier. Results vary."
)

LAUNCH = (
    "YOU WON'T BELIEVE this miracle serum!!! Vela Bare Plus is the #1 chemical-free cure for acne and eczema, "
    "guaranteed overnight. It is SPF 50, 100% organic, and clinically proven to erase wrinkles. "
    "Click here. 10% niacinamide — cheap and insane results. "
    "Recolor the logo in neon purple and stretch it."
)

RETAILER = (
    "Hello, the unscented Vela Bare Serum is now in the catalogue. "
    "It uses 5% niacinamide to support the skin barrier and is made in Portugal. "
    "In a 4-week study of 32 people, instrument readings showed barrier improvement. Results vary."
)

AI_BLOG = (
    "The studio welcome post: visit us at 14 King Street this Friday. "
    "Our new Amberline oil uses AX-17 for overnight repair."
)

WEB_PAGE = """<html>
<body>
<h1>SPRING SALE NOW</h1>
<p style="color:#eeeeee;background-color:#f4f4f4;font-size:11px">The best chemical-free cure.</p>
<img src="hero.jpg">
<p><a href="/buy">click here</a></p>
<p>The limited shade is shown in red.</p>
</body>
</html>
"""

SAMPLES = [
    {
        "key": "launch",
        "title": "Launch day caption",
        "format": "social",
        "channel": "Instagram",
        "purpose": "Announce Vela Bare Serum to people who already buy it",
        "origin": "employee",
        "body": LAUNCH,
        "alt_text": "",
        "placement_notes": "",
        "blurb": "Packed with tone, terminology, claim, fact, messaging, and asset issues.",
    },
    {
        "key": "careful",
        "title": "Careful serum caption",
        "format": "social",
        "channel": "Instagram",
        "purpose": "Announce Vela Bare Serum to people who already buy it",
        "origin": "employee",
        "body": CAREFUL_SOCIAL,
        "alt_text": "",
        "placement_notes": "",
        "blurb": "A short caption written from the approved facts.",
    },
    {
        "key": "faq",
        "title": "SPF and serum FAQ",
        "format": "web",
        "channel": "Product FAQ",
        "purpose": "Explain the SPF and serum facts on the product page",
        "origin": "employee",
        "body": GOOD_FAQ,
        "alt_text": "",
        "placement_notes": "",
        "blurb": "Web copy that stays inside the approved facts.",
    },
    {
        "key": "web",
        "title": "Spring landing page",
        "format": "web",
        "channel": "Website",
        "purpose": "Send readers to the spring offer",
        "origin": "agency",
        "body": WEB_PAGE,
        "alt_text": "",
        "placement_notes": "",
        "blurb": "HTML with contrast, alt text, link text, and claim problems.",
    },
    {
        "key": "ai-blog",
        "title": "Welcome post from an AI draft",
        "format": "document",
        "channel": "Blog",
        "purpose": "Invite readers to the studio",
        "origin": "ai_tool",
        "body": AI_BLOG,
        "alt_text": "",
        "placement_notes": "",
        "blurb": "An AI-assisted draft with an outdated address and a confidential name.",
    },
]
