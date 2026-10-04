"""Tests for the async reading goal helper."""

from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.bookshelves_events import BookshelfEvent
from openlibrary.core.yearly_reading_goals import YearlyReadingGoal
from openlibrary.plugins.upstream.models import User
from openlibrary.plugins.upstream.yearly_reading_goals import (
    YearlyGoal,
    get_reading_goals,
    get_reading_goals_async,
)


def _make_user(key: str = "/people/testuser") -> User:
    """The real User model. ``get_username`` only reads ``key``, so the site is unused."""
    return User(object(), key)


@pytest.mark.asyncio
async def test_get_reading_goals_async_builds_goal():
    with (
        patch(
            "openlibrary.plugins.upstream.yearly_reading_goals.YearlyReadingGoals.select_by_username_and_year",
            new_callable=AsyncMock,
            return_value=[YearlyReadingGoal("testuser", 2026, 25, None, None)],
        ) as mock_select,
        patch(
            "openlibrary.plugins.upstream.yearly_reading_goals.BookshelvesEvents.select_distinct_by_user_type_and_year_async",
            new_callable=AsyncMock,
            return_value=[{"work_id": 1}, {"work_id": 2}, {"work_id": 3}],
        ) as mock_events,
    ):
        goal = await get_reading_goals_async("testuser", 2026)

    assert goal is not None
    assert (goal.year, goal.goal, goal.books_read, goal.progress) == (2026, 25, 3, 12)
    mock_select.assert_awaited_once_with("testuser", 2026)
    mock_events.assert_awaited_once_with("testuser", BookshelfEvent.FINISH, 2026)


@pytest.mark.asyncio
async def test_get_reading_goals_async_returns_none_without_goal():
    with patch(
        "openlibrary.plugins.upstream.yearly_reading_goals.YearlyReadingGoals.select_by_username_and_year",
        new_callable=AsyncMock,
        return_value=[],
    ):
        assert await get_reading_goals_async("testuser", 2026) is None


def test_get_reading_goals_bridges_to_async(monkeypatch):
    """The web.py adapter reads the username off the real User model and bridges."""
    user = _make_user()
    assert user.get_username() == "testuser"
    monkeypatch.setattr(
        "openlibrary.plugins.upstream.yearly_reading_goals.get_current_user",
        lambda: user,
    )
    goal = YearlyGoal(2026, 25, 10)
    with patch(
        "openlibrary.plugins.upstream.yearly_reading_goals.get_reading_goals_async",
        new_callable=AsyncMock,
        return_value=goal,
    ) as mock_async:
        assert get_reading_goals(year=2026) is goal

    mock_async.assert_awaited_once_with("testuser", 2026)


def test_get_reading_goals_without_user_does_not_bridge(monkeypatch):
    monkeypatch.setattr(
        "openlibrary.plugins.upstream.yearly_reading_goals.get_current_user",
        lambda: None,
    )
    with patch(
        "openlibrary.plugins.upstream.yearly_reading_goals.get_reading_goals_async",
        new_callable=AsyncMock,
    ) as mock_async:
        assert get_reading_goals(year=2026) is None

    mock_async.assert_not_called()


def test_get_reading_goals_defaults_to_current_year(monkeypatch):
    monkeypatch.setattr(
        "openlibrary.plugins.upstream.yearly_reading_goals.get_current_user",
        _make_user,
    )
    with (
        patch("openlibrary.plugins.upstream.yearly_reading_goals.datetime") as mock_datetime,
        patch(
            "openlibrary.plugins.upstream.yearly_reading_goals.get_reading_goals_async",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_async,
    ):
        mock_datetime.now.return_value.year = 2026
        assert get_reading_goals() is None

    mock_async.assert_awaited_once_with("testuser", 2026)
