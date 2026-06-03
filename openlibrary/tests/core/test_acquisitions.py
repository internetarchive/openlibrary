from typing import Final

import pytest
import web

from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.db import get_db

# sqlite-friendly DDL (Postgres uses serial/jsonb; sqlite is typeless).
ACQUISITIONS_DDL: Final = """
CREATE TABLE acquisitions (
    id integer primary key,
    work_id integer not null,
    edition_id integer not null,
    provider_name text not null,
    data text not null default '{}',
    created timestamp default current_timestamp,
    updated timestamp default current_timestamp,
    UNIQUE (edition_id, provider_name)
);
"""

SEED: Final = [
    {"id": 1, "work_id": 10, "edition_id": 100, "provider_name": "betterworldbooks", "data": '{"price": "5.00"}'},
    {"id": 2, "work_id": 10, "edition_id": 101, "provider_name": "betterworldbooks", "data": "{}"},
    {"id": 3, "work_id": 20, "edition_id": 200, "provider_name": "lenny", "data": "{}"},
]


@pytest.fixture(scope="module")
def setup_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    db.query(ACQUISITIONS_DDL)
    yield db
    db.query("delete from acquisitions;")


@pytest.fixture
def acquisitions_db(setup_db):
    setup_db.multiple_insert("acquisitions", SEED)
    yield setup_db
    setup_db.query("delete from acquisitions;")


class TestAcquisition:
    def test_get_by_edition_all(self, acquisitions_db):
        rows = Acquisition.get_by_edition(100)
        assert len(rows) == 1
        assert rows[0].data == {"price": "5.00"}

    def test_get_by_edition_provider(self, acquisitions_db):
        rows = Acquisition.get_by_edition(100, "betterworldbooks")
        assert len(rows) == 1
        assert Acquisition.get_by_edition(100, "lenny") == []

    def test_get_by_work(self, acquisitions_db):
        assert [r.edition_id for r in Acquisition.get_by_work(10)] == [100, 101]

    def test_upsert_insert(self, acquisitions_db):
        row = Acquisition.upsert(30, 300, "standard_ebooks", data={"format": "epub"})
        assert row is not None
        assert row.data == {"format": "epub"}
        assert len(Acquisition.get_by_work(30)) == 1

    def test_upsert_update(self, acquisitions_db):
        # Second upsert for same (edition, provider) updates, not duplicates.
        Acquisition.upsert(10, 100, "betterworldbooks", data={"price": "9.99"})
        rows = Acquisition.get_by_edition(100, "betterworldbooks")
        assert len(rows) == 1
        assert rows[0].data == {"price": "9.99"}

    def test_update_work_id(self, acquisitions_db):
        # Work merge: 10 -> 99. Both editions' rows follow.
        Acquisition.update_work_id(10, 99)
        assert Acquisition.get_by_work(10) == []
        assert {r.edition_id for r in Acquisition.get_by_work(99)} == {100, 101}

    def test_update_edition_id_remap(self, acquisitions_db):
        # Edition merge with no clash: 200 -> 201.
        result = Acquisition.update_edition_id(200, 201)
        assert result == {"rows_changed": 1, "rows_deleted": 0}
        assert Acquisition.get_by_edition(200) == []
        assert len(Acquisition.get_by_edition(201)) == 1

    def test_update_edition_id_conflict_deletes(self, acquisitions_db):
        # Editions 100 and 101 both have a betterworldbooks row; merging
        # 100 -> 101 would violate the unique constraint, so 100's row drops.
        result = Acquisition.update_edition_id(100, 101)
        assert result == {"rows_changed": 0, "rows_deleted": 1}
        assert Acquisition.get_by_edition(100) == []
        assert len(Acquisition.get_by_edition(101, "betterworldbooks")) == 1
