"""Server-Timing for the async pool, against a real postgres (see conftest.py)."""

import asyncio

import pytest
from psycopg.rows import class_row

from openlibrary.core import async_db
from openlibrary.utils import server_timing

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.usefixtures("pg_db")]


@pytest.fixture
def timings():
    timings, token = server_timing.start_request()
    yield timings
    server_timing.end_request(token)


def counts(timings) -> dict[str, tuple[int, int]]:
    """{name: (count, failures)}"""
    return {name: (count, failures) for name, (count, _, failures) in timings.snapshot().items()}


class Row:
    def __init__(self, n: int):
        self.n = n


async def test_each_helper_times_one_query_and_one_checkout(timings):
    await async_db.execute("SELECT 1")
    await async_db.fetch_all("SELECT 1 AS n UNION SELECT 2", row_factory=class_row(Row))
    await async_db.fetch_one("SELECT 1")
    assert await async_db.fetch_val("SELECT 42") == 42
    # The pool's health check on each checkout counts toward db-checkout, not db.
    assert counts(timings) == {"db": (4, 0), "db-checkout": (4, 0)}


async def test_transactions_time_every_statement(timings):
    async with async_db.connection() as conn:
        await conn.execute("CREATE TEMP TABLE t (n int)")
        async with conn.cursor() as cursor:
            await cursor.executemany("INSERT INTO t VALUES (%s)", [(1,), (2,), (3,)])
        assert (await (await conn.execute("SELECT count(*) AS c FROM t")).fetchone())["c"] == 3
    assert counts(timings) == {"db": (3, 0), "db-checkout": (1, 0)}


async def test_failed_query_counts_as_failed(timings):
    with pytest.raises(Exception, match="no_such_table"):
        await async_db.fetch_one("SELECT * FROM no_such_table")
    assert counts(timings) == {"db": (1, 1), "db-checkout": (1, 0)}


async def test_checkout_includes_waiting_for_a_free_connection(timings):
    max_size = 20  # async_db's pool size
    release = asyncio.Event()
    checked_out = asyncio.Semaphore(0)

    async def hold():
        async with async_db.connection():
            checked_out.release()
            await release.wait()

    # Created outside the request, so the holders' own checkouts aren't recorded.
    request_context = server_timing._current.set(None)
    holders = [asyncio.create_task(hold()) for _ in range(max_size)]
    server_timing._current.reset(request_context)
    for _ in range(max_size):
        await checked_out.acquire()

    async def release_soon():
        await asyncio.sleep(0.05)
        release.set()

    releaser = asyncio.create_task(release_soon())
    assert await async_db.fetch_val("SELECT 1") == 1
    await asyncio.gather(releaser, *holders)

    (checkout_count, checkout_seconds, _) = timings.snapshot()["db-checkout"]
    assert checkout_count == 1
    assert checkout_seconds >= 0.05
    assert timings.snapshot()["db"][1] < checkout_seconds  # the wait isn't counted as query time


async def test_untimed_outside_a_request():
    assert server_timing._current.get() is None
    assert await async_db.fetch_val("SELECT 1") == 1
