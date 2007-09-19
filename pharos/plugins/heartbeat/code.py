import web
from infogami.utils import delegate
from infogami.core import db
import plugins.search.code as search

class heartbeat(delegate.page):
    def GET(self, site):
        assert db.get_version(site, '').title == "Open Library"
        assert 'b/Political_Fictions' in search.solr.search('political fictions didion').result_list
        print "HEALTHY"
