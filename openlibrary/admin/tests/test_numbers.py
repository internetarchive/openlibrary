from datetime import datetime

import web

from openlibrary.admin import numbers


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


def test_edit_counts_skip_account_creation():
    for fn, author_clause in [
        (numbers.admin_range__human_edits, "t.author_id NOT IN (11, 12)"),
        (numbers.admin_range__bot_edits, "t.author_id IN (11, 12)"),
    ]:
        db = FakeDB()
        assert run(fn, db) == 7
        [(q, vars)] = db.queries
        sql = str(web.db.reparam(q, vars))
        assert "t.action NOT IN ('" in sql
        assert "'new-account'" in sql
        assert author_clause in sql
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
