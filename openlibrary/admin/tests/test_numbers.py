import re
from datetime import datetime
from types import SimpleNamespace

import pytest
import web

from openlibrary.admin import numbers
from openlibrary.contribute import save


class FakeDB:
    """Records the SQL `numbers` runs and answers every query with one row, or with `rows` when given."""

    def __init__(self, count=7, rows=None):
        self.count = count
        self.rows = rows
        self.queries = []

    def query(self, q, vars=None):
        self.queries.append((q, vars))
        return self.rows if self.rows is not None else [web.storage(count=self.count)]


class FakeStore(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def run(fn, db):
    numbers.cached_bot_accounts = [11, 12]
    try:
        return fn(thingdb=db, coverdb=None, logroot=None, start=datetime(2026, 10, 15), end=datetime(2026, 10, 15, 21, 0, 0))
    finally:
        numbers.cached_bot_accounts = None


def test_edit_counts_split_humans_from_bots():
    for fn, author_clause in [
        (numbers.admin_range__human_edits, "t.author_id NOT IN (11, 12)"),
        (numbers.admin_range__bot_edits, "t.author_id IN (11, 12)"),
    ]:
        db = FakeDB()
        assert run(fn, db) == 7
        [(q, vars)] = db.queries
        sql = str(web.db.reparam(q, vars))
        assert author_clause in sql
        assert "t.action" not in sql
        assert "t.created >= '2026-10-15' and t.created < '2026-10-15 21:00:00'" in sql


def test_catalog_edits_skip_account_creation_and_bots():
    db = FakeDB()
    assert run(numbers.admin_range__catalog_edits, db) == 7
    [(q, vars)] = db.queries
    sql = str(web.db.reparam(q, vars))
    assert "t.action NOT IN ('" in sql
    assert "'new-account'" in sql
    assert "t.author_id NOT IN (11, 12)" in sql
    assert "t.created >= '2026-10-15' and t.created < '2026-10-15 21:00:00'" in sql


def test_list_edits_count_list_creation_and_seed_edits():
    db = FakeDB()
    assert run(numbers.admin_range__list_edits, db) == 7
    [(q, vars)] = db.queries
    sql = str(web.db.reparam(q, vars))
    assert "t.action IN ('" in sql
    assert "'create-list'" in sql
    assert "'edit-list-seeds'" in sql
    assert "t.created >= '2026-10-15' and t.created < '2026-10-15 21:00:00'" in sql


def test_editor_counts_use_a_rolling_window_ending_at_end():
    for fn, since in [
        (numbers.admin_range__catalog_editors_7d, "2026-10-08 21:00:00"),
        (numbers.admin_range__catalog_editors_28d, "2026-09-17 21:00:00"),
    ]:
        db = FakeDB()
        assert run(fn, db) == 7
        [(q, vars)] = db.queries
        sql = str(web.db.reparam(q, vars))
        assert f"t.created >= '{since}' AND t.created < '2026-10-15 21:00:00'" in sql
        assert "t.author_id NOT IN (11, 12)" in sql
        assert "NOT EXISTS" not in sql


def test_editor_counts_without_bots_skip_the_bot_clause():
    db = FakeDB()
    numbers.cached_bot_accounts = []
    try:
        numbers.admin_range__catalog_editors_28d(thingdb=db, start=datetime(2026, 10, 15), end=datetime(2026, 10, 15, 21, 0, 0))
    finally:
        numbers.cached_bot_accounts = None
    [(q, vars)] = db.queries
    assert "NOT IN" not in str(web.db.reparam(q, vars))


def test_new_editors_have_no_catalog_change_before_the_window():
    db = FakeDB()
    assert run(numbers.admin_range__new_catalog_editors_28d, db) == 7
    [(q, vars)] = db.queries
    sql = str(web.db.reparam(q, vars))
    assert "NOT EXISTS (SELECT 1 FROM transaction p WHERE p.author_id = e.author_id AND p.created < '2026-09-17 21:00:00'" in sql


def test_tasks_counts_read_the_source_tag():
    for fn in [
        numbers.admin_range__tasks_saves_28d,
        numbers.admin_range__tasks_saves_undone_28d,
        numbers.admin_range__tasks_editors_7d,
        numbers.admin_range__tasks_editors_28d,
    ]:
        db = FakeDB()
        assert run(fn, db) == 7
        [(q, vars)] = db.queries
        assert "key = 'source' AND value = 'contribute'" in str(web.db.reparam(q, vars))


def test_daily_counts_cover_the_calendar_day_not_the_last_24_hours():
    for fn in [
        numbers.admin_range__catalog_editors_1d,
        numbers.admin_range__new_catalog_editors_1d,
        numbers.admin_range__tasks_editors_1d,
        numbers.admin_range__tasks_saves_1d,
    ]:
        db = FakeDB()
        assert run(fn, db) == 7
        [(q, vars)] = db.queries
        sql = str(web.db.reparam(q, vars)).lower()
        assert "t.created >= '2026-10-15' and t.created < '2026-10-15 21:00:00'" in sql
        assert "2026-10-14" not in sql


def test_daily_new_editors_have_no_catalog_change_before_that_day():
    db = FakeDB()
    run(numbers.admin_range__new_catalog_editors_1d, db)
    [(q, vars)] = db.queries
    assert "p.created < '2026-10-15'" in str(web.db.reparam(q, vars))


def test_saves_by_field_is_a_dict_of_the_days_saves():
    db = FakeDB(rows=[web.storage(field="number_of_pages", count=7), web.storage(field="covers", count=2), web.storage(field=None, count=1)])
    assert run(numbers.admin_range__tasks_saves_by_field_1d, db) == {"number_of_pages": 7, "covers": 2}
    [(q, vars)] = db.queries
    sql = str(web.db.reparam(q, vars))
    assert "key = 'source' AND value = 'contribute'" in sql
    assert "t.created >= '2026-10-15' AND t.created < '2026-10-15 21:00:00'" in sql


@pytest.fixture
def fake_initiative(monkeypatch):
    """A stand-in for `openlibrary.contribute.initiatives` with a two-edition list, plus a `web.ctx.site` holding its store doc."""
    calls = []

    def load_frozen(initiative, site):
        return (doc := site.store.get(initiative.store_key)) and doc["editions"]

    def gaps_for(picks, site):
        calls.append(len(picks))
        return [["/books/OL1M", 9, ["lccn"], []], ["/books/OL2M", 8, [], ["covers"]]]

    def build_gaps(initiative, site):
        raise AssertionError("the stats run must not pick and freeze the list")

    initiatives = SimpleNamespace(
        ACTIVE=SimpleNamespace(slug="most-read-test", store_key="contribute-initiative-most-read-test"),
        load_frozen=load_frozen,
        gaps_for=gaps_for,
        build_gaps=build_gaps,
        progress=lambda gaps: {"open": 1, "done": 1, "not_found": 1, "total": 2, "percent": 91},
        calls=calls,
    )
    monkeypatch.setattr(numbers, "_initiative", lambda: initiatives)
    store = FakeStore({"contribute-initiative-most-read-test": {"editions": [["/books/OL1M", 9], ["/books/OL2M", 8]]}})
    monkeypatch.setattr(web.ctx, "site", SimpleNamespace(store=store), raising=False)
    monkeypatch.setattr(numbers, "_cached_initiative_progress", None)
    return initiatives


def test_initiative_snapshot_is_read_once_for_all_its_keys(fake_initiative):
    now = datetime.now()
    kargs = {"thingdb": FakeDB(), "start": now.replace(hour=0, minute=0, second=0, microsecond=0), "end": now}
    assert numbers.admin_range__initiative_open_gaps(**kargs) == 1
    assert numbers.admin_range__initiative_done_editions(**kargs) == 1
    assert numbers.admin_range__initiative_not_found(**kargs) == 1
    assert numbers.admin_range__initiative_editions(**kargs) == 2
    assert numbers.admin_range__initiative_slug(**kargs) == "most-read-test"
    assert fake_initiative.calls == [2]


def test_initiative_snapshot_waits_for_the_web_app_to_freeze_the_list(fake_initiative):
    web.ctx.site.store.clear()
    now = datetime.now()
    kargs = {"thingdb": FakeDB(), "start": now.replace(hour=0, minute=0, second=0, microsecond=0), "end": now}
    with pytest.raises(numbers.NoStats):
        numbers.admin_range__initiative_open_gaps(**kargs)
    assert fake_initiative.calls == []


def test_initiative_snapshot_refuses_past_days(fake_initiative):
    "The backfill loop calls every function for every past day; a snapshot has no past to report."
    for fn in [numbers.admin_range__initiative_open_gaps, numbers.admin_range__initiative_slug]:
        with pytest.raises(numbers.NoStats):
            run(fn, FakeDB())
    assert fake_initiative.calls == []


def test_initiative_saves_are_limited_to_the_frozen_list(fake_initiative):
    db = FakeDB()
    assert run(numbers.admin_range__tasks_saves_initiative_1d, db) == 7
    [(q, vars)] = db.queries
    sql = str(web.db.reparam(q, vars))
    assert "t.changes::json->0->>'key' IN ('/books/OL1M', '/books/OL2M')" in sql
    assert "key = 'source' AND value = 'contribute'" in sql
    assert "t.created >= '2026-10-15' and t.created < '2026-10-15 21:00:00'" in sql


def test_initiative_saves_need_a_frozen_list(fake_initiative):
    web.ctx.site.store.clear()
    with pytest.raises(numbers.NoStats):
        run(numbers.admin_range__tasks_saves_initiative_1d, FakeDB())


def test_tasks_source_matches_what_tasks_saves_write():
    assert numbers.TASKS_SOURCE == save.SOURCE


def test_catalog_change_matches_record_keys_only():
    pattern = re.compile(numbers.CATALOG_CHANGE)
    assert pattern.search('[{"key": "/books/OL1M", "revision": 2}]')
    assert pattern.search('[{"key": "/authors/OL1A", "revision": 2}]')
    assert not pattern.search('[{"key": "/people/x/lists/OL1L", "revision": 2}]')
