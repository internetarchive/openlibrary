"""Module to manage OL loan stats.

Unlike other parts of openlibrary, this modules talks to the database directly.
"""
import re
import time
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
        self._library_titles = None
        self._facet_counts = None

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
            params['fq'].append(self._get_subject_filter(self.solrescape(self.subject)))

        logger.info("SOLR query %s", params)

        q = urllib.urlencode(params, doseq=True)
        url = self.base_url + "/select?" + q
        logger.info("urlopen %s", url)
        response = urllib.urlopen(url).read()
        return simplejson.loads(response)

    def solrescape(self, text):
        return re_solrescape.sub(r'\\\1', text)

    def _get_subject_filter(self, subject):
        if ":" in subject:
            type, subject = subject.split(":", 1)
        else:
            type = "subject"
        key = type + "_key"
        return "%s:%s" % (key, subject)

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
        return dict((name, web.group(counts, 2)) for name, counts in response['facet_counts']['facet_fields'].items())

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
            self._facet_counts = dict((name, web.group(counts, 2)) for name, counts in response['facet_counts']['facet_fields'].items())
        return self._facet_counts

    def get_loans_per_day(self, resource_type="total"):
        params = {
            "wt": "json",
            "fq": ["type:stats"],
            "q": "*:*", 
            "rows": 0,
            "facet": "on",
            "facet.mincount": 1,
            "facet.field": ['start_day_s']
        }
        if resource_type != 'total':
            params['fq'].append("resource_type_s:" + resource_type)

        response = self.solr_select(params)
        counts0 = response['facet_counts']['facet_fields']['start_day_s']
        day_facet = web.group(counts0, 2)
        return [[self.date2timestamp(*self.parse_date(day))*1000, count] for day, count in day_facet]

    def get_loans_per_type(self):
        rows = self.get_facet_counts("resource_type_s")
        return [{"label": row.title, "data": row.count} for row in rows]

    def get_facet_counts(self, name, limit=20):
        facets = list(self.solr_select_facet(name))[:limit]
        return [self.make_facet(name, key, count) for key, count in facets]

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

    def date2timestamp(self, year, month=1, day=1):
        return time.mktime((year, month, day, 0, 0, 0, 0, 0, 0)) # time.mktime takes 9-tuple as argument

    def date2millis(self, year, month=1, day=1):
        return self.date2timestamp(year, month, day) * 1000

    def parse_date(self, date):
        yyyy, mm, dd = date.split("-")
        return int(yyyy), int(mm), int(dd)
