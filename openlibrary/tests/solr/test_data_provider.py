from unittest.mock import MagicMock

import pytest

from infogami.infobase.client import Thing
from openlibrary.solr.data_provider import DatabaseDataProvider

# (Tag's singular tag_type, the work field [plural] that lists such tags,
# a tag key, a tag name) — _preload_tags resolves work-field refs into the cache
# regardless of the Tag's tag_type, so one parametrized case covers every type.
TAG_PRELOAD_CASES = [
    ("genre", "genres", "/tags/OL177T", "Romance"),
    ("subgenre", "subgenres", "/tags/OL272T", "Cyberpunk"),
    ("audience", "audiences", "/tags/OL301T", "Adult"),
    ("content_warning", "content_warnings", "/tags/OL401T", "Violence"),
    ("content_format", "content_formats", "/tags/OL501T", "Graphic Novel"),
    ("literary_form", "literary_forms", "/tags/OL183T", "Fiction"),
]


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
                    "audiences": ["/tags/OL301T"],
                },
            ),
            "/tags/OL177T": Thing(
                mock_site,
                "/tags/OL177T",
                {
                    "key": "/tags/OL177T",
                    "type": {"key": "/type/tag"},
                    "name": "Romance",
                    "tag_type": "genre",
                },
            ),
            "/tags/OL272T": Thing(
                mock_site,
                "/tags/OL272T",
                {
                    "key": "/tags/OL272T",
                    "type": {"key": "/type/tag"},
                    "name": "Cyberpunk",
                    "tag_type": "subgenre",
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
        assert dp.cache["/tags/OL301T"]["name"] == "Adult"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("tag_type", "work_field", "tag_key", "tag_name"), TAG_PRELOAD_CASES)
    async def test_preloads_tag_field(self, tag_type, work_field, tag_key, tag_name):
        # The work field is plural; the Tag it points at carries the singular
        # tag_type. _preload_tags resolves the ref into the cache either way.
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
                    work_field: [{"key": tag_key}],
                },
            ),
            tag_key: Thing(
                mock_site,
                tag_key,
                {
                    "key": tag_key,
                    "type": {"key": "/type/tag"},
                    "name": tag_name,
                    "tag_type": tag_type,
                },
            ),
        }
        mock_site.get_many.side_effect = lambda keys: [docs_by_key[k] for k in keys]

        await dp.get_document("/works/OL1W")

        assert dp.cache[tag_key]["name"] == tag_name
