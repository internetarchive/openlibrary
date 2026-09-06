"""Tests for the harvest HTTP session (#12844).

The session exists to identify the crawler. Proxying is intentionally NOT
handled here: ``setup_requests()`` already exports ``http_proxy`` and
``no_proxy_addresses`` from ``openlibrary.yml`` into the environment, which is
how coverstore, add_book and affiliate_server all do it, and ``requests`` reads
the environment itself. Re-implementing that mapping in a second place is how
the two drift apart.
"""

from __future__ import annotations

from openlibrary.bookworm import harvest


class TestBuildSession:
    def test_sets_a_descriptive_user_agent(self):
        """Cloudflare (in front of Better World Books) blocks python-requests
        outright, and a provider asked to allowlist our crawler needs a name and
        a contact address to allowlist it by."""
        ua = harvest.build_session().headers["User-Agent"]
        assert ua == harvest.USER_AGENT
        assert ua.startswith("OpenLibraryBot/")
        assert "python-requests" not in ua
        # Contactable: a provider deciding whether to allowlist us needs both a
        # link and an address. (Asserted structurally rather than by matching a
        # bare hostname, which CodeQL reads as URL sanitization.)
        assert "+https://" in ua
        assert "@" in ua

    def test_leaves_proxy_handling_to_the_environment(self):
        """No explicit proxies, and trust_env left on, so the environment
        exported by setup_requests() is what takes effect."""
        session = harvest.build_session()
        assert session.proxies == {}
        assert session.trust_env is True


class TestRetries:
    """A backfill from the beginning is ~3,100 sequential fetches for Gutenberg.

    A single transient network blip partway through aborts the whole crawl.
    That is safe -- the cursor does not advance, so the next run resumes -- but
    it means a long backfill may never finish, and we hit exactly this against
    the live Lenny feed during testing (an SSL read error).
    """

    def _adapter(self):
        return harvest.build_session().get_adapter("https://example.org/")

    def test_transient_failures_are_retried(self):
        retries = self._adapter().max_retries
        assert retries.total >= 2
        assert retries.connect
        assert retries.read

    def test_backoff_is_configured(self):
        """Retrying immediately just hammers a provider that is already struggling."""
        assert self._adapter().max_retries.backoff_factor > 0

    def test_server_errors_and_rate_limits_are_retried(self):
        forcelist = set(self._adapter().max_retries.status_forcelist or ())
        assert {429, 502, 503} <= forcelist

    def test_client_errors_are_not_retried(self):
        """A 403 from Cloudflare is a decision, not a blip -- retrying it five
        times just looks like abuse."""
        forcelist = set(self._adapter().max_retries.status_forcelist or ())
        assert not forcelist & {400, 401, 403, 404}

    def test_only_get_is_retried(self):
        """The harvester only GETs; retrying anything else would be a footgun
        for a future caller that reuses this session."""
        assert set(self._adapter().max_retries.allowed_methods or ()) == {"GET"}
