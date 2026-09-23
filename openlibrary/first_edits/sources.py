"""The outside sources the evidence rows name.

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


def get_sources() -> dict[str, Source]:
    """Built per request so the strings pick up the visitor's language."""
    return {
        "loc": Source("loc", _("Library of Congress"), "library"),
        "googlebooks": Source("googlebooks", _("Google Books"), "bookseller"),
        "siblings": Source("siblings", _("Other editions on Open Library"), "openlibrary"),
    }
