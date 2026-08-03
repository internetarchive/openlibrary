"""Tests for the FastAPI hide banner endpoint."""

import json
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from unittest.mock import Mock, patch

import pytest

from openlibrary.plugins.openlibrary.api import hide_banner as legacy_hide_banner

DAY_SECONDS = 60 * 60 * 24


def parse_response_cookie(response, cookie_name: str):
    cookies = SimpleCookie()
    cookies.load(response.headers["set-cookie"])
    return cookies[cookie_name]


def assert_cookie_expiry(cookie, days: int) -> None:
    expires_at = parsedate_to_datetime(cookie["expires"])
    expected = datetime.now(UTC) + timedelta(days=days)
    assert abs((expires_at - expected).total_seconds()) < 5


class TestHideBannerEndpoint:
    def test_returns_json_and_sets_default_cookie(self, fastapi_client):
        with patch("openlibrary.fastapi.internal.api.accounts.get_current_user", return_value=None):
            response = fastapi_client.post("/hide_banner", json={"cookie-name": "test-default-banner"})

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"success": "Preference saved"}

        cookie = parse_response_cookie(response, "test-default-banner")
        assert cookie.value == "1"
        assert cookie["path"] == "/"
        assert cookie["samesite"] == ""
        assert cookie["secure"] == ""
        assert cookie["httponly"] == ""
        assert_cookie_expiry(cookie, 30)

    def test_sets_custom_cookie_duration(self, fastapi_client):
        with patch("openlibrary.fastapi.internal.api.accounts.get_current_user", return_value=None):
            response = fastapi_client.post(
                "/hide_banner",
                json={"cookie-name": "test-custom-banner", "cookie-duration-days": 7},
            )

        assert response.status_code == 200
        assert_cookie_expiry(parse_response_cookie(response, "test-custom-banner"), 7)

    def test_accepts_numeric_string_cookie_duration(self, fastapi_client):
        with patch("openlibrary.fastapi.internal.api.accounts.get_current_user", return_value=None):
            response = fastapi_client.post(
                "/hide_banner",
                json={"cookie-name": "test-string-duration-banner", "cookie-duration-days": "1"},
            )

        assert response.status_code == 200
        assert_cookie_expiry(parse_response_cookie(response, "test-string-duration-banner"), 1)

    def test_saves_yearly_reading_goal_preference_for_authenticated_user(self, fastapi_client):
        user = Mock()
        with patch("openlibrary.fastapi.internal.api.accounts.get_current_user", return_value=user):
            response = fastapi_client.post("/hide_banner", json={"cookie-name": "yrg26"})

        assert response.status_code == 200
        user.save_preferences.assert_called_once_with({"yrg_banner_pref": "yrg26"})

    def test_does_not_save_non_yearly_reading_goal_preference(self, fastapi_client):
        user = Mock()
        with patch("openlibrary.fastapi.internal.api.accounts.get_current_user", return_value=user):
            response = fastapi_client.post("/hide_banner", json={"cookie-name": "site-announcement"})

        assert response.status_code == 200
        user.save_preferences.assert_not_called()

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"cookie-duration-days": 30},
            {"cookie-name": "invalid-duration-banner", "cookie-duration-days": "not-a-number"},
        ],
    )
    def test_rejects_missing_or_invalid_fields(self, fastapi_client, payload):
        response = fastapi_client.post("/hide_banner", json=payload)

        assert response.status_code == 422

    def test_rejects_invalid_json(self, fastapi_client):
        response = fastapi_client.post(
            "/hide_banner",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    def test_only_post_without_json_suffix_is_registered(self, fastapi_client):
        get_response = fastapi_client.get("/hide_banner")
        json_suffix_response = fastapi_client.post("/hide_banner.json", json={"cookie-name": "wrong-path-banner"})

        assert get_response.status_code == 405
        assert json_suffix_response.status_code == 404


def test_hide_banner_response_and_cookie_match_legacy(fastapi_client):
    data = {"cookie-name": "legacy-parity-banner", "cookie-duration-days": 2}

    with (
        patch("openlibrary.plugins.openlibrary.api.accounts.get_current_user", return_value=None),
        patch("openlibrary.plugins.openlibrary.api.web.data", return_value=json.dumps(data)),
        patch("openlibrary.plugins.openlibrary.api.web.setcookie") as legacy_setcookie,
        pytest.deprecated_call(match="migrated to fastapi"),
    ):
        legacy_response = json.loads(legacy_hide_banner().POST()["rawtext"])

    with patch("openlibrary.fastapi.internal.api.accounts.get_current_user", return_value=None):
        fastapi_response = fastapi_client.post("/hide_banner", json=data)

    assert fastapi_response.status_code == 200
    assert fastapi_response.json() == legacy_response
    legacy_setcookie.assert_called_once_with("legacy-parity-banner", "1", expires=2 * DAY_SECONDS)

    fastapi_cookie = parse_response_cookie(fastapi_response, "legacy-parity-banner")
    assert fastapi_cookie.value == "1"
    assert_cookie_expiry(fastapi_cookie, 2)
