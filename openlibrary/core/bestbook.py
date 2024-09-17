from . import db


class Bestbook(db.CommonExtras):
    """Best book award operations"""

    TABLENAME = "bestbooks"
    PRIMARY_KEY = "nomination_id"
    ALLOW_DELETE_ON_CONFLICT = False

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
    def check_if_award_given(cls, submitter, work_id=None, topic=None) -> bool:
        """This function checks if the award is already given to a book or topic by pattron

        Args:
            submitter (text): submitter identifier
            work_id (text): unique identifier of book
            topic (text): topic for which award is given

        Returns:
            bool: returns true if award already given
        """
        oldb = db.get_db()
        data = {'submitter': submitter, 'work_id': work_id, 'topic': topic}

        query = """
            SELECT
                COUNT(*)
            FROM bestbooks
            WHERE submitter=$submitter
        """

        if topic and work_id:
            query += " AND (work_id=$work_id AND topic=$topic)"
        elif work_id:
            query += " AND work_id=$work_id"
        elif topic:
            query += " AND topic=$topic"

        return oldb.query(query, vars=data)[0]['count'] > 0

    @classmethod
    def add(cls, submitter, work_id, topic, comment, edition_id=None) -> bool:
        """This function adds award to database only if award doesn't exist previously

        Args:
            submitter (text): submitter identifier
            work_id (text): unique identifier of book
            edition_id (text): edition for which the award is given to that book
            topic (text): topic for which award is given
            comment (text): comment about award

        Returns:
            bool: true if award is added
        """
        oldb = db.get_db()

        if cls.check_if_award_given(submitter, work_id, topic):
            return False

        oldb.insert(
            'bestbooks',
            submitter=submitter,
            work_id=work_id,
            edition_id=edition_id,
            topic=topic,
            comment=comment,
        )
        return True

    @classmethod
    def remove(cls, submitter, work_id):
        """remove bestbook award from a book

        Args:
            submitter (text): unique identifier of pattron
            work_id (text): unique identifier of book

        Returns:
            bool: return True if award is removed
        """
        oldb = db.get_db()
        where = {'submitter': submitter, 'work_id': work_id}

        try:
            return oldb.delete(
                'bestbooks',
                where=('submitter=$submitter AND work_id=$work_id'),
                vars=where,
            )
        except LookupError:  # we want to catch no entry exists
            return None
