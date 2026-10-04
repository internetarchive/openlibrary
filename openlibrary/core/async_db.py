"""Async PostgreSQL access via Psycopg 3.

This module holds the async connection pools used by FastAPI endpoints and by
code bridged from the synchronous web.py stack through ``async_bridge``. An
``AsyncConnectionPool`` binds its asyncio primitives and opened connections to
the event loop that uses it. Using that pool from another loop raises
``RuntimeError: ... bound to a different event loop``. The module therefore
keeps one pool entry per event loop.

The registry is shared by the FastAPI loop and the bridge loop. A thread lock
protects registry access, while each entry's asyncio lock serializes lazy
initialization on its own loop. Pools are created lazily so bridged model
methods work in the legacy web.py process even when no FastAPI lifespan runs.
``init_pool()`` pre-warms the current loop's pool at FastAPI startup.
``close_pool()`` temporarily rejects new pool creation, then closes the
cached pools on their owning loops. Call it before an owning loop is stopped;
closed or stopped loops can only be removed from the registry with a warning.
The registry holds strong references to its entries, so callers that create
short-lived event loops must close or reset their pools explicitly.

When database configuration exists, missing psycopg dependencies raise during
pool initialization rather than allowing a configured application to start
and fail later on its first database request.

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
    from psycopg.conninfo import make_conninfo
    from psycopg.rows import class_row, dict_row
    from psycopg_pool import AsyncConnectionPool
except ModuleNotFoundError:
    make_conninfo = None  # type: ignore[assignment]
    class_row = None  # type: ignore[assignment]
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


# Keyed by the event loop that owns the pool. The registry is shared by the
# FastAPI loop and AsyncBridge's loop, so registry access must be protected by a
# thread lock. Entries are removed by close_pool()/reset_pools(), never by
# garbage collection.
_entries: dict[asyncio.AbstractEventLoop, _LoopPool] = {}
_registry_lock = threading.RLock()
_closing = False


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

    Returns None if no database is configured. Raises if psycopg is missing
    while database access is configured. Closes the pool on failure or
    cancellation before re-raising.
    """
    db_parameters = getattr(web.config, "db_parameters", None) or {}
    if not db_parameters.get("db"):
        logger.info("db_parameters not configured; skipping async pool creation")
        return None
    if AsyncConnectionPool is None or make_conninfo is None or class_row is None or dict_row is None:
        raise RuntimeError("psycopg[binary,pool] is required when async database access is configured")

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
    with _registry_lock:
        if _closing:
            raise RuntimeError("Async database pool is shutting down")
        entry = _entries.get(loop)
        if entry is None:
            entry = _entries[loop] = _LoopPool()
    if entry.pool is not None:
        return entry.pool

    async with entry.lock:
        if entry.pool is None:
            pool = await _open_pool()
            with _registry_lock:
                entry_is_current = not _closing and _entries.get(loop) is entry
            if not entry_is_current:
                # close_pool()/reset_pools() removed this entry mid-open.
                if pool is not None:
                    with suppress(Exception, asyncio.CancelledError):
                        await pool.close()
                return None
            with _registry_lock:
                # close_pool() cannot start a new close while this assignment
                # is protected, and the identity check prevents replacing a
                # newer entry after an await.
                if not _closing and _entries.get(loop) is entry:
                    entry.pool = pool
                else:
                    entry_is_current = False
            if not entry_is_current:
                if pool is not None:
                    with suppress(Exception, asyncio.CancelledError):
                        await pool.close()
                return None
        return entry.pool


async def init_pool() -> None:
    """Pre-warm the running loop's pool.

    Safe to call repeatedly; an existing pool is reused. When no database is
    configured, e.g. under pytest, no pool is created.
    """
    await _pool_for_loop()


async def _close_loop_pool(loop: asyncio.AbstractEventLoop, expected_entry: _LoopPool) -> None:
    """Close ``loop``'s pool. Must run on ``loop``.

    If an open is in flight, its entry is removed so the opener closes the
    pool itself. The pool stays cached unless close() succeeds, so a failed
    close can be retried.
    """
    with _registry_lock:
        entry = _entries.get(loop)
        if entry is not expected_entry:
            return
    if entry.pool is None:
        with _registry_lock:
            if _entries.get(loop) is expected_entry:
                _entries.pop(loop, None)
        return
    await entry.pool.close()
    with _registry_lock:
        if _entries.get(loop) is expected_entry:
            _entries.pop(loop, None)


def _drop_loop_entry(loop: asyncio.AbstractEventLoop, expected_entry: _LoopPool, reason: str) -> None:
    """Forget a stopped or closed loop's entry. Nothing can run on a dead loop."""
    with _registry_lock:
        removed = _entries.pop(loop, None) if _entries.get(loop) is expected_entry else None
    if removed is not None:
        logger.warning("Dropping async DB pool for event loop %s without closing: %s", loop, reason)


async def close_pool() -> None:
    """Close every cached pool.

    Each pool closes on its own loop; stopped or closed loops are dropped
    with a warning instead of stalling shutdown. A pool that fails to close
    stays cached for a retry.
    """
    global _closing
    current_loop = asyncio.get_running_loop()
    with _registry_lock:
        if _closing:
            raise RuntimeError("Async database pool is already shutting down")
        _closing = True
        entries = list(_entries.items())

    try:
        for loop, entry in entries:
            try:
                if loop is current_loop:
                    await _close_loop_pool(loop, entry)
                elif loop.is_running() and not loop.is_closed():
                    future = asyncio.run_coroutine_threadsafe(_close_loop_pool(loop, entry), loop)
                    await asyncio.wait_for(asyncio.wrap_future(future), timeout=10)
                else:
                    _drop_loop_entry(loop, entry, "event loop is closed" if loop.is_closed() else "event loop is not running")
            except Exception:
                logger.exception("Error closing async pool for event loop %s", loop)
    finally:
        with _registry_lock:
            _closing = False


def get_pool() -> Pool | None:
    """Return the running loop's pool, or None if it was never created."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    with _registry_lock:
        entry = _entries.get(loop)
    return entry.pool if entry else None


def reset_pools() -> None:
    """Synchronously drop all cached pools.

    For callers that can't await, such as test fixtures: running loops get a
    scheduled close, dead loops are dropped where nothing can run. Prefer
    ``await close_pool()``; it waits for cleanup.
    """
    global _closing
    with _registry_lock:
        entries = list(_entries.items())
        _entries.clear()
        _closing = False
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
