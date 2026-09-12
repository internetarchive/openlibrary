"""Table-backed record of librarian batch operations.

One row per batch requested, applied or reverted through
``openlibrary.core.batch_ops`` (previews write nothing). The row keeps the resolved item keys with the
revision each had before the batch ran, so the batch can be reverted as a unit
(or one record at a time) and shown on the librarian dashboard.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, ClassVar

from . import db


class LibrarianBatches:
    TABLENAME = "librarian_batches"

    STATUSES: ClassVar[tuple[str, ...]] = (
        "requested",
        "applying",
        "applied",
        "partially_reverted",
        "reverted",
        "declined",
        "failed",
    )

    @classmethod
    def create(
        cls,
        username: str,
        action: str,
        params: dict[str, Any],
        items: list[dict[str, Any]],
        changes: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        overrides: list[str],
        status: str = "requested",
        comment: str | None = None,
        mrid: int | None = None,
        summary: str | None = None,
    ) -> int:
        oldb = db.get_db()
        return oldb.insert(
            cls.TABLENAME,
            username=username,
            action=action,
            params=json.dumps(params),
            items=json.dumps(items),
            changes=json.dumps(changes),
            warnings=json.dumps(warnings),
            overrides=json.dumps(overrides),
            status=status,
            comment=comment,
            mrid=mrid,
            summary=summary,
        )

    @classmethod
    def update(cls, batch_id: int, **fields: Any) -> None:
        oldb = db.get_db()
        values = {}
        for k, v in fields.items():
            values[k] = json.dumps(v) if k in ("params", "items", "changes", "warnings", "overrides") else v
        values["updated"] = datetime.now(UTC).replace(tzinfo=None)
        oldb.update(cls.TABLENAME, where="id=$id", vars={"id": batch_id}, **values)

    @classmethod
    def get(cls, batch_id: int) -> dict[str, Any] | None:
        oldb = db.get_db()
        rows = list(oldb.select(cls.TABLENAME, where="id=$id", vars={"id": batch_id}))
        return cls._row(rows[0]) if rows else None

    @classmethod
    def list_batches(cls, username: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        oldb = db.get_db()
        wheres, values = [], {}
        if username:
            wheres.append("username=$username")
            values["username"] = username
        if status:
            wheres.append("status=$status")
            values["status"] = status
        rows = oldb.select(
            cls.TABLENAME,
            where=" AND ".join(wheres) or None,
            order="created DESC",
            limit=limit,
            offset=offset,
            vars=values,
        )
        return [cls._row(r) for r in rows]

    @classmethod
    def pending_for_key(cls, key: str) -> list[dict[str, Any]]:
        """Requested batches whose items include ``key``."""
        oldb = db.get_db()
        rows = oldb.query(
            f"SELECT id, action, username, created FROM {cls.TABLENAME} WHERE status='requested' AND items::text LIKE $pattern",
            vars={"pattern": f'%"{key}"%'},
        )
        return [dict(r) for r in rows]

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        d = dict(row)
        for k in ("params", "items", "changes", "warnings", "overrides"):
            v = d.get(k)
            if isinstance(v, str):
                d[k] = json.loads(v)
        for k in ("created", "updated"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        return d
