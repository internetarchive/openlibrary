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
FastAPI lifespan runs. ``init_pool()`` can pre-warm the current loop's pool
at FastAPI startup. ``close_pool()`` closes every cached pool, each on its
own loop.

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
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
    """Create and open a pool for the running loop.

    Returns None when no database is configured or psycopg is missing, e.g.
    under pytest.
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
    await pool.open()
    await pool.wait()
    return pool


async def _pool_for_loop() -> Pool | None:
    """Return the running loop's pool, creating it lazily if needed.

    Concurrent first callers on the same loop share a single open task, so
    the pool opens once per loop.
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
    """Pre-warm the running loop's pool.

    Safe to call repeatedly; an existing pool is reused. When no database is
    configured, e.g. under pytest, no pool is created.
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
                # Close on the owning loop and await the result here through
                # wrap_future, so the current loop keeps running instead of
                # blocking its thread on .result().
                fut = asyncio.run_coroutine_threadsafe(pool.close(), loop)
                await asyncio.wait_for(asyncio.wrap_future(fut), timeout=10)
        except Exception:
            logger.exception("Error closing async pool for event loop %s", loop)


def get_pool() -> Pool | None:
    """Return the running loop's pool, or None if it was never created."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    return _pools.get(loop)


def reset_pools() -> None:
    """Drop all cached pools and in-flight open tasks.

    For test isolation; real code should call :func:`close_pool`.
    """
    _pools.clear()
    _opening.clear()


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
