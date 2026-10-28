from pathlib import Path
import sqlite3
from unittest.mock import MagicMock, patch

from openlibrary.coverstore import db
from openlibrary.coverstore.schema import get_schema


def test_get_schema_postgres():
    sql = get_schema("postgres")
    assert "source character varying(255)" in sql
    assert "failed boolean default False" in sql
    assert "archived boolean default False" in sql
    assert "uploaded boolean default False" in sql
    assert "deleted boolean default False" in sql
    assert "create index cover_failed_idx on cover(failed);" in sql
    assert "create index cover_uploaded_idx on cover(uploaded);" in sql


def test_get_schema_sqlite_defaults():
    sql = get_schema("sqlite")
    con = sqlite3.connect(":memory:")
    con.executescript(sql)
    con.execute("INSERT INTO category(name) VALUES ('b');")
    con.execute("INSERT INTO cover(category_id, olid, filename) VALUES (1, 'OL1M', 'local.jpg');")
    row = con.execute("SELECT id, failed, uploaded, archived, deleted FROM cover;").fetchall()
    assert row == [(1, 0, 0, 0, 0)]

    # Archival selection returns the newly created row without explicit flags
    res = con.execute("SELECT id FROM cover WHERE failed=0 AND archived=0;").fetchall()
    assert res == [(1,)]


def test_schema_sql_defaults():
    sql_path = Path(__file__).parent.parent / "schema.sql"
    sql = sql_path.read_text(encoding="utf-8")
    assert "failed boolean default false" in sql
    assert "archived boolean default false" in sql
    assert "uploaded boolean default false" in sql
    assert "deleted boolean default false" in sql


def test_db_new_cover_initializes_flags():
    mock_db = MagicMock()
    mock_db.insert.return_value = 42

    with (
        patch.object(db, "get_category_id", return_value=1),
        patch.object(db, "getdb", return_value=mock_db),
    ):
        cid = db.new(
            category="b",
            olid="OL1M",
            filename="test.jpg",
            filename_s="test_s.jpg",
            filename_m="test_m.jpg",
            filename_l="test_l.jpg",
            author="Author",
            ip="127.0.0.1",
            source_url="http://example.com/cover.jpg",
            width=200,
            height=300,
        )
        assert cid == 42
        mock_db.insert.assert_any_call(
            "cover",
            category_id=1,
            filename="test.jpg",
            filename_s="test_s.jpg",
            filename_m="test_m.jpg",
            filename_l="test_l.jpg",
            olid="OL1M",
            author="Author",
            ip="127.0.0.1",
            source_url="http://example.com/cover.jpg",
            width=200,
            height=300,
            created=mock_db.insert.call_args_list[0][1]["created"],
            last_modified=mock_db.insert.call_args_list[0][1]["last_modified"],
            deleted=False,
            archived=False,
            failed=False,
            uploaded=False,
        )
