"""Tests for openlibrary.core.shell — guarantee layout is data-only."""

import datetime as dt
import pathlib
import re

import pytest
from markupsafe import Markup

from infogami.utils.context import context as infogami_ctx
from openlibrary.core.shell import (
    AnnouncementBanner,
    HeadContext,
    HeaderContext,
    LayoutContext,
    PageMeta,
    SearchModalContext,
    SentryContext,
    ShellRequest,
    ShellUser,
    can_show_librarian_tools,
    load_shell_user,
)


def _req(**overrides) -> ShellRequest:
    return ShellRequest(**({"path": "/", "readable_path": "/", "query_string": "", "host": "localhost"} | overrides))


def _user(**overrides) -> ShellUser:
    values = {"key": "/people/bob", "created": None, "ia_id": None, "is_librarian": False, "is_super_librarian": False, "open_merges_count": 0}
    return ShellUser(**(values | overrides))


def _build(req: ShellRequest | None = None, user: ShellUser | None = None, **page_values) -> LayoutContext:
    return LayoutContext.build(req=req or _req(), page=PageMeta(**page_values), user=user)


TEMPLATES_DIR = pathlib.Path(__file__).resolve().parents[3] / "openlibrary" / "templates"
LAYOUT_TEMPLATES = [
    TEMPLATES_DIR / "shell" / "base.html.jinja",
    TEMPLATES_DIR / "shell" / "alert.html.jinja",
    TEMPLATES_DIR / "shell" / "banner.html.jinja",
    TEMPLATES_DIR / "shell" / "head.html.jinja",
    TEMPLATES_DIR / "shell" / "footer.html.jinja",
    TEMPLATES_DIR / "shell" / "header.html.jinja",
    TEMPLATES_DIR / "shell" / "browse_popover.html.jinja",
    TEMPLATES_DIR / "shell" / "header_dropdown.html.jinja",
    TEMPLATES_DIR / "shell" / "language_list.html.jinja",
    TEMPLATES_DIR / "shell" / "stats.html.jinja",
]


def test_layout_context_contains_no_callables(request_context_fixture):
    """_build() must be pure data — no functions that could hide I/O."""
    request_context_fixture(lang="en")
    layout = _build()
    # Double-check via to_dict; the frozen dataclass is deliberate
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
        ol_env="production",
        is_local_dev=False,
        header=HeaderContext(
            user=None,
            page_status_url="",
            is_recognized_bot=False,
            is_print_disabled=False,
            homepath="",
            my_books_props={},
            browse_links=[],
            browse_featured_count=4,
            search_modal=SearchModalContext(availability={}, strings={}),
        ),
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
        shelf_button_labels_json="{}",
        announcement_banner=None,
    )
    with pytest.raises((AttributeError, TypeError)):
        layout.lang = "fr"  # type: ignore[misc]


def test_can_show_librarian_tools():
    """Librarian tools should only activate for privileged users on specific catalog paths."""

    librarian = _user(is_librarian=True)
    assert can_show_librarian_tools("/works/OL12345W", librarian)
    assert can_show_librarian_tools("/authors/OL12345A", librarian)
    assert can_show_librarian_tools("/books/OL12345M", librarian)
    assert can_show_librarian_tools("/search", librarian)
    assert not can_show_librarian_tools("/about", librarian)
    assert not can_show_librarian_tools("/works/OL12345W", _user())
    assert not can_show_librarian_tools("/works/OL12345W", None)


def test_layout_build_body_classes_and_librarian_tools(request_context_fixture):
    """LayoutContext should include 'show-librarian-tools' for librarians on catalog paths."""
    request_context_fixture(lang="en")
    librarian = _user(key="/people/librarian_bob", is_librarian=True)
    layout = _build(_req(path="/works/OL12345W"), librarian, bodyclass=("custom-class",), bodyattrs=("itemscope",))
    assert layout.body_classes == ["custom-class", "show-librarian-tools"]
    assert layout.body_class == "custom-class show-librarian-tools"
    assert layout.body_attrs == ["itemscope", 'data-user-key="/people/librarian_bob"']


