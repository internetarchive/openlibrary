"""Tests for openlibrary.core.layout — guarantee layout is data-only."""

import pathlib
import re

import pytest

import infogami.utils.flash as flash_module
from infogami.utils.context import context as infogami_ctx
from openlibrary.core.layout import (
    AnnouncementBanner,
    HeadContext,
    LayoutContext,
    SentryContext,
    can_show_librarian_tools,
)


@pytest.fixture(autouse=True)
def _patch_get_current_user(monkeypatch):
    """Default get_current_user to None for layout tests so LayoutContext.build() is safe."""
    monkeypatch.setattr("openlibrary.core.layout.get_current_user", lambda: None)


TEMPLATES_DIR = pathlib.Path(__file__).resolve().parents[3] / "openlibrary" / "templates"
LAYOUT_TEMPLATES = [
    TEMPLATES_DIR / "site.html.jinja",
    TEMPLATES_DIR / "site" / "alert.html.jinja",
    TEMPLATES_DIR / "site" / "banner.html.jinja",
    TEMPLATES_DIR / "site" / "head.html.jinja",
    TEMPLATES_DIR / "lib" / "nav_foot.html.jinja",
    TEMPLATES_DIR / "lib" / "nav_head.html.jinja",
    TEMPLATES_DIR / "lib" / "browse_popover.html.jinja",
    TEMPLATES_DIR / "lib" / "header_dropdown.html.jinja",
    TEMPLATES_DIR / "search" / "availability_i18n.html.jinja",
    TEMPLATES_DIR / "search" / "search_modal_i18n.html.jinja",
    TEMPLATES_DIR / "languages" / "language_list.html.jinja",
    TEMPLATES_DIR / "site" / "stats.html.jinja",
]


def test_layout_context_contains_no_callables(request_context_fixture):
    """LayoutContext.build() must be pure data — no functions that could hide I/O."""
    request_context_fixture(lang="en")
    layout = LayoutContext.build()
    # __post_init__ already guards this, but double-check via to_dict
    for key, val in layout.to_dict().items():
        assert not callable(val), f"{key} is callable"
        if isinstance(val, dict):
            for k, v in val.items():
                assert not callable(v), f"{key}[{k!r}] is callable"
                if isinstance(v, dict):
                    for kk, vv in v.items():
                        assert not callable(vv), f"{key}[{k!r}][{kk!r}] is callable"
        elif isinstance(val, list):
            for idx, item in enumerate(val):
                assert not callable(item), f"{key}[{idx}] is callable"
                if isinstance(item, dict):
                    for k, v in item.items():
                        assert not callable(v), f"{key}[{idx}][{k!r}] is callable"


def test_layout_templates_do_not_call_layout_fields():
    """Site shell templates must not call layout fields as functions.

    Allowed: data traversals like `layout.stats_summary.items()` (dict method).
    Not allowed: `layout.foo()` where foo is a layout field that could be a
    passed-in function doing network I/O.

    This keeps the layout side fast and pre-computed.
    """
    # Direct layout field call: layout.<field>(...
    direct_call = re.compile(r"layout\.\w+\s*\(")
    for path in LAYOUT_TEMPLATES:
        text = path.read_text()
        # .items() / .values() / .keys() are on the *value* of a field, not on layout itself.
        # Strip those safe calls before checking, so we only flag layout.field(.
        safe_stripped = re.sub(r"layout\.\w+\.\w+\s*\(", "SAFE(", text)
        assert not direct_call.search(safe_stripped), f"{path} calls layout field as function"


def test_layout_context_is_frozen():
    """LayoutContext must stay frozen — templates must not mutate it."""
    layout = LayoutContext(
        show_ol_shell=True,
        is_debug=False,
        is_bot=False,
        total_time_ms=0.0,
        supported_languages=[],
        git_rev_hash="",
        lang="en",
        stats_summary={},
        stats_details=[],
        body_classes=[],
        body_attrs=[],
        donate_script_url="",
        flash_messages=[],
        user=None,
        ol_env="production",
        is_local_dev=False,
        page_status_url="",
        is_recognized_bot=False,
        is_print_disabled=False,
        homepath="",
        my_books_props={},
        browse_links=[],
        featured_browse_links=[],
        simple_browse_links=[],
        browse_featured_count=4,
        head=HeadContext(
            title="",
            domain="",
            canonical_url="",
            disable_analytics=False,
            page_css_path="build/css/page-user.css",
            experiments_json="{}",
            robots="",
            description="",
            links=[],
            metatags=[],
            icon_sprite_url="",
            days_registered_json='"visitor"',
            sentry=None,
        ),
        announcement_banner=None,
    )
    with pytest.raises((AttributeError, TypeError)):
        layout.lang = "fr"  # type: ignore[misc]


