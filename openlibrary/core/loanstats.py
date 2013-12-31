"""Module to manage OL loan stats.

Unlike other parts of openlibrary, this modules talks to the database directly.
"""
import re
import time
import datetime
import urllib
import logging
import simplejson
import web
from infogami import config
from . import inlibrary

logger = logging.getLogger(__name__)

re_solrescape = re.compile(r'([&|+\-!(){}\[\]^"~*?:])')

class LoanStats:
    def __init__(self, region=None, library=None, collection=None, subject=None):
        self.base_url = "http://%s/solr" % config.get("stats_solr")
        self.region = region
        self.library = library
        self.collection = collection
        self.subject = subject
        self.time_period = None
        self.resource_type = None

        self._library_titles = None
        self._facet_counts = None
        self._total_loans = None

    def get_total_loans(self):
        # populate total loans
        self._get_all_facet_counts()
        return self._total_loans

    def solr_select(self, params):
        fq = params.get("fq", [])
        if not isinstance(fq, list):
            fq = [fq]
        params['fq'] = fq
        if self.region:
            params['fq'].append("region_s:" + self.solrescape(self.region))
        if self.library:
            params['fq'].append("library_s:" + self.solrescape(self.library))

        if self.collection:
            params['fq'].append("ia_collections_id:" + self.solrescape(self.collection))

        if self.subject:
            params['fq'].append(self._get_subject_filter(self.subject))

        if self.time_period:
            start, end = self.time_period
            def solrtime(t): 
                return t.isoformat() + "Z"
            params['fq'].append("start_time_dt:[%s TO %s]" % (solrtime(start), solrtime(end)))

        if self.resource_type:
            params['fq'].append("resource_type_s:%s" % self.resource_type)

        logger.info("SOLR query %s", params)

        q = urllib.urlencode(params, doseq=True)
        url = self.base_url + "/select?" + q
        logger.info("urlopen %s", url)
        response = urllib.urlopen(url).read()
        return simplejson.loads(response)

    def solrescape(self, text):
        return re_solrescape.sub(r'\\\1', text)

    def _get_subject_filter(self, subject):
        # subjects are stored as subject_key field as values like:
        # ["subject:fiction", "subject:history", "place:england"] 
        # etc.
        if ":" in subject:
            type, subject = subject.split(":", 1)
        else:
            type = "subject"
        return "subject_key:%s\\:%s" % (type, self.solrescape(subject))

    def solr_select_facet(self, facet_field):
        facet_counts = self._get_all_facet_counts()
        return facet_counts[facet_field]

    def _run_solr_facet_query(self, facet_fields, facet_limit=None):
        params = {
            "wt": "json",
            "fq": "type:stats", 
            "q": "*:*", 
            "rows": 0,
            "facet": "on",
            "facet.mincount": 1,
            "facet.field": facet_fields
        }
        if facet_limit:
            params["facet.limit"] = facet_limit

        response = self.solr_select(params)
        return dict((name, list(web.group(counts, 2))) for name, counts in response['facet_counts']['facet_fields'].items())

    def _get_all_facet_counts(self):
        if not self._facet_counts:
            facets = [
                "library_s","region_s",
                "ia_collections_id", "sponsor_s", "contributor_s",
                "book_key_s", "author_keys_id", "resource_type_s",
                "subject_facet", "place_facet", "person_facet", "time_facet"]

            params = {
                "wt": "json",
                "fq": "type:stats", 
                "q": "*:*", 
                "rows": 0,
                "facet": "on",
                "facet.mincount": 1,
                "facet.field": facets,
                "facet.limit": 20
            }
            response = self.solr_select(params)
            self._total_loans = response['response']['numFound']
            self._facet_counts = dict((name, web.group(counts, 2)) for name, counts in response['facet_counts']['facet_fields'].items())
        return self._facet_counts

    def get_last_updated(self):
        params = {
            "wt": "json",
            "q": "*:*",
            "rows": 1, 
            "sort": "last_updated_dt desc"
        }
        response = self.solr_select(params)
        try:
            return response['response']['docs'][0]['last_updated_dt']
        except (IndexError, KeyError):
            # if last update timestamp is not found in solr,
            # use year 2000 to consider all docs
            return "2000-01-01T00:00:00Z"

    def get_loans_per_day(self, resource_type="total"):
        params = {
            "wt": "json",
            "fq": ["type:stats"],
            "q": "*:*", 
            "rows": 0,
            "facet": "on",
            "facet.mincount": 1,
            "facet.limit": 100000, # don't limit 
            "facet.field": ['start_day_s']
        }
        if resource_type != 'total':
            params['fq'].append("resource_type_s:" + resource_type)

        response = self.solr_select(params)
        counts0 = response['facet_counts']['facet_fields']['start_day_s']
        day_facet = web.group(counts0, 2)
        return sorted([[self.datestr2millis(day), count] for day, count in day_facet])

    def get_loans_per_type(self):
        rows = self.get_facet_counts("resource_type_s")
        return [{"label": row.title, "data": row.count} for row in rows]

    def get_facet_counts(self, name, limit=20):
        facets = list(self.solr_select_facet(name))[:limit]
        return [self.make_facet(name, key, count) for key, count in facets]

    def get_loans_by_published_year(self):
        d = self._run_solr_facet_query("publish_year")['publish_year']
        # strip bad years
        current_year = datetime.date.today().year
        min_year = 1800
        return [[int(y), count] for y, count in d if min_year < int(y) <= current_year]

    def get_loan_durations(self):
        params = {
            "wt": "json",
            "q": "*:*", 
            "rows": 0,
            "facet": "on",
            "facet.field": ['duration_hours_i']
        }
        response = self.solr_select(params)
        counts = [[int(hr), count] for hr, count in web.group(response['facet_counts']['facet_fields']['duration_hours_i'], 2)]
        one_hour = sum(count for hr, count in counts if hr == 0)
        one_day = sum(count for hr, count in counts if 1 <= hr < 24)
        one_week = sum(count for hr, count in counts if 24 <= hr < 24*7)
        two_week = sum(count for hr, count in counts if 24*7 <= hr < 24*14)
        expired = sum(count for hr, count in counts if 24*14 <= hr)
        return [
            {"label": "Less than one hour", "data": one_hour}, 
            {"label": "Less than one day", "data": one_day}, 
            {"label": "Less than one week", "data": one_week}, 
            {"label": "More than a week", "data": two_week}, 
            {"label": "Loan expired", "data": expired}]

    def make_facet(self, name, key, count):
        if name == "library_s":
            title = self._get_library_title(key)
            slug = key
        elif name == "region_s":
            title = key.upper()
            slug = key
        elif name == "book_key_s":
            # XXX-Anand: Optimize this by pre loading all books
            book = web.ctx.site.get(key)
            title = book and book.title or "untitled"
            slug = key
        elif name == "author_keys_id":
            # XXX-Anand: Optimize this by pre loading all the authors
            author = web.ctx.site.get(key)
            title = author and author.name or "unnamed"
            slug = key
        elif name in ["subject_facet", "person_facet", "place_facet", "time_facet"]:
            title = key

            prefix = name.replace("_facet", "") + ":"
            if prefix == "subject:":
                prefix = ""

            slug = key.lower().replace(" ", "_").replace(",", "")
        else:
            title = key
            slug = key.lower().replace(" ", "_")
        return web.storage(title=title, count=count, slug=slug)

    def _get_library_title(self, key):
        if self._library_titles is None:
            libraries = inlibrary.get_libraries()
            self._library_titles = dict((lib.key.split("/")[-1], lib.title) for lib in libraries)
        return self._library_titles.get(key, key)

    def date2millis(self, date):
        return time.mktime(date.timetuple()) * 1000

    def parse_date(self, datestr):
        yyyy, mm, dd = datestr.split("-")
        return datetime.date(int(yyyy), int(mm), int(dd))

    def datestr2millis(self, datestr):
        return self.date2millis(self.parse_date(datestr))
