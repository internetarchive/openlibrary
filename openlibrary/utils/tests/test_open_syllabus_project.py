import sqlite3
from contextlib import closing

import pytest

from openlibrary.utils import open_syllabus_project as osp


@pytest.fixture(autouse=True)
def reset_location():
    yield
    osp.set_osp_dump_location(None)


def test_no_location_returns_none():
    osp.set_osp_dump_location(None)
    assert osp.get_total_by_olid("/works/OL1W") is None


def test_missing_file_returns_none_without_creating_it(tmp_path):
    db_file = tmp_path / "osp_totals.db"
    osp.set_osp_dump_location(db_file)
    assert osp.get_total_by_olid("/works/OL1W") is None
    assert not db_file.exists()


def test_reads_total_from_dump(tmp_path):
    db_file = tmp_path / "osp_totals.db"
    with closing(sqlite3.connect(db_file)) as conn:
        conn.execute("CREATE TABLE data (olid INTEGER PRIMARY KEY, total INTEGER)")
        conn.execute("INSERT INTO data VALUES (123, 42)")
        conn.commit()
    osp.set_osp_dump_location(db_file)
    assert osp.get_total_by_olid("/works/OL123W") == 42
    assert osp.get_total_by_olid("OL999W") is None
