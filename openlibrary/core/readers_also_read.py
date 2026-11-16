"""Readers also read: the works most often logged by the readers of a work.

A nightly rebuild scores how strongly works share readers in the reading log
and keeps each work's best matches in the ``readers_also_read`` table, so the
book page needs one indexed lookup. Proposed in internetarchive/openlibrary#13825.

Scoring is weighted Jaccard over readers. The shelf sets a reader's weight for
a work, a low rating cuts it, and readers who log many books count for less:

    overlap(a, b) = sum over shared readers of damping * min(weight_a, weight_b)
    mass(a)       = sum over all readers of damping * weight_a
    score(a, b)   = overlap / (mass(a) + mass(b) - overlap)

where a reader's damping is 1 / ln(1 + the number of works they logged).
"""

import logging
from dataclasses import dataclass
from itertools import batched
from typing import ClassVar

from openlibrary.core.async_db import connection, fetch_all
from openlibrary.core.bookshelves import Bookshelves

logger = logging.getLogger("openlibrary.readers_also_read")

RELATED_PER_WORK = 12
MIN_CO_READERS = 3
MIN_RELATED_TO_SHOW = 6


@dataclass(frozen=True, slots=True)
class RebuildConfig:
    """Tuning for a rebuild. The defaults are the ones proposed in #13825."""

    already_read_weight: float = 1.0
    currently_reading_weight: float = 0.8
    want_to_read_weight: float = 0.4
    low_rating: int = 2
    low_rating_weight: float = 0.5
    max_books_per_reader: int = 500
    min_co_readers: int = MIN_CO_READERS
    min_weighted_entries: float = 20.0
    related_per_work: int = RELATED_PER_WORK
    include_private_reading_logs: bool = False
    batch_size: int = 500

    def __post_init__(self) -> None:
        if self.min_co_readers < MIN_CO_READERS:
            raise ValueError(f"min_co_readers must be at least {MIN_CO_READERS}, so no pair rests on one or two readers")
        if self.related_per_work < 1 or self.batch_size < 1:
            raise ValueError("related_per_work and batch_size must be positive")

    @property
    def shelf_weights(self) -> dict[int, float]:
        shelves = Bookshelves.PRESET_BOOKSHELVES
        return {
            shelves["Already Read"]: self.already_read_weight,
            shelves["Currently Reading"]: self.currently_reading_weight,
            shelves["Want to Read"]: self.want_to_read_weight,
        }


@dataclass(frozen=True, slots=True)
class RebuildSummary:
    """What a rebuild stored, including the coverage numbers #13825 asks for."""

    eligible_works: int
    works_with_related: int
    works_with_carousel: int
    rows: int


