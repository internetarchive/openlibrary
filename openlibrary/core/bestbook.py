from . import db

class Bestbook(db.CommonExtras):
    """Best book award operations"""
    TABLENAME = "bestbooks"
    PRIMARY_KEY = "nomination_id"
    ALLOW_DELETE_ON_CONFLICT = False

    @classmethod
    def get_count(cls, book_id=None, submitter=None, topic=None) -> int:
        """Used to get count of awards with different filters

        Returns:
            int: count of awards
        """
        oldb = db.get_db()
        query = "SELECT COUNT(*) FROM bestbooks "

        if book_id:
            query += "WHERE book_id=$book_id "

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

        result = oldb.query(query)
        return result[0]['count'] if result else 0

    @classmethod
    def check_if_award_given(cls, submitter, book_id, topic) -> bool:
        """This function checks if the award is already given to a book or topic by pattron

        Args:
            submitter (text): submitter identifier
            book_id (text): unique identifier of book
            topic (text): topic for which award is given

        Returns:
            bool: returns true if award already given
        """
        oldb = db.get_db()
        data = {
            'submitter': submitter,
            'book_id': book_id,
            'topic': topic
        }

        query = """
            SELECT
                COUNT(*)
            FROM bestbooks
            WHERE submitter=$submitter AND (book_id=$book_id OR topic=$topic)
        """
        return oldb.query(query, vars=data)[0]['count'] > 0

    @classmethod
    def add(cls, submitter, book_id, topic, comment) -> bool:
        """This function adds award to database only if award doesn't exist previously

        Args:
            submitter (text): submitter identifier
            book_id (text): unique identifier of book
            topic (text): topic for which award is given
            comment (text): comment about award

        Returns:
            bool: true if award is added
        """
        oldb = db.get_db()

        if cls.check_if_award_given(submitter, book_id, topic):
            return False

        oldb.insert(
            'bestbooks',
            submitter=submitter,
            book_id=book_id,
            topic=topic,
            comment=comment
        )
        return True

    @classmethod
    def remove(cls, submitter, book_id) -> bool:
        """remove bestbook award from a book

        Args:
            submitter (text): unique idenitifier of pattron
            book_id (text): unique identifier of book

        Returns:
            bool: return True if award is removed
        """
        oldb = db.get_db()
        where = {
            'submitter': submitter,
            'book_id': book_id
        }
        try:
            oldb.delete(
                'bestbooks',
                where=(
                    'submitter=$submitter AND book_id=$book_id'
                ),
                vars=where,
            )
        except:  # we want to catch no entry exists
            return False
        return True
