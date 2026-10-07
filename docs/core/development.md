# Development Environment & Workflow

> **Status:** partial
> **Sources:** `raw/openlibrary-wiki/Developer-Resources/Getting-Started.md`, `Testing.md`, `Writing-Bots.md`, `Endpoints.md`
> **Last ingested:** 2026-06-27
> **Source trust:** Low-medium — Getting-Started.md explicitly marked "very out of date, most of it is wrong." Commands verified against patterns; flag stale sections.

Open Library's dev environment is Docker-first. The canonical setup reference is `docker/README.md` in the main repo. What follows is what's reliably true across source vintages plus explicit staleness flags.

---

## Local Setup

⚠️ STALE — Getting-Started.md is self-described as "very out of date." Canonical setup is at `github.com/internetarchive/openlibrary/tree/master/docker#readme`.

**What is reliably true:**
```bash
docker compose up                          # start all services
docker compose up --no-deps -d solr        # start one service detached
docker compose logs web                    # tail logs for a service
docker compose exec web bash               # shell into container
docker compose run --rm home make test     # run all tests
```

**Admin login for local dev:**
```
URL:      http://localhost:8080
Username: openlibrary@example.com
Password: admin123
```

**Admin interface:** `http://localhost:8080/admin`

**Test as a non-admin user:** In admin → People → select `AccountBot` → "Login as this user." To make AccountBot a librarian: edit `http://localhost:8080/usergroup/librarians?m=edit` and add `/people/AccountBot`.

### `fast_web` is the host-facing port, not `web` (changed 2026-08-26)

**As of [#13423](https://github.com/internetarchive/openlibrary/pull/13423) (`c22815fa8`, RayBB,
2026-08-26), `web` no longer publishes a host port at all — `fast_web` is the single dev entrypoint
and reverse-proxies everything it doesn't serve itself back to web.py.** That commit deleted the
`ports:` block from *both* `web` (`${WEB_PORT:-8080}:8080`) and `fast_web`
(`${FAST_WEB_PORT:-18080}:8080`) in `compose.yaml`, and added a single
`${FAST_WEB_PORT:-8080}:8080` to `fast_web` in `compose.override.yaml`. Consequences:

- **`WEB_PORT` is dead in dev.** It survives only in `compose.production.yaml` /
  `compose.staging.yaml`. Setting it locally silently does nothing. Use `FAST_WEB_PORT` to move the
  dev port (`WEB_DEBUG_PORT`/`FAST_WEB_DEBUG_PORT` still control the two debugger ports).
- **`fast_web` must be in your `up` list.** `docker compose up -d web infobase db memcached home
  covers` — the recipe most docs and older agent skills still carry — brings up a fully healthy stack
  that is unreachable from the host. `docker compose logs web` cheerfully shows gunicorn `Listening
  at: http://0.0.0.0:8080` while `curl` returns `000`, because nothing is mapped. Check `docker ps`
  for a `->8080/tcp` row before debugging the app itself.
- **One port now serves both route families.** FastAPI routes are handled by `fast_web` directly;
  anything else is forwarded by `openlibrary/fastapi/proxy.py`'s `proxy_to_webpy()` to
  `http://web:8080`. So there is no longer a reason to publish two ports. A dev traceback for a
  web.py page shows the inner `http://web:8080/...` request — that's the proxy hop, not a bug.
- The same commit removed `openlibrary/plugins/openlibrary/deprecated_handler.py` and reworked
  `openlibrary/asgi_app.py`; the proxy's tests are in `openlibrary/tests/fastapi/test_proxy.py`.

**Book/edition pages need solr *and* mockservices**, which arrive via the dependency graph (`web` →
`db`, `infobase`, `mockservices`; `home` → `db`, `solr`). Trimming the stack with `--no-deps` to dodge
port collisions makes missing containers masquerade as application bugs: an edition page 500s with
`httpx.ConnectError` to `http://solr:8983/solr/openlibrary/get?id=...` without solr, and with an
`UnboundLocalError` referencing `http://mockservices:8090/services/loans/loan/` without mockservices.
Shift the ports, not the dependency graph.

**Cover images 404 locally?** Set `coverstore_public_url: https://covers.openlibrary.org/` in `conf/openlibrary.yml` to pull from production instead.

