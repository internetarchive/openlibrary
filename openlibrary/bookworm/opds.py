"""OPDS 2.0 parsing for the BookWorm feed-ingestion service (#12844).

Parses OPDS 2.0 publications from a registered provider feed into Open Library
import records (``import.schema.json``) that carry an ``acquisitions`` list.

Built on pydantic models so heterogeneous feeds validate and map uniformly:

- **Better World Books** — ISBN identifier, ``acquisition/buy`` links with a price.
- **Project Gutenberg** — identifier is a ``gutenberg.org/ebooks/<id>`` URL,
  ``acquisition/open-access`` (free) links.
- **Lenny** — no ``metadata.identifier``; the id comes from the ``self`` link,
  ``acquisition/open-access`` links.

Feeds also vary in shape (``author`` may be a dict or a list; ``language`` a str
or a list), which the models normalize. Extends the OPDS types drafted in #12852.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from openlibrary.plugins.upstream.utils import get_marc21_language

BUY_REL = "http://opds-spec.org/acquisition/buy"
OPEN_ACCESS_REL = "http://opds-spec.org/acquisition/open-access"
# rel -> the access value we store on the acquisition
ACQUISITION_ACCESS = {BUY_REL: "buy", OPEN_ACCESS_REL: "open-access"}


def _as_list(value: Any) -> list:
    """OPDS scalars-or-lists (``author``, ``language``) -> a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


class Price(BaseModel):
    currency: str
    value: float


class LinkProperties(BaseModel):
    model_config = ConfigDict(extra="allow")
    price: Price | None = None


class Link(BaseModel):
    model_config = ConfigDict(extra="allow")
    rel: str
    href: str
    type: str | None = None
    title: str | None = None
    length: int | None = None
    properties: LinkProperties | None = None


class Publication(BaseModel):
    """One OPDS 2.0 publication, with normalized accessors."""

    model_config = ConfigDict(extra="allow")
    metadata: dict[str, Any] = {}
    links: list[Link] = []
    images: list[Link] = []

    @property
    def title(self) -> str | None:
        return self.metadata.get("title")

    @property
    def authors(self) -> list[dict[str, str]]:
        out = []
        for author in _as_list(self.metadata.get("author")):
            name = author.get("name") if isinstance(author, dict) else author
            if name:
                out.append({"name": name})
        return out

    @property
    def languages(self) -> list[str]:
        return [lang for lang in _as_list(self.metadata.get("language")) if lang]

    @property
    def modified(self) -> str | None:
        return self.metadata.get("modified")

    def self_href(self) -> str | None:
        for link in self.links:
            if link.rel == "self" and link.href:
                return link.href
        return None

    def cover(self) -> str | None:
        for image in self.images:
            if image.rel == "cover" and image.href:
                return image.href
        return None

    def acquisition_links(self) -> list[Link]:
        return [link for link in self.links if link.rel in ACQUISITION_ACCESS]


class Feed(BaseModel):
    """Per-provider config that specializes the generic OPDS 2.0 parser.

    ``id_strategy`` selects how a publication's stable local id is derived:
    ``isbn`` (from ``urn:isbn:`` in ``metadata.identifier``), ``gutenberg`` (the
    numeric id in the ``gutenberg.org/ebooks/<id>`` identifier URL), or
    ``self_link`` (the last path segment of the ``self`` link — Lenny).
    """

    provider_name: str
    id_strategy: str  # "isbn" | "gutenberg" | "self_link"


ISBN_URN_PREFIX = "urn:isbn:"
_GUTENBERG_ID_RE = re.compile(r"/ebooks/(\d+)")


