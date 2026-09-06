"""Tests for Batch.add_or_refresh_items (#12844).

``dedupe_items`` drops any record whose ``ia_id`` is already in ``import_item``,
anywhere, at any status. That is correct for firehose sources -- Amazon price
lookups and daily archive.org imports re-offer the same unchanged records
constantly, and re-queuing them is what previously took Open Library's database
down.

It is wrong for a registered feed, which is a *change stream*: the provider only
returns records whose ``modified`` advanced. Dropping those discards the update
we asked for -- notably a Better World Books price change, which is the reason
the Feed Registry exists.

``add_or_refresh_items`` is additive and opt-in. ``add_items`` is untouched, so
no existing importer changes behaviour.
"""

from __future__ import annotations

import json
from typing import Final

import pytest
import web

from openlibrary.core.db import get_db
from openlibrary.core.imports import Batch

IMPORT_BATCH_DDL: Final = "CREATE TABLE import_batch (id integer primary key, name text, submitter text, submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
IMPORT_ITEM_DDL: Final = """
CREATE TABLE import_item (
    id integer primary key, batch_id integer, added_time timestamp, import_time timestamp,
    status text default 'pending', error text, ia_id text, data text, ol_key text,
    comments text, submitter text, UNIQUE (batch_id, ia_id)
);
"""


@pytest.fixture
def import_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    for table in ("import_item", "import_batch"):
        db.query(f"DROP TABLE IF EXISTS {table};")
    for ddl in (IMPORT_BATCH_DDL, IMPORT_ITEM_DDL):
        db.query(ddl)
    yield db
    for table in ("import_item", "import_batch"):
        db.query(f"DROP TABLE IF EXISTS {table};")


def item(ia_id: str, price: float) -> dict:
    return {
        "ia_id": ia_id,
        "data": {
            "title": "A Book",
            "source_records": [ia_id],
            "acquisitions": [{"provider_name": "betterworldbooks", "local_id": ia_id.split(":")[1], "data": {"access": "buy", "price": price}}],
        },
    }


def rows(db) -> dict[str, web.storage]:
    return {r.ia_id: r for r in db.select("import_item")}


class TestNewRecords:
    def test_new_records_are_inserted(self, import_db):
        batch = Batch.new("bwb-opds")
        result = batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])

        assert result["added"] == 1
        assert rows(import_db)["betterworldbooks:1"].status == "pending"


class TestChangedRecords:
    def test_a_changed_record_is_refreshed_in_place(self, import_db):
        """The whole point: a new price must reach the catalog, and must not
        create a second row."""
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])
        import_db.update("import_item", where="ia_id='betterworldbooks:1'", status="created", import_time="2026-09-01")

        result = batch.add_or_refresh_items([item("betterworldbooks:1", 9.99)])

        assert result["refreshed"] == 1
        assert result["added"] == 0
        assert len(list(import_db.select("import_item"))) == 1  # no second row

        row = rows(import_db)["betterworldbooks:1"]
        assert row.status == "pending"  # requeued for the catalog
        assert json.loads(row.data)["acquisitions"][0]["data"]["price"] == 9.99

    def test_a_refresh_clears_a_previous_error(self, import_db):
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])
        import_db.update("import_item", where="ia_id='betterworldbooks:1'", status="failed", error="boom")

        batch.add_or_refresh_items([item("betterworldbooks:1", 9.99)])

        row = rows(import_db)["betterworldbooks:1"]
        assert row.status == "pending"
        assert row.error is None


class TestUnchangedRecords:
    def test_an_unchanged_record_is_left_alone(self, import_db):
        """Not re-queuing unchanged records is the property that protects the
        database; this must not become an unconditional requeue."""
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])
        import_db.update("import_item", where="ia_id='betterworldbooks:1'", status="created")

        result = batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])

        assert result["unchanged"] == 1
        assert result["refreshed"] == 0
        assert rows(import_db)["betterworldbooks:1"].status == "created"  # NOT requeued

    def test_a_completed_row_whose_data_was_nulled_is_refreshed(self, import_db):
        """set_status() nulls `data` on terminal statuses, so a completed row has
        nothing to compare against.

        That must count as CHANGED. The caller only offers records a feed has
        already flagged as modified, and treating "cannot tell" as "unchanged"
        would mean a price that changes after its first successful import never
        reaches the catalog again -- silently defeating the feed. Callers with
        durable prior state filter earlier; the harvester compares against the
        acquisitions table.
        """
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])
        import_db.update("import_item", where="ia_id='betterworldbooks:1'", status="created", data=None)

        result = batch.add_or_refresh_items([item("betterworldbooks:1", 9.99)])

        assert result["refreshed"] == 1
        assert rows(import_db)["betterworldbooks:1"].status == "pending"


class TestInFlightRecords:
    def test_a_row_being_processed_is_not_yanked(self, import_db):
        """manage-imports claims rows by setting status='processing'; resetting
        one mid-flight races with the importer."""
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])
        import_db.update("import_item", where="ia_id='betterworldbooks:1'", status="processing")

        result = batch.add_or_refresh_items([item("betterworldbooks:1", 9.99)])

        assert result["skipped_in_flight"] == 1
        assert rows(import_db)["betterworldbooks:1"].status == "processing"


class TestIsolation:
    def test_add_items_is_unchanged(self, import_db):
        """Existing importers must not change behaviour: add_items still skips
        anything already present, regardless of content."""
        batch = Batch.new("bwb-opds")
        batch.add_items([item("betterworldbooks:1", 1.25)])
        batch.add_items([item("betterworldbooks:1", 9.99)])

        row = rows(import_db)["betterworldbooks:1"]
        assert json.loads(row.data)["acquisitions"][0]["data"]["price"] == 1.25  # not refreshed

    def test_a_mixed_batch_is_split_correctly(self, import_db):
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25), item("betterworldbooks:2", 2.0)])
        import_db.update("import_item", where="ia_id='betterworldbooks:1'", status="created")

        result = batch.add_or_refresh_items([item("betterworldbooks:1", 9.99), item("betterworldbooks:2", 2.0), item("betterworldbooks:3", 3.0)])

        assert result == {"added": 1, "refreshed": 1, "unchanged": 1, "skipped_in_flight": 0}
        assert len(list(import_db.select("import_item"))) == 3
