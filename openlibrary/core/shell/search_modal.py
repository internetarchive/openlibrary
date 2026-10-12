"""Translated strings for the header search modal, built for client-side fill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchModalContext:
    """Translated strings for the header search modal.

    Built here in Python, not in a Jinja template, because these strings are
    serialized to JSON in the trigger's ``data-i18n*`` attributes and filled in
    client-side (``sprintf``); they must reach the browser with their ``%s``
    placeholders intact. Jinja's formatting ``_()`` would consume those
    placeholders at render time, corrupting single-``%s`` strings and raising on
    multi-``%s`` ones, so the client-fill strings deliberately bypass it.

    The keys/English text must match the fallbacks in
    ``openlibrary/plugins/openlibrary/js/search-modal/constants.js``.
    """

    availability: dict[str, Any]
    strings: dict[str, Any]


def build_search_modal_i18n() -> SearchModalContext:
    from openlibrary.i18n import gettext as _

    return SearchModalContext(
        availability={
            "all": {"label": _("All books")},
            "readable": {"label": _("Readable Only")},
            "open": {"label": _("Free to read now")},
            "borrowable": {"label": _("Borrow online")},
        },
        strings={
            "dialogAria": _("Search Open Library"),
            "inputPlaceholder": _("Search books and authors…"),
            "inputAria": _("Search"),
            "closeAria": _("Close search"),
            "clearAria": _("Clear search"),
            "seeAll": _("See results"),
            "seeNone": _("Go to full search"),
            "seeOne": _("See %s book"),
            "seeMany": _("See %s books"),
            "seeAllMany": _("See all %s books"),
            "seeAllManyNarrow": _("All %s books"),
            "clearAll": _("Clear all"),
            "tabsAria": _("Search scope"),
            "tabBooks": _("Books"),
            "tabInside": _("Inside books"),
            "filtersAria": _("Search filters"),
            "availabilityLabel": _("Availability"),
            "languageLabel": _("Language"),
            "languagePlaceholder": _("Search languages…"),
            "languageHeading": _("Languages"),
            "languagesLoading": _("Loading…"),
            "searchingBooks": _("Searching books and authors…"),
            "searchingInside": _("Searching inside books…"),
            "noResults": _("No results found"),
            "noCatalogResults": _("No matching books or authors"),
            "resultsAnnounce": _("Showing %s of %s results"),
            "authorResults": _("Authors"),
            "topResults": _("Books"),
            "untitled": _("Untitled"),
            "authorLabel": _("Author"),
            "accessReadable": _("Readable"),
            "readableInLanguage": _("Readable in %s"),
            "recentSearches": _("Recent searches"),
            "removeRecent": _('Remove "%s" from recent searches'),
            "insideHeading": _("Search inside books"),
            "seeAllInsideOne": _("Search Inside %s book"),
            "seeAllInsideMany": _("Search Inside %s books"),
            "seeAllInsidePlain": _("Search Inside"),
            "viewAllInside": _("View all"),
            "insidePlaceholder": _("Search inside books…"),
            "insidePrompt": _("Type a word or phrase to find it on the pages of millions of books."),
            "noInsideResults": _("No matches inside books"),
            "insideError": _("Search inside books is temporarily unavailable. Please try again later."),
            "insideAnnounceOne": _("%s match found inside books"),
            "insideAnnounceMany": _("%s matches found inside books"),
        },
    )
