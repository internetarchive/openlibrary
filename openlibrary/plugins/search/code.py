from __future__ import with_statement
import web
import stopword
import pdb

from infogami import utils
from infogami.utils import delegate
from infogami.infobase.client import Thing
from infogami.utils import view, template
from infogami import config
from infogami.plugins.api.code import jsonapi

import re, web
import solr_client
import time
import simplejson
from functools import partial
from gzip import open as gzopen
import cPickle
from collections import defaultdict

render = template.render

sconfig = web.storage()
if hasattr(config, 'plugin_search'):
    sconfig = config.plugin_search

sconfig.setdefault('solr', None)
sconfig.setdefault('fulltext_solr', None)
sconfig.setdefault('fulltext_shards', [])

def parse_host(host_and_port):
    """
    >>> print parse_host('alice:1234')
    ('alice', 1234)
    """
    if host_and_port is None:
        return (None, None)
    h,p = host_and_port.split(':')
    return (h, int(p))

solr_server_address = parse_host(sconfig.solr)
solr_fulltext_address = parse_host(sconfig.fulltext_solr)
solr_fulltext_shards = map(parse_host, sconfig.fulltext_shards)

if solr_fulltext_address is not None:
    if hasattr(sconfig, 'solr_pagetext_address'):
        solr_pagetext_address = parse_host(sconfig.solr_pagetext_address)
    else:
        solr_pagetext_address = solr_fulltext_address

if solr_server_address:
    solr = solr_client.Solr_client(solr_server_address)
    solr.query_processor = solr_client.create_query_processor(sconfig.get('query_processor'))
else:
    solr = None

if solr_fulltext_address:
    solr_fulltext = solr_client.Solr_client(solr_fulltext_address,
                                            shards=solr_fulltext_shards)
    solr_pagetext = solr_client.Solr_client(solr_pagetext_address,
                                            shards=solr_fulltext_shards)

def lookup_ocaid(ocaid):
    ocat = web.ctx.site.things(dict(type='/type/edition', ocaid=ocaid))
    assert type(ocat)==list, (ocaid,ocat)
    w = web.ctx.site.get(ocat[0]) if ocat else None
    return w

from collapse import collapse_groups
class fullsearch(delegate.page):
    def POST(self):
        errortext = None
        out = []

        i = web.input(q = None,
                      rows = 20,
                      offset = 0,
                      _unicode=False
                      )

        class Result_nums: pass
        nums = Result_nums()
        timings = Timestamp()

        nums.offset = int(i.get('offset', '0') or 0)
        nums.rows = int(i.get('rows', '0') or 20)
        nums.total_nbr = 0
        q = i.q

        if not q:
            errortext='you need to enter some search terms'
            return render.fullsearch(q, out,
                                     nums,
                                     [], # timings
                                     errortext=errortext)

        try:
            q = re.sub('[\r\n]+', ' ', q).strip()
            nums.total_nbr, results = \
                       solr_fulltext.fulltext_search(q,
                                                     start=nums.offset,
                                                     rows=nums.rows)
            timings.update('fulltext done')
            t_ocaid = 0.0
            for ocaid in results:
                try:
                    pts = solr_pagetext.pagetext_search(ocaid, q)
                    t_temp = time.time()
                    oln_thing = lookup_ocaid(ocaid)
                    t_ocaid += time.time() - t_temp
                    if oln_thing is None:
                        # print >> web.debug, 'No oln_thing found for', ocaid
                        pass
                    else:
                        out.append((oln_thing, ocaid,
                                    collapse_groups(solr_pagetext.pagetext_search
                                                    (ocaid, q))))
                except IndexError, e:
                    print >> web.debug, ('fullsearch index error', e, e.args)
                    pass
            timings.update('pagetext done (oca lookups: %.4f sec)'% t_ocaid)
        except IOError, e:
            errortext = 'fulltext search is temporarily unavailable (%s)' % \
                        str(e)

        return render.fullsearch(q,
                                 out,
                                 nums,
                                 timings.results(),
                                 errortext=errortext)

    GET = POST

import facet_hash
facet_token = view.public(facet_hash.facet_token)

class Timestamp(object):
    def __init__(self):
        self.t0 = time.time()
        self.ts = []
    def update(self, msg):
        self.ts.append((msg, time.time()-self.t0))
    def results(self):
        return (time.ctime(self.t0), self.ts)

