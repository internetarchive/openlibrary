"""Shared book-data helpers for IA-backed carousels and search results."""

import web

from openlibrary.core import ia

CAROUSELS_PRESETS = {
    "preset:comics": (
        '(subject:"comics" OR creator:("Gary Larson") OR creator:("Larson, Gary") '
        'OR creator:("Charles M Schulz") OR creator:("Schulz, Charles M") OR '
        'creator:("Jim Davis") OR creator:("Davis, Jim") OR creator:("Bill Watterson")'
        'OR creator:("Watterson, Bill") OR creator:("Lee, Stan"))'
    ),
    "preset:authorsalliance_mitpress": (
        "(openlibrary_subject:(authorsalliance) OR collection:(mitpress) OR publisher:(MIT Press) OR openlibrary_subject:(mitpress))"
    ),
}


def format_book_data(book, fetch_availability=True):
    """Format an IA search result / edition doc into the shape carousel cards consume."""
    d = web.storage()
    d.key = book.get("key")
    d.url = book.url()
    d.title = book.title or None
    d.ocaid = book.get("ocaid")
    d.eligibility = book.get("eligibility", {})
    d.availability = book.get("availability", {})

    def get_authors(doc):
        return [web.storage(key=a.key, name=a.name or None) for a in doc.get_authors()]

    work = book.works and book.works[0]
    d.authors = get_authors(work or book)
    d.work_key = work.key if work else book.key

    if cover := book.get_cover():
        d.cover_url = cover.url("M")
    elif d.ocaid:
        d.cover_url = "https://archive.org/services/img/%s" % d.ocaid

    if fetch_availability and d.ocaid:
        collections = ia.get_metadata(d.ocaid).get("collection", [])

        if "inlibrary" in collections:
            d.borrow_url = book.url("/borrow")
        else:
            d.read_url = book.url("/borrow")
    return d
