"""Standalone affiliate link URL helpers.

Kept in openlibrary.core (not openlibrary.plugins) so they can be unit-tested
without triggering the partials -> code.setup() -> partials circular import.
"""

from urllib.parse import quote


def amazon_affiliate_url(isbn: str | None, asin: str | None, tag: str) -> str | None:
    """Return an Amazon affiliate URL for a book, handling 979-prefix ISBNs.

    Amazon's /dp/<ASIN>/ route only accepts ISBN-10 or a real ASIN.
    For 979-prefix ISBN-13s, isbn_13_to_isbn_10() returns None because no
    ISBN-10 equivalent exists (per @hornc: Amazon assigns an arbitrary ASIN
    that cannot be derived programmatically).  In that case we fall back to
    an Amazon search URL (per @mekarpeles).  We gate on isbn_13_to_isbn_10()
    not a raw startswith('979') check so that ISBN structural knowledge stays
    inside isbn utils (per @cdrini).  This fixes issue #6572.

    Args:
        isbn: ISBN-13 string (canonical, digits only), or None.
        asin: Pre-resolved ASIN (e.g. from edition identifiers or ISBN-10),
              or None.  Takes priority over isbn conversion.
        tag:  Amazon affiliate tag.

    Returns:
        A fully-formed Amazon URL, or None if neither isbn nor asin provided.
    """
    from openlibrary.utils.isbn import isbn_13_to_isbn_10

    effective_asin = asin or (isbn and isbn_13_to_isbn_10(isbn))
    if effective_asin:
        return f"https://www.amazon.com/dp/{quote(effective_asin)}/?tag={tag}"
    if isbn:
        return f"https://www.amazon.com/s?k={quote(isbn)}&i=stripbooks&tag={tag}"
    return None