# this is in progress, not used yet.
class Timestamp1(object):
    def __init__(self, key=None):
        self.td = defaultdict(float)
        self.last_t = time.time()
        self.key = key
        self.switch(key)
    def switch(self, key):
        t = time.time()
        self.td[self.key] += self.last_t - t
        self.last_t = t
        self.key = key
        
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
                      _unicode=False
                      )
        timings = Timestamp()
        results = []
        qresults = web.storage(begin=0, total_results=0)
        facets = []
        errortext = None

        if solr is None:
            errortext = 'Solr is not configured.'
        if i.q:
            q0 = [clean_punctuation(i.q)]
        else:
            q0 = []
        for formfield, searchfield in \
                (('wtitle', 'title'),
                 ('wauthor', 'authors'),
                 ('wtopic', 'subjects'),
                 ('wisbn', ['isbn_10', 'isbn_13']),
                 ('wpublisher', 'publishers'),
                 ('wdescription', 'description'),
                 ('pfulltext', 'has_fulltext'),
                 ):
            v = clean_punctuation(i.get(formfield))
            if v:
                if type(searchfield) == str:
                    q0.append('%s:(%s)'% (searchfield, v))
                elif type(searchfield) == list:
                    q0.append('(%s)'% \
                              ' OR '.join(('%s:(%s)'%(s,v))
                                          for s in searchfield))
            # @@
            # @@ need to unpack date range field and sort order here
            # @@

        # print >> web.debug, '** i.q=(%s), q0=(%s)'%(i.q, q0)

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

        # don't throw a backtrace if there's junk tokens.  Robots have
        # been sending them, so just throw away any invalid ones.
        # assert all(re.match('^[a-z]{5,}$', a) for a in ft_list), \
        #       ('invalid facet token(s) in',ft_list)

        ft_list = filter(partial(re.match, '^[a-z]{5,}$'), ft_list)

        qtokens = ' facet_tokens:(%s)'%(' '.join(ft_list)) if ft_list else ''
        ft_pairs = list((t, solr.facet_token_inverse(t)) for t in ft_list)

        # we have somehow gotten some queries for facet tokens with no
        # inverse.  remove these from the list.
        ft_pairs = filter(lambda (a,b): b, ft_pairs)

        if not q0 and not qtokens:
            errortext = 'You need to enter some search terms.'
            return render.advanced_search(i.get('wtitle',''),
                                          qresults,
                                          results,
                                          [], # works_groups
                                          [], # facets
                                          i.ftokens,
                                          ft_pairs,
                                          [], # timings
                                          errortext=errortext)

        out = []
        works_groups = []
        i.q = ' '.join(q0)
        try:
            # work around bug in PHP module that makes queries
            # containing stopwords come back empty.
            query = stopword.basic_strip_stopwords(i.q.strip()) + qtokens
            bquery = solr.basic_query(query)
            offset = int(i.get('offset', '0') or 0)
            qresults = solr.advanced_search(bquery, start=offset)
            # print >> web.debug,('qresults',qresults.__dict__)
            # qresults = solr.basic_search(query, start=offset)
            timings.update("begin faceting")
            facets = solr.facets(bquery, maxrows=5000)
            timings.update("done faceting")
            # results = munch_qresults(qresults.result_list)
            results = munch_qresults_stored(qresults)
            results = filter(bool, results)
            timings.update("done expanding, %d results"% len(results))

            if 0:
                # temporarily disable computing works, per
                # launchpad bug # 325843
                results, works_groups = collect_works(results)
                print >> web.debug, ('works', results, works_groups)

            timings.update("done finding works, (%d,%d) results"%
                           (len(results), len(works_groups)))

            # print >> web.debug, ('works result',
            #                    timings.ts,
            #                    (len(results),results),
            #                    (len(works_groups),works_groups))

        except (solr_client.SolrError, Exception), e:
            import traceback
            errortext = 'Sorry, there was an error in your search.'
            if i.get('safe')=='false':
                errortext +=  '(%r)' % (e.args,)
                errortext += '<p>' + traceback.format_exc()

        # print >> web.debug, 'basic search: about to advanced search (%r)'% \
        #     list((i.get('q', ''),
        #           qresults,
        #           results,
        #           facets,
        #           i.ftokens,
        #           ft_pairs))

        return render.advanced_search(i.get('q', ''),
                                      qresults,
                                      results,
                                      works_groups,
                                      facets,
                                      i.ftokens,
                                      ft_pairs,
                                      timings.results(),
                                      errortext=errortext)

    GET = POST

