"""Tests for the /stats/readinglog view (openlibrary.views.loanstats).

Covers the batch-fetch of works missed by Solr (internetarchive/openlibrary#12432),
which replaced per-work web.ctx.site.get() calls with a single get_many() lookup.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import web

from openlibrary.core.bookshelves import Bookshelves
from openlibrary.views import loanstats

FAKE_LEADERBOARD = {
    "reading_log": {},
    "leaderboard": {
        "most_read": [{"work_id": 1, "cnt": 100}],
        "most_wanted_all": [{"work_id": 2, "cnt": 50}, {"work_id": 3, "cnt": 30}],
        "most_wanted_month": [{"work_id": 4, "cnt": 20}],
        "most_rated_all": [{"work_id": 5, "cnt": 10}],
    },
}

ALL_WORK_IDS = tuple(w["work_id"] for board in FAKE_LEADERBOARD["leaderboard"].values() for w in board)
ALL_WORK_KEYS = [f"/works/OL{i}W" for i in ALL_WORK_IDS]


def seed_works(mock_site, work_ids):
    """Save simple /works/OL<N>W docs into the mock site."""
    for work_id in work_ids:
        mock_site.quicksave(f"/works/OL{work_id}W", type="/type/work", title=f"Work {work_id}")


class TestReadinglogStats:
    def _call_view(self, mock_site, monkeypatch, solr_docs, seed=(), expect_typeerror=False):
        """Seed works, stub out solr/stats/availability/templates and call GET().

        Returns (get_many_calls, leaderboard_items) so tests can assert on the
        batching behavior and on the works attached to each leaderboard item.
        """
        seed_works(mock_site, seed)

        def fake_stats(limit):
            return FAKE_LEADERBOARD

        def no_availabilities(works):
            return {}

        monkeypatch.setattr(loanstats, "get_cached_reading_log_stats", fake_stats)
        monkeypatch.setattr(loanstats, "get_solr_works", solr_docs)
        monkeypatch.setattr(loanstats, "get_availabilities", no_availabilities)
        monkeypatch.setattr(loanstats.app, "render_template", lambda *a, **kw: web.storage())

        original_get_many = mock_site.get_many
        get_many_calls = []

        def counting_get_many(keys):
            get_many_calls.append(list(keys))
            return original_get_many(keys)

        monkeypatch.setattr(mock_site, "get_many", counting_get_many)

        # Let web.input() see defaults as a real GET request would.
        web.ctx.env = web.ctx.environ = web.storage(REQUEST_METHOD="GET", QUERY_STRING="limit=10&mode=all")

        try:
            loanstats.readinglog_stats().GET()
        except TypeError:
            # A work missing from both Solr and the DB resolves to None in
            # item["work"], and the (pre-existing) availability-injection loop
            # crashes on it. That behavior is unchanged by this refactor.
            if not expect_typeerror:
                raise

        all_items = [item for board in FAKE_LEADERBOARD["leaderboard"].values() for item in board]
        return get_many_calls, all_items

    def _assert_batched(self, get_many_calls, expected_keys):
        assert len(get_many_calls) <= 1
        if expected_keys:
            assert len(get_many_calls) == 1
            assert {key for keys in get_many_calls for key in keys} == set(expected_keys)
        else:
            assert get_many_calls == []

    def test_all_solr_hits_does_not_call_get_many(self, mock_site, monkeypatch):
        # Solr returns every work, so there is nothing to batch-fetch from the DB.
        solr_docs = {key: {"key": key} for key in ALL_WORK_KEYS}

        get_many_calls, all_items = self._call_view(mock_site, monkeypatch, lambda keys: solr_docs)

        self._assert_batched(get_many_calls, [])

        for item in all_items:
            assert item["work"]["key"] == f"/works/OL{item['work_id']}W"

    def test_mixed_solr_hit_and_miss_batches_missing_keys(self, mock_site, monkeypatch):
        # Solr returns half the works; the other half must be batch-fetched from the DB.
        hit_ids = (1, 2)
        miss_ids = (3, 4, 5)
        solr_docs = {f"/works/OL{i}W": {"key": f"/works/OL{i}W", "title": f"Solr {i}"} for i in hit_ids}

        get_many_calls, all_items = self._call_view(mock_site, monkeypatch, lambda keys: solr_docs, seed=ALL_WORK_IDS)

        self._assert_batched(get_many_calls, [f"/works/OL{i}W" for i in miss_ids])

        for item in all_items:
            assert item["work"]["key"] == f"/works/OL{item['work_id']}W"

    def test_missing_work_yields_none_keeps_found_ones(self, mock_site, monkeypatch):
        # No Solr hits at all; every leaderboard work is fetched from the DB,
        # but works 3 and 5 don't exist there either. They resolve to None
        # (matching the old per-key site.get() behavior), which crashes the
        # pre-existing availability-injection loop -- so expect a TypeError.
        get_many_calls, all_items = self._call_view(mock_site, monkeypatch, lambda keys: {}, seed=(1, 2, 4), expect_typeerror=True)

        self._assert_batched(get_many_calls, ALL_WORK_KEYS)

        works_by_id = {item["work_id"]: item["work"] for item in all_items}
        assert works_by_id[1]["key"] == "/works/OL1W"
        assert works_by_id[2]["key"] == "/works/OL2W"
        assert works_by_id[3] is None
        assert works_by_id[4]["key"] == "/works/OL4W"
        assert works_by_id[5] is None


class TestTrendingNowCaching:
    def test_cached_get_trending_now_hits_cache(self, monkeypatch):
        now = datetime.datetime.now()
        fake_books = [
            web.storage(work_id=101, bookshelf_id=1, created=now, updated=now),
            web.storage(work_id=102, bookshelf_id=2, created=now, updated=now),
        ]
        mock_get_recent = MagicMock(return_value=fake_books)
        monkeypatch.setattr(Bookshelves, "get_recently_logged_books", mock_get_recent)

        # First call hits the mock DB
        res1 = loanstats.cached_get_trending_now(limit=99, page=99)
        assert len(res1) == 2
        assert res1[0]["work_id"] == 101
        assert isinstance(res1[0]["created"], datetime.datetime)
        assert mock_get_recent.call_count == 1

        # Second call with the same parameters must be served from cache
        res2 = loanstats.cached_get_trending_now(limit=99, page=99)
        assert len(res2) == 2
        assert res2[0]["work_id"] == 101
        assert isinstance(res2[0]["created"], datetime.datetime)
        assert mock_get_recent.call_count == 1

        # In-place mutations on returned items must not poison the cache
        res1[0]["work"] = {"title": "Mutated Work"}
        res3 = loanstats.cached_get_trending_now(limit=99, page=99)
        assert "work" not in res3[0]

    @pytest.mark.asyncio
    async def test_get_trending_books_now_calls_cached_helper(self, monkeypatch):
        fake_result = [web.storage(work_id=201, work={"key": "/works/OL201W"})]
        mock_cached = MagicMock(return_value=fake_result)
        monkeypatch.setattr(loanstats, "cached_get_trending_now", mock_cached)
        monkeypatch.setattr(Bookshelves, "add_solr_works_async", AsyncMock())

        res = await loanstats.get_trending_books(since_days=0, since_hours=0, limit=20, page=1)
        mock_cached.assert_called_once_with(limit=20, page=1)
        assert res == [{"key": "/works/OL201W"}]

    def test_activity_stream_now_calls_cached_helper(self, monkeypatch):
        web.ctx.env = web.ctx.environ = web.storage(REQUEST_METHOD="GET", QUERY_STRING="page=1")
        mock_cached = MagicMock(return_value=[])
        monkeypatch.setattr(loanstats, "cached_get_trending_now", mock_cached)
        monkeypatch.setattr(Bookshelves, "add_solr_works", MagicMock())
        monkeypatch.setattr(loanstats.app, "render_template", lambda *a, **kw: web.storage())

        loanstats.activity_stream().GET(mode="/now")
        mock_cached.assert_called_once_with(limit=loanstats.TRENDING_NOW_LIMIT, page=1)
