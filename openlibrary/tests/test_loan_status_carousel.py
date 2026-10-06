"""A carousel card always ends in a button. A book that can't be read here gets
one secondary "Learn More" to its page: no Preview Only button, no library
lookup, no "Checked Out" or "Not in Library" status line. Everywhere else the
same lending states keep their own buttons and text.
"""

import pytest
import web
from bs4 import BeautifulSoup

from infogami.utils import macro


def _render(render_template, monkeypatch, lending_state, in_carousel, doc=None):
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
    html = str(render_template("tests/loan_status_carousel_check", doc, lending_state, in_carousel))
    return BeautifulSoup(html, "lxml")


def _learn_more(soup):
    return [b for b in soup.find_all("ol-button") if b.get_text(strip=True) == "Learn More"]


def test_carousel_preview_only_becomes_learn_more(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, "preview_only", in_carousel=True)
    (button,) = _learn_more(soup)
    assert button["href"] == "/works/OL1W"
    assert button["variant"] == "secondary"  # ol-button's secondary, not primary
    assert button.has_attr("full-width")
    assert button["data-ol-link-track"] == "BookCarousel|LearnMoreClick|test"
    assert "bookPreview" not in str(soup)
    assert "action=locate" not in str(soup)


def test_carousel_not_in_library_becomes_learn_more(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, "unavailable", in_carousel=True)
    assert len(_learn_more(soup)) == 1
    assert "action=locate" not in str(soup)
    assert "Check Options" not in str(soup)


def test_outside_a_carousel_the_old_buttons_stay(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    assert not _learn_more(_render(render_template, monkeypatch, "preview_only", in_carousel=False))
    soup = _render(render_template, monkeypatch, "unavailable", in_carousel=False)
    assert not _learn_more(soup)
    assert soup.find("a", string=lambda s: s and "Check Options" in s)["href"] == "/works/OL1W"


@pytest.mark.parametrize("lending_state", ["preview_only", "checkedout", "unavailable"])
def test_carousel_never_shows_a_status_line_instead_of_a_button(render_template, request_context_fixture, monkeypatch, lending_state):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, lending_state, in_carousel=True)
    assert len(_learn_more(soup)) == 1
    assert soup.find(class_="waitinglist-message") is None
    assert "Checked Out" not in soup.get_text()


def test_carousel_work_without_an_edition_gets_learn_more(render_template, request_context_fixture, monkeypatch):
    """A work-level card (no edition, nothing to borrow) used to say "Not in Library"."""
    request_context_fixture(lang="en")
    work = web.storage(key="/works/OL1W", title="A Work", availability={})
    soup = _render(render_template, monkeypatch, "unavailable", in_carousel=True, doc=work)
    assert len(_learn_more(soup)) == 1
    assert "Not in Library" not in soup.get_text()


def test_outside_a_carousel_checked_out_stays_a_status_line(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, "checkedout", in_carousel=False)
    assert not _learn_more(soup)
    assert "Checked Out" in soup.get_text()
