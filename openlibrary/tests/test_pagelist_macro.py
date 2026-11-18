"""`macros/PageList.html.jinja`, the wiki page index embedded in page bodies.

The Templetor macro keeps the request reads (`?path=`, `?page=`, `homepath()`)
and the `list_pages` lookup; this template renders what it is handed.

The `use_repr` branch is gone. The 31 Oct `other` dump has 30 `{{PageList(…)}}`
invocations across 30 pages and not one passes `use_repr` -- or `limit`, or any
second argument at all -- so the branch, and the `thingrepr` call inside it,
were unreachable from the database. See #14387.
"""

from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from openlibrary.core.jinja import get_jinja_env


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
