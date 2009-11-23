#!/usr/bin/python
# from __future__ import with_statement
from urllib import quote_plus, urlopen
from xml.etree.cElementTree import ElementTree
from cStringIO import StringIO
import os, re
from collections import defaultdict
import cgi
import web
import simplejson
from facet_hash import facet_token
import pdb

php_location = "/petabox/setup.inc"

# server_addr = ('pharosdb.us.archive.org', 8983)

# Solr search client; fancier version will have multiple persistent
# connections, etc.

solr_server_addr = ('pharosdb.us.archive.org', 8983)
solr_server_addr = ('h02.us.archive.org', 8993)
# solr_server_addr = ('127.0.0.1', 8983)

default_facet_list = ('has_fulltext', 
                      'authors',
                      'subjects',
                      'facet_year',
                      'language',
                      'language_code',
                      'languages',
                      'publishers',
                      )
                      
class PetaboxQueryProcessor:
    """Utility to expand search query using petabox php script."""
    def __init__(self):
        self.cache = {}
        
    def process(self, query):
        if query in self.cache:
            return self.cache[query]

        # this hex conversion is to defeat attempts at shell or PHP code injection
        # by including escape characters, quotes, etc. in the query.
        qhex = query.encode('hex')

        f = os.popen("""php -r 'require_once("%s");
                                 echo Search::querySolr(pack("H*", "%s"),
                                 false,
                                 array("title"=>100,
                                       # "description"=>0.000,
                                       "authors"=>15,
                                       "subjects"=>10,
                                       "language"=>10,
                                       "text"=>1,
                                       "fulltext"=>1));'""" %
                     (php_location, qhex))
        aq = f.read()
        if aq and aq[0] == '\n':
            raise SolrError, ('invalid response from basic query conversion', aq, php_location)
            
        self.cache[query] = aq
        return aq
        
class SimpleQueryProcessor:
    """Alternate query processor to be used when petabox php script is unavailable. To be used in development.
    
        >>> SimpleQueryProcessor().process("hello")
        '(title:hello^100 OR authors:hello^15 OR subjects:hello^10 OR language:hello^10 OR text:hello^1 OR fulltext:hello^1)'
        >>> SimpleQueryProcessor().process("hello world") #doctest: +NORMALIZE_WHITESPACE
        '(title:hello^100 OR authors:hello^15 OR subjects:hello^10 OR language:hello^10 OR text:hello^1 OR fulltext:hello^1)
         (title:world^100 OR authors:world^15 OR subjects:world^10 OR language:world^10 OR text:world^1 OR fulltext:world^1)'
    """
    def process(self, query):
        query = web.utf8(query)
        tokens = query.split(' ')
        return " ".join(self.process_token(t) for t in tokens)
        
    def process_token(self, token):
        return '(title:%s^100 OR authors:%s^15 OR subjects:%s^10 OR language:%s^10 OR text:%s^1 OR fulltext:%s^1)' % (token, token, token, token, token, token)

def create_query_processor(type):
    if type == 'simple':
        return SimpleQueryProcessor()
    else:
        return PetaboxQueryProcessor()

class SolrError(Exception): pass

import traceback                        # @@

def ocaid_to_olid(ocaid):
    return web.ctx.site.things(type='/type/edition',
                               ocaid=ocaid)

class Solr_result(object):
    def __init__(self, result_xml):
        et = ElementTree()
        try:
            w = result_xml.encode('utf-8')
            def tx(a): return (type(a), len(a))
            et.parse(StringIO(w))
        except SyntaxError, e:
            ptb = traceback.extract_stack()
            raise SolrError, (e, result_xml, traceback.format_list(ptb))
        range_info = et.find('info').find('range_info')

        def gn(tagname):
            return int(range_info.findtext(tagname))
        self.total_results = gn('total_nbr')
        self.begin = gn('begin')
        self.end = gn('end')
        self.results_this_page = gn('contained_in_this_set')

        self.result_list = list(str(a.text) \
                                for a in et.getiterator('identifier'))
        
# rewrite of solr result class, to use python or json format result
class SR2(Solr_result):
    def __init__(self, result_json):
        try:
            e = simplejson.loads(result_json)
            # h = e['responseHeader']
            r = e['response']
            self.total_results = r['numFound']
            self.begin = r['start']
            self.end = self.begin + len(r['docs'])
            self.contained_in_this_set = len(r['docs'])
            self.result_list = list(d['identifier'] for d in r['docs'])
            self.raw_results = r['docs']
        except Exception, e:
            ptb = traceback.extract_stack()
            raise SolrError, (e, result_json, traceback.format_list(ptb))
            
