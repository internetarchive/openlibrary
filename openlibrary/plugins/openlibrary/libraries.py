"""Controller for /libraries.
"""
import time
import logging
import datetime
import itertools
from cStringIO import StringIO
import csv
import simplejson

import web
from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template, add_flash_message, public
from openlibrary.core import inlibrary, statsdb, geo_ip
from openlibrary import accounts
from openlibrary.core.iprange import find_bad_ip_ranges

logger = logging.getLogger("openlibrary.libraries")

class libraries(delegate.page):
    def GET(self):
        return render_template("libraries/index", get_libraries_by_country())

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

            user = accounts.get_current_user()
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

#source: https://en.wikipedia.org/wiki/List_of_U.S._state_abbreviations
US_STATE_CODES = """
AL  01  Alabama
AK  02  Alaska
AZ  04  Arizona
AR  05  Arkansas
CA  06  California
CO  08  Colorado
CT  09  Connecticut
DE  10  Delaware
FL  12  Florida
GA  13  Georgia
HI  15  Hawaii
ID  16  Idaho
IL  17  Illinois
IN  18  Indiana
IA  19  Iowa
KS  20  Kansas
KY  21  Kentucky
A   22  Louisiana
ME  23  Maine
MD  24  Maryland
MA  25  Massachusetts
MI  26  Michigan
MN  27  Minnesota
MS  28  Mississippi
MO  29  Missouri
MT  30  Montana
NE  31  Nebraska
NV  32  Nevada
NH  33  New Hampshire
NJ  34  New Jersey
NM  35  New Mexico
NY  36  New York
NC  37  North Carolina
ND  38  North Dakota
OH  39  Ohio
OK  40  Oklahoma
OR  41  Oregon
PA  42  Pennsylvania
RI  44  Rhode Island
SC  45  South Carolina
SD  46  South Dakota
TN  47  Tennessee
TX  48  Texas
UT  49  Utah
VT  50  Vermont
VA  51  Virginia
WA  53  Washington
WV  54  West Virginia
WI  55  Wisconsin
WY  56  Wyoming
"""
def parse_state_codes():
    tokens = (line.split(None, 2) for line in US_STATE_CODES.strip().splitlines())
    return dict((code, name) for code, _, name in tokens)

US_STATE_CODES_DICT = parse_state_codes()

@public
def group_branches_by_state(branches):
    d = {}
    for branch in branches:
        state = branch.state.strip()
        if state.upper() in US_STATE_CODES_DICT:
            state = US_STATE_CODES_DICT[state.upper()]
        d.setdefault(state, []).append(branch)
    return d

def get_libraries_by_country():
    libraries = inlibrary.get_libraries()
    d = {}
    
    usa = "United States of America"
    aliases = {
        "US": usa,
        "U.S.": usa,
        "USA": usa,
        "U.S.A.": usa,
        "United States": usa,
        "UK": "United Kingdom"
    }
    for lib in libraries:
        for branch in lib.get_branches():
            country = aliases.get(branch.country.strip(), branch.country).strip()
            branch.library = lib
            d.setdefault(country, []).append(branch)
    return d

