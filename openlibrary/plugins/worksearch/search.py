"""Search utilities.
"""
from openlibrary.utils.solr import Solr
from infogami import config


def get_solr():
    base_url = config.plugin_worksearch.get('solr_base_url')
    return Solr(base_url)
