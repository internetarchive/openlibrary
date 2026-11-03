"""The Solr updater's transaction-table source, against a real Infobase schema.

Writers use their own psycopg connections so tests can hold a transaction open
while the reader polls, the way concurrent Infobase saves do.
"""

import asyncio
import datetime as dt
import json
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import web
from pytest_postgresql import factories
from pytest_postgresql.janitor import DatabaseJanitor

from openlibrary.core import async_db
from scripts.solr_updater.transaction_log import ForceUpdates, TransactionLog, transaction_id_at

_INFOBASE_SCHEMA = Path(__file__).resolve().parents[2] / "core" / "infobase_schema.sql"

infobase_proc = factories.postgresql_proc(port=None, load=[_INFOBASE_SCHEMA])


@pytest.fixture
def infobase_db(infobase_proc):
    dbname = f"test_{uuid4().hex[:8]}"
    params = {"user": infobase_proc.user, "host": infobase_proc.host, "port": infobase_proc.port, "password": infobase_proc.password or ""}
    with DatabaseJanitor(dbname=dbname, template_dbname=infobase_proc.template_dbname, **params):
        web.config.db_parameters = {
            "dbn": "postgres",
            "db": dbname,
            "user": params["user"],
            "pw": params["password"],
            "host": params["host"],
            "port": params["port"],
        }
        with async_db._entries_lock:
            async_db._entries.clear()
        yield lambda: psycopg.connect(dbname=dbname, **params)
        with async_db._entries_lock:
            async_db._entries.clear()
        web.config.db_parameters = {}


def save(conn, docs: list[dict], created: dt.datetime | None = None) -> int:
    """Write docs the way Infobase's SaveImpl does (without committing): thing, transaction, version, data."""
    changes, rows = [], []
    for doc in docs:
        if row := conn.execute("SELECT id, latest_revision FROM thing WHERE key = %s", (doc["key"],)).fetchone():
            thing_id, revision = row[0], row[1] + 1
            conn.execute("UPDATE thing SET latest_revision = %s WHERE id = %s", (revision, thing_id))
        else:
            revision = 1
            thing_id = conn.execute("INSERT INTO thing (key) VALUES (%s) RETURNING id", (doc["key"],)).fetchone()[0]
        changes.append({"key": doc["key"], "revision": revision})
        rows.append((thing_id, revision, doc))
    tx_id = conn.execute(
        "INSERT INTO transaction (action, changes, created) VALUES ('save_many', %s, %s) RETURNING id",
        (json.dumps(changes), created or dt.datetime.now(dt.UTC).replace(tzinfo=None)),
    ).fetchone()[0]
    for thing_id, revision, doc in rows:
        conn.execute("INSERT INTO version (thing_id, revision, transaction_id) VALUES (%s, %s, %s)", (thing_id, revision, tx_id))
        conn.execute("INSERT INTO data (thing_id, revision, data) VALUES (%s, %s, %s)", (thing_id, revision, json.dumps({**doc, "revision": revision})))
    return tx_id


def commit_save(connect, docs: list[dict], created: dt.datetime | None = None) -> int:
    with connect() as conn:
        return save(conn, docs, created)


def work(n: int) -> dict:
    return {"key": f"/works/OL{n}W", "type": {"key": "/type/work"}, "title": f"Work {n}"}


def poll(log: TransactionLog) -> list[str]:
    batch = asyncio.run(log.read())
    log.commit()
    return batch.keys


@pytest.mark.integration
def test_moved_edition_reindexes_the_work_and_author_it_left(infobase_db):
    edition = {"key": "/books/OL1M", "type": {"key": "/type/edition"}, "works": [{"key": "/works/OL1W"}], "authors": [{"key": "/authors/OL1A"}]}
    commit_save(infobase_db, [edition])
    commit_save(infobase_db, [{**edition, "works": [{"key": "/works/OL2W"}], "authors": [{"key": "/authors/OL1A"}]}])

    log = TransactionLog(0)

    assert poll(log) == ["/books/OL1M", "/works/OL1W"]
    assert log.position == 2


