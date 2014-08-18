import sys
import _init_path
from openlibrary.config import load_config
from openlibrary.core import db
from openlibrary.api import OpenLibrary, OLError
from openlibrary.solr.process_stats import get_ia_db

import web
import json
import logging
import datetime
import time

logger = logging.getLogger("openlibrary.importer")

class Batch(web.storage):
    @staticmethod
    def find(name):
        result = db.query("SELECT * FROM import_batch where name=$name", vars=locals())
        return result and Batch(result[0]) or None

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

    def _set_status(self, status, error=None, ol_key=None):
        logger.info("set-status %s - %s %s %s", self.ia_id, status, error, ol_key)
        d = dict(
            status=status,
            error=error,
            ol_key=ol_key,
            import_time=datetime.datetime.utcnow())
        db.update("import_item", where="id=$id", vars=self, **d)
        self.update(d)

    def mark_failed(self, error):
        self._set_status(status='failed', error=error)

    def mark_found(self, ol_key):
        self._set_status(status='found', ol_key=ol_key)

    def mark_created(self, ol_key):
        self._set_status(status='created', ol_key=ol_key)

    def do_import(self):
        try:
            ol = get_ol()
            logger.info("importing %s", self.ia_id)
            response = ol._request('/api/import/ia', method='POST', data='identifier=' + self.ia_id).read()
        except OLError:
            self.mark_failed('internal-error')
            return

        if response.startswith("{"):
            d = json.loads(response)
            if d.get("success") and 'edition' in d:
                edition = d['edition']
                if edition['status'] == 'matched':
                    self.mark_found(edition['key'])
                    return
                elif edition['status'] == 'created':
                    self.mark_created(edition['key'])
                    return
            self.mark_failed(d.get('error_code', 'unknown-error'))
        else:
            self.mark_failed('internal-error')

@web.memoize
def get_ol():
    ol = OpenLibrary()
    ol.autologin()
    return ol

def add_items(args):
    batch_name = args[0]
    filename = args[1]

    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.load_items(filename)

def add_new_scans(args):
    """Adds new scans from yesterday.
    """
    if args:
        datestr = args[0]
        yyyy, mm, dd = datestr.split("-")
        date = datetime.date(int(yyyy), int(mm), int(dd))
    else:
        # yesterday
        date = datetime.date.today() - datetime.timedelta(days=1)

    c1 = '%opensource%'
    c2 = '%additional_collections%'

    # Find all scans which are updated/added on the given date 
    # and have been scanned at most 2 months ago
    q = ("SELECT identifier FROM metadata" +
        " WHERE repub_state=4" +
        "   AND mediatype='texts'" +
        "   AND scancenter IS NOT NULL" +
        "   AND collection NOT LIKE $c1" +
        "   AND collection NOT LIKE $c2" + 
        "   AND (curatestate IS NULL OR curatestate != 'dark')" +
        "   AND lower(format) LIKE '%%pdf%%' AND lower(format) LIKE '%%marc%%'" +
        "   AND scandate is NOT NULL AND scandate > $min_scandate" +
        "   AND updated > $date AND updated < ($date::date + INTERVAL '1' DAY)")

    min_scandate = date - datetime.timedelta(60) # 2 months ago
    result = get_ia_db().query(q, vars=dict(
        c1=c1, 
        c2=c2, 
        date=date.isoformat(),
        min_scandate=min_scandate.strftime("%Y%m%d")))
    items = [row.identifier for row in result]    
    batch_name = "new-scans-%04d%02d" % (date.year, date.month)
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items(items)

def import_batch(args):
    batch_name = args[0]
    batch = Batch.find(batch_name)
    if not batch:
        print >> sys.syderr, "Unknown batch", batch
        sys.exit(1)

    for item in batch.get_items():
        item.do_import()

def import_item(args):
    ia_id = args[0]
    item = ImportItem.find_by_identifier(ia_id)
    if item:
        item.do_import()
    else:
        logger.error("%s is not found in the import queue", ia_id)

def import_all(args):
    while True:
        items = ImportItem.find_pending()
        if not items:
            logger.info("No pending items found. sleeping for a minute.")
            time.sleep(60)

        for item in items:
            item.do_import()

def main():
    if "--config" in sys.argv:
        index = sys.argv.index("--config")
        configfile = sys.argv[index+1]
        del sys.argv[index:index+2]
    else:
        configfile = "openlibrary.yml"
    load_config(configfile)

    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd == "add-items":
        return add_items(args)
    elif cmd == "add-new-scans":
        return add_new_scans(args)
    elif cmd == "import-batch":
        return import_batch(args)
    elif cmd == "import-all":
        return import_all(args)
    elif cmd == "import-item":
        return import_item(args)
    else:
        logger.error("Unknown command: %s", cmd)

if __name__ == "__main__":
    main()
