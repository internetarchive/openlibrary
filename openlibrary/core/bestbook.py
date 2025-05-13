from openlibrary.core.bookshelves import Bookshelves

from . import db


class Bestbook(db.CommonExtras):
    """Best book award operations"""

    TABLENAME = "bestbooks"
    PRIMARY_KEY = "nomination_id"
    ALLOW_DELETE_ON_CONFLICT = False

    class AwardConditionsError(Exception):
        pass

    @classmethod
    def prepare_query(cls, select="*", work_id=None, username=None, topic=None):
        """Prepare query for fetching bestbook awards

        Args:
            work_id (int): work id
            username (string): username of submitter
            topic (string): topic for bestbook award

        Returns:
            str: query string
        """
        conditions = []
        filters = {
            'work_id': work_id,
            'username': username,
            'topic': topic,
        }
        vars = {}

        for key, value in filters.items():
            if value is not None:
                conditions.append(f"{key}=${key}")
                vars[key] = value
        query = f"SELECT {select} FROM {cls.TABLENAME}"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        return query, vars

    @classmethod
    def get_count(cls, work_id=None, username=None, topic=None) -> int:
        """Used to get count of awards with different filters

        Returns:
            int: count of awards
        """
        oldb = db.get_db()
        query, vars = cls.prepare_query(
            select="count(*)", work_id=work_id, username=username, topic=topic
        )
        result = oldb.query(query, vars=vars)
        return result[0]['count'] if result else 0

    @classmethod
    def get_awards(cls, work_id=None, username=None, topic=None):
        """fetch bestbook awards

        Args:
            work_id (int, optional): work id
            username (string, optional): username of submitter
            topic (string, optional): topic for bestbook award

        Returns:
            list: list of awards
        """
        oldb = db.get_db()
        query, vars = cls.prepare_query(
            select="*", work_id=work_id, username=username, topic=topic
        )
        result = oldb.query(query, vars=vars)
        return list(result) if result else []

    @classmethod
    def add(cls, username, work_id, topic, comment="", edition_id=None) -> bool:
        """Add award to database only if award doesn't exist previously

        Args:
            username (text): username of identifier
            work_id (text): unique identifier of book
            edition_id (text): edition for which the award is given to that book
            topic (text): topic for which award is given
            comment (text): comment about award

        Returns:
            award or raises Bestbook.AwardConditionsError
        """
        # Raise cls.AwardConditionsError if any failing conditions
        cls._check_award_conditions(username, work_id, topic)

        oldb = db.get_db()

        return oldb.insert(
            cls.TABLENAME,
            username=username,
            work_id=work_id,
            edition_id=edition_id,
            topic=topic,
            comment=comment,
        )

    @classmethod
    def remove(cls, username, work_id=None, topic=None):
        """Remove any award for this username where either work_id or topic matches.

        Args:
            username (text): unique identifier of patron
            work_id (text, optional): unique identifier of book
            topic (text, optional): topic for which award is given

        Returns:
            int: Number of rows deleted or 0 if no matches found.
        """
        if not work_id and not topic:
            raise ValueError("Either work_id or topic must be specified.")

        oldb = db.get_db()

        # Build WHERE clause dynamically
        conditions = []
        if work_id:
            conditions.append("work_id = $work_id")
        if topic:
            conditions.append("topic = $topic")

        # Combine with AND for username and OR for other conditions
        where_clause = f"username = $username AND ({' OR '.join(conditions)})"

        try:
            return oldb.delete(
                cls.TABLENAME,
                where=where_clause,
                vars={
                    'username': username,
                    'work_id': work_id,
                    'topic': topic,
                },
            )
        except LookupError:  # No matching rows found
            return 0

    @classmethod
    def get_leaderboard(cls):
        """Get the leaderboard of best books

        Returns:
            list: list of best books
        """
        oldb = db.get_db()
        result = db.select(
            cls.TABLENAME,
            what='work_id, COUNT(*) AS count',
            group='work_id',
            order='count DESC',
        )
        return list(result) if result else []

    @classmethod
    def _check_award_conditions(cls, username, work_id, topic):
        errors = []

        if not (work_id and topic):
            errors.append(
                "A work ID and a topic are both required for best book awards"
            )

        else:
            has_read_book = Bookshelves.user_has_read_work(
                username=username, work_id=work_id
            )
            awarded_book = cls.get_awards(username=username, work_id=work_id)
            awarded_topic = cls.get_awards(username=username, topic=topic)

            if not has_read_book:
                errors.append(
                    "Only books which have been marked as read may be given awards"
                )
            if awarded_book:
                errors.append(
                    "A work may only be nominated one time for a best book award"
                )
            if awarded_topic:
                errors.append(
                    f"A topic may only be nominated one time for a best book award: "
                    f"The work {awarded_topic[0].work_id} has already been nominated "
                    f"for topic {awarded_topic[0].topic}"
                )

        if errors:
            raise cls.AwardConditionsError(" ".join(errors))
        return True
