import re
from datetime import datetime

import web

from openlibrary.admin import numbers
from openlibrary.contribute import save


class FakeDB:
    """Records the SQL `numbers` runs and answers every query with one row."""

    def __init__(self, count=7):
        self.count = count
        self.queries = []

    def query(self, q, vars=None):
        self.queries.append((q, vars))
        return [web.storage(count=self.count)]


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


def test_tasks_source_matches_what_tasks_saves_write():
    assert numbers.TASKS_SOURCE == save.SOURCE


def test_catalog_change_matches_record_keys_only():
    pattern = re.compile(numbers.CATALOG_CHANGE)
    assert pattern.search('[{"key": "/books/OL1M", "revision": 2}]')
    assert pattern.search('[{"key": "/authors/OL1A", "revision": 2}]')
    assert not pattern.search('[{"key": "/people/x/lists/OL1L", "revision": 2}]')
