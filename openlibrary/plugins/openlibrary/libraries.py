"""Controller for /libraries.
"""
import time
import logging
import datetime
import itertools

import web
import couchdb

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template, add_flash_message, public
from openlibrary.core import inlibrary

logger = logging.getLogger("openlibrary.libraries")

class libraries(delegate.page):
    def GET(self):
        return render_template("libraries/index", self.get_branches())
    
    def get_branches(self):
        branches = sorted(get_library_branches(), key=lambda b: b.name.upper())
        return itertools.groupby(branches, lambda b: b.name and b.name[0])
        
class libraries_notes(delegate.page):
    path = "(/libraries/[^/]+)/notes"
    
    def POST(self, key):
        doc = web.ctx.site.get(key)
        if doc is None or doc.type.key != "/type/library":
            raise web.notfound()
        elif not web.ctx.site.can_write(key):
            raise render_template("permission_denied")
        else:
            i = web.input(note="")
            
            user = web.ctx.site.get_user()
            author = user and {"key": user.key}
            timestamp = {"type": "/type/datetime", "value": datetime.datetime.utcnow().isoformat()}
            
            note = {"note": i.note, "author": {"key": user.key}, "timestamp": timestamp}
            
            if not doc.notes:
                doc.notes = []
            doc.notes.append(note)
        doc._save(comment="Added a note.")
        raise web.seeother(key)
        
def get_library_branches():
    """Returns library branches grouped by first letter."""
    libraries = inlibrary.get_libraries()
    for lib in libraries:
        for branch in lib.get_branches():
            branch.library = lib.name
            yield branch
            
class libraries_dashboard(delegate.page):
    path = "/libraries/dashboard"
    
    def GET(self):
        keys = web.ctx.site.things(query={"type": "/type/library", "limit": 1000})
        libraries = web.ctx.site.get_many(keys)
        libraries.sort(key=lambda lib: lib.name)
        return render_template("libraries/dashboard", libraries, self.get_pending_libraries())
        
    def get_pending_libraries(self):
        docs = web.ctx.site.store.values(type="library", name="current_status", value="pending")
        return [self._create_pending_library(doc) for doc in docs]
            
    def _create_pending_library(self, doc):
        """Creates a library object from store doc.
        """
        doc = dict(doc)
        
        key = doc.pop("_key")
        if not key.startswith("/"):
            key = "/" + key
            
        for k in doc.keys():
            if k.startswith("_"):
                del doc[k]
                
        doc['key'] = key
        doc['type'] = {"key": '/type/library'}
        doc['title'] = doc.get("title", doc['name'])
        return web.ctx.site.new(key, doc)
        
class pending_libraries(delegate.page):
    path = "/(libraries/pending-\d+)"
    
    def GET(self, key):
        doc = web.ctx.site.store.get(key)
        if not doc:
            raise web.notfound()
            
        doc["_key"] = self.generate_key(doc)
            
        page = libraries_dashboard()._create_pending_library(doc)
        return render_template("type/library/edit", page)
        
    def generate_key(self, doc):
        key = "/libraries/" + doc['name'].lower().replace(" ", "_")
        
        _key = key
        count = 1
        while web.ctx.site.get(key) is not None:
            key = "%s_%s" % (_key, count)
            count += 1
        return key
    
    def POST(self, key):
        i = web.input(_method="POST")
        
        if "_delete" in i:
            doc = web.ctx.site.store.get(key)
            if doc:
                doc['current_status'] = "deleted"
                web.ctx.site.store[doc['_key']] = doc
                add_flash_message("info", "The requested library has been deleted.")
                raise web.seeother("/libraries/dashboard")
        
        i._key = web.rstrips(i.key, "/").replace(" ", "_")
        page = libraries_dashboard()._create_pending_library(i)
        
        if web.ctx.site.get(page.key):
            add_flash_message("error", "URL %s is already used. Please choose a different one." % page.key)
            return render_template("type/library/edit", page)
        elif not i.key.startswith("/libraries/"):
            add_flash_message("error", "The key must start with /libraries/.")
            return render_template("type/library/edit", page)
            
        doc = web.ctx.site.store.get(key)
        if doc and "registered_on" in doc:
            page.registered_on = {"type": "/type/datetime", "value": doc['registered_on']}
        
        page._save()
        
        if doc:
            doc['current_status'] = "approved"
            doc['page_key'] = page.key
            web.ctx.site.store[doc['_key']] = doc
        raise web.seeother(page.key)
        
