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
