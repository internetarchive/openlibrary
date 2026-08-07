import json
import urllib.parse
from typing import cast
from unittest import mock

from openlibrary.plugins.upstream.mybooks import MyBooksTemplate

PENDING_ACTION = urllib.parse.quote(json.dumps({"action": "Borrow", "name": "The Hobbit", "url": "/works/OL1W", "type": "work"}))


def render_banner(cookie: str | None) -> str:
    """Render the Preserve Intent banner for a given `pending_action` cookie.

    `get_pending_action_banner` reads only `web.cookies()`, never `self`, so it
    can be exercised without building a whole MyBooksTemplate.
    """
    cookies = {"pending_action": cookie} if cookie is not None else {}
    with mock.patch("openlibrary.plugins.upstream.mybooks.web") as mock_web:
        mock_web.cookies.return_value = cookies
        mock_web.net.websafe.side_effect = lambda s: s
        # `self` is genuinely unused by the method, so there is nothing to build.
        return MyBooksTemplate.get_pending_action_banner(cast(MyBooksTemplate, None))


class TestPendingActionBanner:
    def test_tracking_attribute_is_server_rendered(self):
        """Matomo's tag-manager trigger cannot see attributes added after parse.

        This attribute used to be attached in JS at DOMContentLoaded, which
        reached Athena but never Matomo — see #13261. It must be present in the
        server-rendered markup.
        """
        assert 'data-ol-link-track="PreserveIntent|Continue"' in render_banner(PENDING_ACTION)

    def test_tracking_attribute_is_on_the_continue_link(self):
        # Guard against the attribute drifting onto some other element, where
        # the trigger would report the wrong interaction.
        markup = render_banner(PENDING_ACTION)
        link_start = markup.index("<a ")
        link_end = markup.index(">", link_start)
        anchor = markup[link_start:link_end]
        assert "pending-action-link" in anchor
        assert 'data-ol-link-track="PreserveIntent|Continue"' in anchor

    def test_renders_nothing_for_cookies_that_carry_no_usable_intent(self):
        # Nothing to resume means no banner, and therefore no BannerShown event
        # from the template — which keeps the click-through denominator honest.
        for cookie in (None, "", "1", "not-json", urllib.parse.quote(json.dumps({"action": "Borrow"}))):
            assert render_banner(cookie) == ""
