"""Explainable brand checks. This module never calls an external service.

Every finding names the check and the approved source that justified it.
Suggestions replace a span or give advice. They are never applied here.
"""

from __future__ import annotations

import math
import re
from html.parser import HTMLParser

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SOURCE_RANK = {"fact": 4, "term": 3, "asset": 3, "guideline": 2, "policy": 1}

CLAIM_RULES = [
    {
        "key": "guarantee",
        "pattern": r"\b(guaranteed|guarantee|money[- ]back)\b",
        "label": "Absolute guarantee",
        "severity": "critical",
        "why": "An absolute guarantee is a promotional claim. It needs an approved fact that explicitly allows that promise.",
    },
    {
        "key": "superlative",
        "pattern": r"(?:#\s?1|number one|(?<![\w-])(?:best|greatest|leading)(?![\w-]))",
        "label": "Unsupported ranking",
        "severity": "high",
        "why": "A ranking or “best” claim needs an approved fact. None of the approved facts grant this wording.",
    },
    {
        "key": "therapeutic",
        "pattern": r"\b(cure|cures|cured|curing|treat|treats|treated|heal|heals|healing)\b",
        "label": "Therapeutic claim",
        "severity": "critical",
        "why": "Treatment and cure language is a promotional health claim. It is flagged unless an approved fact allows those exact words.",
    },
    {
        "key": "absolute",
        "pattern": r"\b100\s?%\b",
        "label": "Absolute percentage",
        "severity": "high",
        "why": "“100%” is an absolute claim. It stays flagged until an approved fact supports that figure.",
    },
    {
        "key": "safety",
        "pattern": r"\bchemical[- ]free\b",
        "label": "Absolute safety claim",
        "severity": "high",
        "why": "“Chemical-free” is an absolute safety claim and is not an approved description.",
    },
    {
        "key": "organic",
        "pattern": r"\borganic\b",
        "label": "Organic certification claim",
        "severity": "high",
        "why": "Organic is a certification claim. It needs an approved fact that the product holds that certification.",
    },
    {
        "key": "clinical",
        "pattern": r"\b(clinically proven|clinically proved|medically proven)\b",
        "label": "Clinical-proof claim",
        "severity": "critical",
        "why": "“Clinically proven” tells the reader a study proved an outcome. That wording needs an approved fact.",
    },
    {
        "key": "overnight",
        "pattern": r"\bovernight\b",
        "label": "Time-bound outcome",
        "severity": "high",
        "why": "A time-bound result such as “overnight” is a promotional claim unless an approved fact states that timing.",
    },
]

NAMED_COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "navy": (0, 0, 128),
}

DEFAULT_A11Y = {
    "require_alt": True,
    "max_grade_buffer": 1.5,
    "min_contrast": 4.5,
    "min_font_px": 14,
    "flag_click_here": True,
    "flag_all_caps": True,
}
DEFAULT_GRADES = {"social": 8, "email": 9, "web": 12, "document": 12, "image": 8}
DEFAULT_VISUAL = {"max_delta_e": 40, "min_width": 600}
POOR_ALT = re.compile(
    r"^(image|photo|picture|banner|img|screenshot|graphic|logo|[a-z0-9_-]+\.(png|jpe?g|webp|gif))$",
    re.I,
)


def review(
    *,
    body: str,
    fmt: str,
    channel: str,
    purpose: str,
    alt_text: str,
    placement_notes: str,
    decorative: bool,
    asset: dict | None,
    image: dict | None,
    guidelines: list[dict],
    facts: list[dict],
    terms: list[dict],
    assets: list[dict],
    reading_grades: dict | None,
) -> dict:
    findings: list[dict] = []
    warnings: list[str] = []
    checks = ["tone", "terminology", "messaging", "facts", "claims", "visual", "accessibility"]
    grades = {**DEFAULT_GRADES, **(reading_grades or {})}
    prose = body or ""

    fact_spans = _fact_findings(findings, prose, facts)
    _term_findings(findings, prose, terms, fact_spans)
    _guideline_findings(findings, prose, guidelines, warnings)
    _claim_findings(findings, prose, guidelines, facts, fact_spans)
    _required_findings(findings, prose, guidelines, warnings)
    _accessibility_findings(
        findings=findings,
        body=prose,
        fmt=fmt,
        alt_text=alt_text,
        decorative=decorative,
        guidelines=guidelines,
        grades=grades,
        warnings=warnings,
    )
    _visual_findings(
        findings=findings,
        body=prose,
        fmt=fmt,
        channel=channel,
        placement_notes=placement_notes,
        asset=asset,
        image=image,
        guidelines=guidelines,
        assets=assets,
        warnings=warnings,
    )
    _caps_findings(findings, prose, guidelines)

    findings = _dedupe(findings)[:40]
    findings.sort(key=lambda item: (item["start_pos"] is None, item["start_pos"] or 0, -SEVERITY_RANK[item["severity"]]))

    approved_guidelines = [g for g in guidelines if g.get("status", "approved") == "approved"]
    return {
        "findings": findings,
        "meta": {
            "engine": "inkloom-rules-1",
            "external_services": [],
            "purpose": purpose,
            "checks": checks,
            "sources_consulted": {
                "guidelines": len(approved_guidelines),
                "facts": len(facts),
                "terms": len(terms),
                "assets": len(assets),
            },
            "warnings": warnings,
            "truncated": False,
            "reading_grade": _grade_value(html_to_text(prose) if "<" in prose else prose),
        },
    }


