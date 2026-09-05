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

Every hook passes on the host, `mypy` and `generate-pot` included — pre-commit builds an isolated environment per hook, so none of them need Docker. Run `make git` first, though. Both of those hooks read `infogami`, a symlink into the `vendor/infogami` submodule, so while that submodule is unchecked out they fail with `Cannot read file 'infogami'` and `ModuleNotFoundError: No module named 'infogami'`. Everything must pass. Common auto-fixes that pre-commit applies and you should do yourself first:

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

**End-to-end tests** run on the host, not in Docker — Playwright drives a real
browser against the dev stack:

```bash
make e2e-up      # stack, assets, Solr index, browser — once per session
make test-e2e    # run the specs; PLAYWRIGHT_ARGS="search --headed" to narrow
```

`make e2e-up` rebuilds `static/build` from your working tree. Without it the
browser loads the bundles baked into the image from master, so a spec covering
your own JS passes without running your code. See `tests/e2e/README.md`.

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
curl -X POST "http://localhost:8080/people/openlibrary/lists/OL1L/delete.json" -b /tmp/cookies.txt
curl "http://localhost:8080/people/openlibrary/lists/OL1L.json" -b /tmp/cookies.txt
```

**Note:** Sessions expire — always login fresh before testing. In local dev, FastAPI serves on port 8080 and proxies unmatched requests to web.py; both share the same auth system.

### FastAPI and web.py Interaction

Open Library runs two web servers:
- **FastAPI** — primary entry point in local dev (port 8080); unmatched requests proxy to web.py via `openlibrary/fastapi/proxy.py`. All new endpoints go here.
- **web.py** — **Legacy** (web.py / Infogami) — no new endpoints here, use FastAPI. In local dev it is reached through the FastAPI fallback proxy; in production/staging it is still the front door on port 8080 (FastAPI on 18080).

When testing:
- Both servers share the same database
- Session cookies work on both (same auth system)
- FastAPI uses ContextVars (`site.get()`) instead of `web.ctx.site`

Key files for context management:
- `openlibrary/utils/request_context.py` — Contains `site` ContextVar and other request context.
- `openlibrary/plugins/openlibrary/code.py` — Sets up context vars in request processor
