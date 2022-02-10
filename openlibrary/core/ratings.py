from typing import TypedDict, Optional

from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db


class WorkRatingsSummary(TypedDict):
    ratings_average: float
    ratings_count: int
    ratings_count_1: int
    ratings_count_2: int
    ratings_count_3: int
    ratings_count_4: int
    ratings_count_5: int


class Ratings:

    VALID_STAR_RATINGS = range(6)  # inclusive: [0 - 5] (0-5 star)

    @classmethod
    def summary(cls):
        return {
            'total_books_starred': {
                'total': Ratings.total_num_books_rated(),
                'month': Ratings.total_num_books_rated(since=DATE_ONE_MONTH_AGO),
                'week': Ratings.total_num_books_rated(since=DATE_ONE_WEEK_AGO),
                'unique': Ratings.total_num_unique_raters(),
            }
        }

    @classmethod
    def total_num_books_rated(cls, since=None, distinct=False):
        oldb = db.get_db()
        query = "SELECT count(%s work_id) from ratings" % (
            'DISTINCT' if distinct else ''
        )
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={'since': since})
        return results[0] if results else None

    @classmethod
    def total_num_unique_raters(cls, since=None):
        oldb = db.get_db()
        query = "select count(DISTINCT username) from ratings"
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={'since': since})
        return results[0] if results else None

    @classmethod
    def most_rated_books(cls, limit=10, since=False):
        oldb = db.get_db()
        query = 'select work_id, count(*) as cnt from ratings '
        if since:
            query += " WHERE created >= $since"
        query += ' group by work_id order by cnt desc limit $limit'
        return list(oldb.query(query, vars={'limit': limit, 'since': since}))

    @classmethod
    def get_users_ratings(cls, username):
        oldb = db.get_db()
        query = 'select * from ratings where username=$username'
        return list(oldb.query(query, vars={'username': username}))

    @classmethod
    def get_rating_stats(cls, work_id):
        oldb = db.get_db()
        query = (
            "SELECT AVG(rating) as avg_rating, COUNT(DISTINCT username) as num_ratings"
            " FROM ratings"
            " WHERE work_id = $work_id"
        )
        result = oldb.query(query, vars={'work_id': int(work_id)})
        return result[0] if result else {}

    @classmethod
    def get_work_ratings_summary(cls, work_id: int) -> Optional[WorkRatingsSummary]:
        oldb = db.get_db()
        # NOTE: Using some old postgres syntax here :/ for modern postgres syntax,
        # see the query in solr_builder.py
        query = """
            SELECT
                avg(rating)::FLOAT as ratings_average,
                count(*) as ratings_count,
                sum( CASE WHEN rating = 1 THEN 1 ELSE 0 END ) as ratings_count_1,
                sum( CASE WHEN rating = 2 THEN 1 ELSE 0 END ) as ratings_count_2,
                sum( CASE WHEN rating = 3 THEN 1 ELSE 0 END ) as ratings_count_3,
                sum( CASE WHEN rating = 4 THEN 1 ELSE 0 END ) as ratings_count_4,
                sum( CASE WHEN rating = 5 THEN 1 ELSE 0 END ) as ratings_count_5
            FROM ratings
            WHERE work_id = $work_id
            GROUP BY work_id
        """
        result = oldb.query(query, vars={'work_id': work_id})
        return result[0] if result else None

    @classmethod
    def get_all_works_ratings(cls, work_id):
        oldb = db.get_db()
        query = 'select * from ratings where work_id=$work_id'
        return list(oldb.query(query, vars={'work_id': work_id}))

    @classmethod
    def get_users_rating_for_work(cls, username, work_id):
        oldb = db.get_db()
        data = {'username': username, 'work_id': int(work_id)}
        query = 'SELECT * from ratings where username=$username AND work_id=$work_id'
        results = list(oldb.query(query, vars=data))
        rating = results[0].rating if results else None
        return rating

    @classmethod
    def remove(cls, username, work_id):
        oldb = db.get_db()
        where = {'username': username, 'work_id': int(work_id)}
        try:
            return oldb.delete(
                'ratings', where=('work_id=$work_id AND username=$username'), vars=where
            )
        except:  # we want to catch no entry exists
            return None

    @classmethod
    def add(cls, username, work_id, rating, edition_id=None):
        from openlibrary.core.bookshelves import Bookshelves

        oldb = db.get_db()
        work_id = int(work_id)
        data = {'work_id': work_id, 'username': username}

        if rating not in cls.VALID_STAR_RATINGS:
            return None

        # Vote implies user read book; Update reading log status as "Already Read"
        users_read_status_for_work = Bookshelves.get_users_read_status_of_work(
            username, work_id
        )
        if users_read_status_for_work != Bookshelves.PRESET_BOOKSHELVES['Already Read']:
            Bookshelves.add(
                username,
                Bookshelves.PRESET_BOOKSHELVES['Already Read'],
                work_id,
                edition_id=edition_id,
            )

        users_rating_for_work = cls.get_users_rating_for_work(username, work_id)
        if not users_rating_for_work:
            return oldb.insert(
                'ratings',
                username=username,
                work_id=work_id,
                rating=rating,
                edition_id=edition_id,
            )
        else:
            where = "work_id=$work_id AND username=$username"
            return oldb.update('ratings', where=where, rating=rating, vars=data)
