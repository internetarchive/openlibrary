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
            try:
                acquisition.data = json.loads(data)
            except ValueError:
                # A jsonb value whose TOP LEVEL is a JSON string arrives from
                # Postgres already decoded, so re-parsing it raises and, from
                # `get_by_editions`, costs the whole page its acquisitions --
                # the opposite of the documented "one bad row" behaviour.
                # Leave the value as it is: the reader requires a dict and
                # skips the row with a warning. Unreachable on SQLite, where
                # every blob is a string and this parse always succeeds.
                logger.warning("acquisitions row %s/%s has an unparsable data blob; leaving it", acquisition.get("provider_name"), acquisition.get("local_id"))
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
        dropped: dict[int, int] = {}
        for row in rows:
            acquisition = Acquisition._from_row(row)
            bucket = grouped.setdefault(acquisition.edition_id, [])
            # A row whose `acquisitions` array is empty publishes nothing, so
            # spending budget on it is how the starvation worked: raising the
            # cap moved the threshold without changing the shape. Rows that
            # cannot contribute a link do not consume the allowance.
            if not _row_can_publish(acquisition):
                continue
            if len(bucket) < MAX_ROWS_PER_EDITION:
                bucket.append(acquisition)
            else:
                # Logged, because the caller cannot see it. A short list that
                # looks complete is the failure mode this whole field keeps
                # running into; at least leave a trace on our side.
                dropped[acquisition.edition_id] = dropped.get(acquisition.edition_id, 0) + 1
        for edition_id, count in dropped.items():
            logger.info("edition %s has more than %d acquisition rows; dropped %d", edition_id, MAX_ROWS_PER_EDITION, count)
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


MAX_DB_INT = 2**31 - 1
"""Largest value the ``integer`` columns can hold.

A key like ``/books/OL<80 digits>M`` parses fine -- Python ints are arbitrary
precision -- so it reaches the query as an id no row can match. Measured
against this Postgres, it does NOT raise: an 80-digit value in the ``IN``
list returns the rows for the valid ids and no error, so this guard is
defence in depth rather than a fix for an observed failure. An earlier
version of this docstring claimed it failed at the driver and cost the
whole page; that was asserted, not measured, and it is wrong.
"""


def _row_can_publish(acquisition: Acquisition) -> bool:
    """Whether this row could contribute at least one link.

    Deliberately cheap and deliberately not the same check as
    :func:`opds_links_for_edition`, which also validates each href. This only
    asks whether the row carries any candidate at all, because its job is to
    stop empty rows consuming an edition's budget.
    """
    data = acquisition.data if isinstance(acquisition.data, dict) else {}
    entries = data.get("acquisitions")
    return bool(isinstance(entries, list) and entries)


SOURCE_KEY = "openlibrary_source"
"""Where an acquisition came from, inside the OPDS2 ``properties`` object.

Namespaced because ``properties`` is an extension point a feed also writes
into, and this value must mean what Open Library says it means.
"""

SOURCE_HARVESTED = "harvested"
"""Ingested from a registered feed, which the import gate checks against the
feed registry."""

SOURCE_SYNTHESIZED = "synthesized"
"""Built by a provider in ``book_providers`` from the edition's
``identifiers.*``, so the URL's host is ours and the name is the registry's.
The identifier itself is still wiki-editable: this says Open Library
constructed the link, not that it verified the book is there."""

SOURCE_EDITION_PROVIDERS = "edition_providers"
"""Copied out of ``Edition.providers``, where a patron controls the URL AND
the provider name, both verbatim.

Distinct from ``synthesized`` because without it the two collide. A patron
who sets `identifiers.project_gutenberg` and also adds a `providers` entry
naming `project_gutenberg` with a URL of their choosing produces two links
that agree in every published field -- and theirs sorts first, because
``DirectProvider`` heads ``PROVIDER_ORDER``. A consumer keying on
``provider_name`` would then read an arbitrary host as Project Gutenberg.
Naming the two sources apart is what keeps that distinguishable."""

