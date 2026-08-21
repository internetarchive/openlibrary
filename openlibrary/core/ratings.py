from math import sqrt
from typing import TypedDict

from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db


class WorkRatingsSummary(TypedDict):
    ratings_average: float
    ratings_sortable: float
    ratings_count: int
    ratings_count_1: int
    ratings_count_2: int
    ratings_count_3: int
    ratings_count_4: int
    ratings_count_5: int


class Ratings(db.CommonExtras):
    TABLENAME = "ratings"
    VALID_STAR_RATINGS = range(6)  # inclusive: [0 - 5] (0-5 star)
    PRIMARY_KEY = ("username", "work_id")
    ALLOW_DELETE_ON_CONFLICT = True

    @classmethod
    def summary(cls) -> dict:
        return {
            "total_books_starred": {
                "total": Ratings.total_num_books_rated(),
                "month": Ratings.total_num_books_rated(since=DATE_ONE_MONTH_AGO),
                "week": Ratings.total_num_books_rated(since=DATE_ONE_WEEK_AGO),
            },
            "total_star_raters": {
                "total": Ratings.total_num_unique_raters(),
                "month": Ratings.total_num_unique_raters(since=DATE_ONE_MONTH_AGO),
                "week": Ratings.total_num_unique_raters(since=DATE_ONE_WEEK_AGO),
            },
        }

    @classmethod
    def total_num_books_rated(cls, since=None, distinct=False) -> int | None:
        oldb = db.get_db()
        query = "SELECT count(%s work_id) from ratings" % ("DISTINCT" if distinct else "")
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={"since": since})
        return results[0]["count"] if results else 0

    @classmethod
    def total_num_unique_raters(cls, since=None) -> int:
        oldb = db.get_db()
        query = "select count(DISTINCT username) from ratings"
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={"since": since})
        return results[0]["count"] if results else 0

    @classmethod
    def most_rated_books(cls, limit=10, since=False) -> list:
        oldb = db.get_db()
        query = "select work_id, count(*) as cnt from ratings "
        if since:
            query += " WHERE created >= $since"
        query += " group by work_id order by cnt desc limit $limit"
        return list(oldb.query(query, vars={"limit": limit, "since": since}))

    @classmethod
    def get_users_ratings(cls, username) -> list:
        oldb = db.get_db()
        query = "select * from ratings where username=$username"
        return list(oldb.query(query, vars={"username": username}))

    @classmethod
    def get_rating_stats(cls, work_id) -> dict:
        oldb = db.get_db()
        query = "SELECT AVG(rating) as avg_rating, COUNT(DISTINCT username) as num_ratings FROM ratings WHERE work_id = $work_id"
        result = oldb.query(query, vars={"work_id": int(work_id)})
        return result[0] if result else {}

    @classmethod
    def get_work_ratings_summary(cls, work_id: int) -> WorkRatingsSummary | None:
        oldb = db.get_db()
        query = """
            SELECT
                count(*) FILTER (WHERE rating = 1) AS ratings_count_1,
                count(*) FILTER (WHERE rating = 2) AS ratings_count_2,
                count(*) FILTER (WHERE rating = 3) AS ratings_count_3,
                count(*) FILTER (WHERE rating = 4) AS ratings_count_4,
                count(*) FILTER (WHERE rating = 5) AS ratings_count_5
            FROM ratings
            WHERE work_id = $work_id
        """
        result = oldb.query(query, vars={"work_id": work_id})
        if not result:
            return None

        row = result[0]
        return cls.work_ratings_summary_from_counts([row[f"ratings_count_{i}"] for i in range(1, 6)])

    @classmethod
    def work_ratings_summary_from_counts(cls, rating_counts: list[int]) -> WorkRatingsSummary:
        total_count = sum(rating_counts, 0)
        ratings_average = (sum((k * n_k for k, n_k in enumerate(rating_counts, 1)), 0) / total_count) if total_count != 0 else 0
        return {
            "ratings_average": ratings_average,
            "ratings_sortable": cls.compute_sortable_rating(rating_counts),
            "ratings_count": total_count,
            "ratings_count_1": rating_counts[0],
            "ratings_count_2": rating_counts[1],
            "ratings_count_3": rating_counts[2],
            "ratings_count_4": rating_counts[3],
            "ratings_count_5": rating_counts[4],
        }

    @classmethod
    def compute_sortable_rating(cls, rating_counts: list[int]) -> float:
        """
        Computes a rating that can be used for sorting works by rating. It takes
        into account the fact that a book with only 1 rating that is 5 stars, is not
        necessarily "better" than a book with 1 rating that is 1 star, and 10 ratings
        that are 5 stars. The first book has an average rating of 5, but the second
        book has an average rating of 4.6 .

        Uses the algorithm from:
        https://www.evanmiller.org/ranking-items-with-star-ratings.html
        """
        n = rating_counts
        N = sum(n, 0)
        K = len(n)
        z = 1.65
        return sum(((k + 1) * (n_k + 1) / (N + K) for k, n_k in enumerate(n)), 0) - z * sqrt(
            (sum((((k + 1) ** 2) * (n_k + 1) / (N + K) for k, n_k in enumerate(n)), 0) - sum(((k + 1) * (n_k + 1) / (N + K) for k, n_k in enumerate(n)), 0) ** 2)
            / (N + K + 1)
        )

    @classmethod
    def get_all_works_ratings(cls, work_id) -> list:
        oldb = db.get_db()
        query = "select * from ratings where work_id=$work_id"
        return list(oldb.query(query, vars={"work_id": int(work_id)}))

    @classmethod
    def get_users_rating_for_work(cls, username: str, work_id: str | int) -> int | None:
        """work_id must be convertible to int."""
        oldb = db.get_db()
        data = {"username": username, "work_id": int(work_id)}
        query = "SELECT * from ratings where username=$username AND work_id=$work_id"
        results = list(oldb.query(query, vars=data))
        rating: int | None = results[0].rating if results else None
        return rating

    @classmethod
    def remove(cls, username, work_id):
        oldb = db.get_db()
        where = {"username": username, "work_id": int(work_id)}
        try:
            return oldb.delete("ratings", where=("work_id=$work_id AND username=$username"), vars=where)
        except:  # we want to catch no entry exists
            return None

    @classmethod
    def add(cls, username, work_id, rating, edition_id=None):
        from openlibrary.core.bookshelves import Bookshelves

        oldb = db.get_db()
        work_id = int(work_id)
        data = {"work_id": work_id, "username": username}

        if rating not in cls.VALID_STAR_RATINGS:
            return None

        # Vote implies user read book; Update reading log status as "Already Read"
        users_read_status_for_work = Bookshelves.get_users_read_status_of_work(username, work_id)
        if users_read_status_for_work != Bookshelves.PRESET_BOOKSHELVES["Already Read"]:
            Bookshelves.add(
                username,
                Bookshelves.PRESET_BOOKSHELVES["Already Read"],
                work_id,
                edition_id=edition_id,
            )

        users_rating_for_work = cls.get_users_rating_for_work(username, work_id)
        if not users_rating_for_work:
            return oldb.insert(
                "ratings",
                username=username,
                work_id=work_id,
                rating=rating,
                edition_id=edition_id,
            )
        else:
            where = "work_id=$work_id AND username=$username"
            return oldb.update("ratings", where=where, rating=rating, vars=data)

    @classmethod
    def calc_star_rating_counts(cls) -> dict[str, int]:
        results = {}
        oldb = db.get_db()
        total_ratings_query = """
            select count(*) from ratings
            WHERE created >= date_trunc('hour', now() - interval '1 hour')
                AND created < date_trunc('hour', now());
        """
        totals = oldb.query(total_ratings_query)
        results["star_ratings"] = next(iter(totals))["count"]

        distinct_raters_query = """
            select count(distinct username) from ratings
            WHERE created >= date_trunc('hour', now() - interval '1 hour')
                AND created < date_trunc('hour', now());
        """
        distinct_totals = oldb.query(distinct_raters_query)
        results["distinct_star_ratings"] = next(iter(distinct_totals))["count"]

        return results