class libraries_dashboard(delegate.page):
    path = "/libraries/dashboard"

    def GET(self):
        keys = web.ctx.site.things(query={"type": "/type/library", "limit": 10000})
        libraries = web.ctx.site.get_many(keys)
        libraries.sort(key=lambda lib: lib.name.lstrip('The '))
        return render_template("libraries/dashboard", libraries, self.get_pending_libraries())

    def get_pending_libraries(self):
        docs = web.ctx.site.store.values(type="library", name="current_status", value="pending", limit=10000)
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
        doc = dict(i)
        errors = {}
        if not doc.get('name'):
            errors['name'] = 'name is a required field'
        addresses = doc.get('addresses', '').strip()
        if addresses:
            for line in addresses.splitlines():
                tokens = line.split('|')
                if len(tokens) != 9:
                    errors['addresses'] = 'address field is invalid'
                    break
                latlong = tokens[8]
                if ',' not in latlong or len(latlong.split(',')) != 2:
                    errors['addresses'] = 'Lat, Long is invalid'
                    break
        else:
            errors['addresses'] = 'addresses is a required field'

        ip_ranges = doc.get('ip_ranges', '').strip()
        if ip_ranges:
            bad = find_bad_ip_ranges(ip_ranges)
            if bad:
                errors['ip_ranges'] = 'Invalid IP range(s): ' + '; '.join(bad)
        else:
            errors['ip_ranges'] = 'IP ranges is a required field'

        if errors:
            return render_template("libraries/add", errors)

        seq = web.ctx.site.seq.next_value("libraries")

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
        raise web.seeother("/stats/lending")

class stats_per_library(delegate.page):
    path = "/libraries/stats/(.*).csv"

    def GET(self, libname):
        key = "/libraries/" + libname
        lib = web.ctx.site.get(key)
        if not lib:
            raise web.notfound()

        rows = lib.get_loans_per_day("total")        

        dates = [self.to_datestr(row[0]) for row in rows]
        total = [str(row[1]) for row in rows]
        pdf = [str(row[1]) for row in lib.get_loans_per_day("pdf")]
        epub = [str(row[1]) for row in lib.get_loans_per_day("epub")]
        bookreader = [str(row[1]) for row in lib.get_loans_per_day("bookreader")]

        fileobj = StringIO()
        writer = csv.writer(fileobj)
        writer.writerow(["Date", "Total Loans", "PDF Loans", "ePub Loans", "Bookreader Loans"])
        writer.writerows(zip(dates, total, pdf, epub, bookreader))

        return delegate.RawText(fileobj.getvalue(), content_type="application/csv")

    def to_datestr(self, millis):
        t = time.gmtime(millis/1000)
        return "%04d-%02d-%02d" % (t.tm_year, t.tm_mon, t.tm_mday)

@web.memoize


@public
def on_loan_created_statsdb(loan):
    """Adds the loan info to the stats database.
    """
    key = _get_loan_key(loan)
    t_start = datetime.datetime.utcfromtimestamp(loan['loaned_at'])
    d = {
        "book": loan['book'],
        "identifier": loan['ocaid'],
        "resource_type": loan['resource_type'],
        "t_start": t_start.isoformat(),
        "status": "active"
    }
    library = inlibrary.get_library()
    d['library'] = library and library.key
    d['geoip_country'] = geo_ip.get_country(web.ctx.ip)
    statsdb.add_entry(key, d)

def on_loan_completed_statsdb(loan):
    """Marks the loan as completed in the stats database.
    """
    key = _get_loan_key(loan)
    t_start = datetime.datetime.utcfromtimestamp(loan['loaned_at'])
    t_end = datetime.datetime.utcfromtimestamp(loan['returned_at'])
    d = {
        "book": loan['book'],
        "identifier": loan['ocaid'],
        "resource_type": loan['resource_type'],
        "t_start": t_start.isoformat(),
        "t_end": t_end.isoformat(),
        "status": "completed",
    }
    old = statsdb.get_entry(key)
    if old:
        olddata = simplejson.loads(old.json)
        d = dict(olddata, **d)
    statsdb.update_entry(key, d)


def _get_loan_key(loan):
    # The loan key is now changed from uuid to fixed key.
    # Using _key as key for loan stats will result in overwriting previous loans.
    # Using the unique uuid to create the loan key and falling back to _key
    # when uuid is not available.
    return "loans/" + loan.get("uuid") or loan["_key"]

def setup():
    from openlibrary.core import msgbroker
    msgbroker.subscribe("loan-created", on_loan_created_statsdb)
    msgbroker.subscribe("loan-completed", on_loan_completed_statsdb)
