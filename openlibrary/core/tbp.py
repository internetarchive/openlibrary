"""Interface to the Trusted Book Providers (TBP) feed registry.

The ``tbp_feed_registry`` table records which provider feeds Open Library
ingests (Better World Books OPDS, Internet Archive Labs Lenny, Standard
Ebooks, ...) and how far each feed has been processed, so the daily
ingestion cron can resume from the last fetched record.

The ``data`` blob is intentionally open-ended: it holds per-feed connector
config (trust level, polling cadence, record caps, cover-import flag, ...)
so onboarding a new micro-feed is "add a row" rather than "write an adapter".

See https://github.com/internetarchive/openlibrary/issues/12844 and
https://github.com/internetarchive/openlibrary/pull/12793.
"""

from __future__ import annotations

import datetime
import json
import logging
from sqlite3 import IntegrityError
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
        except (UniqueViolation, IntegrityError):  # fmt: skip
            # Raced with a concurrent insert; the row now exists.
            return FeedRegistry.find(provider_name=provider_name, url=url)

    @staticmethod
    def from_request(payload: dict, submitter: str | None = None) -> FeedRegistry | None:
        """Register a feed from an API payload (``/api/import/feeds/register``).

        Records a ``status`` of ``"pending"`` and the submitter in the data
        blob for accountability: a registered feed is not trusted by the
        ingestion cron until a maintainer promotes it, mirroring the
        account-linking policy for Lenny lending instances (#12844). Idempotent
        via :meth:`register`.

        :raises ValueError: if ``provider_name`` or ``url`` is missing.
        """
        provider_name = (payload.get("provider_name") or "").strip()
        url = (payload.get("url") or "").strip()
        if not provider_name or not url:
            raise ValueError("provider_name and url are required")
        feed_type = (payload.get("feed_type") or "opds").strip()
        data = dict(payload.get("data") or {})
        data.setdefault("status", "pending")
        if submitter:
            data.setdefault("submitter", submitter)
        if contact := payload.get("contact"):
            data.setdefault("contact", contact)
        return FeedRegistry.register(provider_name=provider_name, url=url, feed_type=feed_type, data=data)

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

    @staticmethod
    def update_fields(id: int, **fields: Any) -> int:
        """Update columns of a feed by id (e.g. ``url``, ``feed_type``, ``data``).

        A ``data`` dict is JSON-serialized. Returns the number of rows changed.
        """
        if isinstance(fields.get("data"), dict):
            fields["data"] = json.dumps(fields["data"])
        fields["updated"] = _utcnow()
        return db.update("tbp_feed_registry", where="id=$id", vars={"id": id}, **fields)

    @staticmethod
    def delete(id: int) -> int:
        """Delete a feed by id. Returns the number of rows removed."""
        return db.delete("tbp_feed_registry", where="id=$id", vars={"id": id})

    @staticmethod
    def try_lock(id: int, ttl_seconds: int = 3600, now: datetime.datetime | None = None) -> bool:
        """Acquire the per-feed harvest lock (advisory). Returns True if acquired.

        Prevents two harvests of the same feed from overlapping and racing the
        cursor. Recorded in the ``data`` blob (``status='running'`` +
        ``locked_at``); a lock older than ``ttl_seconds`` is treated as stale and
        taken over (so a crashed run self-heals).

        Note: read-modify-write, so not race-proof under true concurrency — a
        production runner should use a Postgres advisory lock or a conditional
        UPDATE. Adequate for the single-runner cron in this prototype (#12844).
        """
        now = now or _utcnow()
        feed = FeedRegistry.get_by_id(id)
        if not feed:
            return False
        data = dict(feed.data or {})
        if (locked_at := data.get("locked_at")) and (now - datetime.datetime.fromisoformat(locked_at)).total_seconds() < ttl_seconds:
            return False
        data["locked_at"] = now.isoformat()
        data["status"] = "running"
        FeedRegistry.update_fields(id, data=data)
        return True

    @staticmethod
    def unlock(id: int, status: str = "idle") -> int:
        """Release the per-feed harvest lock, setting ``status`` (default idle)."""
        feed = FeedRegistry.get_by_id(id)
        if not feed:
            return 0
        data = dict(feed.data or {})
        data.pop("locked_at", None)
        data["status"] = status
        return FeedRegistry.update_fields(id, data=data)
