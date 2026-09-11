"""Tests for the FastAPI monthly logins endpoint."""

from unittest.mock import patch


def test_monthly_logins_returns_cached_count(fastapi_client):
    with patch("openlibrary.fastapi.internal.api.get_unique_logins_since", return_value=12345) as get_logins_mock:
        response = fastapi_client.get("/api/monthly_logins.json")

    assert response.status_code == 200
    assert response.json() == {"loginCount": 12345}
    get_logins_mock.assert_called_once_with()
