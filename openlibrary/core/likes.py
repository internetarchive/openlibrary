import logging

import web

from . import db

logger = logging.getLogger(__name__)


class Likes:
    TABLENAME = "likes"
    PRIMARY_KEY = ("username", "key")

    # Scope decision (2026-07-29): `key` is intentionally not restricted to any
    # object type. For now, `likes` is intended for lists, and possibly future
    # prompts/activity-feed events -- NOT works, editions, or authors. Those
    # object types go through librarian merge/redirect (see
    # Work.resolve_redirects_bulk in core/models.py), which `likes` does not
    # hook into -- a like on a merged work/author/edition key would silently
    # orphan. If a future change extends `likes` to cover those types, this
    # gap needs to be closed first (either by wiring Likes into the existing
    # work-redirect resolution, or -- for authors -- building an equivalent
    # resolver, since none exists for any feature today).

    @classmethod
    def like(cls, username: str, key: str, value: int = 1) -> None:
        if value not in (1, -1):
            raise ValueError("value must be 1 (like) or -1 (dislike)")
        oldb = db.get_db()
        if not cls.patron_liked(username, key):
            oldb.insert(
                cls.TABLENAME,
                username=username,
                key=key,
                value=value,
            )
        else:
            oldb.update(
                cls.TABLENAME,
                where="username=$username AND key=$key",
                vars={"username": username, "key": key},
                value=value,
                modified=web.db.SQLLiteral("CURRENT_TIMESTAMP"),
            )

    @classmethod
    def unlike(cls, username: str, key: str) -> None:
        oldb = db.get_db()
        if cls.patron_liked(username, key):
            oldb.delete(
                cls.TABLENAME,
                where="username=$username AND key=$key",
                vars={"username": username, "key": key},
            )

    @classmethod
    def dislike(cls, username: str, key: str) -> None:
        cls.like(username, key, value=-1)

    @classmethod
    def get_count(cls, key: str) -> dict[str, int]:
        oldb = db.get_db()
        likes_count = oldb.query("SELECT value, COUNT(*) as count FROM likes WHERE key=$key AND value=1 GROUP BY value", vars={"key": key})
        dislike_count = oldb.query("SELECT value, COUNT(*) as count FROM likes WHERE key=$key AND value=-1 GROUP BY value", vars={"key": key})
        return {"likes": likes_count[0]["count"] if likes_count else 0, "dislikes": dislike_count[0]["count"] if dislike_count else 0}

    @classmethod
    def get_for_patron(cls, username: str, limit: int = 50, offset: int = 0) -> list:
        """Return all likes by a patron, paginated."""
        oldb = db.get_db()
        likes = oldb.select(
            cls.TABLENAME,
            where="username=$username",
            vars={"username": username},
            limit=limit,
            offset=offset,
        )
        return list(likes)

    @classmethod
    def patron_liked(cls, username: str, key: str) -> bool:
        """Return whether the patron has liked this key."""
        oldb = db.get_db()
        like = oldb.select(
            cls.TABLENAME,
            where="username=$username AND key=$key",
            vars={"username": username, "key": key},
            limit=1,
        )
        return len(like) > 0
