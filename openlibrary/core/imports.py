"""Interface to import queue.
"""
from collections import defaultdict
import logging
import datetime
import time
import web

from . import db

logger = logging.getLogger("openlibrary.imports")

class Batch(web.storage):
    @staticmethod
    def find(name, create=False):
        result = db.query("SELECT * FROM import_batch where name=$name", vars=locals())
        if result:
            return Batch(result[0])
        elif create:
            return Batch.new(name)

    @staticmethod
    def new(name):
        db.insert("import_batch", name=name)
        return Batch.find(name=name)

    def load_items(self, filename):
        """Adds all the items specified in the filename to this batch.
        """
        items = [line.strip() for line in open(filename) if line.strip()]
        self.add_items(items)

    def add_items(self, items):
        if not items:
            return
        logger.info("batch %s: adding %d items", self.name, len(items))
        already_present = [row.ia_id for row in db.query("SELECT ia_id FROM import_item WHERE ia_id IN $items", vars=locals())]
        # ignore already present
        items = list(set(items) - set(already_present))

        logger.info("batch %s: %d items are already present, ignoring...", self.name, len(already_present))
        if items:
            values = [dict(batch_id=self.id, ia_id=item) for item in items]
            db.get_db().multiple_insert("import_item", values)        
            logger.info("batch %s: added %d items", self.name, len(items))

    def get_items(self, status="pending"):
        result = db.where("import_item", batch_id=self.id, status=status)
        return [ImportItem(row) for row in result]

class ImportItem(web.storage):
    @staticmethod
    def find_pending(limit=1000):
        result = db.where("import_item", status="pending", order="id", limit=limit)
        return [ImportItem(row) for row in result]

    @staticmethod
    def find_by_identifier(identifier):
        result = db.where("import_item", ia_id=identifier)
        if result:
            return ImportItem(result[0])

    def set_status(self, status, error=None, ol_key=None):
        logger.info("set-status %s - %s %s %s", self.ia_id, status, error, ol_key)
        d = dict(
            status=status,
            error=error,
            ol_key=ol_key,
            import_time=datetime.datetime.utcnow())
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


class Stats:
    """Import Stats."""
    def get_count_by_status(self, date=None):
        rows = db.query("SELECT status, count(*) FROM import_item GROUP BY status")
        return dict([(row.status, row.count) for row in rows])

    def get_count_by_date_status(self, ndays=10):
        result = db.query(
            "SELECT added_time::date as date, status, count(*)" +
            " FROM import_item " +
            " WHERE added_time > current_date - interval '$ndays' day"
            " GROUP BY 1, 2" + 
            " ORDER BY 1 desc",
            vars=locals())
        d = defaultdict(dict)
        for row in result:
            d[row.date][row.status] = row.count
        return sorted(d.items(), reverse=True)

    def get_books_imported_per_day(self):
        rows = db.query(
            "SELECT import_time::date as date, count(*) as count"
            " FROM import_item" +
            " WHERE status='created'"
            " GROUP BY 1" +
            " ORDER BY 1")
        return [[self.date2millis(row.date), row.count] for row in rows]

    def date2millis(self, date):
        return time.mktime(date.timetuple()) * 1000

    def get_items(self, date=None, order=None, limit=None):
        """Returns all rows with given added date.
        """
        if date:
            where = "added_time::date = $date"
        else:
            where = "1 = 1"
        return db.select("import_item", 
            where=where, 
            order=order, 
            limit=limit,
            vars=locals())

    def get_items_summary(self, date):
        """Returns all rows with given added date.
        """
        rows = db.query(
                "SELECT status, count(*) as count" +
                " FROM import_item" +
                " WHERE added_time::date = $date"
                " GROUP BY status",
                vars=locals())
        return {
            "counts": dict([(row.status, row.count) for row in rows])
        }