def analyze_image(path: str) -> dict:
    from PIL import Image

    with Image.open(path) as image:
        frame = image.convert("RGB")
        width, height = frame.size
        small = frame.resize((48, 48))
        colors = small.getcolors(48 * 48) or []
    colors.sort(key=lambda item: item[0], reverse=True)
    total = sum(count for count, _rgb in colors) or 1
    dominant = []
    for count, rgb in colors[:6]:
        dominant.append(
            {
                "hex": "#{:02x}{:02x}{:02x}".format(*rgb),
                "share": round(count / total, 3),
                "rgb": list(rgb),
            }
        )
    return {"width": width, "height": height, "dominant": dominant}


def _base_finding(**kwargs) -> dict:
    finding = {
        "category": "messaging",
        "severity": "medium",
        "excerpt": "",
        "explanation": "",
        "suggestion": "",
        "suggestion_mode": "advice",
        "replaces": "",
        "replace_start": None,
        "replace_end": None,
        "replace_text": None,
        "source_type": "policy",
        "source_id": None,
        "source_label": "",
        "source_excerpt": "",
        "confidential_source": False,
        "pattern_key": "",
        "start_pos": None,
        "end_pos": None,
    }
    finding.update(kwargs)
    if finding["severity"] not in SEVERITY_RANK:
        finding["severity"] = "medium"
    return finding


def _phrase_re(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.I)


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - 28) : start]
    return bool(re.search(r"\b(not|no|never|isn't|isnt|aren't|arent|without|n't)\b", window, re.I))


def _span_replace(text: str, start: int, end: int, replacement: str) -> dict:
    replace_start, replace_end = start, end
    if replacement == "" and start > 0 and text[start - 1] == " ":
        replace_start = start - 1
    elif replacement == "" and end < len(text) and text[end : end + 1] == " ":
        replace_end = end + 1
    return {
        "suggestion_mode": "replace",
        "replaces": "span",
        "replace_start": replace_start,
        "replace_end": replace_end,
        "replace_text": text[replace_start:replace_end],
        "suggestion": replacement,
        "start_pos": start,
        "end_pos": end,
        "excerpt": text[start:end],
    }


