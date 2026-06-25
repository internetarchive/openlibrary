"""Tests for the FastAPI monthly logins endpoint."""

import json
from unittest.mock import patch

import pytest
import web

from openlibrary.plugins.openlibrary.api import monthly_logins as legacy_monthly_logins
from openlibrary.utils.request_context import RequestContextVars, req_context


@pytest.fixture(autouse=True)
def _setup_request_context():
    """Set ContextVars for the legacy cached helper used by monthly_logins."""
    req_context.set(
        RequestContextVars(
            x_forwarded_for=None,
            user_agent=None,
            lang="en",
            solr_editions=True,
            print_disabled=False,
        )
    )


def test_monthly_logins_returns_cached_count(fastapi_client):
    with patch("openlibrary.fastapi.internal.api.get_cached_unique_logins_since", return_value=12345) as get_logins_mock:
        response = fastapi_client.get("/api/monthly_logins.json")

    assert response.status_code == 200
    assert response.json() == {"loginCount": 12345}
    get_logins_mock.assert_called_once_with()


def test_monthly_logins_response_matches_legacy(fastapi_client):
    with (
        patch("openlibrary.plugins.openlibrary.api.get_cached_unique_logins_since", return_value=12345) as legacy_get_logins_mock,
        patch("openlibrary.fastapi.internal.api.get_cached_unique_logins_since", return_value=12345) as fastapi_get_logins_mock,
        pytest.deprecated_call(match="migrated to fastapi"),
    ):
        legacy_response = json.loads(legacy_monthly_logins().GET()["rawtext"])
        fastapi_response = fastapi_client.get("/api/monthly_logins.json")

    assert fastapi_response.status_code == 200
    assert fastapi_response.json() == legacy_response
    legacy_get_logins_mock.assert_called_once_with()
    fastapi_get_logins_mock.assert_called_once_with()


def test_monthly_logins_sets_web_ctx_host_for_cached_helper(fastapi_client, monkeypatch):
    captured_hosts = []

    def memcache_memoize_mock(func, key_prefix, timeout=None, prethread=None):
        captured_hosts.append(web.ctx.host)
        assert prethread is not None

        def get_count(since_days=30):
            assert since_days == 30
            return 12345

        return get_count

    monkeypatch.setattr("openlibrary.core.admin.cache.memcache_memoize", memcache_memoize_mock)

    response = fastapi_client.get("/api/monthly_logins.json")

    assert response.status_code == 200
    assert response.json() == {"loginCount": 12345}
    assert captured_hosts == ["testserver"]
