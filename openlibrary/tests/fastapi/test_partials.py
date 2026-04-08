"""Tests for the /partials/LazyCarousel.json FastAPI endpoint.

Run inside Docker:
    docker compose run --rm home make test-py
    # or specifically:
    docker compose run --rm home python -m pytest openlibrary/tests/fastapi/test_partials.py -v
"""

from unittest.mock import patch

import pytest
import web

from openlibrary.plugins.openlibrary.partials import (
    LazyCarouselParams,
    LazyCarouselPartial,
    gather_lazy_carousel_data,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MOCK_GENERATE = "openlibrary.fastapi.partials.LazyCarouselPartial.generate"
_MOCK_GATHER = "openlibrary.plugins.openlibrary.partials.gather_lazy_carousel_data"
_MOCK_MACRO = "web.template.Template.globals"
_MOCK_WORK_SEARCH = "openlibrary.plugins.openlibrary.partials.work_search"

_FAKE_GATHER_RESPONSE = {
    "docs": [{"key": "/works/OL1W", "title": "Test Book"}],
}


@pytest.fixture
def mock_generate():
    """Mock LazyCarouselPartial.generate to avoid Solr + template calls."""
    with patch(_MOCK_GENERATE, return_value={"partials": "<div class='carousel'>books here</div>"}) as mock:
        yield mock


# ---------------------------------------------------------------------------
# Endpoint tests (via FastAPI test client)
# ---------------------------------------------------------------------------


class TestLazyCarouselEndpoint:
    """Tests for GET /partials/LazyCarousel.json"""

    def test_returns_partials_key(self, fastapi_client, mock_generate):
        """Response must contain a 'partials' key with HTML."""
        resp = fastapi_client.get("/partials/LazyCarousel.json", params={"query": "subject:fiction"})
        assert resp.status_code == 200
        data = resp.json()
        assert "partials" in data
        assert "carousel" in data["partials"]

    def test_uses_generate(self, fastapi_client, mock_generate):
        """The endpoint must call generate."""
        fastapi_client.get("/partials/LazyCarousel.json", params={"query": "subject:history"})
        mock_generate.assert_called_once()

    def test_empty_query_is_accepted(self, fastapi_client, mock_generate):
        """An empty query should be a valid request."""
        resp = fastapi_client.get("/partials/LazyCarousel.json", params={"query": ""})
        assert resp.status_code == 200

    def test_all_optional_params_accepted(self, fastapi_client, mock_generate):
        """All LazyCarouselParams fields should be accepted without error."""
        resp = fastapi_client.get(
            "/partials/LazyCarousel.json",
            params={
                "query": "subject:science",
                "title": "Science Books",
                "sort": "editions",
                "key": "homepage-science",
                "limit": 10,
                "search": True,
                "has_fulltext_only": False,
                "layout": "grid",
                "fallback": "subject:nonfiction",
                "safe_mode": False,
            },
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Unit tests for gather_lazy_carousel_data()
# ---------------------------------------------------------------------------


class TestGatherLazyCarouselData:
    """Unit tests for the shared gather_lazy_carousel_data() helper."""

    def test_calls_work_search_with_correct_params(self):
        """Must call work_search with the correct query, sort, limit and fields."""
        with patch(_MOCK_WORK_SEARCH, return_value={"docs": []}) as mock_search:
            gather_lazy_carousel_data("subject:fiction", sort="editions", limit=10, has_fulltext_only=True, safe_mode=False)
        mock_search.assert_called_once()
        kwargs = mock_search.call_args[1]
        assert kwargs["sort"] == "editions"
        assert kwargs["limit"] == 10
        assert kwargs["facet"] is False
        assert kwargs["request_label"] == "BOOK_CAROUSEL"
        assert mock_search.call_args[0][0].get("has_fulltext") == "true"

    def test_no_fulltext_param_when_disabled(self):
        """has_fulltext must not appear in Solr params when has_fulltext_only=False."""
        with patch(_MOCK_WORK_SEARCH, return_value={"docs": []}) as mock_search:
            gather_lazy_carousel_data("subject:history", sort="new", limit=20, has_fulltext_only=False, safe_mode=False)
        assert "has_fulltext" not in mock_search.call_args[0][0]

    def test_safe_mode_appends_content_warning_filter(self):
        """When safe_mode=True, the content-warning filter must be appended to the Solr query."""
        with patch(_MOCK_WORK_SEARCH, return_value={"docs": []}) as mock_search:
            gather_lazy_carousel_data("subject:fiction", sort="new", limit=20, has_fulltext_only=True, safe_mode=True)
        solr_q = mock_search.call_args[0][0]["q"]
        assert '-subject:"content_warning:cover"' in solr_q

    def test_safe_mode_filter_is_idempotent(self):
        """If the filter is already present, it must NOT be appended again."""
        query = 'subject:fiction -subject:"content_warning:cover"'
        with patch(_MOCK_WORK_SEARCH, return_value={"docs": []}) as mock_search:
            gather_lazy_carousel_data(query, sort="new", limit=20, has_fulltext_only=True, safe_mode=True)
        solr_q = mock_search.call_args[0][0]["q"]
        assert solr_q.count('-subject:"content_warning:cover"') == 1

    def test_safe_mode_false_does_not_add_filter(self):
        """When safe_mode=False, the content-warning filter must NOT be added."""
        with patch(_MOCK_WORK_SEARCH, return_value={"docs": []}) as mock_search:
            gather_lazy_carousel_data("subject:fiction", sort="new", limit=20, has_fulltext_only=True, safe_mode=False)
        assert "content_warning" not in mock_search.call_args[0][0]["q"]

    def test_returns_docs_key(self):
        """Result must contain a 'docs' key with the Solr results."""
        fake_docs = [{"key": "/works/OL1W", "title": "Book"}]
        with patch(_MOCK_WORK_SEARCH, return_value={"docs": fake_docs}):
            result = gather_lazy_carousel_data("subject:fiction", sort="editions", limit=10, has_fulltext_only=False, safe_mode=False)
        assert result["docs"] == fake_docs


# ---------------------------------------------------------------------------
# Unit tests for LazyCarouselPartial.generate()
# ---------------------------------------------------------------------------


class TestLazyCarouselPartialUnit:
    """Unit tests for LazyCarouselPartial in isolation."""

    def test_generate_delegates_to_gather_lazy_carousel_data(self):
        """generate() must call gather_lazy_carousel_data() with the correct params."""
        params = LazyCarouselParams(query="subject:fiction", sort="editions", limit=10, safe_mode=False)
        partial = LazyCarouselPartial(params=params)
        mock_macro = web.Storage(RawQueryCarousel=lambda *a, **kw: "<div class='carousel'/>")
        with (
            patch(_MOCK_GATHER, return_value=_FAKE_GATHER_RESPONSE) as mock_gather,
            patch.dict(web.template.Template.globals, {"macros": mock_macro}),
        ):
            result = partial.generate()
        mock_gather.assert_called_once_with(
            query="subject:fiction",
            sort="editions",
            limit=10,
            has_fulltext_only=True,
            safe_mode=False,
        )
        assert "partials" in result

    def test_generate_passes_safe_mode_from_params_to_template(self):
        """generate() must pass self.params.safe_mode to the macro so the
        template can apply the filter to the load_more URL and View All link."""
        for safe_mode_val in (True, False):
            captured = {}

            def capture_macro(*a, safe_mode=None, **kw):
                captured["safe_mode"] = safe_mode
                return "<div/>"

            mock_macro = web.Storage(RawQueryCarousel=capture_macro)
            params = LazyCarouselParams(query="subject:fiction", safe_mode=safe_mode_val)
            partial = LazyCarouselPartial(params=params)
            with (
                patch(_MOCK_GATHER, return_value=_FAKE_GATHER_RESPONSE),
                patch.dict(web.template.Template.globals, {"macros": mock_macro}),
            ):
                partial.generate()
            assert captured.get("safe_mode") is safe_mode_val

    def test_generate_passes_sort_from_params_to_template(self):
        """generate() must pass the sort from LazyCarouselParams directly to the macro."""
        captured = {}

        def capture_macro(*a, sort=None, **kw):
            captured["sort"] = sort
            return "<div/>"

        mock_macro = web.Storage(RawQueryCarousel=capture_macro)
        params = LazyCarouselParams(query="subject:art", sort="editions")
        partial = LazyCarouselPartial(params=params)
        with (
            patch(_MOCK_GATHER, return_value=_FAKE_GATHER_RESPONSE),
            patch.dict(web.template.Template.globals, {"macros": mock_macro}),
        ):
            partial.generate()
        assert captured.get("sort") == "editions"
