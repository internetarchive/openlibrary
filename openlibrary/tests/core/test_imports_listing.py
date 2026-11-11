"""Tests for Batch.list_summaries, which backs the /import/batch listing."""

from typing import Final

import pytest
import web

from openlibrary.core.db import get_db
from openlibrary.core.imports import Batch

LISTING_BATCH_DDL: Final = "CREATE TABLE import_batch (id integer primary key, name text, submitter text, submit_time TIMESTAMP);"
LISTING_ITEM_DDL: Final = """
CREATE TABLE import_item (
    id integer primary key, batch_id integer, added_time timestamp, import_time timestamp,
    status text default 'pending', error text, ia_id text, data text, ol_key text,
    comments text, submitter text, UNIQUE (batch_id, ia_id)
);
"""


@pytest.fixture
def listing_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    for table in ("import_item", "import_batch"):
        db.query(f"DROP TABLE IF EXISTS {table};")
    for ddl in (LISTING_BATCH_DDL, LISTING_ITEM_DDL):
        db.query(ddl)
    db.multiple_insert(
        "import_batch",
        [
            {"id": 1, "name": "old", "submitter": "alice", "submit_time": "2026-01-01 00:00:00"},
            {"id": 2, "name": "mid", "submitter": None, "submit_time": "2026-02-01 00:00:00"},
            {"id": 3, "name": "new", "submitter": "carol", "submit_time": "2026-03-01 00:00:00"},
        ],
    )
    db.multiple_insert(
        "import_item",
        [
            {"batch_id": 1, "ia_id": "a", "status": "needs_review", "comments": "first"},
            {"batch_id": 1, "ia_id": "b", "status": "needs_review"},
            {"batch_id": 1, "ia_id": "c", "status": "created"},
            {"batch_id": 2, "ia_id": "a", "status": "pending", "submitter": "bob"},
            {"batch_id": 3, "ia_id": "a", "status": "needs_review"},
            {"batch_id": 3, "ia_id": "b", "status": "failed"},
        ],
    )
    yield db
    for table in ("import_item", "import_batch"):
        db.query(f"DROP TABLE IF EXISTS {table};")


class TestBatchListSummaries:
    def test_all_statuses_newest_first_by_default(self, listing_db):
        total, rows = Batch.list_summaries()
        assert total == 3
        assert [r.batch_id for r in rows] == [3, 2, 1]
        assert rows[2].status_counts == {"created": 1, "needs_review": 2}
        assert rows[2].comments == "first"

    def test_submitter_falls_back_to_items(self, listing_db):
        _, rows = Batch.list_summaries(sort="batch_id", order="asc")
        assert [r.submitter for r in rows] == ["alice", "bob", "carol"]

    def test_status_filter(self, listing_db):
        total, rows = Batch.list_summaries(status="needs_review", order="asc")
        assert total == 2
        assert [r.batch_id for r in rows] == [1, 3]
        assert [r.status_counts for r in rows] == [{"needs_review": 2}, {"needs_review": 1}]

    def test_pagination(self, listing_db):
        total, rows = Batch.list_summaries(limit=2, offset=2)
        assert total == 3
        assert [r.batch_id for r in rows] == [1]

    @pytest.mark.parametrize(
        "kwargs",
        [{"status": "bogus' OR 1=1 --"}, {"sort": "name"}, {"order": "sideways"}],
    )
    def test_rejects_unknown_arguments(self, kwargs):
        with pytest.raises(ValueError, match=r"^invalid "):
            Batch.list_summaries(**kwargs)
