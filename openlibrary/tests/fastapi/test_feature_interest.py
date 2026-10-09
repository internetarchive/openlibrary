"""Tests for the FastAPI feature interest endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


def test_list_feature_interests_success(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.feature_interest.PatronFeatureInterestDB.select_features_by_username",
        new_callable=AsyncMock,
        return_value=["LibraryThing", "StoryGraph"],
    ):
        response = fastapi_client.get("/account/feature-interest.json")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "features": ["LibraryThing", "StoryGraph"]}


def test_list_feature_interests_empty(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.feature_interest.PatronFeatureInterestDB.select_features_by_username",
        new_callable=AsyncMock,
        return_value=[],
    ):
        response = fastapi_client.get("/account/feature-interest.json")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "features": []}


def test_list_feature_interests_check_specific_feature(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.feature_interest.PatronFeatureInterestDB.exists",
        new_callable=AsyncMock,
        return_value=True,
    ):
        response = fastapi_client.get("/account/feature-interest.json?feature=LibraryThing")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "features": ["LibraryThing"]}


def test_list_feature_interests_check_specific_feature_not_found(fastapi_client, mock_authenticated_user):
    with patch(
        "openlibrary.fastapi.feature_interest.PatronFeatureInterestDB.exists",
        new_callable=AsyncMock,
        return_value=False,
    ):
        response = fastapi_client.get("/account/feature-interest.json?feature=LibraryThing")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "features": []}


def test_list_feature_interests_unauthorized(fastapi_client):
    response = fastapi_client.get("/account/feature-interest.json")
    assert response.status_code == 401


def test_record_feature_interest_success(fastapi_client, mock_authenticated_user):
    with (
        patch(
            "openlibrary.fastapi.feature_interest.PatronFeatureInterestDB.exists",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_exists,
        patch(
            "openlibrary.fastapi.feature_interest.PatronFeatureInterestDB.create",
            new_callable=AsyncMock,
        ) as mock_create,
    ):
        response = fastapi_client.post("/account/feature-interest.json", data={"feature": "LibraryThing"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "already_recorded": False}
    mock_exists.assert_awaited_once_with("testuser", "LibraryThing")
    mock_create.assert_awaited_once_with("testuser", "LibraryThing")


def test_record_feature_interest_already_exists(fastapi_client, mock_authenticated_user):
    with (
        patch(
            "openlibrary.fastapi.feature_interest.PatronFeatureInterestDB.exists",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_exists,
        patch(
            "openlibrary.fastapi.feature_interest.PatronFeatureInterestDB.create",
            new_callable=AsyncMock,
        ) as mock_create,
    ):
        response = fastapi_client.post("/account/feature-interest.json", data={"feature": "LibraryThing"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "already_recorded": True}
    mock_exists.assert_awaited_once_with("testuser", "LibraryThing")
    mock_create.assert_not_awaited()


def test_record_feature_interest_empty_feature(fastapi_client, mock_authenticated_user):
    response = fastapi_client.post("/account/feature-interest.json", data={"feature": ""})
    assert response.status_code == 422  # Pydantic validation error for min_length=1


def test_record_feature_interest_whitespace_only(fastapi_client, mock_authenticated_user):
    response = fastapi_client.post("/account/feature-interest.json", data={"feature": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "Feature required"


def test_record_feature_interest_unauthorized(fastapi_client):
    response = fastapi_client.post("/account/feature-interest.json", data={"feature": "LibraryThing"})
    assert response.status_code == 401


def test_record_feature_interest_invalid_feature_too_long(fastapi_client, mock_authenticated_user):
    long_feature = "x" * 101
    response = fastapi_client.post("/account/feature-interest.json", data={"feature": long_feature})
    assert response.status_code == 422
