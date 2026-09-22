from datetime import date, datetime
from typing import ClassVar

from openlibrary.core.async_db import connection
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db


class YearlyReadingGoals:
    TABLENAME = "yearly_reading_goals"

    @classmethod
    def summary(cls) -> dict[str, dict[str, int]]:
        return {
            "total_yearly_reading_goals": {
                "total": YearlyReadingGoals.total_yearly_reading_goals(),
                "month": YearlyReadingGoals.total_yearly_reading_goals(since=DATE_ONE_MONTH_AGO),
                "week": YearlyReadingGoals.total_yearly_reading_goals(since=DATE_ONE_WEEK_AGO),
            },
        }

    @classmethod
    def total_yearly_reading_goals(cls, since: date | None = None) -> int:
        """Returns the number reading goals that were set. `since` may be used
        number reading goals updated. `since` may be used
        to limit the result to those reading goals updated since a specific
        date. Any python datetime.date type should work.
        :param since: returns all reading goals after date
        """
        oldb = db.get_db()

        query = f"SELECT count(*) from {cls.TABLENAME}"
        if since:
            query += " WHERE updated >= $since"
        results = oldb.query(query, vars={"since": since})
        return results[0]["count"] if results else 0

    # Create methods:
    @classmethod
    async def create_async(cls, username: str, year: int, target: int) -> None:
        async with connection() as conn:
            await conn.execute(
                f"INSERT INTO {cls.TABLENAME} (username, year, target) VALUES (%(username)s, %(year)s, %(target)s)",
                {"username": username, "year": year, "target": target},
            )
            await conn.commit()

    # Read methods:
    # web.db's `order=` kwarg is interpolated raw into the SQL string -- only
    # `vars=` substitutions are parameterized -- so any caller passing a
    # user-controlled `order` would have a SQLi sink in the same shape as the
    # /merges bug fixed in PR #12460. Restrict callers to a known set.
    _ALLOWED_ORDERS: ClassVar[dict[str, str]] = {
        "year ASC": "year ASC",
        "year DESC": "year DESC",
    }

    @classmethod
    async def select_by_username_async(cls, username: str, order: str = "year ASC") -> list[dict]:
        if order not in cls._ALLOWED_ORDERS:
            raise ValueError(f"Invalid order: {order!r}. Must be one of {list(cls._ALLOWED_ORDERS)}.")

        query = f"SELECT * FROM {cls.TABLENAME} WHERE username = %(username)s ORDER BY {cls._ALLOWED_ORDERS[order]}"
        async with connection() as conn:
            cursor = await conn.execute(query, {"username": username})
            return await cursor.fetchall()

    @classmethod
    async def select_by_username_and_year_async(cls, username: str, year: int) -> list[dict]:
        query = f"SELECT * FROM {cls.TABLENAME} WHERE username = %(username)s AND year = %(year)s"
        async with connection() as conn:
            cursor = await conn.execute(query, {"username": username, "year": year})
            return await cursor.fetchall()

    # Update methods:
    @classmethod
    async def update_target_async(cls, username: str, year: int, new_target: int) -> None:
        query = f"UPDATE {cls.TABLENAME} SET target = %(target)s, updated = %(updated)s WHERE username = %(username)s AND year = %(year)s"
        async with connection() as conn:
            await conn.execute(
                query,
                {
                    "username": username,
                    "year": year,
                    "target": new_target,
                    "updated": datetime.now(),
                },
            )
            await conn.commit()

    # Delete methods:
    @classmethod
    async def delete_by_username_and_year_async(cls, username: str, year: int) -> None:
        query = f"DELETE FROM {cls.TABLENAME} WHERE username = %(username)s AND year = %(year)s"
        async with connection() as conn:
            await conn.execute(query, {"username": username, "year": year})
            await conn.commit()

    # Bridge (synchronous) API:
    # The legacy web.py template helper get_reading_goals still calls the
    # synchronous select_by_username_and_year. Rather than keeping a parallel
    # web.db implementation, we bridge the async method over async_bridge's
    # persistent loop. The pool is created lazily per event loop (see
    # openlibrary/core/async_db.py), so this works in the web.py process too.
    @classmethod
    def select_by_username_and_year(cls, username: str, year: int) -> list[dict]:
        return async_bridge.run(cls.select_by_username_and_year_async(username, year))