# Solr search client; fancier version will have multiple persistent
# connections, etc.
class Solr_client(object):
    def __init__(self,
                 server_addr = solr_server_addr,
                 shards = [],
                 pool_size = 1):
        self.server_addr = server_addr
        self.shards = shards
        
        self.query_processor = PetaboxQueryProcessor()

        # for caching expanded query strings
        self._cache = {} 

    def __query_fmt(self, query, **attribs):
        # rows=None, start=None, wt=None, sort=None):
        fshards = ','.join('%s:%s/solr'%(host,port)
                           for host,port in self.shards)
        ax = list((k,v) for k,v in attribs.items() if v is not None)
        if fshards:
            ax.append(('shards', fshards))

        q = [quote_plus(query)] + ['%s=%s'%(k, quote_plus(str(v))) \
                       for k,v in ax]
        r = '&'.join(q)
        # print >> web.debug, "* query fmt: returning (%r)"% r
        return r
    
    @staticmethod
    def prefix_query(prefix, query):
        if '"' in query:
            query = prefix + ':' + query
        else:
            query = ' '.join(prefix + ':' + x for x in query.split(' '))
        return query

    def _prefix_query(self, prefix, query):
        return Solr_client.prefix_query(prefix, query)

    def facet_token_inverse(self, *a,**k):
        r = self.Xfacet_token_inverse(*a,**k)
        return r

    def Xfacet_token_inverse(self,
                            token,
                            facet_list = default_facet_list):
        # for now, just pull this straight from the SE
        # need to add an LRU cache for performance.  @@

        if not re.match('^[a-z]+$', token):
            raise SolrError, 'invalid facet token'
        m = simplejson.loads(self.raw_search('facet_tokens:%s'% token,
                                             rows=1, wt='json'))
        facet_set = set(facet_list)
        for d in m['response']['docs']:
            for k,vx in d.iteritems():
                kfs = k in facet_set
                # if not kfs: continue
                vvx = {str:(vx,), list:vx}.get(type(vx),())
                for v in map(unicode, vvx):
                    if facet_token(k,v) == token:
                        return (k,v)
        return None

    def isearch(self, query, loc=0):
        # iterator interface to search
        while True:
            s = search(self, query, start=loc)
            if len(s) == 0: return
            loc += len(s)
            for y in s:
                if not y.startswith('OCA/'):
                    yield y
                    
    def search(self, query, **params):
        # advanced search: directly post a Solr search which uses fieldnames etc.        
        # return list of document id's
        assert type(query) == str

        server_url = 'http://%s:%d/solr/select' % self.server_addr
        query_url = '%s?q=%s&wt=json&fl=*'% \
            (server_url, self.__query_fmt(query, **params))

        try:
            ru = urlopen(query_url)
            py = ru.read()
            ru.close()
        except IOError:
            raise SolrError, "Search temporarily unavailable, please try later"
        return SR2(py)

    advanced_search = search

    def fulltext_search(self, query, rows=None, start=None):
        """Does an advanced search on fulltext:blah.
        You get back a pair (x,y) where x is the total # of hits
        and y is a list of identifiers like ["foo", "bar", etc.]"""
        
        query = self._prefix_query('fulltext', query)
        result_list = self.raw_search(query, rows=rows, start=start)
        e = ElementTree()
        try:
            e.parse(StringIO(result_list))
        except SyntaxError, e:
            raise SolrError, e

        total_nbr_text = e.find('info/range_info/total_nbr').text
        # total_nbr_text = e.find('result').get('numFound')  # for raw xml
        total_nbr = int(total_nbr_text) if total_nbr_text else 0

        out = []
        for r in e.getiterator('hit'):
            for d in r.find('metadata'):
                for x in list(d.getiterator()):
                    if x.tag == "identifier":
                        xid = unicode(x.text).encode('utf-8')
                        if xid.startswith('OCA/'):
                            xid = xid[4:]
                        elif xid.endswith('.txt'):
                            xid = xid.split('/')[-1].split('_')[0]
                        elif xid.endswith('_ZZ'):
                            xid = xid[:-3]
                        out.append(xid)
                        break
        return (total_nbr, out)
                    

    def pagetext_search(self, locator, query, rows=None, start=None):
        """Does an advanced search on
               pagetext:blah locator:identifier
        where identifier is one of the id's from fulltext search.
        You get back a list of page numbers like [21, 25, 39]."""
        
        def extract(page_id):
            """A page id is something like
            'adventsuburbanit00butlrich_0065.djvu',
            which this function extracts asa a locator and
            a leaf number ('adventsuburbanit00butlrich', 65). """
            
            g = re.search('(.*)_(\d{4})\.djvu$', page_id)
            a,b = g.group(1,2)
            return a, int(b)
        
        # try using qf= parameter here and see if it gives a speedup. @@
        # pdb.set_trace()
        query = self._prefix_query('pagetext', query)
        page_hits = self.raw_search(query,
                                    fq='locator:' + locator,
                                    rows=rows,
                                    start=start)
        XML = ElementTree()
        try:
            XML.parse(StringIO(page_hits))            
        except SyntaxError, e:
            raise SolrError, e
        page_ids = list(e.text for e in XML.getiterator('identifier'))
        return [extract(x)[1] for x in page_ids]

    def exact_facet_count(self, query, selected_facets,
                          facet_name, facet_value):
        ftoken = facet_token(facet_name, facet_value)


        # this function is temporarily broken because of how facets are handled
        # under dismax.  @@
        # well, ok, the use of dismax is temporarily backed out, but leave
        # this signal here to verify that we're not actually using exact
        # counts right now.
        raise NotImplementedError

        sf = list(s for s in selected_facets if re.match('^[a-z]{12}$', s))
        fs = ' '.join(sf+[ftoken])
        result_json = self.raw_search(
            self.basic_query(query),
            fq='facet_tokens:(%s)'% fs,
            rows=0,
            wt='json')
        result = simplejson.loads(result_json)
        n = result['response']['numFound']
        return n

    def facets(self,
               query,
               facet_list = default_facet_list,
               maxrows=5000):
        """Get facet counts for query.  Todo: statistical faceting."""

        result_set = self.raw_search(query, rows=maxrows, wt='json')

        # TODO: avoid using json here, by instead using xml response format
        # and parsing it with elementtree, if speed is acceptable.  That
        # should reduce memory usage by counting facets incrementally instead
        # of building an in-memory structure for the whole response before
        # counting the facets.
        try:
            # print >> web.debug, '*** parsing result_set=', result_set
            h1 = simplejson.loads(result_set)
        except SyntaxError, e:   # we got a solr stack dump
            # print >> web.debug, '*** syntax error result_set=(%r)'% result_set
            raise SolrError, (e, result_set)

        docs = h1['response']['docs']
        r = facet_counts(docs, facet_list)
        return r

    def raw_search(self, query, **params):
        # raw search: directly post a Solr search which uses fieldnames etc.
        # return the raw xml or json result that comes from solr
        # need to refactor this class to combine some of these methods @@
        assert type(query) == str

        server_url = 'http://%s:%d/solr/select' % self.server_addr
        query_url = '%s?q=%s'% (server_url, self.__query_fmt(query, **params))
        # print >> web.debug, ('raw_search', ((query,params),query_url))
        ru = urlopen(query_url)
        return ru.read()

    # translate a basic query into an advanced query, by launching PHP
    # script, passing query to it, and getting result back.
    def basic_query(self, query):
        return self.query_processor.process(query)

    def basic_search(self, query, **params):
        # basic search: use archive.org PHP script to transform the basic
        # search query into an advanced (i.e. expanded) query.  "Basic" searches
        # can actually use complicated syntax that the PHP script transforms
        # by adding search weights, range expansions, and so forth.
        assert type(query)==str         # not sure what to do with unicode @@

        bquery = self.basic_query(query)
        # print >> web.debug, '* basic search: query=(%r)'% bquery
        return self.advanced_search(bquery, **params)

