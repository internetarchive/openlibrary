"""Tests for the async BookshelvesEvents queries.

Two layers of coverage:

1. **Unit test** (below, no ``@pytest.mark.integration``): patches the
   ``fetch_val`` helper and asserts the query and params the method passes.
   Fast (no postgres) and catches logic bugs — wrong params, wrong helper.

2. **Integration tests** (``TestBookshelvesEventsIntegration``, marked
   ``@pytest.mark.integration``): run the method against a real postgres
   started by ``pytest-postgresql``. These catch SQL bugs — syntax errors,
   wrong column names, ``%(foo)s`` placeholder mismatches — that the unit
   test can't.

Run just the unit test (default, no postgres required)::

    pytest openlibrary/tests/core/test_bookshelves_events_async.py

Run the integration tests too (requires ``pg_ctl`` on ``PATH``)::

    pytest -m integration openlibrary/tests/core/test_bookshelves_events_async.py
"""

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
    """Run the async model methods against a real postgres.

    The unit test above verifies the query text and params but never executes
    the SQL. These tests run the same method against a real database (the
    ``pg_db`` fixture from ``conftest.py``), so a syntax error, a wrong column
    name, or a ``%(foo)s`` placeholder mismatch is caught here instead of in
    production.
    """

    @pytest.mark.asyncio
    async def test_count_distinct_work_ids_by_user_type_and_year(self, pg_db):
        async with async_db.connection() as conn:
            # Three FINISH events in 2026, distinct works.
            for work_id in (101, 102, 103):
                await conn.execute(
                    f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) "
                    "VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                    {"u": "alice", "w": work_id, "e": 1, "t": BookshelfEvent.FINISH, "d": "2026-05-01"},
                )
            # A duplicate FINISH on work 101 — distinct count must not double it.
            await conn.execute(
                f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                {"u": "alice", "w": 101, "e": 1, "t": BookshelfEvent.FINISH, "d": "2026-06-01"},
            )
            # A START event (different type) — must not count.
            await conn.execute(
                f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                {"u": "alice", "w": 104, "e": 1, "t": BookshelfEvent.START, "d": "2026-05-01"},
            )
            # A FINISH in 2025 — must not count (wrong year).
            await conn.execute(
                f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                {"u": "alice", "w": 105, "e": 1, "t": BookshelfEvent.FINISH, "d": "2025-05-01"},
            )

        count = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year("alice", BookshelfEvent.FINISH, 2026)
        assert count == 3  # 101, 102, 103 — the duplicate and the 2025/START rows don't count

    @pytest.mark.asyncio
    async def test_count_distinct_work_ids_zero_when_no_events(self, pg_db):
        count = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year("nobody", BookshelfEvent.FINISH, 2026)
        assert count == 0
