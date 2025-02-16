import pytest

from openlibrary.solr.updater.edition import EditionSolrUpdater
from openlibrary.tests.solr.test_update import FakeDataProvider


class TestEditionSolrUpdater:
    @pytest.mark.asyncio
    async def test_deletes_old_orphans(self):
        req, new_keys = await EditionSolrUpdater(FakeDataProvider()).update_key(
            {
                'key': '/books/OL1M',
                'type': {'key': '/type/edition'},
                'works': [{'key': '/works/OL1W'}],
            }
        )

        assert req.deletes == ['/works/OL1M']
        assert req.adds == []
        assert new_keys == ['/works/OL1W']

    @pytest.mark.asyncio
    async def test_enqueues_orphans_as_works(self):
        req, new_keys = await EditionSolrUpdater(FakeDataProvider()).update_key(
            {'key': '/books/OL1M', 'type': {'key': '/type/edition'}}
        )

        assert req.deletes == []
        assert req.adds == []
        assert new_keys == ['/works/OL1M']
