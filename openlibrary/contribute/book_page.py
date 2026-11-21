"""Tasks on the book page: the fields an edition's own page offers to fill in, each answered in a drawer beside the record.

Only signed-in members are asked, on the edition's own page, in the slot where the value would show. The check for
"missing" and the stop rule are the ones Tasks uses, so a book page never asks for what Tasks would not.
"""

from openlibrary.contribute import initiatives, tasks

# The fields a book page asks for, in the order its summary row shows them. All live on the edition.
FIELDS = ("publish_date", "publishers", "languages", "number_of_pages")
# Where the drawer reads its form and posts its answer: ``URL/OL…M/<field>``.
URL = "/tasks/fill"
# ``data.door`` on a save made here, so the stats can tell it from one made on a Tasks page.
DOOR = "book-page"


def open_fields(edition, site, user_key: str) -> list[str]:
    """The fields to offer ``user_key`` on this edition's page: empty, and neither set aside nor already not found by them."""
    if not (missing := [fld for fld in FIELDS if tasks.is_missing(edition, fld)]):
        return []
    stopped = initiatives.not_found_on(site, edition.key, user_key)
    return [fld for fld in missing if fld not in stopped]
