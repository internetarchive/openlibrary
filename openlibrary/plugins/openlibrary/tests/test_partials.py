"""Tests for partials.py functionality."""

from unittest.mock import AsyncMock, patch

import pytest
import web

from openlibrary.plugins.openlibrary.partials import (
    BookPageListsPartial,
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


def _community_card(title: str) -> dict:
    """A card for a list with no owner, so the template needs no follow-button bridge."""
    return {
        "url": "/lists/OL1L",
        "showcase": {"title": title, "count": 2, "covers": [False], "last_mod": ""},
        "owner": None,
        "own_list": False,
        "is_public": False,
        "is_subscribed": False,
    }


LISTS = [web.storage(key=f"/people/u/lists/OL{n}L", owner=None) for n in (1, 2, 3)]


class TestBookPageListsPartial:
    """The Jinja render must degrade the way the Templetor render did, not 500."""

    @pytest.fixture(autouse=True)
    def setup_context(self, request_context_fixture):
        # Set in the sync fixture, not inside the async test: pytest-asyncio runs
        # the coroutine in a copied context, so a token created there cannot be
        # reset by the fixture's teardown.
        request_context_fixture(lang="en")

    @pytest.mark.asyncio
    async def test_broken_card_is_skipped(self):
        good = _community_card("Fine list")
        with (
            patch("openlibrary.plugins.openlibrary.partials.get_lists_async", AsyncMock(return_value=LISTS)),
            patch("openlibrary.plugins.openlibrary.partials.get_current_user", return_value=None),
            patch.object(
                BookPageListsPartial,
                "get_list_card",
                side_effect=[good, AttributeError("'Thing' object has no attribute 'get_users_settings'"), good],
            ),
        ):
            result = await BookPageListsPartial.generate_async(workId="/works/OL1W", editionId="")

        assert result["hasLists"] is True
        html = result["partials"][0]
        assert html.count('class="list-follow-card"') == 2
        assert "Unable to render" not in html

    @pytest.mark.asyncio
    async def test_render_failure_keeps_old_fallback(self):
        with (
            patch("openlibrary.plugins.openlibrary.partials.get_lists_async", AsyncMock(return_value=LISTS)),
            patch("openlibrary.plugins.openlibrary.partials.get_current_user", return_value=None),
            patch.object(BookPageListsPartial, "get_list_card", return_value=_community_card("Fine list")),
            patch(
                "openlibrary.plugins.openlibrary.partials.render_jinja_template",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = await BookPageListsPartial.generate_async(workId="/works/OL1W", editionId="")

        assert result["hasLists"] is True
        assert result["partials"] == [BookPageListsPartial.RENDER_FALLBACK]
