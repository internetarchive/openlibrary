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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Final

import pytest
import web

from openlibrary.core import db as core_db
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


class TestQueuedRecords:
    """Only TERMINAL rows are refreshed.

    manage-imports' `import_all` claims nothing -- `find_pending()` selects
    status='pending' and the row stays `pending` for the whole in-flight window.
    So overwriting a queued row's data races a worker that already read the old
    copy: it imports the stale record, then set_status writes the terminal status
    and NULLs data, discarding the update with no error.
    """

    @pytest.mark.parametrize("status", ["pending", "staged", "processing"])
    def test_a_queued_row_is_not_overwritten(self, import_db, status):
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])
        import_db.query(f"UPDATE import_item SET status='{status}'")

        result = batch.add_or_refresh_items([item("betterworldbooks:1", 9.99)])

        assert result["skipped_in_flight"] == 1
        assert result["refreshed"] == 0
        row = rows(import_db)["betterworldbooks:1"]
        assert row.status == status
        assert json.loads(row.data)["acquisitions"][0]["data"]["price"] == 1.25  # old copy intact

    @pytest.mark.parametrize("status", ["created", "modified", "found", "failed"])
    def test_a_terminal_row_is_refreshed(self, import_db, status):
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])
        import_db.query(f"UPDATE import_item SET status='{status}'")

        result = batch.add_or_refresh_items([item("betterworldbooks:1", 9.99)])

        assert result["refreshed"] == 1
        assert rows(import_db)["betterworldbooks:1"].status == "pending"

    def test_a_refresh_clears_a_stale_ol_key(self, import_db):
        """A refreshed row is no longer a completed import, so it must not keep
        pointing at an edition."""
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25)])
        import_db.query("UPDATE import_item SET status='created', ol_key='/books/OL7M'")

        batch.add_or_refresh_items([item("betterworldbooks:1", 9.99)])

        assert rows(import_db)["betterworldbooks:1"].ol_key is None


class TestBatchScoping:
    def test_another_batch_row_is_not_stolen(self, import_db):
        """The unique key is (batch_id, ia_id), so the same ia_id can legitimately
        exist in another importer's batch. An unscoped write would refresh -- and
        effectively steal -- that row, leaving this batch with none."""
        other = Batch.new("legacy-importer")
        other.add_items([item("betterworldbooks:1", 1.25)])
        import_db.query("UPDATE import_item SET status='created'")

        mine = Batch.new("bwb-opds")
        result = mine.add_or_refresh_items([item("betterworldbooks:1", 9.99)])

        assert result["added"] == 1, "should insert into MY batch, not touch the other one"
        by_batch = {r.batch_id: r for r in import_db.select("import_item")}
        assert len(by_batch) == 2
        assert json.loads(by_batch[other.id].data)["acquisitions"][0]["data"]["price"] == 1.25


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
        """One call covering every outcome: refreshed, unchanged, queued, added."""
        batch = Batch.new("bwb-opds")
        batch.add_or_refresh_items([item("betterworldbooks:1", 1.25), item("betterworldbooks:2", 2.0), item("betterworldbooks:4", 4.0)])
        # 1 and 2 have completed; 4 is still queued.
        import_db.query("UPDATE import_item SET status='created' WHERE ia_id IN ('betterworldbooks:1', 'betterworldbooks:2')")

        result = batch.add_or_refresh_items(
            [
                item("betterworldbooks:1", 9.99),  # changed  -> refreshed
                item("betterworldbooks:2", 2.0),  # same     -> unchanged
                item("betterworldbooks:4", 44.0),  # queued   -> skipped
                item("betterworldbooks:3", 3.0),  # new      -> added
            ]
        )

        assert result == {"added": 1, "refreshed": 1, "unchanged": 1, "skipped_in_flight": 1}
        assert len(list(import_db.select("import_item"))) == 4


