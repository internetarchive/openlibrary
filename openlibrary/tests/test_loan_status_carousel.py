"""In a carousel, a book that can't be read here gets one secondary "Learn More"
to its page: no Preview Only button, no library lookup. Everywhere else the
same lending states keep their own buttons.
"""

import web
from bs4 import BeautifulSoup

from infogami.utils import macro


def _render(render_template, monkeypatch, lending_state, in_carousel):
    macro.load_macros("openlibrary", lazy=True)
    # Enough request for query_param() at the macro's tail.
    web.ctx.env.update(REQUEST_METHOD="GET", QUERY_STRING="")
    web.ctx.path = web.ctx.fullpath = "/"
    web.ctx.query = ""
    web.template.Template.globals["request"] = web.ctx
    # Neither matters for the branches under test, and the real ones need a request-scoped site.
    monkeypatch.setitem(web.template.Template.globals, "get_current_user", lambda: None)
    monkeypatch.setitem(web.template.Template.globals, "get_book_provider", lambda doc: None)
    doc = web.storage(key="/books/OL1M", title="A Book", ocaid="abook00", availability={})
    html = str(render_template("tests/loan_status_carousel_check", doc, lending_state, in_carousel))
    return BeautifulSoup(html, "lxml")


def _learn_more(soup):
    return [a for a in soup.find_all("a") if a.get_text(strip=True) == "Learn More"]


def test_carousel_preview_only_becomes_learn_more(render_template, request_context_fixture, monkeypatch):
    request_context_fixture(lang="en")
    soup = _render(render_template, monkeypatch, "preview_only", in_carousel=True)
    (link,) = _learn_more(soup)
    assert link["href"] == "/works/OL1W"
    assert "cta-btn--shell" in link["class"]  # secondary, not primary
    assert "cta-btn--available" not in link["class"]
    assert link["data-ol-link-track"] == "BookCarousel|LearnMoreClick|test"
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
