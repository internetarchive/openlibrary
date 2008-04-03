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

solr_fulltext = solr_client.Solr_client(('ia301443', 8983))
# solr_pagetext = solr_client.Solr_client(('h7', 8983))
# fulltext and pagetext are on the same server now
solr_pagetext = solr_client.Solr_client(('ia301443', 8983))

from collapse import collapse_groups
class fullsearch(delegate.page):
    def POST(self, site):
        errortext = None
        out = []
        q = web.input(q=None).q

        if not q:
            errortext='you need to enter some search terms'
            return render.fullsearch(q, out, errortext)

        try:
            q = re.sub('[\r\n]+', ' ', q).strip()
            results = solr_fulltext.fulltext_search(q)
            for ocaid in results:
                try:
                    ocat = tdb.Things(oca_identifier=ocaid).list()[0]
                    out.append((ocat,
                                collapse_groups(solr_pagetext.pagetext_search(ocaid, q))))
                except IndexError:
                    pass
        except IOError, e:
            errortext = 'fulltext search is temporarily unavailable (%s)' % \
                        str(e)

        return render.fullsearch(q, out, errortext=errortext)

    GET = POST

import facet_hash
facet_token = view.public(facet_hash.facet_token)

class DebugException(Exception): pass

class search(delegate.page):
    def POST(self):
        i = web.input(wtitle='',
                      wauthor='',
                      wtopic='',
                      wisbn='',
                      wpublisher='',
                      wdescription='',
                      psort_order='',
                      pfulltext='',
                      ftokens=[],
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
        # tokens, and remove duplicates.  Also remove anything in the
        # initial set `init'.
        def strip_duplicates(seq, init=[]):
            """>>> print strip_duplicates((1,2,3,3,4,9,2,0,3))
            [1, 2, 3, 4, 9, 0]
            >>> print strip_duplicates((1,2,3,3,4,9,2,0,3), [3])
            [1, 2, 4, 9, 0]"""
            fs = set(init)
            return list(t for t in seq if not (t in fs or fs.add(t)))

        # we use multiple tokens fields in the input form so we can support
        # date_range and fulltext_only in advanced search, and can add
        # more like that if needed.
        tokens2 = ','.join(i.ftokens)
        ft_list = strip_duplicates((t for t in tokens2.split(',') if t),
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
            results = munch_qresults(qresults.result_list)
        except solr_client.SolrError:
            errortext = 'Sorry, there was an error in your search.'

        return render.advanced_search(i.get('q', ''),
                                      qresults,
                                      results, 
                                      facets,
                                      i.ftokens,
                                      ft_pairs,
                                      errortext=errortext)

    GET = POST

def munch_qresults(qlist):
    results = []
    rset = set()

    # this is so we can remove duplicates from qlist while preserving
    # its original order
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

    # somehow the leading / got stripped off the book identifiers during some
    # part of the search import process.  figure out where that happened and
    # fix it later.  for now, just put the slash back.
    def restore_slash(book):
        if not book.startswith('/'): return '/'+book
        return book

    return [web.ctx.site.get(restore_slash(r)) for r in results]
