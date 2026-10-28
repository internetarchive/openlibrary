from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import web
from psycopg.errors import UniqueViolation

from openlibrary.core.async_db import connection, fetch_all
from openlibrary.core.bestbook import Bestbook
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.bookshelves_events import BookshelvesEvents
from openlibrary.core.db import get_db
from openlibrary.core.observations import Observations
from openlibrary.core.ratings import Ratings


@pytest.fixture
def mocked_async_connection(monkeypatch):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=SimpleNamespace(rowcount=2))
    conn.rollback = AsyncMock()

    @asynccontextmanager
    async def connection():
        yield conn

    monkeypatch.setattr("openlibrary.core.db.connection", connection)
    return conn


READING_LOG_DDL = """
CREATE TABLE bookshelves_books (
    username text NOT NULL,
    work_id integer NOT NULL,
    bookshelf_id INTEGER references bookshelves(id) ON DELETE CASCADE ON UPDATE CASCADE,
    edition_id integer default null,
    primary key (username, work_id, bookshelf_id)
);
"""

BOOKNOTES_DDL = """
CREATE TABLE booknotes (
    username text NOT NULL,
    work_id integer NOT NULL,
    edition_id integer NOT NULL default -1,
    notes text NOT NULL,
    primary key (username, work_id, edition_id)
);
"""

BOOKSHELVES_EVENTS_DDL = """
CREATE TABLE bookshelves_events (
    id serial primary key,
    username text not null,
    work_id integer not null,
    edition_id integer not null,
    event_type integer not null,
    event_date text not null,
    updated timestamp
);
"""


class TestUpdateWorkID:
    @classmethod
    def setup_class(cls):
        web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
        db = get_db()
        db.query(READING_LOG_DDL)
        db.query(BOOKNOTES_DDL)

    @classmethod
    def teardown_class(cls):
        db = get_db()
        db.query("delete from bookshelves_books;")
        db.query("delete from booknotes;")

    def setup_method(self, method):
        self.db = get_db()
        self.source_book = {
            "username": "@cdrini",
            "work_id": "1",
            "edition_id": "1",
            "bookshelf_id": "1",
        }
        assert not list(self.db.select("bookshelves_books"))
        self.db.insert("bookshelves_books", **self.source_book)

    def teardown_method(self):
        self.db.query("delete from bookshelves_books;")

    def test_update_collision(self):
        existing_book = {
            "username": "@cdrini",
            "work_id": "2",
            "edition_id": "2",
            "bookshelf_id": "1",
        }
        self.db.insert("bookshelves_books", **existing_book)
        assert len(list(self.db.select("bookshelves_books"))) == 2
        Bookshelves.update_work_id(self.source_book["work_id"], existing_book["work_id"])
        assert list(
            self.db.select(
                "bookshelves_books",
                where={"username": "@cdrini", "work_id": "2", "edition_id": "2"},
            )
        ), "failed to update 1 to 2"
        assert not list(
            self.db.select(
                "bookshelves_books",
                where={"username": "@cdrini", "work_id": "1", "edition_id": "1"},
            )
        ), "old work_id 1 present"

    def test_update_simple(self):
        assert len(list(self.db.select("bookshelves_books"))) == 1
        Bookshelves.update_work_id(self.source_book["work_id"], "2")

    def test_no_allow_delete_on_conflict(self):
        rows = [
            {"username": "@mek", "work_id": 1, "edition_id": 1, "notes": "Jimmeny"},
            {"username": "@mek", "work_id": 2, "edition_id": 1, "notes": "Cricket"},
        ]
        self.db.multiple_insert("booknotes", rows)
        resp = Booknotes.update_work_id("1", "2")
        assert resp == {"rows_changed": 0, "rows_deleted": 0, "failed_deletes": 1}
        assert [dict(row) for row in self.db.select("booknotes")] == rows


@pytest.mark.asyncio
async def test_update_username_uses_async_connection_and_rolls_back_for_test_mode(mocked_async_connection):
    rows_changed = await Ratings.update_username("alice", "anonymous-alice", _test=True)

    assert rows_changed == 2
    query, params = mocked_async_connection.execute.await_args.args
    assert query == "UPDATE ratings SET username = %(new_username)s WHERE username = %(username)s"
    assert params == {"username": "alice", "new_username": "anonymous-alice"}
    mocked_async_connection.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_username_unique_conflict_rolls_back_and_returns_zero(mocked_async_connection):
    mocked_async_connection.execute.side_effect = UniqueViolation("duplicate username")

    rows_changed = await Ratings.update_username("alice", "anonymous-alice")

    assert rows_changed == 0
    mocked_async_connection.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_all_by_username_uses_async_connection_and_rolls_back_for_test_mode(mocked_async_connection):
    rows_deleted = await Booknotes.delete_all_by_username("alice", _test=True)

    assert rows_deleted == 2
    query, params = mocked_async_connection.execute.await_args.args
    assert query == "DELETE FROM booknotes WHERE username = %(username)s"
    assert params == {"username": "alice"}
    mocked_async_connection.rollback.assert_awaited_once()


