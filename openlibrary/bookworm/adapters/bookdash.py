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

import requests
from bs4 import BeautifulSoup

from openlibrary.coverstore.utils import is_allowed_cover_url

if TYPE_CHECKING:
    from collections.abc import Iterator

    from openlibrary.bookworm.registry import FeedRegistry

logger = logging.getLogger("openlibrary.bookworm.adapters.bookdash")

PROVIDER_NAME = "bookdash"
SITEMAP_URL = "https://bookdash.org/books-sitemap.xml"

# A fetch that is NOT worth retrying: the page is gone, so skipping it (rather than
# holding the whole feed's cursor) is correct. Anything else is treated as
# transient — see BookdashFetchError.
GONE_STATUSES = (404, 410)


class BookdashFetchError(Exception):
    """A book page failed to fetch for a non-permanent reason.

    Raised at the end of a crawl so the harvester reports the feed as failed and,
    critically, does NOT advance the cursor — the next run then retries the whole
    window. This mirrors how the OPDS path treats a bad page fetch
    (:class:`~openlibrary.bookworm.harvest.SuspectFeedPage` / a raised
    ``raise_for_status``): a transient blip must hold the cursor, never silently
    skip a record. A genuinely-removed page (``GONE_STATUSES``) is skipped instead,
    so one deleted book cannot wedge the feed forever.
    """


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
    # .get, not [...]: a meta tag present but missing its content attribute would
    # otherwise raise and (via iter_records' guard) drop the whole book over an
    # optional field.
    description = (description_tag.get("content") or "") if description_tag else ""

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

    Returns None for a record that cannot be imported — no title, no slug, or **no
    authors**. The author guard matters: ``FeedSourcedBook`` (and the OPDS path's
    ``to_import_record``) both require at least one author, so an authorless record
    would stage as a "success" and then fail validation at import time, silently.
    If the ``/team-members/`` selector drifts the way the cover selector already
    did, every record goes authorless at once — returning None makes that show up
    as the record count collapsing on the next harvest, instead of a queue full of
    records that never import.

    The record always carries ``identifiers.bookdash`` (the page slug) so a
    registered Book Dash feed validates it on the provider identifier even without
    an ISBN; a book that has one additionally carries the strong ISBN.
    """
    if not scraped.get("title"):
        return None

    slug = scraped["url"].rstrip("/").split("/")[-1]
    if not slug:
        return None

    authors = [{"name": name} for raw in scraped.get("authors", []) if (name := strip_author_role(raw))]
    if not authors:
        logger.warning("bookdash: %s has no authors; skipping (would fail import validation)", scraped["url"])
        return None

    record: dict[str, Any] = {
        "title": scraped["title"],
        "source_records": [f"{PROVIDER_NAME}:{slug}"],
        "publishers": ["Book Dash"],
        "authors": authors,
        # Strip the region suffix from language codes. Book Dash codes are mostly
        # clean three-letter MARC21 ("eng", "xho", "tso", "nso") but some are
        # region-qualified ("sot-ls" = Sesotho/Lesotho), and format_languages()
        # RAISES on a code it can't resolve, failing the whole book. OL language
        # keys are always exactly three letters (`^/languages/[a-z]{3}$`), so the
        # base segment is the right code to hand it. We deliberately do NOT route
        # through get_marc21_language here: its map collapses distinct languages
        # (tso -> sot, nso -> sot), which would silently mislabel Tsonga and Sepedi
        # books as Sesotho. format_languages (OL's own language table) is the
        # authority and validates these at import time.
        "languages": [base for raw in scraped.get("languages", []) if (base := raw.split("-")[0].strip())],
        "subjects": list(scraped.get("subjects", [])),
        "description": scraped.get("description", ""),
        # The provider identifier is what the registered-feed validation
        # exemption keys on; it MUST equal the registered provider_name.
        "identifiers": {PROVIDER_NAME: [slug]},
    }

    if isbn := scraped.get("isbn"):
        # Top-level (not under identifiers) so add_book treats it as a strong
        # identifier for matching, matching the OPDS ISBN path. Route by digit
        # count so an ISBN-10 is not mis-filed as an ISBN-13.
        digits = isbn.replace("-", "").replace(" ", "")
        if len(digits) == 13:
            record["isbn_13"] = [isbn]
        elif len(digits) == 10:
            record["isbn_10"] = [isbn]
        else:
            logger.warning("bookdash: %s has an unrecognised ISBN %r; dropping it", scraped["url"], isbn)

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

    Failure handling mirrors the OPDS path, because the cursor is a single
    watermark (not per-record):

    - **Transient fetch failure** (network error, or a non-gone HTTP status after
      the session's retries): counted, and :class:`BookdashFetchError` is raised at
      the end of the crawl, so the harvester reports the feed failed and holds the
      cursor. The next run then retries the whole window. Swallowing it instead
      would let a *newer* book advance the cursor past the failed one, which is
      then never revisited — silent, permanent loss.
    - **Gone** (HTTP 404/410): skipped, no raise — a deleted book must not wedge
      the feed forever.
    - **Unparsable page** (shape drift): logged and skipped, like the OPDS path
      skips a malformed publication. Deterministic, so raising would wedge the
      feed; a widespread drift surfaces as the run's record count collapsing.
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
        transient_failures = 0
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
                break

            try:
                page = session.get(entry.url, timeout=REQUEST_TIMEOUT)
                page.raise_for_status()
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                if status in GONE_STATUSES:
                    logger.warning("bookdash: %s is gone (HTTP %s); skipping", entry.url, status)
                    continue
                logger.warning("bookdash: transient HTTP %s fetching %s; will retry next run", status, entry.url)
                transient_failures += 1
                continue
            except requests.RequestException:
                logger.warning("bookdash: network error fetching %s; will retry next run", entry.url)
                transient_failures += 1
                continue

            try:
                scraped = parse_book_page(page.text, entry.url, sitemap_cover=entry.cover)
                record = to_import_record(scraped)
            except Exception:
                # A deterministic parse failure (shape drift) would re-fail every
                # run, so raising would wedge the feed; skip it and keep going,
                # exactly as the OPDS path skips a malformed publication. Not
                # flagged as `truncated` -- that flag means "stopped early, cursor
                # advanced past unfetched records", whose "reset last_updated"
                # remediation does not fit a page that was fetched and could not be
                # parsed. A widespread drift instead shows up as the run's record
                # count collapsing (and here, in the logs).
                logger.exception("bookdash: could not parse %s; skipping this run", entry.url)
                continue

            fetched += 1
            if record:
                yield record, entry.lastmod

            if REQUEST_DELAY:
                time.sleep(REQUEST_DELAY)

        if transient_failures:
            raise BookdashFetchError(f"{transient_failures} Book Dash page(s) failed to fetch; holding the cursor so the next run retries them")
