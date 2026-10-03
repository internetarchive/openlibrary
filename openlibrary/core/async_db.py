"""Async PostgreSQL access via Psycopg 3.

This module holds the shared async connection pools used by FastAPI
endpoints and by code bridged from the synchronous web.py stack via
``async_bridge``. An ``AsyncConnectionPool`` binds its asyncio primitives
and any opened connections to the first event loop that touches it. Using
that pool from a different loop raises ``RuntimeError: ... bound to a
different event loop``. Pools are cached per event loop, the same trick
``cache_per_event_loop`` uses in ``openlibrary.utils.async_utils``.

Pools are created lazily on first use, so a model method wrapped with
``async_bridge.wrap`` works in the legacy web.py process too, where no
FastAPI lifespan runs. Each loop's lock serializes first callers, so
concurrent callers share one pool. ``init_pool()`` can pre-warm the current
loop's pool at FastAPI startup, and ``close_pool()`` closes every cached
pool on its own loop.

Pool lifetime is explicit: an open pool keeps its event loop alive, so close
it before that loop dies. A loop that dies with an open pool leaves the pool's
sockets and worker tasks to process teardown.

Async call sites acquire connections with :func:`connection`:

    async with connection() as conn:
        cursor = await conn.execute("SELECT ...", params)
        rows = await cursor.fetchall()

Legacy synchronous code that has not been bridged yet keeps using the
``web.database`` handle in ``openlibrary/core/db.py``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import web

logger = logging.getLogger("openlibrary.async_db")

# psycopg and psycopg_pool are not in the dev Docker image yet, so this
# file must import without them until the image rebuilds. When they are
# missing, _open_pool() returns None and only endpoints calling
# connection() fail. Remove this guard once the image ships with psycopg.
try:
    from psycopg.conninfo import make_conninfo
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool
except ModuleNotFoundError:
    make_conninfo = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    AsyncConnectionPool = None  # type: ignore

if TYPE_CHECKING:
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool as _PoolClass

    Pool = _PoolClass[AsyncConnection[dict[str, Any]]]


@dataclass
class _LoopPool:
    """One event loop's pool and the lock that opens it."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pool: Pool | None = None


# Keyed by the event loop that owns the pool. Entries are removed by
# close_pool()/reset_pools(), never by garbage collection.
_entries: dict[asyncio.AbstractEventLoop, _LoopPool] = {}


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


def _conninfo(db_parameters: dict) -> str:
    """Build a psycopg conninfo string from web.py ``db_parameters``."""
    return make_conninfo(**_connection_kwargs(db_parameters))


async def _open_pool() -> Pool | None:
    """Create and open a pool for the running loop.

    Returns None if no database is configured or psycopg is missing. Closes
    the pool on failure or cancellation before re-raising.
    """
    db_parameters = getattr(web.config, "db_parameters", None) or {}
    if not db_parameters.get("db"):
        logger.info("db_parameters not configured; skipping async pool creation")
        return None
    if AsyncConnectionPool is None:
        logger.warning("psycopg/psycopg_pool not installed; async DB pool unavailable. Install with: pip install 'psycopg[binary,pool]'")
        return None

    pool = cast(
        "Pool",
        AsyncConnectionPool(
            conninfo=_conninfo(db_parameters),
            kwargs={"row_factory": dict_row},
            open=False,
            # 4 warm connections, grow to 20 under burst.
            min_size=4,
            max_size=20,
            # Discard stale/dead connections before handing them out, e.g. after
            # a Postgres restart or a server-side idle_session_timeout.
            check=AsyncConnectionPool.check_connection,
        ),
    )
    try:
        await pool.open()
        await pool.wait()
    except BaseException:
        # close() is idempotent, so this covers a pool that opened before the
        # failure or cancellation. Suppress close-time cancellation so the
        # original exception still propagates.
        with suppress(Exception, asyncio.CancelledError):
            await pool.close()
        raise
    return pool


