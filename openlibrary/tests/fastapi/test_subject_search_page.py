"""`/search/subjects` HTML page on FastAPI, and its web.py handler while that still exists.

It renders `search/subjects.html.jinja`. The shell around the page (user, flash
messages, language) is tested in `test_site_page.py` and the JSON API in
`test_search.py`; these test the page's own body and inputs.
"""

from contextlib import ExitStack
from math import ceil
from unittest.mock import MagicMock, patch

import pytest
import web
from fastapi.testclient import TestClient

from openlibrary.core.helpers import commify
from openlibrary.core.jinja import render_jinja_template
from openlibrary.fastapi.search import SearchNav, pages
from openlibrary.plugins.worksearch import code as worksearch_code
from openlibrary.plugins.worksearch.code import SearchResponse


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def _solr_response(*docs: dict, error: str = "", num_found: int | None = None) -> SearchResponse:
    return SearchResponse(
        facet_counts={},
        sort="work_count desc",
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


def test_subjects_page_without_query(client):
    with ExitStack() as stack:
        solr_mock = patched_search(stack, _solr_response())
        response = client.get("/search/subjects")

    assert response.status_code == 200
    html = response.text
    assert "<title>Subject search | Open Library</title>" in html
    assert 'action=""' in html
    # The search tabs
    assert 'data-ol-link-track="SearchNav|SearchSubjects"' in html
    # Without a query nothing is searched, and there are no results or pagination
    solr_mock.assert_not_called()
    assert "search-results-stats" not in html
    assert "subjectList" not in html
    assert "ol-pagination-wrapper" not in html


def test_subjects_page_title_leads_with_the_query(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/subjects?q=pokemon+%3Cstuff%3E")

    assert response.status_code == 200
    assert "<title>pokemon &lt;stuff&gt; - Subject search | Open Library</title>" in response.text


def test_subjects_page_results(client):
    with ExitStack() as stack:
        patched_search(
            stack,
            _solr_response(
                {"name": "Science fiction", "subject_type": "subject", "work_count": 1234},
                {"name": "Harry Potter", "subject_type": "person", "work_count": 2},
                {"name": "20th century", "subject_type": "time", "work_count": 1},
                num_found=250,
            ),
        )
        response = client.get("/search/subjects?q=dogs")

    assert response.status_code == 200
    html = response.text
    assert "search-results-stats" in html
    assert "250 hits" in html
    # Subjects, people and times link to their /subjects/ page
    assert '<a href="/subjects/science_fiction">Science fiction</a>' in html
    assert '<a href="/subjects/person:harry_potter">Harry Potter</a>' in html
    assert '<a href="/subjects/time:20th_century">20th century</a>' in html
    # Each subject's size and type
    assert "1234 books" in html
    assert "2 books" in html
    assert "1 book" in html
    assert '<span class="darkgreen">subject</span>' in html
    assert '<span class="red">person</span>' in html
    assert '<span class="teal">time</span>' in html
    # One page per 100 results
    assert 'total-pages="3"' in html
    assert 'current-page="1"' in html


def test_subjects_page_respects_page_param(client):
    with ExitStack() as stack:
        solr_mock = patched_search(stack, _solr_response(num_found=250))
        response = client.get("/search/subjects?q=dogs&page=3")

    assert response.status_code == 200
    assert 'current-page="3"' in response.text
    assert solr_mock.call_args.kwargs["offset"] == 200
    assert solr_mock.call_args.kwargs["rows"] == 100


def test_subjects_page_clamps_page_below_one(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response(num_found=250))
        response = client.get("/search/subjects?q=dogs&page=-3")

    assert response.status_code == 200
    assert 'current-page="1"' in response.text


def test_subjects_page_rejects_a_non_numeric_page(client):
    # web.py read it as page 1; FastAPI validates it: a clean 422, not a 500.
    response = client.get("/search/subjects?q=dogs&page=abc")

    assert response.status_code == 422


def test_subjects_page_no_results(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/subjects?q=zzzzz")

    assert response.status_code == 200
    html = response.text
    assert "No <strong>subjects</strong> directly matched your search" in html
    # The Search Inside matches suggestion with its query carried over
    assert 'data-query="zzzzz"' in html
    assert "subjectList" not in html


def test_subjects_page_solr_error(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response(error="first problem\nsecond problem"))
        response = client.get("/search/subjects?q=broken")

    assert response.status_code == 200
    html = response.text
    assert "first problem" in html
    assert "second problem" in html
    assert "subjectList" not in html


def test_subjects_page_escapes_query(client):
    with ExitStack() as stack:
        patched_search(stack, _solr_response())
        response = client.get("/search/subjects?q=%22%3E%3Cscript%3E")

    assert response.status_code == 200
    # The query is escaped inside the attribute (the shell's own <script> tags are unrelated)
    assert 'data-query="&#34;&gt;&lt;script&gt;"' in response.text
    assert 'data-query="\\"><' not in response.text


def _webpy_get(monkeypatch, path: str, query: str) -> None:
    for key, value in {"path": path, "env": {"QUERY_STRING": query, "REQUEST_METHOD": "GET"}}.items():
        monkeypatch.setattr(web.ctx, key, value, raising=False)


def test_webpy_handler_renders_the_fastapi_body(monkeypatch, request_context_fixture):
    """Until web.py's handler is retired, both servers render the same page body."""
    request_context_fixture(lang="en")
    query = "q=dogs&page=2"
    response = _solr_response(
        {"name": "Dogs", "subject_type": "subject", "work_count": 1234},
        num_found=250,
    )
    monkeypatch.setattr(worksearch_code, "run_solr_query", MagicMock(return_value=response))
    _webpy_get(monkeypatch, "/search/subjects", query)

    result = worksearch_code.subject_search().GET()

    assert result.title == "dogs - Subject search"  # web.py's layout reads the title from here
    webpy_body = str(result)
    expected = render_jinja_template(
        "search/subjects.html.jinja",
        nav=SearchNav.from_query("/search/subjects", {"q": "dogs", "page": "2"}),
        q="dogs",
        search_response=response,
        commified_num_found=commify(response.num_found),
        page=2,
        total_pages=ceil(response.num_found / 100),
    )
    assert webpy_body == expected
    assert '<a href="/subjects/dogs">Dogs</a>' in webpy_body
    assert "1234 books" in webpy_body


def test_concurrent_requests_each_get_only_their_own_page(site_page_app, webpy_leftovers, fetch_concurrently):
    """The query and search tabs come from this request: never another request's, or web.py's leftovers."""
    n = 12
    with patch("openlibrary.fastapi.search.run_solr_query_async", autospec=True) as solr_mock:
        solr_mock.return_value = _solr_response()
        responses = fetch_concurrently(site_page_app(pages), [(f"/search/subjects?q=query-{i}", {}) for i in range(n)])
    for i, response in enumerate(responses):
        html = response.text
        assert response.status_code == 200
        assert webpy_leftovers not in html
        assert f'value="query-{i}"' in html
        assert f"query-{i} - Subject search" in html
        assert not any(f'value="query-{j}"' in html for j in range(n) if j != i)
