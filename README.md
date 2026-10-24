# Inkloom

Inkloom is a brand-governance desk. It reviews a draft against the organisation’s approved guidelines, facts, terminology, and assets, explains every finding, and leaves publication to a person who did not write the piece.

The demo workspace is the fictional skincare brand **Vela Collective**. Nothing in it is a real company, and reviews do not call an external AI service.

## Run

```bash
./scripts/cloud-agent-install.sh
source .venv/bin/activate
uvicorn inkloom.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

## Demo accounts

| Person | Role | Email | Password |
| --- | --- | --- | --- |
| Maya Chen | Creator | maya.chen@vela.example | draft-well |
| Leah North | Agency creator | leah.north@northco.example | agency-well |
| Jules Okafor | Reviewer | jules.okafor@vela.example | review-well |
| Samira Dal | Manager | samira.dal@vela.example | manage-well |
| Adrian Cole | Admin | adrian.cole@vela.example | admin-well |

## What a review covers

- Tone, terminology, and required messaging
- Approved facts, contradictions, and facts past their review date
- Promotional claims that no approved fact supports
- Logo misuse, palette distance, and image size
- Text alternatives, contrast, type size, link text, color-only cues, and reading grade
- Social posts, email, web pages, documents (txt, md, html, docx, pdf), and PNG, JPEG, WebP, or GIF images

Suggestions replace only the flagged words, and only when someone saves a new revision. High and critical findings stay open until a reviewer decides them. Publishing is a separate step for a manager who is not the author.

Confidential sources are hidden from creator accounts. Opening one writes an audit row. The disclosure page inside the app states that analysis stays in the workspace.

## Tests

```bash
source .venv/bin/activate
pytest
```