async def _pool_for_loop() -> Pool | None:
    """Return the running loop's pool, creating it lazily if needed.

    The loop's lock serializes first callers, so the pool opens once. A
    cancelled caller leaves the open to the others, and a pool that loses its
    registry entry while opening closes itself.
    """
    loop = asyncio.get_running_loop()
    entry = _entries.get(loop)
    if entry is None:
        entry = _entries[loop] = _LoopPool()
    if entry.pool is not None:
        return entry.pool

    async with entry.lock:
        if entry.pool is None:
            pool = await _open_pool()
            if _entries.get(loop) is not entry:
                # close_pool()/reset_pools() removed this entry mid-open.
                if pool is not None:
                    with suppress(Exception, asyncio.CancelledError):
                        await pool.close()
                return None
            entry.pool = pool
        return entry.pool


async def init_pool() -> None:
    """Pre-warm the running loop's pool.

    Safe to call repeatedly; an existing pool is reused. When no database is
    configured, e.g. under pytest, no pool is created.
    """
    await _pool_for_loop()


async def _close_loop_pool(loop: asyncio.AbstractEventLoop) -> None:
    """Close ``loop``'s pool. Must run on ``loop``.

    If an open is in flight, its entry is removed so the opener closes the
    pool itself. The pool stays cached unless close() succeeds, so a failed
    close can be retried.
    """
    entry = _entries.get(loop)
    if entry is None:
        return
    if entry.pool is None:
        _entries.pop(loop, None)
        return
    await entry.pool.close()
    _entries.pop(loop, None)


def _drop_loop_entry(loop: asyncio.AbstractEventLoop, reason: str) -> None:
    """Forget a stopped or closed loop's entry. Nothing can run on a dead loop."""
    if _entries.pop(loop, None) is not None:
        logger.warning("Dropping async DB pool for event loop %s without closing: %s", loop, reason)


async def close_pool() -> None:
    """Close every cached pool.

    Each pool closes on its own loop; stopped or closed loops are dropped
    with a warning instead of stalling shutdown. A pool that fails to close
    stays cached for a retry.
    """
    current_loop = asyncio.get_running_loop()
    # Snapshot: owning loops mutate _entries while we await.
    for loop in list(_entries):
        try:
            if loop is current_loop:
                await _close_loop_pool(loop)
            elif loop.is_running() and not loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(_close_loop_pool(loop), loop)
                await asyncio.wait_for(asyncio.wrap_future(future), timeout=10)
            else:
                _drop_loop_entry(loop, "event loop is closed" if loop.is_closed() else "event loop is not running")
        except Exception:
            logger.exception("Error closing async pool for event loop %s", loop)


def get_pool() -> Pool | None:
    """Return the running loop's pool, or None if it was never created."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    entry = _entries.get(loop)
    return entry.pool if entry else None


def reset_pools() -> None:
    """Synchronously drop all cached pools.

    For callers that can't await, such as test fixtures: running loops get a
    scheduled close, dead loops are dropped where nothing can run. Prefer
    ``await close_pool()``; it waits for cleanup.
    """
    entries = list(_entries.items())
    _entries.clear()
    for loop, entry in entries:
        if entry.pool is None:
            continue
        if loop.is_running() and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(entry.pool.close(), loop)
        else:
            logger.debug("Dropping async DB pool for inactive event loop %s without closing", loop)


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
    """Acquire a connection from the running loop's pool.

    Each call checks a connection out of the pool for the duration of the
    ``async with`` block. Callers commit or roll back writes themselves.

    Raises:
        RuntimeError: if no pool can be initialized for the running loop (e.g.
            because no database was configured).
    """
    pool = await _pool_for_loop()
    if pool is None:
        raise RuntimeError("No async database pool available; ensure web.config.db_parameters has a 'db' key configured (or call init_pool() during app startup)")
    async with pool.connection() as conn:
        yield conn
