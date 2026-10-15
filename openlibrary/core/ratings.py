from math import sqrt
from typing import TypedDict

from openlibrary.core.async_db import execute, fetch_all, fetch_one, fetch_val
from openlibrary.utils.async_utils import async_bridge
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
    async def summary(cls) -> dict:
        return {
            "total_books_starred": {
                "total": await cls.total_num_books_rated(),
                "month": await cls.total_num_books_rated(since=DATE_ONE_MONTH_AGO),
                "week": await cls.total_num_books_rated(since=DATE_ONE_WEEK_AGO),
            },
            "total_star_raters": {
                "total": await cls.total_num_unique_raters(),
                "month": await cls.total_num_unique_raters(since=DATE_ONE_MONTH_AGO),
                "week": await cls.total_num_unique_raters(since=DATE_ONE_WEEK_AGO),
            },
        }

    @classmethod
    def summary_sync(cls) -> dict:
        return async_bridge.run(cls.summary())

    @classmethod
    async def total_num_books_rated(cls, since=None, distinct=False) -> int:
        query = "SELECT count(%s) from ratings" % ("DISTINCT work_id" if distinct else "work_id")
        if since:
            query += " WHERE created >= %(since)s"
        count = await fetch_val(query, {"since": since} if since else None)
        return count or 0

    @classmethod
    async def total_num_unique_raters(cls, since=None) -> int:
        query = "select count(DISTINCT username) from ratings"
        if since:
            query += " WHERE created >= %(since)s"
        count = await fetch_val(query, {"since": since} if since else None)
        return count or 0

    @classmethod
    async def most_rated_books(cls, limit=10, since=False) -> list:
        query = "select work_id, count(*) as cnt from ratings "
        if since:
            query += " WHERE created >= %(since)s"
        query += " group by work_id order by cnt desc limit %(limit)s"
        return await fetch_all(query, {"limit": limit, "since": since} if since else {"limit": limit})

    @classmethod
    def most_rated_books_sync(cls, limit=10, since=False) -> list:
        return async_bridge.run(cls.most_rated_books(limit, since))

    @classmethod
    async def get_users_ratings(cls, username) -> list:
        query = "select * from ratings where username=%(username)s"
        return await fetch_all(query, {"username": username})

    @classmethod
    async def get_rating_stats(cls, work_id) -> dict:
        query = "SELECT AVG(rating) as avg_rating, COUNT(DISTINCT username) as num_ratings FROM ratings WHERE work_id = %(work_id)s"
        row = await fetch_one(query, {"work_id": int(work_id)})
        return row or {}

    @classmethod
    def get_rating_stats_sync(cls, work_id) -> dict:
        return async_bridge.run(cls.get_rating_stats(work_id))

    @classmethod
    async def get_work_ratings_summary(cls, work_id: int) -> WorkRatingsSummary | None:
        query = """
            SELECT
                count(*) FILTER (WHERE rating = 1) AS ratings_count_1,
                count(*) FILTER (WHERE rating = 2) AS ratings_count_2,
                count(*) FILTER (WHERE rating = 3) AS ratings_count_3,
                count(*) FILTER (WHERE rating = 4) AS ratings_count_4,
                count(*) FILTER (WHERE rating = 5) AS ratings_count_5
            FROM ratings
            WHERE work_id = %(work_id)s
        """
        row = await fetch_one(query, {"work_id": work_id})
        if not row or sum(row.get(f"ratings_count_{i}", 0) for i in range(1, 6)) == 0:
            return None

        return cls.work_ratings_summary_from_counts([row[f"ratings_count_{i}"] for i in range(1, 6)])

    @classmethod
    def get_work_ratings_summary_sync(cls, work_id: int) -> WorkRatingsSummary | None:
        return async_bridge.run(cls.get_work_ratings_summary(work_id))

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
    async def get_all_works_ratings(cls, work_id) -> list:
        query = "select * from ratings where work_id=%(work_id)s"
        return await fetch_all(query, {"work_id": int(work_id)})

    @classmethod
    def get_all_works_ratings_sync(cls, work_id) -> list:
        return async_bridge.run(cls.get_all_works_ratings(work_id))

    @classmethod
    async def get_users_rating_for_work(cls, username: str, work_id: str | int) -> int | None:
        """work_id must be convertible to int."""
        query = "SELECT * from ratings where username=%(username)s AND work_id=%(work_id)s"
        row = await fetch_one(query, {"username": username, "work_id": int(work_id)})
        return row["rating"] if row else None

    @classmethod
    def get_users_rating_for_work_sync(cls, username: str, work_id: str | int) -> int | None:
        return async_bridge.run(cls.get_users_rating_for_work(username, work_id))

    @classmethod
    async def get_users_ratings_of_works(cls, username: str, work_ids: list[int]) -> dict[int, int]:
        """Map work_id -> rating for the subset of `work_ids` this user has rated."""
        if not work_ids:
            return {}
        query = "SELECT work_id, rating FROM ratings WHERE username=%(username)s AND work_id = ANY(%(work_ids)s)"
        rows = await fetch_all(query, {"username": username, "work_ids": work_ids})
        return {row["work_id"]: row["rating"] for row in rows}

    @classmethod
    def get_users_ratings_of_works_sync(cls, username: str, work_ids: list[int]) -> dict[int, int]:
        return async_bridge.run(cls.get_users_ratings_of_works(username, work_ids))

    @classmethod
    async def remove(cls, username, work_id):
        work_id = int(work_id)
        await execute(
            "DELETE FROM ratings WHERE work_id = %(work_id)s AND username = %(username)s",
            {"work_id": work_id, "username": username},
        )

    @classmethod
    async def add(cls, username, work_id, rating, edition_id=None):
        from openlibrary.core.bookshelves import Bookshelves

        work_id = int(work_id)

        if rating not in cls.VALID_STAR_RATINGS:
            return None

        # Vote implies user read book, so shelve unshelved (or Want to Read) books
        # as "Already Read". Never overwrite Currently Reading or Stopped Reading,
        # where the patron has explicitly said otherwise.
        users_read_status_for_work = Bookshelves.get_users_read_status_of_work(username, work_id)
        if users_read_status_for_work in (
            None,
            Bookshelves.PRESET_BOOKSHELVES["Want to Read"],
        ):
            Bookshelves.add(
                username,
                Bookshelves.PRESET_BOOKSHELVES["Already Read"],
                work_id,
                edition_id=edition_id,
            )

        # A single upsert, so concurrent first ratings of the same work can't
        # both insert and trip the (username, work_id) primary key.
        await execute(
            """
            INSERT INTO ratings (username, work_id, rating, edition_id)
            VALUES (%(username)s, %(work_id)s, %(rating)s, %(edition_id)s)
            ON CONFLICT (username, work_id) DO UPDATE SET rating = EXCLUDED.rating
            """,
            {"username": username, "work_id": work_id, "rating": rating, "edition_id": edition_id},
        )

    @classmethod
    async def calc_star_rating_counts(cls) -> dict[str, int]:
        total_ratings_query = """
            select count(*) from ratings
            WHERE created >= date_trunc('hour', now() - interval '1 hour')
                AND created < date_trunc('hour', now());
        """
        totals = await fetch_val(total_ratings_query)
        star_ratings = totals or 0

        distinct_raters_query = """
            select count(distinct username) from ratings
            WHERE created >= date_trunc('hour', now() - interval '1 hour')
                AND created < date_trunc('hour', now());
        """
        distinct_totals = await fetch_val(distinct_raters_query)
        distinct_star_ratings = distinct_totals or 0

        return {"star_ratings": star_ratings, "distinct_star_ratings": distinct_star_ratings}

    @classmethod
    def calc_star_rating_counts_sync(cls) -> dict[str, int]:
        return async_bridge.run(cls.calc_star_rating_counts())
