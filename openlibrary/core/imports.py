"""Interface to import queue."""

import contextlib
import datetime
import json
import logging
import time
from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Final

import web
from psycopg2.errors import UndefinedTable, UniqueViolation
from pydantic import ValidationError

from openlibrary.catalog import add_book
from openlibrary.core import cache

from . import db

logger = logging.getLogger("openlibrary.imports")

STAGED_SOURCES: Final = ("amazon", "idb", "google_books")

if TYPE_CHECKING:
    from web.db import ResultSet

    from openlibrary.core.models import Edition


def _record_changed(stored: str | None, incoming: str | None) -> bool:
    """Whether a staged record differs from what is already queued.

    Compares parsed JSON rather than raw text so key ordering cannot masquerade
    as a change.

    A NULL ``stored`` means the row already completed and had its data cleared
    by :meth:`ImportItem.set_status`. There is nothing to compare against, so it
    counts as CHANGED: the caller only offers records a feed has already flagged
    as modified, and treating "cannot tell" as "unchanged" would mean a price
    that changes after its first successful import never reaches the catalog
    again -- silently defeating the whole point of the feed. Callers that can
    compare against durable state (the acquisitions table, say) should filter
    before calling.
    """
    if incoming is None:
        return False
    if stored is None:
        return True
    try:
        return json.loads(stored) != json.loads(incoming)
    except TypeError, ValueError:
        # Unparsable stored data: prefer leaving the row alone over re-queuing
        # a corpus on a parse error.
        logger.warning("could not compare staged record; leaving it unchanged")
        return False


