"""Generic Open Library adapter for OPDS 2.0 feeds.

Parses an OPDS 2.0 JSON feed (publications with metadata + acquisition links)
into Open Library import records and provider acquisition metadata. One adapter
serves ANY OPDS 2.0 feed registered in the Trusted Book Provider feed registry;
per-source quirks (import source-id prefix, quality filters) are supplied via a
small :class:`Source` config rather than a bespoke per-feed script.

This is the OPDS **2.0 / JSON** path. ``openlibrary/plugins/importapi/import_opds.py``
is the separate OPDS **1.x / Atom-XML** parser used by the import API.

See https://github.com/internetarchive/openlibrary/issues/12844.
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import requests

from openlibrary.plugins.upstream.utils import get_marc21_language
from openlibrary.utils.isbn import to_isbn_13

logger = logging.getLogger("openlibrary.catalog.opds2")

ACQUISITION_REL = "http://opds-spec.org/acquisition/buy"
ISBN_URN_PREFIX = "urn:isbn:"
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)
REQUEST_TIMEOUT = 60
PAGE_SLEEP_SECONDS = 1.0


@dataclass(frozen=True)
class Source:
    """Per-feed configuration that specializes the generic OPDS 2.0 adapter.

    :param provider_name: acquisitions/registry provider key (e.g. ``"betterworldbooks"``).
    :param source_id_prefix: import ``source_records`` slug prefix — ``"bwb"`` yields
        ``"bwb:{isbn_13}"``, reusing the source's existing import identity.
    :param record_filter: optional predicate returning ``True`` to EXCLUDE a mapped
        record (e.g. partner quality filters). ``None`` keeps everything.
    """

    provider_name: str
    source_id_prefix: str
    record_filter: Callable[[dict[str, Any]], bool] | None = None


def parse_iso(value: str) -> datetime.datetime:
    """Parse an ISO 8601 timestamp, normalising to a tz-aware UTC datetime.

    Feeds emit high-precision offsets like ``2026-05-19T14:47:58.5476301-04:00``
    which ``datetime.fromisoformat`` accepts on Python 3.11+.
    """
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(datetime.UTC)


def extract_isbn(metadata: dict[str, Any]) -> str | None:
    """Return the ISBN-13 from an OPDS ``metadata.identifier`` URN, or None."""
    identifier = metadata.get("identifier") or ""
    if not identifier.startswith(ISBN_URN_PREFIX):
        return None
    return to_isbn_13(identifier[len(ISBN_URN_PREFIX) :])


def extract_price(publication: dict[str, Any]) -> dict[str, Any] | None:
    """Return ``{currency, value}`` from the first buy-acquisition link, or None."""
    for link in publication.get("links", []) or []:
        if link.get("rel") != ACQUISITION_REL:
            continue
        properties = link.get("properties") or {}
        price = properties.get("price") or {}
        if price.get("value") is not None and price.get("currency"):
            return {"currency": price["currency"], "value": price["value"]}
    return None


def build_acquisition_data(publication: dict[str, Any]) -> dict[str, Any]:
    """Extract provider acquisition metadata (price, buy url, formats).

    Stored verbatim in the ``acquisitions.data`` blob for a resolved edition so
    downstream indexing can search by price/format (issues #12844, #11264).
    """
    data: dict[str, Any] = {}
    if price := extract_price(publication):
        data["price"] = price
    for link in publication.get("links", []) or []:
        if link.get("rel") != ACQUISITION_REL:
            continue
        if href := link.get("href"):
            data["url"] = href
        properties = link.get("properties") or {}
        formats = [fmt["type"] for fmt in (properties.get("indirectAcquisition") or []) if fmt.get("type")]
        if formats:
            data["formats"] = formats
        break
    return data


def extract_cover(publication: dict[str, Any]) -> str | None:
    for image in publication.get("images", []) or []:
        if image.get("rel") == "cover" and image.get("href"):
            return image["href"]
    return None


def publication_id(publication: dict[str, Any]) -> str:
    """Return the publication's ``self`` link or raw identifier, for logging."""
    for link in publication.get("links", []) or []:
        if link.get("rel") == "self" and link.get("href"):
            return link["href"]
    return (publication.get("metadata") or {}).get("identifier") or "<unknown>"


def map_publication_to_olbook(publication: dict[str, Any], source: Source) -> dict[str, Any] | None:
    """Convert an OPDS publication to an OL import record for ``source``.

    Returns None when the publication lacks ISBN-13, title, or authors — the
    import API requires all three. ``source_records`` uses the source's slug
    prefix (e.g. ``bwb:{isbn}``) so records reuse the source's import identity.
    """
    metadata = publication.get("metadata") or {}
    isbn_13 = extract_isbn(metadata)
    if not isbn_13:
        logger.warning("Skipping publication with no usable ISBN: %s", publication_id(publication))
        return None

    title = metadata.get("title")
    authors = [{"name": a["name"]} for a in (metadata.get("author") or []) if a.get("name")]
    if not title or not authors:
        logger.warning("Skipping publication missing title/authors: %s", publication_id(publication))
        return None

    languages = [marc for code in (metadata.get("language") or []) if code and (marc := get_marc21_language(code))]

    olbook: dict[str, Any] = {
        "title": title,
        "isbn_13": [isbn_13],
        "source_records": [f"{source.source_id_prefix}:{isbn_13}"],
        "authors": authors,
        "languages": languages,
        "publish_date": metadata.get("published", ""),
        "publishers": [],  # OPDS feed does not include publisher
    }
    if cover := extract_cover(publication):
        olbook["cover"] = cover
    return olbook


def excluded(olbook: dict[str, Any], source: Source) -> bool:
    """Apply the source's quality filter (if any); True means drop the record."""
    if not source.record_filter or not olbook.get("title"):
        return False
    try:
        return bool(source.record_filter(olbook))
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("record_filter failed for %s: %s", olbook.get("isbn_13"), e)
        return False


def find_next_url(feed: dict[str, Any]) -> str | None:
    for link in feed.get("links", []) or []:
        if link.get("rel") == "next" and link.get("href"):
            return link["href"]
    return None


def iter_pages(start_url: str, session: requests.Session, max_pages: int | None = None) -> Iterator[dict[str, Any]]:
    """Yield successive OPDS feed pages, following ``rel=next`` links."""
    url: str | None = start_url
    seen: set[str] = set()
    page_num = 0
    while url:
        if url in seen:
            logger.warning("Cycle detected in OPDS pagination at %s; stopping.", url)
            return
        seen.add(url)
        page_num += 1
        if max_pages is not None and page_num > max_pages:
            logger.info("Reached max_pages=%s; stopping pagination.", max_pages)
            return
        logger.info("Fetching OPDS page %d: %s", page_num, url)
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"Accept": "application/opds+json"})
        resp.raise_for_status()
        feed = resp.json()
        yield feed
        url = find_next_url(feed)
        if url and PAGE_SLEEP_SECONDS:
            time.sleep(PAGE_SLEEP_SECONDS)


