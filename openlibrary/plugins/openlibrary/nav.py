"""Shared navigation destinations for the site header.

Three surfaces render the same set of Browse destinations, each with its own
markup: the desktop Browse popover, the mobile Browse tray (both
``lib/browse_popover.html``) and the hamburger drawer (``lib/nav_head.html``).

Only the destination *table* is shared — what exists, where it points, and its
analytics slug. How a surface presents a destination stays in that surface's
template: the popover promotes the first four to featured rows with an icon and
a blurb, the drawer renders one flat list. Sharing the markup instead would push
icons and layout into this file and buy nothing, since the surfaces genuinely
differ.

Adding a destination is one edit here. Before this table existed the list was
duplicated across the templates and had already drifted — Advanced Search was
missing from the Browse popover.

Labels are translated per call rather than at import, so the list must be built
inside the function: module-level ``_()`` would freeze one request's locale for
the life of the process.
"""

from dataclasses import dataclass

from openlibrary.i18n import gettext as _


@dataclass(frozen=True)
class NavLink:
    """One navigation destination.

    ``track`` is the analytics action slug. It pairs with a per-surface category
    prefix and a positional rank to form the ``data-ol-link-track`` value
    ("category|action|label") that ``ol.analytics.js`` reads on click.
    """

    href: str
    text: str
    track: str


def browse_links() -> list[NavLink]:
    """Browse destinations, in the order surfaces should present them.

    Order is meaningful: the popover features the first four and lists the rest,
    and both surfaces derive their 1-based analytics rank from this position.
    """
    return [
        NavLink("/subjects", _("Subjects"), "Subjects"),
        NavLink("/trending", _("Trending"), "Trending"),
        NavLink("/explore", _("Library Explorer"), "Explore"),
        NavLink("/lists", _("Lists"), "Lists"),
        NavLink("/collections", _("Collections"), "Collections"),
        NavLink("/k-12", _("K-12 Student Library"), "K12Library"),
        NavLink("/booktalks", _("Book Talks"), "BookTalks"),
        NavLink("/random", _("Random Book"), "RandomBook"),
        NavLink("/advancedsearch", _("Advanced Search"), "AdvancedSearch"),
    ]


#: How many leading ``browse_links()`` entries the Browse popover promotes to
#: featured rows. The popover supplies an icon and blurb for exactly these.
BROWSE_FEATURED_COUNT = 4
