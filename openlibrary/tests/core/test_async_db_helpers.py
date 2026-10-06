"""Tests for the single-statement helpers in async_db.

Model tests patch these helpers and assert on the queries and params they
pass; these tests pin what the helpers themselves do with a connection --
query recording, commit-on-clean-exit, and row mapping through a real
psycopg row factory.
"""

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from openlibrary.core import async_db
from openlibrary.tests.core.async_db_fakes import FakeConnection, FakeConnectionContext


@dataclass
class FakeGoal:
    """A stand-in model, so the tests run the real class_row mapping."""

    username: str
    year: int
    target: int


# Column order of the SELECT below, for class_row to map by name.
GOAL_COLUMNS = ("username", "year", "target")


def _patched_connection(conn: FakeConnection):
    """Patch async_db's connection() so helpers run against ``conn``."""
    return patch("openlibrary.core.async_db.connection", return_value=FakeConnectionContext(conn))


@pytest.mark.asyncio
async def test_execute_records_the_query_and_commits():
    conn = FakeConnection()
    with _patched_connection(conn):
        await async_db.execute("DELETE FROM t WHERE id = %(id)s", {"id": 3})

    ((query, params),) = conn.executions
    assert query == "DELETE FROM t WHERE id = %(id)s"
    assert params == {"id": 3}
    assert conn.committed


@pytest.mark.asyncio
async def test_fetch_all_returns_dict_rows_and_commits():
    conn = FakeConnection(rows=[{"username": "testuser"}, {"username": "other"}])
    with _patched_connection(conn):
        rows = await async_db.fetch_all("SELECT username FROM t")

    assert rows == [{"username": "testuser"}, {"username": "other"}]
    ((query, params),) = conn.executions
    assert query == "SELECT username FROM t"
    assert params is None
    assert conn.committed


@pytest.mark.asyncio
async def test_fetch_all_maps_rows_through_the_row_factory():
    conn = FakeConnection(rows=[("testuser", 2026, 25), ("other", 2025, 7)], columns=GOAL_COLUMNS)
    with _patched_connection(conn):
        rows = await async_db.fetch_all(
            "SELECT username, year, target FROM t",
            row_factory=async_db.class_row(FakeGoal),
        )

    assert rows == [FakeGoal("testuser", 2026, 25), FakeGoal("other", 2025, 7)]
    assert conn.committed


@pytest.mark.asyncio
async def test_fetch_one_returns_the_first_row():
    conn = FakeConnection(rows=[{"username": "testuser"}, {"username": "other"}])
    with _patched_connection(conn):
        row = await async_db.fetch_one("SELECT username FROM t", {"x": 1})

    assert row == {"username": "testuser"}
    assert conn.committed


@pytest.mark.asyncio
async def test_fetch_one_returns_none_without_rows():
    conn = FakeConnection()
    with _patched_connection(conn):
        assert await async_db.fetch_one("SELECT username FROM t WHERE false") is None


@pytest.mark.asyncio
async def test_fetch_val_returns_the_first_column_of_the_first_row():
    conn = FakeConnection(rows=[(3, "ignored-second-column")])
    with _patched_connection(conn):
        value = await async_db.fetch_val("SELECT count(*), other FROM t")

    assert value == 3
    assert conn.committed


@pytest.mark.asyncio
async def test_fetch_val_returns_none_without_rows():
    conn = FakeConnection()
    with _patched_connection(conn):
        assert await async_db.fetch_val("SELECT count(*) FROM t WHERE false") is None
