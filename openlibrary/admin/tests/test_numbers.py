import re
from datetime import datetime
from types import SimpleNamespace

import pytest
import web

from openlibrary.admin import numbers
from openlibrary.contribute import initiatives, save
from openlibrary.utils.request_context import site as site_context


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
        return fn(thingdb=db, coverdb=None, start=datetime(2026, 10, 15), end=datetime(2026, 10, 15, 21, 0, 0))
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


FROZEN = {"frozen_at": "2026-10-28T12:00:00+00:00", "editions": [["/books/OL1M", 9], ["/books/OL2M", 8]]}


@pytest.fixture
def fake_initiatives(monkeypatch):
    """A stand-in for `openlibrary.contribute.initiatives` with two initiatives, only the first frozen, plus a `web.ctx.site` holding its store doc."""
    calls = []

    def gaps_for(picks, site):
        calls.append(len(picks))
        return [["/books/OL1M", 9, ["lccn"], []], ["/books/OL2M", 8, [], ["covers"]]]

    def build_gaps(initiative, site):
        raise AssertionError("the stats run must not pick and freeze a list")

    def initiative(slug, fields):
        return SimpleNamespace(slug=slug, store_key=f"contribute-initiative-{slug}", fields=fields, ends_at=None, start=None)

    registry = [initiative("most-read-test", ("covers", "publishers")), initiative("genres-test", ("genres",))]
    initiatives = SimpleNamespace(
        registry=registry,
        read_definitions=lambda site: [],
        started=lambda definitions: registry,
        gaps_for=gaps_for,
        build_gaps=build_gaps,
        progress=lambda gaps, fields, start: {"open": 1, "done": 1, "not_found": 1, "total": 2, "percent": 91},
        calls=calls,
    )
    monkeypatch.setattr(numbers, "_initiative", lambda: initiatives)
    monkeypatch.setattr(web.ctx, "site", SimpleNamespace(store=FakeStore({"contribute-initiative-most-read-test": FROZEN})), raising=False)
    site_context.set(web.ctx.site)
    return initiatives


def today_kargs(db=None):
    now = datetime.now()
    return {"thingdb": db or FakeDB(), "start": now.replace(hour=0, minute=0, second=0, microsecond=0), "end": now}


def test_initiatives_counts_each_frozen_list_and_skips_the_rest(fake_initiatives):
    assert numbers.admin_range__initiatives(**today_kargs()) == {
        "most-read-test": {"open": 1, "done": 1, "not_found": 1, "editions": 2, "percent": 91, "people": 7}
    }
    assert fake_initiatives.calls == [2]


def test_a_newly_frozen_initiative_is_counted_on_the_next_run(fake_initiatives):
    web.ctx.site.store["contribute-initiative-genres-test"] = FROZEN
    assert set(numbers.admin_range__initiatives(**today_kargs())) == {"most-read-test", "genres-test"}


def test_initiatives_survive_a_run_that_crosses_midnight(fake_initiatives):
    "A run started at 23:5x reaches this after midnight; the window, not the clock, says it's today's."
    start = datetime(2026, 10, 29)
    assert "most-read-test" in numbers.admin_range__initiatives(thingdb=FakeDB(), start=start, end=start.replace(hour=23, minute=55))


def test_initiatives_wait_for_the_web_app_to_freeze_a_list(fake_initiatives):
    web.ctx.site.store.clear()
    with pytest.raises(numbers.NoStats):
        numbers.admin_range__initiatives(**today_kargs())
    assert fake_initiatives.calls == []


def test_initiative_people_count_savers_since_the_freeze_by_tag_or_field(fake_initiatives):
    db = FakeDB()
    start = datetime(2026, 11, 2)
    numbers.admin_range__initiatives(thingdb=db, start=start, end=start.replace(hour=21))
    [(q, vars)] = db.queries
    sql = str(web.db.reparam(q, vars))
    assert "count(DISTINCT t.author_id)" in sql
    assert "t.created >= '2026-10-28T12:00:00+00:00' AND t.created < '2026-11-02 21:00:00'" in sql
    assert "key = 'source' AND value = 'contribute'" in sql
    # A save tagged with an initiative counts only there; an untagged one by its field.
    assert "COALESCE(t.data::json->>'initiative' = 'most-read-test', t.data::json->>'field' IN ('covers', 'publishers'))" in sql


def test_initiatives_refuse_past_days(fake_initiatives):
    "The backfill loop calls every function for every past day; a snapshot has no past to report."
    with pytest.raises(numbers.NoStats):
        numbers.admin_range__initiatives(thingdb=FakeDB(), start=datetime(2026, 10, 15), end=datetime(2026, 10, 16))
    assert fake_initiatives.calls == []


def test_other_fills_are_one_query_for_both_keys(monkeypatch):
    monkeypatch.setattr(numbers, "_cached_other_fills", {})
    db = FakeDB(rows=[web.storage(filled=40, undone=3)])
    assert run(numbers.admin_range__other_fills_28d, db) == 40
    assert run(numbers.admin_range__other_fills_undone_28d, db) == 3
    [(q, vars)] = db.queries
    sql = str(web.db.reparam(q, vars))
    # Outside Tasks, by people, on editions, over the 28 days before `end`
    assert "t.id NOT IN (SELECT tx_id FROM transaction_index WHERE key = 'source' AND value = 'contribute')" in sql
    assert "t.author_id NOT IN (11, 12)" in sql
    assert "LIKE '/books/OL%'" in sql
    assert "t.created >= '2026-09-17 21:00:00' AND t.created < '2026-10-15 21:00:00'" in sql


def test_tasks_fields_match_what_the_headline_initiative_offers():
    assert set(numbers.TASKS_FIELDS) == set(initiatives.MOST_READ.fields)


def test_tasks_source_matches_what_tasks_saves_write():
    assert numbers.TASKS_SOURCE == save.SOURCE


def test_catalog_change_matches_record_keys_only():
    pattern = re.compile(numbers.CATALOG_CHANGE)
    assert pattern.search('[{"key": "/books/OL1M", "revision": 2}]')
    assert pattern.search('[{"key": "/authors/OL1A", "revision": 2}]')
    assert not pattern.search('[{"key": "/people/x/lists/OL1L", "revision": 2}]')


@pytest.fixture(autouse=True)
def restore_site_context():
    token = site_context.set(site_context.get(None))
    yield
    site_context.reset(token)


def test_saves_by_initiative_is_a_dict_of_the_days_saves_that_name_one():
    db = FakeDB(rows=[web.storage(initiative="most-read-2026-11", count=9), web.storage(initiative=None, count=4)])
    assert run(numbers.admin_range__tasks_saves_by_initiative_1d, db) == {"most-read-2026-11": 9}
    [(q, vars)] = db.queries
    sql = str(web.db.reparam(q, vars))
    assert "key = 'source' AND value = 'contribute'" in sql
    assert "t.created >= '2026-10-15' AND t.created < '2026-10-15 21:00:00'" in sql


def test_the_28_day_saves_by_initiative_pair_each_count_with_its_undone():
    class TwoQueries(FakeDB):
        def query(self, q, vars=None):
            self.queries.append((q, vars))
            undone = "latest.data" in q
            return [web.storage(initiative="most-read-2026-11", count=2 if undone else 40), web.storage(initiative=None, count=1)]

    db = TwoQueries()
    assert run(numbers.admin_range__tasks_saves_by_initiative_28d, db) == {"most-read-2026-11": {"saves": 40, "undone": 2}}
    assert len(db.queries) == 2
