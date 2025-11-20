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
from web.db import ResultSet

from openlibrary.catalog import add_book
from openlibrary.core import cache

from . import db

logger = logging.getLogger("openlibrary.imports")

STAGED_SOURCES: Final = ('amazon', 'idb', 'google_books')

if TYPE_CHECKING:
    from openlibrary.core.models import Edition


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
    def find(name: str, create: bool = False) -> "Batch":  # type: ignore[return]
        result = db.query("SELECT * FROM import_batch where name=$name", vars=locals())
        if result:
            return Batch(result[0])
        elif create:
            return Batch.new(name)

    @staticmethod
    def new(name: str, submitter: str | None = None) -> "Batch":
        db.insert("import_batch", name=name, submitter=submitter)
        return Batch.find(name=name)

    def load_items(self, filename):
        """Adds all the items specified in the filename to this batch."""
        with open(filename) as file:
            items = [line.strip() for line in file if line.strip()]
        self.add_items(items)

    def dedupe_items(self, items):
        ia_ids = [item.get('ia_id') for item in items if item.get('ia_id')]
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
        return [item for item in items if item.get('ia_id') not in already_present]

    def normalize_items(self, items):
        return [
            (
                {'batch_id': self.id, 'ia_id': item}
                if isinstance(item, str)
                else {
                    'batch_id': self.id,
                    # Partner bots set ia_id to eg "partner:978..."
                    'ia_id': item.get('ia_id'),
                    'status': item.get('status', 'pending'),
                    'data': (
                        json.dumps(item.get('data'), sort_keys=True)
                        if item.get('data')
                        else None
                    ),
                    'submitter': (
                        item.get('submitter') if item.get('submitter') else None
                    ),
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
    def find_staged_or_pending(
        identifiers: Iterable[str], sources: Iterable[str] = STAGED_SOURCES
    ) -> ResultSet:
        """
        Find staged or pending items in import_item matching the ia_id identifiers.

        Given a list of ISBNs as identifiers, creates list of `ia_ids` and
        queries the import_item table for them.

        Generated `ia_ids` have the form `{source}:{identifier}` for each `source`
        in `sources` and `identifier` in `identifiers`.
        """
        ia_ids = [
            f"{source}:{identifier}" for identifier in identifiers for source in sources
        ]

        query = (
            "SELECT * "
            "FROM import_item "
            "WHERE status IN ('staged', 'pending') "
            "AND ia_id IN $ia_ids"
        )
        return db.query(query, vars={'ia_ids': ia_ids})

    @staticmethod
    def import_first_staged(
        identifiers: list[str], sources: Iterable[str] = STAGED_SOURCES
    ) -> "Edition | None":
        """
        Import the first staged item in import_item matching the ia_id identifiers.

        This changes the status of matching ia_id identifiers to prevent a
        race condition that can result in duplicate imports.
        """
        ia_ids = [
            f"{source}:{identifier}" for identifier in identifiers for source in sources
        ]

        query_start_processing = (
            "UPDATE import_item "
            "SET status = 'processing' "
            "WHERE status = 'staged' "
            "AND ia_id IN $ia_ids "
            "RETURNING *"
        )

        # TODO: Would this be better to update by the specific ID, given
        # we have the IDs? If this approach works generally, it could work for
        # both `staged` and `pending` by making a dictionary of the original
        # `status` values, and restoring all the original values, based on `id`,
        # save for the one upon which import was tested.
        query_finish_processing = (
            "UPDATE import_item "
            "SET status = 'staged' "
            "WHERE status = 'processing' "
            "AND ia_id IN $ia_ids"
        )

        if in_process_items := db.query(
            query_start_processing, vars={'ia_ids': ia_ids}
        ):
            item: ImportItem = ImportItem(in_process_items[0])
            try:
                return item.single_import()
            except Exception:  # noqa: BLE001
                return None
            finally:
                db.query(query_finish_processing, vars={'ia_ids': ia_ids})

        return None

    def single_import(self) -> "Edition | None":
        """Import the item using load(), swallow errors, update status, and return the Edition if any."""
        try:
            # Avoids a circular import issue.
            from openlibrary.plugins.importapi.code import parse_data  # noqa: PLC0415

            edition, _ = parse_data(self.data.encode('utf-8'))
            if edition:
                reply = add_book.load(edition)
                if reply.get('success') and 'edition' in reply:
                    edition = reply['edition']
                    self.set_status(edition['status'], ol_key=edition['key'])  # type: ignore[index]
                    return web.ctx.site.get(edition['key'])  # type: ignore[index]
                else:
                    error_code = reply.get('error_code', 'unknown-error')
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
    def bulk_mark_pending(
        identifiers: list[str], sources: Iterable[str] = STAGED_SOURCES
    ):
        """
        Given a list of ISBNs, creates list of `ia_ids` and queries the import_item
        table the `ia_ids`.

        Generated `ia_ids` have the form `{source}:{id}` for each `source` in `sources`
        and `id` in `identifiers`.
        """
        ia_ids = []
        for id in identifiers:
            ia_ids += [f'{source}:{id}' for source in sources]

        query = (
            "UPDATE import_item "
            "SET status = 'pending' "
            "WHERE status = 'staged' "
            "AND ia_id IN $ia_ids"
        )
        db.query(query, vars={'ia_ids': ia_ids})

    def set_status(self, status, error=None, ol_key=None):
        id_ = self.ia_id or f"{self.batch_id}:{self.id}"
        logger.info("set-status %s - %s %s %s", id_, status, error, ol_key)
        d = {
            "status": status,
            "error": error,
            "ol_key": ol_key,
            "import_time": datetime.datetime.utcnow(),
        }
        if status != 'failed':
            d = dict(**d, data=None)
        db.update("import_item", where="id=$id", vars=self, **d)
        self.update(d)

    def mark_failed(self, error):
        self.set_status(status='failed', error=error)

    def mark_found(self, ol_key):
        self.set_status(status='found', ol_key=ol_key)

    def mark_created(self, ol_key):
        self.set_status(status='created', ol_key=ol_key)

    def mark_modified(self, ol_key):
        self.set_status(status='modified', ol_key=ol_key)

    @classmethod
    def delete_items(
        cls, ia_ids: list[str], batch_id: int | None = None, _test: bool = False
    ):
        oldb = db.get_db()
        data: dict[str, Any] = {
            'ia_ids': ia_ids,
        }

        where = 'ia_id IN $ia_ids'

        if batch_id:
            data['batch_id'] = batch_id
            where += ' AND batch_id=$batch_id'

        return oldb.delete('import_item', where=where, vars=data, _test=_test)


class Stats:
    """Import Stats."""

    @staticmethod
    def get_imports_per_hour():
        """Returns the number imports happened in past one hour duration."""
        try:
            result = db.query(
                "SELECT count(*) as count FROM import_item"
                " WHERE import_time > CURRENT_TIMESTAMP - interval '1' hour"
            )
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return 0
        return result[0].count

    @staticmethod
    def _get_count(status=None):
        where = "status=$status" if status else "1=1"
        try:
            rows = db.select(
                "import_item", what="count(*) as count", where=where, vars=locals()
            )
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

    @staticmethod
    def get_items(date=None, order=None, limit=None):
        """Returns all rows with given added date."""
        where = "added_time::date = $date" if date else "1 = 1"
        try:
            return db.select(
                "import_item", where=where, order=order, limit=limit, vars=locals()
            )
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return []

    @staticmethod
    def get_items_summary(date):
        """Returns all rows with given added date."""
        rows = db.query(
            "SELECT status, count(*) as count"
            " FROM import_item"
            " WHERE added_time::date = $date"
            " GROUP BY status",
            vars=locals(),
        )
        return {"counts": {row.status: row.count for row in rows}}
