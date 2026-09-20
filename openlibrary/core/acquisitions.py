"""Interface to the Trusted Book Providers (TBP) ``acquisitions`` table.

An acquisition maps a (work, edition, provider) to a JSON blob of provider
metadata (prices, formats, urls, ...). One row exists per edition per
provider. The ingestion cron upserts rows; Solr later reflects them.

Work merges are handled via :meth:`update_work_id` (inherited from
``CommonExtras``), so the table stays robust against ``resolve_redirects``.

See https://github.com/internetarchive/openlibrary/issues/12844 and
https://github.com/internetarchive/openlibrary/pull/12793.
"""

from __future__ import annotations

import datetime
import functools
import json
import logging
from typing import TYPE_CHECKING, Any

import web

from . import db
from .db import CommonExtras

logger = logging.getLogger("openlibrary.acquisitions")

if TYPE_CHECKING:
    from web.db import ResultSet


def _utcnow() -> datetime.datetime:
    """Timezone-naive UTC now, matching the table's ``timestamp`` columns."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class Acquisition(web.storage, CommonExtras):
    """A single row of the ``acquisitions`` table."""

    id: int
    work_id: int
    edition_id: int
    provider_name: str
    local_id: str
    data: dict
    created: datetime.datetime
    updated: datetime.datetime

    # Configuration for CommonExtras mixin:
    TABLENAME = "acquisitions"
    # These aren't actually used for acquisitions since work/edition IDs are not
    # part of a unique constraint, so work/edition merges will never cause a conflict
    # in this table.
    PRIMARY_KEY = ("local_id", "provider_name")
    ALLOW_DELETE_ON_CONFLICT = False

    @staticmethod
    def _from_row(row: web.storage) -> Acquisition:
        acquisition = Acquisition(row)
        # jsonb comes back as a dict from Postgres but as a string from SQLite.
        if isinstance(data := acquisition.get("data"), str):
            acquisition.data = json.loads(data)
        return acquisition

    @staticmethod
    def get_by_edition(edition_id: int, provider_name: str | None = None) -> list[Acquisition]:
        if provider_name is None:
            rows: ResultSet = db.query(
                "SELECT * FROM acquisitions WHERE edition_id=$edition_id ORDER BY provider_name",
                vars={"edition_id": edition_id},
            )
        else:
            rows = db.query(
                "SELECT * FROM acquisitions WHERE edition_id=$edition_id AND provider_name=$provider_name",
                vars={"edition_id": edition_id, "provider_name": provider_name},
            )
        return [Acquisition._from_row(row) for row in rows]

    @staticmethod
    def find_many(provider_name: str, local_ids: list[str]) -> dict[str, Acquisition]:
        """Acquisitions for a provider, keyed by ``local_id``.

        The durable record of what was last stored for a feed's publication.
        ``import_item.data`` is cleared once a row completes
        (:meth:`ImportItem.set_status`), so this is the only thing left to
        compare a re-offered record against -- which is how a harvest tells a
        genuine price change from a provider re-publishing an unchanged record.
        """
        if not local_ids:
            return {}
        rows: ResultSet = db.query(
            "SELECT * FROM acquisitions WHERE provider_name=$provider_name AND local_id IN $local_ids",
            vars={"provider_name": provider_name, "local_ids": local_ids},
        )
        return {row.local_id: Acquisition._from_row(row) for row in rows}

    @staticmethod
    def get_by_editions(edition_ids: list[int]) -> dict[int, list[Acquisition]]:
        """Batch-fetch acquisitions for many editions, grouped by ``edition_id``.

        Used to weave acquisitions into a page of search results without N+1
        queries.
        """
        if not edition_ids:
            # `IN ()` is a syntax error on Postgres. SQLite accepts it, so a
            # test suite running on SQLite cannot catch a missing guard here.
            return {}
        rows: ResultSet = db.query(
            "SELECT * FROM acquisitions WHERE edition_id IN $edition_ids"
            # local_id breaks the tie: (edition_id, provider_name) is NOT
            # unique -- the table's UNIQUE is (local_id, provider_name) -- so
            # one provider can hold two rows for one edition (an ISBN-10 and an
            # ISBN-13, say) and without this their order is arbitrary.
            " ORDER BY edition_id, provider_name, local_id",
            vars={"edition_ids": edition_ids},
        )
        # Capped per edition, not globally. A single `LIMIT` over the whole
        # page truncates after ORDER BY, so with enough rows the editions
        # sorted last -- the highest ids, meaning the newest -- silently get
        # nothing at all while the first ones get everything. Callers cannot
        # see the difference between "no acquisitions" and "budget exhausted".
        grouped: dict[int, list[Acquisition]] = {}
        for row in rows:
            acquisition = Acquisition._from_row(row)
            bucket = grouped.setdefault(acquisition.edition_id, [])
            if len(bucket) < MAX_ACQUISITIONS_PER_DOC:
                bucket.append(acquisition)
        return grouped

    @staticmethod
    def get_by_work(work_id: int) -> list[Acquisition]:
        rows: ResultSet = db.query(
            "SELECT * FROM acquisitions WHERE work_id=$work_id ORDER BY edition_id, provider_name",
            vars={"work_id": work_id},
        )
        return [Acquisition._from_row(row) for row in rows]

    @staticmethod
    def upsert(
        work_id: int,
        edition_id: int,
        provider_name: str,
        local_id: str,
        data: dict | None = None,
    ) -> Acquisition | None:
        """Insert or update the acquisition for ``(local_id, provider_name)``.

        Keyed on the ``(local_id, provider_name)`` unique constraint; an
        existing row has its ``work_id``/``edition_id``/``data`` refreshed.
        """
        # Need a transaction for the RETURNING * clause
        with db.transaction():
            result = list(
                db.query(
                    """
                    INSERT INTO acquisitions (work_id, edition_id, provider_name, local_id, data)
                    VALUES ($work_id, $edition_id, $provider_name, $local_id, $data)
                    ON CONFLICT (local_id, provider_name) DO UPDATE SET
                        work_id = EXCLUDED.work_id,
                        edition_id = EXCLUDED.edition_id,
                        data = EXCLUDED.data,
                        updated = $updated
                    RETURNING *
                    """,
                    vars={
                        "work_id": work_id,
                        "edition_id": edition_id,
                        "provider_name": provider_name,
                        "local_id": local_id,
                        "data": json.dumps(data or {}),
                        "updated": _utcnow(),
                    },
                )
            )
        return Acquisition._from_row(result[0]) if result else None


_MAX_DB_INT = 2**31 - 1
"""Largest value the ``integer`` columns can hold."""

MAX_ACQUISITIONS_PER_DOC = 24
"""Cap on OPDS2 links returned for one edition.

