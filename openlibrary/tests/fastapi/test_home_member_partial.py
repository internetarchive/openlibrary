"""Tests for the home page's signed-in section (HomeMember partial)."""

from unittest.mock import patch

import web


def _home_member():
    # Imported lazily: importing the plugin at collection time hits a circular import.
    from openlibrary.plugins.openlibrary import home_member  # noqa: PLC0415

    return home_member


def _book(title: str, **extra) -> dict:
    return {"title": title, "author": "", "url": f"/works/{title}", "cover_url": ""} | extra


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
    agenda = _home_member().build_agenda(loans=[], holds=[_hold("ready", ready=True)], reading=[_book("first"), _book("second")])
    assert [card["title"] for card in agenda] == ["first", "ready", "second"]
    assert agenda[0]["action"]["form"] is None


def test_want_available_keeps_only_copies_free_now(request_context_fixture):
    request_context_fixture(lang="en")
    docs = [
        web.storage(key="/works/OL1W", title="free", editions={"docs": [{"key": "/books/OL1M"}]}),
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
    # The card must draw the work, whose availability names the free copy, not the logged edition.
    assert "editions" not in free[0]
