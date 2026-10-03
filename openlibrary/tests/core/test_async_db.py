"""Tests for the async psycopg connection pool (openlibrary/core/async_db.py)."""

import asyncio
import logging
import time
from unittest.mock import patch

import pytest
import web

from openlibrary.core import async_db
from openlibrary.utils.async_utils import async_bridge

DB_PARAMETERS = {"dbn": "postgres", "db": "openlibrary", "user": "openlibrary"}


@pytest.fixture(autouse=True)
def _reset_pools():
    async_db.reset_pools()
    yield
    async_db.reset_pools()


class FakePool:
    """Minimal stand-in for ``psycopg_pool.AsyncConnectionPool``.

    :class:`RecordingPoolFactory` sets the optional hooks used by tests.
    """

    @staticmethod
    async def check_connection(conn):
        pass

    def __init__(self, conninfo, kwargs=None, open=None, check=None, min_size=None, max_size=None):
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.check = check
        self.min_size = min_size
        self.max_size = max_size
        self.opened = False
        self.closed = False
        self.connections = []
        self.open_gate: asyncio.Event | None = None
        self.wait_error: BaseException | None = None
        self.close_error: BaseException | None = None

    async def open(self):
        if self.open_gate is not None:
            await self.open_gate.wait()
        self.opened = True

    async def wait(self):
        if self.wait_error is not None:
            raise self.wait_error

    async def close(self):
        if self.close_error is not None:
            error, self.close_error = self.close_error, None
            raise error
        self.closed = True

    def connection(self):
        conn = FakeConnection()
        self.connections.append(conn)
        return conn


class RecordingPoolFactory:
    """Callable ``AsyncConnectionPool`` replacement that records instances."""

    check_connection = staticmethod(FakePool.check_connection)

    def __init__(self, *, open_gate=None, wait_error=None, close_error=None):
        self.created: list[FakePool] = []
        self.open_gate = open_gate
        self.wait_error = wait_error
        self.close_error = close_error

    def __call__(self, **kwargs):
        pool = FakePool(**kwargs)
        pool.open_gate = self.open_gate
        pool.wait_error = self.wait_error
        pool.close_error = self.close_error
        self.created.append(pool)
        return pool


class FakeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def _wait_until(predicate, max_wait=5.0):
    """Yield to the event loop until ``predicate()`` becomes true."""
    async with asyncio.timeout(max_wait):
        # ASYNC110: a generic predicate doesn't fit asyncio.Event.
        while not predicate():  # noqa: ASYNC110
            await asyncio.sleep(0)


def _lock_is_held(loop) -> bool:
    entry = async_db._entries.get(loop)
    return entry is not None and entry.lock.locked()


def _cache_pool(loop, pool) -> async_db._LoopPool:
    """Seed the registry as if a pool had been opened on ``loop``."""
    entry = async_db._LoopPool()
    entry.pool = pool
    async_db._entries[loop] = entry
    return entry


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
async def test_no_db_config_skips_pool_and_connection_raises():
    web.config.db_parameters = {}
    with patch("openlibrary.core.async_db.AsyncConnectionPool") as mock_pool:
        await async_db.init_pool()
    mock_pool.assert_not_called()
    assert async_db.get_pool() is None
    with pytest.raises(RuntimeError, match="No async database pool available"):
        async with async_db.connection():
            pass


@pytest.mark.asyncio
async def test_init_pool_skips_when_psycopg_not_installed():
    """When psycopg/psycopg_pool aren't installed, _open_pool returns None
    and logs a warning instead of crashing the app."""
    web.config.db_parameters = DB_PARAMETERS
    with patch("openlibrary.core.async_db.AsyncConnectionPool", None):
        await async_db.init_pool()
    assert async_db.get_pool() is None


@pytest.mark.asyncio
async def test_connection_raises_when_psycopg_not_installed():
    """connection() raises RuntimeError (not ModuleNotFoundError) when the
    pool can't be created because psycopg isn't installed."""
    web.config.db_parameters = DB_PARAMETERS
    with patch("openlibrary.core.async_db.AsyncConnectionPool", None), pytest.raises(RuntimeError, match="No async database pool available"):
        async with async_db.connection():
            pass


