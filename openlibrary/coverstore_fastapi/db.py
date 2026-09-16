"""PostgreSQL layer for the FastAPI coverstore.

Async reimplementation of openlibrary/coverstore/db.py using psycopg3's
AsyncConnectionPool (no web.py). The SQL is kept semantically identical to the
legacy implementation, including the quirky UPDATE in delete() -- see the
comment there.
"""

import asyncio
import contextlib
from typing import Any

from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from openlibrary.coverstore_fastapi import config, utils

_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()
_categories: dict[str, int] | None = None

POOL_MAXCONN = 16


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                p = config.db_parameters
                conninfo = make_conninfo(
                    dbname=p.get("db") or "",
                    host=p.get("host"),
                    port=p.get("port", 5432),
                    user=p.get("user"),
                    password=p.get("pw") or p.get("password"),
                )
                pool = AsyncConnectionPool(
                    conninfo=conninfo,
                    min_size=1,
                    max_size=POOL_MAXCONN,
                    # Fail fast when Postgres is unreachable instead of hanging
                    # requests for the default 30s.
                    timeout=5,
                    open=False,
                    kwargs={"row_factory": dict_row},
                )
                await pool.open()
                _pool = pool
    return _pool


async def close_pool() -> None:
    """Close all pooled connections (called on graceful shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def check() -> None:
    """Raises if the database is unreachable."""
    async with _connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT 1")


@contextlib.asynccontextmanager
async def _connection():
    """A pooled connection; commits on success, rolls back on error."""
    pool = await get_pool()
    async with pool.connection() as conn:
        yield conn


async def _select(sql: str, params: tuple | list) -> list[dict]:
    async with _connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, params)
        return await cur.fetchall()


async def get_category_id(category: str) -> int | None:
    # Loaded once per process, like the legacy implementation.
    global _categories
    if _categories is None:
        rows = await _select("SELECT id, name FROM category", [])
        _categories = {row["name"]: row["id"] for row in rows}
    return _categories.get(category)


async def new(row: dict[str, Any]) -> int:
    """Inserts a cover row (+ log entry) from a covers.save_image payload."""
    category_id = await get_category_id(row["category"])
    now = utils.utcnow()

    async with _connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO cover (category_id, filename, filename_s, filename_m,"
            " filename_l, olid, author, ip, source_url, width, height,"
            " created, last_modified, deleted, archived)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, false)"
            " RETURNING id",
            (
                category_id,
                row["filename"],
                row["filename_s"],
                row["filename_m"],
                row["filename_l"],
                row["olid"],
                row["author"],
                row["ip"],
                row["source_url"],
                row["width"],
                row["height"],
                now,
                now,
            ),
        )
        cover_id = (await cur.fetchone())["id"]
        await cur.execute(
            "INSERT INTO log (action, timestamp, cover_id) VALUES (%s, %s, %s)",
            ("new", now, cover_id),
        )
    return cover_id


async def query(category: str, olid: str | list[Any] | None, offset: int = 0, limit: int = 10) -> list[dict]:
    category_id = await get_category_id(category)

    sql = "SELECT * FROM cover WHERE deleted = %s AND category_id = %s"
    params: list[Any] = [False, category_id]

    if isinstance(olid, list):
        sql += " AND olid = ANY(%s)"
        params.append(olid or [-1])
    elif olid is not None:
        sql += " AND olid = %s"
        params.append(olid)

    sql += " ORDER BY last_modified DESC OFFSET %s LIMIT %s"
    params += [offset, limit]
    return await _select(sql, params)


async def details(id: int | str) -> dict | None:
    rows = await _select("SELECT * FROM cover WHERE id = %s", [id])
    return rows[0] if rows else None


async def touch(id: int) -> None:
    """Sets the last_modified of the specified cover to the current timestamp."""
    now = utils.utcnow()
    async with _connection() as conn, conn.cursor() as cur:
        await cur.execute("UPDATE cover SET last_modified = %s WHERE id = %s", (now, id))
        await cur.execute(
            "INSERT INTO log (action, timestamp, cover_id) VALUES (%s, %s, %s)",
            ("touch", now, id),
        )


async def delete(id: int) -> None:
    # This intentionally reproduces the legacy SQL verbatim:
    #   "UPDATE cover set deleted=$true AND last_modified=$now WHERE id=$id"
    # In SQL that's `SET deleted = ($true AND last_modified = $now)` --
    # a boolean *expression* -- which effectively leaves deleted as-is.
    # Kept for 100% backwards compatibility with the old server.
    true = True
    now = utils.utcnow()
    async with _connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE cover SET deleted = (%s AND last_modified = %s) WHERE id = %s",
            (true, now, id),
        )
        await cur.execute(
            "INSERT INTO log (action, timestamp, cover_id) VALUES (%s, %s, %s)",
            ("delete", now, id),
        )