**Cache not clearing?** `docker compose restart memcached`

**Config file:** `conf/openlibrary.yml` — add to `.git/info/exclude` so local changes don't show as dirty.

---

## Testing

```bash
# All tests (Python + JS)
docker compose run web make test

# Specific pytest file
docker compose run web pytest openlibrary/plugins/importapi/tests/test_import_validator.py

# JS lint only
docker compose exec web npm run lint

# JS lint autofix
docker compose exec web npm run lint:fix

# Regenerate i18n POT
docker compose run --rm home python ./scripts/i18n-messages extract
```

**Running vitest on the host (outside Docker), e.g. in a fresh worktree.** Verified 2026-09-28 on #13745 [PR lead auto-assign]. Three traps, each of which fails quietly or blames the wrong thing:

- **`npm ci` refuses any Node other than 24.** `.npmrc` sets `engine-strict=true` and `package.json` pins `"node": "^24.0.0"`. Under Node 25 it prints `EBADENGINE` and installs nothing, **but a `| tail` pipeline still exits 0**, so check that `node_modules/.bin/vitest` exists. Workaround: `npm ci --ignore-scripts --engine-strict=false`. Then say in the PR that you ran on a different Node than CI.
- **7 test files fail to load until you run `make icons`.** They fail with `Failed to resolve import "./icons.generated.js"`. The file is gitignored build output from `scripts/build_icon_sprite.mjs`, which CI builds via `make components`. Those files hold ~300 tests, so a suite without the icons reports **"900 passed"** and looks complete. With them it's 61/61 files and 1200 tests. Run `make icons` before trusting a count.
- **`$TMPDIR` may be unset in an agent shell.** Then `"$TMPDIR/x"` becomes `/x`, which fails on the read-only root. In a `cp … && sed …` mutation check, that silently skips the mutation, and the "mutated" run is green against unmodified source. Use `W=$(mktemp -d "$SCRATCH/agent-XXXXXXXX")`, and print a count proving the mutation applied before you read the result.

**`scripts/gh_scripts/*.mjs` run by `pull_request_target` workflows cannot be tested by the PR that changes them.** With a no-`ref:` checkout, the workflow and the script both run from the default branch. `new_pr_labeler.mjs` also can't be imported in vitest: it runs `main()` on load and needs `@octokit/action`, which isn't in `package.json`. `tests/unit/js/new_pr_labeler.test.js` shows the workaround: parse the source with `@babel/core` and assert structural properties.

**pre-commit (runs outside Docker, hooks into git):**
```bash
pip install pre-commit && pre-commit install   # one-time setup
pre-commit run --all-files                     # run manually
git commit -n                                  # skip hooks for one commit
```

pre-commit runs: `mypy`, `black`, `ruff`, JS lint, Stylelint. Python version must match `default_language_version` in `.pre-commit-config.yaml` — use `pyenv` if your system Python doesn't match.

