# Copilot Instructions

> **Canonical guide:** [`docs/ai/README.md`](../docs/ai/README.md) — read that file for full architecture, templates, data-model, and file-location details.

## Quick Reference

**Stack:** Python 3.12 / web.py (Infogami) + FastAPI · Templetor templates · jQuery, Vue 3, Lit · LESS/webpack · Solr 9.9

**Dev setup:** `make git && docker compose up` → http://localhost:8080

### Key Commands

```bash
make test-py                # Python tests
npm run test:js             # JS tests
make lint                   # Python lint (ruff)
npm run lint                # JS + CSS lint
npm run lint-fix            # Auto-fix JS/CSS
npm run watch               # Dev mode with hot reload
```

### Code Style

- **Python:** Ruff + Black, line length 162
- **JS:** ESLint, single quotes, no jQuery in new code
- **CSS/LESS:** Stylelint — no hex/named colors, use variables
- **Branches:** `{issue-number}/{type}/{slug}`

### Entry Points

| What | Where |
|---|---|
| App entry | `openlibrary/code.py` |
| FastAPI | `openlibrary/asgi_app.py` |
| Route handlers | `openlibrary/plugins/*/code.py` |
| Templates | `openlibrary/templates/` |
| Core logic | `openlibrary/core/` |
| JS source | `openlibrary/plugins/openlibrary/js/` |
| CSS source | `static/css/` |
