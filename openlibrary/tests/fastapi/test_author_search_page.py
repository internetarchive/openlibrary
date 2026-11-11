"""`/search/authors` HTML page on FastAPI.

It renders `search/authors.html.jinja`; the web.py handler renders the same
template until ops routes /search/authors to FastAPI in production. The shell
around the page is tested in `test_site_page.py` and the JSON API in
`test_search.py`; these test the page's own body.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from infogami.utils import macro
from openlibrary.fastapi.search import pages
from openlibrary.plugins.worksearch.code import SearchResponse
from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme


@pytest.fixture
def client(site_page_app) -> TestClient:
    # The site shell renders icons through the Templetor macros; make them available.
    macro.diskmacros.load_templates("openlibrary/macros")
    return TestClient(site_page_app(pages))


@pytest.fixture(autouse=True)
def coverstore_url(monkeypatch) -> str:
    monkeypatch.setattr("openlibrary.fastapi.search.get_coverstore_public_url", lambda: "https://covers.test")
    return "https://covers.test"


def _solr_response(*docs: dict, error: str = "", num_found: int | None = None) -> SearchResponse:
    return SearchResponse(
        facet_counts={},
        sort="",
        docs=list(docs),
        num_found=num_found if num_found is not None else len(docs),
        solr_select="",
        raw_resp={"response": {"start": 0}},
        error=error,
    )


def patched_search(stack: ExitStack, response: SearchResponse) -> MagicMock:
    solr_mock = stack.enter_context(patch("openlibrary.fastapi.search.run_solr_query_async", autospec=True))
    solr_mock.return_value = response
    return solr_mock


def _author(olid: str = "OL1A", name: str = "Jane Austen", work_count: int = 8, **fields) -> dict:
    return {"key": f"/authors/{olid}", "name": name, "work_count": work_count, **fields}


def test_authors_page_without_query(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/authors")

    assert response.status_code == 200
    html = response.text
    assert "<title>Search results for Authors | Open Library</title>" in html
    assert 'action="/search/authors"' in html
    # The search tabs, with Authors selected
    assert 'data-ol-link-track="SearchNav|SearchAuthors"' in html
    # Without a query there are no results, stats or pagination
    assert "search-results-stats" not in html
    assert "authorList" not in html
    assert "ol-pagination-wrapper" not in html
    # ... and no sort menu either
    assert "sort-options" not in html


def test_authors_page_lists_results(client):
    docs = [
        _author(
            "OL1A",
            "Jane Austen",
            8,
            birth_date="1775",
            death_date="1817",
            top_subjects=["Fiction", "Romance"],
            top_work="Pride and Prejudice",
        ),
        _author("OL2A", "Mark Twain", 2),
    ]
    with ExitStack() as stack:
        patched_search(stack, _solr_response(*docs, num_found=2))
        response = client.get("/search/authors?q=austen")

    assert response.status_code == 200
    html = response.text
    assert "search-results-stats" in html
    assert "2 hits" in html
    assert html.count('class="searchResultItem"') == 2
    assert 'href="/authors/OL1A/Jane_Austen"' in html
    assert "1775 - 1817" in html
    assert "<b>8 books</b>" in html
    assert "about Fiction, Romance" in html
    assert "including <i>Pride and Prejudice</i>" in html
    assert 'src="https://covers.test/a/olid/OL1A-M.jpg"' in html
    # The sort menu offers the author search sorts, with Relevance selected
    assert 'class="sort-options"' in html
    assert 'value="relevance"' in html
    assert "Work Count" in html
    assert "&#34;value&#34;: &#34;name&#34;" in html
    # Two results fit on one page, so no pagination
    assert "ol-pagination-wrapper" not in html


def test_authors_page_queries_solr_with_author_scheme(client):
    with ExitStack() as stack:
        solr_mock = patched_search(stack, _solr_response(_author()))
        client.get("/search/authors?q=austen&page=3")

    scheme, query = solr_mock.call_args.args
    assert isinstance(scheme, AuthorSearchScheme)
    assert query == {"q": "austen"}
    assert solr_mock.call_args.kwargs == {
        "offset": 200,  # one page is 100 authors
        "rows": 100,
        "fields": "*",
        "sort": "",
        "request_label": "AUTHOR_SEARCH",
    }


def test_authors_page_paginates(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response(_author(), num_found=250))
        response = client.get("/search/authors?q=austen&page=2")

    assert response.status_code == 200
    html = response.text
    assert "ol-pagination-wrapper" in html
    assert 'total-pages="3"' in html
    assert 'current-page="2"' in html


@pytest.mark.parametrize("page", ["0", "-3"])
def test_authors_page_clamps_page_to_one(client, page):
    with ExitStack() as stack:
        solr_mock = patched_search(stack, _solr_response(_author(), num_found=250))
        response = client.get(f"/search/authors?q=austen&page={page}")

    assert response.status_code == 200
    assert 'current-page="1"' in response.text
    assert solr_mock.call_args.kwargs["offset"] == 0


@pytest.mark.parametrize("sort_option", ["name", "work_count desc", "birth_date asc"])
def test_authors_page_forwards_sort(client, sort_option):
    with ExitStack() as stack:
        solr_mock = patched_search(stack, _solr_response(_author(), num_found=2))
        response = client.get("/search/authors", params={"q": "austen", "sort": sort_option})

    assert response.status_code == 200
    assert solr_mock.call_args.kwargs["sort"] == sort_option
    # The menu opens on the requested sort
    assert f'value="{sort_option}"' in response.text


def test_authors_page_rejects_unknown_sort(client):
    with ExitStack() as stack:
        solr_mock = patched_search(stack, _solr_response())
        response = client.get("/search/authors?q=austen&sort=bogus")

    assert response.status_code == 422
    solr_mock.assert_not_called()


def test_authors_page_no_results(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/authors?q=zzzzz")

    assert response.status_code == 200
    html = response.text
    assert "No <strong>authors</strong> directly matched your search" in html
    # The Search Inside matches suggestion carries the query over
    assert 'id="fulltext-search-suggestion"' in html
    assert 'data-query="zzzzz"' in html
    assert "authorList" not in html
    assert "ol-pagination-wrapper" not in html
    assert "sort-options" not in html


def test_authors_page_solr_error(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response(error="first problem\nsecond problem"))
        response = client.get("/search/authors?q=broken")

    assert response.status_code == 200
    html = response.text
    assert "first problem" in html
    assert "second problem" in html
    assert "authorList" not in html


def test_authors_page_escapes_query(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/authors?q=%22%3E%3Cscript%3E")

    assert response.status_code == 200
    # The query is escaped inside the attribute
    assert 'data-query="&#34;&gt;&lt;script&gt;"' in response.text
    assert 'data-query=""><' not in response.text


def test_authors_page_offers_merge_to_librarians(client):
    librarian = MagicMock()
    librarian.is_librarian_or_higher.return_value = True
    docs = [_author("OL1A", "Jane Austen"), _author("OL2A", "Jane Austin")]
    with ExitStack() as stack:
        patched_search(stack, _solr_response(*docs, num_found=2))
        stack.enter_context(patch("openlibrary.fastapi.search.get_current_user", return_value=librarian))
        response = client.get("/search/authors?q=jane+austen")

    assert response.status_code == 200
    assert "Is the same author listed twice?" in response.text
    assert 'href="/authors/merge?records=OL1A,OL2A"' in response.text


def test_authors_page_does_not_offer_merge_to_visitors(client):
    docs = [_author("OL1A", "Jane Austen"), _author("OL2A", "Jane Austin")]
    with ExitStack() as stack:
        patched_search(stack, _solr_response(*docs, num_found=2))
        response = client.get("/search/authors?q=jane+austen")

    assert response.status_code == 200
    assert "/authors/merge?records=" not in response.text
