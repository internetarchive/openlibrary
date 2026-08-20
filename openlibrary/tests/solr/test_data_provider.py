from unittest.mock import MagicMock

import pytest

from infogami.infobase.client import Thing
from openlibrary.solr.data_provider import DatabaseDataProvider, DataProvider


class TestDatabaseDataProvider:
    @pytest.mark.asyncio
    async def test_get_document(self):
        mock_site = MagicMock()
        dp = DatabaseDataProvider(
            site=mock_site,
            db=MagicMock(),
        )
        mock_site.get_many.return_value = [
            Thing(
                mock_site,
                "/works/OL1W",
                {
                    "key": "/works/OL1W",
                    "type": {"key": "/type/work"},
                },
            )
        ]
        assert mock_site.get_many.call_count == 0
        await dp.get_document("/works/OL1W")
        assert mock_site.get_many.call_count == 1
        await dp.get_document("/works/OL1W")
        assert mock_site.get_many.call_count == 1

    @pytest.mark.asyncio
    async def test_clear_cache(self):
        mock_site = MagicMock()
        dp = DatabaseDataProvider(
            site=mock_site,
            db=MagicMock(),
        )
        mock_site.get_many.return_value = [
            Thing(
                mock_site,
                "/works/OL1W",
                {
                    "key": "/works/OL1W",
                    "type": {"key": "/type/work"},
                },
            )
        ]
        assert mock_site.get_many.call_count == 0
        await dp.get_document("/works/OL1W")
        assert mock_site.get_many.call_count == 1
        dp.clear_cache()
        await dp.get_document("/works/OL1W")
        assert mock_site.get_many.call_count == 2


class TestGetMetadataSkipIA:
    def test_skip_ia_metadata_returns_none_without_fetching(self, monkeypatch):
        dp = DataProvider()
        dp.skip_ia_metadata = True

        def _fail(*args, **kwargs):
            raise AssertionError("get_metadata_direct should not be called when skipping IA metadata")

        monkeypatch.setattr("openlibrary.solr.data_provider.ia.get_metadata_direct", _fail)
        assert dp.get_metadata("foo00bar") is None

    def test_skip_ia_metadata_disabled_still_uses_cache(self):
        dp = DataProvider()
        dp.ia_cache["foo00bar"] = {"identifier": "foo00bar", "collection": ["inlibrary"]}
        assert dp.get_metadata("foo00bar") == {"identifier": "foo00bar", "collection": ["inlibrary"]}

    def test_skip_ia_metadata_enabled_ignores_cache(self):
        dp = DataProvider()
        dp.skip_ia_metadata = True
        dp.ia_cache["foo00bar"] = {"identifier": "foo00bar", "collection": ["inlibrary"]}
        assert dp.get_metadata("foo00bar") is None
