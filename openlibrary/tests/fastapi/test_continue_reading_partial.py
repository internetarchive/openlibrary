"""Tests for the homepage Continue Reading partial."""

import threading
import time
from unittest.mock import patch

import web

DAY = 86400


def _partials():
    # Imported lazily: importing the plugin at collection time hits a circular import.
    from openlibrary.plugins.openlibrary import partials  # noqa: PLC0415

    return partials


def _entry(title: str, *, active: bool, age_days: float):
    from openlibrary.plugins.upstream.mybooks import LoanEntry  # noqa: PLC0415

    book = web.storage(key=f"/books/{title}", title=title, ocaid=f"ia_{title}", cover_i=1)
    book.loan = {"ocaid": book.ocaid, "expiry": None}
    return LoanEntry(book, time.time() - age_days * DAY, active)


def test_logged_out_renders_nothing(fastapi_client):
    response = fastapi_client.get("/partials/ContinueReading.json")
    assert response.status_code == 200
    assert response.json() == {"partials": ""}


def test_keeps_active_loans_and_only_recent_returns(request_context_fixture):
    request_context_fixture(lang="en")
    entries = [_entry("active", active=True, age_days=30), _entry("recent", active=False, age_days=3), _entry("old", active=False, age_days=20)]
    with (
        patch("openlibrary.plugins.openlibrary.partials.render_jinja_template", side_effect=lambda _t, items: items) as render,
        patch("openlibrary.plugins.openlibrary.partials._render_carousel_card_loan_status", return_value="<button>") as loan_status,
    ):
        _partials().ContinueReadingPartial._render(entries)

    assert [item["title"] for item in render.call_args.kwargs["items"]] == ["active", "recent"]
    assert [item["book_url"] for item in render.call_args.kwargs["items"]] == ["/books/active", "/books/recent"]
    # The active loan reaches LoanStatus with its loan attached, so it renders Read.
    assert loan_status.call_args_list[0].args[0].loan["ocaid"] == "ia_active"


def test_caps_items(request_context_fixture):
    request_context_fixture(lang="en")
    ContinueReadingPartial = _partials().ContinueReadingPartial
    entries = [_entry(str(i), active=True, age_days=0) for i in range(20)]
    with (
        patch("openlibrary.plugins.openlibrary.partials.render_jinja_template", return_value="<html>") as render,
        patch("openlibrary.plugins.openlibrary.partials._render_carousel_card_loan_status", return_value="<button>"),
    ):
        ContinueReadingPartial._render(entries)

    assert len(render.call_args.kwargs["items"]) == ContinueReadingPartial.MAX_ITEMS


def test_no_loans_renders_nothing():
    assert _partials().ContinueReadingPartial._render([]) == {"partials": ""}


def test_loan_due_status(request_context_fixture):
    request_context_fixture(lang="en")
    _loan_due_status = _partials()._loan_due_status
    assert _loan_due_status(None) == "Borrowed"
    assert _loan_due_status(30 * 60) == "Due in 30 minutes"
    assert _loan_due_status(5 * 3600) == "Due in 5 hours"
    assert _loan_due_status(1 * DAY + 60) == "Due in 1 day"


def test_generate_sets_up_web_ctx_on_a_fresh_thread():
    # FastAPI runs the sync handler on a worker thread with no web.ctx.env,
    # which the LoanStatus macro's query_param() reads.
    seen = {}

    def run():
        with (
            patch("openlibrary.plugins.openlibrary.partials.get_loans_and_history", return_value=[]),
            patch("openlibrary.plugins.openlibrary.partials.delegate.fakeload", side_effect=lambda: web.ctx.update(env={})) as fakeload,
        ):
            _partials().ContinueReadingPartial.generate("u", "/people/u", None)
        seen["fakeloaded"] = fakeload.called
        seen["env"] = "env" in web.ctx

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    assert seen == {"fakeloaded": True, "env": True}