def test_layout_build_active_ui_lang(request_context_fixture):
    """LayoutContext should resolve active_ui_lang property from request language."""
    request_context_fixture(lang="es")
    layout = _build()
    assert layout.active_ui_lang["code"] == "es"
    assert layout.active_ui_lang["native"] == "Español"


def test_layout_build_donate_script_url(request_context_fixture):
    """donate.js comes from the CDN, or from a valid ``?dev_host=`` IA host."""
    request_context_fixture(lang="en")
    assert _build().donate_script_url == "/cdn/archive.org/donate.js"
    assert _build(_req(query_string="dev_host=www-foo")).donate_script_url == "https://www-foo.archive.org/includes/donate.js"
    assert _build(_req(query_string="dev_host=x/y")).donate_script_url == "/cdn/archive.org/donate.js"


def test_layout_build_flash_messages(request_context_fixture):
    """Flash messages come from the request, as plain dicts."""
    request_context_fixture(lang="en")
    layout = _build(_req(flash_messages=({"type": "error", "message": "Invalid password"},)))
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
    layout = _build()
    assert layout.header.user is None


def test_layout_build_header_user_logged_in(request_context_fixture):
    """LayoutContext should build HeaderUser from the ShellUser."""
    request_context_fixture(lang="en")
    user = _user(key="/people/super_librarian", created=dt.datetime(2020, 1, 1), ia_id="ia_bob", is_librarian=True, is_super_librarian=True, open_merges_count=42)

    layout = _build(user=user)
    assert layout.header.user is not None
    assert layout.header.user.key == "/people/super_librarian"
    assert layout.header.user.username == "super_librarian"
    assert layout.header.user.ia_id == "ia_bob"
    assert layout.header.user.account_title == "super_librarian\nJoined January 1, 2020"
    assert layout.header.user.is_privileged_user is True
    assert layout.header.user.shows_merge_count is True
    assert layout.header.user.open_merges_count == 42


class MockUser:
    key = "/people/super_librarian"
    created = dt.datetime(2020, 1, 1)

    def __init__(self, librarian: bool = True, super_librarian: bool = True):
        self.librarian, self.super_librarian = librarian, super_librarian

    def is_librarian_or_higher(self):
        return self.librarian

    def is_super_librarian_or_higher(self):
        return self.super_librarian


def test_load_shell_user(monkeypatch):
    """load_shell_user() does every lookup the shell needs, so building the shell does none."""
    monkeypatch.setattr("openlibrary.core.shell.user.get_current_user", MockUser)
    monkeypatch.setattr("openlibrary.core.shell.user.get_internet_archive_id", lambda key: f"ia:{key}")
    monkeypatch.setattr("openlibrary.core.shell.user.cached_get_counts_by_mode", lambda mode="open": 42)
    assert load_shell_user() == ShellUser(
        key="/people/super_librarian",
        created=dt.datetime(2020, 1, 1),
        ia_id="ia:/people/super_librarian",
        is_librarian=True,
        is_super_librarian=True,
        open_merges_count=42,
    )

    # Only super-librarians see the merge count, so it isn't looked up for anyone else.
    monkeypatch.setattr("openlibrary.core.shell.user.get_current_user", lambda: MockUser(super_librarian=False))
    monkeypatch.setattr("openlibrary.core.shell.user.cached_get_counts_by_mode", pytest.fail)
    user = load_shell_user()
    assert user is not None
    assert (user.is_librarian, user.is_super_librarian, user.open_merges_count) == (True, False, 0)


def test_load_shell_user_degrades_safely(monkeypatch):
    """A visitor is None; a failed lookup falls back instead of failing the page."""
    monkeypatch.setattr("openlibrary.core.shell.user.get_current_user", lambda: None)
    assert load_shell_user() is None

    def boom(*args, **kwargs):
        raise RuntimeError("infobase is down")

    monkeypatch.setattr("openlibrary.core.shell.user.get_current_user", MockUser)
    monkeypatch.setattr("openlibrary.core.shell.user.get_internet_archive_id", boom)
    monkeypatch.setattr(MockUser, "is_librarian_or_higher", boom)
    monkeypatch.setattr(MockUser, "is_super_librarian_or_higher", boom)
    user = load_shell_user()
    assert user is not None
    assert (user.key, user.ia_id, user.is_librarian, user.is_super_librarian) == ("/people/super_librarian", None, False, False)

    monkeypatch.setattr("openlibrary.core.shell.user.get_current_user", boom)
    assert load_shell_user() is None