@pytest.mark.asyncio
async def test_init_pool_creates_and_reuses_the_pool():
    web.config.db_parameters = DB_PARAMETERS
    factory = RecordingPoolFactory()
    with patch("openlibrary.core.async_db.AsyncConnectionPool", factory):
        await async_db.init_pool()
        first_pool = async_db.get_pool()
        await async_db.init_pool()

    assert len(factory.created) == 1
    assert async_db.get_pool() is first_pool
    assert isinstance(first_pool, FakePool)
    assert first_pool.opened
    assert first_pool.conninfo == "dbname=openlibrary user=openlibrary password=''"
    assert "row_factory" in first_pool.kwargs
    assert first_pool.check is FakePool.check_connection
    assert first_pool.min_size == 4
    assert first_pool.max_size == 20


@pytest.mark.asyncio
async def test_connection_lazy_initializes_and_uses_the_pool():
    """No lifespan/init_pool needed: first connection() call creates the pool."""
    web.config.db_parameters = DB_PARAMETERS
    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        async with async_db.connection() as conn:
            assert isinstance(conn, FakeConnection)

    pool = async_db.get_pool()
    assert isinstance(pool, FakePool)
    assert pool.opened
    assert len(pool.connections) == 1


def test_pools_are_cached_per_event_loop():
    """Each event loop gets its own pool, reused across calls on that loop."""
    web.config.db_parameters = DB_PARAMETERS

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
    assert loop_1_pool_1 is not None
    assert loop_2_pool is not None
    assert loop_1_pool_1 is not loop_2_pool
    # ...reused for later connections on that same loop.
    assert loop_1_pool_2 is loop_1_pool_1


def test_connection_works_via_async_bridge():
    """async_bridge runs its coroutine on a persistent background loop; that
    loop must get its own pool rather than reusing the caller's loop's pool.
    This is the collision that blocked using the async model methods from
    web.py code."""
    web.config.db_parameters = DB_PARAMETERS

    async def _use():
        async with async_db.connection() as conn:
            assert isinstance(conn, FakeConnection)

    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        async_bridge.run(_use())
        pool_on_bridge_loop = async_db._entries[async_bridge._loop].pool

        # A connection from a different (non-bridge) loop must not reuse it.
        with asyncio.Runner() as runner:
            runner.run(_use())
            pools = [entry.pool for entry in async_db._entries.values()]

    assert isinstance(pool_on_bridge_loop, FakePool)
    assert pool_on_bridge_loop in pools
    assert len(pools) == 2


@pytest.mark.asyncio
async def test_close_pool_closes_and_clears():
    web.config.db_parameters = DB_PARAMETERS
    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        await async_db.init_pool()

    pool = async_db.get_pool()
    assert isinstance(pool, FakePool)
    await async_db.close_pool()
    assert pool.closed
    assert async_db.get_pool() is None


@pytest.mark.asyncio
async def test_close_pool_closes_pools_on_other_loops():
    """A pool created on the bridge loop closes there, and a later call opens a fresh one."""
    web.config.db_parameters = DB_PARAMETERS

    async def _use():
        async with async_db.connection():
            pass

    with patch("openlibrary.core.async_db.AsyncConnectionPool", FakePool):
        async_bridge.run(_use())
        bridge_pool = async_db._entries[async_bridge._loop].pool
        assert isinstance(bridge_pool, FakePool)

        await async_db.close_pool()
        assert bridge_pool.closed
        assert async_bridge._loop not in async_db._entries

        async_bridge.run(_use())
        new_pool = async_db._entries[async_bridge._loop].pool

    assert isinstance(new_pool, FakePool)
    assert new_pool is not bridge_pool


# --- Concurrent first callers and cancellation ------------------------------


