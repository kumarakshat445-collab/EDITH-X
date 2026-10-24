"""Local, explainable review engine.

Findings are produced by named rules over the workspace library. This module
does not call an external model or service. A suggestion is never applied here;
callers decide whether a person accepts it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

CREAM = (244, 241, 234)
ALLOW_CAPS = {"FDA", "HTML", "URL", "CTA"}

CLAIM_RULES: list[tuple[str, str, str, str, str]] = [
    (
        r"\bcure[ds]?\b",
        "critical",
        "Unsupported cure claim",
        "CLM-01 forbids saying Grove cures a condition. Grove is a wellness companion, not a medical treatment.",
        "Remove the cure wording. If you need evidence, use the approved public study: an 18% improvement in self-reported sleep regularity (12-week study, n=214).",
    ),
    (
        r"\bclinically proven\b",
        "critical",
        "“Clinically proven” is not an approved claim",
        "CLM-01 allows only the specific approved study result. “Clinically proven” overstates that evidence.",
        "Replace the phrase with the approved wording: “In a 12-week study of 214 participants, members reported an 18% improvement in sleep regularity.”",
    ),
    (
        r"\bFDA\b(?:[-\s]?approved)?",
        "critical",
        "FDA claim is not approved",
        "Grove is not an FDA-cleared medical device. Naming the FDA implies a status the approved facts do not support.",
        "Delete the FDA reference. Describe Grove as a daily wellness ritual supported by practitioners.",
    ),
    (
        r"\b100\s*(?:%|percent)\b",
        "critical",
        "Absolute 100% claim",
        "CLM-01 blocks absolute performance promises. No approved fact supports a 100% outcome.",
        "Remove “100%” and, if a number is necessary, use a figure from the approved fact sheet.",
    ),
    (
        r"\blose\s+\d+\s*(?:pounds|lbs|kg)\b",
        "critical",
        "Weight-loss promise",
        "Weight-loss promises are promotional medical claims. They are not in the approved fact sheet.",
        "Delete the weight-loss line. Talk about the daily ritual or the approved sleep-regularity result instead.",
    ),
    (
        r"\bguarant(?:ee|eed|ees)\b",
        "critical",
        "Guarantee overstates what Grove can promise",
        "CLM-01 does not allow guarantees of health or performance outcomes.",
        "Change the guarantee to a description of what the product is designed to support, without promising an outcome.",
    ),
    (
        r"\bdouble[sd]?\s+your\b",
        "critical",
        "“Double your…” is an unsupported amplification",
        "No approved fact says Grove doubles a health measure.",
        "Remove the doubling claim. Use the approved 18% sleep-regularity figure if you need a result.",
    ),
    (
        r"\bmiracles?\b",
        "critical",
        "Miracle language is an unsupported claim",
        "Miracle wording promises an outcome Grove does not document.",
        "Delete “miracle” and describe the concrete ritual or the approved study result.",
    ),
    (
        r"(?:^|\s)#1\b|\bnumber[- ]one\b|\bthe best\b",
        "warning",
        "Unqualified superlative",
        "Superlatives such as “#1” or “the best” need an approved source. None is on the fact sheet.",
        "Remove the ranking, or wait until a reviewer attaches an approved source.",
    ),
]


@dataclass
class Term:
    id: str
    phrase: str
    replacement: str
    kind: str
    severity: str
    rationale: str
    guideline_code: str


@dataclass
class FactCheck:
    fact_id: str
    title: str
    statement: str
    source: str
    as_of: str
    confidential: bool
    guideline_code: str
    label: str
    value: float
    tolerance: float
    terms: list[str]
    unit: str | None
    min_abs: float | None
    max_abs: float | None
    counterpart: str | None = None


@dataclass
class Guideline:
    id: str
    code: str
    title: str
    body: str
    category: str
    confidential: bool


@dataclass
class PaletteColor:
    asset_id: str
    name: str
    hex: str
    role: str


@dataclass
class Library:
    terms: list[Term]
    checks: list[FactCheck]
    guidelines: list[Guideline]
    palette: list[PaletteColor]
    logo_ratio: float = 3.6
    logo_ratio_tolerance: float = 1.2


@dataclass
class Finding:
    rule_id: str
    category: str
    severity: str
    title: str
    excerpt: str
    explanation: str
    suggestion: str
    replacement: str | None
    apply_mode: str
    source_type: str
    source_id: str
    source_label: str
    confidence: float
    span_start: int | None
    span_end: int | None
    public_explanation: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewInput:
    body: str
    fmt: str
    purpose: str
    alt_text: str = ""
    asset_intent: str = "none"
    image_path: str | None = None


@dataclass
class NumberToken:
    start: int
    end: int
    value: float
    raw: str
    is_percent: bool


def _guideline(library: Library, code: str) -> Guideline:
    for item in library.guidelines:
        if item.code == code:
            return item
    return Guideline(code, code, code, "", "", False)


def _source(guideline: Guideline) -> tuple[str, str, str]:
    return ("guideline", guideline.id, f"{guideline.code} · {guideline.title}")


def _purpose_prefix(purpose: str, text: str) -> str:
    clean = " ".join(purpose.split())
    if not clean:
        return text
    return f"Keep the purpose (“{clean}”). {text}"


def _match_case(excerpt: str, replacement: str) -> str:
    if not replacement or not excerpt:
        return replacement
    if replacement[:1].isupper():
        return replacement
    if excerpt.isupper():
        return replacement.upper()
    if excerpt[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - 48) : start].lower().replace("’", "'")
    return bool(
        re.search(
            r"\b(not|never|no|don't|do not|avoid|instead of|rather than|stop saying|don't say|do not say)\b",
            window,
        )
    )


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def _channel(c: float) -> float:
    c = c / 255
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (_channel(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    left, right = _luminance(a), _luminance(b)
    lighter, darker = max(left, right), min(left, right)
    return (lighter + 0.05) / (darker + 0.05)


def _color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _nearest_palette(
    rgb: tuple[int, int, int], palette: list[PaletteColor]
) -> tuple[PaletteColor | None, float]:
    best: PaletteColor | None = None
    best_dist = 10**9
    for color in palette:
        dist = _color_distance(rgb, _hex_to_rgb(color.hex))
        if dist < best_dist:
            best = color
            best_dist = dist
    return best, best_dist


def _extract_numbers(text: str) -> list[NumberToken]:
    tokens: list[NumberToken] = []
    pattern = re.compile(
        r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s*(?:%|percent))?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        raw_number = match.group(1).replace(",", "")
        value = float(raw_number)
        is_percent = bool(match.group(2))
        tokens.append(
            NumberToken(match.start(), match.end(), value, match.group(0), is_percent)
        )
    return tokens


def _term_in_window(text: str, number: NumberToken, term: str, window: int = 56) -> bool:
    left = max(0, number.start - window)
    right = min(len(text), number.end + window)
    region = text[left:right]
    if term.startswith("re:"):
        return re.search(term[3:], region, re.IGNORECASE) is not None
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", region, re.IGNORECASE) is not None


def _date_year(text: str, number: NumberToken) -> bool:
    """Years attached to a month or an as-of date are not member counts or prices."""
    if number.is_percent or not (1900 <= number.value <= 2039):
        return False
    region = text[max(0, number.start - 16) : number.end + 8]
    return (
        re.search(
            r"\b(January|February|March|April|May|June|July|August|September|"
            r"October|November|December|as of)\b",
            region,
            re.IGNORECASE,
        )
        is not None
    )


def _in_range(number: NumberToken, check: FactCheck) -> bool:
    if check.min_abs is not None and abs(number.value) < check.min_abs:
        return False
    if check.max_abs is not None and abs(number.value) > check.max_abs:
        return False
    if check.unit == "%" and not number.is_percent:
        return False
    return True


def _close(number: NumberToken, check: FactCheck) -> bool:
    return abs(number.value - check.value) <= (check.tolerance or 0) + 1e-6


def _format_value(check: FactCheck) -> str:
    if check.unit == "%" and float(check.value).is_integer():
        return f"{int(check.value)}%"
    if float(check.value).is_integer() and check.value >= 1000:
        return f"{int(check.value):,}"
    if float(check.value).is_integer():
        return str(int(check.value))
    return str(check.value)


def _add(findings: list[Finding], item: Finding) -> None:
    for existing in findings:
        if existing.rule_id != item.rule_id:
            continue
        if existing.span_start is None or item.span_start is None:
            if existing.excerpt == item.excerpt:
                return
            continue
        if item.span_start >= existing.span_start and item.span_end <= existing.span_end:
            return
        if existing.span_start >= item.span_start and existing.span_end <= item.span_end:
            return
    findings.append(item)


def _review_terms(text: str, library: Library, findings: list[Finding]) -> None:
    terms = sorted(library.terms, key=lambda term: len(term.phrase), reverse=True)
    for term in terms:
        pattern = re.compile(r"(?<!\w)" + re.escape(term.phrase) + r"(?!\w)", re.IGNORECASE)
        for match in pattern.finditer(text):
            if _negated(text, match.start()):
                continue
            guideline = _guideline(library, term.guideline_code)
            source_type, source_id, source_label = _source(guideline)
            if term.kind == "fear":
                category = "messaging"
                rule_id = "message.fear"
                title = "Pressure or fear-based phrasing"
            elif term.kind == "avoid":
                category = "tone"
                rule_id = "tone.lexicon"
                title = "Off-tone wording"
            else:
                category = "terminology"
                rule_id = "term.vocabulary"
                title = "Terminology doesn't match the approved vocabulary"
            excerpt = match.group(0)
            replacement = _match_case(excerpt, term.replacement) if term.replacement else None
            if term.kind == "fear":
                suggestion = (
                    f"Soften “{excerpt}”. {term.rationale} "
                    "Invite the reader without a threat or a countdown."
                )
                if term.replacement:
                    suggestion = (
                        f"Replace “{excerpt}” with “{replacement}”. {term.rationale}"
                    )
            elif replacement:
                suggestion = f"Replace “{excerpt}” with “{replacement}”. {term.rationale}"
            else:
                suggestion = f"Remove “{excerpt}”. {term.rationale}"
            _add(
                findings,
                Finding(
                    rule_id=rule_id,
                    category=category,
                    severity=term.severity,
                    title=title,
                    excerpt=excerpt,
                    explanation=(
                        f"“{excerpt}” matches {guideline.code}. {term.rationale}"
                    ),
                    suggestion=suggestion,
                    replacement=replacement,
                    apply_mode="replace" if replacement else "advisory",
                    source_type=source_type,
                    source_id=source_id,
                    source_label=source_label,
                    confidence=0.96,
                    span_start=match.start(),
                    span_end=match.end(),
                ),
            )


def _review_claims(text: str, purpose: str, library: Library, findings: list[Finding]) -> None:
    guideline = _guideline(library, "CLM-01")
    source_type, source_id, source_label = _source(guideline)
    for pattern, severity, title, explanation, suggestion in CLAIM_RULES:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if _negated(text, match.start()):
                continue
            _add(
                findings,
                Finding(
                    rule_id="claim.unsupported",
                    category="claims",
                    severity=severity,
                    title=title,
                    excerpt=match.group(0).strip(),
                    explanation=explanation,
                    suggestion=_purpose_prefix(purpose, suggestion),
                    replacement=None,
                    apply_mode="advisory",
                    source_type=source_type,
                    source_id=source_id,
                    source_label=source_label,
                    confidence=0.93,
                    span_start=match.start(),
                    span_end=match.end(),
                ),
            )


def _review_facts(text: str, purpose: str, library: Library, findings: list[Finding]) -> None:
    numbers = _extract_numbers(text)
    by_label = {check.label: check for check in library.checks}
    for number in numbers:
        secret_hits = [
            check
            for check in library.checks
            if check.confidential and check.unit == "%" and number.is_percent and _close(number, check)
        ]
        public_near = [
            check
            for check in library.checks
            if not check.confidential
            and _in_range(number, check)
            and not (_date_year(text, number) and not (1900 <= check.value <= 2039))
            and any(_term_in_window(text, number, term) for term in check.terms)
        ]
        if secret_hits and not any(_close(number, check) for check in public_near):
            check = secret_hits[0]
            guideline = _guideline(library, check.guideline_code)
            counterpart = by_label.get(check.counterpart or "")
            public = (
                _format_value(counterpart)
                if counterpart is not None
                else "the approved public figure"
            )
            public_statement = counterpart.statement if counterpart else "the public fact sheet"
            suggestion = _purpose_prefix(
                purpose,
                f"Remove {number.raw.strip()} from anything a customer could see. "
                f"The figure approved for publication is {public_statement}",
            )
            _add(
                findings,
                Finding(
                    rule_id="fact.embargo",
                    category="facts",
                    severity="critical",
                    title="Possible use of restricted evidence",
                    excerpt=number.raw.strip(),
                    explanation=(
                        f"{number.raw.strip()} matches restricted source “{check.title}”. "
                        f"{check.statement} It is not cleared for publication."
                    ),
                    public_explanation=(
                        f"{number.raw.strip()} matches evidence that is still restricted. "
                        "It must not be published. A reviewer can open the source. "
                        f"The public figure to consider instead: {public_statement}"
                    ),
                    suggestion=suggestion,
                    replacement=public if counterpart is not None else None,
                    apply_mode="replace" if counterpart is not None else "advisory",
                    source_type="fact",
                    source_id=check.fact_id,
                    source_label=check.title,
                    confidence=0.9,
                    span_start=number.start,
                    span_end=number.end,
                ),
            )
            continue
        if not public_near:
            continue
        check = public_near[0]
        if _close(number, check):
            continue
        guideline = _guideline(library, check.guideline_code)
        approved = _format_value(check)
        _add(
            findings,
            Finding(
                rule_id="fact.mismatch",
                category="facts",
                severity="critical",
                title="Figure doesn't match an approved fact",
                excerpt=number.raw.strip(),
                explanation=(
                    f"{number.raw.strip()} sits next to language for “{check.title}”, "
                    f"but the approved value is {approved}. "
                    f"Source: {check.source} (as of {check.as_of}). {check.statement}"
                ),
                suggestion=_purpose_prefix(
                    purpose,
                    f"Use {approved} instead of {number.raw.strip()}. "
                    f"That is the approved “{check.title}” figure from {check.source}.",
                ),
                replacement=approved,
                apply_mode="replace",
                source_type="fact",
                source_id=check.fact_id,
                source_label=f"{check.title} · {guideline.code}",
                confidence=0.9,
                span_start=number.start,
                span_end=number.end,
            ),
        )


def _review_accessibility(text: str, library: Library, findings: list[Finding]) -> None:
    guideline = _guideline(library, "A11Y-01")
    source_type, source_id, source_label = _source(guideline)
    for match in re.finditer(r"\bclick here\b|\bclick the link\b", text, re.IGNORECASE):
        _add(
            findings,
            Finding(
                rule_id="a11y.link",
                category="accessibility",
                severity="critical",
                title="Link text doesn't say where it goes",
                excerpt=match.group(0),
                explanation=(
                    "A11Y-01 requires link text to name the destination. "
                    "“Click here” fails that for screen-reader users and for anyone scanning."
                ),
                suggestion="Replace “click here” with words that name the destination, such as “read the sleep study notes”.",
                replacement="read the sleep study notes",
                apply_mode="replace",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.98,
                span_start=match.start(),
                span_end=match.end(),
            ),
        )
    for match in re.finditer(r"\b(learn more|read more)\b", text, re.IGNORECASE):
        _add(
            findings,
            Finding(
                rule_id="a11y.link",
                category="accessibility",
                severity="warning",
                title="Vague link text",
                excerpt=match.group(0),
                explanation="A11Y-01 asks for descriptive links. “Learn more” doesn't say more about what.",
                suggestion="Name the destination in the link itself.",
                replacement=None,
                apply_mode="advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.8,
                span_start=match.start(),
                span_end=match.end(),
            ),
        )
    phrase = re.compile(r"[A-Z][A-Z0-9\s'’&,:!\-]{7,}[A-Z]")
    covered: list[tuple[int, int]] = []
    for match in phrase.finditer(text):
        letters = [char for char in match.group(0) if char.isalpha()]
        if len(letters) < 8:
            continue
        if sum(char.isupper() for char in letters) / len(letters) < 0.85:
            continue
        excerpt = match.group(0).strip()
        replacement = excerpt[:1] + excerpt[1:].lower()
        _add(
            findings,
            Finding(
                rule_id="a11y.caps",
                category="accessibility",
                severity="warning",
                title="Shouting capitals",
                excerpt=excerpt,
                explanation=(
                    "A run of capitals is harder to read and is announced awkwardly by screen readers. "
                    "A11Y-01 keeps emphasis in the sentence, not in caps."
                ),
                suggestion=f"Set this in sentence case: “{replacement}”.",
                replacement=replacement,
                apply_mode="replace",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.86,
                span_start=match.start(),
                span_end=match.end(),
            ),
        )
        covered.append((match.start(), match.end()))
    for match in re.finditer(r"\b[A-Z]{6,}\b", text):
        if match.group(0) in ALLOW_CAPS:
            continue
        if any(start <= match.start() and match.end() <= end for start, end in covered):
            continue
        excerpt = match.group(0)
        replacement = excerpt[:1] + excerpt[1:].lower()
        _add(
            findings,
            Finding(
                rule_id="a11y.caps",
                category="accessibility",
                severity="warning",
                title="Shouting capitals",
                excerpt=excerpt,
                explanation="A single shouted word still fails A11Y-01 unless it is an established initialism.",
                suggestion=f"Use “{replacement}” unless this is an approved name.",
                replacement=replacement,
                apply_mode="replace",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.84,
                span_start=match.start(),
                span_end=match.end(),
            ),
        )
    for match in re.finditer(r"[^.!?\n]+[.!?]?", text):
        sentence = match.group(0).strip()
        words = re.findall(r"[A-Za-z0-9’']+", sentence)
        if len(words) < 32:
            continue
        _add(
            findings,
            Finding(
                rule_id="a11y.sentence",
                category="accessibility",
                severity="note",
                title="Very long sentence",
                excerpt=sentence[:180],
                explanation=(
                    f"This sentence is about {len(words)} words. A11Y-01 asks for sentences "
                    "most readers can hold in one pass, generally under 32 words."
                ),
                suggestion="Split it into two sentences. Keep the same facts and the same ask.",
                replacement=None,
                apply_mode="advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.7,
                span_start=match.start(),
                span_end=match.end(),
            ),
        )


def _review_visual_text(text: str, library: Library, findings: list[Finding]) -> None:
    visual = _guideline(library, "VIS-01")
    photo = _guideline(library, "VIS-02")
    access = _guideline(library, "A11Y-01")
    for match in re.finditer(r"\bbefore\s*(?:/|and)\s*after\b", text, re.IGNORECASE):
        source_type, source_id, source_label = _source(photo)
        _add(
            findings,
            Finding(
                rule_id="visual.body",
                category="visual",
                severity="critical",
                title="Before-and-after body imagery is not approved",
                excerpt=match.group(0),
                explanation=(
                    "VIS-02 allows natural-light photography of daily rituals. "
                    "Before-and-after body comparisons are off the approved asset list and imply a transformation claim."
                ),
                suggestion="Use an approved everyday scene instead, and drop the transformation framing.",
                replacement=None,
                apply_mode="advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.92,
                span_start=match.start(),
                span_end=match.end(),
            ),
        )
    for match in re.finditer(r"\b(?:stretch(?:ed|ing)?|squash(?:ed|ing)?|distort(?:ed|ing)?)\b[^.]{0,40}\blogo\b|\blogo\b[^.]{0,40}\b(?:stretch(?:ed|ing)?|squash(?:ed|ing)?|distort(?:ed|ing)?)\b", text, re.IGNORECASE):
        source_type, source_id, source_label = _source(visual)
        _add(
            findings,
            Finding(
                rule_id="visual.logo",
                category="visual",
                severity="critical",
                title="Logo is described as distorted",
                excerpt=match.group(0),
                explanation="VIS-01 says the wordmark is used whole, at its natural proportion, with clear space.",
                suggestion="Use the approved wordmark file without stretching, cropping into a square, or recoloring.",
                replacement=None,
                apply_mode="advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.88,
                span_start=match.start(),
                span_end=match.end(),
            ),
        )
    for match in re.finditer(r"#[0-9A-Fa-f]{6}\b", text):
        rgb = _hex_to_rgb(match.group(0))
        nearest, dist = _nearest_palette(rgb, library.palette)
        nearest_name = f"{nearest.name} {nearest.hex}" if nearest else "the palette"
        if dist > 42:
            source_type, source_id, source_label = _source(visual)
            _add(
                findings,
                Finding(
                    rule_id="visual.palette",
                    category="visual",
                    severity="warning",
                    title="Color is outside the approved palette",
                    excerpt=match.group(0),
                    explanation=(
                        f"{match.group(0).upper()} is {dist:.0f} steps away from the nearest approved color ({nearest_name}). "
                        "VIS-01 limits customer-facing color to Forest, Moss, Cream, Ink, and Clay."
                    ),
                    suggestion=f"Swap {match.group(0)} for the nearest approved color, {nearest_name}, if it still fits the layout.",
                    replacement=nearest.hex if nearest else None,
                    apply_mode="replace" if nearest else "advisory",
                    source_type=source_type,
                    source_id=source_id,
                    source_label=source_label,
                    confidence=0.9,
                    span_start=match.start(),
                    span_end=match.end(),
                ),
            )
        ratio = contrast_ratio(rgb, CREAM)
        if 1.25 < ratio < 4.5:
            source_type, source_id, source_label = _source(access)
            _add(
                findings,
                Finding(
                    rule_id="a11y.contrast",
                    category="accessibility",
                    severity="warning",
                    title="Color may fail contrast on cream",
                    excerpt=match.group(0),
                    explanation=(
                        f"{match.group(0).upper()} against the cream field #F4F1EA has a contrast ratio of {ratio:.2f}:1. "
                        "A11Y-01 requires at least 4.5:1 for body text."
                    ),
                    suggestion="Use Ink #1A1A1A or Forest #1B4332 for text and icons on cream.",
                    replacement="#1B4332",
                    apply_mode="replace",
                    source_type=source_type,
                    source_id=source_id,
                    source_label=source_label,
                    confidence=0.78,
                    span_start=match.start(),
                    span_end=match.end(),
                ),
            )


def _review_messaging(text: str, fmt: str, purpose: str, library: Library, findings: list[Finding]) -> None:
    if fmt not in {"social", "email", "web", "ad"}:
        return
    if len(text) < 280:
        return
    pillars = re.search(
        r"\b(study|evidence|research|ritual|practitioner|members?)\b",
        text,
        re.IGNORECASE,
    )
    if pillars:
        return
    guideline = _guideline(library, "MSG-01")
    source_type, source_id, source_label = _source(guideline)
    _add(
        findings,
        Finding(
            rule_id="message.pillar",
            category="messaging",
            severity="note",
            title="No approved messaging pillar",
            excerpt=text[:140].strip(),
            explanation=(
                "MSG-01 asks every customer-facing piece to touch one pillar: evidence, the everyday ritual, "
                "or human support from practitioners. This draft doesn't use that language."
            ),
            suggestion=_purpose_prefix(
                purpose,
                "Add one concrete tie to a pillar, such as the approved sleep study or the role of practitioners.",
            ),
            replacement=None,
            apply_mode="advisory",
            source_type=source_type,
            source_id=source_id,
            source_label=source_label,
            confidence=0.58,
            span_start=0,
            span_end=min(len(text), 140),
        ),
    )


def _review_punctuation(text: str, fmt: str, library: Library, findings: list[Finding]) -> None:
    guideline = _guideline(library, "TONE-01")
    source_type, source_id, source_label = _source(guideline)
    limit = 2 if fmt == "social" else 0
    exclaims = list(re.finditer(r"!", text))
    if len(exclaims) > limit:
        _add(
            findings,
            Finding(
                rule_id="tone.exclaim",
                category="tone",
                severity="note",
                title="Exclamation marks crowd the voice",
                excerpt="!",
                explanation=(
                    f"TONE-01 keeps the voice calm. This {fmt} piece has {len(exclaims)} exclamation marks; "
                    f"the guide allows {'up to two in social posts' if fmt == 'social' else 'none in this format'}."
                ),
                suggestion="Leave at most one exclamation in a social post, and none in email, web, or documents.",
                replacement=None,
                apply_mode="advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.8,
                span_start=exclaims[limit].start(),
                span_end=exclaims[limit].end(),
            ),
        )
    emojis = list(
        re.finditer(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]", text)
    )
    allowed = 1 if fmt == "social" else 0
    if len(emojis) > allowed:
        for match in emojis[allowed:]:
            _add(
                findings,
                Finding(
                    rule_id="tone.emoji",
                    category="tone",
                    severity="warning",
                    title="Emoji doesn't match the voice",
                    excerpt=match.group(0),
                    explanation="TONE-01 is quiet and specific. Emoji stacks read as hype for this brand.",
                    suggestion="Remove the emoji. Let the sentence carry the emphasis.",
                    replacement="",
                    apply_mode="replace",
                    source_type=source_type,
                    source_id=source_id,
                    source_label=source_label,
                    confidence=0.9,
                    span_start=match.start(),
                    span_end=match.end(),
                ),
            )


def _review_image(item: ReviewInput, library: Library, findings: list[Finding]) -> None:
    if item.fmt != "image":
        return
    access = _guideline(library, "A11Y-01")
    visual = _guideline(library, "VIS-01")
    alt = (item.alt_text or "").strip()
    generic = {"image", "photo", "picture", "graphic", "logo", "img", "banner", "pic"}
    if item.asset_intent == "decorative" and alt == "":
        source_type, source_id, source_label = _source(access)
        _add(
            findings,
            Finding(
                rule_id="a11y.alt",
                category="accessibility",
                severity="note",
                title="Marked as decorative",
                excerpt="",
                explanation=(
                    "An empty alt is allowed only when the image adds nothing a reader needs. "
                    "Confirm that before publication."
                ),
                suggestion="If the image carries meaning, write alt text that states it. If it does not, leave the alt empty.",
                replacement=None,
                apply_mode="advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.6,
                span_start=None,
                span_end=None,
            ),
        )
    elif len(alt) < 8 or alt.lower() in generic:
        source_type, source_id, source_label = _source(access)
        _add(
            findings,
            Finding(
                rule_id="a11y.alt",
                category="accessibility",
                severity="critical",
                title="Missing or generic alt text",
                excerpt=alt,
                explanation=(
                    "A11Y-01 requires alt text that says what the image shows and why it is there. "
                    "A filename or the word “image” doesn't do that."
                ),
                suggestion=(
                    "Describe the visible subject and the action, for example "
                    "“Member pouring tea beside a bright window”."
                ),
                replacement=item.body.strip() if len(item.body.strip()) >= 12 else None,
                apply_mode="set_alt" if len(item.body.strip()) >= 12 else "advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.95,
                span_start=None,
                span_end=None,
            ),
        )
    if not item.image_path:
        return
    try:
        from PIL import Image
    except ImportError:
        source_type, source_id, source_label = _source(visual)
        _add(
            findings,
            Finding(
                rule_id="visual.decode",
                category="visual",
                severity="note",
                title="Image could not be inspected",
                excerpt="",
                explanation="The workspace could not import its image decoder, so color and proportion were not checked.",
                suggestion="A reviewer should inspect the file against VIS-01 manually.",
                replacement=None,
                apply_mode="advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.4,
                span_start=None,
                span_end=None,
            ),
        )
        return
    try:
        image = Image.open(item.image_path).convert("RGB")
    except Exception:
        source_type, source_id, source_label = _source(visual)
        _add(
            findings,
            Finding(
                rule_id="visual.decode",
                category="visual",
                severity="warning",
                title="Image file could not be decoded",
                excerpt="",
                explanation="The file did not open as a readable image, so visual checks did not run.",
                suggestion="Re-export as PNG or JPEG and upload again.",
                replacement=None,
                apply_mode="advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.7,
                span_start=None,
                span_end=None,
            ),
        )
        return
    width, height = image.size
    if item.asset_intent == "logo" and height:
        ratio = width / height
        low = library.logo_ratio - library.logo_ratio_tolerance
        high = library.logo_ratio + library.logo_ratio_tolerance
        if not (low <= ratio <= high):
            source_type, source_id, source_label = _source(visual)
            _add(
                findings,
                Finding(
                    rule_id="visual.logo",
                    category="visual",
                    severity="warning",
                    title="Wordmark proportion looks off",
                    excerpt=f"{width}×{height}",
                    explanation=(
                        f"This file is {width}×{height} ({ratio:.2f}:1). "
                        f"The approved wordmark is a horizontal mark around {library.logo_ratio:.1f}:1 "
                        f"(accepted {low:.1f}:1 to {high:.1f}:1). VIS-01 forbids stretching or squashing it."
                    ),
                    suggestion="Export the approved wordmark at its natural proportion.",
                    replacement=None,
                    apply_mode="advisory",
                    source_type=source_type,
                    source_id=source_id,
                    source_label=source_label,
                    confidence=0.8,
                    span_start=None,
                    span_end=None,
                ),
            )
    if item.asset_intent == "photo":
        return
    resample = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    sample = image.resize((40, 40), resample)
    colors = sample.getcolors(40 * 40) or []
    total = sum(count for count, _color in colors) or 1
    off: list[str] = []
    for count, color in sorted(colors, reverse=True):
        share = count / total
        if share < 0.12:
            continue
        nearest, dist = _nearest_palette(color, library.palette)
        if dist > 70 and nearest is not None:
            off.append(
                f"{share:.0%} of sampled pixels are near #{color[0]:02X}{color[1]:02X}{color[2]:02X}, "
                f"{dist:.0f} steps from {nearest.name} {nearest.hex}"
            )
        if len(off) == 3:
            break
    if off:
        source_type, source_id, source_label = _source(visual)
        severity = "critical" if item.asset_intent in {"logo", "graphic"} else "warning"
        _add(
            findings,
            Finding(
                rule_id="visual.image",
                category="visual",
                severity=severity,
                title="Image colors leave the approved palette",
                excerpt=f"{width}×{height}",
                explanation=(
                    "Sampled from a 40×40 grid so the check is explainable. " + " ".join(off) + ". "
                    "VIS-01 expects logo and graphic files to be built from the approved palette."
                ),
                suggestion="Rebuild the graphic with Forest, Moss, Cream, Ink, or Clay. Photographs of real scenes are reviewed separately.",
                replacement=None,
                apply_mode="advisory",
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                confidence=0.76,
                span_start=None,
                span_end=None,
            ),
        )


def review_content(item: ReviewInput, library: Library) -> list[Finding]:
    """Return explainable findings. Does not modify the content."""
    text = item.body or ""
    findings: list[Finding] = []
    _review_terms(text, library, findings)
    _review_claims(text, item.purpose, library, findings)
    _review_facts(text, item.purpose, library, findings)
    _review_accessibility(text, library, findings)
    _review_visual_text(text, library, findings)
    _review_punctuation(text, item.fmt, library, findings)
    _review_messaging(text, item.fmt, item.purpose, library, findings)
    _review_image(item, library, findings)
    severity_order = {"critical": 0, "warning": 1, "note": 2}
    findings.sort(key=lambda finding: (severity_order.get(finding.severity, 9), finding.span_start or 0))
    return findings
