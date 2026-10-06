"""Tests for the async BookshelvesEvents queries.

The model's queries go through the async_db single-statement helpers;
these tests patch the helpers and assert the query and params each
method passes.
"""

from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents


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