@pytest.fixture
def batch_insert_db(monkeypatch):
    oldb = web.database(dbn="sqlite", db=":memory:")
    monkeypatch.setattr(core_db, "get_db", lambda: oldb)
    for ddl in (IMPORT_BATCH_DDL, IMPORT_ITEM_DDL):
        oldb.query(ddl)
    yield oldb
    oldb.ctx.db.close()


@pytest.fixture
def pg_import_db(pg_db, monkeypatch):
    oldb = web.database(**web.config.db_parameters)
    monkeypatch.setattr(core_db, "get_db", lambda: oldb)
    # Import tables live in the Infobase schema, outside pg_db's feature tables.
    schema = (Path(__file__).resolve().parents[2] / "core" / "infobase_schema.sql").read_text()
    for table in ("import_batch", "import_item"):
        start = schema.index(f"CREATE TABLE {table} (")
        end = schema.index("\n);", start) + len("\n);")
        oldb.query(schema[start:end])
    yield oldb
    oldb.ctx.db.close()


@pytest.mark.parametrize("method", ["add_items", "add_or_refresh_items"])
class TestBatchInserts:
    def test_duplicates_keep_first_row_and_insert_remaining_items(self, batch_insert_db, method):
        batch = Batch.new("duplicate-records")
        write = getattr(batch, method)
        first = item("betterworldbooks:1", 1.25)
        write([first, item("betterworldbooks:1", 9.99), item("betterworldbooks:2", 2.0)])
        before = rows(batch_insert_db)["betterworldbooks:1"]

        write([item("betterworldbooks:1", 50.0), item("betterworldbooks:3", 3.0)])

        stored = rows(batch_insert_db)
        assert len(stored) == 3
        assert stored["betterworldbooks:1"] == before
        assert json.loads(before.data) == first["data"]
        assert json.loads(stored["betterworldbooks:3"].data) == item("betterworldbooks:3", 3.0)["data"]

    def test_collision_after_read_preserves_existing_row(self, batch_insert_db, method, monkeypatch):
        batch = Batch.new("stale-read")
        query = batch_insert_db.query
        snapshots = []

        def insert_after_read(sql, *args, **kwargs):
            result = query(sql, *args, **kwargs)
            if str(sql).lstrip().startswith("SELECT") and "FROM import_item" in str(sql) and not snapshots:
                result = list(result)
                batch_insert_db.insert(
                    "import_item",
                    batch_id=batch.id,
                    ia_id="betterworldbooks:1",
                    status="created",
                    data='{"title": "Existing record"}',
                    submitter="original",
                    added_time="2020-01-01 00:00:00",
                    import_time="2020-01-02 00:00:00",
                    error="original error",
                    comments="original comments",
                    ol_key="/books/OL1M",
                )
                snapshot = {row.ia_id: row for row in query("SELECT * FROM import_item")}
                snapshots.append(snapshot["betterworldbooks:1"])
            return result

        monkeypatch.setattr(batch_insert_db, "query", insert_after_read)
        getattr(batch, method)([item("betterworldbooks:1", 9.99), item("betterworldbooks:2", 2.0)])

        stored = rows(batch_insert_db)
        assert len(stored) == 2
        assert stored["betterworldbooks:1"] == snapshots[0]
        assert json.loads(stored["betterworldbooks:2"].data) == item("betterworldbooks:2", 2.0)["data"]

    def test_one_parameterized_insert_for_the_whole_batch(self, batch_insert_db, method, monkeypatch):
        batch = Batch.new("bound-values")
        query = batch_insert_db.query
        inserts = []

        def capture_insert(sql, *args, **kwargs):
            if str(sql).lstrip().startswith("INSERT INTO import_item"):
                inserts.append((sql, kwargs.get("vars")))
            return query(sql, *args, **kwargs)

        monkeypatch.setattr(batch_insert_db, "query", capture_insert)
        identifier = "partner:O'Reilly; $price 日本語"
        record = {"ia_id": identifier, "status": "staged", "submitter": "O'Reilly", "data": {"title": "A 'quoted' book 日本語"}}
        getattr(batch, method)([record, record, item("betterworldbooks:2", 2.0)])

        assert len(inserts) == 1
        sql, params = inserts[0]
        assert "ON CONFLICT (batch_id, ia_id) DO NOTHING" in sql
        assert identifier not in sql
        assert identifier in params.values()
        stored = rows(batch_insert_db)
        assert len(stored) == 2
        assert stored[identifier].status == "staged"
        assert stored[identifier].submitter == record["submitter"]
        assert json.loads(stored[identifier].data) == record["data"]

    def test_empty_input_does_not_write(self, batch_insert_db, method, monkeypatch):
        batch = Batch.new("empty-input")

        def unexpected_query(*args, **kwargs):
            pytest.fail("Empty input must not query the database")

        monkeypatch.setattr(batch_insert_db, "query", unexpected_query)
        result = getattr(batch, method)([])
        if method == "add_items":
            assert result is None
        else:
            assert result == {"added": 0, "refreshed": 0, "unchanged": 0, "skipped_in_flight": 0}


