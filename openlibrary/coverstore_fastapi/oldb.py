"""Direct access to the Open Library database.

Async port of openlibrary/coverstore/oldb.py. When ol_db_parameters is
configured, isbn/olid/oclc lookups query the infogami postgres schema directly
(thing/property/data/edition_str tables) instead of making HTTP calls to
openlibrary.org -- matching production coverstore behavior.
"""

import asyncio
import json
from typing import Any

from psycopg import AsyncConnection  # noqa: TC002
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from openlibrary.coverstore_fastapi import config

_pool: AsyncConnectionPool[AsyncConnection[dict[str, Any]]] | None = None
_pool_lock = asyncio.Lock()

# Per-process cache of property ids, mirroring legacy functools.cache behavior.
_property_ids: dict[str, int | None] = {}


def is_supported() -> bool:
    return bool(getattr(config, "ol_db_parameters", None))


async def get_pool() -> AsyncConnectionPool[AsyncConnection[dict[str, Any]]]:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                if not config.ol_db_parameters:
                    raise RuntimeError("ol_db_parameters is not configured")
                p = config.ol_db_parameters
                conninfo = make_conninfo(
                    dbname=p.get("db") or "",
                    host=p.get("host"),
                    port=p.get("port", 5432),
                    user=p.get("user"),
                    password=p.get("pw") or p.get("password"),
                )
                pool: AsyncConnectionPool[AsyncConnection[dict[str, Any]]] = AsyncConnectionPool(
                    conninfo=conninfo,
                    min_size=0,
                    max_size=8,
                    timeout=5,
                    open=False,
                    kwargs={"row_factory": dict_row},
                )
                await pool.open()
                _pool = pool
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def check() -> None:
    """Raises if the Open Library database is unreachable."""
    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT 1")


async def get_property_id(name: str) -> int | None:
    if name in _property_ids:
        return _property_ids[name]

    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT id FROM thing WHERE key = %s", ("/type/edition",))
        type_row: dict[str, Any] | None = await cur.fetchone()
        if type_row is None:
            _property_ids[name] = None
            return None

        await cur.execute(
            "SELECT id FROM property WHERE name = %s AND type = %s",
            (name, type_row["id"]),
        )
        row: dict[str, Any] | None = await cur.fetchone()
        _property_ids[name] = row["id"] if row else None
    return _property_ids[name]


async def query(key: str, value: str) -> list[str]:
    """Returns OL edition keys whose string property `key` equals `value`."""
    if key == "isbn_":
        # 'isbn_' is an alias understood by the openlibrary.org API; the raw
        # table has separate isbn_10 and isbn_13 properties.
        key_ids = [key_id for key_id in (await get_property_id("isbn_13"), await get_property_id("isbn_10")) if key_id is not None]
    else:
        key_id = await get_property_id(key)
        key_ids = [key_id] if key_id is not None else []

    if not key_ids:
        return []

    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT thing.key AS key"
            " FROM thing, edition_str"
            " WHERE thing.id = edition_str.thing_id AND key_id = ANY(%s) AND value = %s"
            " ORDER BY thing.last_modified LIMIT 10",
            (key_ids, value),
        )
        return [row["key"] for row in await cur.fetchall()]


async def get(olkey: str) -> dict[str, Any] | None:
    """Returns the JSON document for an OL key at its latest revision."""
    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT id, latest_revision FROM thing WHERE key = %s", (olkey,))
        thing: dict[str, Any] | None = await cur.fetchone()
        if thing is None:
            return None

        await cur.execute(
            "SELECT data FROM data WHERE thing_id = %s AND revision = %s",
            (thing["id"], thing["latest_revision"]),
        )
        data_row: dict[str, Any] | None = await cur.fetchone()
        if data_row is None:
            return None
        return json.loads(data_row["data"])
