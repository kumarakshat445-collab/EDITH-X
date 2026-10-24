"""Pull reviewable text out of uploaded documents. Files never leave the workspace."""

from __future__ import annotations

import io
import re
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in {"p", "div", "h1", "h2", "h3", "li", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    parser = _VisibleText()
    parser.feed(raw)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_docx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    texts: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            texts.append(node.text)
        elif node.tag.endswith("}p"):
            texts.append("\n")
    return re.sub(r"\n{3,}", "\n\n", "".join(texts)).strip()


def extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(pages)).strip()


def extract_upload(filename: str, data: bytes) -> tuple[str, list[str]]:
    """Return extracted text and human-readable warnings."""
    name = (filename or "").lower()
    warnings: list[str] = []
    if name.endswith((".txt", ".md", ".markdown")):
        return data.decode("utf-8", errors="replace").strip(), warnings
    if name.endswith((".html", ".htm")):
        raw = data.decode("utf-8", errors="replace")
        text = html_to_text(raw)
        warnings.append("HTML tags were removed for the prose checks. Accessibility checks still read the markup.")
        return text or raw, warnings
    if name.endswith(".docx"):
        try:
            text = extract_docx(data)
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise ValueError(f"Could not read that document ({exc}). Paste the copy instead.") from exc
        if not text:
            warnings.append("The document had no readable text.")
        return text, warnings
    if name.endswith(".pdf"):
        try:
            text = extract_pdf(data)
        except Exception as exc:  # pypdf raises several parser errors
            raise ValueError(f"Could not read that PDF ({exc}). Paste the copy instead.") from exc
        warnings.append("PDF text extraction can drop layout. Confirm the draft before you rely on the findings.")
        return text, warnings
    raise ValueError("Use a .txt, .md, .html, .docx, or .pdf file, or paste the copy.")
