"""Interface to the Trusted Book Providers (TBP) ``acquisitions`` table.

An acquisition maps a (work, edition, provider) to a JSON blob of provider
metadata (prices, formats, urls, ...). One row exists per edition per
provider. The ingestion cron upserts rows; Solr later reflects them.

Work/edition merges are handled via :meth:`update_work_id` (inherited from
``CommonExtras``) and :meth:`update_edition_id`, so the table stays robust
against ``resolve_redirects``.

See https://github.com/internetarchive/openlibrary/issues/12844 and
https://github.com/internetarchive/openlibrary/pull/12793.
"""

from __future__ import annotations

import datetime
import json
import logging
from sqlite3 import IntegrityError
from typing import TYPE_CHECKING, Any

import web
from psycopg2.errors import UniqueViolation

from . import db
from .db import CommonExtras

logger = logging.getLogger("openlibrary.acquisitions")

if TYPE_CHECKING:
    from web.db import ResultSet


def _utcnow() -> datetime.datetime:
    """Timezone-naive UTC now, matching the table's ``timestamp`` columns."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class Acquisition(web.storage, CommonExtras):
    """A single row of the ``acquisitions`` table."""

    TABLENAME = "acquisitions"
    PRIMARY_KEY = ("edition_id", "provider_name")
    ALLOW_DELETE_ON_CONFLICT = True

    @staticmethod
    def _from_row(row: Any) -> Acquisition:
        acquisition = Acquisition(row)
        # jsonb comes back as a dict from Postgres but as a string from sqlite.
        if isinstance(acquisition.get("data"), str):
            acquisition.data = json.loads(acquisition.data)
        return acquisition

    @staticmethod
    def get_by_edition(edition_id: int, provider_name: str | None = None) -> list[Acquisition]:
        if provider_name is None:
            rows: ResultSet = db.query(
                "SELECT * FROM acquisitions WHERE edition_id=$edition_id ORDER BY provider_name",
                vars={"edition_id": edition_id},
            )
        else:
            rows = db.query(
                "SELECT * FROM acquisitions WHERE edition_id=$edition_id AND provider_name=$provider_name",
                vars={"edition_id": edition_id, "provider_name": provider_name},
            )
        return [Acquisition._from_row(row) for row in rows]

    @staticmethod
    def get_by_work(work_id: int) -> list[Acquisition]:
        rows: ResultSet = db.query(
            "SELECT * FROM acquisitions WHERE work_id=$work_id ORDER BY edition_id, provider_name",
            vars={"work_id": work_id},
        )
        return [Acquisition._from_row(row) for row in rows]

    @staticmethod
    def upsert(
        work_id: int,
        edition_id: int,
        provider_name: str,
        data: dict | None = None,
    ) -> Acquisition | None:
        """Insert or update the acquisition for ``(edition_id, provider_name)``.

        Keyed on the ``(edition_id, provider_name)`` unique constraint; an
        existing row has its ``work_id``/``data`` refreshed.
        """
        payload = json.dumps(data or {})

        def _update() -> int:
            return db.update(
                "acquisitions",
                where="edition_id=$edition_id AND provider_name=$provider_name",
                vars={"edition_id": edition_id, "provider_name": provider_name},
                work_id=work_id,
                data=payload,
                updated=_utcnow(),
            )

        # Update first; insert only when no row exists yet.
        if not _update():
            try:
                db.insert(
                    "acquisitions",
                    work_id=work_id,
                    edition_id=edition_id,
                    provider_name=provider_name,
                    data=payload,
                )
            except UniqueViolation, IntegrityError:
                # Raced with a concurrent insert; fall back to update.
                _update()
        result = Acquisition.get_by_edition(edition_id, provider_name)
        return result[0] if result else None

    @classmethod
    def update_edition_id(cls, current_edition_id: int, new_edition_id: int, _test: bool = False) -> dict:
        """Remap acquisitions when editions merge.

        Mirrors :meth:`CommonExtras.update_work_id` but keyed on
        ``edition_id`` (the column that changes on an edition merge). On a
        unique-constraint clash the surviving edition already has a row for
        that provider, so the redundant row is dropped.
        """
        oldb = db.get_db()
        t = oldb.transaction()
        rows_changed = 0
        rows_deleted = 0

        rows = list(
            oldb.select(
                cls.TABLENAME,
                where="edition_id=$edition_id",
                vars={"edition_id": current_edition_id},
            )
        )
        for row in rows:
            try:
                t_update = oldb.transaction()
                oldb.update(
                    cls.TABLENAME,
                    where="id=$id",
                    vars={"id": row.id},
                    edition_id=new_edition_id,
                    updated=_utcnow(),
                )
                rows_changed += 1
                t_update.rollback() if _test else t_update.commit()
            except UniqueViolation, IntegrityError:
                # Clear the aborted savepoint before issuing the delete.
                t_update.rollback()
                t_delete = oldb.transaction()
                oldb.delete(cls.TABLENAME, where="id=$id", vars={"id": row.id})
                rows_deleted += 1
                t_delete.rollback() if _test else t_delete.commit()

        t.rollback() if _test else t.commit()
        return {"rows_changed": rows_changed, "rows_deleted": rows_deleted}
