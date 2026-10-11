from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from openlibrary.core.async_db import class_row, execute, fetch_all, fetch_one
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.dateutil import date_one_month_ago, date_one_week_ago


@dataclass(frozen=True, slots=True)
class YearlyReadingGoal:
    """A row from the ``yearly_reading_goals`` table."""

    username: str
    year: int
    target: int
    created: datetime | None
    updated: datetime | None


class YearlyReadingGoals:
    TABLENAME = "yearly_reading_goals"

    @classmethod
    async def summary(cls) -> dict[str, dict[str, int]]:
        query = (
            f"SELECT count(*) AS total,"
            f" count(*) FILTER (WHERE updated >= %(month_ago)s) AS month,"
            f" count(*) FILTER (WHERE updated >= %(week_ago)s) AS week"
            f" FROM {cls.TABLENAME}"
        )
        row = await fetch_one(query, {"month_ago": date_one_month_ago(), "week_ago": date_one_week_ago()})
        assert row is not None
        return {
            "total_yearly_reading_goals": {
                "total": row["total"],
                "month": row["month"],
                "week": row["week"],
            },
        }

    @classmethod
    def summary_sync(cls) -> dict[str, dict[str, int]]:
        return async_bridge.run(cls.summary())

    @classmethod
    async def create(cls, username: str, year: int, target: int) -> None:
        await execute(
            f"INSERT INTO {cls.TABLENAME} (username, year, target) VALUES (%(username)s, %(year)s, %(target)s)",
            {"username": username, "year": year, "target": target},
        )

    # Read methods:
    # web.db's `order=` is raw SQL, only `vars=` is parameterized. Limit
    # callers to a known set to avoid a SQLi sink like the /merges bug in PR #12460.
    _ALLOWED_ORDERS: ClassVar[dict[str, str]] = {
        "year ASC": "year ASC",
        "year DESC": "year DESC",
    }

    @classmethod
    async def select_by_username(cls, username: str, order: str = "year ASC") -> list[YearlyReadingGoal]:
        if order not in cls._ALLOWED_ORDERS:
            raise ValueError(f"Invalid order: {order!r}. Must be one of {list(cls._ALLOWED_ORDERS)}.")

        query = f"SELECT username, year, target, created, updated FROM {cls.TABLENAME} WHERE username = %(username)s ORDER BY {cls._ALLOWED_ORDERS[order]}"
        return await fetch_all(query, {"username": username}, row_factory=class_row(YearlyReadingGoal))

    @classmethod
    async def select_by_username_and_year(cls, username: str, year: int) -> YearlyReadingGoal | None:
        """The user's goal for ``year``, or None if they have not set one."""
        query = f"SELECT username, year, target, created, updated FROM {cls.TABLENAME} WHERE username = %(username)s AND year = %(year)s"
        return await fetch_one(query, {"username": username, "year": year}, row_factory=class_row(YearlyReadingGoal))

    @classmethod
    async def update_target(cls, username: str, year: int, new_target: int) -> None:
        query = f"UPDATE {cls.TABLENAME} SET target = %(target)s, updated = %(updated)s WHERE username = %(username)s AND year = %(year)s"
        await execute(
            query,
            {
                "username": username,
                "year": year,
                "target": new_target,
                "updated": datetime.now(),
            },
        )

    @classmethod
    async def delete_by_username_and_year(cls, username: str, year: int) -> None:
        query = f"DELETE FROM {cls.TABLENAME} WHERE username = %(username)s AND year = %(year)s"
        await execute(query, {"username": username, "year": year})
