"""`/search/lists` HTML page on FastAPI.

It renders `search/lists.html.jinja`; the web.py handler still renders the
Templetor `search/lists.html` until ops routes /search/lists to FastAPI in
production. The shell around the page is tested in `test_site_page.py` and the
JSON API in `test_search.py`; these test the page's own body.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from infogami.utils import macro
from openlibrary.core.lists.model import ListPreview
from openlibrary.fastapi.search import pages
from openlibrary.plugins.worksearch.code import SearchResponse


@pytest.fixture
def client(site_page_app) -> TestClient:
    # The page renders Templetor macros (pagination, loading indicator); make them available.
    macro.diskmacros.load_templates("openlibrary/macros")
    return TestClient(site_page_app(pages))


class FakeList:
    """A list that only knows how to preview itself (see `List.card`)."""

    def __init__(self, key: str, name: str):
        self.key = key
        self.name = name

    def card(self, current_user_key: str | None = None) -> ListPreview:
        return ListPreview(
            key=self.key,
            name=self.name,
            cover_url="/static/images/icons/avatar_book-sm.png",
            owner_key="/people/jane",
            owner_name="Jane",
            is_owner=current_user_key == "/people/jane",
            item_count=2,
            modified="2 days ago",
            description_html="<p>About <em>dogs</em></p>",
        )


def _solr_response(*keys, error: str = "", num_found: int | None = None) -> SearchResponse:
    docs = [{"key": key} for key in keys]
    return SearchResponse(
        facet_counts={},
        sort="",
        docs=docs,
        num_found=num_found if num_found is not None else len(docs),
        solr_select="",
        raw_resp={"response": {"start": 0}},
        error=error,
    )


def patched_search(stack: ExitStack, response: SearchResponse, lists: list | None = None) -> MagicMock:
    """Patch solr and the request-scoped site that resolves the list docs."""
    current_site = MagicMock()
    current_site.get_many.return_value = lists if lists is not None else []
    solr_mock = stack.enter_context(patch("openlibrary.fastapi.search.run_solr_query_async", autospec=True))
    site_mock = stack.enter_context(patch("openlibrary.fastapi.search.site"))
    solr_mock.return_value = response
    site_mock.get.return_value = current_site
    return current_site


def test_lists_page_without_query(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/lists")

    assert response.status_code == 200
    html = response.text
    assert "<title>List search | Open Library</title>" in html
    assert 'action="/search/lists"' in html
    # The search tabs
    assert 'data-ol-link-track="SearchNav|SearchLists"' in html
    # Without a query there are no results, stats or pagination
    assert "search-results-stats" not in html
    assert "listResults" not in html
    assert "ol-pagination-wrapper" not in html


def test_lists_page_title_leads_with_the_query(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/lists?q=pokemon+%3Cstuff%3E")

    assert response.status_code == 200
    assert "<title>pokemon &lt;stuff&gt; - List search | Open Library</title>" in response.text


def test_lists_page_results(client):
    with ExitStack() as stack:
        current_site = patched_search(
            stack,
            _solr_response("/people/jane/lists/OL1L", "/people/jane/lists/OL2L", num_found=45),
            lists=[FakeList("/people/jane/lists/OL1L", "Dogs"), FakeList("/people/jane/lists/OL2L", "More dogs")],
        )
        response = client.get("/search/lists?q=dogs")

    assert response.status_code == 200
    html = response.text
    assert "search-results-stats" in html
    assert "1 hit" not in html  # 45 found, so the plural form
    assert 'id="listResults"' in html
    assert html.count('class="searchResultItem"') == 2  # one preview per list doc
    assert "Dogs" in html
    # The owner's byline, and the list's size and last-modified date
    assert 'by <a href="/people/jane">Jane</a>' in " ".join(html.split())
    assert "2 items" in html
    assert "Last modified 2 days ago" in html
    assert "<p>About <em>dogs</em></p>" in html
    # One page per 20 results
    assert 'total-pages="3"' in html
    assert 'current-page="1"' in html
    current_site.get_many.assert_called_once_with(["/people/jane/lists/OL1L", "/people/jane/lists/OL2L"])


def test_lists_page_respects_page_param(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response(num_found=45))
        response = client.get("/search/lists?q=dogs&page=3")

    assert response.status_code == 200
    assert 'current-page="3"' in response.text


def test_lists_page_clamps_page_below_one(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response(num_found=45))
        response = client.get("/search/lists?q=dogs&page=-3")

    assert response.status_code == 200
    assert 'current-page="1"' in response.text


def test_lists_page_rejects_a_non_numeric_page(client):
    # Unlike web.py, which read it as page 1, FastAPI validates it: a clean 422, not a 500.
    response = client.get("/search/lists?q=dogs&page=abc")

    assert response.status_code == 422


def test_lists_page_no_results(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/lists?q=zzzzz")

    assert response.status_code == 200
    html = response.text
    assert "No <strong>lists</strong> directly matched your search" in html
    # The Search Inside matches suggestion with its query carried over
    assert 'data-query="zzzzz"' in html
    assert "listResults" not in html


def test_lists_page_solr_error(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response(error="first problem\nsecond problem"))
        response = client.get("/search/lists?q=broken")

    assert response.status_code == 200
    html = response.text
    assert "first problem" in html
    assert "second problem" in html
    assert "listResults" not in html


def test_lists_page_escapes_query(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/lists?q=%22%3E%3Cscript%3E")

    assert response.status_code == 200
    # The query is escaped inside the attribute (the shell's own <script> tags are unrelated)
    assert 'data-query="&#34;&gt;&lt;script&gt;"' in response.text
    assert 'data-query="\\"><' not in response.text
