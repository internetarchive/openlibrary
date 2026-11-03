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

FORCE_UPDATE_KEY = "solr-force-update"


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
    keys_by_transaction: dict[int, list[str]]
    last_created: dt.datetime | None

    @property
    def keys(self) -> list[str]:
        return list(dict.fromkeys(key for keys in self.keys_by_transaction.values() for key in keys))

    @property
    def transaction_count(self) -> int:
        return len(self.keys_by_transaction)


@dataclass
class TransactionLog:
    """Cursor over the ``transaction`` table.

    ``position`` is the persisted checkpoint: every transaction with an id at or
    below it has been processed or will never commit. Restarting from it can
    reprocess a few transactions above it, which is harmless.
    """

    position: int
    batch_size: int = 100
    # Stop after this transaction id (for read-only comparisons); None reads forever.
    until: int | None = None
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
                WHERE (id > %(high)s OR id = ANY(%(gaps)s)) AND id <= %(until)s
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
            {"high": self._high, "gaps": list(self._gaps), "limit": self.batch_size, "until": self.until if self.until is not None else 2**31 - 1},
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

        keys_by_transaction: dict[int, list[str]] = {}
        last_created = None
        for row in rows:
            if row["id"] is None:
                continue
            keys = keys_by_transaction.setdefault(row["id"], [])
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
        return TransactionLogBatch({tx_id: list(dict.fromkeys(keys)) for tx_id, keys in keys_by_transaction.items()}, last_created)

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
    """Admin "force Solr update" requests, read from the ``solr-force-update`` store document.

    ``/admin/solr`` overwrites that one document, but also keeps the most recent
    requests in its ``requests`` list, each with an increasing ``seq``. This reader
    remembers the last ``seq`` it indexed, so it never misses a request that a later
    one overwrote, and it changes nothing: any number of updaters (or a read-only
    check) can follow the same document.
    """

    def __init__(self, last_seq: int):
        self.last_seq = last_seq
        self._next_seq = last_seq

    async def read(self) -> list[str]:
        requests = await force_update_requests()
        new = [r for r in requests if r["seq"] > self.last_seq]
        if new and new[0]["seq"] > self.last_seq + 1 and self.last_seq:
            logger.error("Missed admin force-update requests %d-%d; only the last %d are kept", self.last_seq + 1, new[0]["seq"] - 1, len(requests))
        self._next_seq = max((r["seq"] for r in new), default=self.last_seq)
        return list(dict.fromkeys(key for r in new for key in r["keys"]))

    def commit(self) -> int:
        self.last_seq = self._next_seq
        return self.last_seq


async def force_update_requests() -> list[dict]:
    doc = await async_db.fetch_val("SELECT json FROM store WHERE key = %(key)s", {"key": FORCE_UPDATE_KEY})
    return json.loads(doc).get("requests", []) if doc else []


async def force_update_seq_at(when: dt.datetime) -> int:
    """The last admin force-update request made before ``when`` (UTC)."""
    return max((r["seq"] for r in await force_update_requests() if dt.datetime.fromisoformat(r["time"]) < when), default=0)
