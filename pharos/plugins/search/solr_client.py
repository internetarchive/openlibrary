#!/usr/bin/python
# from __future__ import with_statement
from urllib import quote, urlopen
from xml.etree.cElementTree import ElementTree
from cStringIO import StringIO
import os, re
from collections import defaultdict

# server_addr = ('pharosdb.us.archive.org', 8983)

# Solr search client; fancier version will have multiple persistent
# connections, etc.

solr_server_addr = ('pharosdb.us.archive.org', 8983)
# solr_server_addr = ('127.0.0.1', 8983)

class SolrError(Exception): pass

class Solr_result(object):
    def __init__(self, result_xml):
        et = ElementTree()
        try:
            et.parse(StringIO(result_xml))
        except SyntaxError, e:
            raise SolrError, e
        range_info = et.find('info').find('range_info')

        def gn(tagname):
            return int(range_info.findtext(tagname))
        self.total_results = gn('total_nbr')
        self.begin = gn('begin')
        self.end = gn('end')
        self.results_this_page = gn('contained_in_this_set')

        self.result_list = list(str(a.text) \
                                for a in et.getiterator('identifier'))
        
# Solr search client; fancier version will have multiple persistent
# connections, etc.
class Solr_client(object):
    def __init__(self,
                 server_addr = solr_server_addr,
                 pool_size = 1):
        self.server_addr = server_addr

    def __query_fmt(self, query, rows=None, start=None, wt=None):
        d = {'rows': rows, 'start': start, 'wt': wt}
        q = [query] + ['%s=%s'%(k, v) \
                       for k,v in d.items() if v is not None]
        return '&'.join(q)

    def isearch(self, query, loc=0):
        # iterator interface to search
        while True:
            s = search(self, query, start=loc)
            if len(s) == 0: return
            loc += len(s)
            for y in s:
                if not y.startswith('OCA/'):
                    yield y
                    
    def search(self, query, rows=None, start=None):
        # advanced search: directly post a Solr search which uses fieldnames etc.        
        # return list of document id's
        assert type(query) == str

        server_url = 'http://%s:%d/solr/select' % self.server_addr
        query_url = '%s?q=%s'% (server_url, self.__query_fmt(query, rows, start))
        #import web
        #print >> web.debug, query_url
        ru = urlopen(query_url)
        xml = ru.read()
        ru.close()
        return Solr_result(xml)

    advanced_search = search

    def fulltext_search(self, query, rows=None, start=None):
        """Does an advanced search on fulltext:blah.
        You get back a list of identifiers like ["foo", "bar", etc.]"""

        result_list = self.raw_search('fulltext:' + query, rows, start)
        e = ElementTree()
        try:
            e.parse(StringIO(result_list))
        except SyntaxError, e:
            raise SolrError, e
        
        out = []
        for r in e.getiterator('hit'):
            for d in r.find('metadata'):
                for x in list(d.getiterator()):
                    if x.tag == "identifier":
                        out.append(unicode(x.text).encode('utf-8')[4:])
                        break
        return out
                    

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
        

        page_hits =self.raw_search('locator:%s pagetext:%s' % (locator, query), rows, start)
        XML = ElementTree()
        try:
            XML.parse(StringIO(page_hits))            
        except SyntaxError, e:
            raise SolrError, e
        page_ids = list(e.text for e in XML.getiterator('identifier'))
        return [extract(x)[1] for x in page_ids]

    def facets(self,
               query,
               facet_list = ('author', 'subject', 'language'),
               maxrows=20000):
        """Get facet counts for query.  Todo: statistical faceting."""

        result_set = self.raw_search(query, rows=maxrows, wt='python')

        # TODO: avoid using eval here, by instead using xml response format
        # and parsing it with elementtree, if speed is acceptable.  That also
        # can reduce memory usage by counting facets incrementally instead
        # of building an in-memory structure for the whole response before
        # counting the facets.
        try:
            h1 = eval(result_set)
        except SyntaxError, e:   # we got a solr stack dump
            raise SolrError, (e, result_set)

        docs = h1['response']['docs']
        r = facet_counts(docs, ('publisher',
                                'authors',
                                'subject',
                                'language'))
        return r

    def raw_search(self, query, rows=None, start=None, wt=None):
        # raw search: directly post a Solr search which uses fieldnames etc.
        # return the raw xml result that comes from solr
        # need to refactor this class to combine some of these methods @@
        # may also wish to read and parse JSON or Python output instead of XML.
        assert type(query) == str

        server_url = 'http://%s:%d/solr/select' % self.server_addr
        ru = urlopen('%s?q=%s'% (server_url, self.__query_fmt(query, rows, start, wt)))
        return ru.read()

    # translate a basic query into an advanced query, by launching PHP
    # script, passing query to it, and getting result back.
    def basic_query(self, query):
        # this hex conversion is to defeat attempts at shell or PHP code injection
        # by including escape characters, quotes, etc. in the query.
        qhex = query.encode('hex')

        f = os.popen("""php -r 'require_once("/petabox/setup.inc");
                                 echo Search::querySolr(pack("H*", "%s"),
                                 false,
                                 array("title"=>100,
                                       "description"=>0.5,
                                       "creator"=>15,
                                       "language"=>10,
                                       "text"=>1,
                                       "fulltext"=>1));'""" %
                     qhex)
        return f.read()

    def basic_search(self, query, rows=None, start=None):
        # basic search: use archive.org PHP script to transform the basic
        # search query into an advanced (i.e. expanded) query.  "Basic" searches
        # can actually use complicated syntax that the PHP script transforms
        # by adding search weights, range expansions, and so forth.
        assert type(query)==str         # not sure what to do with unicode @@

        return self.advanced_search(self.basic_query(query), rows, start)

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

if False and __name__ == '__main__':
    def test(q='random'):
        global z
        s = Solr_client()
        z = s.search('fulltext:'+q)
    #    print z

    # cache-hostile search engine speed test: send search words to
    # solr in random order

    import random
    # words is a dictionary wordlist, often /usr/share/dict/words
    words = [w.strip() for w in open('words')]
    print len(words),'words'
    rq = filter(bool,words)  # remove empty lines
    random.shuffle(rq)

    from time import time
    t0=time()
    for n,q in enumerate(rq):
        if n%100==0: print n, time()-t0
        test(q)
    print time()-t0
