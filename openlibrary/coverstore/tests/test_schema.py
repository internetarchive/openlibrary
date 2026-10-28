import sqlite3

from openlibrary.coverstore.schema import get_schema


def test_get_schema_postgres():
    sql = get_schema("postgres")
    assert "source character varying(255)" in sql
    assert "failed boolean" in sql
    assert "uploaded boolean" in sql
    assert "create index cover_failed_idx on cover(failed);" in sql
    assert "create index cover_uploaded_idx on cover(uploaded);" in sql


def test_get_schema_sqlite():
    sql = get_schema("sqlite")
    con = sqlite3.connect(":memory:")
    con.executescript(sql)
    cursor = con.execute("SELECT id, failed, uploaded, source, archived, deleted FROM cover WHERE failed=0 AND uploaded=0;")
    assert cursor.fetchall() == []
