"""`/search/inside` HTML page on FastAPI.

It renders `search/inside.html.jinja`; the web.py handler still serves the path
in production and renders the same body through `render_inside_body`. The shell
around the page is tested in `test_site_page.py` and the JSON API in
`test_search.py`; these test the page's own body and inputs.
"""

import re
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import web
from fastapi.testclient import TestClient
from markupsafe import Markup

from openlibrary.core.fulltext import FulltextRow, Snippet
from openlibrary.fastapi.search import pages
from openlibrary.plugins.inside import code as inside_code


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def _fts_response(*ocaids: str, total: int | None = None, error: str = "", all_words_fallback: bool = False) -> dict:
    """An FTS response envelope: `fulltext_page` keeps `hits.hits[].fields.identifier`."""
    if error:
        return {"error": error}
    data: dict = {
        "hits": {
            "hits": [{"fields": {"identifier": [ocaid]}, "highlight": {"text": ["a {{{passage}}} here"]}} for ocaid in ocaids],
            "total": total if total is not None else len(ocaids),
        }
    }
    if all_words_fallback:
        data["all_words_fallback"] = True
    return data


def patched_search(stack: ExitStack, data: dict, rows: tuple[str, ...] = ('<li class="searchResultItem">ROW</li>',)) -> tuple[AsyncMock, MagicMock]:
    """Patch the FTS call and the Templetor row bridge; the bridge has its own test."""
    fts = stack.enter_context(patch("openlibrary.fastapi.search.fulltext_search_async", new_callable=AsyncMock))
    fts.return_value = data
    rows_mock = stack.enter_context(patch("openlibrary.plugins.inside.code.render_hit_rows", autospec=True))
    rows_mock.return_value = [Markup(row) for row in rows]
    return fts, rows_mock


def test_inside_page_without_query(client):
    with ExitStack() as stack:
        fts, rows = patched_search(stack, _fts_response())
        response = client.get("/search/inside")

    assert response.status_code == 200
    html = response.text
    assert "<title>Search Open Library for" in html
    assert 'action="/search/inside"' in html
    # The search tabs
    assert 'data-ol-link-track="SearchNav|SearchFulltext"' in html
    # Without a query there is nothing to search, so no stats and no results
    assert "search-results-stats" not in html
    assert "searchResults" not in html
    fts.assert_not_awaited()
    rows.assert_not_called()


def test_inside_page_title_and_searchbox_escape_the_query(client):
    with ExitStack() as stack:
        patched_search(stack, _fts_response())
        response = client.get("/search/inside?q=pokemon+%3Cstuff%3E")

    assert response.status_code == 200
    html = response.text
    assert "<title>Search Open Library for pokemon &lt;stuff&gt; | Open Library</title>" in html
    assert 'value="pokemon &lt;stuff&gt;"' in html


def test_inside_page_results(client):
    with ExitStack() as stack:
        fts, rows = patched_search(
            stack,
            _fts_response("a", "b", total=45),
            rows=('<li class="searchResultItem">first</li>', '<li class="searchResultItem">second</li>'),
        )
        response = client.get("/search/inside?q=dogs")

    assert response.status_code == 200
    html = response.text
    assert "first" in html
    assert "second" in html
    assert html.count('class="searchResultItem"') == 2
    assert "1 - 2 of about 45 results" in html
    # One page per 20 hits
    assert 'total-pages="3"' in html
    assert 'current-page="1"' in html
    fts.assert_awaited_once_with("dogs", page=1, limit=20, facets=False, readable=False, language=None, phrase=True)
    rows.assert_called_once()
    # The snippets search for the phrase FTS was sent; no reader, so no reading states
    assert rows.call_args.args[1] == '"dogs"'
    assert rows.call_args.args[2] is None


def test_inside_page_single_hit_uses_the_singular_form(client):
    with ExitStack() as stack:
        patched_search(stack, _fts_response("a", total=1))
        response = client.get("/search/inside?q=dogs")

    assert "1 - 1 of about 1 result" in response.text


def test_inside_page_shows_the_bare_total_when_filtered(client):
    with ExitStack() as stack:
        stack.enter_context(patch("openlibrary.fastapi.search.resolve_language", return_value=("fre", "French")))
        fts, _ = patched_search(stack, _fts_response("a", total=45))
        response = client.get("/search/inside?q=dogs&language=fre&readable=true")

    html = response.text
    # A filtered total counts hits the page dropped, so a "1 - 20 of" range would skip numbers
    assert "About 45 results" in html
    assert "of about 45" not in html
    # Both filters ride along in the form, so a new search keeps them
    assert '<input type="hidden" name="language" value="fre">' in html
    assert '<input type="hidden" name="readable" value="true">' in html
    fts.assert_awaited_once()
    assert fts.await_args.kwargs["readable"] is True
    # FTS takes the language name, not the MARC code
    assert fts.await_args.kwargs["language"] == "French"


