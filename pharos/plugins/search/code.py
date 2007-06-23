import web

from infogami import utils
from infogami.utils import delegate
from infogami.utils import view
from infogami import tdb, config
from infogami.plugins.wikitemplates import code as wt

render = view.render.search
render.search = wt.sitetemplate("search", render.search)
wt.register_wiki_template("Search Template", "plugins/search/templates/search.html", "templates/search.tmpl")

import solr_client

solr_server_address = getattr(config, 'solr_server_address', None)
if solr_server_address:
    solr = solr_client.Solr_client(solr_server_address)
else:
    solr = None

class search(delegate.page):
    def GET(self, site):
        i = web.input()
        if solr is None:
            view.set_error('Solr is not configured.')
            results = []
        elif 'q' in i:
            if i.q == '':
                view.set_error('You need to enter some search terms.')
                results = []
            else:
                try:
                    results = []
                    offset = int(i.get('offset', '0'))
                    qresults = solr.basic_search(i.q, start=offset)

                    for res in qresults.result_list:
                        if res.startswith('OCA/'):
                            t = tdb.Things(oca_identifier=res[4:]).list()[0].name
                            if t not in results: results.append(t)
                        else:
                            if res not in results: results.append(res)
                    results = tdb.withNames(results, site)
                    for x in results:
                        if x.type.name != 'edition' or not x.get('title'): results.remove(x)
                except solr_client.SolrError:
                    view.set_error('Sorry, there was an error in your search.')
                    results = []
	else:
	    results = []

	return render.search(i.get('q', ''),
                             qresults,
                             results)