**Rendering a real Templetor/web.py template against the actual dev DB (not the `render_template` pytest fixture's mocks).** The `render_template` fixture in `openlibrary/conftest.py` is great for template-syntax/output tests, but it never touches a real site — `get_current_user()` and anything else that reads `web.ctx.site` or the `site` ContextVar will raise `LookupError`. For a one-off script (e.g. to prove an escaping fix with a real payload, or to seed/inspect real dev-DB state — accounts, lists, preferences — for a review's Playwright setup) that needs the *actual* running infobase behind `docker compose`, wire it up like this instead, run via `docker compose run --rm --no-deps home python your_script.py` (with `OL_MOUNT_DIR="$(pwd)"` so it sees your worktree's code):

```python
import web
from openlibrary.config import load_config   # NOT infogami.config.load — that has no .load()
from infogami.utils import delegate

load_config('/openlibrary/conf/openlibrary.yml')
delegate.fakeload()   # connects web.ctx.site to the REAL infobase over its client, disables permission checks

site = web.ctx.site
# Now real reads/writes work, e.g.:
prefs_key = "/people/AccountBot/preferences"
prefs = site.store.get(prefs_key) or {"update": "no", "public_readlog": "no", "type": "preferences"}
prefs["public_readlog"] = "yes"
prefs["_rev"] = None
site.store[prefs_key] = prefs   # writes for real — same DB the `web` container reads from
```

If you also need `get_current_user()`/`accounts.get_current_user()` or anything gated on the `site` ContextVar specifically (as opposed to `web.ctx.site`) to resolve inside a *pytest* test (as opposed to a standalone script, where `fakeload()` above is enough on its own), additionally pull in `site as site_context` from `openlibrary.utils.request_context` and set it explicitly — `fakeload()` alone does not populate that ContextVar:

```python
import web
from openlibrary.utils.request_context import site as site_context

def test_something(render_template, request_context_fixture, mock_site):
    request_context_fixture(lang="en")
    site_context.set(web.ctx.site)   # mock_site fixture already set web.ctx.site = MockSite()
    html = str(render_template("follow/follow", "somepublisher", following=True, link_track=PAYLOAD))
```

Confirmed working on PR #12985's review (2026-07-20): used the standalone-script form to flip a test account's `public_readlog` preference (`site.store[...] = prefs`, as above) so Playwright could exercise a real call site end-to-end against the dev DB, and the pytest-fixture form to render `follow/follow.html` with an XSS payload and inspect the actual escaped output.

⚠️ **Unresolved gap**: creating a *real* `/type/list` doc this way (`owner.new_list(name=..., description=..., seeds=[...])` followed by `lst._save(comment=...)`, per the docstring on `core/models.py`'s `new_list`) did **not** work in this same session — `lst.key`, `lst.owner`, and `lst.seeds` all read back as `<Nothing>`/empty both before and after calling `_save()`, so nothing was actually persisted. Root cause not isolated (possibly the `List` model class resolving `.key`/`.owner` as computed properties that need something `fakeload()` doesn't set up, as opposed to genuine `Thing.__init__` behavior which does set `self.key` directly). Store-key read/write (above) is solid; new-entity creation via a model's `new_*()` + `_save()` convenience method needs more digging before relying on it.

**`generate-pot` fails inside Docker for a `git worktree` checkout — but not on the host.** Root cause: `compose.override.yaml` mounts the worktree at a fixed container path (`${OL_MOUNT_DIR:-.}:/openlibrary`), but a worktree's `.git` is a *file* pointing at an absolute **host** path (`gitdir: /path/to/main-repo/.git/worktrees/<name>`) — that path isn't mounted inside the container, so any git-dependent hook (this one runs `git ls-files --others` internally) fails with `fatal: not a git repository`, exit 128 — **but only inside the container.**

**Correction (verified 2026-09-01, `pr-12914-worldcat-rename`): this hook works fine on the host in a
worktree — run it there.** An earlier version of this note said it failed "regardless of host vs.
Docker"; that overreached. On the host the `gitdir:` path in the worktree's `.git` file is a real,
resolvable absolute path, so `git ls-files --others` works normally. `pre-commit run generate-pot
--all-files` (or a plain `git diff origin/master..HEAD --name-only | xargs pre-commit run --files`)
regenerated `openlibrary/i18n/messages.pot` correctly in a worktree, and a re-run reported `Passed`.
So the failure is specific to invoking the hook *through* `docker compose run`, and the fix is simply
not to do that — **do not reach for `git commit --no-verify` here.** That matters whenever a branch
genuinely adds or removes translatable strings (e.g. a rebase where both sides regenerated the
`.pot`), because there the `.pot` must actually be correct and skipping the hook is not an option. A real fix (not just the workaround) is possible for a solo dev machine: also bind-mount the main repo's actual `.git` directory into the container at the *same absolute host path* it lives at (e.g. an extra `docker-compose.override.yaml` layer with `- /Users/you/Projects/openlibrary/.git:/Users/you/Projects/openlibrary/.git:ro`) — but that path is per-developer, so it can't go into the repo's own committed compose files.

**Integration tests** (not run in CI — require Chrome, non-headless):
```bash
cd /tmp && virtualenv venv && source venv/bin/activate
git clone git@github.com:internetarchive/openlibrary.git
cd openlibrary && pip install -r requirements.txt
cd tests/integration && pytest
```

**Bundle size errors** (`FAIL static/build/page-plain.css: 18.81KB > maxSize 18.8KB`): Move styles to a JS entry point (`<file>--js.less`, import in `static/css/js-all.less`) — JS bundle has a higher threshold. Or adjust `openlibrary/package.json` thresholds if justified.

**Critical paths that must be tested before any release:**
Auth (register/login), Lending (borrow/return/waitlist), Search (all/title/author/subject/advanced + facets), Navigation, Reading Log (set/change/remove status), Lists, Editions/Works pages, Carousels, Import, Stats.

---

## PostgreSQL / Infobase Internals

OL's database is a **triplestore** — all entities stored as `thing` rows in PostgreSQL, managed entirely through Infobase (never touch directly in prod).

```bash
# Connect (local dev only)
docker compose exec db su postgres -c "psql openlibrary"
```

Key type IDs in the `thing` table (IDs are stable but verify on your instance):
```sql
-- Find type IDs
SELECT id, key FROM thing WHERE key IN ('/type/author', '/type/work', '/type/edition', '/type/user');

-- Count records by type (replace ID with actual from above)
SELECT count(*) FROM thing WHERE type = 58;   -- authors
SELECT count(*) FROM thing WHERE type = 17872418; -- works
SELECT count(*) FROM thing WHERE type = 52;   -- editions
```

All OL data lives in the `thing` table with columns: `id, key, type, latest_revision, created, last_modified`.

---

## Non-Infobase Tables (`schema.sql`) — Fresh vs. Existing Dev DBs

Tables outside the Infobase triplestore (`ratings`, `bookshelves_books`, `booknotes`, `observations`, `follows`, and newer additions like `likes`) are defined in `openlibrary/core/schema.sql`, not managed by Infobase. Provisioning is a two-step sequence in `docker/ol-db-init.sh`, mounted at `/docker-entrypoint-initdb.d/ol-db-init.sh`:

```bash
psql openlibrary < openlibrary/core/schema.sql          # 1. create all tables (incl. new ones)
psql -U openlibrary openlibrary < scripts/dev-instance/dev_db.pg_dump   # 2. restore committed sample data
```

**Critical: this only runs on a genuinely empty Postgres data directory** — that's the official `postgres` Docker image's own `docker-entrypoint-initdb.d` convention, not an OL-specific choice. Concretely:
- **Fresh dev DB (new `ol-postgres` volume)** — any table added to `schema.sql` shows up automatically, empty, ready to use. Verified directly: `likes` (added in PR #12932) came up correctly across many fresh-volume test runs with zero issues.
- **Existing/long-running dev DB volume** — `ol-db-init.sh` does **not** re-run. A newly-added table simply won't exist until the volume is wiped/recreated, or the new DDL is applied manually (e.g. `psql openlibrary -c "CREATE TABLE likes (...)"`). There is no incremental migration runner in this codebase for these tables — `scripts/migrate_db.py` exists but is unverified/likely stale (see Common Confusion below).

**When adding a brand-new empty table** (like `likes`): no changes to `scripts/dev-instance/dev_db.pg_dump` are needed — it has no rows for a table that doesn't exist yet in its own schema, so it does not conflict with `schema.sql`'s `CREATE TABLE`.

**When adding a new *seed/reference row* to an existing table** (e.g. PR #12400 adding the "Stopped Reading" bookshelf via a new `INSERT INTO bookshelves (...)` in `schema.sql`): the dump **does** need regenerating in the same PR. `dev_db.pg_dump` is a full dump (confirmed: 124 `CREATE TABLE`/`COPY` statements, no `DROP TABLE`s) captured from an instance that predates the new row — if left unregenerated, a fresh dev instance's `bookshelves` reference table would be missing the new seed row relative to what the dump's downstream consumers (CI fixtures, onboarding docs) assume. This is why `scripts/dev-instance/dev_db.pg_dump`'s own git history shows commits like #12400 (bookshelves) and #12319 (`transaction_details`) touching it alongside their `schema.sql` changes.

---

## Memcache

Infobase queries are cached in memcache. To inspect in local dev:

```python
docker compose run --rm home python
>>> import yaml
>>> from openlibrary.utils import olmemcache
>>> with open('/openlibrary/conf/openlibrary-docker.yml') as f:
...     y = yaml.safe_load(f)
>>> mc = olmemcache.Client(y['memcache_servers'])
>>> mc.get('/authors/OL18319A')    # get cached value
>>> mc.delete('/authors/OL18319A') # bust cache entry
```

---

## Bots

Bot accounts automate bulk metadata corrections and imports via HTTP POSTs to OL's API (or the `openlibrary-client` library).

**Applying for a bot account:**
1. Create a new OL account (separate from personal) with username ending in "Bot" (e.g. `WorkBot`)
2. Open a GitHub issue requesting bot privileges + membership in the `API` usergroup; tag @mekarpeles or @hornc

**Bot rules (non-negotiable):**
- Never run bulk changes (>100 records) until reviewed by @hornc (metadata lead)
- All bot code must live in `github.com/internetarchive/openlibrary-bots` — create a directory per bot
- Source data files that a bot reads from must also be committed to that repo
- Open a PR with @hornc or @mekarpeles as reviewer; wait for approval before running

**The right library:** Use `openlibrary-client` (`github.com/internetarchive/openlibrary-client`). The old `openlibrary/api.py` is deprecated.

**Monitoring bots:** Recent bot changes are visible at `openlibrary.org/recentchanges#bots`.

---

## Internal API Endpoints (Unofficial / Under Audit)

⚠️ UNVERIFIED — These are from an internal audit of "unofficially supported" APIs intended to be replaced by public APIs. Use with caution; they may change.

```
# Create a work
POST /api/new.json
Body: {"type": {"key": "/type/work"}, "title": "...", "authors": [...]}

# Edit an edition
PUT /books/(OL...M).json
Body: { <full current JSON from GET> + "_comment": "reason" }

# Delete a work/edition (admin only)
PUT /works/(OL...W).json
Body: { "type": {"key": "/type/delete"}, "_comment": "reason" }
# WARNING: deleting a Work with editions leaves orphaned editions

# List search
GET /lists/search?q=<query>
```

Full route listing: `https://dev.openlibrary.org/developers/routes`

---

## Key Files

| File | Purpose |
|------|---------|
| `docker/README.md` | Canonical setup instructions (source of truth) |
| `conf/openlibrary.yml` | Local dev config; `otp_seed`, `coverstore_public_url`, reCAPTCHA keys |
| `.pre-commit-config.yaml` | Linting hooks config; Python version must match |
| `openlibrary/package.json` | Bundle size thresholds |
| `CONTRIBUTING.md` | Contributor guide |
| `tests/integration/` | Splinter integration tests |

---

## Common Confusion

- **`docker compose run` vs `exec`** — `run` starts a new container (use for one-off commands); `exec` runs inside an already-running container (use for interactive work)
- **Pre-commit runs outside Docker** — it hooks into your local `git`, so your local Python version must match the config, not the container's
- **Database migrations** — ⚠️ STALE: `python setup.py shell && python scripts/migrate_db.py` is documented but the setup.py approach is from an old era; verify against current repo before using. What's confirmed current (2026-07-28): there is no incremental migration mechanism for `schema.sql`-defined tables — see "Non-Infobase Tables" above for what actually happens on fresh vs. existing dev DBs.
- **Upstart logs** — source mentions `/var/log/upstart/ol-web.log` but Upstart is long deprecated; ⚠️ STALE — actual log location: `docker compose logs web`
- **"This does not close #N" closes #N.** GitHub's keyword parser matches `close #N`, `fixes #N`, `resolves #N` and their variants anywhere in a PR body or commit message, and ignores negation. On #13725 (2026-09-25), "It does not close #9836" linked the issue for closing. Keep closing verbs away from issue references ("#9836 stays open"), and check `gh pr view N --json closingIssuesReferences` **after a short wait**: GitHub recomputes it after parsing, and a check right after an edit can come back empty.

---

## Dependencies

**Depends on:**
- [[infrastructure]] — Docker host layout; ol-dev as staging; production secrets in olsystem
- [[core-operations]] — Infobase is the data layer all local dev touches

**Depended on by:**
- Every other domain — development environment is the prerequisite for working on anything

---

*Sources: `raw/openlibrary-wiki/Developer-Resources/Getting-Started.md` (⚠️ STALE — self-described), `Testing.md`, `Writing-Bots.md`, `Endpoints.md` · Canonical setup: `docker/README.md` in repo · See [[README]] · [[METHODOLOGY]]*