def test_can_show_librarian_tools():
    """Librarian tools should only activate for privileged users on specific catalog paths."""

    class LibrarianUser:
        def is_librarian_or_higher(self):
            return True

    class NormalUser:
        def is_librarian_or_higher(self):
            return False

    assert can_show_librarian_tools("/works/OL12345W", LibrarianUser())
    assert can_show_librarian_tools("/authors/OL12345A", LibrarianUser())
    assert can_show_librarian_tools("/books/OL12345M", LibrarianUser())
    assert can_show_librarian_tools("/search", LibrarianUser())
    assert not can_show_librarian_tools("/about", LibrarianUser())
    assert not can_show_librarian_tools("/works/OL12345W", NormalUser())
    assert not can_show_librarian_tools("/works/OL12345W", None)


def test_layout_build_body_classes_and_librarian_tools(monkeypatch, request_context_fixture):
    """LayoutContext should include 'show-librarian-tools' for librarians on catalog paths."""
    request_context_fixture(lang="en")

    class MockUser:
        key = "/people/librarian_bob"

        def is_librarian_or_higher(self):
            return True

    mock_user = MockUser()
    infogami_ctx["bodyclass"] = ["custom-class"]
    infogami_ctx["bodyattrs"] = ["itemscope"]
    infogami_ctx["show_ol_shell"] = True
    infogami_ctx["path"] = "/works/OL12345W"
    infogami_ctx["user"] = mock_user
    monkeypatch.setattr("openlibrary.core.layout.get_current_user", lambda: mock_user)

    layout = LayoutContext.build()
    assert "custom-class" in layout.body_classes
    assert "show-librarian-tools" in layout.body_classes
    assert "custom-class" in layout.body_class
    assert "show-librarian-tools" in layout.body_class
    assert "itemscope" in layout.body_attrs
    assert 'data-user-key="/people/librarian_bob"' in layout.body_attrs

    # Reset
    infogami_ctx.clear()


def test_layout_build_active_ui_lang(request_context_fixture):
    """LayoutContext should resolve active_ui_lang property from request language."""
    request_context_fixture(lang="es")
    layout = LayoutContext.build()
    assert layout.active_ui_lang["code"] == "es"
    assert layout.active_ui_lang["native"] == "Español"


def test_layout_build_donate_script_url(monkeypatch, request_context_fixture):
    """LayoutContext should set donate_script_url and backward-compatible donate_script_src."""
    request_context_fixture(lang="en")
    layout = LayoutContext.build()
    assert layout.donate_script_url == "/cdn/archive.org/donate.js"
    assert layout.donate_script_src == "/cdn/archive.org/donate.js"


def test_layout_build_flash_messages(monkeypatch, request_context_fixture):
    """LayoutContext should extract and format flash messages into pure dicts."""
    request_context_fixture(lang="en")
    monkeypatch.setattr(
        flash_module,
        "get_flash_messages",
        lambda: [{"type": "error", "message": "Invalid password"}],
    )
    layout = LayoutContext.build()
    assert layout.flash_messages == [{"type": "error", "message": "Invalid password"}]


def test_announcement_banner_structure():
    """AnnouncementBanner should be a frozen data object."""
    banner = AnnouncementBanner(content="Maintenance scheduled", cookie_name="maint_2026", cookie_duration_days=7)
    assert banner.content == "Maintenance scheduled"
    assert banner.cookie_name == "maint_2026"
    assert banner.cookie_duration_days == 7
    with pytest.raises((AttributeError, TypeError)):
        banner.content = "New content"  # type: ignore[misc]


def test_layout_build_header_user_logged_out(request_context_fixture):
    """LayoutContext should have user=None when no user is logged in."""
    request_context_fixture(lang="en")
    layout = LayoutContext.build()
    assert layout.user is None


