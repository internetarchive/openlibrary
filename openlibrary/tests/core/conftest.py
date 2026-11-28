"""Postgres fixtures for the async DB integration tests.

- ``pg_proc``: session postgres with ``openlibrary/core/schema.sql`` loaded.
- ``pg_db``: fresh database per test, with ``web.config.db_parameters``
  pointed at it so production ``async_db`` code runs unmodified.

Integration tests use ``@pytest.mark.integration`` and stay skipped by
default. Run them with ``pytest -m integration openlibrary/tests/core/``.
"""

from __future__ import annotations

import time as _time

# Save before the autouse ``no_sleep`` fixture patches it. The janitor needs a real wait.
_real_sleep = _time.sleep

from pathlib import Path
from uuid import uuid4

import pytest_asyncio
import web
from pytest_postgresql import factories
from pytest_postgresql.janitor import DatabaseJanitor

from openlibrary.core import async_db

# Load the canonical schema directly so tests track schema.sql with no second copy.
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "core" / "schema.sql"

pg_proc = factories.postgresql_proc(load=[_SCHEMA_PATH])


@pytest_asyncio.fixture
async def pg_db(pg_proc, monkeypatch):
    """Fresh postgres per test, with ``web.config.db_parameters`` pointed at it."""
    monkeypatch.setattr("time.sleep", _real_sleep)

    dbname = f"test_{uuid4().hex[:8]}"
    with DatabaseJanitor(
        user=pg_proc.user,
        host=pg_proc.host,
        port=pg_proc.port,
        dbname=dbname,
        password=pg_proc.password,
        template_dbname=pg_proc.template_dbname,
    ):
        monkeypatch.setitem(
            web.config,
            "db_parameters",
            {
                "dbn": "postgres",
                "db": dbname,
                "user": pg_proc.user,
                "pw": pg_proc.password or "",
                "host": pg_proc.host,
                "port": pg_proc.port,
            },
        )
        # Fresh pool per test database.
        with async_db._entries_lock:
            async_db._entries.clear()
        try:
            yield
        finally:
            # Stop pool workers on their owning loop before pytest shuts it down
            # or the janitor drops the database. Clearing the registry isn't a close.
            await async_db.close_pool()
            with async_db._entries_lock:
                async_db._entries.clear()
