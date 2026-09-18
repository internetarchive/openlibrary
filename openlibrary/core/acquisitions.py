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
            " ORDER BY edition_id, provider_name, local_id"
            " LIMIT $limit",
            vars={"edition_ids": edition_ids, "limit": _row_budget(len(edition_ids))},
        )
        grouped: dict[int, list[Acquisition]] = {}
        for row in rows:
            acquisition = Acquisition._from_row(row)
            grouped.setdefault(acquisition.edition_id, []).append(acquisition)
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


def _row_budget(id_count: int) -> int:
    return min(MAX_ROWS_PER_QUERY, max(1, id_count) * MAX_ACQUISITIONS_PER_DOC)


#: ``book_providers`` identifies a provider by ``short_name``; the feed registry
#: identifies one by ``provider_name``, and the two disagree. They cannot simply
#: be renamed to match: a feed's ``provider_name`` is also its ``source_records``
#: prefix and its ``identifiers`` key, and the import validator's feed-source
#: exemption only accepts a record when those agree -- so Gutenberg has to stay
#: ``project_gutenberg`` on our side and ``gutenberg`` on theirs.
#:
#: Without this mapping the two sources look like different providers and an
#: edition ends up with both a harvested acquisition and a synthesized one for
#: the same provider, silently duplicated.
PROVIDER_SHORT_NAMES = {
    "gutenberg": "project_gutenberg",
}

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


def feed_provider_name(short_name: str | None) -> str | None:
    """A ``book_providers`` short name as the feed registry would spell it."""
    return PROVIDER_SHORT_NAMES.get(short_name or "", short_name or None)


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
            if not isinstance(link, dict) or not link.get("href"):
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
    if not rel or not href:
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