def munch_qresults_stored(qresults):
    def mk_author(a,ak):
        class Pseudo_thing(Thing):
            def _get(self, key, revision=None):
                return self
            def __setattr__(self, a, v):
                self.__dict__[a] = v

        authortype = Thing(web.ctx.site,u'/type/author')
        d = Pseudo_thing(web.ctx.site, unicode(ak))
        d.name = a
        d.type = authortype
        # print >> web.debug, ('mk_author made', d)
        # experimentally try db retrieval to compare with our test object
        # dba = web.ctx.site.get(ak)
        # print >> web.debug, ('mk_author db retrieval', dba)
        return d
    def mk_book(d):
        assert type(d)==dict
        d['key'] = d['identifier']
        for x in ['title_prefix', 'ocaid','publish_date',
                  'publishers', 'physical_format']:
            if x not in d:
                d[x] = ''

        def dget(attr):
            a = d.get(attr, [])
            a = [] if a is None else a
            return a
        da, dak = dget('authors'), dget('author_keys')
        # print >> web.debug, ('da,dak',da,dak)
        d['authors'] = list(mk_author(a,k) for a,k in zip(da,dak) if k is not None)
        return web.storage(**d)
    return map(mk_book, qresults.raw_results)
    
def collect_works(result_list):
    wds = defaultdict(list)
    rs = []
    # split result_list into two lists, those editions that have been assigned
    # to a work and those that have not.
    for r in result_list:
        ws = r.get('works')
        if ws:
            for w in ws:
                wds[w['key']].append(r)
        else:
            rs.append(r)

    # print >> web.debug, ('collect works', rs,wds)

    s_works = sorted(wds.items(), key=lambda (a,b): len(b), reverse=True)
    return rs, [(web.ctx.site.get(a), b) for a,b in s_works]


# somehow the leading / got stripped off the book identifiers during some
# part of the search import process.  figure out where that happened and
# fix it later.  for now, just put the slash back.
def restore_slash(book):
    if not book.startswith('/'): return '/'+book
    return book

@view.public
def exact_facet_count(query, selected_facets, facet_name, facet_value):
    t0 = time.time()
    r = solr.exact_facet_count(query, selected_facets,
                               facet_name, facet_value)
    t1 = time.time()-t0
    qfn = (query, facet_name, facet_value)
    print >> web.debug, ('*** efc', qfn, r, t1)
    return r

def get_books(keys):
    """Get all books specified by the keys in a single query and also prefetch all the author records.
    """
    books = web.ctx.site.get_many(keys)

    # prefetch the authors so they will be cached by web.ctx.site for
    # later use.  Avoid trapping in case some author record doesn't
    # have a key, since this seems to happen sometimes.
    author_keys = set(getattr(a, 'key', None)
                      for b in books for a in b.authors)
    author_keys.discard(None)

    # actually retrieve the authors and don't do anything with them.
    # this is just to get them into cache.
    web.ctx.site.get_many(list(author_keys))
    return books

def munch_qresults(qlist):
    raise NotImplementedError   # make sure we're not using this func

    results = []
    rset = set()

    # make a copy of qlist with duplicates removed, but retaining
    # original order
    for res in qlist:
        if res not in rset:
            rset.add(res)
            results.append(res)

    # this is supposed to be faster than calling site.get separately
    # for each result
    return get_books(map(restore_slash, results))

# disable the above function by redefining it as a do-nothing.
# This replaces a version that removed all punctuation from the
# query (see change history, 2008-05-01).  Something a bit smarter
# than this is probably better.

# additionally: if term is 10 or 13 digits with some hyphens,
# treat it as an ISBN and strip the hyphens, since they are
# indexed with no hyphens.  LP #375277.

# hmm, this should be done only for unqualified and isbn-specific
# fields, not other named fields.  test like this for now. @@
def clean_punctuation(s,field=None):
    def clean1(w):
        x = w.lstrip(':')
        # return x                # actually don't compress ISBN for now.
        maybe_isbn = list(c for c in x if c != '-')
        if len(maybe_isbn) in [10,13] and all(c.isdigit() for c in maybe_isbn):
            x = ''.join(maybe_isbn)
        return x
    ws = map(clean1, s.split())
    r = ' '.join(filter(bool,ws))
    return r

