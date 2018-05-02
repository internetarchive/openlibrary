from . import db

class Ratings(object):

    @classmethod
    def total_num_books_rated(cls, since=None, distinct=False):
        oldb = db.get_db()
        query = "SELECT count(%s work_id) from ratings" % ('DISTINCT' if distinct else '')
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
        query = 'select work_id, count(*) as cnt from ratings group by work_id order by cnt desc limit $limit'
        if since:
            query += " WHERE created >= $since"
        return list(oldb.query(query, vars={'limit': limit, 'since': since}))

    @classmethod
    def get_users_ratings(cls, username):
        oldb = db.get_db()
        query = 'select * from ratings where username=$username'
        return list(oldb.query(query, vars={'username': username}))
                    
    @classmethod
    def get_all_works_ratings(cls, work_id):
        oldb = db.get_db()
        query = 'select * from ratings where work_id=$work_id'
        return list(oldb.query(query, vars={'work_id': work_id)))

    @classmethod
    def get_users_rating_for_work(cls, username, work_id):
        oldb = db.get_db()
        data = {
            'username': username,
            'work_id': int(work_id)
        }
        query = 'SELECT * from ratings where username=%username AND work_id=$work_id'
        results = list(oldb.query(query, vars=data))
        rating = results[0] if results else None
        return rating

    def remove(cls, username, work):
        # XXX -- should we keep work marked as read...?

        oldb = db.get_db()
        where = {
            'username': username,
            'work_id': int(work_id)
        }
        try:
            return oldb.delete('ratings',
                               where=('work_id=$work_id AND username=$username'), vars=where)
        except:  # we want to catch no entry exists
            return None            

    def add(cls, username, work_id, rating, edition_id=None):
        oldb = db.get_db()
        work_id = int(work_id)
        data = {'work_id': work_id, 'username': username}

        users_rating_for_work = get_users_rating_for_work(username, work_id)

        # XXX -- should we update bookshelf status as read...? Yes.
        # Bookshelves.add(
        #   username, Bookshelves.PRESET_BOOKSHELVES['Already Read'], work_id, edition_id=edition_id)

        if not users_rating_for_work:
            return oldb.insert('ratings', username=username,
                               work_id=work_id, rating=rating, edition_id=edition_id)
        else:
            where = "work_id=$work_id AND username=$username"
            return oldb.update('ratings', where=where,
                               rating=rating,  vars=data)
