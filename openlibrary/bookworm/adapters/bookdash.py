"""Book Dash source adapter for the BookWorm feed harvest (#14749).

Book Dash (https://bookdash.org) publishes free, openly-licensed African
children's picture books. It has no OPDS feed: the catalogue is an HTML site with
an XML sitemap. This adapter walks that sitemap and scrapes each book page into an
Open Library import record, so Book Dash harvests through the same registry,
staging, dedup and cursor machinery as every OPDS feed.

Ported from the standalone ``scripts/import_bookdash.py`` scraper (#10856, PR
#13237), which this replaces. Two things changed in the move, both because the
live site had drifted from what that scraper assumed:

- **Cover.** The scraper read a ``<picture>`` element that bookdash.org no longer
  emits, so it had silently stopped finding covers. The sitemap carries each
  book's cover in an ``<image:image>`` element, and the page still carries an
  ``og:image`` — we take the former and fall back to the latter. (Coverstore only
  fetches allow-listed hosts, so ``bookdash.org`` is added to
  :data:`openlibrary.coverstore.utils.ALLOWED_COVER_URLS`; without that, covers
  are rejected on upload — which is why the scraper's covers never landed even
  before the ``<picture>`` drift.)
- **Identity / validation.** Each record now carries ``identifiers.bookdash``
  (the page slug) as well as the optional ISBN. A Book Dash book without an ISBN
  used to fail import validation; now the registered-feed exemption
  (:class:`~openlibrary.plugins.importapi.import_validator.FeedSourcedBook`)
  accepts it on the provider identifier, exactly as Lenny and Gutenberg are
  accepted.

The cursor is the sitemap's per-URL ``<lastmod>``: Book Dash is a full-crawl feed
(no ``modified_since``), so the harvester fetches the whole sitemap each run but
only re-scrapes and re-stages books whose ``lastmod`` is newer than the cursor.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import time
from typing import TYPE_CHECKING, Any, NamedTuple
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from openlibrary.coverstore.utils import is_allowed_cover_url

if TYPE_CHECKING:
    from collections.abc import Iterator

    import requests

    from openlibrary.bookworm.registry import FeedRegistry

logger = logging.getLogger("openlibrary.bookworm.adapters.bookdash")

PROVIDER_NAME = "bookdash"
SITEMAP_URL = "https://bookdash.org/books-sitemap.xml"

_SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}
# The sitemap lists the /books/ index page alongside the individual book pages;
# it has no book to scrape, so it is dropped.
_BOOKS_INDEX_URL = "https://bookdash.org/books"

ISBN_RE = re.compile(r"ISBN:\s*([\d\-Xx]+)")
_ROLE_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")

REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.5
"""Seconds to pause between book-page fetches, to be polite to bookdash.org.

