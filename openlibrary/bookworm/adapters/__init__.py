"""Non-OPDS source adapters for the BookWorm feed harvest (#14749).

The feed registry began life speaking only OPDS 2.0 (#12844). Not every provider
publishes an OPDS feed, though: Book Dash is an HTML site with a sitemap, ITAN
(#13413) ships a JSONL dump. This package is the seam that lets those feeds reuse
the whole harvest machinery — staging, dedup, the full-crawl cursor — behind one
uniform interface.

An adapter converts a source's native format into Open Library import records.
The OPDS implementation lives in :class:`~openlibrary.bookworm.harvest.OpdsAdapter`
(it needs the OPDS paging helpers that live beside the harvester); bespoke
adapters live here, one module per source:

- :mod:`openlibrary.bookworm.adapters.bookdash` — scrapes bookdash.org.

Adding a new non-OPDS source means writing an ``iter_records`` here and wiring it
into ``NON_OPDS_ADAPTERS`` in :mod:`openlibrary.bookworm.harvest`. See that
module's ``get_adapter`` for the dispatch, and the README for the step-by-step.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterator

    import requests

    from openlibrary.bookworm.registry import FeedRegistry


@runtime_checkable
class SourceAdapter(Protocol):
    """Convert one provider's native feed into Open Library import records.

    The single interface the harvester drives, whatever the source's format.
    One method, mirroring the OPDS path exactly: yield ``(import_record,
    modified)`` pairs. Everything downstream of that — client-side ``since``
    filtering, change detection, batched staging, and advancing the cursor — is
    the harvester's job, so an adapter never touches the database or the
    registry. That split is what lets a scraper and an OPDS feed share one
    battle-tested staging path.

    ``import_record`` is an ``import.schema.json``-shaped dict (``title``,
    ``authors``, ``source_records``, ...), the same shape
    :func:`openlibrary.bookworm.opds.to_import_record` produces. An adapter skips
    a record it cannot map (no title, no id) by simply not yielding it, rather
    than yielding ``None`` — the harvester never sees the rejects, so they can
    never move the cursor.

    ``modified`` is the record's own last-modified timestamp (tz-aware UTC) or
    ``None`` when the source does not express one:

    - A ``modified_since`` feed (server-filtered) ignores it entirely.
    - A full-crawl feed skips any record whose ``modified`` is at or below the
      cursor, and parks the cursor at the newest ``modified`` it saw.
    - ``None`` from a full-crawl source means "I can't date this record": it is
      considered every run and change detection (against the acquisitions table,
      then against ``import_item.data``) is the only thing keeping it from being
      re-queued. Prefer a real timestamp whenever the source offers one.
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
        """Yield ``(import_record, modified)`` for every mappable record.

        :param feed: the registry row being harvested (url, connector config).
        :param since: the current cursor. A server-filtered adapter uses it to
            build its request; a full-crawl adapter may ignore it (the harvester
            filters by ``modified`` on its side).
        :param session: a shared :class:`requests.Session` carrying the OL
            crawler User-Agent and retry policy — use it for every fetch so the
            adapter inherits proxy and retry behaviour and tests can inject a
            fake transport.
        :param max_pages: a testing cap on how much of the source to walk.
            Truncating a crawl and advancing the cursor anyway permanently skips
            what was not fetched, so an adapter that honours this MUST record
            ``state["truncated"] = True`` when the cap cuts it short.
        :param state: an out-parameter the adapter sets flags on (currently only
            ``truncated``); the harvester reads it to warn that the cursor moved
            past unfetched records.
        """
        ...
