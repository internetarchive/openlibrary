"""Who the outside sources are, in words a newcomer can trust.

``kind`` groups sources by lineage so the evidence sentence can say
"library catalogs agree" rather than count records that share one origin.
"""

from dataclasses import dataclass

from openlibrary.i18n import gettext as _


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    kind: str
    blurb: str
    why_trusted: str


def get_sources() -> dict[str, Source]:
    """Built per request so the strings pick up the visitor's language."""
    return {
        "loc": Source(
            "loc",
            _("Library of Congress"),
            "library",
            _("The national library of the United States. Its catalog describes the books publishers deposit there, from the book itself."),
            _("Records are made by cataloguers holding the physical book, so what they say about a printed edition is usually right."),
        ),
        "googlebooks": Source(
            "googlebooks",
            _("Google Books"),
            "bookseller",
            _("Google's book index, built from publisher feeds and scanned copies."),
            _("Good for titles, dates and page counts of recent trade books. Publisher names can be the parent company rather than the imprint on the book."),
        ),
        "siblings": Source(
            "siblings",
            _("Other editions on Open Library"),
            "openlibrary",
            _("The other editions of this same work already catalogued here."),
            _("They show how this catalog already spells things, which keeps records consistent."),
        ),
    }