class TestLegacyBatchInserts:
    def test_legacy_and_dict_items_can_share_one_insert(self, batch_insert_db):
        batch = Batch.new("mixed-input")
        record = {"ia_id": "partner:1", "status": "needs_review", "submitter": "patron", "data": {"title": "A Book"}}
        assert batch.add_items(["ocaid_1", record, "ocaid_1"]) is None
        batch.add_items(["ocaid_1", "ocaid_2"])

        stored = rows(batch_insert_db)
        assert len(stored) == 3
        assert stored["ocaid_1"].status == "pending"
        assert stored["ocaid_1"].data is None
        assert stored["ocaid_1"].submitter is None
        assert stored["partner:1"].status == "needs_review"
        assert stored["partner:1"].submitter == "patron"
        assert json.loads(stored["partner:1"].data) == record["data"]

    def test_add_items_keeps_global_deduplication(self, batch_insert_db):
        other = Batch.new("other-importer")
        other.add_items(["ocaid_1"])
        batch = Batch.new("new-importer")
        batch.add_items(["ocaid_1", "ocaid_2"])

        stored = rows(batch_insert_db)
        assert len(stored) == 2
        assert stored["ocaid_1"].batch_id == other.id
        assert stored["ocaid_2"].batch_id == batch.id
        assert batch.total_submitted == 2
        assert batch.total_queued == 1
        assert batch.items_skipped == {"ocaid_1"}


@pytest.mark.integration
class TestBatchInsertsPostgres(TestBatchInserts):
    @pytest.fixture
    def batch_insert_db(self, pg_import_db):
        return pg_import_db

    def test_concurrent_inserts_keep_every_unique_item(self, pg_import_db, method, monkeypatch):
        batch = Batch.new("concurrent-importers")
        query = pg_import_db.query
        barrier = Barrier(2, timeout=10)

        def read_before_either_insert(sql, *args, **kwargs):
            result = query(sql, *args, **kwargs)
            if str(sql).lstrip().startswith("SELECT") and "FROM import_item" in str(sql):
                result = list(result)
                barrier.wait()
            return result

        def write(index):
            try:
                # Each thread has its own web.py connection and Batch counters.
                with pg_import_db.transaction():
                    getattr(Batch(dict(batch)), method)([item("betterworldbooks:shared", index), item(f"betterworldbooks:{index}", index)])
            finally:
                pg_import_db.ctx.db.close()

        with monkeypatch.context() as patcher:
            patcher.setattr(pg_import_db, "query", read_before_either_insert)
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(write, [1, 2]))

        stored = rows(pg_import_db)
        assert set(stored) == {"betterworldbooks:shared", "betterworldbooks:1", "betterworldbooks:2"}
        assert all(row.status == "pending" for row in stored.values())
        assert all(row.added_time is not None for row in stored.values())


@pytest.mark.integration
class TestLegacyBatchInsertsPostgres(TestLegacyBatchInserts):
    @pytest.fixture
    def batch_insert_db(self, pg_import_db):
        return pg_import_db
