"""Read Solr updates straight from Infobase's ``transaction`` table.

Every Infobase save inserts one ``transaction`` row with the changed keys and
their new revisions, and writes the saved documents to ``data`` in the same
database transaction. Reading those rows gives the Solr updater the same keys
the Infobase write log does, with no extra table or trigger.

Transaction ids come from a sequence, so they are handed out before commit and
can become visible out of order. The reader remembers ids below the highest one
it has read that aren't visible yet ("missing ids") and re-reads them until they
show up, or until every transaction that was running when the id was first missed
has finished; then it was rolled back and is dropped. This relies on the sequence
having no cache (``serial``'s default) and on Infobase writing ``thing`` before
``transaction``, so the writer already has a transaction id when it takes one.
"""

import datetime as dt
import json
from collections.abc import Iterator

from pydantic import BaseModel

from openlibrary.core import async_db

FORCE_UPDATE_KEY = "solr-force-update"


def find_keys(d: dict | list) -> Iterator[str]:
    """
    Find any keys in the given dict or list.

    >>> list(find_keys({'key': 'foo'}))
    ['foo']
    >>> list(find_keys([{}, {'key': 'bar'}]))
    ['bar']
    >>> list(find_keys([{'key': 'blue'}, {'key': 'bar'}]))
    ['blue', 'bar']
    >>> list(find_keys({'title': 'foo'}))
    []
    >>> list(find_keys({ 'works': [ {'key': 'foo'} ] }))
    ['foo']
    >>> list(find_keys({ 'authors': [ { 'author': {'key': 'foo'} } ] }))
    ['foo']
    """
    if isinstance(d, dict):
        if "key" in d:
            yield d["key"]
        for val in d.values():
            yield from find_keys(val)
    elif isinstance(d, list):
        for val in d:
            yield from find_keys(val)


class TransactionsOffset(BaseModel):
    """How far the transactions source has indexed, saved after every batch."""

    transaction: int
    """Infobase ``transaction.id``. Every transaction at or below it is indexed (or was rolled back)."""
    force_update: int
    """``seq`` of the last ``/admin/solr`` force-update request indexed."""


class TransactionLog:
    """Reads the ``transaction`` table in batches, in id order, without skipping late commits.

    ``offset`` is what to save: every transaction at or below it has been read or
    will never commit. Restarting from it may re-read a few transactions above it,
    which only reindexes those keys again.
    """

    def __init__(self, offset: int, batch_size: int = 100):
        self.batch_size = batch_size
        # The highest transaction id read so far; the next batch starts after it.
        self.highest_seen_id = offset
        # Ids below highest_seen_id that weren't visible yet, mapped to the snapshot
        # xmax when each was first missed: the id is dropped as rolled back once every
        # transaction that was running then has finished.
        self.missing_ids: dict[int, int] = {}
        # When the newest transaction read was created, to log how far behind we are.
        self.last_created_at: dt.datetime | None = None

    @property
    def offset(self) -> int:
        return min(self.missing_ids) - 1 if self.missing_ids else self.highest_seen_id

    async def read(self) -> tuple[list[str], int]:
        """Read the next batch: the keys to reindex, and how many transactions were read."""
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
                WHERE id > %(highest_seen_id)s OR id = ANY(%(missing_ids)s)
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
            {"highest_seen_id": self.highest_seen_id, "missing_ids": list(self.missing_ids), "limit": self.batch_size},
        )
        xmin, xmax = rows[0]["xmin"], rows[0]["xmax"]
        read_ids = sorted({row["id"] for row in rows if row["id"] is not None})

        for tx_id in read_ids:
            self.missing_ids.pop(tx_id, None)
            if tx_id > self.highest_seen_id:
                # Ids skipped over aren't visible yet: still running, or rolled back.
                self.missing_ids.update(dict.fromkeys(range(self.highest_seen_id + 1, tx_id), xmax))
                self.highest_seen_id = tx_id
        # Every transaction that could have held these ids has finished, so they were rolled back.
        self.missing_ids = {tx_id: xmax_when_missed for tx_id, xmax_when_missed in self.missing_ids.items() if xmin < xmax_when_missed}

        keys = []
        for row in rows:
            if row["changed_key"] is None:
                continue
            self.last_created_at = row["created"]
            keys.append(row["changed_key"])
            if row["previous_data"] and row["current_data"]:
                # Keys the old revision referenced but the new one doesn't, e.g. the
                # work an edition moved away from.
                before = set(find_keys(json.loads(row["previous_data"])))
                keys.extend(before - set(find_keys(json.loads(row["current_data"]))))
        return list(dict.fromkeys(keys)), len(read_ids)


async def find_transaction_id_at(when: dt.datetime) -> int:
    """Find the offset to start from to read every transaction created at or after ``when`` (UTC)."""
    first = await async_db.fetch_val("SELECT min(id) FROM transaction WHERE created >= %(when)s", {"when": when})
    if first is None:
        return await async_db.fetch_val("SELECT coalesce(max(id), 0) FROM transaction")
    return first - 1


async def get_transaction_created_at(offset: int) -> dt.datetime | None:
    """Get when the transaction at ``offset`` (or the last one before it) was created."""
    return await async_db.fetch_val("SELECT created FROM transaction WHERE id <= %(id)s ORDER BY id DESC LIMIT 1", {"id": offset})


class ForceUpdates:
    """Admin "force Solr update" requests, read from the ``solr-force-update`` store document.

    ``/admin/solr`` overwrites that one document but keeps recent requests in its
    ``requests`` list, each with an increasing ``seq``. Remembering the last ``seq``
    means a request a later one overwrote isn't missed, and nothing is written, so
    any number of updaters can follow the same document. (If the document is ever
    deleted, ``seq`` restarts at 1; reset ``force_update`` in the saved offset to 0.)
    """

    def __init__(self, last_seq: int):
        self.last_seq = last_seq

    async def read(self) -> list[str]:
        """Read the keys of requests made since the last read."""
        new = [r for r in await fetch_force_update_requests() if r["seq"] > self.last_seq]
        self.last_seq = max((r["seq"] for r in new), default=self.last_seq)
        return list(dict.fromkeys(key for r in new for key in r["keys"]))


async def fetch_force_update_requests() -> list[dict]:
    """Fetch the recent requests kept in the ``solr-force-update`` store document."""
    doc = await async_db.fetch_val("SELECT json FROM store WHERE key = %(key)s", {"key": FORCE_UPDATE_KEY})
    return json.loads(doc).get("requests", []) if doc else []


async def find_force_update_seq_at(when: dt.datetime) -> int:
    """Find the ``seq`` of the last force-update request made before ``when`` (UTC)."""
    return max((r["seq"] for r in await fetch_force_update_requests() if dt.datetime.fromisoformat(r["time"]) < when), default=0)