def test_inside_page_respects_page_param(client):
    with ExitStack() as stack:
        fts, _ = patched_search(stack, _fts_response("a", total=45))
        response = client.get("/search/inside?q=dogs&page=3")

    assert response.status_code == 200
    assert 'current-page="3"' in response.text
    assert fts.await_args.kwargs["page"] == 3


def test_inside_page_clamps_page_below_one(client):
    with ExitStack() as stack:
        fts, _ = patched_search(stack, _fts_response("a", total=45))
        response = client.get("/search/inside?q=dogs&page=-3")

    assert response.status_code == 200
    assert 'current-page="1"' in response.text
    assert fts.await_args.kwargs["page"] == 1


def test_inside_page_rejects_a_non_numeric_page(client):
    # Unlike web.py, which read it as page 1, FastAPI validates it: a clean 422, not a 500.
    response = client.get("/search/inside?q=dogs&page=abc")

    assert response.status_code == 422


def test_inside_page_no_results(client):
    with ExitStack() as stack:
        patched_search(stack, _fts_response())
        response = client.get("/search/inside?q=zzzzz")

    assert response.status_code == 200
    assert "No results found. Try a different word or phrase." in response.text
    assert "searchResults" not in response.text


def test_inside_page_filtered_out(client):
    with ExitStack() as stack:
        stack.enter_context(patch("openlibrary.fastapi.search.resolve_language", return_value=("fre", "French")))
        patched_search(stack, _fts_response(total=45))
        response = client.get("/search/inside?q=dogs&language=fre")

    assert "None of the matches on this page can be shown with these filters." in response.text


def test_inside_page_past_end(client):
    with ExitStack() as stack:
        patched_search(stack, _fts_response(total=45))
        response = client.get("/search/inside?q=dogs&page=9")

    assert "No more results. Try an earlier page." in response.text


def test_inside_page_solr_error(client):
    with ExitStack() as stack:
        patched_search(stack, _fts_response(error="first problem\nsecond problem"))
        response = client.get("/search/inside?q=broken")

    assert response.status_code == 200
    assert "first problem" in response.text
    assert "second problem" in response.text
    assert 'id="searchResults"' not in response.text


def test_inside_page_phrase_link_keeps_the_filters(client):
    with ExitStack() as stack:
        stack.enter_context(patch("openlibrary.fastapi.search.resolve_language", return_value=("spa", "Spanish")))
        patched_search(stack, _fts_response("a", total=3))
        html = client.get("/search/inside?q=argentina+brazil&page=2&language=spa").text

    assert "Showing exact matches for" in html
    # `page` is dropped, the filters are kept, and the query is quoted for FTS
    assert 'href="/search/inside?q=argentina+brazil&amp;language=spa&amp;phrase=false"' in html


def test_inside_page_opted_out_links_back_to_the_phrase(client):
    with ExitStack() as stack:
        patched_search(stack, _fts_response("a", total=3))
        html = client.get("/search/inside?q=argentina+brazil&phrase=false").text

    assert "Showing all of these words, in any order." in html
    assert 'href="/search/inside?q=argentina+brazil"' in html


def test_inside_page_fallback_note(client):
    with ExitStack() as stack:
        patched_search(stack, _fts_response("a", total=3, all_words_fallback=True))
        html = client.get("/search/inside?q=argentina+brazil").text

    # The shell has strings of its own, so look at the page's note rather than the whole document.
    notes = re.findall(r'<span class="search-results-stats__note">(.*?)</span>', html, re.DOTALL)
    assert len(notes) == 1
    assert "No exact matches for" in notes[0]
    assert "Showing books containing all of these words." in notes[0]


def test_inside_page_escapes_the_query_in_the_note(client):
    with ExitStack() as stack:
        patched_search(stack, _fts_response("a", total=3, all_words_fallback=True))
        html = client.get("/search/inside?q=%22%3E%3Cscript%3E+words").text

    # The shell has <script> tags of its own; the query must not become one.
    assert '"><script>' not in html
    assert "&#34;&gt;&lt;script&gt; words" in html


