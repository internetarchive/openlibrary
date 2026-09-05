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
        assert "OpenLibrary" in ua
        assert "python-requests" not in ua
        assert "openlibrary.org" in ua

    def test_leaves_proxy_handling_to_the_environment(self):
        """No explicit proxies, and trust_env left on, so the environment
        exported by setup_requests() is what takes effect."""
        session = harvest.build_session()
        assert session.proxies == {}
        assert session.trust_env is True
