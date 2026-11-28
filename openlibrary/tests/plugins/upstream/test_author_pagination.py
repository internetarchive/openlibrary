from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import web

from openlibrary.plugins.upstream import code as upstream_code
from openlibrary.plugins.worksearch import code as worksearch_code
from openlibrary.utils.request_context import site as site_context


@pytest.mark.parametrize(
    ("num_found", "page", "rows", "expected_status"),
    [
        (0, 1, None, "200 OK"),
        (0, 2, None, "404 Not Found"),
        (20, 1, None, "200 OK"),
        (20, 2, None, "404 Not Found"),
        (21, 2, None, "200 OK"),
        (40, 2, None, "200 OK"),
        (40, 3, None, "404 Not Found"),
        (None, 2, None, "200 OK"),
        (3, 2, "1", "200 OK"),
        (3, 3, "1", "200 OK"),
        (3, 4, "1", "404 Not Found"),
        (30, 2, "100", "404 Not Found"),
        (40, 2, "abc", "200 OK"),
        (40, 3, "0", "200 OK"),
    ],
)
def test_author_view_returns_404_only_after_last_page(monkeypatch, num_found, page, rows, expected_status):
    author = web.storage(type=web.storage(key="/type/author"), get_olid=Mock(return_value="OL123A"))
    site = SimpleNamespace(get=Mock(return_value=author))
    count_query = Mock(return_value=web.storage(num_found=num_found))
    render_author = Mock(return_value="rendered author page")

    web.ctx.clear()
    web.ctx.site = site
    site_context.set(web.ctx.site)
    web.ctx.status = "200 OK"
    monkeypatch.setattr(web, "input", lambda **kwargs: web.storage(page=str(page), q="query", mode="ebooks", rows=rows))
    monkeypatch.setattr(worksearch_code, "works_by_author", count_query)
    monkeypatch.setattr(upstream_code.core.view, "GET", render_author)

    result = upstream_code.view().GET("/authors/OL123A/Example")

    assert result == "rendered author page"
    assert web.ctx.status == expected_status
    render_author.assert_called_once()
    if page > 1:
        count_query.assert_called_once_with(
            "OL123A",
            rows=0,
            query="query",
            has_fulltext=True,
            facet=False,
            request_label="AUTHOR_BOOKS_PAGE_COUNT",
        )
    else:
        count_query.assert_not_called()


@pytest.fixture(autouse=True)
def restore_site_context():
    token = site_context.set(site_context.get(None))
    yield
    site_context.reset(token)
