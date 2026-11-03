"""Read Solr updates straight from Infobase's ``transaction`` table.

Every Infobase save inserts one ``transaction`` row with the changed keys and
their new revisions, and writes the saved documents to ``data`` in the same
database transaction. Reading those rows gives the Solr updater the same keys
the Infobase write log does, with no extra table or trigger.

Transaction ids come from a sequence, so they are handed out before commit and
can become visible out of order. The reader keeps a cursor on the highest id it
has seen and remembers the ids below it that weren't visible yet ("gaps"). A gap
is re-read until it shows up, or until every transaction that was running when
the gap was first seen has finished: after that it can never show up (it was
rolled back), so it is dropped. Postgres snapshots tell us exactly when that is.
"""

import datetime as dt
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from openlibrary.core import async_db

logger = logging.getLogger("openlibrary.solr-updater")

FORCE_UPDATE_TYPE = "solr-force-update"


def find_document_keys(document: dict | list) -> Iterator[str]:
    """Yield every ``key`` referenced anywhere in a saved Infobase document."""
    if isinstance(document, dict):
        if key := document.get("key"):
            yield key
        for value in document.values():
            yield from find_document_keys(value)
    elif isinstance(document, list):
        for value in document:
            yield from find_document_keys(value)


@dataclass
class TransactionLogBatch:
    keys: list[str]
    transaction_count: int
    last_created: dt.datetime | None


@dataclass
class TransactionLog:
    """Cursor over the ``transaction`` table.

    ``position`` is the persisted checkpoint: every transaction with an id at or
    below it has been processed or will never commit. Restarting from it can
    reprocess a few transactions above it, which is harmless.
    """

    position: int
    batch_size: int = 100
    _high: int = field(init=False)
    # gap id -> txid_snapshot_xmax() when the gap was first seen
    _gaps: dict[int, int] = field(init=False, default_factory=dict)
    _next_gaps: dict[int, int] = field(init=False, default_factory=dict)
    _next_high: int = field(init=False)

    def __post_init__(self):
        self._high = self._next_high = self.position

    @property
    def pending_gaps(self) -> list[int]:
        return sorted(self._gaps)

    async def read(self) -> TransactionLogBatch:
        rows = await async_db.fetch_all(
            """
            WITH snap AS (
                SELECT
                    txid_snapshot_xmin(txid_current_snapshot()) AS xmin,
                    txid_snapshot_xmax(txid_current_snapshot()) AS xmax
            ),
            tx AS (
                SELECT id, created, changes
                FROM transaction
                WHERE id > %(high)s OR id = ANY(%(gaps)s)
                ORDER BY id
                LIMIT %(limit)s
            )
            SELECT
                snap.xmin,
                snap.xmax,
                tx.id,
                tx.created,
                changed.key AS changed_key,
                current_data.data AS current_data,
                previous_data.data AS previous_data
            FROM snap
            LEFT JOIN tx ON true
            LEFT JOIN LATERAL jsonb_to_recordset(tx.changes::jsonb)
                AS changed(key text, revision integer) ON true
            LEFT JOIN thing ON thing.key = changed.key
            LEFT JOIN data AS current_data
                ON current_data.thing_id = thing.id
                AND current_data.revision = changed.revision
            LEFT JOIN data AS previous_data
                ON previous_data.thing_id = thing.id
                AND previous_data.revision = changed.revision - 1
            ORDER BY tx.id
            """,
            {"high": self._high, "gaps": list(self._gaps), "limit": self.batch_size},
        )
        xmin, xmax = rows[0]["xmin"], rows[0]["xmax"]
        seen = sorted({row["id"] for row in rows if row["id"] is not None})

        gaps = {gap: seen_at for gap, seen_at in self._gaps.items() if gap not in seen}
        high = self._high
        for tx_id in seen:
            if tx_id > high:
                gaps.update(dict.fromkeys(range(high + 1, tx_id), xmax))
                high = tx_id
        # Every transaction that could have held these ids has finished, and the
        # ids still aren't visible: they were rolled back and will never commit.
        for gap in [gap for gap, seen_at in gaps.items() if xmin >= seen_at]:
            del gaps[gap]
        self._next_gaps, self._next_high = gaps, high

        keys: list[str] = []
        last_created = None
        for row in rows:
            if row["id"] is None:
                continue
            last_created = max(last_created or row["created"], row["created"])
            if row["changed_key"] is None:
                continue
            keys.append(row["changed_key"])
            if row["current_data"] is None:
                # Can't happen for a committed save; reindex the key anyway rather than block.
                logger.error("No data for %s in transaction %s", row["changed_key"], row["id"])
                continue
            if row["previous_data"]:
                # Keys the old revision referenced but the new one doesn't, e.g. the
                # work an edition moved away from.
                before = set(find_document_keys(json.loads(row["previous_data"])))
                after = set(find_document_keys(json.loads(row["current_data"])))
                keys.extend(before - after)
        return TransactionLogBatch(list(dict.fromkeys(keys)), len(seen), last_created)

    def commit(self) -> int:
        """Advance past the last batch once it's been indexed. Returns the new position."""
        self._gaps, self._high = self._next_gaps, self._next_high
        self.position = min(self._gaps) - 1 if self._gaps else self._high
        return self.position


async def transaction_id_at(when: dt.datetime) -> int:
    """Position just before the first transaction created at or after ``when`` (UTC)."""
    first = await async_db.fetch_val("SELECT min(id) FROM transaction WHERE created >= %(when)s", {"when": when})
    if first is None:
        return await latest_transaction_id()
    return first - 1


async def latest_transaction_id() -> int:
    return await async_db.fetch_val("SELECT coalesce(max(id), 0) FROM transaction")


async def position_status(position: int) -> tuple[dt.datetime | None, int]:
    """When the last transaction at or before ``position`` was created, and how many transactions come after it."""
    row = await async_db.fetch_one(
        """
        SELECT
            (SELECT created FROM transaction WHERE id <= %(id)s ORDER BY id DESC LIMIT 1) AS created,
            (SELECT count(*) FROM transaction WHERE id > %(id)s) AS behind
        """,
        {"id": position},
    )
    assert row is not None
    return row["created"], row["behind"]


class ForceUpdates:
    """Admin "force Solr update" requests, one store document per request.

    ``/admin/solr`` writes ``solr-force-update/<time>-<random>`` documents with
    ``type: solr-force-update``. Infobase indexes every store document's key by
    type in ``store_index``, which is how they are found here. Each document is
    deleted (store row and its index rows, as Infobase does) once its keys are
    indexed, so a request is never lost to a later one overwriting it.
    """

    def __init__(self):
        self._ids: list[int] = []

    async def read(self) -> list[str]:
        rows = await async_db.fetch_all(
            """
            SELECT store.id, store.json
            FROM store_index
            JOIN store ON store.id = store_index.store_id
            WHERE store_index.type = %(type)s AND store_index.name = '_key'
            ORDER BY store.id
            """,
            {"type": FORCE_UPDATE_TYPE},
        )
        self._ids = [row["id"] for row in rows]
        return list(dict.fromkeys(key for row in rows for key in json.loads(row["json"]).get("keys", [])))

    async def acknowledge(self) -> None:
        if not self._ids:
            return
        async with async_db.connection() as conn:
            await conn.execute("DELETE FROM store_index WHERE store_id = ANY(%(ids)s)", {"ids": self._ids})
            await conn.execute("DELETE FROM store WHERE id = ANY(%(ids)s)", {"ids": self._ids})
        self._ids = []