class libraries_register(delegate.page):
    path = "/libraries/register"
    def GET(self):
        return render_template("libraries/add")
        
    def POST(self):
        i = web.input()
        
        seq = web.ctx.site.seq.next_value("libraries")
        
        doc = dict(i)
        doc.update({
            "_key": "libraries/pending-%d" % seq,
            "type": "library",
            "current_status": "pending",
            "registered_on": datetime.datetime.utcnow().isoformat()
        })
        web.ctx.site.store[doc['_key']] = doc
        
        self.sendmail(i.contact_email, 
            render_template("libraries/email_confirmation"))
        
        if config.get("libraries_admin_email"):
            self.sendmail(config.libraries_admin_email,
                render_template("libraries/email_notification", i))
        
        return render_template("libraries/postadd")
        
    def sendmail(self, to, msg, cc=None):
        cc = cc or []
        subject = msg.subject.strip()
        body = web.safestr(msg).strip()
        
        if config.get('dummy_sendmail'):
            print >> web.debug, 'To:', to
            print >> web.debug, 'From:', config.from_address
            print >> web.debug, 'Subject:', subject
            print >> web.debug
            print >> web.debug, body
        else:
            web.sendmail(config.from_address, to, subject=subject, message=body, cc=cc)


class locations(delegate.page):
    path = "/libraries/locations.txt"

    def GET(self):
        libraries = inlibrary.get_libraries()
        web.header("Content-Type", "text/plain")
        return delegate.RawText(render_template("libraries/locations", libraries))

class stats(delegate.page):
    path = "/libraries/stats"

    def GET(self):
        stats  = LoanStats()
        return render_template("libraries/stats", stats);

@web.memoize
def get_admin_couchdb():
    db_url = config.get("admin", {}).get("counts_db")
    return db_url and couchdb.Database(db_url)

class LoanStats:
    def __init__(self):
        self.db = get_admin_couchdb()

    def view(self, viewname, **kw):
        kw['stale'] = 'ok'
        if self.db:
            return self.db.view(viewname, **kw)
        else:
            return web.storage(rows=[])

    def percent(self, value, total):
        if total == 0:
            return 0
        else:
            return (100.0 * value)/total

    def get_summary(self):
        d = web.storage({
            "total_loans": 0,
            "one_hour_loans": 0,
            "expired_loans": 0
        })

        rows = self.view("loans/duration").rows
        if not rows:
            return d

        d['total_loans']  = rows[0].value['count']

        freq = rows[0].value['freq']

        d['one_hour_loans'] = freq.get("0", 0)
        d['expired_loans'] = sum(count for time, count in freq.items() if int(time) >= 14*24)
        return d

    def get_loans_per_day(self, resource_type="total"):
        rows = self.view("loans/loans", group=True).rows
        return [[self.date2timestamp(*row.key)*1000, row.value.get(resource_type, 0)] for row in rows]

    def date2timestamp(self, year, month=1, day=1):
        return time.mktime((year, month, day, 0, 0, 0, 0, 0, 0)) # time.mktime takes 9-tuple as argument

    def date2millis(self, year, month=1, day=1):
        return self.date2timestamp(year, month, day) * 1000

    def get_loan_duration_frequency(self):
        rows = self.view("loans/duration").rows
        if not rows:
            return []

        row = rows[0]
        d = {}
        for time, count in row.value['freq'].items():
            n = 1 + int(time)/24

            # The loan entry gets added to couch only when the loan is deleted in the database, which is probably triggered by a cron job.
            # Even though the max loan duration is 2 weeks, there is a chance that duration is more than 14.
            if n > 14:
                n =15

            d[n] = d.get(n, 0) + count
        return sorted(d.items())

    def get_average_duration_per_month(self):
        """Returns average duration per month."""
        rows = self.view("loans/duration", group_level=2).rows
        minutes_per_day = 60.0 * 24.0
        return [[self.date2timestamp(*row.key)*1000, min(14, row.value['avg']/minutes_per_day)] for row in rows]
        
    def get_average_duration_per_day(self):
        """Returns average duration per day."""
        return [[self.date2millis(*key), value] for key, value in self._get_average_duration_per_day()]
        
    def _get_average_duration_per_day(self):
        """Returns (date, duration-in-days) for each day with duration averaged per day."""
        rows = self.view("loans/duration", group=True).rows
        minutes_per_day = 60.0 * 24.0
        return [[row.key, min(14, row.value['avg']/minutes_per_day)] for row in rows]
        
    def _get_average_duration_per_month(self):
        """Returns (date, duration-in-days) for each day with duration averaged per month."""
        for month, chunk in itertools.groupby(self._get_average_duration_per_day(), lambda x: x[0][:2]):
            chunk = list(chunk)
            avg = sum(v for k, v in chunk) / len(chunk)
            for k, v in chunk:
                yield k, avg
        
    def get_average_duration_per_month(self):
        """Returns (date-in-millis, duration-in-days) for each day with duration averaged per month."""
        return [[self.date2millis(*key), value] for key, value in self._get_average_duration_per_month()]

    def get_popular_books(self, limit=10):
        rows = self.view("loans/books", reduce=False, startkey=["", {}], endkey=[""], descending=True, limit=limit).rows
        counts = [row.key[-1] for row in rows]
        keys = [row.id for row in rows]
        books = web.ctx.site.get_many(keys)
        return zip(books, counts)

    def get_loans_per_book(self, key="", limit=1):
        """Returns the distribution of #loans/book."""
        rows = self.view("loans/books", group=True, startkey=[key], endkey=[key, {}]).rows
        return [[row.key[-1], row.value] for row in rows if row.value >= limit]
        
    def get_loans_per_user(self, key="", limit=1):
        """Returns the distribution of #loans/user."""
        rows = self.view("loans/people", group=True, startkey=[key], endkey=[key, {}]).rows
        return [[row.key[-1], row.value] for row in rows if row.value >= limit]
        
    def get_loans_per_library(self):
        # view contains:
        #   [lib_key, status], 1
        # Need to use group_level=1 and take key[0] to get the library key.
        rows = self.view("loans/libraries", group=True, group_level=1).rows
        names = self._get_library_names()
        return [[names.get(row.key[0], "-"), row.value] for row in rows]
        
    def get_active_loans_of_libraries(self):
        """Returns count of current active loans per library as a dictionary.
        """
        rows = self.view("loans/libraries", group=True).rows
        return dict((row.key[0], row.value) for row in rows if row.key[1] == "active")
        
    def _get_library_names(self):
        return dict((lib.key, lib.name) for lib in inlibrary.get_libraries())
        
