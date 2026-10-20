from unittest.mock import MagicMock

import pytest

from infogami.infobase.client import Thing
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

    @pytest.mark.asyncio
    async def test_preloads_tags_from_db_shaped_refs(self):
        mock_site = MagicMock()
        dp = DatabaseDataProvider(
            site=mock_site,
            db=MagicMock(),
        )
        docs_by_key = {
            "/works/OL1W": Thing(
                mock_site,
                "/works/OL1W",
                {
                    "key": "/works/OL1W",
                    "type": {"key": "/type/work"},
                    "genres": [{"key": "/tags/OL177T"}],
                    "subgenres": [{"key": "/tags/OL272T"}],
                    "audience": ["/tags/OL301T"],
                },
            ),
            "/tags/OL177T": Thing(
                mock_site,
                "/tags/OL177T",
                {
                    "key": "/tags/OL177T",
                    "type": {"key": "/type/tag"},
                    "name": "Romance",
                    "tag_type": "genres",
                },
            ),
            "/tags/OL272T": Thing(
                mock_site,
                "/tags/OL272T",
                {
                    "key": "/tags/OL272T",
                    "type": {"key": "/type/tag"},
                    "name": "Cyberpunk",
                    "tag_type": "subgenres",
                },
            ),
            "/tags/OL301T": Thing(
                mock_site,
                "/tags/OL301T",
                {
                    "key": "/tags/OL301T",
                    "type": {"key": "/type/tag"},
                    "name": "Adult",
                    "tag_type": "audience",
                },
            ),
        }
        mock_site.get_many.side_effect = lambda keys: [docs_by_key[k] for k in keys]

        await dp.get_document("/works/OL1W")

        assert dp.cache["/tags/OL177T"]["name"] == "Romance"
        assert dp.cache["/tags/OL272T"]["name"] == "Cyberpunk"
        assert dp.cache["/tags/OL301T"]["name"] == "Adult"
