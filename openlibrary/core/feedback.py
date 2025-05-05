# openlibrary/core/feedback.py
from openlibrary.core import db

def insert_feedback(key, score, patron_name=None, country=None):
    oldb = db.get_db()
    return oldb.insert(
        'feedback',
        key=key,
        score=score,
        patron_name=patron_name,
        country=country,
    )

def get_feedback_by_key(key):
    oldb = db.get_db()
    return list(oldb.select('feedback', where="key=$key", vars={"key": key}))
