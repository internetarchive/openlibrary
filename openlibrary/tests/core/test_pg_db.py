"""The integration fixture owns the lifetime of its event loop's pool."""

import pytest

from openlibrary.core import async_db


@pytest.fixture
def pools_closed_after_test():
    pools = []
    yield pools
    assert pools
    assert all(pool.closed for pool in pools)


@pytest.fixture
def pg_db(pools_closed_after_test, pg_db):
    # Make the assertion run after the real pg_db fixture's teardown.
    return pg_db


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pg_db_closes_its_pool(pg_db, pools_closed_after_test):
    assert await async_db.fetch_val("SELECT 1") == 1
    pools_closed_after_test.append(await async_db._pool_for_loop())