@pytest.mark.integration
class TestCommonExtrasAsync:
    @pytest.mark.asyncio
    async def test_username_updates_and_delete(self, pg_db):
        username = "@anonymize-test"
        new_username = "@anonymous-test"
        async with connection() as conn:
            await conn.execute("INSERT INTO booknotes (username, work_id, notes) VALUES (%s, 1, 'note')", (username,))
            await conn.execute("INSERT INTO ratings (username, work_id, rating) VALUES (%s, 1, 5)", (username,))
            await conn.execute(
                "INSERT INTO observations (username, work_id, observation_type, observation_value) VALUES (%s, 1, 1, 1)",
                (username,),
            )
            await conn.execute("INSERT INTO bookshelves_books (username, work_id, bookshelf_id) VALUES (%s, 1, 1)", (username,))
            await conn.execute(
                "INSERT INTO bestbooks (username, work_id, topic, comment) VALUES (%s, 1, 'test-topic', 'test')",
                (username,),
            )

        models = (Ratings, Observations, Bookshelves, Bestbook)
        for model in models:
            assert await model.update_username(username, new_username, _test=True) == 1
        assert await Booknotes.delete_all_by_username(username, _test=True) == 1
        for table in ("booknotes", "ratings", "observations", "bookshelves_books", "bestbooks"):
            assert await fetch_all(f"SELECT 1 FROM {table} WHERE username = %(username)s", {"username": username})

        for model in models:
            assert await model.update_username(username, new_username) == 1
        assert await Booknotes.delete_all_by_username(username) == 1
        assert not await fetch_all("SELECT 1 FROM booknotes WHERE username = %(username)s", {"username": username})
        for table in ("ratings", "observations", "bookshelves_books", "bestbooks"):
            assert len(await fetch_all(f"SELECT 1 FROM {table} WHERE username = %(username)s", {"username": new_username})) == 1


BOOKSHELVES_EVENTS_SETUP_ROWS = [
    {
        "id": 1,
        "username": "@kilgore_trout",
        "work_id": 1,
        "edition_id": 2,
        "event_type": 1,
        "event_date": "2022-04-17",
    },
    {
        "id": 2,
        "username": "@kilgore_trout",
        "work_id": 1,
        "edition_id": 2,
        "event_type": 2,
        "event_date": "2022-05-10",
    },
    {
        "id": 3,
        "username": "@kilgore_trout",
        "work_id": 1,
        "edition_id": 2,
        "event_type": 3,
        "event_date": "2022-06-20",
    },
    {
        "id": 4,
        "username": "@billy_pilgrim",
        "work_id": 3,
        "edition_id": 4,
        "event_type": 1,
        "event_date": "2020",
    },
    {
        "id": 5,
        "username": "@eliot_rosewater",
        "work_id": 3,
        "edition_id": 4,
        "event_type": 3,
        "event_date": "2019-08-20",
    },
    {
        "id": 6,
        "username": "@eliot_rosewater",
        "work_id": 3,
        "edition_id": 4,
        "event_type": 3,
        "event_date": "2019-10",
    },
]


class TestCheckIns:
    @classmethod
    def setup_class(cls):
        web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
        db = get_db()
        db.query(BOOKSHELVES_EVENTS_DDL)

    def setup_method(self):
        self.db = get_db()
        self.db.multiple_insert("bookshelves_events", BOOKSHELVES_EVENTS_SETUP_ROWS)

    def teardown_method(self):
        self.db.query("delete from bookshelves_events;")

    def test_update_event_date(self):
        assert len(list(self.db.select("bookshelves_events", where={"id": 1}))) == 1
        row = self.db.select("bookshelves_events", where={"id": 1})[0]
        assert row["event_date"] == "2022-04-17"
        new_date = "1999-01-01"
        BookshelvesEvents.update_event_date(1, new_date)
        row = self.db.select("bookshelves_events", where={"id": 1})[0]
        assert row["event_date"] == new_date

    def test_delete_by_username(self):
        assert len(list(self.db.select("bookshelves_events"))) == 6
        assert len(list(self.db.select("bookshelves_events", where={"username": "@kilgore_trout"}))) == 3
        BookshelvesEvents.delete_by_username("@kilgore_trout")
        assert len(list(self.db.select("bookshelves_events"))) == 3
        assert len(list(self.db.select("bookshelves_events", where={"username": "@kilgore_trout"}))) == 0

    def test_get_latest_event_date(self):
        assert BookshelvesEvents.get_latest_event_date("@eliot_rosewater", 3, 3)["event_date"] == "2019-10"
        assert BookshelvesEvents.get_latest_event_date("@eliot_rosewater", 3, 3)["id"] == 6
        assert BookshelvesEvents.get_latest_event_date("@eliot_rosewater", 3, 1) is None
