"""Interface to the Trusted Book Providers (TBP) feed registry.

The ``tbp_feed_registry`` table records which provider feeds Open Library
ingests (Better World Books OPDS, Internet Archive Labs Lenny, Standard
Ebooks, ...) and how far each feed has been processed, so the daily
ingestion cron can resume from the last fetched record.

See https://github.com/internetarchive/openlibrary/issues/12844 and
https://github.com/internetarchive/openlibrary/pull/12793.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

import web
from psycopg2.errors import UniqueViolation

from . import db

logger = logging.getLogger("openlibrary.tbp")

if TYPE_CHECKING:
    from web.db import ResultSet


def _utcnow() -> datetime.datetime:
    """Timezone-naive UTC now, matching the table's ``timestamp`` columns."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class FeedRegistry(web.storage):
    """A single row of the ``tbp_feed_registry`` table."""

    TABLENAME = "tbp_feed_registry"

    @staticmethod
    def _from_row(row: Any) -> FeedRegistry:
        registry = FeedRegistry(row)
        # jsonb comes back as a dict from Postgres but as a string from sqlite.
        if isinstance(registry.get("data"), str):
            registry.data = json.loads(registry.data)
        return registry

    @staticmethod
    def find(provider_name: str, url: str) -> FeedRegistry | None:
        result = db.query(
            "SELECT * FROM tbp_feed_registry WHERE provider_name=$provider_name AND url=$url",
            vars={"provider_name": provider_name, "url": url},
        )
        return FeedRegistry._from_row(result[0]) if result else None

    @staticmethod
    def get_by_id(id: int) -> FeedRegistry | None:
        result = db.query("SELECT * FROM tbp_feed_registry WHERE id=$id", vars={"id": id})
        return FeedRegistry._from_row(result[0]) if result else None

    @staticmethod
    def all() -> list[FeedRegistry]:
        rows: ResultSet = db.query("SELECT * FROM tbp_feed_registry ORDER BY id")
        return [FeedRegistry._from_row(row) for row in rows]

    @staticmethod
    def new(
        provider_name: str,
        url: str,
        feed_type: str = "opds",
        data: dict | None = None,
    ) -> FeedRegistry | None:
        db.insert(
            "tbp_feed_registry",
            provider_name=provider_name,
            url=url,
            feed_type=feed_type,
            data=json.dumps(data or {}),
        )
        return FeedRegistry.find(provider_name=provider_name, url=url)

    @staticmethod
    def register(
        provider_name: str,
        url: str,
        feed_type: str = "opds",
        data: dict | None = None,
    ) -> FeedRegistry | None:
        """Idempotently return the registry row, creating it if missing.

        Safe to call repeatedly; honours the ``(provider_name, url)`` unique
        constraint.
        """
        if existing := FeedRegistry.find(provider_name=provider_name, url=url):
            return existing
        try:
            return FeedRegistry.new(
                provider_name=provider_name,
                url=url,
                feed_type=feed_type,
                data=data,
            )
        except UniqueViolation:
            # Raced with a concurrent insert; the row now exists.
            return FeedRegistry.find(provider_name=provider_name, url=url)

    @staticmethod
    def advance(id: int, last_updated: datetime.datetime, data: dict | None = None) -> int:
        """Record ingestion progress for the feed.

        Moves the processing cursor (``last_updated``) forward; optionally
        replaces the ``data`` blob.
        """
        fields: dict[str, Any] = {"last_updated": last_updated, "updated": _utcnow()}
        if data is not None:
            fields["data"] = json.dumps(data)
        return db.update("tbp_feed_registry", where="id=$id", vars={"id": id}, **fields)