class search_api:
    error_val = {'status':'error'}
    def GET(self):
        def format(val, prettyprint=False, callback=None):
            if callback is not None:
                if type(callback) != str or \
                       not re.match('[a-z][a-z0-9\.]*$', callback, re.I):
                    val = self.error_val
                    callback = None

            if prettyprint:
                json = simplejson.dumps(val, indent = 4)
            else:
                json = simplejson.dumps(val)

            if callback is None:
                return json
            else:
                return '%s(%s)'% (callback, json)

        i = web.input(q = None,
                      rows = 20,
                      offset = 0,
                      format = None,
                      callback = None,
                      prettyprint=False,
                      _unicode=False)

        offset = int(i.get('offset', '0') or 0)
        rows = int(i.get('rows', '0') or 20)

        try:
            query = simplejson.loads(i.q).get('query')
        except (ValueError, TypeError):
            return format(self.error_val, i.prettyprint, i.callback)

        dval = dict()

        if type(query) == list:
            qval = list(self._lookup(i, q, offset, rows) for q in query)
            dval["result_list"] = qval
        else:
            dval = self._lookup(i, query, offset, rows)

        return format(dval, i.prettyprint, i.callback)

    def _lookup(self, *args):
        try:
            return self._lookup_1(*args)
        except solr_client.SolrError:
            return self.error_val

    def _lookup_1(self, i, query, offset, rows):
        qresult = query and \
                   solr.basic_search(query.encode('utf8'),
                                     start=offset,
                                     rows=rows
                                     )
        if not qresult:
            result = []
        else:
            result = map(restore_slash, qresult.result_list)

        dval = dict()

        if i.format == "expanded":
            eresult = list(book.dict() for book in munch_qresults(result)
                           if book)
            for e in eresult:
                for a in e.get("authors", []):
                    ak = web.ctx.site.get(a["key"])
                    if ak:
                        akd = ak.dict()
                        if 'books' in akd:
                            del akd['books']
                        a["expanded"] = akd

            dval["expanded_result"] = eresult
        else:
            dval["result"] = result

        dval["status"] = "ok"
        return dval

class SearchProcessor:
    def _process_query(self, query):
        """Process a query dictionary and returns a query string."""
        query = dict(query)
        q = query.pop('q', None)
        
        parts = []
        if q:
            parts.append(self.normalize(q))
                
        for k, v in query.items():
            k = k.lower()
            v = self.normalize(v)
            if k == 'isbn':
                part = '(isbn_10:(%s) OR isbn_13:(%s))' % (v, v)
            else:
                part = '%s:(%s)' % (k, v)
            parts.append(part)
        return " ".join(parts)
        
    def normalize(self, value):
        """Normalize string value by remove unnecessary punctuation."""
        return clean_punctuation(value)
        
    def _solr_query(self, q):
        """Takes a query string and expands it"""
        return solr.basic_query(q)
        
    def _process_doc(self, doc):
        d = {
            'key': doc['identifier'],
            'type': {'key': '/type/edition'},
            'title': doc.get('title', '')
        }
        
        if 'authors' in doc and 'author_keys' in doc:
            d['authors'] = [{'key': key, 'name': name} for key, name in zip(doc['author_keys'], doc['authors'])]
            
        keys = ['title', 'publishers', 'languages', 'subjects']
        for k in keys:
            if k in doc:
                d[k] = doc[k]
                
        return d

    def _process_result(self, result, facets=None):
        out = {
            'matches': result.total_results,
            'docs': [self._process_doc(d) for d in result.raw_results]
        } 
        if facets is not None:
            out['facets'] = facets
        return out
        
    def search(self, query):
        """Constructs solr query from given query dict, executes it and returns the results.

        Sample queries:

            {'q': 'Tom Sawyer'}
            {'authors': 'Mark Twain'}
            {'q': 'Tom Sawyer'}
            {'title': 'Tom Sawyer'}
            {'title': 'Tom Sawyer', 'authors': 'Mark Twain', 'lccn': '49049011'}
            {'title': 'Tom Sawyer', 'authors': 'Mark Twain', 'publisher': '49049011'}
        """
        t1 = time.time()

        query = dict(query)
        offset = query.pop('offset', 0)
        try:
            limit = int(query.pop('limit', 20))
        except ValueError:
            limit = 20
            
        if limit > 1000:
            limit = 1000
        
        facets = str(query.pop('facets', 'false')).lower() == 'true'

        query_string = self._process_query(query)
        solr_query = self._solr_query(query_string)

        if facets:
            # what if offset it more than 5000?
            
            # query for 5000 rows and take the required part from the results to avoid another request
            result = solr.advanced_search(solr_query, start=offset, rows=5000)
            facet_counts = solr_client.facet_counts(result.raw_results, solr_client.default_facet_list)
            result.raw_results = result.raw_results[offset:offset+limit]

            d = self._process_result(result, dict(facet_counts))
        else:
            result = solr.advanced_search(solr_query, start=offset, rows=limit)
            d = self._process_result(result)
            
        t2 = time.time()
        d['time_taken'] = t2-t1
        return d
        
class search_json(delegate.page):
    path = "/search"
    encoding = "json"
    
    @jsonapi
    def GET(self):
        i = web.input(q='', query=None, _unicode=False)
        # query can be either specified as json with parameter query or just query parameters
        query = i.pop('query')
        if query:
            query = simplejson.loads(i.query)
        else:
            query = i
        
        result = SearchProcessor().search(i)
        return simplejson.dumps(result)

# add search API if api plugin is enabled.
if 'api' in delegate.get_plugins():
    from infogami.plugins.api import code as api
    api.add_hook('search', search_api)

if __name__ == '__main__':
    import doctest
    doctest.testmod()
