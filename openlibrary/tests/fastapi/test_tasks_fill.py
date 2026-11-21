"""Tests for /tasks/fill, the form a book page's drawer loads for one empty field and posts its answer to."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import web

from openlibrary.contribute import book_page, save
from openlibrary.fastapi.shared.dependencies import get_client_ip

URL = "/tasks/fill/OL1M/publishers"


class FakeEdition(dict):
    key = "/books/OL1M"
    type = web.storage(key="/type/edition")


class FakeSite:
    def __init__(self, edition):
        self.edition = edition

    def get(self, key):
        return self.edition if key == "/books/OL1M" else None


@pytest.fixture
def fill(fastapi_client, mock_authenticated_user):
    """The routes with an edition that has no publisher, and everything below them stubbed. Yields the stubs by name."""
    targets = {
        "site": "openlibrary.fastapi.tasks.site",
        "spam": "openlibrary.fastapi.tasks.spamcheck.is_spam",
        "render": "openlibrary.fastapi.tasks.render_jinja_template",
        "form": "openlibrary.fastapi.tasks.contribute.build_fill_context",
        "done": "openlibrary.fastapi.tasks.contribute.build_fill_done",
        "open": "openlibrary.fastapi.tasks.book_page.open_fields",
        "save": "openlibrary.fastapi.tasks.save.save_answer",
        "notfound": "openlibrary.fastapi.tasks.initiatives.record_not_found",
        "listing": "openlibrary.fastapi.tasks.initiatives.listing",
    }
    patches = {name: patch(target) for name, target in targets.items()}
    stubs = {name: p.start() for name, p in patches.items()}
    stubs["site"].get.return_value = FakeSite(FakeEdition(publish_date="2001"))
    stubs["spam"].return_value = False
    stubs["render"].side_effect = lambda template, **_kw: template
    stubs["open"].return_value = ["languages"]
    stubs["listing"].return_value = None
    # mock_authenticated_user clears the overrides when the test ends.
    fastapi_client.app.dependency_overrides[get_client_ip] = lambda: "203.0.113.7"
    yield stubs
    for p in patches.values():
        p.stop()


def test_the_form_needs_a_signed_in_member(fastapi_client):
    assert fastapi_client.get(URL).status_code == 401
    assert fastapi_client.post(URL, data={"value": "Penguin"}).status_code == 401


def test_a_field_the_book_page_does_not_ask_for_is_not_found(fastapi_client, fill):
    assert "isbn" not in book_page.FIELDS
    assert fastapi_client.get("/tasks/fill/OL1M/isbn").status_code == 404
    assert fastapi_client.get("/tasks/fill/OL2M/publishers").status_code == 404
    assert fastapi_client.get("/tasks/fill/OL1W/publishers").status_code == 422


def test_an_empty_field_gets_its_form(fastapi_client, fill):
    response = fastapi_client.get(URL)
    assert (response.status_code, response.text) == (200, "contribute/fill.html.jinja")
    assert fill["form"].call_args.args[1] == "publishers"


def test_a_field_filled_in_the_meantime_says_so(fastapi_client, fill):
    response = fastapi_client.get("/tasks/fill/OL1M/publish_date")
    assert response.text == "contribute/fill_done.html.jinja"
    assert fill["done"].call_args.args[1:3] == ("publish_date", "filled")
    fastapi_client.post("/tasks/fill/OL1M/publish_date", data={"value": "2002"})
    assert not fill["save"].called


def test_an_answer_saves_as_a_book_page_edit(fastapi_client, fill, mock_authenticated_user):
    response = fastapi_client.post(URL, data={"value": "Penguin", "note": "From the title page"})
    assert (response.status_code, response.text) == (200, "contribute/fill_done.html.jinja")
    assert fill["save"].call_args.args[1:5] == ("publishers", "Penguin", "Publisher", "From the title page")
    assert fill["save"].call_args.kwargs == {"initiative": "", "door": book_page.DOOR}
    assert fill["done"].call_args.args[1:] == ("publishers", "saved", "Penguin", ["languages"])


def test_an_answer_that_cannot_be_stored_hands_the_form_back(fastapi_client, fill):
    fill["save"].side_effect = save.InvalidAnswer("Fill in an answer.")
    response = fastapi_client.post(URL, data={"value": " ", "note": "n"})
    assert (response.status_code, response.text) == (422, "contribute/fill.html.jinja")
    assert fill["form"].call_args.kwargs == {"error": "Fill in an answer.", "value": " ", "note": "n"}


def test_not_found_is_noted_without_an_edit(fastapi_client, fill, mock_authenticated_user):
    response = fastapi_client.post(URL, data={"then": "notfound", "note": "Checked WorldCat"})
    assert response.status_code == 200
    assert fill["notfound"].call_args.args[1:] == ("/books/OL1M", "publishers", mock_authenticated_user.user_key, "Checked WorldCat")
    assert fill["done"].call_args.args[1:3] == ("publishers", "notfound")
    assert not fill["save"].called


def test_a_spam_answer_is_refused(fastapi_client, fill):
    fill["spam"].return_value = True
    assert fastapi_client.post(URL, data={"value": "buy pills"}).status_code == 403
    assert not fill["save"].called
