from unittest.mock import MagicMock

from infogami.infobase.client import Thing
from openlibrary.solr.data_provider import BetterDataProvider


class TestBetterDataProvider:
    def test_get_document(self):
        mock_site = MagicMock()
        dp = BetterDataProvider(
            site=mock_site,
            db=MagicMock(),
            ia_db=MagicMock(),
        )
        mock_site.get_many.return_value = [Thing(mock_site, '/works/OL1W', {
            'key': '/works/OL1W',
            'type': {'key': '/type/work'},
        })]
        assert mock_site.get_many.call_count == 0
        dp.get_document('/works/OL1W')
        assert mock_site.get_many.call_count == 1
        dp.get_document('/works/OL1W')
        assert mock_site.get_many.call_count == 1

    def test_clear_cache(self):
        mock_site = MagicMock()
        dp = BetterDataProvider(
            site=mock_site,
            db=MagicMock(),
            ia_db=MagicMock(),
        )
        mock_site.get_many.return_value = [Thing(mock_site, '/works/OL1W', {
            'key': '/works/OL1W',
            'type': {'key': '/type/work'},
        })]
        assert mock_site.get_many.call_count == 0
        dp.get_document('/works/OL1W')
        assert mock_site.get_many.call_count == 1
        dp.clear_cache()
        dp.get_document('/works/OL1W')
        assert mock_site.get_many.call_count == 2