MAX_ACQUISITIONS_PER_DOC = 24
"""Cap on the HARVESTED links published for one edition.

Not a cap on the field: synthesized acquisitions are appended afterwards, so
an edition at the cap can publish more than this many links in total. Measured
at 29 for one edition. Said plainly because the docstring used to claim it
bounded the whole list, which it never did.

Bounds a `/search.json` response: `limit` has no upper bound (unlike list
search, which clamps to 1000), so neither the id list nor the row count can be
assumed small.
"""

MAX_ROWS_PER_EDITION = 200
"""Cap on the DATABASE ROWS read for one edition, which is a different unit.

One number served as both, and rows and links are not interchangeable: a row
holds a whole `acquisitions` array, and that array can be empty. So an edition
with 30 rows whose first 24 by sort order carried nothing returned 24 rows and
zero links, with six real acquisitions unreachable -- the field reporting that
a book has no acquisitions when it has six. Rows that carry no acquisitions
at all no longer consume the allowance, which is what actually closes that
class -- raising the number alone just moves the threshold.

It does NOT bound the work, and an earlier version of this docstring said it
did. There is no SQL ``LIMIT``: every matching row crosses the connection and
is built into an ``Acquisition`` before this is consulted. Measured, 10,000
rows for one edition takes 33 ms to fetch and construct, then keeps 200.
Bounding the fetch needs a per-edition window function, filed as a follow-up
and deliberately not a global ``LIMIT``, which starves the tail of the page.
"""

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
connection. It caps how many editions a caller can ask about; it does not cap
the work, because the rows those editions hold are unbounded and unlimited in
SQL. With the row cap at 200 the retained product is 200 x 200, and the
fetched product has no ceiling at all.

Twice the default page size, so it is invisible to real use and a hard stop
for abuse. Editions past it simply do not get the field."""


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


def provider_dedupe_key(name: object) -> str | None:
    """What both sides of the dedupe compare on -- and nothing else.

    Never published. An earlier revision also used a resolved name as the
    ``provider_name`` it served, which turned user-typed text from the
    edit-book form into ``project_gutenberg``, the registry identifier the
    ingest gate and ``identifiers.*`` key on. Resolution is a comparison
    detail; both sides of the response now carry the name their own source
    gave them.

    Falls back to the squashed form rather than leaving an unknown name
    alone, because a feed-only provider (``lenny``) has no ``book_providers``
    entry -- so resolving alone was a no-op for exactly the providers that
    have harvested rows today, and ``"Lenny"`` compared unequal to ``"lenny"``
    while both meant one provider.
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
            # `provider_name` and the source marker are applied AFTER the
            # blob, so a feed can neither relabel itself nor claim to be
            # something other than harvested.
            feed_properties = link.get("properties")
            links.append(
                {
                    **link,
                    "provider_name": row.provider_name,
                    "properties": {**(feed_properties if isinstance(feed_properties, dict) else {}), SOURCE_KEY: SOURCE_HARVESTED},
                }
            )
            if len(links) >= MAX_ACQUISITIONS_PER_DOC:
                logger.info("truncating acquisitions for edition %s at %d links", row.edition_id, MAX_ACQUISITIONS_PER_DOC)
                return links
    return links


def synthesized_acquisitions(solr_doc: dict, edition: Any) -> list[tuple[str | None, Any]]:
    """Every synthesized acquisition, paired with a trusted provider name.

    `get_acquisitions` flattens two different things into one list. A concrete
    provider derives its acquisition from the edition's `identifiers.*` -- so
    Open Library knows which provider that is, and the registry spelling is
    the right one to publish. A provider with no override falls through to
    `AbstractBookProvider.get_acquisitions`, which reads `Edition.providers`:
    the edit-book form, where the name is whatever a patron typed.

    The pair says which is which. `None` means "no trusted name, serve what
    the blob says", which is the only safe answer for patron text -- resolving
    it would publish a registry identifier Open Library has not verified.

    The distinction exists here rather than in `provider_acquisition_as_opds`
    because a bare `Acquisition` carries no provenance; by the time the
    coercion sees one, which of the two produced it is unrecoverable.
    """
    from openlibrary.book_providers import AbstractBookProvider, InternetArchiveProvider, get_book_providers

    paired: list[tuple[str | None, Any]] = []
    for provider in get_book_providers(edition):
        if isinstance(provider, InternetArchiveProvider):
            acquisitions = provider.get_acquisitions(solr_doc, db_edition=edition)
        else:
            acquisitions = provider.get_acquisitions(edition)
        # Identity check on the function, not `hasattr`: every provider has
        # the attribute, and only an override means the name is ours.
        trusted = provider.provider_name if type(provider).get_acquisitions is not AbstractBookProvider.get_acquisitions else None
        paired.extend((trusted, acquisition) for acquisition in acquisitions)
    return paired


