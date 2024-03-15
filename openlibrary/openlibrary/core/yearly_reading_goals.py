from datetime import datetime
from . import db


class YearlyReadingGoals:
    TABLENAME = 'yearly_reading_goals'

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
            updated=datetime.utcnow(),
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
            updated=datetime.utcnow(),
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
