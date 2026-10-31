from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import web

from openlibrary.plugins.upstream import code as upstream_code
from openlibrary.plugins.worksearch import code as worksearch_code


@pytest.mark.parametrize(
    ("num_found", "page", "expected_status"),
    [
        (0, 1, "200 OK"),
        (0, 2, "404 Not Found"),
        (20, 1, "200 OK"),
        (20, 2, "404 Not Found"),
        (21, 2, "200 OK"),
        (40, 2, "200 OK"),
        (40, 3, "404 Not Found"),
        (None, 2, "200 OK"),
    ],
)
def test_author_view_returns_404_only_after_last_page(monkeypatch, num_found, page, expected_status):
    author = web.storage(type=web.storage(key="/type/author"), get_olid=Mock(return_value="OL123A"))
    site = SimpleNamespace(get=Mock(return_value=author))
    count_query = Mock(return_value=web.storage(num_found=num_found))
    render_author = Mock(return_value="rendered author page")

    web.ctx.clear()
    web.ctx.site = site
    web.ctx.status = "200 OK"
    monkeypatch.setattr(web, "input", lambda **kwargs: web.storage(page=str(page), q="query", mode="ebooks"))
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
