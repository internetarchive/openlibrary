"""Async PostgreSQL access via Psycopg 3.

This module owns the shared async connection pools used by async FastAPI
endpoints and by anything bridged from the synchronous web.py stack via
``async_bridge``. An ``AsyncConnectionPool`` lazily binds its internal asyncio
primitives (and any opened connections) to whichever event loop first touches
it, so a single process-wide pool cannot be reused from a different loop --
that raises ``RuntimeError: ... bound to a different event loop``. Pools are
therefore cached *per event loop*, mirroring ``cache_per_event_loop`` (see
``openlibrary.utils.async_utils``).

Each pool is created lazily on first use from whichever loop is running, so a
model method wrapped with ``async_bridge.wrap`` works even in the legacy web.py
process, where no FastAPI lifespan runs. ``init_pool()`` optionally pre-warms
the pool for the current loop at FastAPI startup and ``close_pool()`` closes
every pool, each on its own loop.

Async call sites acquire connections with :func:`connection`:

    async with connection() as conn:
        cursor = await conn.execute("SELECT ...", params)
        rows = await cursor.fetchall()

Legacy synchronous code that has not been bridged yet continues to use the
``web.database`` handle in ``openlibrary/core/db.py``.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

import web
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

if TYPE_CHECKING:
    from psycopg import AsyncConnection

logger = logging.getLogger("openlibrary.async_db")

if TYPE_CHECKING:
    Pool = AsyncConnectionPool[AsyncConnection[dict[str, Any]]]
    PoolMap = weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Pool]

_pools: PoolMap = weakref.WeakKeyDictionary()
_opening: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Task] = weakref.WeakKeyDictionary()


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
    """Create and open a pool for the currently running loop.

    Returns None (without caching anything) when no database is configured,
    e.g. under pytest.
    """
    db_parameters = getattr(web.config, "db_parameters", None) or {}
    if not db_parameters.get("db"):
        logger.info("db_parameters not configured; skipping async pool creation")
        return None

    pool = cast(
        "Pool",
        AsyncConnectionPool(
            conninfo=_conninfo(db_parameters),
            kwargs={"row_factory": dict_row},
            open=False,
        ),
    )
    await pool.open()
    await pool.wait()
    return pool


async def _pool_for_loop() -> Pool | None:
    """Return the running loop's pool, creating and opening it lazily if needed.

    Concurrent first callers on the same loop share a single open task so the
    pool is created only once per loop.
    """
    loop = asyncio.get_running_loop()
    if pool := _pools.get(loop):
        return pool
    if opening := _opening.get(loop):
        return await opening

    task = asyncio.create_task(_open_pool())
    _opening[loop] = task
    try:
        pool = await task
    finally:
        _opening.pop(loop, None)
    if pool is not None:
        _pools[loop] = pool
    return pool


async def init_pool() -> None:
    """Eagerly create the current loop's pool.

    Safe to call multiple times; a pool already created for the running loop is
    reused. When no database is configured (e.g. under pytest) no pool is
    created.
    """
    await _pool_for_loop()


async def close_pool() -> None:
    """Close every cached pool, dispatching each close onto its own loop."""
    current_loop = asyncio.get_running_loop()
    for loop, pool in list(_pools.items()):
        _pools.pop(loop, None)
        try:
            if loop is current_loop:
                await pool.close()
            else:
                asyncio.run_coroutine_threadsafe(pool.close(), loop).result()
        except Exception:
            logger.exception("Error closing async pool for event loop %s", loop)


def get_pool() -> Pool | None:
    """Return the running loop's pool, or None if it was never created."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    return _pools.get(loop)


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
    """Acquire a connection from the running loop's pool.

    Each call checks out a connection from the pool for the duration of the
    ``async with`` block. Callers must commit/rollback themselves for writes.

    Raises:
        RuntimeError: if no pool can be initialized for the running loop (e.g.
            because no database was configured).
    """
    pool = await _pool_for_loop()
    if pool is None:
        raise RuntimeError("Async connection pool is not initialized; call init_pool() during app startup")
    async with pool.connection() as conn:
        yield conn
