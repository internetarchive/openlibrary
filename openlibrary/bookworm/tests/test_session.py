"""Tests for the harvest HTTP session: proxy config and User-Agent (#12844).

Both exist because of concrete production failures found during the ol-home0
rollout:

- Open Library's cron container reaches the internet only through an
  authenticated Squid proxy. A bare ``requests.Session()`` picks up
  ``HTTP_PROXY``/``HTTPS_PROXY`` from the environment, but the credentials are
  not there, so every fetch returned ``407 Proxy Authentication Required``.
  Reading them from ``openlibrary.yml`` keeps the secret with the rest of the
  deployment config instead of in the container environment.
- Cloudflare (in front of Better World Books) blocks the default
  ``python-requests/x.y.z`` User-Agent outright. A crawler that does not say who
  it is also gives a provider no way to allowlist us.
"""

from __future__ import annotations

import pytest

import infogami
from openlibrary.bookworm import harvest

PROXY_KEYS = ("http_proxy", "https_proxy")


@pytest.fixture
def ol_config(monkeypatch):
    """Set proxy keys on ``infogami.config``, restored after the test.

    ``infogami.config`` is a module, not a mapping, so keys are attributes.
    Any pre-existing proxy keys are cleared first so a developer's own config
    cannot make these tests pass or fail spuriously.
    """
    for key in PROXY_KEYS:
        monkeypatch.delattr(infogami.config, key, raising=False)

    def _set(**kwargs):
        for key, value in kwargs.items():
            monkeypatch.setattr(infogami.config, key, value, raising=False)

    return _set


class TestProxiesFromConfig:
    def test_no_config_returns_nothing(self, ol_config):
        """Absent config must yield {} so requests falls back to the environment."""
        assert harvest.proxies_from_config() == {}

    def test_reads_both_schemes(self, ol_config):
        ol_config(http_proxy="http://user:pw@proxy:8080", https_proxy="http://user:pw@proxy:8080")
        assert harvest.proxies_from_config() == {
            "http": "http://user:pw@proxy:8080",
            "https": "http://user:pw@proxy:8080",
        }

    def test_https_only_is_honoured(self, ol_config):
        ol_config(https_proxy="http://proxy:8080")
        assert harvest.proxies_from_config() == {"https": "http://proxy:8080"}

    def test_empty_value_is_ignored(self, ol_config):
        """An empty key must not shadow the environment with a blank proxy."""
        ol_config(http_proxy="")
        assert harvest.proxies_from_config() == {}


class TestBuildSession:
    def test_sets_a_descriptive_user_agent(self, ol_config):
        session = harvest.build_session()
        ua = session.headers["User-Agent"]
        assert "OpenLibrary" in ua
        assert "python-requests" not in ua
        # A provider must be able to identify and contact us from the UA alone.
        assert "openlibrary.org" in ua

    def test_applies_configured_proxies(self, ol_config):
        ol_config(https_proxy="http://user:pw@proxy:8080")
        session = harvest.build_session()
        assert session.proxies["https"] == "http://user:pw@proxy:8080"

    def test_without_config_leaves_env_handling_to_requests(self, ol_config):
        """No explicit proxies means requests still honours HTTP(S)_PROXY itself."""
        session = harvest.build_session()
        assert session.proxies == {}
        assert session.trust_env is True
