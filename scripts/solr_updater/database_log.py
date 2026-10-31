"""Read Solr update events from Infobase's PostgreSQL database.

The queue is populated by database triggers in the same transaction as the
Infobase write. Reading unacknowledged queue rows avoids relying on the order in
which transaction sequence IDs become visible to other connections.
"""

import json
from collections.abc import Iterator

from openlibrary.core import async_db


def find_document_keys(document: dict | list) -> Iterator[str]:
    """Yield referenced keys from a saved Infobase document."""
    if isinstance(document, dict):
        if key := document.get("key"):
            yield key
        for value in document.values():
            yield from find_document_keys(value)
    elif isinstance(document, list):
        for value in document:
            yield from find_document_keys(value)


class DatabaseLog:
    """Single-consumer database queue of keys to refresh in Solr.

    Acknowledging a batch removes it for every consumer, so independent Solr
    cores must continue using their own source until the queue supports fan-out.
    """

    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self._queue_ids: list[int] = []

    @property
    def has_pending_batch(self) -> bool:
        """Whether the last read returned queue rows, even if they had no keys."""
        return bool(self._queue_ids)

    async def read_keys(self) -> list[str]:
        """Read one batch of pending writes and return all affected keys."""
        rows = await async_db.fetch_all(
            """
            WITH pending AS (
                SELECT id, transaction_id, keys
                FROM solr_updater_queue
                ORDER BY id
                LIMIT %(limit)s
            )
            SELECT
                pending.id AS queue_id,
                pending.transaction_id,
                pending.keys AS force_keys,
                changed.key AS changed_key,
                current_data.data AS current_data,
                previous_data.data AS previous_data
            FROM pending
            LEFT JOIN transaction AS tx ON tx.id = pending.transaction_id
            LEFT JOIN LATERAL jsonb_to_recordset(tx.changes::jsonb)
                AS changed(key text, revision integer) ON true
            LEFT JOIN thing ON thing.key = changed.key
            LEFT JOIN data AS current_data
                ON current_data.thing_id = thing.id
                AND current_data.revision = changed.revision
            LEFT JOIN data AS previous_data
                ON previous_data.thing_id = thing.id
                AND previous_data.revision = changed.revision - 1
            ORDER BY pending.id
            """,
            {"limit": self.batch_size},
        )
        self._queue_ids = list(dict.fromkeys(row["queue_id"] for row in rows))
        keys = [key for row in rows if row["transaction_id"] is None for key in (row["force_keys"] or [])]

        for row in rows:
            if row["changed_key"] is None:
                continue
            if row["current_data"] is None:
                # Leave the row unacknowledged so an operator can inspect and repair it.
                raise RuntimeError(f"No saved data found for Solr queue row {row['queue_id']} (transaction {row['transaction_id']}, key {row['changed_key']})")
            keys.append(row["changed_key"])
            current_doc = json.loads(row["current_data"])
            previous_doc = json.loads(row["previous_data"]) if row["previous_data"] else None
            if previous_doc:
                keys.extend(set(find_document_keys(previous_doc)) - set(find_document_keys(current_doc)))

        # Keep the old log parser's behavior of deduplicating references per batch.
        # update_keys filters keys that are not understood by a Solr updater.
        return list(dict.fromkeys(keys))

    async def acknowledge(self) -> None:
        """Delete the batch after ``update_keys`` returns successfully."""
        if not self._queue_ids:
            return
        await async_db.execute(
            "DELETE FROM solr_updater_queue WHERE id = ANY(%(ids)s)",
            {"ids": self._queue_ids},
        )
        self._queue_ids = []
