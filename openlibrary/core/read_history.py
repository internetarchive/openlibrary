from typing import Any

from openlibrary.core.async_db import connection, execute, fetch_all
from openlibrary.utils.async_utils import async_bridge


class ReadHistory:
    TABLENAME = "read_history"

    @classmethod
    async def add(cls, username: str, work_id: int, edition_id: int | None = None) -> None:
        await execute(
            f"""
            INSERT INTO {cls.TABLENAME} (username, work_id, edition_id, updated)
            VALUES (%(username)s, %(work_id)s, %(edition_id)s, now() at time zone 'utc')
            ON CONFLICT (username, work_id) DO UPDATE SET
                edition_id = EXCLUDED.edition_id,
                updated = EXCLUDED.updated
            """,
            {"username": username, "work_id": work_id, "edition_id": edition_id},
        )

    @classmethod
    def add_sync(cls, username: str, work_id: int, edition_id: int | None = None) -> None:
        return async_bridge.run(cls.add(username, work_id, edition_id))

    @classmethod
    async def get_history(cls, username: str, limit: int = 20, page: int = 1, offset: int | None = None) -> list[dict[str, Any]]:
        page = int(page or 1)
        if offset is None:
            offset = limit * (page - 1)
        return await fetch_all(
            f"SELECT * FROM {cls.TABLENAME} WHERE username = %(username)s ORDER BY updated DESC LIMIT %(limit)s OFFSET %(offset)s",
            {"username": username, "limit": limit, "offset": offset},
        )

    @classmethod
    def get_history_sync(cls, username: str, limit: int = 20, page: int = 1, offset: int | None = None) -> list[dict[str, Any]]:
        return async_bridge.run(cls.get_history(username, limit, page, offset))

    @classmethod
    async def get_for_work(cls, work_id: int | str) -> list[dict[str, Any]]:
        return await fetch_all(f"SELECT * FROM {cls.TABLENAME} WHERE work_id = %(work_id)s", {"work_id": int(work_id)})

    @classmethod
    def get_for_work_sync(cls, work_id: int | str) -> list[dict[str, Any]]:
        return async_bridge.run(cls.get_for_work(work_id))

    @classmethod
    async def clear_history(cls, username: str) -> None:
        await execute(f"DELETE FROM {cls.TABLENAME} WHERE username = %(username)s", {"username": username})

    @classmethod
    def clear_history_sync(cls, username: str) -> None:
        return async_bridge.run(cls.clear_history(username))

    @classmethod
    async def update_username(cls, username: str, new_username: str, _test: bool = False) -> int:
        """Rename a patron's rows, optionally rolling back for dry-run counts."""
        async with connection() as conn:
            cursor = await conn.execute(
                f"UPDATE {cls.TABLENAME} SET username = %(new_username)s WHERE username = %(username)s",
                {"username": username, "new_username": new_username},
            )
            rows_changed = cursor.rowcount
            if _test:
                await conn.rollback()
        return rows_changed

    @classmethod
    async def update_work_id(cls, current_work_id: int | str, new_work_id: int | str, _test: bool = False) -> dict[str, int]:
        """Move every row from ``current_work_id`` to ``new_work_id`` (e.g. after a work redirect).

        A patron who already has a row for ``new_work_id`` would violate the primary key,
        so their row for the old work is deleted instead of moved.
        """
        params = {"current": int(current_work_id), "new": int(new_work_id)}
        async with connection() as conn:
            deleted = await conn.execute(
                f"""
                DELETE FROM {cls.TABLENAME}
                WHERE work_id = %(current)s
                  AND username IN (SELECT username FROM {cls.TABLENAME} WHERE work_id = %(new)s)
                """,
                params,
            )
            rows_deleted = deleted.rowcount
            updated = await conn.execute(f"UPDATE {cls.TABLENAME} SET work_id = %(new)s WHERE work_id = %(current)s", params)
            rows_changed = updated.rowcount
            if _test:
                await conn.rollback()
        return {"rows_changed": rows_changed, "rows_deleted": rows_deleted, "failed_deletes": 0}

    @classmethod
    def update_work_id_sync(cls, current_work_id: int | str, new_work_id: int | str, _test: bool = False) -> dict[str, int]:
        return async_bridge.run(cls.update_work_id(current_work_id, new_work_id, _test))
