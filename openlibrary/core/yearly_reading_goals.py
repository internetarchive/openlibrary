from datetime import date, datetime
from typing import ClassVar

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

    # Create methods:
    @classmethod
    def create(cls, username: str, year: int, target: int) -> None:
        oldb = db.get_db()
        oldb.insert(cls.TABLENAME, username=username, year=year, target=target)

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
    def select_by_username(cls, username: str, order: str = "year ASC") -> list[dict]:
        oldb = db.get_db()

        if order not in cls._ALLOWED_ORDERS:
            raise ValueError(f"Invalid order: {order!r}. Must be one of {list(cls._ALLOWED_ORDERS)}.")

        where = "username=$username"
        data = {
            "username": username,
        }

        return list(oldb.select(cls.TABLENAME, where=where, order=cls._ALLOWED_ORDERS[order], vars=data))

    @classmethod
    def select_by_username_and_year(cls, username: str, year: int) -> list[dict]:
        oldb = db.get_db()

        where = "username=$username AND year=$year"
        data = {
            "username": username,
            "year": year,
        }

        return list(oldb.select(cls.TABLENAME, where=where, vars=data))

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

    # Update methods:
    @classmethod
    def update_target(cls, username: str, year: int, new_target: int) -> None:
        oldb = db.get_db()

        where = "username=$username AND year=$year"
        data = {
            "username": username,
            "year": year,
        }

        oldb.update(
            cls.TABLENAME,
            where=where,
            vars=data,
            target=new_target,
            updated=datetime.now(),
        )

    # Delete methods:
    @classmethod
    def delete_by_username(cls, username: str) -> None:
        oldb = db.get_db()

        where = "username=$username"
        data = {"username": username}

        oldb.delete(cls.TABLENAME, where=where, vars=data)

    @classmethod
    def delete_by_username_and_year(cls, username: str, year: int) -> None:
        oldb = db.get_db()

        data = {
            "username": username,
            "year": year,
        }
        where = "username=$username AND year=$year"

        oldb.delete(cls.TABLENAME, where=where, vars=data)
