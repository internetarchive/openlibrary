# Database

How Open Library stores data, and which access path to use when. Most data is Infogami pages in Infobase, never SQL. A handful of features keep their own SQL tables, and direct SQL access is migrating from the sync web.py handle (`db.py`) to an async psycopg3 pool (`async_db.py`). If you're writing a new query, especially anything FastAPI reaches, use the async pool.

## Where data lives

**Most data: Infogami pages (Infobase).** Works, editions, authors, users, and lists are versioned "things" addressed by keys like `/works/OL123W`. They're stored through Infogami (`vendor/infogami/`), not in tables you query. Read and write them through the site handle or the HTTP API (`/api/get?key=...`), never SQL.

The handle is two calls. `site.get()` returns the current site; it's the `site` ContextVar from `openlibrary/utils/request_context.py` (`web.ctx.site` in legacy web.py code). `.get(key)` fetches the thing. Put together: `site.get().get("/works/OL123W")`.

**Some data: feature tables (direct SQL).** The reading log (`bookshelves`, `bookshelves_books`, `bookshelves_events`), ratings, observations, booknotes, likes, follows, yearly reading goals, and a few others keep their own tables. `openlibrary/core/schema.sql` is the list. The models in `openlibrary/core/` (`bookshelves.py`, `ratings.py`, `yearly_reading_goals.py`, ...) own them, and the rest of this doc is about these tables.

## Two drivers, and when to use each

| Driver | Use for | What it is |
|---|---|---|
| `openlibrary/core/async_db.py` | All new code, anything FastAPI touches | Async psycopg3 pool |
| `openlibrary/core/db.py` | Legacy web.py paths, until their model migrates | Sync web.py handle (`get_db()`), psycopg2 underneath |

The sync handle isn't going away overnight. Plenty of legacy web.py code still runs through it, and you don't need to migrate a model just to fix something adjacent to it. But don't add new sync queries. When FastAPI work touches a model, migrate it; the pattern below is a few lines per method.

## The async pool: `openlibrary/core/async_db.py`

Single-statement helpers. Each takes a connection from the pool, runs one query, commits, and returns the connection:

```python
from openlibrary.core.async_db import class_row, execute, fetch_all, fetch_one, fetch_val

rows = await fetch_all("SELECT ... WHERE x = %(x)s", {"x": 1}, row_factory=class_row(MyRow))
row = await fetch_one("SELECT ...")             # first row, or None
count = await fetch_val("SELECT count(*) ...")  # first column of the first row
await execute("INSERT ...", params)
```

For multi-statement transactions, take the connection explicitly:

```python
from openlibrary.core.async_db import connection

async with connection() as conn:
    await conn.execute(...)
    await conn.execute(...)
```

The module docstring documents the details. The parts that trip agents up:

- Placeholders are psycopg3's `%(name)s`, not web.py's `$name`.
- One pool per event loop. FastAPI's loop gets its pool from the app lifespan (`init_pool()` / `close_pool()` in `openlibrary/asgi_app.py`); anything else (the bridge loop, a pytest loop) gets one lazily on first use. This is why `AsyncConnectionPool` can't be a module-level singleton.
- Rows map through psycopg row factories. `class_row(Model)` gives typed rows; import it from `async_db`, which guards the psycopg import. Migrated models keep a small dataclass or TypedDict next to them for the row type (`YearlyReadingGoal` in `yearly_reading_goals.py`).
- Missing psycopg with a configured database fails at pool startup, not on the first request.

## Calling async code from sync web.py code: the bridge

web.py code can't `await`, so sync callers run async model methods on a persistent background event loop (`openlibrary/utils/async_utils.py`):

```python
from openlibrary.utils.async_utils import async_bridge

@classmethod
def summary_sync(cls) -> dict[str, dict[str, int]]:
    """Sync bridge for the legacy web.py caller."""
    return async_bridge.run(cls.summary())
```

