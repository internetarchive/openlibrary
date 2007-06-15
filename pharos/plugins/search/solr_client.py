#!/usr/bin/python
# from __future__ import with_statement
from urllib import quote, urlopen
from xml.etree.cElementTree import ElementTree
import os

# Solr search client; fancier version will have multiple persistent
# connections, etc.

class SolrError(Exception): pass

# Solr search client; fancier version will have multiple persistent
# connections, etc.
class Solr_client(object):
    def __init__(self, server_addr, pool_size = 1):
        self.server_addr = server_addr

    def __query_fmt(self, query, rows, start):
        d = {'rows': rows, 'start': start}
        q = '&'.join('%s=%d'%(k, v) for k,v in d.items()
                                        if v is not None)
        query = quote(query)
        if q != '':
            query += '?' + q
        return query

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
        ru = urlopen('%s?q=%s'% (server_url, self.__query_fmt(query, rows, start)))
        e = ElementTree()
        try:
            e.parse(ru)
        except SyntaxError, e:
            raise SolrError, e
        return list(str(a.text) for a in e.getiterator('identifier'))

    advanced_search = search

    def raw_search(self, query, rows=None, start=None):
        # raw search: directly post a Solr search which uses fieldnames etc.
        # return the raw xml result that comes from solr
        # need to refactor this class to combine some of these methods @@
        # may also wish to read and parse JSON or Python output instead of XML.
        assert type(query) == str

        server_url = 'http://%s:%d/solr/select' % self.server_addr
        ru = urlopen('%s?q=%s'% (server_url, self.__query_fmt(query, rows, start)))
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
                                       "description"=>15,
                                       "creator"=>15,
                                       "language"=>10,
                                       "text"=>1,
                                       "fulltext"=>0.5));'""" %
                     qhex)
        return f.read()

    def basic_search(self, query, rows=None, start=None):
        # basic search: use archive.org PHP script to transform the basic
        # search query into an advanced (i.e. expanded) query.  "Basic" searches
        # can actually use complicated syntax that the PHP script transforms
        # by adding search weights, range expansions, and so forth.
        assert type(query)==str         # not sure what to do with unicode @@

        return self.search(self.basic_query(query), rows, start)

if __name__ == '__main__':
    import sys
    def test(q='random'):
        global z
        s = Solr_client(sys.argv[1])
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
