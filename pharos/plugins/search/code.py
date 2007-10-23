import web
import stopword

from infogami import utils
from infogami.utils import delegate
from infogami.utils import view, template
from infogami import tdb, config
#from infogami.plugins.wikitemplates import code as wt
import re

render = template.render

#render = view.render.search
#render.search = wt.sitetemplate("search", render.search)
#render.fullsearch = wt.sitetemplate("fullsearch", render.fullsearch)
#wt.register_wiki_template("Search Template", "plugins/search/templates/search.html", "templates/search.tmpl")

#wt.register_wiki_template("Advanced Search Template", "plugins/search/templates/advanced.html", "templates/advanced.tmpl")

import solr_client

solr_server_address = getattr(config, 'solr_server_address', None)
if solr_server_address:
    solr = solr_client.Solr_client(solr_server_address)
else:
    solr = None


class old_search(delegate.page):
    def GET(self, site):
        i = web.input(q=None)
        results = []
        qresults = web.storage(begin=0, total_results=0)
        facets = []
        errortext = None
        if solr is None:
            errortext = 'Solr is not configured.'
        elif not i.q:
            errortext = 'You need to enter some search terms.'
        else:
            try:
                query = i.q.strip()
                offset = int(i.get('offset', '0'))
                qresults = solr.basic_search(query, start=offset)
                facets = solr.facets(solr.basic_query(i.q), maxrows=5000)

                for res in qresults.result_list:
                    if res.startswith('OCA/'):
                        try:
                            t = tdb.Things(oca_identifier=res[4:]).list()[0].name
                            if t not in results: results.append(t)
                        except IndexError:
                            pass
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

solr_fulltext = solr_client.Solr_client(('ia301443', 8983))
solr_pagetext = solr_client.Solr_client(('h7', 8983))
from collapse import collapse_groups
class fullsearch(delegate.page):
    def POST(self, site):
        i = web.input(q=None)
        errortext = None
        out = []

        if i.q:
            q = re.sub('[\r\n]+', ' ', i.q)
            results = solr_fulltext.fulltext_search(q)
            for ocaid in results:
                try:
                    ocat = tdb.Things(oca_identifier=ocaid).list()[0]
                    out.append((ocat,
                                collapse_groups(solr_pagetext.pagetext_search(ocaid, q))))
                except IndexError:
                    pass
        else:
            q = i.q
            errortext = 'You need to enter some search terms.'

        return render.fullsearch(q, out, errortext=errortext)

    GET = POST

# this is just to test exporting python functions to templates
@view.public
def square(n):
    if n != 3:
        raise TypeError, 'whoops'
    return n*n

class Panic(Exception): pass
@view.public
def tpanic(msg,x=0):
    print >> web.debug, ('panic', msg)
    if x:
        raise Panic, msg

import facet_hash
facet_token = view.public(facet_hash.facet_token)

class search(delegate.page):
    def GET(self, site):
        i = web.input(wtitle='',
                      wauthor='',
                      wtopic='',
                      wisbn='',
                      wpublisher='',
                      wdescription='',
                      psort_order='',
                      pfulltext='',
                      ftokens='',
                      fselect=[],
                      q='',
                      )
        results = []
        qresults = web.storage(begin=0, total_results=0)
        facets = []
        errortext = None

        if solr is None:
            errortext = 'Solr is not configured.'

        q0 = filter(bool, [i.q])
        for formfield, searchfield in \
                (('wtitle', 'title'),
                 ('wauthor', 'authors'),
                 ('wtopic', 'subject'),
                 ('wisbn', 'isbn'),
                 ('wpublisher', 'publisher'),
                 ('wdescription', 'description'),
                 ('pfulltext', 'has_fulltext'),
                 ):
            v = i.get(formfield)
            if v:
                q0.append('%s:(%s)'% (searchfield, v))
            # @@
            # @@ need to unpack date range field and sort order here
            # @@
        
        # get list of facet tokens by splitting out comma separated
        # tokens, and remove duplicates.
        def strip_duplicates(seq, init=[]):
            """>>> print strip_duplicates((1,2,3,3,4,9,2,0,3))
            [1, 2, 3, 4, 9, 0]
            >>> print strip_duplicates((1,2,3,3,4,9,2,0,3), [3])
            [1, 2, 4, 9, 0]"""
            fs = set(init)
            return list(t for t in seq if not (t in fs or fs.add(t)))

        # @@
        @view.public
        def removals(x=i.get('remove')):
            return x
        @view.public
        def selections(x=i.get('fselect')):
            return x

        ft_list = strip_duplicates((t for t in i.ftokens.split(',') if t),
                                   (i.get('remove'),))
        # reassemble ftokens string in case it had duplicates
        i.ftokens = ','.join(ft_list)
        
        assert all(re.match('^[a-z]{5,}$', a) for a in ft_list), \
               ('invalid facet token(s) in',ft_list)

        qtokens = ' facet_tokens:(%s)'%(' '.join(ft_list)) if ft_list else ''

        ft_pairs = list((t, solr.facet_token_inverse(t)) for t in ft_list)

        if not q0:
            errortext = 'You need to enter some search terms.'
            return render.advanced_search(i.get('wtitle',''),
                                          qresults,
                                          results,
                                          [],
                                          i.ftokens,
                                          ft_pairs,
                                          errortext=errortext)

        out = []
        i.q = ' '.join(q0)
        try:
            # work around bug in PHP module that makes queries
            # containing stopwords come back empty.
            query = stopword.basic_strip_stopwords(i.q.strip()) + qtokens
            offset = int(i.get('offset', '0') or 0)
            # qresults = solr.advanced_search(query, start=offset)
            qresults = solr.basic_search(query, start=offset)
            facets = solr.facets(query, maxrows=5000)
            results = munch_qresults(qresults.result_list, site)
        except solr_client.SolrError:
            errortext = 'Sorry, there was an error in your search.'

        return render.advanced_search(i.get('q', ''),
                                      qresults,
                                      results, 
                                      facets,
                                      i.ftokens,
                                      ft_pairs,
                                      errortext=errortext)

def munch_qresults(qlist, site):
    results = []
    rset = set()
    def maybe_add(t):
        if t not in rset:
            rset.add(t)
            results.append(t)

    for res in qlist:
        if res.startswith('OCA/'):
            try:
                t = tdb.Things(oca_identifier=res[4:]).list()[0].name
                maybe_add(t)
            except (IndexError, AttributeError):
                pass
        else:
            maybe_add(res)

    return tdb.withNames(results, site)
