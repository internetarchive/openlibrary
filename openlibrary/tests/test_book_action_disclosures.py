"""Both book-action disclosures are built on <ol-popover>.

The reading-log dropper used to toggle a hidden div from an
`<a href="javascript:;">` with no ARIA at all, and the read button used a
separate `<details>` element. Two implementations, one of them inaccessible.
Both now slot a real `<button>` into `<ol-popover>`, which supplies
aria-haspopup/aria-expanded/aria-controls, Escape and outside-click dismissal,
and focus restore.
"""

import re
from pathlib import Path

import web
from bs4 import BeautifulSoup

from infogami.utils import macro
from infogami.utils.context import context as infogami_ctx
from openlibrary.utils.request_context import site


def analytics_attr(action):
    """Stand-in for the callable LoanStatus passes into ReadButton."""
    return f'data-ol-link-track="CTAClick|{action}"'


def render_macro(name, *a, **kw):
    """Render a macro from ``openlibrary/macros``.

    The ``render_template`` fixture only loads ``templates/``; macros live in
    their own store, and one macro calling another (ReadButton -> LocateButton)
    resolves through the ``macros`` template global.
    """
    macro.load_macros("openlibrary", lazy=False)
    # Templates reach sibling macros by attribute (macros.LocateButton), which
    # the raw DictPile store does not support.
    web.template.Template.globals["macros"] = web.storage({k: macro.macrostore[k] for k in macro.macrostore})
    # These macros ask who is logged in; render them as a logged-out patron.
    site.set(web.storage(get_user=lambda: None))
    # LoanStatus ends in a query_param('debug') block, which reaches for the
    # request method. The fixture builds ctx.env empty.
    web.ctx.env.setdefault("REQUEST_METHOD", "GET")
    # The dropper reads the current path off infogami's context, to send a
    # logged-out patron back here after signing in.
    infogami_ctx.path = "/search"
    infogami_ctx.user = None
    return str(macro.macrostore[name](*a, **kw))


def test_dropper_disclosure_is_a_button_in_a_popover(render_template, request_context_fixture):
    request_context_fixture(lang="en")
    html = render_template(
        "lib/dropper",
        "<button>Want to Read</button>",
        "<div>shelves</div>",
        dropdown_label="More reading options for Dune",
    )
    soup = BeautifulSoup(html, "lxml")

    popover = soup.find("ol-popover")
    assert popover is not None, "the drop-down must be presented by <ol-popover>"

    trigger = soup.find(class_="generic-dropper__dropclick")
    assert trigger.name == "button", "the disclosure must be a real button, not an anchor"
    assert trigger["type"] == "button"
    assert trigger["slot"] == "trigger", "the popover only toggles on its slotted trigger"
    assert trigger["aria-label"] == "More reading options for Dune"

    # The primary action must stay outside the trigger, or clicking it would
    # both submit the shelf form and toggle the panel.
    assert trigger.find("button") is None
    assert soup.find(class_="generic-dropper__primary").find_parent("ol-popover") is None

    assert 'href="javascript:;"' not in str(html)


def test_read_button_overflow_is_a_popover_not_details(render_template, request_context_fixture):
    request_context_fixture(lang="en")
    html = render_macro("ReadButton", "someocaid", analytics_attr, listen=True, edition_key="OL1M")
    soup = BeautifulSoup(html, "lxml")

    assert soup.find("details") is None, "the <details> overflow has been replaced"

    popover = soup.find("ol-popover")
    assert popover is not None
    assert popover["aria-label"] == "More reading options"

    trigger = soup.find(class_="cta-dropper__toggle")
    assert trigger.name == "button"
    assert trigger["type"] == "button"
    assert trigger["slot"] == "trigger"

    # Both overflow items survive the move.
    menu = soup.find(class_="dropper-menu")
    assert "Listen" in menu.get_text()
    assert "Find in a library" in menu.get_text()


def test_read_button_has_no_overflow_when_there_is_nothing_to_put_in_it(render_template, request_context_fixture):
    """Carousels used to be excluded by string-matching the analytics attribute.

    The only thing that should decide this is whether there are menu items.
    """
    request_context_fixture(lang="en")
    html = render_macro("ReadButton", "someocaid", analytics_attr, listen=False)
    soup = BeautifulSoup(html, "lxml")

    assert soup.find("ol-popover") is None
    assert soup.find("details") is None
    assert soup.find(class_="cta-btn--read") is not None


