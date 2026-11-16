"""Tests for the "Readers also read" model and its nightly rebuild.

Unit tests patch the ``async_db`` helpers. Integration tests seed reading logs
in real postgres and check the stored scores against hand-computed values.
"""

import math
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.readers_also_read import ReadersAlsoRead, RebuildConfig, RebuildSummary

WANT_TO_READ = Bookshelves.PRESET_BOOKSHELVES["Want to Read"]
CURRENTLY_READING = Bookshelves.PRESET_BOOKSHELVES["Currently Reading"]
ALREADY_READ = Bookshelves.PRESET_BOOKSHELVES["Already Read"]
STOPPED_READING = Bookshelves.PRESET_BOOKSHELVES["Stopped Reading"]

A, B, C, D, E = 1, 2, 3, 4, 5

EVERY_READER = RebuildConfig(include_private_reading_logs=True, min_weighted_entries=1)


class TestRebuildConfig:
    def test_defaults_follow_the_proposal(self):
        config = RebuildConfig()

        assert config.shelf_weights == {ALREADY_READ: 1.0, CURRENTLY_READING: 0.8, WANT_TO_READ: 0.4}
        assert (config.max_books_per_reader, config.min_co_readers, config.min_weighted_entries, config.related_per_work) == (500, 3, 20.0, 12)

    def test_private_reading_logs_are_left_out_by_default(self):
        assert RebuildConfig().include_private_reading_logs is False

    @pytest.mark.parametrize("min_co_readers", [0, 1, 2])
    def test_rejects_a_co_reader_floor_below_three(self, min_co_readers):
        with pytest.raises(ValueError, match="min_co_readers"):
            RebuildConfig(min_co_readers=min_co_readers)

    @pytest.mark.parametrize("field", ["related_per_work", "batch_size"])
    def test_rejects_non_positive_sizes(self, field):
        with pytest.raises(ValueError, match="must be positive"):
            RebuildConfig(**{field: 0})


@pytest.mark.asyncio
async def test_get_related_work_ids_reads_one_works_rows_in_rank_order():
    with patch("openlibrary.core.readers_also_read.fetch_all", new_callable=AsyncMock) as fetch_all:
        fetch_all.return_value = [{"related_work_id": 7}, {"related_work_id": 3}]

        related = await ReadersAlsoRead.get_related_work_ids(42, limit=5)

    assert related == [7, 3]
    (query, params), _kwargs = fetch_all.await_args
    assert query == "SELECT related_work_id FROM readers_also_read WHERE work_id = %(work_id)s ORDER BY rank LIMIT %(limit)s"
    assert params == {"work_id": 42, "limit": 5}


def _readers(prefix: str, count: int, *works: int, shelf: int = ALREADY_READ) -> list[tuple[str, int, int]]:
    """``count`` readers named ``prefix0``, ``prefix1``... who each logged ``works`` on ``shelf``."""
    return [(f"{prefix}{n}", work, shelf) for n in range(count) for work in works]


async def _shelve(entries: list[tuple[str, int, int]]) -> None:
    async with async_db.connection() as conn, conn.cursor() as cursor:
        await cursor.executemany("INSERT INTO bookshelves_books (username, work_id, bookshelf_id) VALUES (%s, %s, %s)", entries)


async def _rate(username: str, work_id: int, rating: int) -> None:
    await async_db.execute(
        "INSERT INTO ratings (username, work_id, rating) VALUES (%(username)s, %(work_id)s, %(rating)s)",
        {"username": username, "work_id": work_id, "rating": rating},
    )


async def _set_public_readlog(**readers: str) -> None:
    """Store each reader's ``public_readlog`` preference the way infobase's store indexes it."""
    async with async_db.connection() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS store (id serial primary key, key text unique, json text)")
        await conn.execute("CREATE TABLE IF NOT EXISTS store_index (id serial primary key, store_id int references store, type text, name text, value text)")
        for username, public_readlog in readers.items():
            cursor = await conn.execute("INSERT INTO store (key, json) VALUES (%(key)s, '{}') RETURNING id", {"key": f"/people/{username}/preferences"})
            row = await cursor.fetchone()
            assert row is not None
            await conn.execute(
                "INSERT INTO store_index (store_id, type, name, value) VALUES (%(id)s, 'preferences', 'public_readlog', %(value)s)",
                {"id": row["id"], "value": public_readlog},
            )


