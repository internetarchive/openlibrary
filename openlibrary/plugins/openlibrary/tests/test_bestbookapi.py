import json
import web
from openlibrary import accounts
from openlibrary.core import bestbook as bestbook_model, bookshelves
from openlibrary.plugins.upstream.code import bestbook, bestbook_count


def test_bestbook_award_addition(monkeypatch):
    work_id = "OL123W"

    class FakeUser:
        def __init__(self, key):
            self.key = '/users/%s' % key

    monkeypatch.setattr(accounts, "get_current_user", FakeUser('testuser'))
    monkeypatch.setattr(
        bookshelves.Bookshelves,
        "get_users_read_status_of_work",
        lambda username, work_id: 3,
    )
    monkeypatch.setattr(
        bestbook_model.Bestbook, "get_awards", lambda book_id, submitter: []
    )
    monkeypatch.setattr(
        bestbook_model.Bestbook,
        "add",
        lambda submitter, book_id, edition_id, comment, topic: None,
    )
    monkeypatch.setattr(
        bestbook_model.Bestbook, "remove", lambda submitter, book_id: None
    )

    i = web.input(edition_key=None, topic="Fiction", comment="Great book!", redir=False)
    result = bestbook.POST(bestbook(), work_id)

    assert json.loads(result)["success"] == "Awarded the book"


def test_bestbook_award_removal(monkeypatch):
    work_id = "OL123W"

    class FakeUser:
        def __init__(self, key):
            self.key = '/users/%s' % key

    monkeypatch.setattr(accounts, "get_current_user", FakeUser('testuser'))
    monkeypatch.setattr(
        bookshelves.Bookshelves,
        "get_users_read_status_of_work",
        lambda username, work_id: 3,
    )
    monkeypatch.setattr(
        bestbook_model.Bestbook, "get_awards", lambda book_id, submitter: ["Fiction"]
    )
    monkeypatch.setattr(
        bestbook_model.Bestbook, "remove", lambda submitter, book_id: None
    )

    i = web.input(edition_key=None, topic=None, comment=None, redir=False)
    result = bestbook.POST(bestbook(), work_id)

    assert json.loads(result)["success"] == "Removed award"


def test_bestbook_award_limit(monkeypatch):
    work_id = "OL123W"

    class FakeUser:
        def __init__(self, key):
            self.key = '/users/%s' % key

    monkeypatch.setattr(accounts, "get_current_user", FakeUser('testuser'))
    monkeypatch.setattr(
        bookshelves.Bookshelves,
        "get_users_read_status_of_work",
        lambda username, work_id: 3,
    )
    monkeypatch.setattr(
        bestbook_model.Bestbook,
        "check_if_award_given",
        lambda submitter, book_id, topic: True,
    )

    i = web.input(edition_key=None, topic="Fiction", comment=None, redir=False)
    result = bestbook.POST(bestbook(), work_id)

    assert (
        json.loads(result)["success"]
        == "Error: limit one award per book, and one award per topic."
    )


def test_bestbook_award_not_reader(monkeypatch):
    work_id = "OL123W"

    class FakeUser:
        def __init__(self, key):
            self.key = '/users/%s' % key

    monkeypatch.setattr(accounts, "get_current_user", FakeUser('testuser'))
    monkeypatch.setattr(
        bookshelves.Bookshelves,
        "get_users_read_status_of_work",
        lambda username, work_id: 2,
    )

    i = web.input(edition_key=None, topic="Fiction", comment=None, redir=False)
    result = bestbook.POST(bestbook(), work_id)

    assert json.loads(result)["success"] == "Only readers can award"


def test_bestbook_count(monkeypatch):
    monkeypatch.setattr(
        bestbook_model.Bestbook, "get_count", lambda book_id, submitter, topic: 5
    )

    filt = web.input(book_id="OL123W", submitter="testuser", topic="Fiction")
    result = bestbook_count.GET(bestbook_count())

    assert json.loads(result)["count"] == 5
