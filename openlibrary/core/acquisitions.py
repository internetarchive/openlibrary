"""Interface to the Trusted Book Providers (TBP) ``acquisitions`` table.

An acquisition maps a (work, edition, provider) to a JSON blob of provider
metadata (prices, formats, urls, ...). One row exists per edition per
provider. The ingestion cron upserts rows; Solr later reflects them.

Work merges are handled via :meth:`update_work_id` (inherited from
``CommonExtras``), so the table stays robust against ``resolve_redirects``.

See https://github.com/internetarchive/openlibrary/issues/12844 and
https://github.com/internetarchive/openlibrary/pull/12793.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING

import web

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

    id: int
    work_id: int
    edition_id: int
    provider_name: str
    local_id: str
    data: dict
    created: datetime.datetime
    updated: datetime.datetime

    # Configuration for CommonExtras mixin:
    TABLENAME = "acquisitions"
    # These aren't actually used for acquisitions since work/edition IDs are not
    # part of a unique constraint, so work/edition merges will never cause a conflict
    # in this table.
    PRIMARY_KEY = ("local_id", "provider_name")
    ALLOW_DELETE_ON_CONFLICT = False

    @staticmethod
    def _from_row(row: web.storage) -> Acquisition:
        acquisition = Acquisition(row)
        # jsonb comes back as a dict from Postgres but as a string from SQLite.
        if isinstance(data := acquisition.get("data"), str):
            acquisition.data = json.loads(data)
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
        local_id: str,
        data: dict | None = None,
    ) -> Acquisition | None:
        """Insert or update the acquisition for ``(local_id, provider_name)``.

        Keyed on the ``(local_id, provider_name)`` unique constraint; an
        existing row has its ``work_id``/``edition_id``/``data`` refreshed.
        """
        # Need a transaction for the RETURNING * clause
        with db.transaction():
            result = list(
                db.query(
                    """
                    INSERT INTO acquisitions (work_id, edition_id, provider_name, local_id, data)
                    VALUES ($work_id, $edition_id, $provider_name, $local_id, $data)
                    ON CONFLICT (local_id, provider_name) DO UPDATE SET
                        work_id = EXCLUDED.work_id,
                        edition_id = EXCLUDED.edition_id,
                        data = EXCLUDED.data,
                        updated = $updated
                    RETURNING *
                    """,
                    vars={
                        "work_id": work_id,
                        "edition_id": edition_id,
                        "provider_name": provider_name,
                        "local_id": local_id,
                        "data": json.dumps(data or {}),
                        "updated": _utcnow(),
                    },
                )
            )
        return Acquisition._from_row(result[0]) if result else None
