from typing import Final

import pytest
import web

from openlibrary.core.db import get_db
from openlibrary.core.staged import PROMOTED, STAGED, StagedRecord

# sqlite-friendly DDL (Postgres uses serial/jsonb; sqlite is typeless).
STAGED_RECORD_DDL: Final = """
CREATE TABLE tbp_staged_record (
    id integer primary key,
    provider_name text not null,
    local_id text not null,
    record text not null,
    acquisition text default null,
    status text not null default 'staged',
    created timestamp default current_timestamp,
    updated timestamp default current_timestamp,
    UNIQUE (provider_name, local_id)
);
"""

RECORD: Final = {"title": "A Book", "isbn_13": ["9781737408802"], "source_records": ["bwb:9781737408802"]}
ACQ: Final = {"price": {"currency": "USD", "value": 1.25}, "formats": ["application/epub+zip"]}


@pytest.fixture
def staged_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    db.query("DROP TABLE IF EXISTS tbp_staged_record;")
    db.query(STAGED_RECORD_DDL)
    yield db
    db.query("DROP TABLE IF EXISTS tbp_staged_record;")


class TestStagedRecord:
    def test_upsert_creates_then_reads(self, staged_db):
        row = StagedRecord.upsert("bwb", "urn:isbn:9781737408802", RECORD, acquisition=ACQ)
        assert row is not None
        assert row.status == STAGED
        # record and acquisition round-trip as dicts.
        assert row.record["source_records"] == ["bwb:9781737408802"]
        assert row.acquisition["price"]["value"] == 1.25

    def test_upsert_is_idempotent_and_refreshes(self, staged_db):
        StagedRecord.upsert("bwb", "urn:isbn:9781737408802", RECORD, acquisition=ACQ)
        # Re-harvest with a changed price -> same row, refreshed, still one row.
        changed = {"price": {"currency": "USD", "value": 3.5}}
        StagedRecord.upsert("bwb", "urn:isbn:9781737408802", RECORD, acquisition=changed)
        rows = list(staged_db.select("tbp_staged_record"))
        assert len(rows) == 1
        assert StagedRecord.find("bwb", "urn:isbn:9781737408802").acquisition["price"]["value"] == 3.5

    def test_pending_excludes_promoted(self, staged_db):
        StagedRecord.upsert("bwb", "a", RECORD)
        StagedRecord.upsert("bwb", "b", RECORD)
        assert {r.local_id for r in StagedRecord.pending()} == {"a", "b"}
        b = StagedRecord.find("bwb", "b")
        assert StagedRecord.set_status(b.id, PROMOTED) == 1
        # Promoted rows drop out of the promotion queue.
        assert [r.local_id for r in StagedRecord.pending()] == ["a"]

    def test_acquisition_is_optional(self, staged_db):
        row = StagedRecord.upsert("bwb", "no-acq", RECORD)
        assert row.acquisition is None
