"""Off the book page a book always ends in a button. One that can't be read
here gets one secondary "Learn More" to its page: no Preview Only button, no
Check Options, no library lookup, no "Checked Out" or "Not in Library" status
line. That holds for carousel cards, search results (list and grid), lists and
the reading log alike. The book page keeps its own buttons and text.
"""

import pytest
import web
from bs4 import BeautifulSoup

from infogami.utils import macro


def _render(render_template, monkeypatch, lending_state, book_page=False, doc=None):
    macro.load_macros("openlibrary", lazy=True)
    # Enough request for query_param() at the macro's tail.
    web.ctx.env.update(REQUEST_METHOD="GET", QUERY_STRING="")
    web.ctx.path = web.ctx.fullpath = "/"
    web.ctx.query = ""
    web.template.Template.globals["request"] = web.ctx
    # Neither matters for the branches under test, and the real ones need a request-scoped site.
    monkeypatch.setitem(web.template.Template.globals, "get_current_user", lambda: None)
    monkeypatch.setitem(web.template.Template.globals, "get_book_provider", lambda doc: None)
    doc = doc or web.storage(key="/books/OL1M", title="A Book", ocaid="abook00", availability={})
    html = str(render_template("tests/loan_status_learn_more_check", doc, lending_state, book_page))
    return BeautifulSoup(html, "lxml")


def _learn_more(soup):
    return [b for b in soup.find_all("ol-button") if b.get_text(strip=True) == "Learn More"]


def test_preview_only_becomes_learn_more(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, "preview_only")
    (button,) = _learn_more(soup)
    assert button["href"] == "/works/OL1W"
    assert button["variant"] == "secondary"  # ol-button's secondary, not primary
    assert button.has_attr("full-width")
    assert button["data-ol-link-track"] == "BookCarousel|LearnMoreClick|test"
    assert "bookPreview" not in str(soup)
    assert "Preview Only" not in soup.get_text()
    assert "action=locate" not in str(soup)


def test_edition_not_in_library_becomes_learn_more(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, "unavailable")
    assert len(_learn_more(soup)) == 1
    assert "action=locate" not in str(soup)
    assert "Check Options" not in soup.get_text()


@pytest.mark.parametrize("lending_state", ["preview_only", "checkedout", "unavailable"])
def test_a_listing_never_shows_a_status_line_instead_of_a_button(render_template, request_context_fixture, monkeypatch, lending_state):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, lending_state)
    assert len(_learn_more(soup)) == 1
    assert soup.find(class_="waitinglist-message") is None
    assert "Checked Out" not in soup.get_text()


def test_work_without_an_edition_gets_learn_more(render_template, request_context_fixture, monkeypatch):
    """A work-level entry (no edition, nothing to borrow) used to say "Not in Library"."""
    request_context_fixture(lang="en")
    work = web.storage(key="/works/OL1W", title="A Work", availability={})
    soup = _render(render_template, monkeypatch, "unavailable", doc=work)
    assert len(_learn_more(soup)) == 1
    assert "Not in Library" not in soup.get_text()


def test_book_page_preview_only_keeps_the_library_lookup(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, "preview_only", book_page=True)
    assert not _learn_more(soup)
    assert "action=locate" in str(soup)
    assert "Only a preview is available." in soup.get_text()


def test_book_page_unavailable_edition_keeps_the_library_lookup(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, "unavailable", book_page=True)
    assert not _learn_more(soup)
    assert "action=locate" in str(soup)


def test_book_page_checked_out_keeps_its_note(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, "checkedout", book_page=True)
    assert not _learn_more(soup)
    assert "All copies are checked out." in soup.get_text()


def test_book_page_work_without_an_edition_stays_a_status_line(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    work = web.storage(key="/works/OL1W", title="A Work", availability={})
    soup = _render(render_template, monkeypatch, "unavailable", book_page=True, doc=work)
    assert not _learn_more(soup)
    assert "Not in Library" in soup.get_text()
