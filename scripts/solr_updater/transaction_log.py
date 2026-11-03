"""Read Solr updates straight from Infobase's ``transaction`` table.

Every Infobase save inserts one ``transaction`` row with the changed keys and
their new revisions, and writes the saved documents to ``data`` in the same
database transaction. Reading those rows gives the Solr updater the same keys
the Infobase write log does, with no extra table or trigger.

Transaction ids come from a sequence, so they are handed out before commit and
can become visible out of order. The reader remembers ids below the highest one
it has seen that aren't visible yet ("gaps") and re-reads them until they show
up, or until every transaction that was running when the gap was first seen has
finished; then it was rolled back and is dropped. This relies on the sequence
having no cache (``serial``'s default) and on Infobase writing ``thing`` before
``transaction``, so the writer already has a transaction id when it takes one.
"""

import datetime as dt
import json
from collections.abc import Iterator

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


class TransactionLog:
    """Cursor over the ``transaction`` table.

    ``position`` is the checkpoint to save: every transaction at or below it has
    been read or will never commit. Restarting from it may reread a few above it.
    """

    def __init__(self, position: int, batch_size: int = 100):
        self.batch_size = batch_size
        self.high = position
        # gap id -> txid_snapshot_xmax() when the gap was first seen
        self.gaps: dict[int, int] = {}
        self.last_created: dt.datetime | None = None

    @property
    def position(self) -> int:
        return min(self.gaps) - 1 if self.gaps else self.high

    async def read(self) -> tuple[list[str], int]:
        """The keys to reindex for the next batch of transactions, and how many transactions it had."""
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
            {"high": self.high, "gaps": list(self.gaps), "limit": self.batch_size},
        )
        xmin, xmax = rows[0]["xmin"], rows[0]["xmax"]
        seen = sorted({row["id"] for row in rows if row["id"] is not None})

        for tx_id in seen:
            self.gaps.pop(tx_id, None)
            if tx_id > self.high:
                self.gaps.update(dict.fromkeys(range(self.high + 1, tx_id), xmax))
                self.high = tx_id
        # Every transaction that could have held these ids has finished: rolled back.
        self.gaps = {gap: seen_at for gap, seen_at in self.gaps.items() if xmin < seen_at}

        keys = []
        for row in rows:
            if row["changed_key"] is None:
                continue
            self.last_created = row["created"]
            keys.append(row["changed_key"])
            if row["previous_data"] and row["current_data"]:
                # Keys the old revision referenced but the new one doesn't, e.g. the
                # work an edition moved away from.
                before = set(find_keys(json.loads(row["previous_data"])))
                keys.extend(before - set(find_keys(json.loads(row["current_data"]))))
        return list(dict.fromkeys(keys)), len(seen)


async def transaction_id_at(when: dt.datetime) -> int:
    """Position just before the first transaction created at or after ``when`` (UTC)."""
    first = await async_db.fetch_val("SELECT min(id) FROM transaction WHERE created >= %(when)s", {"when": when})
    if first is None:
        return await async_db.fetch_val("SELECT coalesce(max(id), 0) FROM transaction")
    return first - 1


async def transaction_created(position: int) -> dt.datetime | None:
    return await async_db.fetch_val("SELECT created FROM transaction WHERE id <= %(id)s ORDER BY id DESC LIMIT 1", {"id": position})


class ForceUpdates:
    """Admin "force Solr update" requests, read from the ``solr-force-update`` store document.

    ``/admin/solr`` overwrites that one document but keeps recent requests in its
    ``requests`` list, each with an increasing ``seq``. Remembering the last ``seq``
    means a request a later one overwrote isn't missed, and nothing is written, so
    any number of updaters can follow the same document. (If the document is ever
    deleted, ``seq`` restarts at 1; reset the saved ``force_update`` to 0.)
    """

    def __init__(self, last_seq: int):
        self.last_seq = last_seq

    async def read(self) -> list[str]:
        new = [r for r in await force_update_requests() if r["seq"] > self.last_seq]
        self.last_seq = max((r["seq"] for r in new), default=self.last_seq)
        return list(dict.fromkeys(key for r in new for key in r["keys"]))


async def force_update_requests() -> list[dict]:
    doc = await async_db.fetch_val("SELECT json FROM store WHERE key = %(key)s", {"key": FORCE_UPDATE_KEY})
    return json.loads(doc).get("requests", []) if doc else []


async def force_update_seq_at(when: dt.datetime) -> int:
    """The last admin force-update request made before ``when`` (UTC)."""
    return max((r["seq"] for r in await force_update_requests() if dt.datetime.fromisoformat(r["time"]) < when), default=0)
