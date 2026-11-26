import pytest

from scripts.solr_builder.solr_builder.solr_builder import LocalPostgresDataProvider


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
