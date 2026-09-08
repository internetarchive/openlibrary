"""Feed registry for the BookWorm ingestion service (#12844).

Tracks the provider feeds Open Library ingests (Better World Books, Project
Gutenberg, Lenny, ...) and how far each has been processed — the
``last_updated`` cursor — so the bookworm poller resumes incrementally.

Lives in the Open Library database for v1 (``feed_registry`` table); it moves to
a dedicated bookworm database later. Per-feed connector config lives in the
``data`` blob: ``id_strategy`` (how to derive the publication id) and
``cursor_style`` (how the feed expresses "since"). A row maps to an
:class:`openlibrary.bookworm.opds.Feed`.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import web

from openlibrary.bookworm.opds import Feed
from openlibrary.core import db

logger = logging.getLogger("openlibrary.bookworm.registry")

if TYPE_CHECKING:
    from web.db import ResultSet

CursorStyle = Literal["client", "modified_since"]
"""How a feed lets us fetch only what changed since the last run:

- ``modified_since``: the feed honors a ``?modified_since=<cursor>`` query param
  and filters server-side (Gutenberg, Lenny). This is the desired shape.
- ``client``: the feed has no such param, so it must be crawled in full and
  filtered on our side by each publication's ``modified`` timestamp (currently
  only BWB). Ideally every feed becomes ``modified_since`` and this can be
  dropped along with the full-crawl code path.
"""

CURSOR_CLIENT: CursorStyle = "client"
CURSOR_MODIFIED_SINCE: CursorStyle = "modified_since"


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class FeedRegistry(web.storage):
    """A single row of the ``feed_registry`` table."""

    # Columns (annotations so the fields type-check; web.storage holds them):
    id: int
    provider_name: str
    feed_type: str
    url: str
    last_updated: datetime.datetime | None
    data: dict
    created: datetime.datetime
    updated: datetime.datetime

    TABLENAME = "feed_registry"

    @staticmethod
    def _from_row(row: Any) -> FeedRegistry:
        registry = FeedRegistry(row)
        # jsonb comes back as a dict from Postgres but as a string from SQLite.
        raw = registry.get("data")
        if isinstance(raw, str):
            registry.data = json.loads(raw)
        return registry

    @staticmethod
    def find(provider_name: str, url: str) -> FeedRegistry | None:
        rows = db.query(
            "SELECT * FROM feed_registry WHERE provider_name=$provider_name AND url=$url",
            vars={"provider_name": provider_name, "url": url},
        )
        return FeedRegistry._from_row(rows[0]) if rows else None

    @staticmethod
    def get_by_id(id: int) -> FeedRegistry | None:
        rows = db.query("SELECT * FROM feed_registry WHERE id=$id", vars={"id": id})
        return FeedRegistry._from_row(rows[0]) if rows else None

    @staticmethod
    def all() -> list[FeedRegistry]:
        rows: ResultSet = db.query("SELECT * FROM feed_registry ORDER BY id")
        return [FeedRegistry._from_row(row) for row in rows]

    @staticmethod
    def provider_names() -> set[str]:
        """The ``provider_name`` of every registered feed.

        This is the trust anchor for acquisitions: the catalog only writes an
        acquisition whose ``provider_name`` names a registered feed, so records
        arriving through the (privileged) import API cannot mint acquisitions
        for arbitrary providers. See :func:`add_book._save_acquisitions`.
        """
        rows: ResultSet = db.query("SELECT DISTINCT provider_name FROM feed_registry")
        return {row.provider_name for row in rows}

    @staticmethod
    def register(
        provider_name: str,
        url: str,
        feed_type: str = "opds",
        id_strategy: str = "isbn",
        cursor_style: CursorStyle = CURSOR_CLIENT,
        data: dict | None = None,
    ) -> FeedRegistry | None:
        """Idempotently register a feed (keyed on ``provider_name`` + ``url``).

        ``id_strategy`` and ``cursor_style`` are the connector config; extra
        config may be passed via ``data``. Pass ``cursor_style="modified_since"``
        for feeds that support the server-side filter (Gutenberg, Lenny); the
        conservative default ``client`` (full crawl) works for any feed.
        """
        if existing := FeedRegistry.find(provider_name, url):
            return existing
        blob = {"id_strategy": id_strategy, "cursor_style": cursor_style, "status": "pending", **(data or {})}
        db.insert("feed_registry", provider_name=provider_name, url=url, feed_type=feed_type, data=json.dumps(blob))
        return FeedRegistry.find(provider_name, url)

    @staticmethod
    def advance(id: int, last_updated: datetime.datetime, data: dict | None = None) -> int:
        """Move the processing cursor (``last_updated``) forward."""
        fields: dict[str, Any] = {"last_updated": last_updated, "updated": _utcnow()}
        if data is not None:
            fields["data"] = json.dumps(data)
        return db.update("feed_registry", where="id=$id", vars={"id": id}, **fields)

    # --- connector config accessors ---

    @property
    def id_strategy(self) -> str:
        return (self.data or {}).get("id_strategy", "isbn")

    @property
    def cursor_style(self) -> CursorStyle:
        return (self.data or {}).get("cursor_style", CURSOR_CLIENT)

    @property
    def supports_modified_since(self) -> bool:
        """Whether the feed filters server-side via ``?modified_since=<cursor>``."""
        return self.cursor_style == CURSOR_MODIFIED_SINCE

    def request_url(self, since: datetime.datetime) -> str:
        """This feed's fetch URL with the ``modified_since`` cursor injected.

        The cursor is truncated to a date (day granularity), so a run re-requests
        the whole starting day — conservative overlap, never a missed record
        (imports are idempotent).
        """
        parts = urlparse(self.url)
        query = parse_qs(parts.query, keep_blank_values=True)
        query["modified_since"] = [since.date().isoformat()]
        return urlunparse(parts._replace(query=urlencode(query, doseq=True)))

    def to_feed(self) -> Feed:
        """The :class:`~openlibrary.bookworm.opds.Feed` parser config for this row."""
        return Feed(provider_name=self.provider_name, id_strategy=self.id_strategy)
