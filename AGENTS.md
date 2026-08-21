# AGENTS.md

> **Canonical guide:** [`docs/ai/README.md`](docs/ai/README.md) — read that file for full architecture, templates, data-model, and file-location details.

## Quick Reference

**Stack:** Python 3.14 / web.py (Infogami) + FastAPI · Templetor (legacy) / **Jinja2 (preferred for new code)** templates · jQuery, Vue 3, Lit · webpack · Solr 10

> 📖 **Guides:** [`docs/ai/i18n.md`](docs/ai/i18n.md) — i18n best practices for Templetor, Jinja, and client-side strings. [`docs/ai/README.md`](docs/ai/README.md) — full architecture and data-model.

> 🏗️ **FastAPI:** When working on FastAPI endpoints, always load the [FastAPI skill](https://raw.githubusercontent.com/fastapi/fastapi/refs/heads/master/fastapi/.agents/skills/fastapi/SKILL.md) and follow the existing patterns in the codebase. Don't invent new architectural patterns — match what's already there.

**Dev setup:** `make git && docker compose up` → http://localhost:8080

### Key Commands

**Before committing**, run pre-commit on your changed files (requires Python 3.14 on host — `brew install python@3.14`):

```bash
pre-commit run --files <file1> <file2> ...
```

The `mypy` and `generate-pot` hooks will fail on the host (they need `infogami` which only lives in Docker) — that's expected. Everything else must pass. Common auto-fixes that pre-commit applies and you should do yourself first:

- **Double quotes** — use `"string"` not `'string'` in all new Python code (the Ruff formatter enforces this)
- **Import order** — imports must be sorted: stdlib → third-party (alphabetical within each group) → local (ruff isort enforces this)
- **No trailing whitespace** on any line
- **Single newline at EOF** — no blank lines at end of file
- **Walrus operator** — prefer `if x := expr:` over `x = expr` / `if x:` (auto-walrus enforces this)
- **Line length** — max 162 chars

The following commands should be run inside docker (with `docker compose run --rm home <command>`). The exception is `test-py-uv`, which runs faster outside Docker using `uv`:

```bash
make test-py-uv             # Python tests (preferred — runs outside Docker with uv)
make test-py                # Python tests

# Run a subset of Python tests by specifying a path:
make test-py-uv PYTEST_ARGS="openlibrary/tests/fastapi/"
# Or directly: uv run --with-requirements requirements_test.txt pytest openlibrary/tests/fastapi/

npm run test:js             # JS tests
make lint                   # Python lint (ruff)
npm run lint                # JS + CSS lint
npm run lint-fix            # Auto-fix JS/CSS
npm run watch               # Dev mode with hot reload
```

### Code Style

- **Python:** Ruff for linting and `ruff format` for formatting, line length 162, double quotes
- **JS:** ESLint, single quotes, no jQuery in new code
- **CSS:** Stylelint — no hex/named colors, use variables
- **i18n (Internationalization):** Do not split sentences into separate translatable strings/fragments with HTML links. Instead, use single, unified translatable strings with Python formatting placeholders (e.g. `%(link_start)s` / `%(link_end)s`) so translators can position links according to the target language's grammatical structure.
- **Branches:** `{issue-number}/{type}/{slug}`

### Entry Points

| What | Where |
|---|---|
| App entry | `openlibrary/code.py` |
| FastAPI | `openlibrary/asgi_app.py` |
| Route handlers | `openlibrary/plugins/*/code.py` (legacy web.py) · **FastAPI routers** (preferred): `openlibrary/fastapi/*.py` |
| Templates | `openlibrary/templates/` |
| JS source | `openlibrary/plugins/openlibrary/js/` |
| CSS source | `static/css/` |

### Testing Authenticated Endpoints with curl

The dev environment has a pre-configured test user:

| Property | Value |
|----------|-------|
| Username | `openlibrary` |
| Password | `openlibrary` |
| Key | `/people/openlibrary` |

1. **Login to get a session cookie:**
```bash
curl -s -c /tmp/cookies.txt -X POST "http://localhost:8080/account/login.json" \
  -H "Content-Type: application/json" \
  -d '{"username":"openlibrary","password":"openlibrary"}'

# View the cookie file
cat /tmp/cookies.txt
# Example output:
# # Netscape HTTP Cookie File
# localhost  FALSE   /       FALSE   0       session /people/openlibrary,2026-01-18T17:25:46,7897f\$841a3bd2f8e9a5ca46f505fa557d57bd
```

2. **Use the session cookie in subsequent requests:**
```bash
# Just use -b to send the cookie automatically (no manual extraction needed)
curl -X POST "http://localhost:18080/people/openlibrary/lists/OL1L/delete.json" -b /tmp/cookies.txt
curl "http://localhost:18080/people/openlibrary/lists/OL1L.json" -b /tmp/cookies.txt
```

**Note:** Sessions expire — always login fresh before testing. Both web.py (port 8080) and FastAPI (port 18080) share the same auth system.

### FastAPI and web.py Interaction

Open Library runs two web servers in parallel:
- **web.py** (port 8080) — **Legacy** (web.py / Infogami) — no new endpoints here, use FastAPI
- **FastAPI** (port 18080) — New async endpoints via nginx proxy

When testing:
- Both servers share the same database
- Session cookies work on both (same auth system)
- FastAPI uses ContextVars (`site.get()`) instead of `web.ctx.site`

Key files for context management:
- `openlibrary/utils/request_context.py` — Contains `site` ContextVar and other request context.
- `openlibrary/plugins/openlibrary/code.py` — Sets up context vars in request processor