def test_read_button_overflow_does_not_depend_on_the_analytics_string(render_template, request_context_fixture):
    request_context_fixture(lang="en")

    def carousel_attr(action):
        return f'data-ol-link-track="BookCarousel|CTAClick|{action}"'

    html = render_macro("ReadButton", "someocaid", carousel_attr, listen=True, edition_key="OL1M")

    assert BeautifulSoup(html, "lxml").find("ol-popover") is not None


# ── Access labels are verbs ───────────────────────────────────────────────────
#
# The access slot used to carry ten labels mixing verbs (Read, Borrow), a noun
# (Audiobook) and four statuses (Preview Only, Checked Out, Not in Library,
# Special Access). Statuses now render as a caption beside the button.

RETIRED_LABELS = ["Preview Only", "Special Access", "Checked Out", "Not in Library", "Audiobook", "Locate"]


def test_print_disabled_access_reads_as_a_verb(render_template, request_context_fixture):
    request_context_fixture(lang="en")
    html = render_macro("ReadButton", "someocaid", analytics_attr, printdisabled=True)
    label = BeautifulSoup(html, "lxml").find("a", class_="cta-btn").get_text(strip=True)

    assert label == "Read"
    # The explanation survives as the link's title, and as the state line.
    assert "print disabilities" in BeautifulSoup(html, "lxml").find("a", class_="cta-btn")["title"]


def test_preview_button_is_never_labelled_preview_only(render_template, request_context_fixture):
    request_context_fixture(lang="en")
    html = render_macro("BookPreview", "someocaid")
    label = BeautifulSoup(html, "lxml").find("a", class_="cta-btn--preview").get_text(strip=True)

    assert label == "Preview"


def test_locate_button_names_the_destination(render_template, request_context_fixture):
    request_context_fixture(lang="en")
    for icon in (True, False):
        html = render_macro("LocateButton", "OL1M", icon=icon)
        assert "Find in a library" in BeautifulSoup(html, "lxml").get_text()


def test_no_macro_still_ships_a_retired_access_label(render_template, request_context_fixture):
    """A guard against the vocabulary drifting back open."""
    request_context_fixture(lang="en")
    sources = [
        Path("openlibrary/macros/ReadButton.html"),
        Path("openlibrary/macros/BookPreview.html"),
        Path("openlibrary/macros/LocateButton.html"),
        Path("openlibrary/macros/LoanStatus.html"),
        Path("openlibrary/templates/book_providers/read_button.html"),
    ]
    for source in sources:
        text = source.read_text(encoding="utf-8")
        # Only look at translated strings, so explanatory comments are exempt.
        translated = re.findall(r"_\(\s*[\"']([^\"']+)[\"']", text)
        for label in RETIRED_LABELS:
            assert label not in translated, f"{source} still offers {label!r} as a label"


def test_not_in_library_macro_is_gone():
    assert not Path("openlibrary/macros/NotInLibrary.html").exists()


# ── The action column ─────────────────────────────────────────────────────────
#
# Access and Save are separate systems. BookActions groups them in one place so
# the hierarchy between them is set once rather than re-derived per surface.


def book_doc(**overrides):
    doc = web.storage(key="/works/OL1W", title="Dune", availability={})
    doc.update(overrides)
    return doc


def test_book_actions_groups_access_above_save(render_template, request_context_fixture):
    request_context_fixture(lang="en")
    html = render_macro("BookActions", book_doc())
    soup = BeautifulSoup(html, "lxml")

    group = soup.find(class_="book-actions")
    assert group is not None

    regions = [c.get("class")[0] for c in group.find_all("div", recursive=False) if c.get("class")]
    assert regions == ["book-actions__access", "book-actions__save"]


def test_book_actions_can_omit_either_half(render_template, request_context_fixture):
    request_context_fixture(lang="en")

    no_save = BeautifulSoup(render_macro("BookActions", book_doc(), show_save=False), "lxml")
    assert no_save.find(class_="book-actions__access") is not None
    assert no_save.find(class_="book-actions__save") is None

    no_access = BeautifulSoup(render_macro("BookActions", book_doc(), show_access=False), "lxml")
    assert no_access.find(class_="book-actions__access") is None
    assert no_access.find(class_="book-actions__save") is not None


def test_book_actions_uses_a_shelf_status_the_page_already_loaded(render_template, request_context_fixture):
    """add_read_statuses() stamps `readinglog` on each doc in one query.

    The dropper must read that rather than querying per book — a search page
    renders twenty of these.
    """
    request_context_fixture(lang="en")
    html = render_macro("BookActions", book_doc(readinglog=2))

    label = BeautifulSoup(html, "lxml").find(class_="book-progress-btn").get_text(strip=True)
    assert "Currently Reading" in label
