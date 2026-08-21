"""Tests for partials.py functionality."""

import pytest

from openlibrary.plugins.openlibrary.partials import (
    CarouselCardPartial,
    CarouselLoadMoreParams,
    _solr_query_to_subject_key,
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


class TestSearchCarouselPublishYear:
    """The publishing-history chart's year range reaching a SEARCH carousel."""

    async def _captured_query(self, monkeypatch, published_in: str) -> str:
        captured = {}

        async def fake_work_search_async(query_params, **kwargs):
            captured.update(query_params)
            return {"docs": []}

        monkeypatch.setattr(
            "openlibrary.plugins.openlibrary.partials.work_search_async",
            fake_work_search_async,
        )
        params = CarouselLoadMoreParams(queryType="SEARCH", q="subject_key:fiction", published_in=published_in)
        await CarouselCardPartial._do_search_query(params)
        return captured["q"]

    @pytest.mark.asyncio
    async def test_year_range_is_filtered(self, monkeypatch):
        q = await self._captured_query(monkeypatch, "1990-2004")
        assert q == "subject_key:fiction publish_year:[1990 TO 2004]"

    @pytest.mark.asyncio
    async def test_single_year_click_is_filtered(self, monkeypatch):
        """A bar click sends from == to; it must still narrow the results."""
        q = await self._captured_query(monkeypatch, "1994-1994")
        assert q == "subject_key:fiction publish_year:[1994 TO 1994]"

    @pytest.mark.asyncio
    async def test_no_selection_leaves_query_alone(self, monkeypatch):
        assert await self._captured_query(monkeypatch, "") == "subject_key:fiction"

    @pytest.mark.asyncio
    async def test_unparseable_range_leaves_query_alone(self, monkeypatch):
        assert await self._captured_query(monkeypatch, "abc-def") == "subject_key:fiction"
