"""Feed registry for the BookWorm ingestion service (#12844).

Tracks the provider feeds Open Library ingests (Better World Books, Project
Gutenberg, Lenny, ...) and how far each has been processed — the
``last_updated`` cursor — so the bookworm poller resumes incrementally.

Lives in the Open Library database for v1 (``feed_registry`` table); it moves to
a dedicated bookworm database later. Per-feed connector config lives in the
``data`` blob: ``id_strategy`` (how to derive the publication id) and
``cursor_style`` (how the feed expresses "since" — client-side filtering vs a
``modified_since`` query param). A row maps to an
:class:`openlibrary.bookworm.opds.Feed`.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

import web

from openlibrary.bookworm.opds import Feed
from openlibrary.core import db

logger = logging.getLogger("openlibrary.bookworm.registry")

if TYPE_CHECKING:
    from web.db import ResultSet

# cursor styles
CURSOR_CLIENT = "client"  # crawl rel=next, filter modified > cursor client-side (BWB, Lenny)
CURSOR_MODIFIED_SINCE = "modified_since"  # inject ?modified_since=<cursor> into the request (Gutenberg)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class FeedRegistry(web.storage):
    """A single row of the ``feed_registry`` table."""

    TABLENAME = "feed_registry"

    @staticmethod
    def _from_row(row: Any) -> FeedRegistry:
        registry = FeedRegistry(row)
        if isinstance(registry.get("data"), str):
            registry.data = json.loads(registry.data)
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
    def register(
        provider_name: str,
        url: str,
        feed_type: str = "opds",
        id_strategy: str = "isbn",
        cursor_style: str = CURSOR_CLIENT,
        data: dict | None = None,
    ) -> FeedRegistry | None:
        """Idempotently register a feed (keyed on ``provider_name`` + ``url``).

        ``id_strategy`` and ``cursor_style`` are the connector config; extra
        config may be passed via ``data``.
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
    def cursor_style(self) -> str:
        return (self.data or {}).get("cursor_style", CURSOR_CLIENT)

    def to_feed(self) -> Feed:
        """The :class:`~openlibrary.bookworm.opds.Feed` parser config for this row."""
        return Feed(provider_name=self.provider_name, id_strategy=self.id_strategy)