@pytest.mark.integration
def test_transaction_that_commits_late_is_not_skipped(infobase_db):
    slow = infobase_db()
    slow_id = save(slow, [work(1)])  # gets id 1, not committed yet
    fast_id = commit_save(infobase_db, [work(2)])
    log = TransactionLog(0)

    assert poll(log) == ["/works/OL2W"]
    assert log.pending_gaps == [slow_id]
    assert log.position == 0  # can't move past the in-flight save

    slow.commit()
    slow.close()

    assert poll(log) == ["/works/OL1W"]
    assert log.pending_gaps == []
    assert log.position == fast_id


@pytest.mark.integration
def test_rolled_back_transaction_does_not_block_the_position(infobase_db):
    failed = infobase_db()
    save(failed, [work(1)])
    later_id = commit_save(infobase_db, [work(2)])
    log = TransactionLog(0)
    poll(log)
    failed.rollback()
    failed.close()

    assert poll(log) == []
    assert log.pending_gaps == []
    assert log.position == later_id


@pytest.mark.integration
def test_gap_is_kept_while_its_transaction_could_still_commit(infobase_db):
    slow = infobase_db()
    save(slow, [work(1)])
    commit_save(infobase_db, [work(2)])
    log = TransactionLog(0)
    poll(log)

    # Other edits and polls don't settle the gap while the slow save is open.
    commit_save(infobase_db, [work(3)])
    assert poll(log) == ["/works/OL3W"]
    assert poll(log) == []
    assert log.position == 0

    slow.rollback()
    slow.close()


@pytest.mark.integration
def test_batches_page_through_a_backlog(infobase_db):
    for n in range(1, 6):
        commit_save(infobase_db, [work(n)])
    log = TransactionLog(0, batch_size=2)

    assert [poll(log) for _ in range(3)] == [["/works/OL1W", "/works/OL2W"], ["/works/OL3W", "/works/OL4W"], ["/works/OL5W"]]
    assert log.position == 5


@pytest.mark.integration
def test_start_from_a_point_in_time(infobase_db):
    commit_save(infobase_db, [work(1)], created=dt.datetime(2026, 11, 2, 23, 59))
    second = commit_save(infobase_db, [work(2)], created=dt.datetime(2026, 11, 3, 0, 1))

    assert asyncio.run(transaction_id_at(dt.datetime(2026, 11, 3))) == second - 1
    assert asyncio.run(transaction_id_at(dt.datetime(2026, 11, 4))) == second  # nothing yet: start at the end


@pytest.mark.integration
def test_every_force_update_request_is_indexed_once(infobase_db):
    with infobase_db() as conn:
        for n, keys in enumerate((["/works/OL1W"], ["/authors/OL1A", "/works/OL1W"])):
            key = f"solr-force-update/2026110{n}"
            store_id = conn.execute(
                "INSERT INTO store (key, json) VALUES (%s, %s) RETURNING id", (key, json.dumps({"type": "solr-force-update", "keys": keys}))
            ).fetchone()[0]
            conn.execute("INSERT INTO store_index (store_id, type, name, value) VALUES (%s, 'solr-force-update', '_key', %s)", (store_id, key))
        other = conn.execute("INSERT INTO store (key, json) VALUES ('account/x', '{\"type\": \"account\"}') RETURNING id").fetchone()[0]
        conn.execute("INSERT INTO store_index (store_id, type, name, value) VALUES (%s, 'account', '_key', 'account/x')", (other,))

    async def run():
        force = ForceUpdates()
        keys = await force.read()
        await force.acknowledge()
        return keys, await force.read(), await async_db.fetch_val("SELECT count(*) FROM store")

    keys, keys_after_ack, remaining = asyncio.run(run())

    assert keys == ["/works/OL1W", "/authors/OL1A"]
    assert keys_after_ack == []
    assert remaining == 1  # only the unrelated document is left
