import pytest

from openlibrary.solr.updater.edition import EditionSolrBuilder, EditionSolrUpdater, sort_title
from openlibrary.tests.solr.test_update import FakeDataProvider, make_edition


class TestEditionSolrUpdater:
    @pytest.mark.asyncio
    async def test_deletes_old_orphans(self):
        req, new_keys = await EditionSolrUpdater(FakeDataProvider()).update_key(
            {
                "key": "/books/OL1M",
                "type": {"key": "/type/edition"},
                "works": [{"key": "/works/OL1W"}],
            }
        )

        assert req.deletes == ["/works/OL1M"]
        assert req.adds == []
        assert new_keys == ["/works/OL1W"]

    @pytest.mark.asyncio
    async def test_enqueues_orphans_as_works(self):
        req, new_keys = await EditionSolrUpdater(FakeDataProvider()).update_key({"key": "/books/OL1M", "type": {"key": "/type/edition"}})

        assert req.deletes == []
        assert req.adds == []
        assert new_keys == ["/works/OL1M"]


@pytest.mark.parametrize(
    ("title", "subtitle", "expected"),
    [
        ("The Great Gatsby", None, "Great Gatsby, The"),
        ("Dune", None, "Dune"),
        ("The Hobbit", "There and Back Again", "Hobbit: There and Back Again, The"),
        ("L'amour", None, "amour, L'"),
    ],
)
def test_sort_title(title, subtitle, expected):
    assert sort_title(title, subtitle) == expected


class TestEditionSolrBuilder:
    def test_identifiers(self):
        edition = make_edition(
            identifiers={
                "Some.Weird.Key##": ["  id-1  ", None, "id-1", "id-2  "],
                "foo": [None],
            }
        )

        assert EditionSolrBuilder(edition).identifiers == {
            "id_some_weird_key": ["id-1", "id-2"],
        }
