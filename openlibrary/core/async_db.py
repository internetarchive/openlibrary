"""Async PostgreSQL access via Psycopg 3.

One pool per event loop. An ``AsyncConnectionPool`` binds to the loop that
opens it, so FastAPI's loop, ``async_bridge``'s loop, and any other caller
(e.g. a pytest-asyncio loop) each get their own pool.

Pools open lazily on first use, so bridged model methods work in the legacy
web.py process where no FastAPI lifespan runs. ``init_pool()`` pre-warms the
current loop's pool at FastAPI startup and ``close_pool()`` closes it at
shutdown. See ``docs/core/database.md`` for the full guide.

Async call sites use the single-statement helpers:

    await execute("INSERT ...", params)
    rows = await fetch_all("SELECT ...", params)
    row = await fetch_one("SELECT ...", params)
    count = await fetch_val("SELECT count(*) ...", params)

``fetch_all`` and ``fetch_one`` map rows through ``row_factory`` when one is
passed, e.g. ``class_row(Model)``, and return dict rows otherwise. Methods
that need several statements in one transaction use the connection directly:

    async with connection() as conn:
        await conn.execute(...)
        await conn.execute(...)

Legacy sync code that has not been bridged yet keeps using the
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

# Lets modules import without psycopg installed. A configured app fails in
# _open_pool() at startup instead of on its first request.
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
    """One event loop's pool and the lock that serializes open and close."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pool: Pool | None = None


# One entry per owning loop. Touched from multiple threads, so structural
# changes go through _entries_lock, never held across an await.
_entries: dict[asyncio.AbstractEventLoop, _LoopPool] = {}
_entries_lock = threading.Lock()
# Counter for pool names in logs.
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
            min_size=4,
            max_size=20,
            # Re-check connections before checkout, so restarts and idle timeouts do not hand out dead ones.
            check=AsyncConnectionPool.check_connection,
            name=f"async-db-{next(_pool_names)}",
        ),
    )
    try:
        await pool.open(wait=True)
    except BaseException:
        # close() covers a pool that opened before the failure. Suppress
        # close-time errors so the original exception propagates.
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

    The entry lock covers opens and closes, so a close waits out an in-flight
    open. A cancelled opener leaves the pool unset for the next caller to retry.
    """
    entry = _entry_for_loop()
    if entry.pool is not None:
        return entry.pool
    async with entry.lock:
        if entry.pool is None:
            entry.pool = await _open_pool()
        return entry.pool


async def init_pool() -> None:
    """Pre-warm the running loop's pool. Reuses an existing pool."""
    await _pool_for_loop()


async def close_pool() -> None:
    """Close the running loop's pool. Other loops keep theirs.

    Waits out an in-flight open first. A failed close stays cached so a later
    call can retry.
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
    """Check out a connection from the running loop's pool.

    Commits on clean exit, rolls back on error. Raises RuntimeError if no
    database is configured.
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
    """Run ``query`` on ``conn`` and return the cursor."""
    if row_factory is None:
        return await conn.execute(query, params)
    cursor = conn.cursor(row_factory=row_factory)
    await cursor.execute(query, params)
    return cursor


async def execute(query: str, params: dict[str, Any] | None = None) -> None:
    """Run one statement on its own pooled connection."""
    async with connection() as conn:
        await conn.execute(query, params)


async def fetch_all(
    query: str,
    params: dict[str, Any] | None = None,
    *,
    row_factory: BaseRowFactory[Any] | None = None,
) -> list[Any]:
    """Every row of one query. Dict rows by default, ``row_factory`` maps them."""
    async with connection() as conn:
        cursor = await _run(conn, query, params, row_factory)
        return await cursor.fetchall()


async def fetch_one(
    query: str,
    params: dict[str, Any] | None = None,
    *,
    row_factory: BaseRowFactory[Any] | None = None,
) -> Any:
    """First row of one query, or None if it matched nothing."""
    async with connection() as conn:
        cursor = await _run(conn, query, params, row_factory)
        return await cursor.fetchone()


async def fetch_val(query: str, params: dict[str, Any] | None = None) -> Any:
    """First column of the first row, or None if there were no rows."""
    row = await fetch_one(query, params, row_factory=tuple_row)
    return row[0] if row is not None else None
