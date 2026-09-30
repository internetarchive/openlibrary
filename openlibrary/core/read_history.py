from . import db


class ReadHistory(db.CommonExtras):
    TABLENAME = "read_history"
    PRIMARY_KEY = ("username", "work_id")
    ALLOW_DELETE_ON_CONFLICT = True

    @classmethod
    def add(cls, username: str, work_id: int, edition_id: int | None = None):
        oldb = db.get_db()
        return oldb.query(
            """
            INSERT INTO read_history (username, work_id, edition_id, updated)
            VALUES ($username, $work_id, $edition_id, now() at time zone 'utc')
            ON CONFLICT (username, work_id) DO UPDATE SET
                edition_id = EXCLUDED.edition_id,
                updated = EXCLUDED.updated
            """,
            vars={
                "username": username,
                "work_id": work_id,
                "edition_id": edition_id,
            },
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
    def get_for_work(cls, work_id: int | str) -> list:
        oldb = db.get_db()
        work_id = int(work_id)
        return list(
            oldb.select(
                cls.TABLENAME,
                where="work_id=$work_id",
                vars={"work_id": work_id},
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