def test_concurrent_requests_each_get_only_their_own_page(site_page_app, webpy_leftovers, fetch_concurrently):
    """The query, the tabs and the results come from this request: never another request's."""
    n = 12
    with ExitStack() as stack:
        fts = stack.enter_context(patch("openlibrary.fastapi.search.fulltext_search_async", new_callable=AsyncMock))
        fts.side_effect = lambda q, **kwargs: _fts_response(f"{q}-ocaid", total=1)
        rows = stack.enter_context(patch("openlibrary.plugins.inside.code.render_hit_rows", autospec=True))
        rows.side_effect = lambda hits, phrase, user: [Markup(f"<li>{hit.ocaid}</li>") for hit in hits]
        responses = fetch_concurrently(site_page_app(pages), [(f"/search/inside?q=query-{i}", {}) for i in range(n)])

    for i, response in enumerate(responses):
        html = response.text
        assert response.status_code == 200
        assert webpy_leftovers not in html
        assert f'value="query-{i}"' in html
        assert f"<li>query-{i}-ocaid</li>" in html
        assert not any(f"<li>query-{j}-ocaid</li>" in html for j in range(n) if j != i)


def test_render_hit_rows_bridges_the_templetor_row_with_the_readers_shelf_state(monkeypatch, request_context_fixture):
    """The row macro stays Templetor, so this is the contract that keeps it right under FastAPI."""
    request_context_fixture(lang="en")
    edition = {"key": "/books/OL1M"}
    rows = [
        FulltextRow(ocaid="a", snippets=[Snippet([("passage", True)])], edition=edition, availability={"status": "borrowable"}),
        FulltextRow(ocaid="b", snippets=[], title="No OL record"),
    ]
    states = {"/works/OL1W": {"shelf": "want_to_read"}}
    reading_states = MagicMock(return_value=states)
    macro = MagicMock(return_value={"__body__": "<li>edition row</li>"})
    monkeypatch.setattr(inside_code, "get_reading_states", reading_states)
    monkeypatch.setattr(inside_code, "render_macro", macro)

    rendered = inside_code.render_hit_rows(rows, '"rabbit"', user=object())

    # One reading-state lookup for the page, passed into the row
    reading_states.assert_called_once()
    assert reading_states.call_args.args[1] == [edition]
    assert macro.call_args.args == ("SearchResultsWork", (edition,))
    assert macro.call_args.kwargs["include_dropper"] is True
    assert macro.call_args.kwargs["reading_states"] == states
    assert macro.call_args.kwargs["availability"] == {"status": "borrowable"}
    assert macro.call_args.kwargs["seq_index"] == 0
    assert macro.call_args.kwargs["show_title_year"] is True
    # The snippet's BookReader link searches for the phrase FTS was sent
    assert "q=%22rabbit%22" in macro.call_args.kwargs["extra_row"]
    assert rendered[0] == "<li>edition row</li>"
    # A hit with no OL edition still renders, from its IA metadata
    assert 'href="https://archive.org/details/b?' in str(rendered[1])


def _webpy_get(monkeypatch, path: str, query: str) -> None:
    for key, value in {"path": path, "query": "?" + query, "env": {"QUERY_STRING": query, "REQUEST_METHOD": "GET"}}.items():
        monkeypatch.setattr(web.ctx, key, value, raising=False)


def test_webpy_handler_renders_the_fastapi_body(monkeypatch, request_context_fixture, client):
    """Until web.py's handler is retired, both servers render the same page body."""
    request_context_fixture(lang="en")
    query = "q=rabbit&page=2&readable=true"
    _webpy_get(monkeypatch, "/search/inside", query)
    # No site in this test, so neither handler has a reader to look up.
    monkeypatch.setattr(inside_code, "get_current_user", lambda: None)
    with ExitStack() as stack:
        fts = stack.enter_context(patch("openlibrary.plugins.inside.code.fulltext_search_async", new_callable=AsyncMock))
        fts.return_value = _fts_response("a", total=45)
        rows = stack.enter_context(patch("openlibrary.plugins.inside.code.render_hit_rows", autospec=True))
        rows.return_value = [Markup('<li class="searchResultItem">row</li>')]
        result = inside_code.search_inside().GET()

    assert result.title == "Search Open Library for rabbit"  # web.py's layout reads the title from here
    webpy_body = str(result)
    # readable is a filter, so the total is shown bare rather than as a range
    assert "About 45 results" in webpy_body
    assert 'value="rabbit"' in webpy_body

    with ExitStack() as stack:
        patched_search(stack, _fts_response("a", total=45), rows=('<li class="searchResultItem">row</li>',))
        response = client.get("/search/inside?" + query)

    assert response.status_code == 200
    assert webpy_body in response.text
