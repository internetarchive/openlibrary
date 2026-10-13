"""Unit and integration tests for the async admin queries. See ``docs/core/database.md``."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.admin import get_unique_logins_since
from openlibrary.core.cache import invalidate

# --- Unit test (no postgres required) ------------------------------------------


@pytest.fixture
def helpers():
    with patch("openlibrary.core.admin.fetch_val", new_callable=AsyncMock) as fetch_val:
        yield SimpleNamespace(fetch_val=fetch_val)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the memoize cache before each test."""
    invalidate("logins_since")
    yield
    invalidate("logins_since")


@pytest.mark.asyncio
async def test_get_unique_logins_since(helpers):
    helpers.fetch_val.return_value = 12345

    count = await get_unique_logins_since(30)

    assert count == 12345
    (query, params), _kwargs = helpers.fetch_val.await_args
    assert "SELECT COUNT(id) FROM store_index" in query
    assert "type = 'account'" in query
    assert "name = 'last_login'" in query
    assert "value > %(date)s" in query
    assert params["date"].startswith("202")  # recent date


@pytest.mark.asyncio
async def test_get_unique_logins_since_zero_when_no_results(helpers):
    helpers.fetch_val.return_value = None

    count = await get_unique_logins_since(31)  # different arg to avoid cache

    assert count == 0


# --- Integration tests (require postgres) ----------------------------------------


@pytest.mark.integration
class TestGetUniqueLoginsSinceIntegration:
    @pytest.mark.asyncio
    async def test_get_unique_logins_since_returns_count(self, pg_db):
        # Use dates relative to now: recent (within 30 days) and older (beyond 30 days)
        recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        older = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")

        async with async_db.connection() as conn:
            await conn.execute(
                "INSERT INTO store_index (id, type, name, value) VALUES (%(id)s, %(type)s, %(name)s, %(value)s)",
                {"id": "acc1", "type": "account", "name": "last_login", "value": recent},
            )
            await conn.execute(
                "INSERT INTO store_index (id, type, name, value) VALUES (%(id)s, %(type)s, %(name)s, %(value)s)",
                {"id": "acc2", "type": "account", "name": "last_login", "value": recent},
            )
            # Older than 30 days - should not count
            await conn.execute(
                "INSERT INTO store_index (id, type, name, value) VALUES (%(id)s, %(type)s, %(name)s, %(value)s)",
                {"id": "acc3", "type": "account", "name": "last_login", "value": older},
            )

        count = await get_unique_logins_since(30)
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_unique_logins_since_zero_when_no_logins(self, pg_db):
        count = await get_unique_logins_since(30)
        assert count == 0