def process_feed(
    feed_url: str,
    since: datetime.datetime,
    prices_out_fh,
    source: Source,
    max_pages: int | None = None,
    early_stop: bool = False,
    acquisitions_out: list[tuple[str, dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], datetime.datetime]:
    """Crawl the OPDS feed and return ``(olbooks, max_modified_seen)``.

    Records are filtered to those with ``metadata.modified > since``. Price rows
    are written to ``prices_out_fh``; acquisition ``(isbn_13, data)`` pairs are
    appended to ``acquisitions_out`` when provided. The cursor advances on every
    publication newer than ``since`` even when mapping fails, so an unmappable
    but newer record never forces every future run to re-scan it.

    ``source.record_filter`` drops low-quality/out-of-scope records the same way
    the source's legacy importer does.

    ``early_stop`` (off by default): halt pagination once a whole page contains
    nothing newer than ``since``. OPDS does not mandate sort-by-modified, so
    leave off until a feed's ordering is confirmed, else an out-of-order stale
    page would skip fresh records on later pages.
    """
    session = requests.Session()
    olbooks: list[dict[str, Any]] = []
    max_modified = since

    for feed in iter_pages(feed_url, session, max_pages=max_pages):
        fresh_in_page = 0
        for publication in feed.get("publications", []) or []:
            metadata = publication.get("metadata") or {}
            modified_raw = metadata.get("modified")
            if not modified_raw:
                continue
            try:
                modified = parse_iso(modified_raw)
            except ValueError:
                logger.warning("Skipping publication with unparsable modified=%r", modified_raw)
                continue
            if modified <= since:
                continue
            fresh_in_page += 1
            max_modified = max(max_modified, modified)

            olbook = map_publication_to_olbook(publication, source)
            if not olbook:
                continue
            if excluded(olbook, source):
                continue
            olbooks.append(olbook)

            if acquisitions_out is not None and (acq_data := build_acquisition_data(publication)):
                acquisitions_out.append((olbook["isbn_13"][0], acq_data))

            if price := extract_price(publication):
                prices_out_fh.write(json.dumps({"isbn_13": olbook["isbn_13"][0], "price": price["value"], "currency": price["currency"]}) + "\n")

        if early_stop and fresh_in_page == 0:
            logger.info("Page contains no records newer than %s; stopping (feed is modified-desc).", since.isoformat())
            break

    return olbooks, max_modified
