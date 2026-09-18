"""Tests for the async psycopg connection pool (openlibrary/core/async_db.py)."""

from unittest.mock import patch

import pytest
import web

from openlibrary.core import async_db


@pytest.fixture(autouse=True)
def _reset_pool():
    async_db._pool = None


class FakePool:
    def __init__(self, conninfo, kwargs=None, open=None):
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.opened = False
        self.closed = False

    async def open(self):
        self.opened = True

    async def wait(self):
        pass

    async def close(self):
        self.closed = True


def test_connection_kwargs_translates_web_parameters():
    db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
        "pw": "secret",
        "host": "db",
        "port": 5432,
    }
    assert async_db._connection_kwargs(db_parameters) == {
        "dbname": "openlibrary",
        "user": "openlibrary",
        "password": "secret",
        "host": "db",
        "port": 5432,
    }


def test_connection_kwargs_defaults_password_and_optional_fields():
    assert async_db._connection_kwargs({"dbn": "postgres", "db": "openlibrary", "user": "openlibrary"}) == {
        "dbname": "openlibrary",
        "user": "openlibrary",
        "password": "",
    }


@pytest.mark.asyncio
async def test_init_pool_skips_without_db_config():
    web.config.db_parameters = {}
    with patch("openlibrary.core.async_db.AsyncConnectionPool") as mock_pool:
        await async_db.init_pool()
    mock_pool.assert_not_called()
    assert async_db.get_pool() is None


@pytest.mark.asyncio
async def test_init_pool_creates_and_opens_pool():
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
    }
    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        await async_db.init_pool()

    pool = async_db.get_pool()
    assert isinstance(pool, FakePool)
    assert pool.opened
    assert pool.conninfo == "dbname=openlibrary user=openlibrary password=''"
    assert "row_factory" in pool.kwargs


@pytest.mark.asyncio
async def test_init_pool_is_idempotent():
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
    }
    with patch("openlibrary.core.async_db.AsyncConnectionPool", side_effect=FakePool) as mock_pool:
        await async_db.init_pool()
        first_pool = async_db.get_pool()
        await async_db.init_pool()

    assert mock_pool.call_count == 1
    assert async_db.get_pool() is first_pool


@pytest.mark.asyncio
async def test_close_pool_closes_and_clears():
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
    }
    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        await async_db.init_pool()

    pool = async_db.get_pool()
    assert isinstance(pool, FakePool)
    await async_db.close_pool()
    assert pool.closed
    assert async_db.get_pool() is None
