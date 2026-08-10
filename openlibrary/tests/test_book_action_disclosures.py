"""Both book-action disclosures are built on <ol-popover>.

The reading-log dropper used to toggle a hidden div from an
`<a href="javascript:;">` with no ARIA at all, and the read button used a
separate `<details>` element. Two implementations, one of them inaccessible.
Both now slot a real `<button>` into `<ol-popover>`, which supplies
aria-haspopup/aria-expanded/aria-controls, Escape and outside-click dismissal,
and focus restore.
"""

import web
from bs4 import BeautifulSoup

from infogami.utils import macro
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
    assert "Locate" in menu.get_text()


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
