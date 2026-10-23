import pytest
import web

from openlibrary.contribute import save
from openlibrary.plugins.openlibrary import contribute


class FakeChange:
    def __init__(self, source, timestamp=0):
        self.data = {"source": source} if source else None
        self.timestamp = timestamp


class FakeSite:
    def __init__(self, changes):
        self.changes = changes
        self.queries = []

    def recentchanges(self, query):
        self.queries.append(query)
        return [c for c in self.changes if getattr(c, "kind", "edit-book") == query["kind"]]


class FakeUser:
    key = "/people/reader"

    def __init__(self, librarian=False):
        self.librarian = librarian

    def is_librarian_or_higher(self):
        return self.librarian


def test_saves_today_counts_only_tasks_edits_since_midnight(monkeypatch):
    cover = FakeChange("contribute")
    cover.kind = "add-cover"
    site = FakeSite([FakeChange("contribute"), FakeChange(None), FakeChange("contribute"), FakeChange("other"), cover])
    monkeypatch.setattr(web.ctx, "site", site, raising=False)
    assert save.saves_today("/people/reader") == 3
    assert [q["kind"] for q in site.queries] == ["edit-book", "add-cover"]
    for query in site.queries:
        assert query["author"] == "/people/reader"
        assert len(query["begin_date"]) == len("2026-01-01")


def test_recent_saves_interleave_covers_with_other_edits_newest_first(monkeypatch):
    older, newer, cover = FakeChange("contribute", 1), FakeChange("contribute", 3), FakeChange("contribute", 2)
    cover.kind = "add-cover"
    monkeypatch.setattr(web.ctx, "site", FakeSite([older, newer, cover]), raising=False)
    assert save.recent_saves("/people/reader") == [newer, cover, older]


def test_a_cover_needs_an_image(monkeypatch):
    with pytest.raises(save.InvalidAnswer):
        save.save_cover(object(), {})


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
