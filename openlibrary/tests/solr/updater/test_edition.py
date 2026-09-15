import pytest

from openlibrary.solr.updater.edition import EditionSolrBuilder, EditionSolrUpdater, sort_title
from openlibrary.solr.updater.work import WorkSolrBuilder
from openlibrary.tests.solr.test_update import FakeDataProvider, make_edition, make_work


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

        assert EditionSolrBuilder(edition, solr_work={}, db_work=None, db_authors=[])._identifiers == {
            "id_some_weird_key": ["id-1", "id-2"],
        }

    def test_carries_genre_fields_from_work_builder(self):
        genre = {
            "key": "/tags/OL177T",
            "type": {"key": "/type/tag"},
            "name": "Romance",
            "tag_type": "genres",
        }
        work_builder = WorkSolrBuilder(
            work=make_work(),
            editions=[],
            authors=[],
            series=[],
            data_provider=FakeDataProvider(),
            ia_metadata={},
            trending_data={},
            tags=[genre],
        )
        edition = make_edition()
        doc = EditionSolrBuilder(
            edition, solr_work=work_builder, db_work=None, db_authors=[]
        ).build()
        assert doc["genre_key"] == ["OL177T"]
        assert doc["genre_name"] == ["Romance"]
        assert "subgenre_key" not in doc
        assert "subgenre_name" not in doc
        assert "audience_key" not in doc
        assert "audience_name" not in doc

    def test_carries_genre_fields_from_work_dict(self):
        edition = make_edition()
        doc = EditionSolrBuilder(
            edition,
            solr_work={
                "genre_key": ["OL177T"],
                "genre_name": ["Romance"],
                "subgenre_key": ["OL272T"],
                "subgenre_name": ["Cyberpunk"],
                "audience_key": ["OL301T"],
                "audience_name": ["Adult"],
            },
            db_work=None,
            db_authors=[],
        ).build()
        assert doc["genre_key"] == ["OL177T"]
        assert doc["genre_name"] == ["Romance"]
        assert doc["subgenre_key"] == ["OL272T"]
        assert doc["subgenre_name"] == ["Cyberpunk"]
        assert doc["audience_key"] == ["OL301T"]
        assert doc["audience_name"] == ["Adult"]

    def test_missing_genre_fields_from_work_dict(self):
        edition = make_edition()
        doc = EditionSolrBuilder(
            edition, solr_work={"author_name": ["Foo"]}, db_work=None, db_authors=[]
        ).build()
        assert "genre_key" not in doc
        assert "genre_name" not in doc
        assert "subgenre_key" not in doc
        assert "audience_key" not in doc
