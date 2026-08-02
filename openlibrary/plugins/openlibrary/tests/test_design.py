"""Tests for the developer design pages."""

from unittest.mock import patch

import pytest
import web

from openlibrary.plugins.openlibrary.design import activity_feed_gallery

DEFAULT = activity_feed_gallery.DEFAULT_API


@pytest.fixture
def host():
    """Pretend the gallery was served from a given host.

    The original is captured before the test runs, not after -- restoring a
    value the test itself set would leak between tests.
    """
    original = getattr(web.ctx, "host", None) or "localhost:8080"

    def _set(value):
        web.ctx.host = value

    yield _set
    web.ctx.host = original


class TestGalleryApiUrl:
    """The gallery's fetch origin is overridable because a local dev stack has no
    proxy from web.py to FastAPI -- but only to the same machine."""

    def test_no_override_uses_the_default_path(self, host):
        host("localhost:8080")
        assert activity_feed_gallery._api_url(None) == DEFAULT
        assert activity_feed_gallery._api_url("") == DEFAULT

    def test_relative_paths_pass_through(self, host):
        host("localhost:8080")
        assert activity_feed_gallery._api_url("/api/internal/activity/feed.json") == "/api/internal/activity/feed.json"

    @pytest.mark.parametrize(
        ("served_from", "requested"),
        [
            ("localhost:8080", "http://localhost:18080/api/internal/activity/feed.json"),
            ("127.0.0.1:8087", "http://127.0.0.1:18087/api/internal/activity/feed.json"),
            # Opening the gallery from a phone on the same network is the point.
            ("192.168.1.223:8087", "http://192.168.1.223:18087/api/internal/activity/feed.json"),
        ],
    )
    def test_same_host_on_another_port_is_allowed(self, host, served_from, requested):
        host(served_from)
        assert activity_feed_gallery._api_url(requested) == requested

    @pytest.mark.parametrize(
        "requested",
        [
            "http://evil.example.com/api/internal/activity/feed.json",
            "//evil.example.com/api/internal/activity/feed.json",
            "javascript:alert(1)",
            "http://localhost.evil.example.com:18080/api/internal/activity/feed.json",
        ],
    )
    def test_another_host_falls_back_to_the_default(self, host, requested):
        host("localhost:8080")
        assert activity_feed_gallery._api_url(requested) == DEFAULT

    def test_a_same_host_url_outside_the_api_falls_back(self, host):
        # The parameter drives a fetch, so keep it pointed at the API surface.
        host("localhost:8080")
        assert activity_feed_gallery._api_url("http://localhost:8080/account/login") == DEFAULT


class TestGalleryVariants:
    def test_variant_ids_are_contiguous_and_match_the_component(self):
        ids = [v["id"] for v in activity_feed_gallery.VARIANTS]
        assert ids == list(range(1, 11))

    def test_every_variant_is_described(self):
        for variant in activity_feed_gallery.VARIANTS:
            assert variant["name"]
            assert variant["blurb"]


class TestGalleryGet:
    def test_clamps_an_unknown_scope(self, host):
        host("localhost:8080")
        captured = {}

        def fake_render(_template, variants, selected, scope, viewer, api):
            captured.update(selected=selected, scope=scope, viewer=viewer, api=api)
            return ""

        with (
            patch("openlibrary.plugins.openlibrary.design.render_template", side_effect=fake_render),
            patch("openlibrary.plugins.openlibrary.design.accounts.get_current_user", return_value=None),
            patch("openlibrary.plugins.openlibrary.design.web.input", return_value=web.storage(design="3", scope="bogus", api=None)),
        ):
            activity_feed_gallery().GET()

        assert captured["scope"] == "auto"
        assert captured["selected"] == 3
        assert captured["viewer"] == ""
        assert captured["api"] == DEFAULT
