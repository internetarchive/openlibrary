"""Tests for the home page's signed-in section (HomeMember partial)."""

from unittest.mock import patch

import web


def _home_member():
    # Imported lazily: importing the plugin at collection time hits a circular import.
    from openlibrary.plugins.openlibrary import home_member  # noqa: PLC0415

    return home_member


def _book(title: str, **extra) -> dict:
    return {"title": title, "author": "", "url": f"/works/{title}", "cover_url": "", "thumb_url": ""} | extra


def _loan(title: str, days_left: int) -> dict:
    return _book(title, ocaid=f"ia_{title}", can_read_here=True, days_left=days_left, due=f"due in {days_left}", urgent=days_left <= 2)


def _hold(title: str, *, ready: bool) -> dict:
    return _book(title, ready=ready, borrow_url=f"/books/{title}/borrow", note=f"note for {title}")


def test_logged_out_renders_nothing(fastapi_client):
    response = fastapi_client.get("/partials/HomeMember.json")
    assert response.status_code == 200
    assert response.json() == {"partials": ""}


def test_agenda_leads_with_the_loan_then_what_has_a_clock(request_context_fixture):
    request_context_fixture(lang="en")
    agenda = _home_member().build_agenda(
        loans=[_loan("soon", 1), _loan("later", 9)],
        holds=[_hold("waiting", ready=False), _hold("ready", ready=True)],
        reading=[_book("shelf")],
    )
    assert [(card["title"], card["kind"]) for card in agenda] == [
        ("soon", "loan"),
        ("ready", "ready"),
        ("later", "loan"),
        ("shelf", "reading"),
        ("waiting", "waiting"),
    ]
    assert agenda[0]["tone"] == "urgent"
    assert agenda[0]["action"]["form"] == {"action": "/borrow/ia/ia_soon", "value": "read"}
    assert agenda[1]["action"]["form"] == {"action": "/books/ready/borrow", "value": "borrow"}


def test_agenda_without_a_loan_leads_with_currently_reading(request_context_fixture):
    request_context_fixture(lang="en")
    agenda = _home_member().build_agenda(loans=[], holds=[_hold("ready", ready=True)], reading=[_book("first", cta="<read>"), _book("second")])
    assert [card["title"] for card in agenda] == ["first", "ready", "second"]
    # A Currently Reading book has no button or status of ours, only what the shelf gave it.
    assert agenda[0]["action"] is None
    assert agenda[0]["status"] == ""
    assert agenda[0]["cta"] == "<read>"
    assert agenda[2]["cta"] == ""


def test_agenda_without_a_loan_leads_with_a_book_that_has_a_free_copy(request_context_fixture):
    request_context_fixture(lang="en")
    reading = [_book("newest"), _book("free", cta="<borrow>"), _book("also free", cta="<borrow>"), _book("oldest")]
    agenda = _home_member().build_agenda(loans=[], holds=[], reading=reading)
    assert [card["title"] for card in agenda] == ["free", "newest", "also free", "oldest"]
    # With no free copy anywhere the shelf order stands.
    agenda = _home_member().build_agenda(loans=[], holds=[], reading=[_book("newest"), _book("oldest")])
    assert [card["title"] for card in agenda] == ["newest", "oldest"]


def test_reading_now_offers_a_button_only_for_a_free_copy(request_context_fixture):
    request_context_fixture(lang="en")
    docs = [
        web.storage(key="/works/OL1W", title="free", editions={"docs": [{"key": "/books/OL1M"}]}),
        web.storage(key="/works/OL9W"),  # not in search: no title, dropped
        web.storage(key="/works/OL2W", title="out"),
    ]
    statuses = {"free": "borrow_available", "out": "borrow_unavailable"}

    def add_availability(items):
        for item in items:
            item["availability"] = {"status": statuses[item["title"]]}

    class ReadLog:
        def get_works(self, key, limit):
            assert (key, limit) == ("currently-reading", 6)
            return web.storage(docs=docs)

    with (
        patch("openlibrary.core.lending.add_availability", side_effect=add_availability),
        patch("openlibrary.plugins.openlibrary.partials._render_carousel_card_loan_status", side_effect=lambda book, **kw: f"<{kw['layout']}>") as cta,
        patch("openlibrary.plugins.upstream.mybooks.shelf_button_for", side_effect=lambda doc, **kw: f"<shelf {kw.get('size')}>"),
    ):
        books = _home_member().reading_now(ReadLog())

    assert [(b["title"], b["cta"], b["cta_small"]) for b in books] == [("free", "<None>", "<ol-carousel>"), ("out", "", "")]
    assert [(b["shelf"], b["shelf_small"]) for b in books] == [("<shelf None>", "<shelf small>")] * 2
    # The button is for the work, whose availability names the free copy, not the edition the reader logged.
    assert "editions" not in cta.call_args.args[0]


def test_want_available_keeps_only_copies_free_now(request_context_fixture):
    request_context_fixture(lang="en")
    docs = [
        web.storage(key="/works/OL1W", title="free"),
        web.storage(key="/works/OL2W", title="out"),
        web.storage(key="/works/OL3W", title="open"),
        web.storage(key="/works/OL4W", title="unknown"),
    ]
    statuses = {"free": "borrow_available", "out": "borrow_unavailable", "open": "open", "unknown": "error"}

    def add_availability(items):
        for item in items:
            item["availability"] = {"status": statuses[item["title"]]}

    class ReadLog:
        def get_works(self, key, limit, fq):
            assert key == "want-to-read"
            return web.storage(docs=docs)

    with patch("openlibrary.core.lending.add_availability", side_effect=add_availability):
        free = _home_member().want_available(ReadLog())

    assert [doc["title"] for doc in free] == ["free", "open"]


def test_generate_keeps_the_request_context(request_context_fixture):
    """Replacing it from the bare web.ctx marks the request a bot, and availability then skips the real check."""
    from openlibrary.plugins.openlibrary import partials  # noqa: PLC0415
    from openlibrary.utils.request_context import req_context  # noqa: PLC0415

    request_context_fixture(lang="en", is_bot=False)
    before = req_context.get()
    with (
        patch.object(partials.delegate, "fakeload"),
        patch.object(partials.home_member, "get_cached_html", return_value=None),
        patch.object(partials, "get_user_object", return_value=None),
    ):
        assert partials.HomeMemberPartial.generate("someone") == {"partials": ""}
    assert req_context.get() is before


def test_cached_section_is_served_until_the_shelves_change(request_context_fixture):
    request_context_fixture(lang="en")
    home_member = _home_member()
    store: dict = {}

    class Memcache:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, expires=0):
            store[key] = value

        def delete(self, key):
            store.pop(key, None)

    version = ["v1"]
    with (
        patch.object(home_member.cache, "get_memcache", return_value=Memcache()),
        patch.object(home_member.Bookshelves, "reading_log_version", side_effect=lambda username: version[0]),
    ):
        assert home_member.get_cached_html("reader") is None
        home_member.cache_html("reader", "<section>")
        assert home_member.get_cached_html("reader") == "<section>"
        version[0] = "v2"  # a book was shelved
        assert home_member.get_cached_html("reader") is None
        home_member.cache_html("reader", "<new>")
        home_member.invalidate_cache("reader")  # a borrow or return
        assert home_member.get_cached_html("reader") is None
