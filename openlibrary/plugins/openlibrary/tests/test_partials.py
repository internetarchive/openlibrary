"""Tests for partials.py functionality."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from openlibrary.plugins.openlibrary.partials import (
    NearbyBooksPartial,
    _solr_query_to_subject_key,
    gather_nearby_books_async,
)


class TestSolrQueryToSubjectKey:
    """Tests for _solr_query_to_subject_key conversion."""

    def test_subject_key_format(self):
        """Test subject_key: format conversion."""
        assert _solr_query_to_subject_key("subject_key:science") == "/subjects/science"

    def test_person_key_format(self):
        """Test person_key: format conversion."""
        assert _solr_query_to_subject_key("person_key:harry_potter") == "/subjects/person:harry_potter"

    def test_place_key_format(self):
        """Test place_key: format conversion."""
        assert _solr_query_to_subject_key("place_key:france") == "/subjects/place:france"

    def test_time_key_format(self):
        """Test time_key: format conversion."""
        assert _solr_query_to_subject_key("time_key:19th_century") == "/subjects/time:19th_century"

    def test_subject_seed_format(self):
        """Test subject: format conversion."""
        assert _solr_query_to_subject_key("subject:science") == "/subjects/science"

    def test_already_in_correct_format(self):
        """Test /subjects/ format passes through."""
        assert _solr_query_to_subject_key("/subjects/science") == "/subjects/science"

    def test_invalid_format_raises_error(self):
        """Test invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Unable to convert query to subject key"):
            _solr_query_to_subject_key("invalid:format")


def _solr_result(docs):
    result = Mock()
    result.docs = docs
    return result


class TestGatherNearbyBooksAsync:
    """Tests for the "Nearby Books" (DDC shelf-adjacency) Solr queries."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_work_has_no_ddc_sort(self):
        mock_solr = Mock()
        mock_solr.get_async = AsyncMock(return_value=None)

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await gather_nearby_books_async("/works/OL1W", language=None, limit=20)

        assert docs == []
        mock_solr.get_async.assert_awaited_once_with("/works/OL1W", fields=["ddc_sort"])

    @pytest.mark.asyncio
    async def test_returns_empty_for_non_numeric_ddc_sort(self):
        """[Fic]/[E] etc. sort after every number and aren't a real shelf position."""
        mock_solr = Mock()
        mock_solr.get_async = AsyncMock(return_value={"ddc_sort": "[Fic]"})

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await gather_nearby_books_async("/works/OL1W", language=None, limit=20)

        assert docs == []

    @pytest.mark.asyncio
    async def test_anchors_on_the_works_indexed_ddc_sort_with_strict_bounds(self):
        """The anchor is the work's own ddc_sort (fetched from Solr), not a
        value recomputed from whichever edition happens to be viewed."""
        mock_solr = Mock()
        mock_solr.get_async = AsyncMock(return_value={"ddc_sort": "813.54"})
        mock_solr.select_async = AsyncMock(
            side_effect=[
                _solr_result([{"key": "/works/OL2W"}]),  # exact
                _solr_result([{"key": "/works/OL3W"}]),  # before
                _solr_result([{"key": "/works/OL4W"}]),  # after
            ]
        )

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await gather_nearby_books_async("/works/OL1W", language="eng", limit=20)

        assert [d["key"] for d in docs] == ["/works/OL3W", "/works/OL2W", "/works/OL4W"]

        queries = [c.args[0] for c in mock_solr.select_async.call_args_list]
        assert 'ddc_sort:"813.54"' in queries[0]
        assert 'ddc_sort:["000" TO "813.54"}' in queries[1]
        assert 'ddc_sort:{"813.54" TO "999.99999"]' in queries[2]
        assert all('-key:"/works/OL1W"' in q for q in queries)
        assert all('language:"eng"' in q for q in queries)
        assert all("content_warning:cover" in q for q in queries)
        assert all("type:work" in q for q in queries)


class TestNearbyBooksPartial:
    @pytest.mark.asyncio
    async def test_generate_async_returns_empty_partial_when_no_neighbours(self):
        with patch(
            "openlibrary.plugins.openlibrary.partials.gather_nearby_books_async",
            AsyncMock(return_value=[]),
        ):
            params = Mock(work_key="/works/OL1W", language=None, limit=20)
            result = await NearbyBooksPartial.generate_async(params)

        assert result == {"partials": ""}
