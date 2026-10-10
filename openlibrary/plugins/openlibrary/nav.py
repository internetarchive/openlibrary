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

Adding a destination is one edit here — the surfaces pick it up on their own.
Give it an icon in ``browse_popover.html``'s ``navIcons`` too, or the popover
falls back to a generic one. Before this table existed the list was duplicated
across the templates and had already drifted — Advanced Search was missing from
the Browse popover.

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


def mybooks_links() -> list[list[NavLink]]:
    """My Books destinations, grouped as the My Books popover presents them.

    The first group is featured (icon tile + blurb); each later group is a plain
    link list set off by a divider. ``/account/...`` paths redirect to the
    patron's own pages, or to login when signed out, so no username is needed.
    """
    return [
        [
            NavLink("/account/books", _("My Books"), "MyBooks"),
            NavLink("/account/loans", _("Loans & History"), "Loans"),
            NavLink("/account/lists", _("My Lists"), "MyLists"),
        ],
        [
            NavLink("/account/books/want-to-read", _("Want to Read"), "WantToRead"),
            NavLink("/account/books/currently-reading", _("Currently Reading"), "CurrentlyReading"),
            NavLink("/account/books/already-read", _("Already Read"), "AlreadyRead"),
            NavLink("/account/books/stopped-reading", _("Stopped Reading"), "StoppedReading"),
        ],
        [
            NavLink("/account/books/feed", _("My Feed"), "MyFeed"),
            NavLink("/account/books/notes", _("My Notes"), "MyNotes"),
            NavLink("/account/books/observations", _("My Reviews"), "MyReviews"),
            NavLink("/account/books/already-read/stats", _("My Reading Stats"), "ReadingStats"),
            NavLink("/account/import", _("Import & Export Options"), "ImportExport"),
        ],
    ]