`async_bridge.wrap(func)` does the same for a whole function. The bridge loop gets its own lazily-created pool, which is the second long-lived loop the per-loop registry exists for.

## Naming: async is primary

Migrated models keep the plain name on the async method (`select_by_username`, `summary`) and give the sync bridge a `_sync` suffix (`summary_sync`). Don't add `_async`-suffixed model methods; that was the pre-migration shape and it's gone.

## Reference migration

The reading-goals model was the first to move end-to-end. Copy this set:

- `openlibrary/core/yearly_reading_goals.py` — the model, with typed rows and a `summary_sync` bridge
- `openlibrary/fastapi/yearly_reading_goals.py` — FastAPI endpoint calling the async model directly
- `openlibrary/plugins/upstream/yearly_reading_goals.py` — the web.py adapter; it resolves the current user, then bridges with `async_bridge.run`
- `openlibrary/plugins/openlibrary/partials.py` — `ReadingGoalProgressPartial.generate_async`, an async partial feeding Jinja
- Tests: `openlibrary/tests/core/test_yearly_reading_goals_async.py` patches the helpers and asserts the query and params; `openlibrary/tests/core/async_db_fakes.py` holds the connection/cursor fakes for helper-level tests

## Testing DB code

Two layers, in two files next to the model:

1. **Unit tests** (no postgres, ~0.05s) — patch the `async_db` helpers (`fetch_all`, `fetch_one`, `execute`, `fetch_val`) with `AsyncMock`, set a return value, and assert the query text and params the method passes. These catch logic bugs: wrong params, wrong helper called, wrong query shape. Run on every `make test-py-uv`; no postgres required.

2. **Integration tests** (real postgres, ~2s) — marked `@pytest.mark.integration`, in a `Test*Integration` class in the same file. Run the model methods against a real postgres started by `pytest-postgresql`, which loads `openlibrary/core/schema.sql` into a template database and clones it per test for isolation. These catch SQL bugs the unit tests can't: syntax errors, wrong column names, `%(foo)s` placeholder mismatches, and postgres-specific features (`count(*) FILTER`, `DISTINCT`, `LIKE` on dates) that would parse in a string but fail on the real schema. Skipped by default (`-m 'not integration'`); CI runs them in a separate step after the main test suite.

```python
# Unit test — patches the helpers, asserts the query text
@pytest.mark.asyncio
async def test_select_by_username(helpers):
    helpers.fetch_all.return_value = [goal]
    rows = await YearlyReadingGoals.select_by_username("alice")
    assert rows == [goal]
    (query, params), _ = helpers.fetch_all.await_args
    assert "username = %(username)s" in query

# Integration test — runs the SQL against a real postgres
@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_select(self, pg_db):
    await YearlyReadingGoals.create("alice", 2026, 25)
    rows = await YearlyReadingGoals.select_by_username("alice")
    assert len(rows) == 1 and rows[0].target == 25
```

Add integration tests when a method uses postgres-specific SQL (aggregates, `FILTER`, `DISTINCT`, date/time, `json`/`jsonb`, `ARRAY`). Trivial CRUD is covered by the unit tests; a column typo surfaces immediately in dev. The `pg_db` fixture (from `openlibrary/tests/core/conftest.py`) handles the rest — just use it as a fixture argument and it points `web.config.db_parameters` at a fresh database.

Run them with `make test-py-integration` (needs `pg_ctl` on `PATH` — `brew install postgresql@14` on macOS).

## Rules of thumb

- **New table or new query?** Async helpers from the start.
- **FastAPI endpoint or partial touching SQL?** Always async. A sync DB call blocks the event-loop worker.
- **Only touching legacy web.py behavior on a `db.py` model?** Sync is fine; don't half-migrate one flow across both drivers.
- **Same model needed in both worlds?** Async method plus a thin `_sync` bridge, or a web.py adapter like `get_reading_goals`.
- **Page data (works, editions, authors, users)?** Not SQL at all. Use `site.get()` or the API.
