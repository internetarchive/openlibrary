"""Tests for the async psycopg connection pool (openlibrary/core/async_db.py)."""

import asyncio
from unittest.mock import patch

import pytest
import web

from openlibrary.core import async_db
from openlibrary.utils.async_utils import AsyncBridge, async_bridge


@pytest.fixture(autouse=True)
def _reset_pools():
    async_db._pools.clear()
    async_db._opening.clear()
    yield
    async_db._pools.clear()
    async_db._opening.clear()


class FakePool:
    def __init__(self, conninfo, kwargs=None, open=None):
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.opened = False
        self.closed = False
        self.connections = []

    async def open(self):
        self.opened = True

    async def wait(self):
        pass

    async def close(self):
        self.closed = True

    def connection(self):
        conn = FakeConnection()
        self.connections.append(conn)
        return conn


class FakeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


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
async def test_connection_lazy_initializes_pool():
    """No lifespan/init_pool needed: first connection() call creates the pool."""
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
    }
    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        async with async_db.connection() as conn:
            assert isinstance(conn, FakeConnection)

    pool = async_db.get_pool()
    assert isinstance(pool, FakePool)
    assert pool.opened


def test_pools_are_cached_per_event_loop():
    """Each event loop gets its own pool, reused across calls on that loop."""
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
    }

    async def _first_connection():
        async with async_db.connection():
            pass
        return async_db.get_pool()

    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        loop_1 = asyncio.new_event_loop()
        try:
            loop_1_pool_1 = loop_1.run_until_complete(_first_connection())
            loop_1_pool_2 = loop_1.run_until_complete(_first_connection())
        finally:
            loop_1.close()

        loop_2 = asyncio.new_event_loop()
        try:
            loop_2_pool = loop_2.run_until_complete(_first_connection())
        finally:
            loop_2.close()

    # A second, independent loop gets a different pool...
    assert loop_1_pool_1 is not None and loop_2_pool is not None
    assert loop_1_pool_1 is not loop_2_pool
    # ...reused for later connections on that same loop.
    assert loop_1_pool_2 is loop_1_pool_1


def test_connection_works_via_async_bridge():
    """async_bridge runs its coroutine on a persistent background loop; that
    loop must get its own pool rather than reusing the caller's loop's pool.
    This is the collision that blocked using the async model methods from
    web.py code."""
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
    }

    async def _use():
        async with async_db.connection() as conn:
            assert isinstance(conn, FakeConnection)

    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        async_bridge.run(_use())
        pool_on_bridge_loop = async_db._pools.get(async_bridge._loop)

        # A connection from a different (non-bridge) loop must not reuse it.
        with asyncio.Runner() as runner:
            runner.run(_use())
            pools = list(async_db._pools.values())

    assert isinstance(pool_on_bridge_loop, FakePool)
    assert pool_on_bridge_loop in pools
    assert len(pools) == 2


def test_connection_works_via_custom_bridge():
    """Same as above but with a fresh bridge, proving any bridged loop can
    lazily create its own pool."""
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
    }
    bridge = AsyncBridge()

    async def _use():
        async with async_db.connection():
            pass

    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        bridge.run(_use())

    assert isinstance(async_db._pools.get(bridge._loop), FakePool)


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


@pytest.mark.asyncio
async def test_close_pool_closes_pools_on_other_loops():
    """A pool created on the bridge loop must be closed on that loop, not the
    caller's."""
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
    }

    async def _use():
        async with async_db.connection():
            pass

    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        async_bridge.run(_use())

    bridge_pool = async_db._pools.get(async_bridge._loop)
    assert isinstance(bridge_pool, FakePool)

    await async_db.close_pool()

    assert bridge_pool.closed
    assert async_db.get_pool() is None


@pytest.mark.asyncio
async def test_connection_raises_without_pool():
    web.config.db_parameters = {}
    with pytest.raises(RuntimeError):
        async with async_db.connection():
            pass


@pytest.mark.asyncio
async def test_connection_yields_pool_connection():
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
    }
    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        await async_db.init_pool()

    pool = async_db.get_pool()
    async with async_db.connection() as conn:
        assert isinstance(conn, FakeConnection)
    assert len(pool.connections) == 1
