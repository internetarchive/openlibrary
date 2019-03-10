from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db

class Follows(object):

    __table__ = "user_follows"

    @classmethod
    def summary(cls):
        return {
            'total_users_following': {
                'total': Follows.total_user_follows(),
                'month': Follows.total_user_follows(since=DATE_ONE_MONTH_AGO),
                'week': Follows.total_user_follows(since=DATE_ONE_WEEK_AGO)
            },
            'total_unique_users_following': {
                'total': Follows.total_user_follows(distinct='username'),
                'month': Follows.total_user_follows(since=DATE_ONE_MONTH_AGO, distinct='username'),
                'week': Follows.total_user_follows(since=DATE_ONE_WEEK_AGO, distinct='username')
            },
            'total_unique_users_followed': {
                'total': Follows.total_user_follows(distinct='followed_username'),
                'month': Follows.total_user_follows(since=DATE_ONE_MONTH_AGO, distinct='followed_username'),
                'week': Follows.total_user_follows(since=DATE_ONE_WEEK_AGO, distinct='followed_username')
            }
        }

    @classmethod
    def total_user_follows(cls, since=None, distinct=None):
        """
        distinct - a key to count distinctly (e.g. username or followed_username)
        """
        oldb = db.get_db()
        count = 'count(DISTINCT $distinct)' if distinct else 'count(*)'
        query = "SELECT %s from %s" % (count, cls.__table__)
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={'since': since, 'distinct': distinct})
        return results[0] if results else None

    @classmethod
    def most_followed_users(cls, username, limit=10, since=False):
        oldb = db.get_db()
        query = 'select followed_username, count(*) as cnt from %s WHERE  ' % cls.__table__
        if since:
            query += " AND created >= $since"
        query += ' group by followed_username order by cnt desc limit $limit'
        return list(oldb.query(query, vars={'shelf_id': shelf_id, 'limit': limit, 'since': since}))

    @classmethod
    def get_users_following(cls, followed_username, limit=50, page=1):
        oldb = db.get_db()
        page = int(page) if page else 1
        offset = limit * (page - 1)
        data = {
            'followed_username': followed_username,
            'limit': limit,
            'offset': offset
        }
        query = ('SELECT username from %s ' % cls.__table__ +
                 'WHERE followed_username=$followed_username '
                 'LIMIT $limit OFFSET $offset')
        return list(oldb.query(query, vars=data))

    @classmethod
    def get_users_followed_by(cls, username, limit=50, page=1):
        oldb = db.get_db()
        page = int(page) if page else 1
        offset = limit * (page - 1)
        data = {
            'username': username,
            'limit': limit,
            'offset': offset
        }
        query = ('SELECT * from %s ' % cls.__table__ +
                 'WHERE username=$username '
                 'LIMIT $limit OFFSET $offset')
        return list(oldb.query(query, vars=data))

    @classmethod
    def get_follow(cls, username, followed_username):
        """Returns record if username is following followed_username"""
        oldb = db.get_db()
        query = ('SELECT * from %s ' % cls.__table__ +
                 'WHERE username=$username AND followed_username=$followed_username')
        return list(oldb.query(query, vars={
            'username': username,
            'followed_username': followed_username
        }))

    @classmethod
    def add(cls, username, followed_username):
        oldb = db.get_db()
        data = {'username': username, 'followed_username': followed_username}

        user_follow = cls.get_follow(username, followed_username)
        if user_follow:
            # Does this return the same thing as oldb.insert?
            return user_follow
        return oldb.insert(cls.__table__, username=username,
                           followed_username=followed_username)

    @classmethod
    def remove(cls, username, followed_username):
        try:
            return oldb.delete(cls.__table__,
                               where=('username=$username AND followed_username=$followed_username'),
                               vars={'username': username, 'followed_username': followed_username})
        except:  # we want to catch no entry exists
            return None
