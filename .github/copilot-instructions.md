# Copilot Instructions

> **Canonical guide:** [`docs/ai/README.md`](../docs/ai/README.md) — read that file for full architecture, templates, data-model, and file-location details.

## Quick Reference

**Stack:** Python 3.12 / web.py (Infogami) + FastAPI · Templetor templates · jQuery, Vue 3, Lit · webpack · Solr 9.9

**Dev setup:** `make git && docker compose up` → http://localhost:8080

**Note:** When updating a dependency, ensure it's updated across all dependency locations: requirements*.txt files, package.json files, and .pre-commit-config.yaml.

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
- **CSS:** Stylelint — no hex/named colors, use variables
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

### Code Quality Guidelines

**Code Cleanup:** Remove dead/commented code, unused variables, and redundant comments that restate the code.

**Naming Conventions:** Use descriptive names consistent with project style (snake_case for Python, UpperCamelCase for Vue components). Avoid vague names like `data`, `p`, `item`.

**Idiomatic Code:** Use language idioms (e.g., comprehensions in Python, modern JS features). Simplify verbose patterns like `if len(items) > 0:` → `if items:`.

**DRY:** Abstract repeated code blocks into shared helpers.

**i18n:** Wrap all user-facing strings in translation functions (`$_(...)` or `$:_('...')`). Do not use string concatenation to construct user-visible strings; prefer a single parameterized translation string instead. Use named placeholders (`_('Hello, %(name)s')`) rather than positional placeholders such as `%s` so translators have more context. Use `$:_()` for HTML content to prevent double-escaping.

**FastAPI:** When touching FastAPI code, follow [FastAPI best practices](https://raw.githubusercontent.com/fastapi/fastapi/refs/heads/master/fastapi/.agents/skills/fastapi/SKILL.md) and ensure compliance with their recommendations. When in doubt, reference other parts of our FastAPI codebase for how we do things, as we generally follow established best practices.

**web.py Migration:** When modifying a web.py endpoint that is marked as deprecated, update the corresponding FastAPI endpoint instead. FastAPI is the preferred framework for new features and migrations. Ensure backward compatibility by checking that the same inputs are accepted. Validation errors and status codes may differ slightly, which is acceptable.
