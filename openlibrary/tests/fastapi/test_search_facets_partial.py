"""Tests for GET /partials/SearchFacets.json — the search page's facet sidebar."""

import json
from unittest.mock import patch

import pytest

from openlibrary.plugins.worksearch.code import SearchResponse, get_facet_map
from openlibrary.utils.request_context import RequestContextVars, req_context

URL = "/partials/SearchFacets.json"


@pytest.fixture(autouse=True)
def english_request():
    """The facet templates translate their labels, which reads the request's language."""
    token = req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=True, print_disabled=False))
    yield
    req_context.reset(token)


@pytest.fixture
def mock_solr():
    # The sidebar reads every facet and skips any with fewer than two values.
    facet_counts = {header: [] for header, _label in get_facet_map()}
    facet_counts["language"] = [("eng", "English", 10), ("fre", "French", 5)]
    response = SearchResponse(
        facet_counts=facet_counts,
        sort="",
        docs=[],
        num_found=10,
        solr_select="",
    )
    with patch("openlibrary.plugins.openlibrary.partials.run_solr_query_async", return_value=response) as mock:
        yield mock


def get_facets(client, data):
    return client.get(URL, params={"data": json.dumps(data)})


class TestSearchFacetsPartial:
    def test_facet_links_point_at_the_given_path(self, fastapi_client, mock_solr):
        response = get_facets(fastapi_client, {"param": {"q": "tolkien"}, "path": "/search", "query": "?q=tolkien"})

        assert response.status_code == 200
        sidebar = response.json()["sidebar"]
        assert "/search?q=tolkien&amp;language=eng" in sidebar
        assert "/install" not in sidebar

    @pytest.mark.parametrize(
        "path",
        [None, "", "search", "https://example.com/search", 123],
        ids=["missing", "empty", "relative", "absolute-url", "not-a-string"],
    )
    def test_rejects_data_without_a_page_path(self, fastapi_client, mock_solr, path):
        data = {"param": {"q": "tolkien"}, "query": "?q=tolkien"}
        if path is not None:
            data["path"] = path

        response = get_facets(fastapi_client, data)

        assert response.status_code == 422
        assert "path" in response.json()["detail"]
        mock_solr.assert_not_called()

    def test_rejects_data_that_is_not_an_object(self, fastapi_client, mock_solr):
        response = get_facets(fastapi_client, ["/search"])

        assert response.status_code == 422
        mock_solr.assert_not_called()

    def test_rejects_invalid_json(self, fastapi_client, mock_solr):
        response = fastapi_client.get(URL, params={"data": "{not json"})

        assert response.status_code == 400
        mock_solr.assert_not_called()
