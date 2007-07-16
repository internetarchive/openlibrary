import web

from infogami import utils
from infogami.utils import delegate
from infogami.utils import view
from infogami import tdb, config
from infogami.plugins.wikitemplates import code as wt

render = view.render.search
render.search = wt.sitetemplate("search", render.search)
render.fullsearch = wt.sitetemplate("fullsearch", render.fullsearch)
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
        results = []
        qresults = web.storage(begin=0, total_results=0)
        facets = []
        errortext = None
        if solr is None:
            errortext = 'Solr is not configured.'
        elif 'q' in i:
            if i.q == '':
                errortext = 'You need to enter some search terms.'
            else:
                try:
                    offset = int(i.get('offset', '0'))
                    qresults = solr.basic_search(i.q, start=offset)
                    facets = solr.facets(solr.basic_query(i.q), maxrows=5000)

                    for res in qresults.result_list:
                        if res.startswith('OCA/'):
                            t = tdb.Things(oca_identifier=res[4:]).list()[0].name
                            if t not in results: results.append(t)
                        else:
                            if res not in results: results.append(res)
                    results = tdb.withNames(results, site)
                    for x in results:
                        if x.type.name not in ['edition', 'type/edition'] or not x.get('title'):
                            results.remove(x)
                except solr_client.SolrError:
                    errortext = 'Sorry, there was an error in your search.'

        return render.search(i.get('q', ''),
                             qresults,
                             results, 
                             facets,
                             errortext=errortext)

solr_fulltext = solr_client.Solr_client(('pharosdb', 8983))
solr_pagetext = solr_client.Solr_client(('h7', 8983))
class fullsearch(delegate.page):
    def GET(self, site):
        i = web.input()
        results = solr_fulltext.fulltext_search(i.q)

        out = []
        for ocaid in results:
            ocat = tdb.Things(oca_identifier=ocaid).list()[0]
            out.append((ocat, solr_pagetext.pagetext_search(ocaid, i.q)))

        return render.fullsearch(i.q, out)