def _match_case(source: str, replacement: str) -> str:
    if not source or not replacement:
        return replacement
    if source.isupper():
        return replacement.upper()
    if source[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _normalize_contradicts(raw) -> list[dict]:
    items = []
    for entry in raw or []:
        if isinstance(entry, str):
            items.append({"phrase": entry, "replacement": None})
        elif isinstance(entry, dict) and entry.get("phrase"):
            items.append({"phrase": entry["phrase"], "replacement": entry.get("replacement")})
    return items


def _fact_findings(findings: list[dict], text: str, facts: list[dict]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for fact in facts:
        status = fact.get("status", "approved")
        if status not in {"approved", "expired"}:
            continue
        confidential = bool(fact.get("confidential"))
        statement = fact.get("statement") or ""
        source_excerpt = "" if confidential else f"{statement} — {fact.get('source_label', '')}".strip(" —")
        contradicts = _normalize_contradicts(fact.get("contradicts"))
        contradicts.sort(key=lambda item: len(item["phrase"]), reverse=True)
        used: list[tuple[int, int]] = []
        for entry in contradicts:
            pattern = _phrase_re(entry["phrase"])
            for match in pattern.finditer(text):
                if _negated(text, match.start()) or _overlaps_any(match.start(), match.end(), used):
                    continue
                used.append((match.start(), match.end()))
                spans.append((match.start(), match.end()))
                replacement = entry.get("replacement")
                if replacement is None:
                    replacement = fact.get("replacement") or None
                if confidential or not replacement:
                    extra = _base_finding(
                        category="facts",
                        severity="critical" if confidential else fact.get("severity") or "high",
                        explanation=_confidential_explanation(match.group(0), expired=status == "expired")
                        if confidential
                        else (
                            f"“{match.group(0)}” contradicts the approved fact “{fact.get('topic')}”. "
                            f"{statement} "
                            + ("This fact is also past its review date. " if status == "expired" else "")
                            + "The suggestion is wording you can edit. Nothing is changed until you save a revision."
                        ),
                        suggestion="Remove this from the public draft and ask a reviewer for the cleared wording."
                        if confidential
                        else (fact.get("suggested") or f"Remove “{match.group(0)}” or replace it with the approved fact."),
                        suggestion_mode="advice",
                        source_type="fact",
                        source_id=fact.get("id"),
                        source_label=fact.get("topic") or "Approved fact",
                        source_excerpt=f"{statement} — {fact.get('source_label', '')}".strip(" —"),
                        confidential_source=confidential,
                        pattern_key=f"fact:{fact.get('id')}:{entry['phrase'].lower()}",
                        start_pos=match.start(),
                        end_pos=match.end(),
                        excerpt=match.group(0),
                    )
                else:
                    shown = _match_case(match.group(0), replacement)
                    extra = _base_finding(
                        category="facts",
                        severity=fact.get("severity") or "high",
                        explanation=(
                            f"“{match.group(0)}” contradicts the approved fact “{fact.get('topic')}”. "
                            f"{statement} "
                            + ("This fact is also past its review date. " if status == "expired" else "")
                            + "Only the flagged words would change. The rest of the draft stays as written."
                        ),
                        source_type="fact",
                        source_id=fact.get("id"),
                        source_label=fact.get("topic") or "Approved fact",
                        source_excerpt=source_excerpt,
                        confidential_source=False,
                        pattern_key=f"fact:{fact.get('id')}:{entry['phrase'].lower()}",
                        **_span_replace(text, match.start(), match.end(), shown),
                    )
                findings.append(extra)
        if status == "expired":
            for phrase in fact.get("supports") or []:
                pattern = _phrase_re(phrase)
                for match in pattern.finditer(text):
                    if _negated(text, match.start()) or _overlaps_any(match.start(), match.end(), used):
                        continue
                    used.append((match.start(), match.end()))
                    spans.append((match.start(), match.end()))
                    replacement = fact.get("replacement") or ""
                    payload = _base_finding(
                        category="facts",
                        severity="high",
                        explanation=(
                            _confidential_explanation(match.group(0), expired=True)
                            if confidential
                            else (
                                f"“{match.group(0)}” matches a fact that is past its review date and is no longer approved. "
                                f"{statement} Publishing it would repeat outdated information."
                            )
                        ),
                        source_type="fact",
                        source_id=fact.get("id"),
                        source_label=fact.get("topic") or "Expired fact",
                        source_excerpt=f"{statement} — {fact.get('source_label', '')}".strip(" —"),
                        confidential_source=confidential,
                        pattern_key=f"fact-expired:{fact.get('id')}",
                        start_pos=match.start(),
                        end_pos=match.end(),
                        excerpt=match.group(0),
                    )
                    if replacement and not confidential:
                        payload.update(_span_replace(text, match.start(), match.end(), _match_case(match.group(0), replacement)))
                    else:
                        payload["suggestion_mode"] = "advice"
                        payload["suggestion"] = fact.get("suggested") or "Replace this with the current approved fact."
                    findings.append(payload)
    return spans


def _confidential_explanation(excerpt: str, expired: bool = False) -> str:
    extra = " The fact is also past its review date." if expired else ""
    return (
        f"“{excerpt}” is not cleared for public copy.{extra} "
        "The match comes from a confidential approved fact. Creator accounts see that a confidential source matched. "
        "Reviewers can open the source. Inkloom does not copy the confidential statement into this explanation."
    )


def _overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    for left, right in spans:
        if min(end, right) - max(start, left) > 0:
            return True
    return False


def _term_findings(findings: list[dict], text: str, terms: list[dict], blocked: list[tuple[int, int]]) -> None:
    for term in terms:
        if term.get("status", "approved") != "approved":
            continue
        preferred = term.get("preferred") or ""
        for avoid in term.get("avoid") or []:
            pattern = _phrase_re(avoid)
            match = next((item for item in pattern.finditer(text) if not _negated(text, item.start())), None)
            if not match or _overlaps_any(match.start(), match.end(), blocked):
                continue
            count = len(list(pattern.finditer(text)))
            more = f" It appears {count} times. The first is shown." if count > 1 else ""
            confidential = bool(term.get("confidential"))
            definition = term.get("definition") or ""
            replacement = _match_case(match.group(0), preferred)
            payload = _base_finding(
                category="terminology",
                severity=term.get("severity") or "medium",
                explanation=(
                    f"“{match.group(0)}” is on the avoid list. The approved term is “{preferred}”. "
                    + ("" if confidential else (definition + " " if definition else ""))
                    + (f"Context: {term.get('context')}. " if term.get("context") and not confidential else "")
                    + "The rest of the sentence is left alone."
                    + more
                ),
                source_type="term",
                source_id=term.get("id"),
                source_label=preferred,
                source_excerpt=definition,
                confidential_source=confidential,
                pattern_key=f"term:{term.get('id')}:{avoid.lower()}",
            )
            if confidential:
                payload.update(
                    {
                        "suggestion_mode": "advice",
                        "suggestion": "Replace the avoided wording with the approved term. A reviewer can confirm the cleared word.",
                        "start_pos": match.start(),
                        "end_pos": match.end(),
                        "excerpt": match.group(0),
                    }
                )
            else:
                payload.update(_span_replace(text, match.start(), match.end(), replacement))
            findings.append(payload)
            blocked.append((match.start(), match.end()))


def _guideline_findings(findings: list[dict], text: str, guidelines: list[dict], warnings: list[str]) -> None:
    for guide in guidelines:
        if guide.get("status", "approved") != "approved":
            continue
        match_type = guide.get("match_type")
        if match_type == "keywords":
            phrases = _keyword_list(guide.get("match_value"))
            for phrase in phrases:
                pattern = _phrase_re(phrase)
                match = next((item for item in pattern.finditer(text) if not _negated(text, item.start())), None)
                if not match:
                    continue
                count = sum(1 for _ in pattern.finditer(text))
                more = f" It appears {count} times in this draft." if count > 1 else ""
                confidential = bool(guide.get("confidential"))
                if confidential:
                    explanation = (
                        f"“{match.group(0)}” matches a confidential guideline. "
                        "Creator accounts do not see the rule text. Reviewers can open the source. "
                        "Deleting or replacing the flagged word keeps the surrounding sentence."
                        + more
                    )
                else:
                    hint = f" {guide.get('suggestion')}" if guide.get("suggestion") else ""
                    explanation = (
                        f"“{match.group(0)}” matches the guideline “{guide.get('title')}”. "
                        f"{guide.get('body')}{more}{hint} "
                        "Deleting or replacing the flagged word keeps the surrounding sentence."
                    )
                findings.append(
                    _base_finding(
                        category=guide.get("category") or "tone",
                        severity=guide.get("severity") or "medium",
                        explanation=explanation,
                        source_type="guideline",
                        source_id=guide.get("id"),
                        source_label=guide.get("title") or "Guideline",
                        source_excerpt=guide.get("body") or "",
                        confidential_source=confidential,
                        pattern_key=f"guideline:{guide.get('id')}:{phrase.lower()}",
                        **_span_replace(text, match.start(), match.end(), ""),
                    )
                )
        elif match_type == "regex":
            pattern_text = (guide.get("match_value") or "").strip()
            if not pattern_text or len(pattern_text) > 180:
                warnings.append(f"Guideline “{guide.get('title')}” has an unusable pattern and was skipped.")
                continue
            try:
                pattern = re.compile(pattern_text, re.I)
            except re.error:
                warnings.append(f"Guideline “{guide.get('title')}” has an invalid pattern and was skipped.")
                continue
            match = next((item for item in pattern.finditer(text) if not _negated(text, item.start())), None)
            if not match:
                continue
            confidential = bool(guide.get("confidential"))
            explanation = (
                f"“{match.group(0)}” matches a confidential guideline. The rule text is hidden from creator accounts."
                if confidential
                else f"“{match.group(0)}” matches the guideline “{guide.get('title')}”. {guide.get('body')}"
            )
            findings.append(
                _base_finding(
                    category=guide.get("category") or "messaging",
                    severity=guide.get("severity") or "medium",
                    explanation=explanation,
                    suggestion=guide.get("suggestion") or "Rewrite this so it follows the guideline. The draft is not changed until you save a revision.",
                    suggestion_mode="advice",
                    source_type="guideline",
                    source_id=guide.get("id"),
                    source_label=guide.get("title") or "Guideline",
                    source_excerpt=guide.get("body") or "",
                    confidential_source=confidential,
                    pattern_key=f"guideline:{guide.get('id')}",
                    start_pos=match.start(),
                    end_pos=match.end(),
                    excerpt=match.group(0),
                )
            )


def _keyword_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            import json

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return [part.strip() for part in re.split(r"[\n|]", text) if part.strip()]
    return []


def _policy(guidelines: list[dict], match_type: str) -> dict | None:
    for guide in guidelines:
        if guide.get("status", "approved") == "approved" and guide.get("match_type") == match_type:
            return guide
    return None


def _claim_findings(findings: list[dict], text: str, guidelines: list[dict], facts: list[dict], blocked: list[tuple[int, int]]) -> None:
    policy = _policy(guidelines, "claims")
    label = policy.get("title") if policy else "Promotional-claim check"
    excerpt_source = policy.get("body") if policy else "No approved claim policy is on file. Absolute promotional claims are still flagged so they are not published silently."
    source_type = "guideline" if policy else "policy"
    source_id = policy.get("id") if policy else None
    for rule in CLAIM_RULES:
        pattern = re.compile(rule["pattern"], re.I)
        for match in pattern.finditer(text):
            if _negated(text, match.start()):
                continue
            if _overlaps_any(match.start(), match.end(), blocked):
                continue
            if _covered(text, match.start(), match.end(), rule["key"], facts):
                continue
            blocked.append((match.start(), match.end()))
            findings.append(
                _base_finding(
                    category="claims",
                    severity=rule["severity"],
                    explanation=(
                        f"{rule['why']} Flagged text: “{match.group(0)}”. "
                        f"Source: {label}. "
                        "You can delete the claim or type a replacement. Inkloom will not publish either choice for you."
                    ),
                    source_type=source_type,
                    source_id=source_id,
                    source_label=label,
                    source_excerpt=excerpt_source or "",
                    confidential_source=bool(policy and policy.get("confidential")),
                    pattern_key=f"claim:{rule['key']}",
                    **_span_replace(text, match.start(), match.end(), ""),
                )
            )


def _covered(text: str, start: int, end: int, key: str, facts: list[dict]) -> bool:
    sentence = _sentence(text, start, end)
    for fact in facts:
        if fact.get("status") != "approved":
            continue
        if key not in (fact.get("covers") or []):
            continue
        for phrase in fact.get("supports") or []:
            if phrase and re.search(re.escape(phrase), sentence, re.I):
                return True
    return False


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start), text.rfind("\n", 0, start))
    left = 0 if left < 0 else left + 1
    rights = [pos for pos in (text.find(".", end), text.find("!", end), text.find("?", end), text.find("\n", end)) if pos != -1]
    right = min(rights) + 1 if rights else len(text)
    return text[left:right]


