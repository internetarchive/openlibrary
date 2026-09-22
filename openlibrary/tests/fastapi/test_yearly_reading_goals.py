"""Tests for the FastAPI yearly reading goals endpoints."""

from unittest.mock import AsyncMock, patch


def test_get_reading_goals_success(fastapi_client, mock_authenticated_user):
    fake_records = [{"year": 2026, "target": 25}]
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.select_by_username_async",
        new_callable=AsyncMock,
        return_value=fake_records,
    ):
        response = fastapi_client.get("/reading-goal.json")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "goal": [{"year": 2026, "goal": 25}]}


def test_get_reading_goals_with_year(fastapi_client, mock_authenticated_user):
    fake_records = [{"year": 2026, "target": 25}]
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.select_by_username_and_year_async",
        new_callable=AsyncMock,
        return_value=fake_records,
    ):
        response = fastapi_client.get("/reading-goal.json?year=2026")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "goal": [{"year": 2026, "goal": 25}]}


def test_get_reading_goals_invalid_year(fastapi_client, mock_authenticated_user):
    response = fastapi_client.get("/reading-goal.json?year=-500")
    assert response.status_code == 422


def test_create_reading_goal_success(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.create_async",
        new_callable=AsyncMock,
    ) as mock_create:
        response = fastapi_client.post("/reading-goal.json", data={"goal": 25, "year": 2026})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_create.assert_awaited_once_with("testuser", 2026, 25)


def test_create_reading_goal_invalid_year(fastapi_client, mock_authenticated_user):
    response = fastapi_client.post("/reading-goal.json", data={"goal": 25, "year": -500})
    assert response.status_code == 422


def test_update_reading_goal_success(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.update_target_async",
        new_callable=AsyncMock,
    ) as mock_update:
        response = fastapi_client.post(
            "/reading-goal.json",
            data={"goal": 30, "year": 2026, "is_update": "1"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_update.assert_awaited_once_with("testuser", 2026, 30)


def test_delete_reading_goal_success(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.yearly_reading_goals.YearlyReadingGoals.delete_by_username_and_year_async",
        new_callable=AsyncMock,
    ) as mock_delete:
        response = fastapi_client.post(
            "/reading-goal.json",
            data={"goal": 0, "year": 2026, "is_update": "1"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_delete.assert_awaited_once_with("testuser", 2026)