A module constant so tests can zero it out rather than sleep for real.
"""


class SitemapEntry(NamedTuple):
    """One book URL from the sitemap, with the two fields the sitemap carries.

    ``cover`` and ``lastmod`` come free with the sitemap, so the per-page scrape
    does not have to find them (the cover in particular is no longer reliably on
    the page — see the module docstring).
    """

    url: str
    lastmod: dt.datetime | None
    cover: str | None


def _parse_lastmod(value: str | None) -> dt.datetime | None:
    """A sitemap ``<lastmod>`` (W3C datetime) as a tz-aware UTC datetime, or None."""
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip())
    except ValueError:
        logger.warning("bookdash: unparsable <lastmod> %r", value)
        return None
    return parsed.replace(tzinfo=dt.UTC) if parsed.tzinfo is None else parsed.astimezone(dt.UTC)


def parse_sitemap(xml: bytes) -> list[SitemapEntry]:
    """Parse the Book Dash sitemap into per-book entries.

    Pure (takes bytes, no I/O) so a captured sitemap is a fixture: if Book Dash
    changes the sitemap's shape, the parse test breaks rather than a live harvest
    silently returning nothing.
    """
    root = ET.fromstring(xml)
    entries: list[SitemapEntry] = []
    for url_el in root.findall("sm:url", _SITEMAP_NS):
        loc_el = url_el.find("sm:loc", _SITEMAP_NS)
        loc = (loc_el.text or "").strip() if loc_el is not None else ""
        if not loc or loc.rstrip("/") == _BOOKS_INDEX_URL:
            continue
        lastmod_el = url_el.find("sm:lastmod", _SITEMAP_NS)
        image_el = url_el.find("image:image/image:loc", _SITEMAP_NS)
        cover = (image_el.text or "").strip() if image_el is not None else None
        entries.append(
            SitemapEntry(
                url=loc,
                lastmod=_parse_lastmod(lastmod_el.text if lastmod_el is not None else None),
                cover=cover or None,
            )
        )
    return entries


def strip_author_role(name: str) -> str:
    """Strip a trailing role annotation: ``"Jane Doe (Illustrator)"`` -> ``"Jane Doe"``."""
    return _ROLE_SUFFIX_RE.sub("", name).strip()


def parse_book_page(html: str, url: str, sitemap_cover: str | None = None) -> dict[str, Any]:
    """Extract one book's raw metadata from its page HTML.

    Pure (takes the HTML string, does no fetching) so a captured page is a
    fixture — the test that pins this output is what flags a Book Dash redesign.

    Raises :class:`ValueError` if the page has no ``<h1>`` title: a title is the
    one field we cannot sensibly import without, and a page that lost its ``<h1>``
    is the loudest signal the site's shape has changed, so we fail the record (it
    is skipped and the cursor holds) rather than stage a titleless book.
    """
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1")
    if not title_tag:
        raise ValueError(f"Missing <h1> title on {url} (bookdash page shape may have changed)")
    title = title_tag.get_text(strip=True)

    description_tag = soup.find("meta", attrs={"property": "og:description"})
    description = description_tag["content"] if description_tag else ""

    languages = [a["href"].removeprefix("/languages/") for a in soup.find_all("a", href=True) if a["href"].startswith("/languages/")]
    subjects = [a.get_text(strip=True) for a in soup.find_all("a", href=True) if a["href"].startswith("/themes/")]
    authors = [a.get_text(strip=True) for a in soup.find_all("a", href=True) if "/team-members/" in a["href"]]

    isbn_match = ISBN_RE.search(soup.get_text())
    isbn = isbn_match.group(1) if isbn_match else None

    # Cover: the sitemap's <image:loc> is the reliable source; the page's
    # og:image is the fallback for an entry that somehow lacked one. The old
    # <picture> scrape is deliberately gone — bookdash.org stopped emitting it.
    cover = sitemap_cover
    if not cover and (og_image := soup.find("meta", attrs={"property": "og:image"})):
        cover = og_image.get("content") or None

    return {
        "url": url,
        "title": title,
        "cover_url": cover,
        "description": description,
        "languages": languages,
        "subjects": subjects,
        "authors": authors,
        "isbn": isbn,
    }


def to_import_record(scraped: dict[str, Any]) -> dict[str, Any] | None:
    """Map one scraped Book Dash book to an Open Library import record.

    Returns None if the book has no title (nothing importable). The record always
    carries ``identifiers.bookdash`` (the page slug) so a registered Book Dash
    feed validates it on the provider identifier even without an ISBN; a book that
    does have an ISBN additionally carries the strong ``isbn_13``.
    """
    if not scraped.get("title"):
        return None

    slug = scraped["url"].rstrip("/").split("/")[-1]
    if not slug:
        return None

    record: dict[str, Any] = {
        "title": scraped["title"],
        "source_records": [f"{PROVIDER_NAME}:{slug}"],
        "publishers": ["Book Dash"],
        "authors": [{"name": name} for raw in scraped.get("authors", []) if (name := strip_author_role(raw))],
        # Book Dash publishes MARC-style three-letter codes ("eng", "afr",
        # "zul"), already in the shape OL editions want, so they pass through
        # unmapped — unlike OPDS feeds' two-letter ISO codes. Mapping them
        # through get_marc21_language would drop the many African languages that
        # table does not list.
        "languages": list(scraped.get("languages", [])),
        "subjects": list(scraped.get("subjects", [])),
        "description": scraped.get("description", ""),
        # The provider identifier is what the registered-feed validation
        # exemption keys on; it MUST equal the registered provider_name.
        "identifiers": {PROVIDER_NAME: [slug]},
    }

    if isbn := scraped.get("isbn"):
        # Top-level isbn_13 (not under identifiers) so add_book treats it as a
        # strong identifier for matching, matching the OPDS ISBN path.
        record["isbn_13"] = [isbn]

    # Gate the cover on the coverstore allow-list: an un-allowed URL is rejected
    # on upload anyway, and on the match/merge path add_cover retries a rejected
    # URL 10x with sleep(2) — up to 20s wasted per record. bookdash.org is on the
    # allow-list (see ALLOWED_COVER_URLS), so its covers pass.
    if (cover := scraped.get("cover_url")) and is_allowed_cover_url(cover):
        record["cover"] = cover

    return record


class BookdashAdapter:
    """Walk the Book Dash sitemap and scrape each book into an import record.

    A full-crawl adapter: it fetches the whole sitemap every run (Book Dash has
    no ``modified_since``), yielding ``(record, lastmod)`` so the harvester skips
    books at or below the cursor and re-scrapes only what changed.

    Fetches only what it has to. The sitemap is cheap (one request) and carries
    ``lastmod``, so a book already at or below the cursor is skipped WITHOUT
    fetching its page — a steady-state run makes one request total.
    """

    def iter_records(
        self,
        feed: FeedRegistry,
        *,
        since: dt.datetime,
        session: requests.Session,
        max_pages: int | None = None,
        state: dict | None = None,
    ) -> Iterator[tuple[dict[str, Any], dt.datetime | None]]:
        resp = session.get(feed.url or SITEMAP_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        entries = parse_sitemap(resp.content)

        fetched = 0
        for entry in entries:
            # Skip unchanged books cheaply, before fetching the page. (The
            # harvester also filters on modified, but filtering here means a
            # steady-state run never scrapes a page it would only discard.)
            if entry.lastmod is not None and entry.lastmod <= since:
                continue

            if max_pages is not None and fetched >= max_pages:
                # Honoured as a cap on book pages fetched (the sitemap is a
                # single listing, not paginated). Truncating and letting the
                # cursor advance would permanently skip the rest, so flag it.
                if state is not None:
                    state["truncated"] = True
                logger.info("bookdash: stopping at max_pages=%d (cursor would skip the rest)", max_pages)
                return

            try:
                page = session.get(entry.url, timeout=REQUEST_TIMEOUT)
                page.raise_for_status()
                scraped = parse_book_page(page.text, entry.url, sitemap_cover=entry.cover)
                record = to_import_record(scraped)
            except Exception:
                # One malformed/renamed page must not abort the crawl and strand
                # the cursor; skip it (so it is retried next run) and continue.
                logger.exception("bookdash: skipping %s", entry.url)
                continue

            fetched += 1
            if record:
                yield record, entry.lastmod

            if REQUEST_DELAY:
                time.sleep(REQUEST_DELAY)