@pytest.mark.asyncio
async def test_concurrent_first_callers_share_one_pool():
    """Ten simultaneous first callers must open exactly one pool."""
    web.config.db_parameters = DB_PARAMETERS
    gate = asyncio.Event()
    factory = RecordingPoolFactory(open_gate=gate)
    with patch("openlibrary.core.async_db.AsyncConnectionPool", side_effect=factory):
        callers = [asyncio.create_task(async_db._pool_for_loop()) for _ in range(10)]
        await _wait_until(lambda: len(factory.created) == 1)
        gate.set()
        pools = await asyncio.gather(*callers)

    assert len(factory.created) == 1
    assert all(pool is factory.created[0] for pool in pools)
    assert async_db.get_pool() is factory.created[0]


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_affect_the_open():
    """Cancelling a caller that is waiting on the lock doesn't lose the pool."""
    web.config.db_parameters = DB_PARAMETERS
    gate = asyncio.Event()
    factory = RecordingPoolFactory(open_gate=gate)
    loop = asyncio.get_running_loop()
    with patch("openlibrary.core.async_db.AsyncConnectionPool", side_effect=factory):
        opener = asyncio.create_task(async_db._pool_for_loop())
        waiter = asyncio.create_task(async_db._pool_for_loop())
        await _wait_until(lambda: len(factory.created) == 1 and _lock_is_held(loop))

        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        gate.set()
        pool = await opener

    assert pool is factory.created[0]
    assert len(factory.created) == 1
    assert async_db.get_pool() is pool


@pytest.mark.asyncio
async def test_cancelled_open_closes_pool_and_allows_retry():
    """Cancelling the opener closes the half-open pool and lets the next caller retry."""
    web.config.db_parameters = DB_PARAMETERS
    gate = asyncio.Event()
    factory = RecordingPoolFactory(open_gate=gate)
    loop = asyncio.get_running_loop()
    with patch("openlibrary.core.async_db.AsyncConnectionPool", side_effect=factory):
        opener = asyncio.create_task(async_db._pool_for_loop())
        await _wait_until(lambda: len(factory.created) == 1 and _lock_is_held(loop))

        opener.cancel()
        with pytest.raises(asyncio.CancelledError):
            await opener

        assert factory.created[0].closed
        assert async_db.get_pool() is None

        gate.set()
        pool = await async_db._pool_for_loop()

    assert len(factory.created) == 2
    assert pool is factory.created[1]
    assert async_db.get_pool() is pool


@pytest.mark.asyncio
async def test_failed_open_closes_pool_and_does_not_cache():
    """A failed open leaves no half-open pool or cache entry."""
    web.config.db_parameters = DB_PARAMETERS
    factory = RecordingPoolFactory(wait_error=RuntimeError("wait failed"))
    with patch("openlibrary.core.async_db.AsyncConnectionPool", side_effect=factory), pytest.raises(RuntimeError, match="wait failed"):
        await async_db._pool_for_loop()

    assert factory.created[0].closed
    assert async_db.get_pool() is None


@pytest.mark.asyncio
async def test_mass_cancellation_does_not_leak_pools():
    """Cancelled callers never leave an uncached pool open behind them."""
    web.config.db_parameters = DB_PARAMETERS
    gate = asyncio.Event()
    factory = RecordingPoolFactory(open_gate=gate)
    with patch("openlibrary.core.async_db.AsyncConnectionPool", side_effect=factory):
        callers = [asyncio.create_task(async_db._pool_for_loop()) for _ in range(20)]
        await _wait_until(lambda: len(factory.created) == 1)
        for index, caller in enumerate(callers):
            if index % 2 == 0:
                caller.cancel()
        gate.set()
        await asyncio.gather(*callers, return_exceptions=True)

    # Only the successful pool stays open and cached; every abandoned attempt
    # was closed before it returned.
    assert async_db.get_pool() is factory.created[-1]
    assert all(pool.closed for pool in factory.created[:-1])


# --- Lifetime and close_pool edge cases -------------------------------------


