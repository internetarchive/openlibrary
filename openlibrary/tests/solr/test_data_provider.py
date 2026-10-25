from unittest.mock import MagicMock

import pytest

from infogami.infobase.client import Thing
from openlibrary.plugins.openlibrary import connection
from openlibrary.solr.data_provider import DatabaseDataProvider


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

    def test_reads_skip_memcache(self, monkeypatch):
        mock_ol_connection = MagicMock()
        monkeypatch.setattr(connection, "OLConnection", mock_ol_connection)
        dp = DatabaseDataProvider(db=MagicMock())

        site = dp.get_site()

        mock_ol_connection.assert_called_once_with(use_memcache=False)
        assert site._conn is mock_ol_connection.return_value
