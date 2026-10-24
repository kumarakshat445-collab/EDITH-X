# Inkloom

Brand governance before publication. Inkloom checks drafts against a workspace library of guidelines, approved facts, terminology, and assets, then keeps a person in charge of every correction, dismissal, approval, and publish.

The demo workspace is **Lumen & Grove**, a wellness brand with a calm voice and a strict claims policy.

## Run

```bash
./scripts/cloud-agent-install.sh
source .venv/bin/activate
uvicorn inkloom.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` and enter as a creator, reviewer, manager, or admin. Roles are enforced on the server.

## What a review covers

- Tone, terminology, and messaging pillars
- Figures checked against approved facts, including restricted evidence
- Unsupported promotional claims
- Visual palette, wordmark proportion, and photography rules
- Accessibility: link text, alt text, contrast, and shouted capitals

Suggestions are proposals. Applying one creates a new version and keeps the previous wording. Creators cannot approve their own work. Critical findings block approval until they are corrected or a different reviewer dismisses them with a reason. Only a manager publishes, and only after approval.

Confidential guidelines and facts are hidden from creators. Reviewers can open them, and those reads are written to the audit log. The checker is a local rules engine: drafts are not sent to an external AI service.

Supported drafts are pasted text, `.txt`, `.md`, `.html`, and PNG, JPEG, WEBP, or GIF images. PDF is refused with an explanation.

## Tests

```bash
source .venv/bin/activate
pytest
```