@pytest.mark.asyncio
async def test_close_pool_forgets_inflight_open():
    """close_pool stops tracking an in-flight open; the opener closes the pool itself."""
    web.config.db_parameters = DB_PARAMETERS
    gate = asyncio.Event()
    factory = RecordingPoolFactory(open_gate=gate)
    with patch("openlibrary.core.async_db.AsyncConnectionPool", side_effect=factory):
        opener = asyncio.create_task(async_db._pool_for_loop())
        await _wait_until(lambda: len(factory.created) == 1)

        await async_db.close_pool()
        assert not async_db._entries

        gate.set()
        assert await opener is None

    assert factory.created[0].closed
    assert async_db.get_pool() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("close_loop", "reason"), [(False, "not running"), (True, "is closed")])
async def test_close_pool_drops_dead_loops_without_waiting(close_loop, reason, caplog):
    """A stopped or closed loop can't run close, so close_pool drops it promptly and warns."""
    loop = asyncio.new_event_loop()
    if close_loop:
        loop.close()
    pool = FakePool(conninfo="dbname=openlibrary")
    _cache_pool(loop, pool)

    with caplog.at_level(logging.WARNING, logger="openlibrary.async_db"):
        start = time.monotonic()
        await async_db.close_pool()
        elapsed = time.monotonic() - start
    if not close_loop:
        loop.close()

    assert elapsed < 0.5
    assert loop not in async_db._entries
    assert not pool.closed, "nothing can run on a dead loop"
    assert reason in caplog.text


@pytest.mark.asyncio
async def test_close_pool_keeps_entry_when_close_fails(caplog):
    """A failed close leaves the pool cached so a later call can retry."""
    loop = asyncio.get_running_loop()
    pool = FakePool(conninfo="dbname=openlibrary")
    pool.close_error = RuntimeError("close failed")
    _cache_pool(loop, pool)

    with caplog.at_level(logging.ERROR, logger="openlibrary.async_db"):
        await async_db.close_pool()
    assert async_db._entries[loop].pool is pool
    assert not pool.closed

    await async_db.close_pool()
    assert loop not in async_db._entries
    assert pool.closed


@pytest.mark.asyncio
async def test_reset_pools_closes_pools_on_running_loops():
    """reset_pools can't await, so it schedules closes on running loops."""
    pool = FakePool(conninfo="dbname=openlibrary")
    _cache_pool(asyncio.get_running_loop(), pool)

    async_db.reset_pools()

    assert not async_db._entries
    await _wait_until(lambda: pool.closed)


@pytest.mark.asyncio
async def test_reset_pools_forgets_inflight_open():
    """reset_pools drops the entry; the opener closes the pool it was building."""
    web.config.db_parameters = DB_PARAMETERS
    gate = asyncio.Event()
    factory = RecordingPoolFactory(open_gate=gate)
    with patch("openlibrary.core.async_db.AsyncConnectionPool", side_effect=factory):
        opener = asyncio.create_task(async_db._pool_for_loop())
        await _wait_until(lambda: len(factory.created) == 1)

        async_db.reset_pools()
        assert not async_db._entries

        gate.set()
        assert await opener is None

    assert factory.created[0].closed
    assert async_db.get_pool() is None


# --- Integration with the real psycopg pool ----------------------------------


@pytest.mark.asyncio
async def test_real_pool_cancelled_open_is_closed_and_not_cached(monkeypatch):
    """A real pool cancelled while opening against an unreachable server closes and caches nothing."""
    pytest.importorskip("psycopg_pool")
    web.config.db_parameters = {
        "dbn": "postgres",
        "db": "openlibrary",
        "user": "openlibrary",
        "host": "127.0.0.1",
        "port": 1,  # Nothing listens here; connections fail fast.
    }
    created: list = []
    real_pool_class = async_db.AsyncConnectionPool

    def capturing_pool(**kwargs):
        pool = real_pool_class(**kwargs)
        created.append(pool)
        return pool

    # _open_pool reads check_connection off the class.
    capturing_pool.check_connection = real_pool_class.check_connection
    monkeypatch.setattr(async_db, "AsyncConnectionPool", capturing_pool)
    loop = asyncio.get_running_loop()
    opener = asyncio.create_task(async_db._pool_for_loop())
    await _wait_until(lambda: len(created) == 1 and _lock_is_held(loop))

    opener.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opener

    assert created[0].closed
    assert async_db.get_pool() is None
