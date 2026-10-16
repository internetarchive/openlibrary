from dataclasses import dataclass
from datetime import datetime

from openlibrary.core.async_db import class_row, execute, fetch_all, fetch_one, fetch_val
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db


@dataclass(frozen=True, slots=True)
class Booknote:
    """A row from the ``booknotes`` table."""

    username: str
    work_id: int
    edition_id: int
    notes: str
    created: datetime | None
    updated: datetime | None


class Booknotes(db.CommonExtras):
    TABLENAME = "booknotes"
    PRIMARY_KEY = ("username", "work_id", "edition_id")
    NULL_EDITION_VALUE = -1
    ALLOW_DELETE_ON_CONFLICT = False

    @classmethod
    async def summary(cls) -> dict:
        query = f"""
            SELECT
                count(*) AS total_notes,
                count(*) FILTER (WHERE created >= %(month_ago)s) AS month_notes,
                count(*) FILTER (WHERE created >= %(week_ago)s) AS week_notes,
                count(DISTINCT username) AS total_users,
                count(DISTINCT username) FILTER (WHERE created >= %(month_ago)s) AS month_users,
                count(DISTINCT username) FILTER (WHERE created >= %(week_ago)s) AS week_users
            FROM {cls.TABLENAME}
        """
        row = await fetch_one(
            query,
            {"month_ago": DATE_ONE_MONTH_AGO, "week_ago": DATE_ONE_WEEK_AGO},
        )
        assert row is not None
        return {
            "total_notes_created": {
                "total": row["total_notes"],
                "month": row["month_notes"],
                "week": row["week_notes"],
            },
            "total_note_takers": {
                "total": row["total_users"],
                "month": row["month_users"],
                "week": row["week_users"],
            },
        }

    @classmethod
    def summary_sync(cls) -> dict:
        """Sync version for legacy callers and tests."""
        return async_bridge.run(cls.summary())

    @classmethod
    async def get_booknotes_for_work(cls, work_id: int) -> list[Booknote]:
        query = f"SELECT username, work_id, edition_id, notes, created, updated FROM {cls.TABLENAME} WHERE work_id = %(work_id)s"
        return await fetch_all(query, {"work_id": work_id}, row_factory=class_row(Booknote))

    @classmethod
    def get_booknotes_for_work_sync(cls, work_id: int) -> list[Booknote]:
        """Sync version for legacy callers and tests."""
        return async_bridge.run(cls.get_booknotes_for_work(work_id))

    @classmethod
    async def count_works_with_notes_by_user(cls, username: str) -> int:
        count = await fetch_val(
            f"SELECT COUNT(DISTINCT work_id) FROM {cls.TABLENAME} WHERE username = %(username)s",
            {"username": username},
        )
        return count or 0

    @classmethod
    def count_works_with_notes_by_user_sync(cls, username: str) -> int:
        """Sync version for legacy callers and tests."""
        return async_bridge.run(cls.count_works_with_notes_by_user(username))

    @classmethod
    async def get_patron_booknote(cls, username: str, work_id: int, edition_id: int = NULL_EDITION_VALUE) -> Booknote | None:
        notes = await cls.get_patron_booknotes(username, work_id=work_id, edition_id=edition_id, limit=1)
        return notes[0] if notes else None

    @classmethod
    def get_patron_booknote_sync(cls, username: str, work_id: int, edition_id: int = NULL_EDITION_VALUE) -> Booknote | None:
        """Sync version for legacy callers and tests."""
        return async_bridge.run(cls.get_patron_booknote(username, work_id, edition_id))

    @classmethod
    async def get_patron_booknotes(
        cls,
        username: str,
        work_id: int | None = None,
        edition_id: int = NULL_EDITION_VALUE,
        search: str | None = None,
        limit: int = 100,
        page: int = 1,
    ) -> list[Booknote]:
        page = int(page) if page else 1
        params = {
            "username": username,
            "work_id": work_id,
            "edition_id": edition_id,
            "limit": limit,
            "offset": limit * (page - 1),
            "search_pattern": f"%{search}%" if search else None,
        }
        query = f"SELECT username, work_id, edition_id, notes, created, updated FROM {cls.TABLENAME} WHERE username = %(username)s "
        if work_id:
            query += "AND work_id = %(work_id)s AND edition_id = %(edition_id)s "
        if search:
            query += "AND notes LIKE %(search_pattern)s "
        query += "LIMIT %(limit)s OFFSET %(offset)s"
        return await fetch_all(query, params, row_factory=class_row(Booknote))

    @classmethod
    async def get_notes_grouped_by_work(cls, username: str, limit: int = 25, page: int = 1) -> list[dict]:
        params = {"username": username, "limit": limit, "offset": limit * (page - 1)}
        query = f"""
            SELECT
                work_id,
                json_agg(row_to_json(
                    (SELECT r FROM (SELECT edition_id, notes) r)
                )) AS notes
            FROM {cls.TABLENAME}
            WHERE username = %(username)s
            GROUP BY work_id
            LIMIT %(limit)s OFFSET %(offset)s
        """
        return await fetch_all(query, params)

    @classmethod
    def get_notes_grouped_by_work_sync(cls, username: str, limit: int = 25, page: int = 1) -> list[dict]:
        """Sync version for legacy callers and tests."""
        return async_bridge.run(cls.get_notes_grouped_by_work(username, limit, page))

    @classmethod
    async def add(cls, username: str, work_id: int, notes: str, edition_id: int = NULL_EDITION_VALUE) -> Booknote:
        row = await fetch_one(
            f"""
            INSERT INTO {cls.TABLENAME} (username, work_id, notes, edition_id)
            VALUES (%(username)s, %(work_id)s, %(notes)s, %(edition_id)s)
            ON CONFLICT (username, work_id, edition_id)
            DO UPDATE SET notes = EXCLUDED.notes, updated = DEFAULT
            RETURNING username, work_id, edition_id, notes, created, updated
            """,
            {
                "username": username,
                "work_id": work_id,
                "edition_id": edition_id,
                "notes": notes,
            },
            row_factory=class_row(Booknote),
        )
        assert row is not None
        return row

    @classmethod
    def add_sync(cls, username: str, work_id: int, notes: str, edition_id: int = NULL_EDITION_VALUE) -> Booknote:
        """Sync version for legacy callers and tests."""
        return async_bridge.run(cls.add(username, work_id, notes, edition_id))

    @classmethod
    async def remove(cls, username: str, work_id: int, edition_id: int = NULL_EDITION_VALUE) -> None:
        if work_id is None:
            return None
        await execute(
            f"DELETE FROM {cls.TABLENAME} WHERE username = %(username)s AND work_id = %(work_id)s AND edition_id = %(edition_id)s",
            {
                "username": username,
                "work_id": int(work_id),
                "edition_id": edition_id,
            },
        )

    @classmethod
    def remove_sync(cls, username: str, work_id: int, edition_id: int = NULL_EDITION_VALUE) -> None:
        """Sync version for legacy callers and tests."""
        return async_bridge.run(cls.remove(username, work_id, edition_id))
