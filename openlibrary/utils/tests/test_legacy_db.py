from unittest.mock import Mock

import psycopg2
import pytest
from web import DB

from openlibrary.utils import legacy_db


class Connection:
    """Fake psycopg2 connection, so the tests run web.py's real query and transaction code."""

    def __init__(self):
        self.closed = 0
        self.statements = []
        self.drop_on = None  # "execute", "commit" or "rollback": simulate the server going away

    def cursor(self):
        if self.closed:
            raise psycopg2.InterfaceError("connection already closed")
        return self

    def execute(self, query, params):
        self.statements.append(query)
        self._maybe_drop("execute")

    def commit(self):
        self._maybe_drop("commit")

    def rollback(self):
        self._maybe_drop("rollback")

    def _maybe_drop(self, step):
        if self.closed:
            raise psycopg2.InterfaceError("connection already closed")
        if self.drop_on == step:
            self.closed = 2
            raise psycopg2.OperationalError("server closed the connection unexpectedly")

    description = None
    rowcount = 1


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(legacy_db, "_installed", False)
    monkeypatch.setattr(DB, "_load_context", DB._load_context)
    legacy_db.install_connection_recovery()
    db = DB(None, {"pooling": False})
    db.printing = False
    db._connect = Mock(side_effect=lambda keywords: Connection())
    return db


@pytest.mark.parametrize("query", ["SELECT 1", "INSERT INTO t VALUES (1)"])
def test_dropped_connection_reconnects_without_retrying(db, query):
    db.query("SELECT 0")
    first = db.ctx.db
    first.drop_on = "execute"
    with pytest.raises(psycopg2.OperationalError):
        db.query(query)
    assert first.statements == ["SELECT 0", query]
    db.query("SELECT 2")
    assert db.ctx.db is not first
    assert db.ctx.db.statements == ["SELECT 2"]


def test_healthy_connection_is_reused(db):
    db.query("SELECT 1")
    db.query("SELECT 2")
    assert db._connect.call_count == 1


@pytest.mark.parametrize("drop_on", ["execute", "commit"])
def test_dropped_transaction_fails_then_reconnects(db, drop_on):
    def write():
        with db.transaction():
            db.ctx.db.drop_on = drop_on
            db.query("INSERT INTO t VALUES (1)")

    with pytest.raises(psycopg2.OperationalError):
        write()
    assert not db._ctx.get("transactions")
    db.query("SELECT 2")
    assert db._connect.call_count == 2


def test_savepoint_drop_keeps_outer_transaction_failing(db):
    outer = db.transaction()
    savepoint = db.transaction()
    db.ctx.db.drop_on = "execute"
    with pytest.raises(psycopg2.Error):
        db.query("INSERT INTO t VALUES (1)")
    with pytest.raises(psycopg2.InterfaceError):
        savepoint.rollback()
    # The caller swallowed the savepoint's error; the outer transaction must not
    # carry on in autocommit on a new connection.
    with pytest.raises(psycopg2.InterfaceError):
        db.query("INSERT INTO t VALUES (2)")
    outer.rollback()
    db.query("SELECT 2")
    assert db._connect.call_count == 2


def test_drop_during_rollback_reconnects(db):
    transaction = db.transaction()
    db.ctx.db.drop_on = "rollback"
    with pytest.raises(psycopg2.OperationalError):
        transaction.rollback()
    db.query("SELECT 2")
    assert db._connect.call_count == 2
