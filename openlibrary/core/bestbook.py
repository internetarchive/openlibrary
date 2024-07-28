from . import db

class Bestbook(db.CommonExtras):
    """Best book award operations"""
    TABLENAME = "bestbooks"
    PRIMARY_KEY = "nomination_id"
    ALLOW_DELETE_ON_CONFLICT = False

    @classmethod
    def get_count_by_book(cls, book_id) -> int:
        """Returns number of awards a book has got
        Returns:
            int: count of awards for a book
        """
        oldb = db.get_db()
        query = "SELECT COUNT(*) FROM bestbooks WHERE book_id=$book_id"
        result = oldb.query(query, vars={'book_id': book_id})
        return result[0]['count'] if result else 0

    @classmethod
    def get_count_by_submitter(cls, submitter) -> int:
        """Returns number of awards given by a submitter
        Returns:
            int: count of awards given by a submitter
        """
        oldb = db.get_db()
        query = "SELECT COUNT(*) FROM bestbooks WHERE submitter=$submitter"
        result = oldb.query(query, vars={'submitter': submitter})
        return result[0]['count'] if result else 0

    @classmethod
    def get_count_for_book_by_topic(cls, book_id, topic) -> int:
        """Returns number of awards given to a book for a specific topic
        Returns:
            int: count of awards with book_id & topic
        """
        oldb = db.get_db()
        query = "SELECT COUNT(*) FROM bestbooks WHERE book_id=$book_id AND topic=$topic"
        result = oldb.query(query, vars={'book_id': book_id, 'topic': topic})
        return result[0]['count'] if result else 0

    @classmethod
    def get_total_num_of_awards(cls) -> int:
        """Returns the total number of awards ever given
        Returns:
            int: count of awards given by all pattrons
        """
        oldb = db.get_db()
        query = "SELECT COUNT(*) FROM bestbooks"
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

        if cls.check_if_award_given(submitter, book_id):
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
