import re
import sqlite3
from pathlib import Path

import pytest

from openlibrary.coverstore.schema import get_schema

SCHEMA_SQL = (Path(__file__).parents[1] / "schema.sql").read_text()


def schema_sql_columns(table: str) -> list[str]:
    match = re.search(rf"create table {table} \((.*?)\n\);", SCHEMA_SQL, re.DOTALL)
    assert match
    return [line.split()[0] for line in match.group(1).strip().splitlines()]


def schema_sql_indexed_columns(table: str) -> set[str]:
    return set(re.findall(rf"create index \w+ on {table} ?\((\w+)\)", SCHEMA_SQL, re.IGNORECASE))


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(get_schema("sqlite"))
    yield conn
    conn.close()


@pytest.mark.parametrize("table", ["category", "cover", "log"])
def test_get_schema_matches_schema_sql(db, table):
    columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
    indexed_columns = {
        column[2] for index in db.execute(f"PRAGMA index_list({table})") for column in db.execute(f"PRAGMA index_info({index[1]})") if index[3] == "c"
    }

    assert columns == schema_sql_columns(table)
    assert indexed_columns == schema_sql_indexed_columns(table)


def test_get_schema_postgres_has_cover_state_columns():
    sql = get_schema("postgres")

    assert "failed boolean" in sql
    assert "uploaded boolean" in sql
    assert "source character varying" in sql
