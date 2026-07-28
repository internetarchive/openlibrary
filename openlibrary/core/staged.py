"""Interface to the ``tbp_staged_record`` staging buffer.

Part of the BookWorm staging pipeline (#12655 / #12844). Harvested feed records
land here first — in an isolated staging DB, so bulk ingestion never contends
with production Open Library — before being promoted into the catalog.

Each row carries both the normalized import ``record`` (the "olbook") and its
provider ``acquisition`` metadata (price/formats/url). Keeping the acquisition
alongside the record is what lets the post-import step attach an acquisition to
the edition once the catalog creates it — the record and its acquisition never
get separated.

In production the ``bookworm`` service points its DB connection at the staging
DB; the interface itself uses the standard ``db`` abstraction so it is portable
and unit-testable.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

import web

from . import db

logger = logging.getLogger("openlibrary.staged")

if TYPE_CHECKING:
    from web.db import ResultSet

STAGED = "staged"
PROMOTED = "promoted"
FAILED = "failed"


def _utcnow() -> datetime.datetime:
    """Timezone-naive UTC now, matching the table's ``timestamp`` columns."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class StagedRecord(web.storage):
    """A single row of the ``tbp_staged_record`` staging buffer."""

    TABLENAME = "tbp_staged_record"

    @staticmethod
    def _from_row(row: Any) -> StagedRecord:
        staged = StagedRecord(row)
        # jsonb comes back as a dict from Postgres but as a string from sqlite.
        for field in ("record", "acquisition"):
            if isinstance(staged.get(field), str):
                staged[field] = json.loads(staged[field])
        return staged

    @staticmethod
    def find(provider_name: str, local_id: str) -> StagedRecord | None:
        result = db.query(
            "SELECT * FROM tbp_staged_record WHERE provider_name=$provider_name AND local_id=$local_id",
            vars={"provider_name": provider_name, "local_id": local_id},
        )
        return StagedRecord._from_row(result[0]) if result else None

    @staticmethod
    def pending(limit: int = 1000) -> list[StagedRecord]:
        """Records awaiting promotion into the catalog, oldest first."""
        rows: ResultSet = db.query(
            "SELECT * FROM tbp_staged_record WHERE status=$status ORDER BY id LIMIT $limit",
            vars={"status": STAGED, "limit": limit},
        )
        return [StagedRecord._from_row(row) for row in rows]

    @staticmethod
    def upsert(
        provider_name: str,
        local_id: str,
        record: dict,
        acquisition: dict | None = None,
    ) -> StagedRecord | None:
        """Stage a harvested record, idempotent on ``(provider_name, local_id)``.

        Re-harvesting refreshes the record/acquisition in place (and re-arms it
        for promotion) rather than creating a duplicate.
        """
        if existing := StagedRecord.find(provider_name, local_id):
            db.update(
                "tbp_staged_record",
                where="id=$id",
                vars={"id": existing.id},
                record=json.dumps(record),
                acquisition=json.dumps(acquisition) if acquisition is not None else None,
                status=STAGED,
                updated=_utcnow(),
            )
        else:
            db.insert(
                "tbp_staged_record",
                provider_name=provider_name,
                local_id=local_id,
                record=json.dumps(record),
                acquisition=json.dumps(acquisition) if acquisition is not None else None,
                status=STAGED,
            )
        return StagedRecord.find(provider_name, local_id)

    @staticmethod
    def set_status(id: int, status: str) -> int:
        """Mark a staged record ``promoted`` or ``failed`` after processing."""
        return db.update(
            "tbp_staged_record",
            where="id=$id",
            vars={"id": id},
            status=status,
            updated=_utcnow(),
        )
