"""Tests for the FastAPI yearly reading goals endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

from openlibrary.core.yearly_reading_goals import YearlyReadingGoal


def test_get_reading_goals_success(fastapi_client, mock_authenticated_user):
    fake_records = [YearlyReadingGoal("testuser", 2026, 25, None, None)]
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.select_by_username",
        new_callable=AsyncMock,
        return_value=fake_records,
    ):
        response = fastapi_client.get("/reading-goal.json")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "goal": [{"year": 2026, "goal": 25}]}


def test_get_reading_goals_with_year(fastapi_client, mock_authenticated_user):
    record = YearlyReadingGoal("testuser", 2026, 25, None, None)
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.select_by_username_and_year",
        new_callable=AsyncMock,
        return_value=record,
    ):
        response = fastapi_client.get("/reading-goal.json?year=2026")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "goal": [{"year": 2026, "goal": 25}]}


def test_get_reading_goals_with_year_without_goal(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.select_by_username_and_year",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = fastapi_client.get("/reading-goal.json?year=2026")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "goal": []}


def test_get_reading_goals_invalid_year(fastapi_client, mock_authenticated_user):
    response = fastapi_client.get("/reading-goal.json?year=-500")
    assert response.status_code == 422


def test_save_reading_goal_upserts(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.create",
        new_callable=AsyncMock,
    ) as mock_create:
        response = fastapi_client.post("/reading-goal.json", data={"goal": 25, "year": 2026})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_create.assert_awaited_once_with("testuser", 2026, 25)


def test_save_reading_goal_with_is_update_flag_upserts(fastapi_client, mock_authenticated_user):
    # is_update is accepted for backwards compatibility and ignored.
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.create",
        new_callable=AsyncMock,
    ) as mock_create:
        response = fastapi_client.post(
            "/reading-goal.json",
            data={"goal": 30, "year": 2026, "is_update": "1"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_create.assert_awaited_once_with("testuser", 2026, 30)


def test_save_reading_goal_defaults_year_to_current_year(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.create",
        new_callable=AsyncMock,
    ) as mock_create:
        response = fastapi_client.post("/reading-goal.json", data={"goal": 25})

    assert response.status_code == 200
    mock_create.assert_awaited_once_with("testuser", datetime.now().year, 25)


def test_save_reading_goal_invalid_year(fastapi_client, mock_authenticated_user):
    response = fastapi_client.post("/reading-goal.json", data={"goal": 25, "year": -500})
    assert response.status_code == 422


def test_save_reading_goal_invalid_goal(fastapi_client, mock_authenticated_user):
    response = fastapi_client.post("/reading-goal.json", data={"goal": -5, "year": 2026})
    assert response.status_code == 422


def test_save_reading_goal_requires_goal(fastapi_client, mock_authenticated_user):
    # An absent goal must not be treated as "delete the goal".
    response = fastapi_client.post("/reading-goal.json", data={"year": 2026})
    assert response.status_code == 422


def test_delete_reading_goal_success(fastapi_client, mock_authenticated_user):
    # goal=0 deletes without needing a client-sent is_update flag.
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.delete_by_username_and_year",
        new_callable=AsyncMock,
    ) as mock_delete:
        response = fastapi_client.post("/reading-goal.json", data={"goal": 0, "year": 2026})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_delete.assert_awaited_once_with("testuser", 2026)


def test_delete_reading_goal_with_is_update_flag(fastapi_client, mock_authenticated_user):
    # is_update is accepted for backwards compatibility and ignored.
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.delete_by_username_and_year",
        new_callable=AsyncMock,
    ) as mock_delete:
        response = fastapi_client.post(
            "/reading-goal.json",
            data={"goal": 0, "year": 2026, "is_update": "1"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_delete.assert_awaited_once_with("testuser", 2026)


def test_delete_reading_goal_defaults_year_to_current_year(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.delete_by_username_and_year",
        new_callable=AsyncMock,
    ) as mock_delete:
        response = fastapi_client.post("/reading-goal.json", data={"goal": 0})

    assert response.status_code == 200
    mock_delete.assert_awaited_once_with("testuser", datetime.now().year)