def _required_findings(findings: list[dict], text: str, guidelines: list[dict], warnings: list[str]) -> None:
    for guide in guidelines:
        if guide.get("status", "approved") != "approved" or guide.get("match_type") != "required_when":
            continue
        spec = guide.get("match_value")
        if isinstance(spec, str):
            import json

            try:
                spec = json.loads(spec)
            except json.JSONDecodeError:
                warnings.append(f"Guideline “{guide.get('title')}” has invalid messaging rules and was skipped.")
                continue
        if not isinstance(spec, dict):
            continue
        trigger = spec.get("trigger") or ""
        required = spec.get("required") or ""
        addition = spec.get("addition") or required
        if not trigger or not required:
            continue
        try:
            triggered = re.search(trigger, text, re.I)
        except re.error:
            warnings.append(f"Guideline “{guide.get('title')}” has an invalid trigger and was skipped.")
            continue
        if not triggered or re.search(re.escape(required), text, re.I):
            continue
        findings.append(
            _base_finding(
                category=guide.get("category") or "messaging",
                severity=guide.get("severity") or "medium",
                excerpt=required,
                explanation=(
                    f"The draft mentions “{triggered.group(0)}”, and the guideline “{guide.get('title')}” "
                    f"asks for “{required}” whenever that comes up. Those words are not in the draft. "
                    f"{guide.get('body')}"
                ),
                suggestion="\n" + addition.strip(),
                suggestion_mode="replace",
                replaces="append",
                replace_start=len(text),
                replace_end=len(text),
                replace_text="",
                source_type="guideline",
                source_id=guide.get("id"),
                source_label=guide.get("title") or "Guideline",
                source_excerpt=guide.get("body") or "",
                confidential_source=bool(guide.get("confidential")),
                pattern_key=f"guideline:{guide.get('id')}",
            )
        )


