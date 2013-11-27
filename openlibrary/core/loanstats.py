"""Module to manage OL loan stats.

Unlike other parts of openlibrary, this modules talks to the database directly.
"""
import web
import time
import urllib
import simplejson

class LoanStats:
    def __init__(self):
        self.base_url = "http://localhost:8983/solr"

    def solr_select(self, params):
        q = urllib.urlencode(params, doseq=True)
        url = self.base_url + "/select?" + q
        response = urllib.urlopen(url).read()
        return simplejson.loads(response)

    def solr_select_facet(self, facet_field):
        params = {
            "wt": "json",
            "fq": "type:stats", 
            "q": "*:*", 
            "rows": 0,
            "facet": "on",
            "facet.mincount": 1,
            "facet.field": facet_field,
        }
        response = self.solr_select(params)
        facet = web.group(response['facet_counts']['facet_fields'][facet_field], 2)
        return facet

    def get_loans_per_day(self, resource_type="total"):
        day_facet = self.solr_select_facet('start_day_s')
        return [[self.date2timestamp(*self.parse_date(day))*1000, count] for day, count in day_facet]

    def get_facet_counts(self, name, limit=20):
        return list(self.solr_select_facet(name))[:limit]

    def date2timestamp(self, year, month=1, day=1):
        return time.mktime((year, month, day, 0, 0, 0, 0, 0, 0)) # time.mktime takes 9-tuple as argument

    def date2millis(self, year, month=1, day=1):
        return self.date2timestamp(year, month, day) * 1000

    def parse_date(self, date):
        yyyy, mm, dd = date.split("-")
        return int(yyyy), int(mm), int(dd)
