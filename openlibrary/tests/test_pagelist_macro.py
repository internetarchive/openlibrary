"""`macros/PageList.html.jinja`, the wiki page index embedded in page bodies.

The Templetor macro keeps the request reads (`?path=`, `?page=`, `homepath()`)
and the `list_pages` lookup; this template renders what it is handed.

The `use_repr` branch is gone. The 31 Oct `other` dump has 30 `{{PageList(…)}}`
invocations across 30 pages and not one passes `use_repr` -- or `limit`, or any
second argument at all -- so the branch, and the `thingrepr` call inside it,
were unreachable from the database. See #14387.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import web
from bs4 import BeautifulSoup

from openlibrary.core.jinja import get_jinja_env, render_jinja_template


def page(key: str, type_key: str = "/type/page") -> SimpleNamespace:
    return SimpleNamespace(key=key, type=SimpleNamespace(key=type_key))


def _render(pages, homepath: str = "") -> str:
    template = get_jinja_env().get_template("PageList.html.jinja")
    return str(template.module.page_list(pages, homepath))


def _links(pages, homepath: str = ""):
    return BeautifulSoup(_render(pages, homepath), "lxml").find_all("a")


def test_each_page_becomes_a_link():
    links = _links([page("/about"), page("/docs")])

    assert [a["href"] for a in links] == ["/about", "/docs"]
    assert [a.text.strip() for a in links] == ["/about", "/docs"]


def test_homepath_prefixes_the_href_but_not_the_text():
    (link,) = _links([page("/about")], homepath="/fr")

    assert link["href"] == "/fr/about"
    assert link.text.strip() == "/about"


def test_deleted_pages_are_skipped():
    links = _links([page("/kept"), page("/gone", "/type/delete"), page("/also-kept")])

    assert [a["href"] for a in links] == ["/kept", "/also-kept"]


def test_an_empty_list_still_renders_the_list_element():
    html = _render([])

    assert BeautifulSoup(html, "lxml").find("ul") is not None
    assert BeautifulSoup(html, "lxml").find("a") is None


def test_the_islist_marker_is_kept():
    """Template bodies are scanned for this marker; it is not decoration."""
    assert "<!--islist-->" in _render([page("/about")])


@pytest.mark.parametrize(
    "key",
    [
        '/x" onmouseover=alert(1) q="',
        "/<script>alert(1)</script>",
        "/a&b",
    ],
)
def test_a_page_key_cannot_inject_markup(key):
    """Keys come from the database, which librarians can create."""
    (link,) = _links([page(key)])

    assert link.get("onmouseover") is None
    assert link["href"] == key
    assert link.text.strip() == key
    assert BeautifulSoup(_render([page(key)]), "lxml").find("script") is None


# ---------------------------------------------------------------------------
# The Templetor wrapper. The tests above hand `pages` straight to the Jinja
# macro, which leaves the half that actually reads the request untested: the
# ?path=/?page= reads and the offset = page * limit arithmetic. That is the
# part with somewhere to hide an off-by-one or a crash on a non-numeric page,
# so drive the real macro file here. Raised by the review bot on #14568.
# ---------------------------------------------------------------------------

WRAPPER = Path("openlibrary/macros/PageList.html").read_text(encoding="utf-8")


def _render_wrapper(query: dict[str, str], pages=(), path="", limit=500):
    """Render macros/PageList.html, recording how list_pages was called."""
    calls: list[dict] = []

    def list_pages(p, limit, offset):
        calls.append({"path": p, "limit": limit, "offset": offset})
        return list(pages)

    def safeint(value, default=0):
        try:
            return int(value)
        except TypeError, ValueError:
            return default

    g = dict(web.template.Template.globals)
    g.update(
        query_param=lambda name, default=None: query.get(name, default),
        safeint=safeint,
        list_pages=list_pages,
        homepath=lambda: "",
        render_jinja_template=render_jinja_template,
    )
    template = web.template.Template(WRAPPER, filename="PageList.html", globals=g)
    return str(template(path=path, limit=limit)), calls


@pytest.mark.parametrize(
    ("page_param", "limit", "expected_offset"),
    [
        (None, 500, 0),  # no ?page=
        ("0", 500, 0),
        ("1", 500, 500),
        ("3", 50, 150),
    ],
)
def test_the_page_parameter_becomes_an_offset(page_param, limit, expected_offset):
    query = {} if page_param is None else {"page": page_param}

    _, calls = _render_wrapper(query, limit=limit)

    assert calls == [{"path": "", "limit": limit, "offset": expected_offset}]


def test_a_non_numeric_page_falls_back_to_the_first_page():
    """`?page=abc` must not raise; safeint is why."""
    _, calls = _render_wrapper({"page": "abc"})

    assert calls[0]["offset"] == 0


def test_the_path_query_parameter_overrides_the_argument():
    _, calls = _render_wrapper({"path": "/from-query"}, path="/from-argument")

    assert calls[0]["path"] == "/from-query"


def test_the_path_argument_is_used_when_the_query_has_none():
    _, calls = _render_wrapper({}, path="/from-argument")

    assert calls[0]["path"] == "/from-argument"


def test_the_wrapper_renders_the_pages_it_fetched():
    """End to end: Templetor wrapper -> render_jinja_template -> the macro."""
    html, _ = _render_wrapper({}, pages=[page("/about"), page("/gone", "/type/delete")])

    links = BeautifulSoup(html, "lxml").find_all("a")
    assert [a["href"] for a in links] == ["/about"]
    assert "<!--islist-->" in html
