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
from typing import TYPE_CHECKING

import web

from openlibrary.utils import extract_numeric_id_from_olid

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
    def get_by_works(work_ids: list[int]) -> dict[int, list[Acquisition]]:
        """Batch-fetch acquisitions for many works, grouped by ``work_id``.

        The work-level counterpart of :meth:`get_by_editions`. A search for a
        title returns *works*, so this is what lets a result say "buy from
        $1.01" without the caller having to ask for edition sub-documents.
        """
        if not work_ids:
            return {}
        rows: ResultSet = db.query(
            "SELECT * FROM acquisitions WHERE work_id IN $work_ids ORDER BY work_id, edition_id, provider_name, local_id LIMIT $limit",
            vars={"work_ids": work_ids, "limit": _row_budget(len(work_ids))},
        )
        grouped: dict[int, list[Acquisition]] = {}
        for row in rows:
            acquisition = Acquisition._from_row(row)
            grouped.setdefault(acquisition.work_id, []).append(acquisition)
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
"""Cap on entries attached to one search doc.

The work branch is unbounded by nature: a work can have thousands of editions,
each with several links. One work with 300 priced editions and two links apiece
renders 600 entries and ~70KB on a single document, and a page of those is a
multi-megabyte response from two cheap queries -- and `/search.json`'s `limit`
has no upper bound, unlike list search which clamps to 1000. Truncating is the
lesser evil; a client that needs every price for a work should ask for that
work's editions.
"""

MAX_ROWS_PER_QUERY = 2000
"""Absolute ceiling on rows fetched for one page, whatever its size."""


def _row_budget(id_count: int) -> int:
    return min(MAX_ROWS_PER_QUERY, max(1, id_count) * MAX_ACQUISITIONS_PER_DOC)


def add_acquisitions(docs: list[dict]) -> None:
    """Attach provider acquisitions to a page of search-result docs (#12844).

    Handles both shapes a search can return, because they are not
    interchangeable and the naive query returns the first one:

    - a **work** doc (``/works/OL...W``) -- what ``/search.json`` returns unless
      the caller asks for edition sub-documents. Matched on ``work_id``, so the
      result spans every edition of the work and each entry names the edition it
      belongs to. A search for a title has to be able to say "buy from $1.01"
      without the client knowing to request editions first; an earlier version
      of this only handled edition docs and so silently attached nothing to the
      obvious query.
    - an **edition** doc (``/books/OL...M``) -- what appears under
      ``editions.docs`` when they are requested. Matched on ``edition_id``.

    Each entry carries ``provider_name``, ``local_id`` and ``edition_key``::

        [{"provider_name": "betterworldbooks", "local_id": "978...",
          "edition_key": "/books/OL61605616M",
          "access": "buy", "price": {"currency": "USD", "value": 1.01}, ...},
         {"provider_name": "lenny", "local_id": "51008637",
          "edition_key": "/books/OL51008637M",
          "access": "open-access", "format": "text/html", ...}]

    Two queries at most per page, both on indexed columns. Read at query time
    rather than indexed into Solr because prices change far more often than
    bibliographic data, and re-indexing an edition per price change is not
    viable. #12844
    """
    works: dict[int, dict] = {}
    editions: dict[int, dict] = {}
    for doc in docs:
        key = doc.get("key") or ""
        target = editions if key.startswith("/books/OL") else works if key.startswith("/works/OL") else None
        if target is None:
            continue
        try:
            numeric_id = int(extract_numeric_id_from_olid(key))
        except ValueError, TypeError, IndexError:
            # IndexError: extract_numeric_id_from_olid indexes olid[-1], so a
            # bare "/books/OL" raises rather than returning nothing.
            continue
        if not 0 < numeric_id <= _MAX_DB_INT:
            # Python ints are arbitrary precision, so "/books/OL<80 digits>M"
            # parses happily and only fails once it reaches the database -- as
            # an OverflowError from the driver, inside the caller's page-wide
            # guard, costing every document on the page its prices. Rejected
            # here instead, where it costs only this key.
            continue
        target[numeric_id] = doc

    for by_id, fetch in ((editions, Acquisition.get_by_editions), (works, Acquisition.get_by_works)):
        if not by_id:
            continue
        for id_, rows in fetch(list(by_id)).items():
            if flattened := _flatten(rows):
                by_id[id_]["acquisitions"] = flattened


def _flatten(rows: list[Acquisition]) -> list[dict]:
    """One flat list of acquisitions for a doc, from its rows.

    Flattened across providers because a consumer wants a single list it can
    filter by access or price -- an edition can carry a Better World Books
    price and a Gutenberg epub at once -- with each entry labelled by the
    provider it came from and the edition it applies to.

    Two things this defends against, because ``data`` is a blob written from an
    external provider feed rather than by us:

    - **A provider does not get to relabel itself.** The injected keys are
      applied AFTER the blob is spread, so a feed cannot assert a
      ``provider_name``, ``local_id`` or ``edition_key`` that contradicts its
      own row. ``edition_key`` exists precisely to tell a client which edition
      a price belongs to, so letting a feed choose it would be worse than
      omitting it.
    - **One malformed row must not blank the page.** ``data`` is jsonb, so its
      top level can be a list, a string or a number, and ``.get`` on those
      raises. The caller's guard is page-wide, so an unhandled row here would
      cost every document its prices; skipping the row costs only that row.
    """
    flattened: list[dict] = []
    for row in rows:
        data = row.data if isinstance(row.data, dict) else {}
        entries = data.get("acquisitions")
        if not isinstance(entries, list):
            logger.warning(
                "acquisitions row %s/%s has an unusable data blob; skipping it",
                row.provider_name,
                row.local_id,
            )
            continue
        for acquisition in entries:
            if not isinstance(acquisition, dict):
                continue
            flattened.append(
                {
                    **acquisition,
                    "provider_name": row.provider_name,
                    "local_id": row.local_id,
                    "edition_key": f"/books/OL{row.edition_id}M",
                }
            )
            if len(flattened) >= MAX_ACQUISITIONS_PER_DOC:
                logger.info("truncating acquisitions for edition %s at %d entries", row.edition_id, MAX_ACQUISITIONS_PER_DOC)
                return flattened
    return flattened