class Batch(web.storage):
    def __init__(self, mapping, *requires, **defaults):
        """
        Initialize some statistics instance attributes yet retain web.storage's __init__ method.
        """
        super().__init__(mapping, *requires, **defaults)
        self.total_submitted: int = 0
        self.total_queued: int = 0
        self.total_skipped: int = 0
        self.items_skipped: set = set()

    @staticmethod
    def find(name: str, create: bool = False) -> Batch:  # type: ignore[return]
        result = db.query("SELECT * FROM import_batch where name=$name", vars=locals())
        if result:
            return Batch(result[0])
        elif create:
            return Batch.new(name)

    @staticmethod
    def new(name: str, submitter: str | None = None) -> Batch:
        db.insert("import_batch", name=name, submitter=submitter)
        return Batch.find(name=name)

    def load_items(self, filename):
        """Adds all the items specified in the filename to this batch."""
        with open(filename) as file:
            items = [line.strip() for line in file if line.strip()]
        self.add_items(items)

    def dedupe_items(self, items: list[dict]) -> list[dict]:
        ia_ids = [item.get("ia_id") for item in items if item.get("ia_id")]
        already_present = {
            row.ia_id
            for row in db.query(
                "SELECT ia_id FROM import_item WHERE ia_id IN $ia_ids",
                vars={"ia_ids": ia_ids},
            )
        }
        # ignore already present
        logger.info(
            "batch %s: %d items are already present, ignoring...",
            self.name,
            len(already_present),
        )

        # Update batch counts
        self.total_submitted = len(ia_ids)
        self.total_skipped = len(already_present)
        self.total_queued = self.total_submitted - self.total_skipped
        self.items_skipped = already_present

        # Those unique items whose ia_id's aren't already present
        return [item for item in items if item.get("ia_id") not in already_present]

    REFRESHABLE_STATUSES = ("created", "modified", "found", "failed")
    """Terminal statuses -- the only rows safe to refresh.

    A row that is ``pending`` or ``staged`` is QUEUED, and ``manage-imports``
    (``import_all`` -> ``find_pending()``) never claims it -- it stays ``pending``
    for the whole in-flight window. So replacing a queued row's ``data`` races a
    worker that has already read the old copy into memory: the worker imports the
    stale record, then ``set_status`` writes the terminal status and NULLs
    ``data``, discarding the update with no error.

    Refusing to touch queued rows removes that race entirely. Nothing is lost:
    once the row reaches a terminal status its ``data`` is NULL, so the next
    harvest that sees a genuine change refreshes it then. ``processing`` is
    excluded too -- it is written only by the on-demand staged path.
    """

    def add_or_refresh_items(self, items: list[dict]) -> dict[str, int]:
        """Insert new items, and refresh CHANGED ones in place instead of skipping.

        ``add_items`` skips anything whose ``ia_id`` already exists, anywhere, at
        any status. That is right for firehose sources -- Amazon price lookups
        and daily archive.org imports re-offer unchanged records constantly, and
        re-queuing them is what previously overwhelmed the database.

        It is wrong for a registered feed, which is a change stream: the provider
        returns a record because it changed, and dropping it discards the update
        we asked for -- a Better World Books price, say. This variant compares
        content and re-queues only what actually differs, so the protection
        against re-processing unchanged records is kept.

        A row whose ``data`` is NULL (cleared by :meth:`ImportItem.set_status`
        once it completed) counts as changed, since there is nothing left to
        compare against and the caller only offers records a feed already
        flagged as modified. Callers with durable prior state should filter
        first -- :mod:`openlibrary.bookworm.harvest` compares against the
        acquisitions table.

        Rows claimed by manage-imports (``status='processing'``) are left alone
        rather than yanked mid-flight.

        Additive and opt-in -- ``add_items`` is untouched, so no existing
        importer changes behaviour.

        :return: counts keyed ``added``, ``refreshed``, ``unchanged``,
            ``skipped_in_flight``.
        """
        normalized = self.normalize_items(items)
        counts = {"added": 0, "refreshed": 0, "unchanged": 0, "skipped_in_flight": 0}
        if not normalized:
            return counts

        ia_ids = [item["ia_id"] for item in normalized if item.get("ia_id")]
        if not ia_ids:
            return counts

        # Scoped to THIS batch. The unique key is (batch_id, ia_id), so the same
        # ia_id can legitimately exist in another importer's batch -- an
        # unscoped read collapses those non-deterministically, and turning that
        # read into a write would let a feed refresh (and effectively steal)
        # another batch's row.
        existing = {
            row.ia_id: row
            for row in db.query(
                "SELECT id, ia_id, data, status FROM import_item WHERE batch_id=$batch_id AND ia_id IN $ia_ids",
                vars={"batch_id": self.id, "ia_ids": ia_ids},
            )
        }

        to_insert = []
        for item in normalized:
            row = existing.get(item.get("ia_id"))
            if row is None:
                to_insert.append(item)
                counts["added"] += 1
                continue
            if row.status not in self.REFRESHABLE_STATUSES:
                # Queued or in flight: leave it for the worker that may already
                # be holding it.
                counts["skipped_in_flight"] += 1
                continue
            if not _record_changed(row.data, item.get("data")):
                counts["unchanged"] += 1
                continue
            # Status predicate closes the window between the SELECT above and
            # this write. ol_key is cleared because the row is no longer a
            # completed import pointing at an edition.
            updated = db.update(
                "import_item",
                where="id=$id AND status=$status",
                vars={"id": row.id, "status": row.status},
                data=item.get("data"),
                status="pending",
                error=None,
                import_time=None,
                ol_key=None,
            )
            if updated:
                counts["refreshed"] += 1
            else:
                counts["skipped_in_flight"] += 1

        if to_insert:
            # Mirrors add_items: bulk insert, falling back per row so one
            # collision cannot lose the rest of the batch.
            try:
                db.get_db().multiple_insert("import_item", to_insert)
            except UniqueViolation:
                for item in to_insert:
                    with contextlib.suppress(UniqueViolation):
                        db.get_db().insert("import_item", **item)

        logger.info(
            "batch %s: %d added, %d refreshed, %d unchanged, %d in flight",
            self.name,
            counts["added"],
            counts["refreshed"],
            counts["unchanged"],
            counts["skipped_in_flight"],
        )
        return counts

    def normalize_items(self, items: list[str] | list[dict]) -> list[dict]:
        return [
            (
                {"batch_id": self.id, "ia_id": item}
                if isinstance(item, str)
                else {
                    "batch_id": self.id,
                    # Partner bots set ia_id to eg "partner:978..."
                    "ia_id": item.get("ia_id"),
                    "status": item.get("status", "pending"),
                    "data": (json.dumps(item.get("data"), sort_keys=True) if item.get("data") else None),
                    "submitter": item.get("submitter") or None,
                }
            )
            for item in items
        ]

    def add_items(self, items: list[str] | list[dict]) -> None:
        """
        :param items: either a list of `ia_id`  (legacy) or a list of dicts
            containing keys `ia_id` and book `data`. In the case of
            the latter, `ia_id` will be of form e.g. "isbn:1234567890";
            i.e. of a format id_type:value which cannot be a valid IA id.
        """
        if not items:
            return None

        logger.info("batch %s: adding %d items", self.name, len(items))

        items = self.dedupe_items(self.normalize_items(items))
        if items:
            try:
                # TODO: Upgrade psql and use `INSERT OR IGNORE`
                # otherwise it will fail on UNIQUE `data`
                # https://stackoverflow.com/questions/1009584
                db.get_db().multiple_insert("import_item", items)
            except UniqueViolation:
                for item in items:
                    with contextlib.suppress(UniqueViolation):
                        db.get_db().insert("import_item", **item)

            logger.info("batch %s: added %d items", self.name, len(items))

        return None

    def get_items(self, status="pending"):
        result = db.where("import_item", batch_id=self.id, status=status)
        return [ImportItem(row) for row in result]