def test_layout_build_header_user_logged_in(monkeypatch, request_context_fixture):
    """LayoutContext should build HeaderUser when a user is logged in."""
    request_context_fixture(lang="en")

    class MockUser:
        key = "/people/super_librarian"
        created = "2020-01-01"

        def is_librarian_or_higher(self):
            return True

        def is_super_librarian_or_higher(self):
            return True

    monkeypatch.setattr("openlibrary.core.layout.get_current_user", MockUser)
    monkeypatch.setattr("openlibrary.core.layout.get_internet_archive_id", lambda key: "ia_bob")
    monkeypatch.setattr("openlibrary.core.layout.cached_get_counts_by_mode", lambda mode="open": 42)

    layout = LayoutContext.build()
    assert layout.user is not None
    assert layout.user.key == "/people/super_librarian"
    assert layout.user.username == "super_librarian"
    assert layout.user.ia_id == "ia_bob"
    assert "super_librarian" in layout.user.account_title
    assert layout.user.is_privileged_user is True
    assert layout.user.shows_merge_count is True
    assert layout.user.open_merges_count == 42


def test_layout_build_header_navigation(request_context_fixture):
    """LayoutContext should build header navigation props and browse links."""
    request_context_fixture(lang="en")
    layout = LayoutContext.build()
    assert layout.my_books_props["name"] == "mybooks"
    assert layout.my_books_props["label"] == "My Books"
    assert len(layout.my_books_props["links"]) == 1
    assert layout.my_books_props["links"][0]["track"] == "MyBooks"
    assert len(layout.browse_links) > 0
    assert len(layout.featured_browse_links) == 4
    assert len(layout.simple_browse_links) == len(layout.browse_links) - 4
    assert layout.ol_env in ("production", "development", "testing")


def test_layout_build_head_defaults(request_context_fixture):
    """Head fields should have safe defaults on a bare request context."""
    request_context_fixture(lang="en")
    layout = LayoutContext.build()
    head = layout.head
    assert head.title == ""
    assert head.disable_analytics is False
    assert head.page_css_path == "build/css/page-user.css"
    assert head.experiments_json == "{}"
    assert head.robots == ""
    assert head.description == ""
    assert head.links == []
    assert head.metatags == []
    assert head.days_registered_json == '"visitor"'
    assert head.sentry is None
    assert isinstance(head.canonical_url, str)
    assert isinstance(head.domain, str)
    assert isinstance(head.icon_sprite_url, str)
    assert isinstance(layout.is_local_dev, bool)


def test_layout_build_head_title_passthrough(request_context_fixture):
    """``build(title=...)`` should surface the page title for the <head>."""
    request_context_fixture(lang="en")
    layout = LayoutContext.build(title="The Hobbit")
    assert layout.head.title == "The Hobbit"


def test_layout_build_head_reads_page_context(request_context_fixture):
    """Head fields should be sourced from the per-page infogami context."""
    request_context_fixture(lang="en")
    infogami_ctx["disable_analytics"] = True
    infogami_ctx["cssfile"] = "work"
    infogami_ctx["experiments"] = {"foo": "bar"}
    infogami_ctx["robots"] = "noindex"
    infogami_ctx["description"] = "A description"
    infogami_ctx["links"] = ['<link rel="alternate" href="/x">']
    infogami_ctx["metatags"] = ['<meta name="custom" content="v">']
    try:
        head = LayoutContext.build().head
        assert head.disable_analytics is True
        assert head.page_css_path == "build/css/page-work.css"
        assert head.experiments_json == '{"foo": "bar"}'
        assert head.robots == "noindex"
        assert head.description == "A description"
        assert head.links == ['<link rel="alternate" href="/x">']
        assert head.metatags == ['<meta name="custom" content="v">']
    finally:
        infogami_ctx.clear()


def test_sentry_context_build_disabled_returns_none(monkeypatch):
    """Sentry should be None when no client is configured."""
    monkeypatch.setattr("openlibrary.utils.sentry.get_sentry", lambda: None)

    assert SentryContext.build() is None


def test_sentry_context_build_enabled_precomputes_fields(monkeypatch):
    """An enabled Sentry client should be flattened into a frozen data object."""
    sentry = type(
        "Sentry",
        (),
        {
            "enabled": True,
            "get_traceparent": lambda self: "TRACE",
            "get_baggage": lambda self: "BAGGAGE",
            "get_frontend_config": lambda self: {"dsn": "https://x"},
        },
    )()
    monkeypatch.setattr("openlibrary.utils.sentry.get_sentry", lambda: sentry)

    result = SentryContext.build()
    assert isinstance(result, SentryContext)
    assert result.traceparent == "TRACE"
    assert result.baggage == "BAGGAGE"
    assert result.frontend_config_json == '{"dsn": "https://x"}'
