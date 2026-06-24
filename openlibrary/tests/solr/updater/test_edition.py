import pytest

from openlibrary.solr.updater.edition import EditionSolrBuilder, EditionSolrUpdater, sort_title
from openlibrary.tests.solr.test_update import FakeDataProvider, make_edition


class FakeDataProviderWithCovers(FakeDataProvider):
    """FakeDataProvider with controllable cover dimensions."""

    def __init__(self, docs=None, cover_dimensions: dict[int, tuple[int, int] | None] | None = None):
        super().__init__(docs)
        self._cover_dimensions_map = cover_dimensions or {}

    def get_cover_dimensions(self, cover_id: int) -> tuple[int, int] | None:
        return self._cover_dimensions_map.get(cover_id)


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


class TestEditionSolrBuilderCoverDimensions:
    def test_cover_width_and_height_none_when_no_covers_field(self):
        """Edition with no covers field → cover_i None → dimensions None."""
        edition = make_edition()
        esb = EditionSolrBuilder(edition)
        assert esb.cover_i is None
        assert esb.cover_width is None
        assert esb.cover_height is None

    def test_cover_width_and_height_none_without_data_provider(self):
        """Edition has a cover id but no data_provider → dimensions are None."""
        edition = make_edition(covers=[55])
        esb = EditionSolrBuilder(edition, data_provider=None)
        assert esb.cover_i == 55
        assert esb.cover_width is None
        assert esb.cover_height is None

    def test_cover_width_and_height_from_data_provider(self):
        """Edition has cover id and data_provider returns valid dimensions."""
        edition = make_edition(covers=[55])
        dp = FakeDataProviderWithCovers(cover_dimensions={55: (640, 960)})
        esb = EditionSolrBuilder(edition, data_provider=dp)
        assert esb.cover_i == 55
        assert esb.cover_width == 640
        assert esb.cover_height == 960

    def test_sentinel_cover_id_minus_one_skipped(self):
        """cover id -1 is the sentinel for 'no cover'; it must be skipped."""
        edition = make_edition(covers=[-1, 88])
        dp = FakeDataProviderWithCovers(cover_dimensions={88: (320, 480)})
        esb = EditionSolrBuilder(edition, data_provider=dp)
        assert esb.cover_i == 88
        assert esb.cover_width == 320
        assert esb.cover_height == 480
