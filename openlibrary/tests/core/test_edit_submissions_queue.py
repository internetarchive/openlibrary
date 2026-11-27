"""Queue-level tests for BookWorm edit submissions (#14750).

These exercise the wiring that makes the batch-import queue accept edits as
well as imports:

- ``batch_import`` recognises an edit line, validates it for edit shape, and
  queues it with a synthetic ``edit:`` ia_id.
- ``ImportItem.single_import`` dispatches an edit row to the apply path and
  maps the outcome onto the row's status (modified / needs_review / failed).

They use an in-memory sqlite ``import_item``/``import_batch`` (as the other
core import tests do) together with the ``mock_site`` fixture for the live
catalog the patch is applied to.
"""

import json
from typing import Final

import pytest
import web

from openlibrary.core.batch_imports import batch_import
from openlibrary.core.db import get_db
from openlibrary.core.imports import ImportItem

IMPORT_ITEM_DDL: Final = """
CREATE TABLE IF NOT EXISTS import_item (
    id serial primary key,
    batch_id integer,
    added_time timestamp,
    import_time timestamp,
    status text default 'pending',
    error text,
    ia_id text,
    data text,
    ol_key text,
    comments text,
    submitter text,
    UNIQUE (batch_id, ia_id)
);
"""

IMPORT_BATCH_DDL: Final = """
CREATE TABLE IF NOT EXISTS import_batch (
    id integer primary key,
    name text,
    submitter text,
    submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture
def queue_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    # The web.py sqlite ``:memory:`` connection is process-global and shared
    # with other import tests (e.g. test_imports.py), which create their own
    # ``import_item`` with a different column set. Drop any leftover tables and
    # recreate ours, then drop again on teardown so the next module starts
    # clean regardless of run order.
    db.query("DROP TABLE IF EXISTS import_item;")
    db.query("DROP TABLE IF EXISTS import_batch;")
    db.query(IMPORT_ITEM_DDL)
    db.query(IMPORT_BATCH_DDL)
    yield db
    db.query("DROP TABLE IF EXISTS import_item;")
    db.query("DROP TABLE IF EXISTS import_batch;")


class TestBatchImportIngestsEdits:
    def test_edit_line_is_queued_with_edit_ia_id(self, queue_db, monkeypatch):
        monkeypatch.setattr("openlibrary.core.batch_imports.accounts.get_current_user", lambda: None)
        jsonl = json.dumps({"key": "/books/OL1M", "v": "1", "title": "New title"}).encode("utf-8")

        result = batch_import(jsonl, import_status="pending")

        assert result.errors is None
        rows = list(queue_db.select("import_item"))
        assert len(rows) == 1
        assert rows[0].ia_id.startswith("edit:/books/OL1M:")
        assert rows[0].status == "pending"
        assert json.loads(rows[0].data)["title"] == "New title"

    def test_malformed_edit_line_is_rejected_without_queueing(self, queue_db, monkeypatch):
        monkeypatch.setattr("openlibrary.core.batch_imports.accounts.get_current_user", lambda: None)
        # Missing base version `v`.
        jsonl = json.dumps({"key": "/books/OL1M", "title": "New title"}).encode("utf-8")

        result = batch_import(jsonl, import_status="pending")

        assert result.batch is None
        assert result.errors
        assert any("version" in e.error_message for e in result.errors)
        assert list(queue_db.select("import_item")) == []

    def test_two_distinct_edits_to_same_record_do_not_collide(self, queue_db, monkeypatch):
        monkeypatch.setattr("openlibrary.core.batch_imports.accounts.get_current_user", lambda: None)
        jsonl = (json.dumps({"key": "/books/OL1M", "v": "1", "title": "A"}) + "\n" + json.dumps({"key": "/books/OL1M", "v": "1", "subtitle": "B"})).encode(
            "utf-8"
        )

        batch_import(jsonl, import_status="pending")

        rows = list(queue_db.select("import_item"))
        assert len(rows) == 2  # distinct patch hashes -> distinct ia_ids


@pytest.mark.usefixtures("mock_site")
class TestSingleImportDispatchesEdits:
    def _queue_edit(self, queue_db, record, row_id=1):
        queue_db.insert(
            "import_item",
            seqname=False,
            id=row_id,
            batch_id=1,
            ia_id=f"edit:{record['key']}:{row_id}",
            data=json.dumps(record),
            status="pending",
        )
        row = queue_db.select("import_item", where="id=$row_id", vars={"row_id": row_id})[0]
        return ImportItem(row)

    def test_applied_when_version_matches(self, queue_db, mock_site):
        mock_site.save({"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "Old"})  # rev 1
        item = self._queue_edit(queue_db, {"key": "/books/OL1M", "v": "1", "title": "New"})

        item.single_import()

        assert mock_site.get("/books/OL1M").title == "New"
        row = queue_db.select("import_item", where="id=1", vars={})[0]
        assert row.status == "modified"
        assert row.ol_key == "/books/OL1M"

    def test_conflict_routes_to_needs_review_and_keeps_data(self, queue_db, mock_site):
        mock_site.save({"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "v1"})  # rev 1
        mock_site.save({"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "v2"})  # rev 2
        item = self._queue_edit(queue_db, {"key": "/books/OL1M", "v": "1", "title": "patch"})

        item.single_import()

        assert mock_site.get("/books/OL1M").title == "v2"  # untouched
        row = queue_db.select("import_item", where="id=1", vars={})[0]
        assert row.status == "needs_review"
        assert row.error == "version-conflict"
        assert row.data is not None  # preserved for rebase

    def test_missing_target_fails(self, queue_db, mock_site):
        item = self._queue_edit(queue_db, {"key": "/books/OL404M", "v": "1", "title": "x"})

        item.single_import()

        row = queue_db.select("import_item", where="id=1", vars={})[0]
        assert row.status == "failed"
        assert row.error == "edit-target-missing"