class ImportItem(web.storage):
    @staticmethod
    def find_pending(limit=1000):
        if result := db.where("import_item", status="pending", order="id", limit=limit):
            return map(ImportItem, result)

        return None

    @staticmethod
    def find_staged_or_pending(identifiers: Iterable[str], sources: Iterable[str] = STAGED_SOURCES) -> ResultSet:
        """
        Find staged or pending items in import_item matching the ia_id identifiers.

        Given a list of ISBNs as identifiers, creates list of `ia_ids` and
        queries the import_item table for them.

        Generated `ia_ids` have the form `{source}:{identifier}` for each `source`
        in `sources` and `identifier` in `identifiers`.
        """
        ia_ids = [f"{source}:{identifier}" for identifier in identifiers for source in sources]

        query = "SELECT * FROM import_item WHERE status IN ('staged', 'pending') AND ia_id IN $ia_ids"
        return db.query(query, vars={"ia_ids": ia_ids})

    @staticmethod
    def import_first_staged(identifiers: list[str], sources: Iterable[str] = STAGED_SOURCES) -> Edition | None:
        """
        Import the first staged item in import_item matching the ia_id identifiers.

        This changes the status of matching ia_id identifiers to prevent a
        race condition that can result in duplicate imports.
        """
        ia_ids = [f"{source}:{identifier}" for identifier in identifiers for source in sources]

        query_start_processing = "UPDATE import_item SET status = 'processing' WHERE status = 'staged' AND ia_id IN $ia_ids RETURNING *"

        # TODO: Would this be better to update by the specific ID, given
        # we have the IDs? If this approach works generally, it could work for
        # both `staged` and `pending` by making a dictionary of the original
        # `status` values, and restoring all the original values, based on `id`,
        # save for the one upon which import was tested.
        query_finish_processing = "UPDATE import_item SET status = 'staged' WHERE status = 'processing' AND ia_id IN $ia_ids"

        if in_process_items := db.query(query_start_processing, vars={"ia_ids": ia_ids}):
            item: ImportItem = ImportItem(in_process_items[0])
            try:
                return item.single_import()
            except Exception:  # noqa: BLE001
                return None
            finally:
                db.query(query_finish_processing, vars={"ia_ids": ia_ids})

        return None

    def single_import(self) -> Edition | None:
        """Import the item using load(), swallow errors, update status, and return the Edition if any."""
        try:
            # Avoids a circular import issue.
            from openlibrary.plugins.importapi.code import parse_data

            edition, _ = parse_data(self.data.encode("utf-8"))
            if edition:
                reply = add_book.load(edition)
                if reply.get("success") and "edition" in reply:
                    edition = reply["edition"]
                    self.set_status(edition["status"], ol_key=edition["key"])  # type: ignore[index]
                    return web.ctx.site.get(edition["key"])  # type: ignore[index]
                else:
                    error_code = reply.get("error_code", "unknown-error")
                    self.set_status("failed", error=error_code)

        except ValidationError:
            self.set_status("failed", error="invalid-value")
            return None
        except Exception:  # noqa: BLE001
            self.set_status("failed", error="unknown-error")
            return None

        return None

    @staticmethod
    def find_by_identifier(identifier):
        result = db.where("import_item", ia_id=identifier)
        if result:
            return ImportItem(result[0])

    @staticmethod
    def bulk_mark_pending(identifiers: list[str], sources: Iterable[str] = STAGED_SOURCES):
        """
        Given a list of ISBNs, creates list of `ia_ids` and queries the import_item
        table the `ia_ids`.

        Generated `ia_ids` have the form `{source}:{id}` for each `source` in `sources`
        and `id` in `identifiers`.
        """
        ia_ids = []
        for id in identifiers:
            ia_ids += [f"{source}:{id}" for source in sources]

        query = "UPDATE import_item SET status = 'pending' WHERE status = 'staged' AND ia_id IN $ia_ids"
        db.query(query, vars={"ia_ids": ia_ids})

    def set_status(self, status, error=None, ol_key=None):
        id_ = self.ia_id or f"{self.batch_id}:{self.id}"
        logger.info("set-status %s - %s %s %s", id_, status, error, ol_key)
        d = {
            "status": status,
            "error": error,
            "ol_key": ol_key,
            "import_time": datetime.datetime.utcnow(),
        }
        if status != "failed":
            d = dict(**d, data=None)
        db.update("import_item", where="id=$id", vars=self, **d)
        self.update(d)

    def mark_failed(self, error):
        self.set_status(status="failed", error=error)

    def mark_found(self, ol_key):
        self.set_status(status="found", ol_key=ol_key)

    def mark_created(self, ol_key):
        self.set_status(status="created", ol_key=ol_key)

    def mark_modified(self, ol_key):
        self.set_status(status="modified", ol_key=ol_key)

    @classmethod
    def delete_items(cls, ia_ids: list[str], batch_id: int | None = None, _test: bool = False):
        oldb = db.get_db()
        data: dict[str, Any] = {
            "ia_ids": ia_ids,
        }

        where = "ia_id IN $ia_ids"

        if batch_id:
            data["batch_id"] = batch_id
            where += " AND batch_id=$batch_id"

        return oldb.delete("import_item", where=where, vars=data, _test=_test)