def extract_local_id(pub: Publication, feed: Feed) -> str | None:
    """The provider-stable id for a publication (identity in the acquisitions table)."""
    identifier = pub.metadata.get("identifier") or ""
    if feed.id_strategy == "isbn":
        return identifier[len(ISBN_URN_PREFIX) :] if identifier.startswith(ISBN_URN_PREFIX) else None
    if feed.id_strategy == "gutenberg":
        match = _GUTENBERG_ID_RE.search(identifier)
        return match.group(1) if match else None
    if feed.id_strategy == "self_link":
        href = pub.self_href() or ""
        # Drop any query/fragment so ".../pub/123?x=y" yields "123", not "123?x=y".
        href = href.split("?", 1)[0].split("#", 1)[0]
        return href.rstrip("/").rsplit("/", 1)[-1] or None
    return None


def build_acquisitions(pub: Publication, feed: Feed, local_id: str) -> list[dict[str, Any]]:
    """Acquisition items for a publication: one per buy/open-access link.

    Each item is an acquisitions-table row minus work/edition ids (the catalog
    supplies those): ``provider_name`` + ``local_id`` + a ``data`` blob. The blob
    stores the raw OPDS acquisition ``link`` as the source of truth (so provider
    data we don't lift out yet — currency, indirect acquisition, ... — isn't
    lost); the flat access/url/format/title/price fields are a denormalized
    convenience copy of values already inside ``link``.
    """
    items = []
    for link in pub.acquisition_links():
        data: dict[str, Any] = {"access": ACQUISITION_ACCESS[link.rel], "url": link.href}
        if link.type:
            data["format"] = link.type
        if link.title:
            data["title"] = link.title
        if link.properties and link.properties.price:
            data["price"] = link.properties.price.model_dump()
        data["link"] = link.model_dump(mode="json", exclude_none=True)
        items.append({"provider_name": feed.provider_name, "local_id": local_id, "data": data})
    return items


def to_import_record(pub: Publication, feed: Feed) -> dict[str, Any] | None:
    """Map an OPDS publication to an OL import record with ``acquisitions[]``.

    Returns None if the publication lacks a title, authors, or a resolvable id.
    Identifier mapping is per-provider: BWB -> ``isbn_13``; Gutenberg ->
    ``identifiers.project_gutenberg``; Lenny -> ``identifiers.lenny``.
    """
    local_id = extract_local_id(pub, feed)
    if not local_id or not pub.title or not pub.authors:
        return None

    # OPDS feeds give ISO codes (e.g. "en"); OL editions need MARC21 ("eng").
    languages = [marc for code in pub.languages if (marc := get_marc21_language(code))]
    record: dict[str, Any] = {
        "title": pub.title,
        "authors": pub.authors,
        "languages": languages,
        "source_records": [f"{feed.provider_name}:{local_id}"],
        "publish_date": pub.metadata.get("published", ""),
    }
    # Invariant: for non-ISBN feeds the ``identifiers`` KEY must equal the
    # registered ``provider_name`` (the ``source_records`` prefix). The import
    # validator's feed-source exemption only accepts the record when the two
    # agree (see import_validator.FeedSourcedBook), so a feed's provider_name and
    # its identifier type are one and the same — e.g. gutenberg must be
    # registered as ``project_gutenberg``.
    if feed.id_strategy == "isbn":
        record["isbn_13"] = [local_id]
    elif feed.id_strategy == "gutenberg":
        record["identifiers"] = {"project_gutenberg": [local_id]}
    elif feed.id_strategy == "self_link":
        record["identifiers"] = {feed.provider_name: [local_id]}
    # A ``cover`` URL is intentionally NOT emitted. OL's server-side cover fetch
    # is gated by two host allowlists (none of these feed hosts satisfy), and on
    # the match/merge path — which feed re-imports hit constantly — add_cover()
    # retries a doomed URL 10x with sleep(2), burning up to 20s per record (see
    # internetarchive/openlibrary#10856 and the covers wiki). Covers for ingested
    # feeds are a separate, later concern. ``Publication.cover()`` stays available
    # for that future path. #12844
    if acquisitions := build_acquisitions(pub, feed, local_id):
        record["acquisitions"] = acquisitions
    return record
