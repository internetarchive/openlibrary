import asyncio
import json

import pytest

from openlibrary.core import async_db
from scripts.solr_updater.database_log import DatabaseLog


def test_read_keys_uses_current_and_previous_documents(monkeypatch):
    async def fetch_all(query, params):
        assert params == {"limit": 100}
        assert "jsonb_to_recordset" in query
        return [
            {
                "queue_id": 1,
                "transaction_id": 42,
                "force_keys": None,
                "changed_key": "/books/OL1M",
                "current_data": json.dumps(
                    {
                        "key": "/books/OL1M",
                        "type": {"key": "/type/edition"},
                        "authors": [{"key": "/authors/OL2A"}],
                    }
                ),
                "previous_data": json.dumps(
                    {
                        "key": "/books/OL1M",
                        "type": {"key": "/type/edition"},
                        "authors": [{"key": "/authors/OL3A"}],
                    }
                ),
            }
        ]

    monkeypatch.setattr(async_db, "fetch_all", fetch_all)

    keys = asyncio.run(DatabaseLog().read_keys())

    assert keys == ["/books/OL1M", "/authors/OL3A"]


def test_read_keys_includes_every_admin_force_update(monkeypatch):
    async def fetch_all(query, params):
        assert "solr_updater_queue" in query
        return [
            {"queue_id": 1, "transaction_id": None, "force_keys": ["/books/OL1M"], "changed_key": None},
            {"queue_id": 2, "transaction_id": None, "force_keys": ["/works/OL2W"], "changed_key": None},
        ]

    monkeypatch.setattr(async_db, "fetch_all", fetch_all)

    keys = asyncio.run(DatabaseLog().read_keys())

    assert keys == ["/books/OL1M", "/works/OL2W"]


def test_acknowledge_deletes_only_after_success(monkeypatch):
    calls = []

    async def fetch_all(query, params):
        if "solr_updater_queue" in query:
            return [{"queue_id": 4, "transaction_id": 8, "force_keys": None, "changed_key": None}]
        raise AssertionError("DatabaseLog should use one query per batch")

    async def execute(query, params):
        calls.append((query, params))

    monkeypatch.setattr(async_db, "fetch_all", fetch_all)
    monkeypatch.setattr(async_db, "execute", execute)
    log = DatabaseLog()

    asyncio.run(log.read_keys())
    asyncio.run(log.acknowledge())
    asyncio.run(log.acknowledge())

    assert calls == [("DELETE FROM solr_updater_queue WHERE id = ANY(%(ids)s)", {"ids": [4]})]


def test_read_keys_tracks_rows_that_produce_no_keys(monkeypatch):
    async def fetch_all(query, params):
        return [{"queue_id": 9, "transaction_id": 42, "force_keys": None, "changed_key": None}]

    async def execute(query, params):
        pass

    monkeypatch.setattr(async_db, "fetch_all", fetch_all)
    monkeypatch.setattr(async_db, "execute", execute)
    log = DatabaseLog()

    assert asyncio.run(log.read_keys()) == []
    assert log.has_pending_batch

    asyncio.run(log.acknowledge())

    assert not log.has_pending_batch


def test_read_keys_reports_queue_context_for_missing_current_data(monkeypatch):
    async def fetch_all(query, params):
        return [
            {
                "queue_id": 12,
                "transaction_id": 34,
                "force_keys": None,
                "changed_key": "/works/OL56W",
                "current_data": None,
                "previous_data": None,
            }
        ]

    monkeypatch.setattr(async_db, "fetch_all", fetch_all)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(DatabaseLog().read_keys())

    assert "queue row 12" in str(exc_info.value)
    assert "transaction 34" in str(exc_info.value)
    assert "/works/OL56W" in str(exc_info.value)
