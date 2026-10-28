from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock

import psycopg2
import pytest
import web
from web.db import DB, Transaction

from openlibrary.utils import legacy_db


class Connection:
    """Minimal driver; exercise web.py's actual query and transaction machinery."""

    def __init__(self):
        self.closed = 0
        self.statements = []
        self.drop_on_execute = False
        self.drop_on_commit = False
        self.drop_on_rollback = False

    def cursor(self):
        if self.closed:
            raise psycopg2.InterfaceError("connection already closed")
        return Cursor(self)

    def commit(self):
        self._finish(self.drop_on_commit)

    def rollback(self):
        self._finish(self.drop_on_rollback)

    def _finish(self, dropped):
        if self.closed:
            raise psycopg2.InterfaceError("connection already closed")
        if dropped:
            self.closed = 2
            raise psycopg2.OperationalError("server closed the connection unexpectedly")


class Cursor:
    description = None
    rowcount = 1

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params):
        self.connection.statements.append(query)
        if self.connection.drop_on_execute:
            self.connection.closed = 2
            raise psycopg2.OperationalError("server closed the connection unexpectedly")


@pytest.fixture
def recovery(monkeypatch):
    # Other FastAPI tests can install the process-wide hooks too. Restore every
    # method and the installation flag so this suite does not change their state.
    monkeypatch.setattr(legacy_db, "_installed", False)
    for cls, name in [(DB, "_getctx"), (DB, "ctx"), (Transaction, "commit"), (Transaction, "rollback")]:
        monkeypatch.setattr(cls, name, getattr(cls, name))
    legacy_db.install_connection_recovery()


@pytest.fixture
def db(recovery):
    db = DB(None, {"pooling": False})
    db.printing = False
    db._connect = Mock(side_effect=lambda keywords: Connection())
    return db


def test_closed_connection_reconnects_on_next_query(db):
    db.query("SELECT 1")
    first = db.ctx.db
    first.closed = 1

    assert db.query("SELECT 1") == 1
    assert db.ctx.db is not first
    assert db._connect.call_count == 2


def test_healthy_connection_is_reused(db):
    db.query("SELECT 1")
    first = db.ctx.db
    db.query("SELECT 2")
    assert db.ctx.db is first
    assert db._connect.call_count == 1


def test_recovers_even_when_rollback_on_closed_connection_raises(db):
    assert not db.has_pooling
    first = db.ctx.db
    first.closed = 1
    with pytest.raises(psycopg2.InterfaceError):
        db._ctx.rollback()
    # web.py's non-pooled rollback does not unload the connection, and even
    # pooled rollback would skip unloading when the driver's rollback raises.
    assert db._ctx.db is first
    assert db.query("SELECT 1") == 1
    assert db.ctx.db is not first


@pytest.mark.parametrize("query", ["SELECT 1", "INSERT INTO example VALUES (1)"])
def test_drop_during_execute_is_not_retried(db, query):
    first = db.ctx.db
    first.drop_on_execute = True
    with pytest.raises(psycopg2.OperationalError):
        db.query(query)
    assert first.statements == [query]
    # web.py may access ctx again to roll back, discovering the dead connection.
    assert db.query("SELECT 2") == 1
    assert db.ctx.db.statements == ["SELECT 2"]


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("detected", [False, True])
def test_failed_transaction_unwinds_without_reconnecting_or_replaying(db, nested, detected):
    def write_in_transaction():
        with db.transaction():
            if nested:
                db.transaction()
            first = db.ctx.db
            if detected:
                first.closed = 1
            else:
                first.drop_on_execute = True
            try:
                db.query("INSERT INTO example VALUES (1)")
            finally:
                assert db._connect.call_count == 1

    with pytest.raises(psycopg2.Error):
        write_in_transaction()

    assert not db._ctx.get("transactions")
    assert "db" not in db._ctx
    assert db.query("SELECT 2") == 1
    assert db._connect.call_count == 2
    assert db.ctx.db.statements == ["SELECT 2"]


def test_closed_transaction_stays_failed_until_rollback(db):
    transaction = db.transaction()
    db.ctx.db.closed = 1
    for _ in range(2):
        with pytest.raises(psycopg2.InterfaceError):
            db.query("INSERT INTO example VALUES (1)")
        assert db._connect.call_count == 1
    transaction.rollback()
    assert db.query("SELECT 2") == 1


@pytest.mark.parametrize("nested", [False, True])
def test_drop_during_commit_does_not_leave_stale_transaction(db, nested):
    def commit_transaction():
        with db.transaction():
            transaction = db.transaction() if nested else None
            first = db.ctx.db
            if nested:
                first.drop_on_execute = True  # RELEASE SAVEPOINT
                transaction.commit()
            else:
                first.drop_on_commit = True

    with pytest.raises(psycopg2.OperationalError):
        commit_transaction()
    assert "db" not in db._ctx
    assert not db._ctx.transactions
    assert db.query("SELECT 2") == 1


def test_drop_during_rollback_does_not_leave_stale_transaction(db):
    transaction = db.transaction()
    db.ctx.db.drop_on_rollback = True
    with pytest.raises(psycopg2.OperationalError):
        transaction.rollback()
    assert "db" not in db._ctx
    assert not db._ctx.transactions
    assert db.query("SELECT 2") == 1


def test_healthy_transactions_and_nested_savepoints(db):
    with db.transaction(), db.transaction():
        db.query("INSERT INTO example VALUES (1)")
    assert not db.ctx.transactions
    assert db._connect.call_count == 1
    assert db.ctx.db.statements == ["SAVEPOINT webpy_sp_1", "INSERT INTO example VALUES (1)", "RELEASE SAVEPOINT webpy_sp_1"]


def test_thread_connections_recover_independently(db):
    barrier = Barrier(4)

    def worker():
        db.query("SELECT 1")
        first = db.ctx.db
        barrier.wait(timeout=10)
        first.closed = 1
        db.query("SELECT 2")
        return first, db.ctx.db

    with ThreadPoolExecutor(max_workers=4) as executor:
        connections = list(executor.map(lambda _: worker(), range(4)))
    assert len({id(conn) for pair in connections for conn in pair}) == 8
    assert all(first.closed and not second.closed for first, second in connections)


def test_sqlite_connections_without_closed_attribute_are_unchanged(recovery):
    db = web.database(dbn="sqlite", db=":memory:", pooling=False)
    try:
        with db.transaction():
            db.query("CREATE TABLE example(value INTEGER)")
            db.query("INSERT INTO example VALUES (1)")
        assert db.query("SELECT value FROM example")[0].value == 1
    finally:
        db.ctx.db.close()


def test_installation_is_idempotent(recovery):
    methods = DB._getctx, DB.ctx, Transaction.commit, Transaction.rollback
    legacy_db.install_connection_recovery()
    assert (DB._getctx, DB.ctx, Transaction.commit, Transaction.rollback) == methods
