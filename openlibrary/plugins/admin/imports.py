import time
from collections import defaultdict
from openlibrary.core import db

class Imports:
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

    def get_items(self, date):
        """Returns all rows with given added date.
        """
        return db.query(
            "SELECT * FROM import_item" +
            " WHERE added_time::date = $date",
            vars=locals())

    def get_items_summary(self, date):
        """Returns all rows with given added date.
        """
        rows = db.query(
                "SELECT status, count(*) as count" +
                " FROM import_item" +
                " GROUP BY status")
        return {
            "counts": dict([(row.status, row.count) for row in rows])
        }