def provider_acquisition_as_opds(acquisition: Any, trusted_provider_name: str | None = None) -> dict | None:
    """A ``book_providers.Acquisition`` coerced into an OPDS2 acquisition link.

    So a caller reads one field in one format rather than reconciling
    ``providers`` against ``opds_acquisitions`` itself. Returns None when the
    access kind has no OPDS2 equivalent, rather than inventing a ``rel``.
    """
    rel = OPDS_REL_FOR_ACCESS.get(getattr(acquisition, "access", "") or "")
    href = getattr(acquisition, "url", None)
    if not rel or not _is_safe_url(href):
        return None
    # The RAW name, deliberately. `Edition.providers` is written straight from
    # the edit-book form, so canonicalizing it here would turn user-typed text
    # into `project_gutenberg` -- the registry identifier that `identifiers.*`
    # and the ingest gate key on -- and publish it as though Open Library had
    # verified the provider. Canonicalization is for comparison only; see
    # `provider_dedupe_key`.
    #
    # `trusted_provider_name` is the exception, and only the caller can supply
    # it: a concrete provider derives its acquisition from `identifiers.*`, so
    # the registry spelling is ours to publish. Without it the two sides
    # disagreed -- concrete providers build acquisitions with `short_name`
    # while a harvested row carries `identifier_key or short_name`, because
    # the import validator requires a feed's provider_name to equal the
    # `identifiers.*` key -- so one response carried `gutenberg` on a
    # synthesized link and `project_gutenberg` on a harvested one.
    #
    # Still type-checked: `providers` reaches this through from_json_safe,
    # which does not validate, so the raw value can be a dict or an int and
    # would otherwise be serialized into the response as-is.
    raw_name = trusted_provider_name or getattr(acquisition, "provider_name", None)
    link: dict[str, Any] = {
        "rel": rel,
        "href": href,
        "provider_name": raw_name if isinstance(raw_name, str) and raw_name else None,
        # Says where this came from, and it is the whole point of the field
        # being safe to publish. A harvested link passed the ingest gate,
        # which drops any provider not in the feed registry. A synthesized
        # one was built from `Edition.providers`, which is written straight
        # from the edit-book form -- so a patron can type `project_gutenberg`
        # and have it served verbatim beside a URL they chose. Serving the
        # raw name stops us MINTING a registry identifier from typed text,
        # but it cannot stop someone typing one; without this marker the
        # vetted and unvetted links are the same JSON object and a consumer
        # reading `provider_name` has no way to tell them apart.
        # The trusted name and the source marker come from the same fact --
        # which producer made this acquisition -- so they must not be
        # decided separately. A provider that derived it from `identifiers.*`
        # supplies a name; the base path, reading `Edition.providers`, does
        # not, and its links say so.
        "properties": {SOURCE_KEY: SOURCE_SYNTHESIZED if trusted_provider_name else SOURCE_EDITION_PROVIDERS},
    }
    # `format` and `price` reach this from the same unvalidated blob as
    # `provider_name`, via from_json_safe, which catches only ValueError. An
    # unhashable `format` (a patron saving a list) raised TypeError straight
    # out of the dict lookup and 500ed every search page that edition
    # appeared on.
    raw_format = getattr(acquisition, "format", None)
    if media_type := OPDS_TYPE_FOR_FORMAT.get(raw_format if isinstance(raw_format, str) else ""):
        link["type"] = media_type
    # `providers` carries price as an opaque string ("$4.99"); OPDS2 wants a
    # currency and a number. Passed through under a distinct key rather than
    # guessed at, so nothing downstream reads a fabricated amount -- and only
    # when it really is a string, so a dict cannot be served under a key
    # whose name promises a display string.
    raw_price = getattr(acquisition, "price", None)
    if isinstance(raw_price, str) and raw_price:
        link["properties"]["price_display"] = raw_price
    return link
