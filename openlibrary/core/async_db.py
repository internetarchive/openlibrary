"""Async PostgreSQL access via Psycopg 3.

One pool per event loop: an ``AsyncConnectionPool`` binds its lock, queue,
scheduler, and background workers to the loop that opened it, so using that
pool from another loop fails. Two loops use these pools in a process --
FastAPI's and ``async_bridge``'s, each for the life of the process -- and
anything else that calls :func:`connection` (e.g. a pytest-asyncio loop)
gets its own pool the same way.

Pools are created lazily on first use so bridged model methods work in the
legacy web.py process, where no FastAPI lifespan runs. ``init_pool()``
pre-warms the current loop's pool at FastAPI startup. Each entry's asyncio
lock is held across both opens and closes, so the two cannot interleave on
one loop: a close during an in-flight open waits for the open to finish,
then closes the fresh pool, and a cancelled opener leaves the pool unset
for the next caller to retry. A closed pool sets ``entry.pool`` back to
None so the entry (and its lock) is reused by a later open.

``close_pool()`` closes the running loop's pool and is called from the
FastAPI lifespan shutdown. Pools owned by other loops (the bridge loop's,
or a pytest loop's) live for the lifetime of their loop or process and are
not touched. The registry is shared by the FastAPI loop's thread and the
bridge loop's thread, so its structural changes go through a thread lock
that is never held across an await.

When database configuration exists, missing psycopg dependencies raise
during pool initialization rather than allowing a configured application
to start and fail later on its first database request.

Async call sites use the single-statement helpers, each of which takes
one connection from the pool, runs one query, and gives the connection
back when the query completes:

    await execute("INSERT ...", params)
    rows = await fetch_all("SELECT ...", params)
    row = await fetch_one("SELECT ...", params)
    count = await fetch_val("SELECT count(*) ...", params)

``fetch_all`` and ``fetch_one`` map their rows through ``row_factory``
when one is passed, e.g. ``class_row(Model)``, and give back the pool's
default dict rows otherwise. A method that needs several statements in
one transaction acquires the connection explicitly instead:

    async with connection() as conn:
        await conn.execute(...)
        await conn.execute(...)

Legacy synchronous code that has not been bridged yet keeps using the
``web.database`` handle in ``openlibrary/core/db.py``.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import web

logger = logging.getLogger("openlibrary.async_db")

# Keep this import guard so modules and tests which don't use the async database
# can still be imported without psycopg installed. A configured application
# fails during startup in _open_pool() instead of failing on its first request.
try:
    from psycopg.rows import class_row, dict_row, tuple_row
    from psycopg_pool import AsyncConnectionPool
except ModuleNotFoundError:
    class_row = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    tuple_row = None  # type: ignore[assignment]
    AsyncConnectionPool = None  # type: ignore

if TYPE_CHECKING:
    from psycopg import AsyncConnection, AsyncCursor
    from psycopg.rows import BaseRowFactory
    from psycopg_pool import AsyncConnectionPool as _PoolClass

    Pool = _PoolClass[AsyncConnection[dict[str, Any]]]


@dataclass
class _LoopPool:
    """One event loop's pool and the lock that serializes opening and closing it."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pool: Pool | None = None


# Keyed by the event loop that owns the pool. Entries are created on the
# owning loop and live for the life of the process; close_pool() closes the
# running loop's pool and sets entry.pool back to None so the entry (and its
# lock) is reused by a later open. The registry is touched from multiple
# threads (FastAPI's loop and AsyncBridge's), so structural changes go
# through _entries_lock.
_entries: dict[asyncio.AbstractEventLoop, _LoopPool] = {}
# Never held across an await.
_entries_lock = threading.Lock()
# Distinguishes pools from each other in logs and stats, one per pool.
_pool_names = itertools.count(1)


def _connection_kwargs(db_parameters: dict) -> dict:
    """Translate web.py ``db_parameters`` into psycopg connection kwargs."""
    kwargs = {
        "dbname": db_parameters.get("db"),
        "user": db_parameters.get("user"),
        "password": db_parameters.get("pw") or "",
    }
    if host := db_parameters.get("host"):
        kwargs["host"] = host
    if port := db_parameters.get("port"):
        kwargs["port"] = port
    return kwargs


async def _open_pool() -> Pool | None:
    """Create and open a pool for the running loop.

    Returns None if no database is configured. Raises if psycopg is missing
    while database access is configured. Closes the pool on failure or
    cancellation before re-raising.
    """
    db_parameters = getattr(web.config, "db_parameters", None) or {}
    if not db_parameters.get("db"):
        logger.info("db_parameters not configured; skipping async pool creation")
        return None
    if AsyncConnectionPool is None or dict_row is None:
        raise RuntimeError("psycopg[binary,pool] is required when async database access is configured")

    pool = cast(
        "Pool",
        AsyncConnectionPool(
            kwargs={**_connection_kwargs(db_parameters), "row_factory": dict_row},
            open=False,
            # 4 warm connections, grow to 20 under burst.
            min_size=4,
            max_size=20,
            # Discard stale/dead connections before handing them out, e.g. after
            # a Postgres restart or a server-side idle_session_timeout.
            check=AsyncConnectionPool.check_connection,
            name=f"async-db-{next(_pool_names)}",
        ),
    )
    try:
        await pool.open(wait=True)
    except BaseException:
        # close() is idempotent, so this covers a pool that opened before the
        # failure or cancellation. Suppress close-time cancellation so the
        # original exception still propagates.
        with suppress(Exception, asyncio.CancelledError):
            await pool.close()
        raise
    return pool