@public
def get_active_loans_of_libraries():
    return LoanStats().get_active_loans_of_libraries()
    
def on_loan_created(loan):
    """Adds the loan info to the admin stats database.
    """
    logger.debug("on_loan_created")
    db = get_admin_couchdb()
    
    # The loan key is now changed from uuid to fixed key.
    # Using _key as key for loan stats will result in overwriting previous loans.
    # Using the unique uuid to create the loan key and falling back to _key
    # when uuid is not available.
    key = "loans/" + loan.get("uuid") or loan["_key"]

    t_start = datetime.datetime.utcfromtimestamp(loan['loaned_at'])

    d = {
        "_id": key,
        "book": loan['book'],
        "resource_type": loan['resource_type'],
        "t_start": t_start.isoformat(),
        "status": "active"
    }
    
    library = inlibrary.get_library()
    d['library'] = library and library.key

    if key in db:
        logger.warn("loan document is already present in the stats database: %r", key)
    else:
        db[d['_id']] = d

    yyyy_mm = t_start.strftime("%Y-%m")

    logger.debug("incrementing loan count of %s", d['book'])

    # Increment book loan count
    # Loan count is maintained per month so that it is possible to find popular books per month, year and overall.
    book = db.get(d['book']) or {"_id": d['book']}
    book["loans"][yyyy_mm] = book.setdefault("loans", {}).setdefault(yyyy_mm, 0) + 1
    db[d['book']] = book

    # Increment user loan count
    user_key = loan['user']
    user = db.get(user_key) or {"_id": user_key}
    user["loans"][yyyy_mm] = user.setdefault("loans", {}).setdefault(yyyy_mm, 0) + 1
    db[user_key] = user

def on_loan_completed(loan):
    """Marks the loan as completed in the admin stats database.
    """
    logger.debug("on_loan_completed")
    db = get_admin_couchdb()
    
    # The loan key is now changed from uuid to fixed key.
    # Using _key as key for loan stats will result in overwriting previous loans.
    # Using the unique uuid to create the loan key and falling back to _key
    # when uuid is not available.
    key = "loans/" + loan.get("uuid") or loan["_key"]
    doc = db.get(key)

    t_end = datetime.datetime.utcfromtimestamp(loan['returned_at'])

    if doc:
        doc.update({
            "status": "completed",
            "t_end": t_end.isoformat()
        })
        db[doc['_id']] = doc
    else:
        logger.warn("loan document missing in the stats database: %r", key)

def setup():
    from openlibrary.core import msgbroker

    msgbroker.subscribe("loan-created", on_loan_created)
    msgbroker.subscribe("loan-completed", on_loan_completed)
