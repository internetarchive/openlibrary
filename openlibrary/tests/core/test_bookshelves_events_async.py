"""Unit and integration tests for the async BookshelvesEvents queries. See ``docs/ai/database.md``."""

from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents

# --- Unit test (no postgres required) ------------------------------------------


@pytest.mark.asyncio
async def test_count_distinct_work_ids_by_user_type_and_year():
    with patch(
        "openlibrary.core.bookshelves_events.fetch_val",
        new_callable=AsyncMock,
        return_value=3,
    ) as mock_fetch_val:
        count = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year("testuser", BookshelfEvent.FINISH, 2026)

    assert count == 3
    (query, params), _kwargs = mock_fetch_val.await_args
    assert "count(DISTINCT work_id)" in query
    assert "event_date LIKE %(event_date)s" in query
    assert params == {
        "username": "testuser",
        "event_type": BookshelfEvent.FINISH,
        "event_date": "2026%",
    }


# --- Integration tests (real postgres, marked `integration`) -------------------


@pytest.mark.integration
class TestBookshelvesEventsIntegration:
    @pytest.mark.asyncio
    async def test_count_distinct_work_ids_by_user_type_and_year(self, pg_db):
        async with async_db.connection() as conn:
            for work_id in (101, 102, 103):
                await conn.execute(
                    f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) "
                    "VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                    {"u": "alice", "w": work_id, "e": 1, "t": BookshelfEvent.FINISH, "d": "2026-05-01"},
                )
            # Duplicate on 101 stays distinct. START and 2025 rows must not count.
            await conn.execute(
                f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                {"u": "alice", "w": 101, "e": 1, "t": BookshelfEvent.FINISH, "d": "2026-06-01"},
            )
            await conn.execute(
                f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                {"u": "alice", "w": 104, "e": 1, "t": BookshelfEvent.START, "d": "2026-05-01"},
            )
            await conn.execute(
                f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                {"u": "alice", "w": 105, "e": 1, "t": BookshelfEvent.FINISH, "d": "2025-05-01"},
            )

        count = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year("alice", BookshelfEvent.FINISH, 2026)
        assert count == 3

    @pytest.mark.asyncio
    async def test_count_distinct_work_ids_zero_when_no_events(self, pg_db):
        count = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year("nobody", BookshelfEvent.FINISH, 2026)
        assert count == 0
