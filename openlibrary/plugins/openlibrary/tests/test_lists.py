import json
from unittest.mock import Mock, patch

import pytest
from starlette.datastructures import URL

from openlibrary.plugins.openlibrary import lists as legacy_lists
from openlibrary.plugins.openlibrary.lists import ListRecord


class TestListRecord:
    def test_from_input_no_data(self):
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
        ):
            mock_web_data.return_value = b""
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": [],
            }
            assert ListRecord.from_input() == ListRecord(
                key=None,
                name="foo",
                description="bar",
                seeds=[],
            )

    def test_from_input_with_data(self):
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
            patch("web.ctx") as mock_web_ctx,
        ):
            mock_web_ctx.env = {}
            mock_web_data.return_value = b"key=/lists/OL1L&name=foo+data&description=bar&seeds--0--key=/books/OL1M&seeds--1--key=/books/OL2M"
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": [],
            }
            assert ListRecord.from_input() == ListRecord(
                key="/lists/OL1L",
                name="foo data",
                description="bar",
                seeds=[{"key": "/books/OL1M"}, {"key": "/books/OL2M"}],
            )

    def test_from_input_with_json_data(self):
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
            patch("web.ctx") as mock_web_ctx,
        ):
            mock_web_ctx.env = {"CONTENT_TYPE": "application/json"}
            mock_web_data.return_value = json.dumps(
                {
                    "name": "foo data",
                    "description": "bar",
                    "seeds": [{"key": "/books/OL1M"}, {"key": "/books/OL2M"}],
                }
            ).encode("utf-8")
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": [],
            }
            assert ListRecord.from_input() == ListRecord(
                key=None,
                name="foo data",
                description="bar",
                seeds=[{"key": "/books/OL1M"}, {"key": "/books/OL2M"}],
            )

    SEED_TESTS: tuple = (
        ([], []),
        (["OL1M"], [{"key": "/books/OL1M"}]),
        (["OL1M", "OL2M"], [{"key": "/books/OL1M"}, {"key": "/books/OL2M"}]),
        (["OL1M,OL2M"], [{"key": "/books/OL1M"}, {"key": "/books/OL2M"}]),
    )

    @pytest.mark.parametrize(("seeds", "expected"), SEED_TESTS)
    def test_from_input_seeds(self, seeds, expected):
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
        ):
            mock_web_data.return_value = b""
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": seeds,
            }
            assert ListRecord.from_input() == ListRecord(
                key=None,
                name="foo",
                description="bar",
                seeds=expected,
            )

    def test_normalize_input_seed(self):
        f = ListRecord.normalize_input_seed

        assert f("/books/OL1M") == {"key": "/books/OL1M"}
        assert f({"key": "/books/OL1M"}) == {"key": "/books/OL1M"}
        assert f("/subjects/love") == "subject:love"
        assert f("subject:love") == "subject:love"

    def test_normalize_input_seed_with_blank_key(self):
        """Test that normalize_input_seed rejects blank keys.

        Blank keys should raise a ValueError instead of
        being accepted and passed through to the database.
        """
        f = ListRecord.normalize_input_seed

        # Blank keys should now raise ValueError
        with pytest.raises(ValueError, match="Seed key cannot be empty"):
            f({"key": ""})

        # Valid keys should still work
        assert f({"key": "/books/OL1M"}) == {"key": "/books/OL1M"}

    def test_from_input_rejects_blank_keys(self):
        """Test that form submission rejects seeds with blank keys.

        Attempting to submit a form with blank keys
        should raise a ValueError during normalization.
        """
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
        ):
            mock_web_data.return_value = b""
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": [
                    {"key": "/books/OL1M"},  # valid
                    {"key": ""},  # blank key - should raise error
                    {"key": "/books/OL2M"},  # valid
                ],
            }
            # Blank keys should now raise ValueError during normalization
            with pytest.raises(ValueError, match="Seed key cannot be empty"):
                ListRecord.from_input()


class FakePreviewList:
    def __init__(self, key):
        self.key = key

    def preview(self):
        return {"key": self.key}


class FakeListsDoc:
    def __init__(self, count):
        self._lists = [FakePreviewList(f"/people/alice/lists/OL{index}L") for index in range(count)]

    def get_lists(self, limit=50, offset=0):
        return self._lists[offset : offset + limit]


class TestBuildPaginationLinks:
    """Tests for build_pagination_links function."""

    def test_first_page_has_next_no_prev(self):
        """First page with more results should have next, no prev."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=60, count=50, offset=0, limit=50)
        assert links == {
            "next": "/people/alice/lists.json?limit=50&offset=50",
        }

    def test_middle_page_has_both_next_and_prev(self):
        """A middle paginated page should have both next and prev."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=60, count=25, offset=25, limit=25)
        assert links == {
            "next": "/people/alice/lists.json?limit=25&offset=50",
            "prev": "/people/alice/lists.json?limit=25&offset=0",
        }

    def test_last_page_has_prev_no_next(self):
        """Last page should have prev, no next."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=60, count=10, offset=50, limit=50)
        assert links == {
            "prev": "/people/alice/lists.json?limit=50&offset=0",
        }

    def test_single_page_no_pagination(self):
        """When results fit on one page, no pagination links."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=30, count=30, offset=0, limit=50)
        assert links == {}

    def test_empty_results_no_pagination(self):
        """When there are no results, no pagination links."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=0, count=0, offset=0, limit=50)
        assert links == {}

    def test_prev_offset_never_negative(self):
        """Prev offset should be 0, not negative, when offset < limit."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=100, count=5, offset=5, limit=50)
        assert links["prev"] == "/people/alice/lists.json?limit=50&offset=0"

    def test_works_with_custom_endpoint_path(self):
        """Should work with any endpoint path (e.g., seed paths without .json)."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists"), total=60, count=50, offset=0, limit=50)
        assert links == {
            "next": "/people/alice/lists?limit=50&offset=50",
        }

    def test_uses_count_not_limit_for_determining_more(self):
        """Pagination 'next' should depend on count returned, not limit."""
        # Even with limit=50, if only 5 items returned and total=60, there's more
        links = legacy_lists.build_pagination_links(URL("/works/OL42W/lists.json"), total=60, count=5, offset=0, limit=50)
        assert links == {
            "next": "/works/OL42W/lists.json?limit=50&offset=50",
        }


def test_get_lists_data_uses_lists_json_path_for_pagination_links():
    doc = FakeListsDoc(60)
    mock_site = Mock()
    mock_site.get.return_value = doc

    with patch("openlibrary.plugins.openlibrary.lists.site") as mock_site_context:
        mock_site_context.get.return_value = mock_site

        data = legacy_lists.lists_json.get_lists_data(
            "/people/alice",
            limit=50,
            offset=0,
            query_path="/people/alice/lists.json",
        )

    assert data["links"]["self"] == "/people/alice"
    assert data["links"]["next"] == "/people/alice/lists.json?limit=50&offset=50"