# get second element of a tuple
def snd((a,b)): return b

def facet_counts(result_list, facet_fields):
    """Return list of facet counts for a search result set.

    The list of field names to fact on is `facet_fields'.
    The result list from solr is `result_list'.  The structures
    look like:
       result_list = [ { fieldname1 : [values...] }, ... ]
       facet_fields = ('author', 'media_type', ...)


    >>> results = [  \
           {'title': ['Julius Caesar'],                         \
            'author': ['William Shakespeare'],                  \
            'format': ['folio'] },                              \
           {'title': ['Richard III'],                           \
            'author': ['William Shakespeare'],                  \
            'format': ['folio'] },                              \
           {'title': ['Tom Sawyer'],                            \
            'author': ['Mark Twain'],                           \
            'format': ['hardcover'] },                          \
           {'title': ['The Space Merchants'],                   \
            'author': ['Frederik Pohl', 'C. M. Kornbluth'],     \
            'format': ['paperback'] },                          \
           ]
    >>> fnames = ('author', 'topic', 'format')
    >>> facet_counts(results, fnames)  #doctest: +NORMALIZE_WHITESPACE
    [('author', [('William Shakespeare', 2),
                 ('C. M. Kornbluth', 1),
                 ('Frederik Pohl', 1),
                 ('Mark Twain', 1)]),
     ('format', [('folio', 2),
                 ('hardcover', 1),
                 ('paperback', 1)])]
    """

    facets = defaultdict(lambda: defaultdict(int))
    for r in result_list:
        for k in set(r.keys()) & set(facet_fields):
            facets_k = facets[k]        # move lookup out of loop for speed
            for x in r[k]:
                facets_k[x] += 1

    return filter(snd, ((f, sorted(facets[f].items(),
                                   key=lambda (a,b): (-b,a)))
                        for f in facet_fields))

if __name__ == '__main__':
    import doctest
    doctest.testmod()
