# AI Coding Guide for Open Library

This is the canonical AI-agent reference for the Open Library codebase. Tool-specific bridge files (`CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`) point here. If you update project guidance, update **this file** and leave the bridges alone.

## Project Overview

Open Library (openlibrary.org) is an open, editable library catalog by the Internet Archive. It's built on **Infogami**, a wiki framework using **web.py**, with a gradual migration to **FastAPI**. The frontend uses server-rendered templates (Templetor), jQuery, Vue 3 components, and Lit web components.

## Development Setup

Run `make git` to initialize the Infogami submodule, then `docker compose up` and visit http://localhost:8080. The FastAPI server runs on port 18080.

## Build Commands

Build targets are in the `Makefile`. Key dev workflow commands:

```bash
make all                    # Build everything (css, js, components, lit-components, i18n)
npm run watch               # Dev mode with hot reload (CSS + JS)
npm run watch:lit-components # Watch Lit components
```

## Testing

```bash
# Python tests (excludes integration tests by default)
make test-py
pytest . --ignore=infogami --ignore=vendor --ignore=node_modules

# Run a single Python test file
pytest openlibrary/core/tests/test_models.py

# Run a specific test
pytest openlibrary/core/tests/test_models.py::test_function_name -xvs

# JavaScript tests
npm run test:js

# i18n validation
make test-i18n

# All tests
make test
```

## Linting

```bash
# Python (ruff)
make lint

# JavaScript + CSS
npm run lint
npm run lint:js              # ESLint only
npm run lint:css             # Stylelint only

# Auto-fix
npm run lint-fix
```

Pre-commit hooks are configured. Install with `pre-commit install`.

## Architecture

### Backend: Infogami + web.py (legacy) → FastAPI (new)

The app is loaded through Infogami's plugin system. `openlibrary/code.py` is the main entry point, which loads plugins from `openlibrary/plugins/`. Each plugin's `code.py` registers routes, templates, and macros.

**Routes (web.py/Infogami):** Defined as classes extending `delegate.page` in plugin `code.py` files. The class attribute `path` is a regex pattern, and `GET`/`POST` methods handle requests.

**Routes (FastAPI):** New endpoints go in `openlibrary/fastapi/`. The ASGI app in `openlibrary/asgi_app.py` mounts FastAPI alongside the legacy WSGI app.

**Key plugins:**
- `plugins/openlibrary/` — Main plugin: site routes, JS source files (`js/`), processors
- `plugins/upstream/` — Core features: book editing, accounts, borrowing, models
- `plugins/worksearch/` — Solr search integration
- `plugins/books/` — Books API (JSON/RDF)
- `plugins/importapi/` — Book import API
- `plugins/admin/` — Admin panel

### Templates (Templetor)

Templates live in `openlibrary/templates/` and use web.py's Templetor syntax (not Jinja2):
- `$def with (arg1, arg2)` — template arguments
- `$variable` or `$:variable` (unescaped) — variable interpolation
- `$if`, `$for`, `$while` — control flow
- `$code:` — inline Python blocks
- Macros in `openlibrary/macros/` extend templates

Route handlers render templates via `render_template("path/name", args)` which maps to `templates/path/name.html`.

### Core Business Logic

`openlibrary/core/` contains the data layer:
- `models.py` — Data models (Work, Edition, Author, etc.)
- `db.py` — Database access
- `lending.py` — Book lending/availability
- `bookshelves.py`, `ratings.py`, `booknotes.py` — User content features
- `vendors.py` — External vendor integrations
- `ia.py` — Internet Archive integration

### Frontend

- **CSS:** LESS files in `static/css/`, compiled via webpack. Files prefixed `page-` are page-specific. Shared styles in `static/css/base/` and `static/css/less/`.
- **JavaScript:** Source in `openlibrary/plugins/openlibrary/js/`, bundled via webpack to `static/build/js/`.
- **Vue components:** `openlibrary/components/*.vue`, built with Vite to `static/build/components/`.
- **Lit web components:** `openlibrary/components/lit/`, built with Vite to `static/build/lit-components/`.
- **jQuery** is still widely used but new code should avoid it (ESLint no-jquery plugin active).

### Search

Apache Solr 9.9 powers search. Config in `conf/solr/`. Indexing logic in `openlibrary/solr/`. The `solr-updater` service keeps the index current.

### Data Model

Open Library uses a wiki-style versioned data store (Infobase) via the `vendor/infogami/` git submodule. The core entities are:
- **Works** (`/works/OL123W`) — Abstract representation of a book (title, author associations)
- **Editions** (`/books/OL456M`) — A specific publication of a Work (ISBN, publisher, format)
- **Authors** (`/authors/OL789A`) — Author records linked from Works

A Work has many Editions. This is the central relationship in the data model.

## Code Style

- **Python:** Ruff linter, Black formatter. Line length 162. Target Python 3.12.
- **JavaScript:** ESLint with single quotes, `prefer-template`, `eqeqeq`. No jQuery in new code.
- **CSS/LESS:** Stylelint enforces strict value rules — no hex colors, no named colors (use variables). Strict values required for `font-family`, `background-color`, `z-index`, `color`.
- **Branch naming:** `{issue-number}/{type}/{slug}` (e.g., `123/fix/login-redirect`)

## Topic Guides

These companion docs cover specific areas in depth:

- [Web Component Standards](web-components.md) — Lit component conventions, naming, accessibility, events

## Key File Locations

| What | Where |
|---|---|
| Python app entry | `openlibrary/code.py` |
| FastAPI app | `openlibrary/asgi_app.py` |
| Plugin route handlers | `openlibrary/plugins/*/code.py` |
| HTML templates | `openlibrary/templates/` |
| Template macros | `openlibrary/macros/` |
| Core models & logic | `openlibrary/core/` |
| JS source | `openlibrary/plugins/openlibrary/js/` |
| CSS/LESS source | `static/css/` |
| Vue components | `openlibrary/components/*.vue` |
| Lit components | `openlibrary/components/lit/` |
| Python tests | `tests/`, `openlibrary/**/tests/` |
| JS tests | `tests/unit/js/`, `openlibrary/plugins/openlibrary/js/**/*.test.js` |
| Docker config | `docker/`, `compose.yaml` |
| Solr config | `conf/solr/` |
| i18n translations | `openlibrary/i18n/` |
| Infogami submodule | `vendor/infogami/` |

## Contributing to These Docs

This `docs/ai/` directory is the single source of truth for AI-agent guidance. The root-level bridge files (`CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`) are thin pointers — they rarely need updating.

**To add a new topic:**
1. Create `docs/ai/<topic>.md` (one domain per file, e.g., `solr.md`, `templates.md`).
2. Add a link to it in the **Topic Guides** section above.
3. No changes to the bridge files are needed — agents follow links from this README.

**To update general guidance:** edit this file (`docs/ai/README.md`). Only update the bridge files if a key command or style rule changes, since those are inlined in the bridges for quick reference.

**To remove a tool's bridge:** delete the bridge file when the team stops using that tool.