class ReadersAlsoRead:
    TABLENAME = "readers_also_read"

    _PUBLIC_READERS_ONLY: ClassVar[str] = (
        "WHERE bookshelves_books.username IN ("
        " SELECT substring(store.key FROM '^/people/(.+)/preferences$')"
        " FROM store JOIN store_index ON store_index.store_id = store.id"
        " WHERE store_index.type = 'preferences' AND store_index.name = 'public_readlog' AND store_index.value = 'yes')"
    )

    _ENTRIES: ClassVar[str] = (
        "CREATE TEMP TABLE co_read_entries ON COMMIT DROP AS"
        " WITH shelved AS ("
        " SELECT bookshelves_books.username, bookshelves_books.work_id, max(shelf.weight) AS weight"
        " FROM bookshelves_books"
        " JOIN unnest(%(shelf_ids)s::int[], %(shelf_weights)s::float8[]) AS shelf (bookshelf_id, weight)"
        " ON shelf.bookshelf_id = bookshelves_books.bookshelf_id AND shelf.weight > 0"
        " {readers_filter}"
        " GROUP BY bookshelves_books.username, bookshelves_books.work_id),"
        " readers AS ("
        " SELECT username, 1 / ln(1 + count(*)::float8) AS damping FROM shelved"
        " GROUP BY username HAVING count(*) <= %(max_books_per_reader)s)"
        " SELECT shelved.username, shelved.work_id, readers.damping,"
        " shelved.weight * CASE WHEN ratings.rating <= %(low_rating)s THEN %(low_rating_weight)s ELSE 1 END AS weight"
        " FROM shelved JOIN readers ON readers.username = shelved.username"
        " LEFT JOIN ratings ON ratings.username = shelved.username AND ratings.work_id = shelved.work_id"
    )

    _PREPARE: ClassVar[tuple[str, ...]] = (
        "CREATE INDEX ON co_read_entries (work_id)",
        "CREATE INDEX ON co_read_entries (username)",
        "ANALYZE co_read_entries",
        (
            "CREATE TEMP TABLE co_read_works ON COMMIT DROP AS"
            " SELECT work_id, sum(weight) AS weighted_entries, sum(damping * weight) AS mass FROM co_read_entries GROUP BY work_id"
        ),
        "ALTER TABLE co_read_works ADD PRIMARY KEY (work_id)",
        "ANALYZE co_read_works",
    )

    _ELIGIBLE_WORKS: ClassVar[str] = "SELECT work_id FROM co_read_works WHERE weighted_entries >= %(min_weighted_entries)s ORDER BY work_id"

    _SCORE_BATCH: ClassVar[str] = (
        f"INSERT INTO {TABLENAME} (work_id, related_work_id, score, rank)"
        " WITH pairs AS ("
        " SELECT source.work_id, related.work_id AS related_work_id,"
        " sum(source.damping * least(source.weight, related.weight)) AS overlap"
        " FROM co_read_entries source"
        " JOIN co_read_entries related ON related.username = source.username AND related.work_id <> source.work_id"
        " WHERE source.work_id = ANY(%(work_ids)s::int[])"
        " GROUP BY source.work_id, related.work_id"
        " HAVING count(*) >= %(min_co_readers)s),"
        " scored AS ("
        " SELECT pairs.work_id, pairs.related_work_id, pairs.overlap / (source.mass + related.mass - pairs.overlap) AS score"
        " FROM pairs"
        " JOIN co_read_works source ON source.work_id = pairs.work_id"
        " JOIN co_read_works related ON related.work_id = pairs.related_work_id),"
        " ranked AS ("
        " SELECT work_id, related_work_id, score,"
        " row_number() OVER (PARTITION BY work_id ORDER BY score DESC, related_work_id) AS rank"
        " FROM scored)"
        " SELECT work_id, related_work_id, score, rank FROM ranked WHERE rank <= %(related_per_work)s"
    )

    _SUMMARY: ClassVar[str] = (
        "SELECT count(*) AS works_with_related,"
        " count(*) FILTER (WHERE related >= %(min_to_show)s) AS works_with_carousel,"
        " coalesce(sum(related), 0)::bigint AS rows"
        f" FROM (SELECT count(*) AS related FROM {TABLENAME} GROUP BY work_id) AS per_work"
    )

    @classmethod
    async def get_related_work_ids(cls, work_id: int, limit: int = RELATED_PER_WORK) -> list[int]:
        """IDs of the works most read alongside ``work_id``, best match first."""
        query = f"SELECT related_work_id FROM {cls.TABLENAME} WHERE work_id = %(work_id)s ORDER BY rank LIMIT %(limit)s"
        rows = await fetch_all(query, {"work_id": work_id, "limit": limit})
        return [row["related_work_id"] for row in rows]

    @classmethod
    async def rebuild(cls, config: RebuildConfig | None = None, dry_run: bool = False) -> RebuildSummary | None:
        """Recompute every work's related works in one transaction.

        Readers keep seeing the previous rows until the new ones commit. With
        ``dry_run`` the transaction is rolled back once the summary is taken.
        Returns None, leaving the table alone, while another rebuild is running.
        """
        config = config or RebuildConfig()
        shelf_weights = config.shelf_weights
        readers_filter = "" if config.include_private_reading_logs else cls._PUBLIC_READERS_ONLY
        entries_params = {
            "shelf_ids": list(shelf_weights),
            "shelf_weights": list(shelf_weights.values()),
            "max_books_per_reader": config.max_books_per_reader,
            "low_rating": config.low_rating,
            "low_rating_weight": config.low_rating_weight,
        }
        score_params = {"min_co_readers": config.min_co_readers, "related_per_work": config.related_per_work}

        async with connection() as conn:
            cursor = await conn.execute("SELECT pg_try_advisory_xact_lock(hashtext(%(table)s)) AS locked", {"table": cls.TABLENAME})
            lock = await cursor.fetchone()
            if not (lock and lock["locked"]):
                logger.warning("Skipping the rebuild of %s: another rebuild is running", cls.TABLENAME)
                return None

            await conn.execute(cls._ENTRIES.format(readers_filter=readers_filter), entries_params)
            for statement in cls._PREPARE:
                await conn.execute(statement)
            cursor = await conn.execute(cls._ELIGIBLE_WORKS, {"min_weighted_entries": config.min_weighted_entries})
            work_ids = [row["work_id"] for row in await cursor.fetchall()]

            await conn.execute(f"DELETE FROM {cls.TABLENAME}")
            batches = list(batched(work_ids, config.batch_size, strict=False))
            for done, batch in enumerate(batches, start=1):
                await conn.execute(cls._SCORE_BATCH, {**score_params, "work_ids": list(batch)})
                logger.info("Scored batch %d of %d", done, len(batches))

            cursor = await conn.execute(cls._SUMMARY, {"min_to_show": MIN_RELATED_TO_SHOW})
            totals = await cursor.fetchone()
            if dry_run:
                await conn.rollback()

        assert totals is not None
        return RebuildSummary(
            eligible_works=len(work_ids),
            works_with_related=totals["works_with_related"],
            works_with_carousel=totals["works_with_carousel"],
            rows=totals["rows"],
        )
