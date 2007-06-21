
from collections import defaultdict    # python 2.5
from operator import itemgetter

snd = itemgetter(1)  # snd(t) is 2nd element of tuple t

def facet_counts(result_list, facet_fields):
    """Return list of facet counts for a search result set.

    The list of field names to fact on is `facet_fields'.
    The result list from solr is `result_list'.  The structures
    look like:
       result_list = [ { fieldname1 : [values...] }, ... ]
       facet_fields = ('author', 'media_type', ...)

    >>> fnames = ('author', 'topic', 'format')
    """

    facets = defaultdict(lambda: defaultdict(int))
    for r in result_list:
        for k in set(r.keys()) & set(facet_fields):
            facets_k = facets[k]        # move lookup out of loop for speed
            for x in r[k]:
                facets_k[x] += 1

    return filter(snd, ((f, sorted(facets[f].items(),
                                   key=snd,
                                   reverse=True))
                        for f in facet_fields))
                  
fnames = ('author', 'topic', 'format')
results = [{'title': ['Julius Caesar'],
            'author': ['William Shakespeare'],
            'format': ['folio'] },
           {'title': ['Richard III'],
            'author': ['William Shakespeare'],
            'format': ['folio'] },
           {'title': ['Tom Sawyer'],
            'author': ['Mark Twain'],
            'format': ['paperback'] },
           {'title': ['The Space Merchants'],
            'author': ['Frederik Pohl', 'C. M. Kornbluth'],
            'format': ['paperback'] },
           ]

import urllib
from time import time

def query(q=None, max_rows=2000, facets_to_show=5):
    global h,h0,h1,docs,fc

    timings = []
    # record a timestamped message in timings[]
    def a(m=''): timings.append((time(), m))

    q = q or raw_input('enter query: ')
    url='http://127.0.0.1:8993/solr/select?' + \
         urllib.urlencode({'q':q, 'rows':0, 'wt':'python'})
    a('get #hits')
    h = urllib.urlopen(url).read()
    a('eval 1st response, %d bytes'% len(h))
    h0 = eval(h)
    n = h0['response']['numFound']
    a('get n=%d rows'% n)
    if n > max_rows:
        a('limit retrieval to %d rows'% max_rows)
        n = max_rows
    url='http://127.0.0.1:8993/solr/select?' + \
         urllib.urlencode({'q':q, 'rows':n, 'wt':'python'})
    h = urllib.urlopen(url).read()
    a('eval full response %d bytes'% len(h))
    h1 = eval(h)
    a('extract doc list')
    docs = h1['response']['docs']
    a('got %d docs'% len(docs))
    fc = facet_counts(docs, ('authors','subject','language'))
    a('got facet counts')

    for fname,facets in fc:
        m = min(len(facets), facets_to_show)
        print 'top %d (of %d) "%s" facets'% (m, len(facets), fname)
        print '','\n '.join(repr(t) for t in facets[:facets_to_show]),'\n'

    a('done')

    def deltas(timings):
        for (a1,b1),(a2,b2) in zip(timings[:-1], timings[1:]):
            print ' (%s)->(%s): %.3e sec'% (b1,b2,a2-a1)
        print '   total: %.3e sec'% (timings[-1][0] - timings[0][0])

    print 'speed:'
    deltas(timings)

query()