class _TagFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[dict] = []
        self.anchors: list[str] = []
        self.current_anchor: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        attr = {key.lower(): (value or "") for key, value in attrs}
        if tag == "img":
            self.images.append(attr)
        if tag == "a":
            self.current_anchor = []
        if tag in {"p", "span", "div", "h1", "h2", "li", "a"} and "style" in attr:
            self.images.append({"__style__": attr["style"], "__tag__": tag})

    def handle_endtag(self, tag):
        if tag == "a" and self.current_anchor is not None:
            self.anchors.append("".join(self.current_anchor).strip())
            self.current_anchor = None

    def handle_data(self, data):
        if self.current_anchor is not None:
            self.current_anchor.append(data)


def _accessibility_findings(
    *,
    findings: list[dict],
    body: str,
    fmt: str,
    alt_text: str,
    decorative: bool,
    guidelines: list[dict],
    grades: dict,
    warnings: list[str],
) -> None:
    policy = _policy(guidelines, "accessibility")
    spec = dict(DEFAULT_A11Y)
    raw = policy.get("match_value") if policy else None
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                spec.update(parsed)
        except json.JSONDecodeError:
            warnings.append("The accessibility guideline has invalid settings and the workspace defaults were used.")
    elif isinstance(raw, dict):
        spec.update(raw)
    source = {
        "source_type": "guideline" if policy else "policy",
        "source_id": policy.get("id") if policy else None,
        "source_label": policy.get("title") if policy else "Accessibility check",
        "source_excerpt": policy.get("body") if policy else "Workspace accessibility checks.",
        "confidential_source": bool(policy and policy.get("confidential")),
    }

    if fmt == "image" and spec.get("require_alt", True):
        alt = (alt_text or "").strip()
        if decorative and alt:
            findings.append(
                _base_finding(
                    category="accessibility",
                    severity="low",
                    excerpt=alt,
                    explanation=(
                        "This image is marked decorative, so the text alternative should be empty. "
                        "A description will be read aloud as if the image added meaning. Clear the alt text in the draft fields."
                    ),
                    suggestion="Clear the text alternative.",
                    suggestion_mode="advice",
                    pattern_key="a11y:decorative-alt",
                    **source,
                )
            )
        elif not decorative and not alt:
            findings.append(
                _base_finding(
                    category="accessibility",
                    severity="high",
                    excerpt="(no text alternative)",
                    explanation="This image has no text alternative. People who cannot see it will not get the message. Describe the information the image adds, or mark it decorative if it adds none.",
                    suggestion="Describe what the image communicates, in the same tone as the caption.",
                    suggestion_mode="advice",
                    pattern_key="a11y:missing-alt",
                    **source,
                )
            )
        elif not decorative and POOR_ALT.match(alt):
            findings.append(
                _base_finding(
                    category="accessibility",
                    severity="medium",
                    excerpt=alt,
                    explanation=f"“{alt}” describes the file, not the content. A text alternative should say what the reader needs from the image.",
                    suggestion="Replace the file name with a short description of the information in the image.",
                    suggestion_mode="advice",
                    pattern_key="a11y:poor-alt",
                    **source,
                )
            )

    if "<" in body:
        _html_accessibility(findings, body, spec, source)
        visible = html_to_text(body)
    else:
        visible = body
        if spec.get("flag_click_here", True):
            for match in re.finditer(r"\bclick here\b", body, re.I):
                findings.append(
                    _base_finding(
                        category="accessibility",
                        severity="medium",
                        explanation="“Click here” does not say where the link goes. Link text should name the destination.",
                        suggestion="Name the destination in the link text.",
                        suggestion_mode="advice",
                        pattern_key="a11y:click-here",
                        start_pos=match.start(),
                        end_pos=match.end(),
                        excerpt=match.group(0),
                        **source,
                    )
                )
                break

    for match in re.finditer(r"\b(?:shown|marked|highlighted|written) in (?:red|green|blue|yellow|orange|purple)\b", body, re.I):
        findings.append(
            _base_finding(
                category="accessibility",
                severity="medium",
                explanation=f"“{match.group(0)}” asks the reader to use color alone. Some people will not see that color. Add a word, label, or shape as well.",
                suggestion="Add a text label so the meaning does not depend on color.",
                suggestion_mode="advice",
                pattern_key="a11y:color-only",
                start_pos=match.start(),
                end_pos=match.end(),
                excerpt=match.group(0),
                **source,
            )
        )
        break

    grade = _grade_value(visible)
    limit = float(grades.get(fmt, grades.get("document", 12)))
    buffer = float(spec.get("max_grade_buffer", 1.5))
    if grade is not None and grade > limit + buffer:
        sentence = _longest_sentence(visible)
        start = body.find(sentence[:40]) if sentence else -1
        severity = "high" if grade > limit + 4 else "medium"
        findings.append(
            _base_finding(
                category="accessibility",
                severity=severity,
                excerpt=(sentence[:180] + ("…" if len(sentence) > 180 else "")) if sentence else visible[:180],
                explanation=(
                    f"Estimated reading grade is {grade:.1f}. This {fmt} channel asks for about grade {limit:.0f} or clearer. "
                    "Long sentences and specialist words are pushing the grade up. "
                    "Inkloom has not rewritten the draft, because a shorter version could change the meaning."
                ),
                suggestion="Split the longest sentence and swap specialist words for the approved plain-language term where you have one. Then run the review again.",
                suggestion_mode="advice",
                pattern_key="a11y:reading-grade",
                start_pos=start if start >= 0 else None,
                end_pos=(start + len(sentence)) if start >= 0 else None,
                **source,
            )
        )


