import web

from openlibrary.core.async_db import fetch_all, fetch_one, fetch_val
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.utils.async_utils import async_bridge

from . import db


class Bestbook(db.CommonExtras):
    """Best book award operations"""

    TABLENAME = "bestbooks"
    PRIMARY_KEY = "award_id"
    ALLOW_DELETE_ON_CONFLICT = False

    class AwardConditionsError(Exception):
        pass

    # `select` is interpolated raw into the SQL string below. Restrict it to
    # the two values the rest of this class actually needs so the function
    # cannot be turned into a column-list SQL injection sink if a future
    # caller forwards user input as `select`.
    _ALLOWED_SELECTS: tuple[str, ...] = ("*", "count(*)")

    @classmethod
    def prepare_query(
        cls,
        select: str = "*",
        work_id: str | None = None,
        username: str | None = None,
        topic: str | None = None,
    ) -> tuple[str, dict]:
        """Prepare query for fetching bestbook awards"""
        if select not in cls._ALLOWED_SELECTS:
            raise ValueError(f"Invalid select: {select!r}. Must be one of {cls._ALLOWED_SELECTS}.")
        conditions = []
        filters = {
            "work_id": work_id,
            "username": username,
            "topic": topic,
        }
        vars = {}

        for key, value in filters.items():
            if value is not None:
                param_value: str | int = value
                if key == "work_id":
                    param_value = int(extract_numeric_id_from_olid(str(value)))
                conditions.append(f"{key} = %({key})s")
                vars[key] = param_value
        query = f"SELECT {select} FROM {cls.TABLENAME}"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        return query, vars

    @classmethod
    async def get_count(
        cls,
        work_id: str | None = None,
        username: str | None = None,
        topic: str | None = None,
    ) -> int:
        """Get the count of awards matching the provided filters."""
        query, vars = cls.prepare_query(select="count(*)", work_id=work_id, username=username, topic=topic)
        return await fetch_val(query, vars) or 0

    @classmethod
    def get_count_sync(
        cls,
        work_id: str | None = None,
        username: str | None = None,
        topic: str | None = None,
    ) -> int:
        """Synchronous bridge for legacy web.py callers."""
        return async_bridge.run(cls.get_count(work_id=work_id, username=username, topic=topic))

    @classmethod
    async def get_awards(
        cls,
        work_id: str | None = None,
        username: str | None = None,
        topic: str | None = None,
    ) -> list:
        """Fetches a list of bestbook awards based on the provided filters.

        This method queries the database to retrieve awards associated with a
        specific work, submitted by a particular user, or related to a given topic.
        """
        query, vars = cls.prepare_query(select="*", work_id=work_id, username=username, topic=topic)
        return await fetch_all(query, vars)

    @classmethod
    def get_awards_sync(
        cls,
        work_id: str | None = None,
        username: str | None = None,
        topic: str | None = None,
    ) -> list:
        """Synchronous bridge preserving web.py storage rows for legacy callers."""
        rows = async_bridge.run(cls.get_awards(work_id=work_id, username=username, topic=topic))
        return [web.storage(row) for row in rows]

    @classmethod
    async def add(
        cls,
        username: str,
        work_id: str,
        topic: str,
        comment: str = "",
        edition_id: int | None = None,
    ) -> int | None:
        """Add award to database only if award doesn't exist previously
        or raises Bestbook.AwardConditionsError
        """
        # Raise cls.AwardConditionsError if any failing conditions
        await cls._check_award_conditions(username, work_id, topic)

        row = await fetch_one(
            f"""
            INSERT INTO {cls.TABLENAME} (username, work_id, edition_id, topic, comment)
            VALUES (%(username)s, %(work_id)s, %(edition_id)s, %(topic)s, %(comment)s)
            ON CONFLICT DO NOTHING
            RETURNING award_id
            """,
            {
                "username": username,
                "work_id": work_id,
                "edition_id": edition_id,
                "topic": topic,
                "comment": comment,
            },
        )
        if row is not None:
            return row["award_id"]

        # A concurrent request may have inserted the same work or topic after
        # validation passed. Recheck to return the domain validation error.
        await cls._check_award_conditions(username, work_id, topic)
        raise cls.AwardConditionsError("A work or topic has already been nominated")

    @classmethod
    async def remove(cls, username: str, work_id: str | None = None, topic: str | None = None) -> int:
        """Remove any award for this username where either work_id or topic matches."""
        if not work_id and not topic:
            raise ValueError("Either work_id or topic must be specified.")

        # Build WHERE clause dynamically
        conditions = []
        params = {"username": username}
        if work_id:
            conditions.append("work_id = %(work_id)s")
            params["work_id"] = work_id
        if topic:
            conditions.append("topic = %(topic)s")
            params["topic"] = topic

        # Combine with AND for username and OR for other conditions
        query = f"DELETE FROM {cls.TABLENAME} WHERE username = %(username)s AND ({' OR '.join(conditions)}) RETURNING award_id"
        return len(await fetch_all(query, params))

    @classmethod
    def get_leaderboard(cls) -> list[dict]:
        """Get the leaderboard of best books"""

        oldb = db.get_db()

        result = oldb.select(
            cls.TABLENAME,
            what="work_id, COUNT(*) AS count",
            group="work_id",
            order="count DESC",
        )
        return list(result) if result else []

    @classmethod
    async def _check_award_conditions(cls, username: str, work_id: str, topic: str) -> bool:
        """
        Validates the conditions for adding a bestbook award.

        This method checks if the provided work ID and topic meet the necessary
        conditions for adding a best book award. It ensures that:
        - Both a work ID and a topic are provided.
        - The user has marked the book as read.
        - The work has not already been nominated for a best book award by the user.
        - The topic has not already been nominated for a best book award by the user.

        If any of these conditions are not met, it raises a Bestbook.AwardConditionsError
        with the appropriate error messages.
        """
        errors = []

        if not (work_id and topic):
            errors.append("A work ID and a topic are both required for best book awards")

        else:
            has_read_book = await Bookshelves.user_has_read_work(username=username, work_id=work_id)
            awarded_book = await cls.get_awards(username=username, work_id=work_id)
            awarded_topic = await cls.get_awards(username=username, topic=topic)

            if not has_read_book:
                errors.append("Only books which have been marked as read may be given awards")
            if awarded_book:
                errors.append("A work may only be nominated one time for a best book award")
            if awarded_topic:
                errors.append(
                    f"A topic may only be nominated one time for a best book award: "
                    f"The work {awarded_topic[0]['work_id']} has already been nominated "
                    f"for topic {awarded_topic[0]['topic']}"
                )

        if errors:
            raise cls.AwardConditionsError(" ".join(errors))
        return True