class Stats:
    """Import Stats."""

    @staticmethod
    def get_imports_per_hour():
        """Returns the number imports happened in past one hour duration."""
        try:
            result = db.query("SELECT count(*) as count FROM import_item WHERE import_time > CURRENT_TIMESTAMP - interval '1' hour")
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return 0
        return result[0].count

    @staticmethod
    def _get_count(status=None):
        where = "status=$status" if status else "1=1"
        try:
            rows = db.select("import_item", what="count(*) as count", where=where, vars=locals())
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return 0
        return rows[0].count

    @classmethod
    def get_count(cls, status=None, use_cache=False):
        return (
            cache.memcache_memoize(
                cls._get_count,
                "imports.get_count",
                timeout=5 * 60,
            )
            if use_cache
            else cls._get_count
        )(status=status)

    @staticmethod
    def get_count_by_status(date=None):
        rows = db.query("SELECT status, count(*) FROM import_item GROUP BY status")
        return {row.status: row.count for row in rows}

    @staticmethod
    def _get_count_by_date_status(ndays=10):
        try:
            result = db.query(
                "SELECT added_time::date as date, status, count(*)"
                " FROM import_item "
                " WHERE added_time > current_date - interval '$ndays' day"
                " GROUP BY 1, 2"
                " ORDER BY 1 desc",
                vars=locals(),
            )
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return []
        d = defaultdict(dict)
        for row in result:
            d[row.date][row.status] = row.count
        date_counts = sorted(d.items(), reverse=True)
        return date_counts

    @classmethod
    def get_count_by_date_status(cls, ndays=10, use_cache=False):
        if use_cache:
            date_counts = cache.memcache_memoize(
                cls._get_count_by_date_status,
                "imports.get_count_by_date_status",
                timeout=60 * 60,
            )(ndays=ndays)
            # Don't cache today
            date_counts[0] = cache.memcache_memoize(
                cls._get_count_by_date_status,
                "imports.get_count_by_date_status_today",
                timeout=60 * 3,
            )(ndays=1)[0]
            return date_counts
        return cls._get_count_by_date_status(ndays=ndays)

    @staticmethod
    def _get_books_imported_per_day():
        def date2millis(date):
            return time.mktime(date.timetuple()) * 1000

        try:
            query = """
            SELECT import_time::date as date, count(*) as count
            FROM import_item WHERE status ='created'
            GROUP BY 1 ORDER BY 1
            """
            rows = db.query(query)
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return []
        return [[date2millis(row.date), row.count] for row in rows]

    @classmethod
    def get_books_imported_per_day(cls, use_cache=False):
        return (
            cache.memcache_memoize(
                cls._get_books_imported_per_day,
                "import_stats.get_books_imported_per_day",
                timeout=60 * 60,
            )
            if use_cache
            else cls._get_books_imported_per_day
        )()

    # web.db's `order=` kwarg is not parameterized; restrict to a fixed set
    # so this stays robust even if a future caller forwards user input as the
    # `order` argument (the bug shape fixed for /merges in PR #12460).
    _ALLOWED_ORDERS: Final = {
        None: None,
        "import_time desc": "import_time desc",
        "import_time asc": "import_time asc",
        "added_time desc": "added_time desc",
        "added_time asc": "added_time asc",
    }

    @staticmethod
    def get_items(date=None, order=None, limit=None):
        """Returns all rows with given added date."""
        if order not in Stats._ALLOWED_ORDERS:
            raise ValueError(f"Invalid order: {order!r}. Must be one of {list(Stats._ALLOWED_ORDERS)}.")
        order = Stats._ALLOWED_ORDERS[order]
        where = "added_time::date = $date" if date else "1 = 1"
        try:
            return db.select("import_item", where=where, order=order, limit=limit, vars=locals())
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return []

    @staticmethod
    def get_items_summary(date):
        """Returns all rows with given added date."""
        rows = db.query(
            "SELECT status, count(*) as count FROM import_item WHERE added_time::date = $date GROUP BY status",
            vars=locals(),
        )
        return {"counts": {row.status: row.count for row in rows}}
