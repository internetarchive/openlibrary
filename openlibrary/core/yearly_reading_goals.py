import asyncio
from datetime import date, datetime
from typing import ClassVar, TypedDict, cast

from openlibrary.core.async_db import connection
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO


class YearlyReadingGoal(TypedDict):
    """A row from the ``yearly_reading_goals`` table."""

    username: str
    year: int
    target: int
    created: datetime
    updated: datetime


class YearlyReadingGoals:
    TABLENAME = "yearly_reading_goals"

    @classmethod
    async def summary(cls) -> dict[str, dict[str, int]]:
        total, month, week = await asyncio.gather(
            cls.total_yearly_reading_goals(),
            cls.total_yearly_reading_goals(since=DATE_ONE_MONTH_AGO),
            cls.total_yearly_reading_goals(since=DATE_ONE_WEEK_AGO),
        )
        return {
            "total_yearly_reading_goals": {
                "total": total,
                "month": month,
                "week": week,
            },
        }

    @classmethod
    def summary_sync(cls) -> dict[str, dict[str, int]]:
        return async_bridge.run(cls.summary())

    @classmethod
    async def total_yearly_reading_goals(cls, since: date | None = None) -> int:
        """Count reading goals, optionally filtered to those updated since `since`.

        :param since: if given, only count goals updated at or after this date.
        """
        query = f"SELECT count(*) FROM {cls.TABLENAME}"
        params: dict[str, date] = {}
        if since:
            query += " WHERE updated >= %(since)s"
            params["since"] = since
        async with connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
        return rows[0]["count"] if rows else 0

    # Create methods:
    @classmethod
    async def create(cls, username: str, year: int, target: int) -> None:
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
    async def select_by_username(cls, username: str, order: str = "year ASC") -> list[YearlyReadingGoal]:
        if order not in cls._ALLOWED_ORDERS:
            raise ValueError(f"Invalid order: {order!r}. Must be one of {list(cls._ALLOWED_ORDERS)}.")

        query = f"SELECT * FROM {cls.TABLENAME} WHERE username = %(username)s ORDER BY {cls._ALLOWED_ORDERS[order]}"
        async with connection() as conn:
            cursor = await conn.execute(query, {"username": username})
            return cast(list[YearlyReadingGoal], await cursor.fetchall())

    @classmethod
    async def select_by_username_and_year(cls, username: str, year: int) -> list[YearlyReadingGoal]:
        query = f"SELECT * FROM {cls.TABLENAME} WHERE username = %(username)s AND year = %(year)s"
        async with connection() as conn:
            cursor = await conn.execute(query, {"username": username, "year": year})
            return cast(list[YearlyReadingGoal], await cursor.fetchall())

    # Update methods:
    @classmethod
    async def update_target(cls, username: str, year: int, new_target: int) -> None:
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
    async def delete_by_username_and_year(cls, username: str, year: int) -> None:
        query = f"DELETE FROM {cls.TABLENAME} WHERE username = %(username)s AND year = %(year)s"
        async with connection() as conn:
            await conn.execute(query, {"username": username, "year": year})
            await conn.commit()

    # Bridge (synchronous) API:
    # The legacy web.py template helper get_reading_goals still calls the
    # synchronous select_by_username_and_year_sync. Rather than keeping a
    # parallel web.db implementation, we bridge the async method over
    # async_bridge's persistent loop. The pool is created lazily per event
    # loop (see openlibrary/core/async_db.py), so this works in the web.py
    # process too.
    @classmethod
    def select_by_username_and_year_sync(cls, username: str, year: int) -> list[YearlyReadingGoal]:
        return async_bridge.run(cls.select_by_username_and_year(username, year))
