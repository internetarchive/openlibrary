"""Async PostgreSQL access via Psycopg 3.

This module owns the shared async connection pool used by async FastAPI
endpoints. The pool is created once during FastAPI's lifespan startup and
closed on shutdown; see ``openlibrary/asgi_app.py`` for the wiring.

Legacy synchronous web.py code continues to use the ``web.database`` handle in
``openlibrary/core/db.py``. This module is only for async call sites.
"""

import logging

import web
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger("openlibrary.async_db")

_pool: AsyncConnectionPool | None = None


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


async def init_pool() -> None:
    """Create the shared async connection pool from ``web.config.db_parameters``.

    Safe to call multiple times; only the first call creates the pool. When no
    database is configured (e.g. under pytest) the pool is not created.
    """
    global _pool
    if _pool is not None:
        return

    db_parameters = getattr(web.config, "db_parameters", None) or {}
    if not db_parameters.get("db"):
        logger.info("db_parameters not configured; skipping async pool creation")
        return

    _pool = AsyncConnectionPool(
        conninfo=_conninfo(db_parameters),
        kwargs={"row_factory": dict_row},
        open=False,
    )
    await _pool.open()
    await _pool.wait()


async def close_pool() -> None:
    """Close the shared async connection pool, if one was created."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool | None:
    """Return the shared async connection pool, or None if never initialized."""
    return _pool
