"""Shared fixtures for the async DB integration tests.

Provides:
- ``pg_proc``: a session-scoped real PostgreSQL server with the canonical
  schema from ``openlibrary/core/schema.sql`` pre-loaded into the template
  database.
- ``pg_db``: a function-scoped fresh database (cloned from the template) with
  ``web.config.db_parameters`` pointed at it, so the production ``async_db``
  code path runs unmodified.

The autouse ``no_sleep`` fixture in ``openlibrary/conftest.py`` patches
``time.sleep``, which ``pytest-postgresql``'s ``DatabaseJanitor`` needs.
``pg_db`` saves the real ``time.sleep`` at import time and restores it via
``monkeypatch`` so the janitor can actually wait for the server.

Integration tests are marked ``@pytest.mark.integration`` and skipped by
default (``-m 'not integration'`` in ``pyproject.toml``). Run them with::

    pytest -m integration openlibrary/tests/core/
"""

from __future__ import annotations

import time as _time

# Save the real time.sleep before the autouse ``no_sleep`` fixture patches it.
# DatabaseJanitor needs to actually wait for the server to start/stop.
_real_sleep = _time.sleep

from pathlib import Path
from uuid import uuid4

import pytest
import web
from pytest_postgresql import factories
from pytest_postgresql.janitor import DatabaseJanitor

from openlibrary.core import async_db

# The canonical schema for the OL database. Loading it directly (instead of
# duplicating the DDL here) keeps the integration tests in sync with the real
# schema — a column added or a type changed in schema.sql is picked up
# automatically, with no second copy to maintain.
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "core" / "schema.sql"

# Start a real postgres once per session, with the canonical schema pre-loaded
# into the template database. Session-scoped, so it starts before the
# function-scoped ``no_sleep`` autouse fixture patches time.sleep.
pg_proc = factories.postgresql_proc(load=[_SCHEMA_PATH])


@pytest.fixture
def pg_db(pg_proc, monkeypatch):
    """A fresh postgres database per test, pointed at by ``web.config.db_parameters``.

    Uses ``DatabaseJanitor`` to clone the template DB for each test (so tests
    are isolated with no cross-test cleanup). The autouse ``no_sleep`` fixture
    patches ``time.sleep``, so we restore it here — the janitor needs to
    actually wait for the server.
    """
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
        web.config.db_parameters = {
            "dbn": "postgres",
            "db": dbname,
            "user": pg_proc.user,
            "pw": pg_proc.password or "",
            "host": pg_proc.host,
            "port": pg_proc.port,
        }
        # Clear any cached pools from previous tests; the new test's event
        # loop will create a fresh pool pointed at this test's database.
        with async_db._entries_lock:
            async_db._entries.clear()
        yield
        # The pool's event loop is the test's loop, which is closing by the
        # time this sync teardown runs. The database is dropped by the
        # janitor anyway, so just drop the entries.
        with async_db._entries_lock:
            async_db._entries.clear()
        web.config.db_parameters = {}
