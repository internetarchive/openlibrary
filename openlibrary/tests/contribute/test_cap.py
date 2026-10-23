import web

from openlibrary.contribute import save
from openlibrary.plugins.openlibrary import contribute


class FakeChange:
    def __init__(self, source):
        self.data = {"source": source} if source else None


class FakeSite:
    def __init__(self, changes):
        self.changes = changes
        self.queries = []

    def recentchanges(self, query):
        self.queries.append(query)
        return self.changes


class FakeUser:
    key = "/people/reader"

    def __init__(self, librarian=False):
        self.librarian = librarian

    def is_librarian_or_higher(self):
        return self.librarian


def test_saves_today_counts_only_tasks_edits_since_midnight(monkeypatch):
    site = FakeSite([FakeChange("contribute"), FakeChange(None), FakeChange("contribute"), FakeChange("other")])
    monkeypatch.setattr(web.ctx, "site", site, raising=False)
    assert save.saves_today("/people/reader") == 2
    (query,) = site.queries
    assert query["author"] == "/people/reader"
    assert query["kind"] == "edit-book"
    assert len(query["begin_date"]) == len("2026-01-01")


def test_cap_blocks_a_member_at_the_limit_but_never_a_librarian(monkeypatch):
    monkeypatch.setattr(contribute, "daily_cap", lambda: 2)
    monkeypatch.setattr(save, "saves_today", lambda key: 2)
    assert contribute.cap_message(FakeUser()).startswith("You've saved 2 tasks today")
    assert contribute.cap_message(FakeUser(librarian=True)) == ""


def test_cap_lets_a_member_under_the_limit_through_and_zero_lifts_it(monkeypatch):
    monkeypatch.setattr(save, "saves_today", lambda key: 1)
    monkeypatch.setattr(contribute, "daily_cap", lambda: 2)
    assert contribute.cap_message(FakeUser()) == ""
    monkeypatch.setattr(save, "saves_today", lambda key: 500)
    monkeypatch.setattr(contribute, "daily_cap", lambda: 0)
    assert contribute.cap_message(FakeUser()) == ""
