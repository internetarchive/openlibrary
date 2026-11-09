from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import web

from openlibrary.contribute.tasks import Task
from openlibrary.plugins.openlibrary import contribute


class Redirect(Exception):
    pass


def row(olid: str, *fields: str) -> dict:
    return {
        "book": {"key": f"/books/{olid}"},
        "tasks": [{"url": f"/tasks/task/{olid}/{f}", "field": f, "weight": 1} for f in fields],
    }


@pytest.fixture
def pick(monkeypatch):
    """Run /tasks/one over a fixed pool of rows, returning the URL it redirects to."""
    pool = [row("OL1M", "languages"), row("OL2M", "languages", "publishers"), row("OL3M", "covers")]

    def build_rows(task, initiative, fields=None):
        fields = fields or contribute.get_filter_fields(task, initiative)
        rows = [{**r, "tasks": [t for t in r["tasks"] if t["field"] in fields]} for r in pool]
        return [r for r in rows if r["tasks"]]

    def run(**params) -> str:
        monkeypatch.setattr(contribute, "query_param", lambda name, default=None: params.get(name, default))
        with pytest.raises(Redirect) as e:
            contribute.contribute_one().GET()
        return e.value.args[0]

    monkeypatch.setattr(contribute, "require_login", lambda path: None)
    monkeypatch.setattr(contribute, "build_task_rows", build_rows)
    monkeypatch.setattr(web, "seeother", Redirect)
    return run


def test_next_url_keeps_the_field_unless_surprise_chose_it():
    assert parse_qs(urlsplit(contribute.build_next_url("", Task("OL1M", "languages"), saved=False)).query) == {"field": ["languages"], "exclude": ["OL1M"]}
    assert parse_qs(urlsplit(contribute.build_next_url("", Task("OL1M", "languages"), saved=False, surprise=True)).query) == {"exclude": ["OL1M"]}


def test_task_url_carries_back_and_surprise():
    assert contribute.build_task_url(Task("OL1M", "languages")) == "/tasks/task/OL1M/languages"
    assert contribute.build_task_url(Task("OL1M", "languages"), "languages", surprise=True) == "/tasks/task/OL1M/languages?back=languages&surprise=1"


def test_stays_on_the_field_and_off_the_book_just_done(pick):
    for _ in range(20):
        assert "/tasks/task/OL2M/languages" in pick(field="languages", exclude="OL1M")


def test_falls_back_to_any_field_when_the_field_runs_out(pick):
    url = pick(field="covers", exclude="OL3M")
    assert "/languages" in url or "/publishers" in url
    # The fallback's field is the user's new run, so it isn't marked as a surprise.
    assert "surprise" not in url


def test_a_field_outside_the_filter_yields_to_the_filter(pick):
    assert "/tasks/task/OL3M/covers" in pick(task="covers", field="languages")


def test_surprise_me_is_marked_so_the_next_pick_stays_open(pick):
    assert "surprise=1" in pick()
    assert "surprise" not in pick(field="languages")


def test_redirects_to_the_list_when_nothing_is_left(pick, monkeypatch):
    monkeypatch.setattr(contribute, "build_task_rows", lambda task, initiative, fields=None: [])
    assert pick(task="covers", field="covers").endswith("/tasks?task=covers")


def test_receipt_says_what_was_saved(monkeypatch):
    edition = SimpleNamespace(title="A Book", url=lambda: "/books/OL1M/A_Book", get_cover_url=lambda size: "/cover.jpg")
    monkeypatch.setattr(web, "ctx", web.storage(site=SimpleNamespace(get=lambda key: edition)))
    monkeypatch.setattr(contribute, "get_field_guides", lambda: {"languages": web.storage(label="Language")})
    monkeypatch.setattr(contribute, "format_field_value", lambda e, f: "English")
    assert contribute.build_receipt("OL1M/languages") == {
        "field_label": "Language",
        "title": "A Book",
        "value": "English",
        "url": "/books/OL1M/A_Book",
        "cover_url": "/cover.jpg",
    }


def test_no_receipt_without_a_saved_task():
    assert contribute.build_receipt("") is None


@pytest.mark.parametrize(
    ("fld", "cover_url", "shown"),
    [
        ("languages", "/cover.jpg", False),
        ("covers", None, False),
        ("covers", "/cover.jpg", True),
    ],
)
def test_receipt_needs_a_saved_value(monkeypatch, fld, cover_url, shown):
    edition = SimpleNamespace(title="A Book", url=lambda: "/books/OL1M/A_Book", get_cover_url=lambda size: cover_url)
    monkeypatch.setattr(web, "ctx", web.storage(site=SimpleNamespace(get=lambda key: edition)))
    monkeypatch.setattr(contribute, "get_field_guides", lambda: {fld: web.storage(label="Label")})
    monkeypatch.setattr(contribute, "format_field_value", lambda e, f: "")
    assert bool(contribute.build_receipt(f"OL1M/{fld}")) is shown


FICTION, MYSTERY = web.storage(key="/tags/OL1T", name="Fiction"), web.storage(key="/tags/OL2T", name="Mystery")


@pytest.fixture
def vocabulary(monkeypatch):
    by_field = {"literary_forms": [FICTION], "genres": [MYSTERY]}
    monkeypatch.setattr(contribute, "find_tag", lambda fld, key: next((t for t in by_field[fld] if t.key == key), None))
    monkeypatch.setattr(contribute, "get_field_guides", lambda: {"literary_forms": web.storage(label="Literary form"), "genres": web.storage(label="Genres")})


def test_picked_carries_a_work_answers_tags():
    assert contribute.picked_param({"literary_forms": ["/tags/OL1T"], "genres": ["/tags/OL2T", " /tags/OL2T"]}) == "OL1T,OL2T"
    url = contribute.build_next_url("", Task("OL1M", "literary_forms"), saved=True, picked="OL1T")
    assert parse_qs(urlsplit(url).query)["picked"] == ["OL1T"]


def test_receipt_names_the_picked_tags_not_the_records(monkeypatch, vocabulary):
    """The record may be the copy cached before the save, so the receipt names what was picked."""
    edition = SimpleNamespace(title="A Book", url=lambda: "/books/OL1M/A_Book", get_cover_url=lambda size: None)
    monkeypatch.setattr(web, "ctx", web.storage(site=SimpleNamespace(get=lambda key: edition)))
    monkeypatch.setattr(contribute, "format_field_value", lambda e, f: "")
    receipt = contribute.build_receipt("OL1M/literary_forms", "OL1T")
    assert (receipt["field_label"], receipt["value"]) == ("Literary form", "Fiction")
    receipt = contribute.build_receipt("OL1M/literary_forms", "OL1T,OL2T")
    assert (receipt["field_label"], receipt["value"]) == ("Literary form and Genres", "Fiction · Mystery")


def test_receipt_shows_only_the_answered_field_without_picked(monkeypatch, vocabulary):
    edition = SimpleNamespace(title="A Book", url=lambda: "/books/OL1M/A_Book", get_cover_url=lambda size: None)
    monkeypatch.setattr(web, "ctx", web.storage(site=SimpleNamespace(get=lambda key: edition)))
    monkeypatch.setattr(contribute, "format_field_value", lambda e, f: {"literary_forms": "Fiction", "genres": "Sci-Fi"}[f])
    assert contribute.build_receipt("OL1M/literary_forms")["value"] == "Fiction"
