"""Tests for the ReadingGoalProgress partial endpoint."""

from datetime import datetime
from unittest.mock import AsyncMock, patch


def test_reading_goal_progress_partial_uses_authenticated_user(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.partials.ReadingGoalProgressPartial.generate_async",
        new_callable=AsyncMock,
        return_value={"partials": "<div>goal</div>"},
    ) as mock_generate:
        response = fastapi_client.get("/partials/ReadingGoalProgress.json")

    assert response.status_code == 200
    assert response.json() == {"partials": "<div>goal</div>"}
    mock_generate.assert_awaited_once_with(username="testuser", year=datetime.now().year)


def test_reading_goal_progress_partial_passes_year(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.partials.ReadingGoalProgressPartial.generate_async",
        new_callable=AsyncMock,
        return_value={"partials": ""},
    ) as mock_generate:
        response = fastapi_client.get("/partials/ReadingGoalProgress.json?year=2025")

    assert response.status_code == 200
    mock_generate.assert_awaited_once_with(username="testuser", year=2025)
