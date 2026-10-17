"""Render tests for the My Books sidebar in owner vs visitor states.

The sidebar shows different blocks depending on whether the viewer owns the
page (owners_page) and whether the reading log is public (public):
- owners: everything (profile + actions, goal, shelves, activity, lists)
- public visitors: profile (no "Hi", share-only actions), "Books" nav,
  shelves, lists — but no goal, activity, privacy buttons or "My" labels
- private visitors: profile header (avatar + name) and lists only

These tests render ``account/sidebar.html`` with stubbed template globals.
"""

import time as time_module
from pathlib import Path
from types import SimpleNamespace

from web.template import Template


def _gettext_stub(s, **kwargs):
    return s % kwargs if kwargs else s


def render_sidebar(username="someuser", key="mybooks", owners_page=False, public=False, counts=None, lists=None):
    text = Path("openlibrary/templates/account/sidebar.html").read_text(encoding="utf-8")
    template = Template(
        text,
        "account/sidebar.html",
        globals={
            "time": time_module.time,
            "_": _gettext_stub,
            "ctx": SimpleNamespace(path="/people/someuser/books", get=lambda key, default=None: default),
            "request": SimpleNamespace(canonical_url="http://localhost/people/someuser/books", home="http://localhost"),
            # ShareModal stub renders just the trigger markup (args[2]),
            # so share triggers stay observable without the real macro.
            "macros": SimpleNamespace(ShareModal=lambda *args, **kwargs: args[2] if len(args) > 2 else ""),
            "set_share_links": lambda *args, **kwargs: None,
            "get_reading_goals": lambda year=None: None,
            "current_year": lambda: 2026,
            "shelf_ids": lambda: {
                "currently-reading": 1,
                "want-to-read": 2,
                "already-read": 3,
                "stopped-reading": 4,
            },
        },
    )
    return str(
        template(
            username,
            key,
            owners_page,
            public,
            counts if counts is not None else {},
            lists if lists is not None else [],
            {},
        )
    )


FULL_COUNTS = {
    "currently-reading": 1,
    "want-to-read": 2,
    "already-read": 3,
    "stopped-reading": 0,
    "notes": 4,
    "observations": 5,
    "following": 6,
    "followers": 7,
}


def test_owner_sees_everything():
    html = render_sidebar(owners_page=True, public=True, counts=FULL_COUNTS)
    assert "Hi," in html
    assert "/account/privacy" in html
    assert "Public profile" in html
    assert "MyBooksModalLinkClick|ShareIcon" in html
    assert 'slot="trigger"' in html
    assert "My Books" in html
    assert "My Feed" in html
    assert "Reading Goal" in html
    assert "Activity" in html
    assert "Bookshelves" in html
    assert "My lists" in html


def test_public_visitor_has_no_owner_content():
    html = render_sidebar(owners_page=False, public=True, counts=FULL_COUNTS)
    # Profile header without the owner's greeting voice
    assert "Hi," not in html
    assert "someuser" in html
    # No privacy settings links for visitors ...
    assert "/account/privacy" not in html
    assert "Private profile" not in html
    assert "Public profile" not in html
    # ... but the share trigger stays (full-width labeled button)
    assert "MyBooksModalLinkClick|ShareIcon" in html
    assert 'slot="trigger"' in html
    assert ">Share<" in html
    # Neutral labels, owner links gone
    assert "My Books" not in html
    assert "My Feed" not in html
    assert "My Reading Stats" not in html
    assert "Import your data" not in html
    assert "Reading Goal" not in html
    assert "Activity" not in html
    # Shelves and lists stay
    assert "Bookshelves" in html
    assert "Lists" in html


def test_private_visitor_sees_profile_lists_and_share():
    html = render_sidebar(owners_page=False, public=False, counts={}, lists=[])
    assert "someuser" in html
    assert "Hi," not in html
    # No privacy settings, no follow counts ...
    assert "/account/privacy" not in html
    assert "Following" not in html
    assert "Followers" not in html
    # ... but the share trigger stays
    assert "MyBooksModalLinkClick|ShareIcon" in html
    assert 'slot="trigger"' in html
    assert ">Share<" in html
    assert "Bookshelves" not in html
    assert "Reading Goal" not in html
    assert "Activity" not in html
    assert "Lists" in html
    assert "All lists" in html
