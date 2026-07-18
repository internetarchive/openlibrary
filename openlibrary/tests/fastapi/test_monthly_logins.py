"""Tests for the FastAPI monthly logins endpoint."""

import json
from unittest.mock import patch

import pytest

from openlibrary.plugins.openlibrary.api import monthly_logins as legacy_monthly_logins


def test_monthly_logins_returns_cached_count(fastapi_client):
    with patch("openlibrary.fastapi.internal.api.get_unique_logins_since", return_value=12345) as get_logins_mock:
        response = fastapi_client.get("/api/monthly_logins.json")

    assert response.status_code == 200
    assert response.json() == {"loginCount": 12345}
    get_logins_mock.assert_called_once_with()


def test_monthly_logins_response_matches_legacy(fastapi_client):
    with (
        patch("openlibrary.plugins.openlibrary.api.get_unique_logins_since", return_value=12345) as legacy_get_logins_mock,
        patch("openlibrary.fastapi.internal.api.get_unique_logins_since", return_value=12345) as fastapi_get_logins_mock,
        pytest.deprecated_call(match="migrated to fastapi"),
    ):
        legacy_response = json.loads(legacy_monthly_logins().GET()["rawtext"])
        fastapi_response = fastapi_client.get("/api/monthly_logins.json")

    assert fastapi_response.status_code == 200
    assert fastapi_response.json() == legacy_response
    legacy_get_logins_mock.assert_called_once_with()
    fastapi_get_logins_mock.assert_called_once_with()