def test_layout_build_header_navigation(request_context_fixture):
    """LayoutContext should build header navigation props and browse links."""
    request_context_fixture(lang="en")
    layout = _build()
    assert layout.header.my_books_props["name"] == "mybooks"
    assert layout.header.my_books_props["label"] == "My Books"
    assert len(layout.header.my_books_props["links"]) == 1
    assert layout.header.my_books_props["links"][0]["track"] == "MyBooks"
    assert len(layout.header.browse_links) > 0
    assert layout.header.browse_featured_count == 4
    assert layout.ol_env in ("production", "development", "testing")


def test_layout_build_search_modal_preserves_client_fill_placeholders(request_context_fixture):
    """Client-fill strings must keep their ``%s`` for browser-side ``sprintf``.

    Building them in Python (rather than a Jinja template) is what keeps Jinja's
    formatting ``_`` away from placeholders it cannot fill.
    """
    request_context_fixture(lang="en")
    modal = _build().header.search_modal
    assert modal.availability["all"]["label"] == "All books"
    assert modal.strings["seeOne"] == "See %s book"
    assert modal.strings["resultsAnnounce"] == "Showing %s of %s results"
    assert modal.strings["removeRecent"] == 'Remove "%s" from recent searches'


def test_layout_build_head_defaults(request_context_fixture):
    """Head fields should have safe defaults on a bare request context."""
    request_context_fixture(lang="en")
    layout = _build()
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
    """The page title should surface in the <head>."""
    request_context_fixture(lang="en")
    assert _build(title="The Hobbit").head.title == "The Hobbit"


def test_layout_build_head_reads_page_and_request(request_context_fixture):
    """Head fields come from the page meta and the request, nothing else."""
    request_context_fixture(lang="en")
    head = _build(
        _req(host="openlibrary.org", path="/search", readable_path="/search", query_string="q=x&sort=new&debug=1", experiments={"foo": "bar"}),
        disable_analytics=True,
        cssfile="work",
        robots="noindex",
        description="A description",
        links=('<link rel="alternate" href="/x">',),
        metatags=('<meta name="custom" content="v">',),
    ).head
    assert head.domain == "openlibrary.org"
    assert head.canonical_url == "https://openlibrary.org/search?q=x"
    assert head.disable_analytics is True
    assert head.page_css_path == "build/css/page-work.css"
    assert head.experiments_json == '{"foo": "bar"}'
    assert head.robots == "noindex"
    assert head.description == "A description"
    assert head.links == ['<link rel="alternate" href="/x">']
    assert head.metatags == ['<meta name="custom" content="v">']


def test_page_meta_from_infogami_ctx():
    """web.py pages still set head/body values via ``$putctx``; PageMeta reads them."""
    infogami_ctx.clear()  # earlier tests leave page values behind on this thread
    infogami_ctx["cssfile"] = "work"
    infogami_ctx["bodyclass"] = ["a"]
    infogami_ctx["metatags"] = ["<meta>"]
    infogami_ctx["show_ol_shell"] = False
    try:
        page = PageMeta.from_infogami_ctx(title="T")
    finally:
        infogami_ctx.clear()
    assert page == PageMeta(title="T", cssfile="work", bodyclass=("a",), metatags=("<meta>",), show_ol_shell=False)
    # Templetor escaped them already, so the shell mustn't escape them again.
    assert isinstance(page.title, Markup)
    assert isinstance(page.metatags[0], Markup)


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


@pytest.mark.parametrize("host", ["[", "a]", "[abc]"])
def test_malformed_host_leaves_out_the_canonical_link(request_context_fixture, host):
    """The Host header comes from the client: one urlparse rejects drops the canonical link, not the page."""
    request_context_fixture(lang="en")
    assert _build(_req(host=host)).head.canonical_url == ""
