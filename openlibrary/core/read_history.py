from datetime import datetime

from . import db


class ReadHistory(db.CommonExtras):
    TABLENAME = "read_history"
    PRIMARY_KEY = ("username", "work_id")
    ALLOW_DELETE_ON_CONFLICT = True

    @classmethod
    def add(cls, username: str, work_id: int, edition_id: int | None = None):
        oldb = db.get_db()
        data = {"username": username, "work_id": work_id}

        existing = list(
            oldb.select(
                cls.TABLENAME,
                where="username=$username AND work_id=$work_id",
                vars=data,
            )
        )
        if not existing:
            return oldb.insert(
                cls.TABLENAME,
                username=username,
                work_id=work_id,
                edition_id=edition_id,
            )
        else:
            return oldb.update(
                cls.TABLENAME,
                where="username=$username AND work_id=$work_id",
                vars=data,
                edition_id=edition_id,
                updated=datetime.now(),
            )

    @classmethod
    def get_history(cls, username: str, limit: int = 20, page: int = 1, offset: int | None = None) -> list:
        oldb = db.get_db()
        page = int(page or 1)
        if offset is None:
            offset = limit * (page - 1)
        return list(
            oldb.select(
                cls.TABLENAME,
                where="username=$username",
                order="updated DESC",
                limit=limit,
                offset=offset,
                vars={"username": username},
            )
        )

    @classmethod
    def clear_history(cls, username: str):
        oldb = db.get_db()
        return oldb.delete(
            cls.TABLENAME,
            where="username=$username",
            vars={"username": username},
        )
