from datetime import datetime
from enum import IntEnum

from openlibrary.core.async_db import fetch_all, fetch_one, fetch_val
from openlibrary.utils.async_utils import async_bridge

from . import db


class BookshelfEvent(IntEnum):
    START = 1
    UPDATE = 2
    FINISH = 3

    @classmethod
    def has_value(cls, value: int) -> bool:
        return value in (item.value for item in BookshelfEvent.__members__.values())


class BookshelvesEvents(db.CommonExtras):
    TABLENAME = "bookshelves_events"
    NULL_EDITION_ID = -1

    # Create methods:
    @classmethod
    async def create_event(
        cls,
        username: str,
        work_id: int,
        edition_id: int | None,
        event_date: str,
        event_type=BookshelfEvent.START.value,
    ) -> int:
        row = await fetch_one(
            f"INSERT INTO {cls.TABLENAME} (username, work_id, edition_id, event_type, event_date) "
            "VALUES (%(username)s, %(work_id)s, %(edition_id)s, %(event_type)s, %(event_date)s) RETURNING id",
            {
                "username": username,
                "work_id": work_id,
                "edition_id": edition_id or cls.NULL_EDITION_ID,
                "event_type": event_type,
                "event_date": event_date,
            },
        )
        assert row is not None
        return row["id"]

    @classmethod
    def create_event_sync(
        cls,
        username: str,
        work_id: int,
        edition_id: int | None,
        event_date: str,
        event_type=BookshelfEvent.START.value,
    ) -> int:
        return async_bridge.run(cls.create_event(username, work_id, edition_id, event_date, event_type=event_type))

    # Read methods:
    @classmethod
    async def select_by_id(cls, pid: int) -> list[dict]:
        return await fetch_all(f"SELECT * FROM {cls.TABLENAME} WHERE id = %(id)s", {"id": pid})

    @classmethod
    def select_by_id_sync(cls, pid: int) -> list[dict]:
        return async_bridge.run(cls.select_by_id(pid))

    @classmethod
    def get_latest_event_date(cls, username, work_id, event_type):
        oldb = db.get_db()

        data = {
            "username": username,
            "work_id": work_id,
            "event_type": event_type,
        }

        query = (
            f"SELECT id, event_date FROM {cls.TABLENAME}"
            " WHERE username=$username AND work_id=$work_id"
            " AND event_type=$event_type"
            " ORDER BY event_date DESC LIMIT 1"
        )

        results = list(oldb.query(query, vars=data))
        return results[0] if results else None

    @classmethod
    def get_latest_event_dates(cls, username: str, work_ids: list[int], event_type: int) -> dict[int, dict]:
        """`get_latest_event_date` for a batch: work_id -> {id, event_date}, only for works with an event."""
        if not work_ids:
            return {}
        oldb = db.get_db()
        data = {
            "username": username,
            "work_ids": work_ids,
            "event_type": event_type,
        }
        query = (
            f"SELECT DISTINCT ON (work_id) id, work_id, event_date FROM {cls.TABLENAME}"
            " WHERE username=$username AND work_id IN $work_ids"
            " AND event_type=$event_type"
            " ORDER BY work_id, event_date DESC"
        )
        return {row.work_id: {"id": row.id, "event_date": row.event_date} for row in oldb.query(query, vars=data)}

    @classmethod
    def get_user_yearly_read_counts(cls, username: str) -> list[tuple[int, int]]:
        """Returns books read by year for a given user."""
        results = db.get_db().query(
            """
                SELECT
                    substring(event_date from 1 for 4) as year,
                    count(*) as count
                FROM bookshelves_events
                WHERE username=$username AND event_type=$event_type
                GROUP BY year
                ORDER BY year DESC
            """,
            vars={
                "username": username,
                "event_type": BookshelfEvent.FINISH,
            },
        )

        return [(int(row.year), row.count) for row in results]

    @classmethod
    def select_by_book_user_and_type(cls, username, work_id, edition_id, event_type):
        oldb = db.get_db()

        data = {
            "username": username,
            "work_id": work_id,
            "edition_id": edition_id,
            "event_type": event_type,
        }

        where = """
            username=$username AND
            work_id=$work_id AND
            edition_id=$edition_id AND
            event_type=$event_type
        """

        return list(oldb.select(cls.TABLENAME, where=where, vars=data))

    @classmethod
    async def count_distinct_work_ids_by_user_type_and_year(cls, username: str, event_type: int, year: int) -> int:
        """Distinct works with an event of ``event_type`` in ``year``."""
        query = (
            f"SELECT count(DISTINCT work_id) FROM {cls.TABLENAME}"
            " WHERE username = %(username)s AND event_type = %(event_type)s"
            " AND event_date LIKE %(event_date)s"
        )
        return await fetch_val(
            query,
            {
                "username": username,
                "event_type": event_type,
                "event_date": f"{year}%",
            },
        )

    # Update methods:
    @classmethod
    async def update_event(cls, pid: int, edition_id: int | None = None, event_date: str | None = None, data: str | None = None) -> int:
        updates: dict[str, str | int | datetime] = {}
        if event_date:
            updates["event_date"] = event_date
        if data:
            updates["data"] = data
        if edition_id:
            updates["edition_id"] = edition_id
        if updates:
            updates["updated"] = datetime.now()
            params = {"id": pid, **updates}
            assignments = ", ".join(f"{column} = %({column})s" for column in updates)
            rows = await fetch_all(f"UPDATE {cls.TABLENAME} SET {assignments} WHERE id = %(id)s RETURNING id", params)
            return len(rows)
        return 0

    @classmethod
    def update_event_sync(cls, pid: int, edition_id: int | None = None, event_date: str | None = None, data: str | None = None) -> int:
        return async_bridge.run(cls.update_event(pid, edition_id=edition_id, event_date=event_date, data=data))

    @classmethod
    def update_event_date(cls, pid, event_date):
        oldb = db.get_db()

        where_clause = "id=$id"
        where_vars = {"id": pid}
        update_time = datetime.now()

        return oldb.update(
            cls.TABLENAME,
            where=where_clause,
            vars=where_vars,
            updated=update_time,
            event_date=event_date,
        )

    def update_event_data(cls, pid, data):
        oldb = db.get_db()

        where_clause = "id=$id"
        where_vars = {"id": pid}
        update_time = datetime.now()

        return oldb.update(
            cls.TABLENAME,
            where=where_clause,
            vars=where_vars,
            updated=update_time,
            data=data,
        )

    # Delete methods:
    @classmethod
    async def delete_by_id(cls, pid: int) -> int:
        rows = await fetch_all(f"DELETE FROM {cls.TABLENAME} WHERE id = %(id)s RETURNING id", {"id": pid})
        return len(rows)

    @classmethod
    def delete_by_id_sync(cls, pid: int) -> int:
        return async_bridge.run(cls.delete_by_id(pid))

    @classmethod
    def delete_by_username(cls, username):
        oldb = db.get_db()

        where_clause = "username=$username"
        where_vars = {"username": username}

        return oldb.delete(cls.TABLENAME, where=where_clause, vars=where_vars)

    @classmethod
    def delete_by_username_and_work(cls, username, work_id):
        oldb = db.get_db()

        where_clause = "username=$username AND work_id=$work_id"
        data = {
            "username": username,
            "work_id": work_id,
        }

        return oldb.delete(cls.TABLENAME, where=where_clause, vars=data)