async def _stored() -> dict[int, list[tuple[int, float]]]:
    rows = await async_db.fetch_all("SELECT work_id, related_work_id, score FROM readers_also_read ORDER BY work_id, rank")
    stored: dict[int, list[tuple[int, float]]] = {}
    for row in rows:
        stored.setdefault(row["work_id"], []).append((row["related_work_id"], pytest.approx(row["score"], rel=1e-6)))
    return stored


@pytest.mark.integration
class TestRebuildIntegration:
    @pytest.mark.asyncio
    async def test_scores_are_jaccard_over_readers_with_a_floor_of_three(self, pg_db):
        await _shelve(_readers("ab", 4, A, B) + _readers("ac", 3, A, C) + _readers("ad", 2, A, D) + _readers("ce", 3, C, E))

        summary = await ReadersAlsoRead.rebuild(RebuildConfig(include_private_reading_logs=True, min_weighted_entries=3))

        assert await _stored() == {
            A: [(B, 4 / 9), (C, 3 / 12)],
            B: [(A, 4 / 9)],
            C: [(E, 3 / 6), (A, 3 / 12)],
            E: [(C, 3 / 6)],
        }
        assert summary == RebuildSummary(eligible_works=4, works_with_related=4, works_with_carousel=0, rows=6)

    @pytest.mark.asyncio
    async def test_shelves_weigh_a_reader_in(self, pg_db):
        await _shelve(
            _readers("want", 3, A) + _readers("want", 3, B, shelf=WANT_TO_READ) + _readers("reading", 3, A) + _readers("reading", 3, C, shelf=CURRENTLY_READING)
        )

        await ReadersAlsoRead.rebuild(EVERY_READER)

        assert (await _stored())[A] == [(C, 2.4 / 6), (B, 1.2 / 6)]

    @pytest.mark.asyncio
    async def test_stopped_reading_does_not_count(self, pg_db):
        await _shelve(_readers("r", 3, A) + _readers("r", 3, B, shelf=STOPPED_READING))

        summary = await ReadersAlsoRead.rebuild(EVERY_READER)

        assert await _stored() == {}
        assert summary.eligible_works == 1

    @pytest.mark.asyncio
    async def test_readers_who_log_more_books_count_for_less(self, pg_db):
        heavy_readers = [(f"heavy{n}", work, ALREADY_READ) for n in range(3) for work in (A, C, *range(100 + 10 * n, 108 + 10 * n))]
        await _shelve(_readers("light", 3, A, B) + heavy_readers)

        await ReadersAlsoRead.rebuild(EVERY_READER)

        light, heavy = 1 / math.log(3), 1 / math.log(11)
        assert (await _stored())[A] == [(B, light / (light + heavy)), (C, heavy / (light + heavy))]

    @pytest.mark.asyncio
    async def test_readers_above_the_book_cap_are_left_out(self, pg_db):
        await _shelve(_readers("r", 2, A, C) + [("power", work, ALREADY_READ) for work in (A, C, D, E)])

        await ReadersAlsoRead.rebuild(EVERY_READER)
        assert (await _stored())[A] == [(C, 3 / 3)]

        await ReadersAlsoRead.rebuild(RebuildConfig(include_private_reading_logs=True, min_weighted_entries=1, max_books_per_reader=3))
        assert await _stored() == {}

    @pytest.mark.asyncio
    async def test_a_low_rating_weakens_the_readers_link(self, pg_db):
        await _shelve(_readers("r", 3, A, B))
        await _rate("r0", B, 1)

        await ReadersAlsoRead.rebuild(EVERY_READER)

        assert (await _stored())[A] == [(B, 2.5 / 3)]

    @pytest.mark.asyncio
    async def test_keeps_the_best_matches_and_breaks_ties_by_work(self, pg_db):
        await _shelve(_readers("r", 3, A, B, C, D))

        await ReadersAlsoRead.rebuild(RebuildConfig(include_private_reading_logs=True, min_weighted_entries=1, related_per_work=2))

        assert (await _stored())[A] == [(B, 1.0), (C, 1.0)]

    @pytest.mark.asyncio
    async def test_only_public_reading_logs_count_by_default(self, pg_db):
        await _shelve(_readers("r", 4, A, B))
        await _set_public_readlog(r0="yes", r1="yes", r2="no")

        await ReadersAlsoRead.rebuild(RebuildConfig(min_weighted_entries=1))
        assert await _stored() == {}

        await _set_public_readlog(r3="yes")
        await ReadersAlsoRead.rebuild(RebuildConfig(min_weighted_entries=1))
        assert await _stored() == {A: [(B, 1.0)], B: [(A, 1.0)]}

    @pytest.mark.asyncio
    async def test_private_reading_logs_count_when_included(self, pg_db):
        await _shelve(_readers("r", 3, A, B))
        await _set_public_readlog(r0="no", r1="no")

        await ReadersAlsoRead.rebuild(EVERY_READER)

        assert await _stored() == {A: [(B, 1.0)], B: [(A, 1.0)]}

    @pytest.mark.asyncio
    async def test_replaces_the_previous_rows(self, pg_db):
        await async_db.execute("INSERT INTO readers_also_read (work_id, related_work_id, score, rank) VALUES (99, 98, 0.5, 1)")
        await _shelve(_readers("r", 3, A, B))

        await ReadersAlsoRead.rebuild(EVERY_READER)

        assert await _stored() == {A: [(B, 1.0)], B: [(A, 1.0)]}

    @pytest.mark.asyncio
    async def test_dry_run_reports_without_writing(self, pg_db):
        await async_db.execute("INSERT INTO readers_also_read (work_id, related_work_id, score, rank) VALUES (99, 98, 0.5, 1)")
        await _shelve(_readers("r", 3, A, B, C, D, E, 6, 7))

        summary = await ReadersAlsoRead.rebuild(EVERY_READER, dry_run=True)

        assert summary == RebuildSummary(eligible_works=7, works_with_related=7, works_with_carousel=7, rows=42)
        assert await _stored() == {99: [(98, 0.5)]}

    @pytest.mark.asyncio
    async def test_skips_while_another_rebuild_is_running(self, pg_db):
        await async_db.execute("INSERT INTO readers_also_read (work_id, related_work_id, score, rank) VALUES (99, 98, 0.5, 1)")
        await _shelve(_readers("r", 3, A, B))

        async with async_db.connection() as running:
            await running.execute("SELECT pg_advisory_xact_lock(hashtext('readers_also_read'))")
            assert await ReadersAlsoRead.rebuild(EVERY_READER) is None

        assert await _stored() == {99: [(98, 0.5)]}
        assert await ReadersAlsoRead.rebuild(EVERY_READER) is not None

    @pytest.mark.asyncio
    async def test_scores_every_eligible_work_across_batches(self, pg_db):
        await _shelve(_readers("ab", 3, A, B) + _readers("cd", 3, C, D))

        summary = await ReadersAlsoRead.rebuild(RebuildConfig(include_private_reading_logs=True, min_weighted_entries=1, batch_size=1))

        assert summary == RebuildSummary(eligible_works=4, works_with_related=4, works_with_carousel=0, rows=4)

    @pytest.mark.asyncio
    async def test_get_related_work_ids_returns_the_stored_ranking(self, pg_db):
        await _shelve(_readers("abc", 4, A, B, C) + _readers("ab", 2, A, B))

        await ReadersAlsoRead.rebuild(EVERY_READER)

        assert await ReadersAlsoRead.get_related_work_ids(A) == [B, C]
        assert await ReadersAlsoRead.get_related_work_ids(A, limit=1) == [B]
        assert await ReadersAlsoRead.get_related_work_ids(E) == []
