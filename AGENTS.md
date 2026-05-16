# AGENTS.md

> **Canonical guide:** [`docs/ai/README.md`](docs/ai/README.md) — read that file for full architecture, templates, data-model, and file-location details.

## Quick Reference

**Stack:** Python 3.12 / web.py (Infogami) + FastAPI · Templetor templates · jQuery, Vue 3, Lit · webpack · Solr 9.9

**Dev setup:** `make git && docker compose up` → http://localhost:8080

### Key Commands

**Before committing**, run pre-commit on your changed files (requires Python 3.12 on host — `brew install python@3.12`):

```bash
pre-commit run --files <file1> <file2> ...
```

The `mypy` and `generate-pot` hooks will fail on the host (they need `infogami` which only lives in Docker) — that's expected. Everything else must pass. Common auto-fixes that pre-commit applies and you should do yourself first:

- **Double quotes** — use `"string"` not `'string'` in all new Python code (black/ruff-format enforces this)
- **Import order** — imports must be sorted: stdlib → third-party (alphabetical within each group) → local (ruff isort enforces this)
- **No trailing whitespace** on any line
- **Single newline at EOF** — no blank lines at end of file
- **Walrus operator** — prefer `if x := expr:` over `x = expr` / `if x:` (auto-walrus enforces this)
- **Line length** — max 162 chars

The following commands should always be run inside docker like this: `docker compose run --rm home <command>`

```bash
make test-py                # Python tests
npm run test:js             # JS tests
make lint                   # Python lint (ruff)
npm run lint                # JS + CSS lint
npm run lint-fix            # Auto-fix JS/CSS
npm run watch               # Dev mode with hot reload
```

### Code Style

- **Python:** Ruff + Black, line length 162, double quotes
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
- **web.py** (port 8080) — Legacy Infogami app
- **FastAPI** (port 18080) — New async endpoints via nginx proxy

When testing:
- Both servers share the same database
- Session cookies work on both (same auth system)
- FastAPI uses ContextVars (`site.get()`) instead of `web.ctx.site`

Key files for context management:
- `openlibrary/utils/request_context.py` — Contains `site` ContextVar and other request context.
- `openlibrary/plugins/openlibrary/code.py` — Sets up context vars in request processor