Bounds a `/search.json` response: `limit` has no upper bound (unlike list
search, which clamps to 1000), so neither the id list nor the row count can be
assumed small.
"""

MAX_ROWS_PER_QUERY = 2000
"""Absolute ceiling on rows fetched for one page, whatever its size."""

MAX_EDITIONS_PER_QUERY = 200
"""Ceiling on how many editions one page may look up, independent of page size.

`/search.json`'s `limit` has no upper bound -- `Pagination.limit` is declared
`ge=0` with no `le=` (openlibrary/fastapi/models.py), and a request for
`limit=1200` really does return 1200 documents, verified against a live
deployment. That is a pre-existing hole, but hanging a Postgres query off it
turns page size into an attacker-chosen `IN` list on the one connection every
coroutine in the worker shares -- so an unauthenticated request could make an
arbitrarily large query and block every other database user behind it.

Bounding the input here is much cheaper than moving off the shared
connection, and it is what makes keeping this on the event loop defensible:
the work per request is now capped by a constant rather than by the caller.

Twice the default page size, so it is invisible to real use and a hard stop
for abuse. Editions past it simply do not get the field."""


def _row_budget(id_count: int) -> int:
    return min(MAX_ROWS_PER_QUERY, max(1, id_count) * MAX_ACQUISITIONS_PER_DOC)


#: OPDS2 `rel` for each of ``book_providers``'s access literals, so a
#: synthesized acquisition is the same shape as a harvested one.
OPDS_REL_FOR_ACCESS = {
    "buy": "http://opds-spec.org/acquisition/buy",
    "open-access": "http://opds-spec.org/acquisition/open-access",
    "borrow": "http://opds-spec.org/acquisition/borrow",
    "sample": "http://opds-spec.org/acquisition/sample",
    "subscribe": "http://opds-spec.org/acquisition/subscribe",
}

#: Media type for each of ``book_providers``'s coarse format names.
OPDS_TYPE_FOR_FORMAT = {
    "web": "text/html",
    "pdf": "application/pdf",
    "epub": "application/epub+zip",
    "audio": "audio/*",
}


SAFE_URL_SCHEMES = ("http://", "https://")
"""`data` is authored by an external feed and this field serves it through a
public API, so an href is attacker-controlled input we republish under our own
name -- and a consumer renders it as an anchor. Checked on the way out as well
as in, because rows harvested before this existed are already in the table."""


def _is_safe_url(href: object) -> bool:
    return isinstance(href, str) and href.lower().startswith(SAFE_URL_SCHEMES)


def _squash(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


@functools.cache
def _provider_name_lookup() -> dict[str, str]:
    """Every spelling a provider answers to, mapped to its canonical name.

    Built from the registry, not by hand: ``provider_name`` already returns
    ``identifier_key or short_name``, and ``identifier_key`` is the
    ``identifiers.*`` key -- which is what a feed's provider_name must equal
    for the import validator to accept its records.
    """
    from openlibrary.book_providers import PROVIDER_ORDER

    lookup: dict[str, str] = {}
    for provider in PROVIDER_ORDER:
        canonical = provider.provider_name
        for spelling in (provider.short_name, provider.provider_name):
            if spelling:
                lookup[_squash(spelling)] = canonical
    return lookup


def feed_provider_name(name: str | None) -> str | None:
    """A provider's name as the feed registry spells it, for display.

    Unknown names pass through unchanged, because a feed-only provider
    (``lenny``) has no ``book_providers`` entry and its own spelling is the
    right one to publish.
    """
    if not isinstance(name, str) or not name:
        return None
    return _provider_name_lookup().get(_squash(name), name)


def provider_dedupe_key(name: object) -> str | None:
    """What both sides of the dedupe compare on.

    Deliberately not :func:`feed_provider_name`. That resolves a name for
    *display* and leaves an unknown one alone -- which makes it a no-op for
    exactly the providers that have harvested rows today, so ``"Lenny"`` and
    ``"lenny"`` compared unequal and the edition showed the same acquisition
    twice. Comparison falls back to the squashed form, so spelling differences
    that do not change which provider is meant cannot produce a duplicate.
    """
    if not isinstance(name, str) or not name:
        return None
    squashed = _squash(name)
    return _provider_name_lookup().get(squashed, squashed)


def opds_links_for_edition(rows: list[Acquisition]) -> list[dict]:
    """The stored OPDS2 acquisition links for one edition.

    Each row's ``data`` blob keeps the provider's raw OPDS2 ``link`` as the
    source of truth, so this returns those directly rather than rebuilding
    them -- they are already the format the field promises. ``provider_name``
    is injected so a consumer can tell the links apart, and is applied after
    the blob so a provider feed cannot relabel itself.

    A row whose blob is unusable is skipped rather than raising: ``data`` is
    jsonb written from an external feed, its top level can be any JSON type,
    and one bad row must not cost the whole page its acquisitions.
    """
    links: list[dict] = []
    for row in rows:
        data = row.data if isinstance(row.data, dict) else {}
        entries = data.get("acquisitions")
        if not isinstance(entries, list):
            logger.warning("acquisitions row %s/%s has an unusable data blob; skipping it", row.provider_name, row.local_id)
            continue
        for acquisition in entries:
            if not isinstance(acquisition, dict):
                continue
            link = acquisition.get("link")
            if not isinstance(link, dict):
                continue
            if not _is_safe_url(link.get("href")):
                logger.warning(
                    "dropping acquisition from %s/%s: unsafe or missing href",
                    row.provider_name,
                    row.local_id,
                )
                continue
            links.append({**link, "provider_name": row.provider_name})
            if len(links) >= MAX_ACQUISITIONS_PER_DOC:
                logger.info("truncating acquisitions for edition %s at %d links", row.edition_id, MAX_ACQUISITIONS_PER_DOC)
                return links
    return links


def provider_acquisition_as_opds(acquisition: Any) -> dict | None:
    """A ``book_providers.Acquisition`` coerced into an OPDS2 acquisition link.

    So a caller reads one field in one format rather than reconciling
    ``providers`` against ``opds_acquisitions`` itself. Returns None when the
    access kind has no OPDS2 equivalent, rather than inventing a ``rel``.
    """
    rel = OPDS_REL_FOR_ACCESS.get(getattr(acquisition, "access", "") or "")
    href = getattr(acquisition, "url", None)
    if not rel or not _is_safe_url(href):
        return None
    link: dict[str, Any] = {"rel": rel, "href": href, "provider_name": feed_provider_name(getattr(acquisition, "provider_name", None))}
    if media_type := OPDS_TYPE_FOR_FORMAT.get(getattr(acquisition, "format", "") or ""):
        link["type"] = media_type
    # `providers` carries price as an opaque string ("$4.99"); OPDS2 wants a
    # currency and a number. Passed through under a distinct key rather than
    # guessed at, so nothing downstream reads a fabricated amount.
    if price := getattr(acquisition, "price", None):
        link["properties"] = {"price_display": price}
    return link
