from datetime import date, datetime

from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db


class YearlyReadingGoals:
    TABLENAME = 'yearly_reading_goals'

    @classmethod
    def summary(cls):
        return {
            'total_yearly_reading_goals': {
                'total': YearlyReadingGoals.total_yearly_reading_goals(),
                'month': YearlyReadingGoals.total_yearly_reading_goals(
                    since=DATE_ONE_MONTH_AGO
                ),
                'week': YearlyReadingGoals.total_yearly_reading_goals(
                    since=DATE_ONE_WEEK_AGO
                ),
            },
        }

    # Create methods:
    @classmethod
    def create(cls, username: str, year: int, target: int):
        oldb = db.get_db()

        return oldb.insert(cls.TABLENAME, username=username, year=year, target=target)

    # Read methods:
    @classmethod
    def select_by_username(cls, username: str, order='year ASC'):
        oldb = db.get_db()

        where = 'username=$username'
        data = {
            'username': username,
        }

        return list(oldb.select(cls.TABLENAME, where=where, order=order, vars=data))

    @classmethod
    def select_by_username_and_year(cls, username: str, year: int):
        oldb = db.get_db()

        where = 'username=$username AND year=$year'
        data = {
            'username': username,
            'year': year,
        }

        return list(oldb.select(cls.TABLENAME, where=where, vars=data))

    @classmethod
    def has_reached_goal(cls, username: str, year: int) -> bool:
        oldb = db.get_db()

        where = 'username=$username AND year=$year'
        data = {
            'username': username,
            'year': year,
        }
        results = list(oldb.select(cls.TABLENAME, where=where, vars=data))

        if not results:
            return False
        else:
            return results[0]['current'] >= results[0]['target']

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
        results = oldb.query(query, vars={'since': since})
        return results[0]['count'] if results else 0

    # Update methods:
    @classmethod
    def update_current_count(cls, username: str, year: int, current_count: int):
        oldb = db.get_db()

        where = 'username=$username AND year=$year'
        data = {
            'username': username,
            'year': year,
        }

        return oldb.update(
            cls.TABLENAME,
            where=where,
            vars=data,
            current=current_count,
            updated=datetime.now(),
        )

    @classmethod
    def update_target(cls, username: str, year: int, new_target: int):
        oldb = db.get_db()

        where = 'username=$username AND year=$year'
        data = {
            'username': username,
            'year': year,
        }

        return oldb.update(
            cls.TABLENAME,
            where=where,
            vars=data,
            target=new_target,
            updated=datetime.now(),
        )

    # Delete methods:
    @classmethod
    def delete_by_username(cls, username):
        oldb = db.get_db()

        where = 'username=$username'
        data = {'username': username}

        return oldb.delete(cls.TABLENAME, where=where, vars=data)

    @classmethod
    def delete_by_username_and_year(cls, username, year):
        oldb = db.get_db()

        data = {
            'username': username,
            'year': year,
        }
        where = 'username=$username AND year=$year'

        return oldb.delete(cls.TABLENAME, where=where, vars=data)
