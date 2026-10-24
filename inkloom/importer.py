"""Turn pasted source material into draft records a person still has to approve."""

from __future__ import annotations

import csv
import io
import re


def _chunks(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _field_map(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in block.splitlines():
        match = re.match(r"^([A-Z][A-Z ]{1,30}):\s*(.*)$", line.strip())
        if match:
            if current:
                fields[current] = "\n".join(lines).strip()
            current = match.group(1).strip()
            lines = [match.group(2)]
        elif current:
            lines.append(line)
    if current:
        fields[current] = "\n".join(lines).strip()
    return fields


def _split_list(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[|\n]", value) if part.strip()]


def _yes(value: str) -> bool:
    return value.strip().lower() in {"yes", "true", "y", "1", "confidential"}


def parse_import(kind: str, text: str) -> list[dict]:
    text = text.strip()
    if not text:
        return []
    if kind == "terms" and text.lower().startswith("preferred,"):
        return _parse_term_csv(text)
    if kind == "facts" and re.search(r"(?m)^FACT:", text):
        return _parse_facts(text)
    if kind == "terms" and re.search(r"(?m)^PREFERRED:", text):
        return _parse_terms(text)
    if kind == "assets" and re.search(r"(?m)^ASSET:", text):
        return _parse_assets(text)
    if kind == "guidelines":
        return _parse_guidelines(text)
    raise ValueError(
        "The paste did not match this library. Guidelines use markdown headings. "
        "Facts start with FACT:. Terms start with PREFERRED: or a CSV header. Assets start with ASSET:."
    )


def _parse_guidelines(text: str) -> list[dict]:
    chunks = re.split(r"(?m)^#{1,3}\s+", text)
    items = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        title = lines[0].strip()[:160]
        body_lines = []
        category = "messaging"
        severity = "medium"
        good = ""
        bad = ""
        for line in lines[1:]:
            lowered = line.strip()
            cat = re.match(r"^category:\s*(.+)$", lowered, re.I)
            sev = re.match(r"^severity:\s*(.+)$", lowered, re.I)
            g = re.match(r"^good:\s*(.+)$", lowered, re.I)
            b = re.match(r"^bad:\s*(.+)$", lowered, re.I)
            if cat:
                category = cat.group(1).strip().lower()[:40]
            elif sev:
                severity = sev.group(1).strip().lower()
            elif g:
                good = g.group(1).strip()
            elif b:
                bad = b.group(1).strip()
            else:
                body_lines.append(line)
        body = "\n".join(body_lines).strip()
        if not title or not body:
            continue
        if severity not in {"info", "low", "medium", "high", "critical"}:
            severity = "medium"
        items.append(
            {
                "title": title,
                "body": body,
                "category": category or "messaging",
                "severity": severity,
                "match_type": "keywords",
                "match_value": "",
                "suggestion": "",
                "good_example": good,
                "bad_example": bad,
                "confidential": False,
                "note": "Imported as a draft. Add match patterns before you approve it, or it will not flag anything.",
            }
        )
    if not items:
        raise ValueError("No headed sections were found. Start each guideline with a markdown heading.")
    return items


def _parse_facts(text: str) -> list[dict]:
    items = []
    for block in _chunks(text):
        fields = _field_map(block)
        statement = fields.get("FACT", "")
        if not statement:
            continue
        items.append(
            {
                "topic": fields.get("TOPIC", statement[:80]),
                "statement": statement,
                "source_label": fields.get("SOURCE", "Imported source"),
                "severity": fields.get("SEVERITY", "high").lower(),
                "contradicts": _split_list(fields.get("AVOID", "")),
                "supports": _split_list(fields.get("SAY", "")),
                "suggested": fields.get("SUGGESTED", ""),
                "replacement": fields.get("REPLACEMENT", ""),
                "confidential": _yes(fields.get("CONFIDENTIAL", "")),
                "note": "Imported as a draft. Reviews ignore it until someone approves it.",
            }
        )
    if not items:
        raise ValueError("No FACT: blocks were found.")
    return items


def _parse_terms(text: str) -> list[dict]:
    items = []
    for block in _chunks(text):
        fields = _field_map(block)
        preferred = fields.get("PREFERRED", "")
        if not preferred:
            continue
        items.append(
            {
                "preferred": preferred,
                "avoid": _split_list(fields.get("AVOID", "")),
                "definition": fields.get("DEFINITION", ""),
                "context": fields.get("CONTEXT", ""),
                "severity": fields.get("SEVERITY", "medium").lower(),
                "confidential": _yes(fields.get("CONFIDENTIAL", "")),
                "note": "Imported as a draft. Reviews ignore it until someone approves it.",
            }
        )
    if not items:
        raise ValueError("No PREFERRED: blocks were found.")
    return items


def _parse_term_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    items = []
    for row in reader:
        preferred = (row.get("preferred") or "").strip()
        if not preferred:
            continue
        avoid_raw = row.get("avoid") or ""
        items.append(
            {
                "preferred": preferred,
                "avoid": [part.strip() for part in avoid_raw.split(";") if part.strip()],
                "definition": (row.get("definition") or "").strip(),
                "context": (row.get("context") or "").strip(),
                "severity": (row.get("severity") or "medium").strip().lower(),
                "confidential": _yes(row.get("confidential") or ""),
                "note": "Imported as a draft. Reviews ignore it until someone approves it.",
            }
        )
    if not items:
        raise ValueError("The CSV had no preferred terms.")
    return items


def _parse_assets(text: str) -> list[dict]:
    items = []
    for block in _chunks(text):
        fields = _field_map(block)
        name = fields.get("ASSET", "")
        if not name:
            continue
        items.append(
            {
                "name": name,
                "kind": fields.get("KIND", "layout").lower(),
                "description": fields.get("DESCRIPTION", ""),
                "usage_rules": fields.get("RULES", ""),
                "color_hex": fields.get("HEX", ""),
                "do_not": _split_list(fields.get("DO NOT", "")),
                "confidential": _yes(fields.get("CONFIDENTIAL", "")),
                "note": "Imported as a draft. Reviews ignore it until someone approves it.",
            }
        )
    if not items:
        raise ValueError("No ASSET: blocks were found.")
    return items
