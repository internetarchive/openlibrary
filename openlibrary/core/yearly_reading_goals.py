from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from openlibrary.core.async_db import class_row, execute, fetch_all, fetch_one
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO


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
        row = await fetch_one(query, {"month_ago": DATE_ONE_MONTH_AGO, "week_ago": DATE_ONE_WEEK_AGO})
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

    # Create methods:
    @classmethod
    async def create(cls, username: str, year: int, target: int) -> None:
        await execute(
            f"INSERT INTO {cls.TABLENAME} (username, year, target) VALUES (%(username)s, %(year)s, %(target)s)",
            {"username": username, "year": year, "target": target},
        )

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

        query = f"SELECT username, year, target, created, updated FROM {cls.TABLENAME} WHERE username = %(username)s ORDER BY {cls._ALLOWED_ORDERS[order]}"
        return await fetch_all(query, {"username": username}, row_factory=class_row(YearlyReadingGoal))

    @classmethod
    async def select_by_username_and_year(cls, username: str, year: int) -> list[YearlyReadingGoal]:
        query = f"SELECT username, year, target, created, updated FROM {cls.TABLENAME} WHERE username = %(username)s AND year = %(year)s"
        return await fetch_all(query, {"username": username, "year": year}, row_factory=class_row(YearlyReadingGoal))

    # Update methods:
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

    # Delete methods:
    @classmethod
    async def delete_by_username_and_year(cls, username: str, year: int) -> None:
        query = f"DELETE FROM {cls.TABLENAME} WHERE username = %(username)s AND year = %(year)s"
        await execute(query, {"username": username, "year": year})
