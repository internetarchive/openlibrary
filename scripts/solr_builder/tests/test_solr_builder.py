import re

import pytest

from scripts.solr_builder.solr_builder.solr_builder import (
    LocalPostgresDataProvider,
    build_job_query,
)


@pytest.fixture
def provider(tmp_path, monkeypatch):
    conf = tmp_path / "db.ini"
    conf.write_text("[postgres]\nhost=localhost\n")
    provider = LocalPostgresDataProvider(str(conf))
    rows = {"/authors/OL1A": {"key": "/authors/OL1A", "type": {"key": "/type/author"}}}
    monkeypatch.setattr(
        provider,
        "query_iter",
        lambda q: iter([(doc,) for key, doc in rows.items() if f"'{key}'" in q]),
    )
    return provider


class TestLocalPostgresDataProvider:
    @pytest.mark.asyncio
    async def test_get_document(self, provider):
        assert await provider.get_document("/authors/OL1A") == {
            "key": "/authors/OL1A",
            "type": {"key": "/type/author"},
        }

    @pytest.mark.asyncio
    async def test_get_document_missing(self, provider):
        assert await provider.get_document("/authors/OL2A") == {
            "key": "/authors/OL2A",
            "type": {"key": "/type/delete"},
        }


@pytest.mark.parametrize(
    ("job", "thing_type"),
    [
        ("works", "/type/work"),
        ("orphans", "/type/edition"),
        ("authors", "/type/author"),
        ("lists", "/type/list"),
        ("series", "/type/series"),
    ],
)
def test_build_job_query_selects_job_type(job, thing_type):
    assert f"""WHERE "Type" = '{thing_type}'""" in build_job_query(job)


def test_build_job_query_chunking():
    q = build_job_query("series", start_at="/series/OL5L", limit=100)
    assert """AND "Key" >= '/series/OL5L'""" in q
    assert "LIMIT 100" in q


class TestCacheSeries:
    @pytest.fixture
    def provider(self, tmp_path, monkeypatch):
        conf = tmp_path / "postgres.ini"
        conf.write_text("[postgres]\nhost=db\n")
        provider = LocalPostgresDataProvider(str(conf))
        queries: list[str] = []

        def fake_query_all(query, json_cache=None):
            queries.append(query)
            rows = [(key, {"key": key, "type": {"key": "/type/series"}}) for key in re.findall(r"'(/series/[^']+)'", query)]
            if json_cache is not None:
                json_cache.update(rows)
            return rows

        monkeypatch.setattr(provider, "query_all", fake_query_all)
        provider.queries = queries
        return provider

    def test_one_query_for_all_referenced_series(self, provider):
        work = {
            "key": "/works/OL1W",
            "series": [{"series": {"key": "/series/OL1L"}, "position": "1"}],
        }
        editions = [
            {"key": "/books/OL1M", "series": ["Legacy series string"]},
            {"key": "/books/OL2M", "series": [{"series": {"key": "/series/OL2L"}}]},
            {"key": "/books/OL3M", "series": [{"series": {"key": "/series/OL1L"}}]},
            {"key": "/books/OL4M"},
        ]
        provider.cache_series([work, *editions])

        assert len(provider.queries) == 1
        assert set(provider.cache) == {"/series/OL1L", "/series/OL2L"}

    def test_skips_query_when_nothing_to_fetch(self, provider):
        provider.cache["/series/OL1L"] = {"key": "/series/OL1L"}
        provider.cache_series(
            [
                {"key": "/works/OL1W", "series": [{"series": {"key": "/series/OL1L"}}]},
                {"key": "/books/OL1M", "series": ["Legacy series string"]},
            ]
        )
        assert provider.queries == []

    @pytest.mark.asyncio
    async def test_get_document_served_from_cache(self, provider):
        provider.cache_series([{"key": "/works/OL1W", "series": [{"series": {"key": "/series/OL1L"}}]}])
        assert (await provider.get_document("/series/OL1L"))["key"] == "/series/OL1L"
        assert len(provider.queries) == 1
