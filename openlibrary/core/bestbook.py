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
    def get_count(cls, work_id=None, submitter=None, topic=None) -> int:
        """Used to get count of awards with different filters

        Returns:
            int: count of awards
        """
        oldb = db.get_db()
        query = "SELECT COUNT(*) FROM bestbooks "

        if work_id:
            query += "WHERE work_id=$work_id "

        if submitter:
            if query.find("WHERE") != -1:
                query += "AND "
            else:
                query += "WHERE "
            query += "submitter=$submitter "

        if topic:
            if query.find("WHERE") != -1:
                query += "AND "
            else:
                query += "WHERE "
            query += "topic=$topic "

        result = oldb.query(
            query, vars={'work_id': work_id, 'submitter': submitter, 'topic': topic}
        )
        return result[0]['count'] if result else 0

    @classmethod
    def get_awards(cls, work_id=None, submitter=None, topic=None):
        """fetch bestbook awards

        Args:
            work_id (int, optional): work id
            submitter (string, optional): username of submitter
            topic (string, optional): topic for bestbook award

        Returns:
            list: list of awards
        """
        oldb = db.get_db()
        query = "SELECT * FROM bestbooks "

        if work_id:
            query += "WHERE work_id=$work_id "

        if submitter:
            if query.find("WHERE") != -1:
                query += "AND "
            else:
                query += "WHERE "
            query += "submitter=$submitter "

        if topic:
            if query.find("WHERE") != -1:
                query += "AND "
            else:
                query += "WHERE "
            query += "topic=$topic "

        result = oldb.query(
            query, vars={'work_id': work_id, 'submitter': submitter, 'topic': topic}
        )
        return list(result) if result else []

    @classmethod
    def check_if_award_given(cls, submitter, work_id=None, topic=None):
        """This function checks if the award is already given to a book or topic by patron

        Args:
            submitter (text): submitter identifier
            work_id (text): unique identifier of book
            topic (text): topic for which award is given

        Returns:
            award: returns first matching award or None
        """
        oldb = db.get_db()
        data = {'submitter': submitter, 'work_id': work_id, 'topic': topic}

        query = """
            SELECT *
            FROM bestbooks
            WHERE submitter=$submitter
        """

        if topic and work_id:
            query += " AND (work_id=$work_id AND topic=$topic)"
        elif work_id:
            query += " AND work_id=$work_id"
        elif topic:
            query += " AND topic=$topic"
        award = list(oldb.query(query, vars=data))
        return award[0] if award else None

    @classmethod
    def add(cls, submitter, work_id, topic, comment="", edition_id=None) -> bool:
        """Add award to database only if award doesn't exist previously

        Args:
            submitter (text): submitter identifier
            work_id (text): unique identifier of book
            edition_id (text): edition for which the award is given to that book
            topic (text): topic for which award is given
            comment (text): comment about award

        Returns:
            award or raises Bestbook.AwardConditionsError
        """
        oldb = db.get_db()

        # Raise cls.AwardConditionsError if any failing conditions
        cls._check_award_conditions(submitter, work_id, topic)

        return oldb.insert(
            'bestbooks',
            submitter=submitter,
            work_id=work_id,
            edition_id=edition_id,
            topic=topic,
            comment=comment,
        )

    @classmethod
    def remove(cls, submitter, work_id=None, topic=None):
        """Remove any award for this submitter where either work_id or topic matches.

        Args:
            submitter (text): unique identifier of patron
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

        # Combine with AND for submitter and OR for other conditions
        where_clause = f"submitter = $submitter AND ({' OR '.join(conditions)})"

        try:
            return oldb.delete(
                'bestbooks',
                where=where_clause,
                vars={
                    'submitter': submitter,
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
        query = """
            SELECT
                work_id,
                COUNT(*) AS count
            FROM bestbooks
            GROUP BY work_id
            ORDER BY count DESC
        """
        result = oldb.query(query)
        print(result)
        return list(result) if result else []

    @classmethod
    def _check_award_conditions(cls, username, work_id, topic):
        errors = []

        if not (work_id and topic):
            errors += "A work ID and a topic are both required for best book awards"

        else:
            has_read_book = Bookshelves.user_has_read_work(
                username=username, work_id=work_id
            )
            awarded_book = cls.check_if_award_given(username, work_id=work_id)
            awarded_topic = cls.check_if_award_given(username, topic=topic)

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
                    f"A topic may only be nominated one time for a best book award: The work {awarded_topic.work_id} has already been nominated for topic {awarded_topic.topic}"
                )

        if errors:
            raise cls.AwardConditionsError(" ".join(errors))
        return True
