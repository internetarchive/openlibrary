"""`macros/Paginate.html`, the prev/next links under a wiki page listing.

The macro had no tests. It reads `?page=`, turns it into a `list_pages` offset,
and decides whether to draw each link -- the same paging arithmetic as
`PageList`, and the same places for an off-by-one to hide.

These were added alongside dropping its unused `use_repr` argument (#14570), so
that the removal is covered by something that would notice if the rest of the
macro moved with it.
"""

from pathlib import Path

import pytest
import web
from bs4 import BeautifulSoup

MACRO = Path("openlibrary/macros/Paginate.html").read_text(encoding="utf-8")


def _render(query: dict[str, str], page_count: int = 0, path: str = "", limit: int = 50):
    """Render the macro, recording how list_pages was called."""
    calls: list[dict] = []

    def list_pages(p, limit, offset):
        calls.append({"path": p, "limit": limit, "offset": offset})
        return [object()] * page_count

    def safeint(value, default=0):
        try:
            return int(value)
        except TypeError, ValueError:
            return default

    # $_.prev / $_.next are infogami i18n lookups, which read web.ctx.lang.
    web.ctx.lang = "en"

    g = dict(web.template.Template.globals)
    g.update(
        query_param=lambda name, default=None: query.get(name, default),
        safeint=safeint,
        list_pages=list_pages,
        changequery=lambda **kw: "?" + "&".join(f"{k}={v}" for k, v in kw.items()),
    )
    template = web.template.Template(MACRO, filename="Paginate.html", globals=g)
    return str(template(path=path, limit=limit)), calls


def _links(html):
    return BeautifulSoup(html, "lxml").find_all("a")


@pytest.mark.parametrize(
    ("page_param", "limit", "expected_offset"),
    [
        (None, 50, 0),
        ("0", 50, 0),
        ("1", 50, 50),
        ("3", 20, 60),
    ],
)
def test_the_page_parameter_becomes_an_offset(request_context_fixture, page_param, limit, expected_offset):
    request_context_fixture(lang="en")
    query = {} if page_param is None else {"page": page_param}

    _, calls = _render(query, limit=limit)

    assert calls == [{"path": "", "limit": limit, "offset": expected_offset}]


def test_a_non_numeric_page_falls_back_to_the_first_page(request_context_fixture):
    request_context_fixture(lang="en")

    _, calls = _render({"page": "abc"})

    assert calls[0]["offset"] == 0


def test_the_path_is_passed_through(request_context_fixture):
    request_context_fixture(lang="en")

    _, calls = _render({}, path="/templates")

    assert calls[0]["path"] == "/templates"


def test_the_first_page_has_no_previous_link(request_context_fixture):
    request_context_fixture(lang="en")

    html, _ = _render({"page": "0"}, page_count=50)

    assert [a["href"] for a in _links(html)] == ["?page=1"]


def test_a_later_page_links_back_one_page(request_context_fixture):
    request_context_fixture(lang="en")

    html, _ = _render({"page": "2"}, page_count=50)

    assert [a["href"] for a in _links(html)] == ["?page=1", "?page=3"]


def test_a_short_last_page_has_no_next_link(request_context_fixture):
    """A full page means there may be more; a short one means there is not."""
    request_context_fixture(lang="en")

    html, _ = _render({"page": "1"}, page_count=49)

    assert [a["href"] for a in _links(html)] == ["?page=0"]


def test_an_empty_first_page_has_no_links_at_all(request_context_fixture):
    request_context_fixture(lang="en")

    html, _ = _render({}, page_count=0)

    assert _links(html) == []