def _entry_for_loop() -> _LoopPool:
    """Return the running loop's entry, creating it on first use."""
    loop = asyncio.get_running_loop()
    with _entries_lock:
        entry = _entries.get(loop)
        if entry is None:
            entry = _entries[loop] = _LoopPool()
    return entry


async def _pool_for_loop() -> Pool | None:
    """Return the running loop's pool, creating it lazily if needed.

    The entry's lock serializes first callers AND close_pool's closes, so an
    open can never interleave with a close of the same entry: a close during
    an open waits for the open to finish, then closes the fresh pool. A
    cancelled opener releases the lock with entry.pool unset, so the next
    caller retries.
    """
    entry = _entry_for_loop()
    if entry.pool is not None:
        return entry.pool
    async with entry.lock:
        if entry.pool is None:
            entry.pool = await _open_pool()
        return entry.pool


async def init_pool() -> None:
    """Pre-warm the running loop's pool.

    Safe to call repeatedly; an existing pool is reused. When no database is
    configured, e.g. under pytest, no pool is created.
    """
    await _pool_for_loop()


async def close_pool() -> None:
    """Close the running loop's pool.

    Called from the FastAPI lifespan shutdown. Pools owned by other loops
    (the bridge loop's, or a pytest loop's) are left alone; they live until
    their loop or process goes away.

    The entry lock waits out any in-flight open first. A pool that fails to
    close is logged and left cached, so a later call can retry; a pool
    opened while this close runs may also be missed and stays cached for a
    later close.
    """
    with _entries_lock:
        entry = _entries.get(asyncio.get_running_loop())
    if entry is None:
        return
    async with entry.lock:
        pool = entry.pool
        if pool is None:
            return
        try:
            await pool.close()
        except Exception:
            logger.exception("Error closing async DB pool for the running event loop")
            return
        entry.pool = None


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
    """Acquire a connection from the running loop's pool.

    Each call checks a connection out of the pool for the duration of the
    ``async with`` block. The pool commits when the block exits normally and
    rolls back when it exits with an exception. Callers should only call
    ``commit()`` when they intentionally need an intermediate transaction
    boundary.

    Raises:
        RuntimeError: if no pool can be initialized for the running loop (e.g.
            because no database was configured).
    """
    pool = await _pool_for_loop()
    if pool is None:
        raise RuntimeError("No async database pool available; ensure web.config.db_parameters has a 'db' key configured (or call init_pool() during app startup)")
    async with pool.connection() as conn:
        yield conn


async def _run(
    conn: AsyncConnection[dict[str, Any]],
    query: str,
    params: dict[str, Any] | None,
    row_factory: BaseRowFactory[Any] | None,
) -> AsyncCursor[Any]:
    """Execute ``query`` on ``conn`` and return the cursor to fetch from.

    Without a ``row_factory`` the cursor inherits the connection's dict
    rows; with one, e.g. ``class_row(Model)``, the cursor maps rows
    through it instead.
    """
    if row_factory is None:
        return await conn.execute(query, params)
    cursor = conn.cursor(row_factory=row_factory)
    await cursor.execute(query, params)
    return cursor


async def execute(query: str, params: dict[str, Any] | None = None) -> None:
    """Run one statement on its own pooled connection.

    The connection commits when the statement completes and rolls back if
    it raises, the same transaction semantics an explicit ``async with
    connection()`` block gives. Use that form instead when a method needs
    several statements in one transaction.
    """
    async with connection() as conn:
        await conn.execute(query, params)


async def fetch_all(
    query: str,
    params: dict[str, Any] | None = None,
    *,
    row_factory: BaseRowFactory[Any] | None = None,
) -> list[Any]:
    """Every row of one query, on its own pooled connection.

    Without ``row_factory``, rows are the pool's default dicts; with one,
    e.g. ``class_row(Model)``, rows are whatever it builds. The
    connection commits when the query completes, like :func:`execute`.
    """
    async with connection() as conn:
        cursor = await _run(conn, query, params, row_factory)
        return await cursor.fetchall()


async def fetch_one(
    query: str,
    params: dict[str, Any] | None = None,
    *,
    row_factory: BaseRowFactory[Any] | None = None,
) -> Any:
    """The first row of one query, or None if it matched nothing.

    Rows map through ``row_factory`` the same way :func:`fetch_all` maps
    them. The connection commits when the query completes.
    """
    async with connection() as conn:
        cursor = await _run(conn, query, params, row_factory)
        return await cursor.fetchone()


async def fetch_val(query: str, params: dict[str, Any] | None = None) -> Any:
    """The first column of the first row, or None if there were no rows.

    For one-column queries -- ``SELECT count(*) ...`` and other scalars.
    The connection commits when the query completes.
    """
    row = await fetch_one(query, params, row_factory=tuple_row)
    return row[0] if row is not None else None
