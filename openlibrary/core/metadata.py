from . import db


class Metadata(object):

    EMOTIONS = {
        'happiness': 1,
        'sadness': 2,
        'fear': 3,
        'disgust': 4,
        'anger': 5,
        'surprise': 6
    }

    @classmethod
    def add_emotion(cls, work_id, username, value):
        value = cls.EMOTIONS[value]
        cls.add(work_id, username, 'emotion', value)

    @classmethod
    def add(cls, work_id, username, feature_id, value):
        oldb = db.get_db()
        work_id = int(work_id)
        value = int(value)

        return oldb.insert('user_metadata', work_id=work_id, username=username, feature_id=feature_id, value=value)