def _html_accessibility(findings: list[dict], body: str, spec: dict, source: dict) -> None:
    if re.search(r"<html\b", body, re.I) and not re.search(r"<html\b[^>]*\blang\s*=", body, re.I):
        findings.append(
            _base_finding(
                category="accessibility",
                severity="medium",
                excerpt="<html>",
                explanation="This page’s html element has no lang attribute. Screen readers use it to choose pronunciation.",
                suggestion='Add lang="en" (or the real language) to the html element.',
                suggestion_mode="advice",
                pattern_key="a11y:lang",
                **source,
            )
        )
    for match in re.finditer(r"<img\b[^>]*>", body, re.I):
        tag = match.group(0)
        alt = re.search(r"\balt\s*=\s*(['\"])(.*?)\1", tag, re.I)
        if alt is None:
            findings.append(
                _base_finding(
                    category="accessibility",
                    severity="high",
                    excerpt=tag[:180],
                    explanation="An image in the markup has no alt attribute. Add a text alternative, or alt=\"\" if the image is decorative.",
                    suggestion='Add an alt attribute that states the information, or alt="" if the image is decorative.',
                    suggestion_mode="advice",
                    pattern_key="a11y:img-alt",
                    start_pos=match.start(),
                    end_pos=match.end(),
                    **source,
                )
            )
        elif not alt.group(2).strip():
            continue
        elif POOR_ALT.match(alt.group(2).strip()):
            findings.append(
                _base_finding(
                    category="accessibility",
                    severity="medium",
                    excerpt=alt.group(2),
                    explanation=f"The alt text “{alt.group(2)}” names the file rather than the content.",
                    suggestion="Describe the information the image adds.",
                    suggestion_mode="advice",
                    pattern_key="a11y:poor-alt",
                    start_pos=match.start(),
                    end_pos=match.end(),
                    **source,
                )
            )
    if spec.get("flag_click_here", True):
        for match in re.finditer(r">\s*click here\s*<", body, re.I):
            findings.append(
                _base_finding(
                    category="accessibility",
                    severity="medium",
                    excerpt="click here",
                    explanation="Link text says “click here”, which does not name the destination.",
                    suggestion="Use the name of the page or action as the link text.",
                    suggestion_mode="advice",
                    pattern_key="a11y:click-here",
                    start_pos=match.start(),
                    end_pos=match.end(),
                    **source,
                )
            )
            break
    min_contrast = float(spec.get("min_contrast", 4.5))
    min_font = float(spec.get("min_font_px", 14))
    for match in re.finditer(r"style\s*=\s*(['\"])(.*?)\1", body, re.I):
        style = match.group(2)
        color = _css_color(style, "color")
        background = _css_color(style, "background")
        if color and background:
            ratio = contrast_ratio(color, background)
            if ratio < min_contrast:
                findings.append(
                    _base_finding(
                        category="accessibility",
                        severity="high",
                        excerpt=style[:180],
                        explanation=(
                            f"The text and background colors in this style measure about {ratio:.2f}:1. "
                            f"The accessibility rule asks for at least {min_contrast:.1f}:1 so the words stay readable."
                        ),
                        suggestion="Darken the text or lighten the background until the contrast reaches the guideline.",
                        suggestion_mode="advice",
                        pattern_key="a11y:contrast",
                        start_pos=match.start(),
                        end_pos=match.end(),
                        **source,
                    )
                )
        size = re.search(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", style, re.I)
        if size and float(size.group(1)) < min_font:
            findings.append(
                _base_finding(
                    category="accessibility",
                    severity="medium",
                    excerpt=size.group(0),
                    explanation=(
                        f"The style sets type at {size.group(1)}px. The accessibility guideline asks for at least {min_font:.0f}px in body copy."
                    ),
                    suggestion=f"Raise the body size to {min_font:.0f}px or larger.",
                    suggestion_mode="advice",
                    pattern_key="a11y:font-size",
                    start_pos=match.start(),
                    end_pos=match.end(),
                    **source,
                )
            )


def _css_color(style: str, prop: str) -> tuple[int, int, int] | None:
    if prop == "background":
        match = re.search(r"background(?:-color)?\s*:\s*([^;]+)", style, re.I)
    else:
        match = re.search(r"(?:^|;)\s*color\s*:\s*([^;]+)", style, re.I)
    if not match:
        return None
    return parse_color(match.group(1).strip())


def parse_color(value: str) -> tuple[int, int, int] | None:
    value = value.strip().lower()
    hex_match = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", value)
    if hex_match:
        raw = hex_match.group(1)
        if len(raw) == 3:
            raw = "".join(ch * 2 for ch in raw)
        return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    rgb_match = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", value)
    if rgb_match:
        return tuple(int(part) for part in rgb_match.groups())  # type: ignore[return-value]
    return NAMED_COLORS.get(value.split()[0])


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        srgb = value / 255
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(part) for part in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    left, right = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(left, right), min(left, right)
    return (lighter + 0.05) / (darker + 0.05)


def _grade_value(text: str) -> float | None:
    words = re.findall(r"[A-Za-z']+", text or "")
    sentences = [part for part in re.split(r"[.!?]+", text or "") if part.strip()]
    if len(words) < 20 or not sentences:
        return None
    syllables = sum(_syllables(word) for word in words)
    return 0.39 * (len(words) / len(sentences)) + 11.8 * (syllables / len(words)) - 15.59


def _syllables(word: str) -> int:
    groups = re.findall(r"[aeiouy]+", word.lower())
    count = len(groups)
    if word.lower().endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def _longest_sentence(text: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if not parts:
        return ""
    return max(parts, key=lambda part: len(part.split()))


def html_to_text(raw: str) -> str:
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in {"script", "style"}:
                self.skip += 1

        def handle_endtag(self, tag):
            if tag in {"script", "style"} and self.skip:
                self.skip -= 1

        def handle_data(self, data):
            if not self.skip:
                self.parts.append(data)

    parser = Parser()
    parser.feed(raw)
    return " ".join("".join(parser.parts).split())


def _visual_findings(
    *,
    findings: list[dict],
    body: str,
    fmt: str,
    channel: str,
    placement_notes: str,
    asset: dict | None,
    image: dict | None,
    guidelines: list[dict],
    assets: list[dict],
    warnings: list[str],
) -> None:
    policy = _policy(guidelines, "visual")
    spec = dict(DEFAULT_VISUAL)
    raw = policy.get("match_value") if policy else None
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                spec.update(parsed)
        except json.JSONDecodeError:
            warnings.append("The visual guideline has invalid settings and the workspace defaults were used.")
    elif isinstance(raw, dict):
        spec.update(raw)
    source = {
        "source_type": "guideline" if policy else "policy",
        "source_id": policy.get("id") if policy else None,
        "source_label": policy.get("title") if policy else "Visual consistency check",
        "source_excerpt": policy.get("body") if policy else "",
        "confidential_source": bool(policy and policy.get("confidential")),
    }
    notes = f"{placement_notes}\n{body}"
    logo = None
    if asset and asset.get("kind") == "logo":
        logo = asset
    elif re.search(r"\blogo\b", notes, re.I):
        logo = next((item for item in assets if item.get("kind") == "logo" and item.get("status", "approved") == "approved"), None)
    if logo:
        rules = logo.get("rules") or {}
        for phrase in rules.get("do_not") or []:
            match = _phrase_re(phrase).search(notes)
            if not match:
                continue
            confidential = bool(logo.get("confidential"))
            findings.append(
                _base_finding(
                    category="visual",
                    severity="high",
                    excerpt=match.group(0),
                    explanation=(
                        f"“{match.group(0)}” conflicts with the usage rules for the asset “{logo.get('name')}”. "
                        + ("" if confidential else f"{logo.get('usage_rules') or ''} ")
                        + "The asset file is not modified by this finding."
                    ),
                    suggestion=f"Place the asset as approved, without “{phrase}”.",
                    suggestion_mode="advice",
                    source_type="asset",
                    source_id=logo.get("id"),
                    source_label=logo.get("name") or "Asset",
                    source_excerpt=logo.get("usage_rules") or "",
                    confidential_source=confidential,
                    pattern_key=f"asset:{logo.get('id')}:{phrase.lower()}",
                    start_pos=body.find(match.group(0)) if match.group(0) in body else None,
                    end_pos=(body.find(match.group(0)) + len(match.group(0))) if match.group(0) in body else None,
                )
            )
    allow_natural = bool(asset and (asset.get("rules") or {}).get("allow_natural_color"))
    if image and image.get("dominant") and not allow_natural and fmt == "image":
        palette = []
        for item in assets:
            if item.get("kind") == "color" and item.get("status", "approved") == "approved" and item.get("color_hex"):
                rgb = parse_color(item["color_hex"])
                if rgb:
                    palette.append((item, rgb))
        if palette:
            limit = float(spec.get("max_delta_e", 40))
            for color in image["dominant"]:
                if color.get("share", 0) < 0.15:
                    continue
                rgb = tuple(color["rgb"])
                nearest, distance = min(
                    ((item, delta_e(rgb, brand)) for item, brand in palette),
                    key=lambda pair: pair[1],
                )
                if distance > limit:
                    findings.append(
                        _base_finding(
                            category="visual",
                            severity="medium",
                            excerpt=color["hex"],
                            explanation=(
                                f"About {round(color['share'] * 100)}% of this image is {color['hex']}. "
                                f"The nearest approved color is {nearest.get('name')} ({nearest.get('color_hex')}), "
                                f"and the rough color distance is {distance:.0f}. "
                                f"The visual guideline allows about {limit:.0f}. "
                                "This is a screen-color estimate, not a press proof."
                            ),
                            suggestion="Recolor toward the approved palette, or attach an approved asset that allows natural color.",
                            suggestion_mode="advice",
                            pattern_key="visual:off-palette",
                            **source,
                        )
                    )
                    break
        min_width = int(spec.get("min_width") or 0)
        width = int(image.get("width") or 0)
        if min_width and width and width < min_width and ("paid" in channel.lower() or "hero" in channel.lower() or fmt == "image"):
            findings.append(
                _base_finding(
                    category="visual",
                    severity="low",
                    excerpt=f"{width}px",
                    explanation=(
                        f"The file is {width} pixels wide. The visual guideline asks for at least {min_width}px "
                        "so the asset stays sharp in this channel."
                    ),
                    suggestion="Export the image at the approved size and upload that file as a new revision.",
                    suggestion_mode="advice",
                    pattern_key="visual:low-resolution",
                    **source,
                )
            )
    elif image and image.get("error"):
        warnings.append(image["error"])


def _caps_findings(findings: list[dict], text: str, guidelines: list[dict]) -> None:
    tone = None
    for guide in guidelines:
        if guide.get("status", "approved") == "approved" and guide.get("category") == "tone":
            tone = guide
            break
    source_label = tone.get("title") if tone else "Tone check"
    for match in re.finditer(r"[A-Z][A-Z\s'!?]{11,}", text):
        letters = [ch for ch in match.group(0) if ch.isalpha()]
        if len(letters) < 12:
            continue
        if sum(ch.isupper() for ch in letters) / len(letters) < 0.85:
            continue
        if any(
            item["category"] == "tone"
            and item["start_pos"] is not None
            and _overlap_ratio(item["start_pos"], item["end_pos"], match.start(), match.end()) > 0.4
            for item in findings
        ):
            continue
        findings.append(
            _base_finding(
                category="tone",
                severity="low",
                explanation=(
                    f"“{match.group(0).strip()}” is set in capitals. "
                    f"The tone guideline “{source_label}” asks for a calm, precise voice. "
                    "Capitals read as shouting and are harder to read."
                ),
                suggestion="Use sentence case.",
                suggestion_mode="advice",
                source_type="guideline" if tone else "policy",
                source_id=tone.get("id") if tone else None,
                source_label=source_label,
                source_excerpt=tone.get("body") if tone else "",
                confidential_source=bool(tone and tone.get("confidential")),
                pattern_key="tone:caps",
                start_pos=match.start(),
                end_pos=match.end(),
                excerpt=match.group(0).strip(),
            )
        )
        break


def _overlap_ratio(a0: int, a1: int, b0: int, b1: int) -> float:
    inter = min(a1, b1) - max(a0, b0)
    if inter <= 0:
        return 0
    shorter = min(a1 - a0, b1 - b0)
    return inter / shorter if shorter else 0


def delta_e(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(_rgb_to_lab(rgb1), _rgb_to_lab(rgb2), strict=True)))


def _rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    def pivot(channel: float) -> float:
        channel = channel / 255
        return ((channel + 0.055) / 1.055) ** 2.4 if channel > 0.04045 else channel / 12.92

    red, green, blue = (pivot(channel) for channel in rgb)
    x = (red * 0.4124 + green * 0.3576 + blue * 0.1805) / 0.95047
    y = red * 0.2126 + green * 0.7152 + blue * 0.0722
    z = (red * 0.0193 + green * 0.1192 + blue * 0.9505) / 1.08883

    def f(value: float) -> float:
        return value ** (1 / 3) if value > 0.008856 else (7.787 * value) + (16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy) - 16, 500 * (fx - fy), 200 * (fy - fz)


def _same_issue(left: dict, right: dict) -> bool:
    same_excerpt = left["excerpt"].strip().lower() == right["excerpt"].strip().lower()
    if left["pattern_key"] == right["pattern_key"] and same_excerpt:
        return True
    if not same_excerpt or left["start_pos"] is None or right["start_pos"] is None:
        return False
    len_left = (left["end_pos"] or 0) - left["start_pos"]
    len_right = (right["end_pos"] or 0) - right["start_pos"]
    if min(len_left, len_right) <= 0:
        return False
    if min(len_left, len_right) / max(len_left, len_right) < 0.6:
        return False
    return _overlap_ratio(left["start_pos"], left["end_pos"], right["start_pos"], right["end_pos"]) >= 0.8


def _better(left: dict, right: dict) -> dict:
    if SEVERITY_RANK[left["severity"]] != SEVERITY_RANK[right["severity"]]:
        return left if SEVERITY_RANK[left["severity"]] > SEVERITY_RANK[right["severity"]] else right
    if SOURCE_RANK.get(left["source_type"], 0) != SOURCE_RANK.get(right["source_type"], 0):
        return left if SOURCE_RANK.get(left["source_type"], 0) > SOURCE_RANK.get(right["source_type"], 0) else right
    return left


def _dedupe(findings: list[dict]) -> list[dict]:
    kept: list[dict] = []
    for finding in findings:
        merged = False
        for index, existing in enumerate(kept):
            if _same_issue(finding, existing):
                kept[index] = _better(finding, existing)
                merged = True
                break
        if not merged:
            kept.append(finding)
    return kept
