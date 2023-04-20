"""Module to manage OL loan stats.

Unlike other parts of openlibrary, this modules talks to the database directly.
"""
import logging
import requests
from urllib.parse import urlencode
from infogami import config


logger = logging.getLogger(__name__)


class LoanStats:
    def __init__(self):
        self.base_url = "http://%s/solr" % config.get("stats_solr")

    def solr_select(self, params):
        fq = params.get("fq", [])
        if not isinstance(fq, list):
            fq = [fq]
        params['fq'] = fq

        logger.info("SOLR query %s", params)

        q = urlencode(params, doseq=True)
        url = self.base_url + "/select?" + q
        logger.info("requests.get(%s).json()", url)
        return requests.get(url).json()

    def get_last_updated(self):
        params = {"wt": "json", "q": "*:*", "rows": 1, "sort": "last_updated_dt desc"}
        response = self.solr_select(params)
        try:
            return response['response']['docs'][0]['last_updated_dt']
        except (IndexError, KeyError):
            # if last update timestamp is not found in solr,
            # use year 2000 to consider all docs
            return "2000-01-01T00:00:00Z"
