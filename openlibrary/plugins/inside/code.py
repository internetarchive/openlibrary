from infogami.utils import delegate, stats
from infogami.utils.view import render_template, public
from infogami import config
from lxml import etree
from openlibrary.utils import escape_bracket
import logging
import re, web, urllib, urllib2, urlparse, simplejson, httplib

logger = logging.getLogger("openlibrary.inside")
search_host = 'https://books-search0.us.archive.org/api/v0.1/search'

def escape_q(q):
    """Hook for future pre-treatment of search query"""
    return q

def inside_search_select(params):
    search_select = search_host + '?' + urllib.urlencode(params)

    # TODO: Update for Elastic
    # stats.begin("solr", url=search_select)

    try:
        json_data = urllib2.urlopen(search_select, timeout=30).read()
        logger.debug('URL: ' + search_select)
        logger.debug(json_data)
    except IOError, e:
        logger.error("Unable to query search engine", exc_info=True)
        return {'error': web.htmlquote(str(e))}
    finally:
        # TODO: Update for Elastic
        # stats.end()
        pass

    try:
        return simplejson.loads(json_data)
    except:
        return {'error': 'Error converting search engine data to JSON'}

@public
def search_inside_result_count(q):
    q = escape_q(q)
    params = {
        'q': web.urlquote(q)
    }
    results = inside_search_select(params)
    if 'error' in results:
        return None

    return results['hits']['total']

class search_inside(delegate.page):
    path = '/search/inside'

    def GET(self):
        def get_results(q, offset=0, limit=100):
            q = escape_q(q)
            results = inside_search_select({'q': q, 'from': offset, 'size': limit})
            # If there is any error in gettig the response, return the error
            if 'error' in results:
                return results

            # TODO: This chunk seems unused
            ekey_doc = {}
            for doc in results['hits']['hits']:
                ia = doc['fields']['identifier'][0]
                q = {'type': '/type/edition', 'ocaid': ia}
                ekeys = web.ctx.site.things(q)
                if not ekeys:
                    del q['ocaid']
                    q['source_records'] = 'ia:' + ia
                    ekeys = web.ctx.site.things(q)
                if ekeys:
                    ekey_doc[ekeys[0]] = doc
            editions = web.ctx.site.get_many(ekey_doc.keys())
            for e in editions:
                ekey_doc[e['key']]['edition'] = e

            return results

        def quote_snippet(snippet):
            trans = { '\n': ' ', '{{{': '<b>', '}}}': '</b>', }
            re_trans = re.compile(r'(\n|\{\{\{|\}\}\})')
            return re_trans.sub(lambda m: trans[m.group(1)], web.htmlquote(snippet))

        def editions_from_ia(ia):
            q = {'type': '/type/edition', 'ocaid': ia, 'title': None, 'covers': None, 'works': None, 'authors': None}
            editions = web.ctx.site.things(q)
            if not editions:
                del q['ocaid']
                q['source_records'] = 'ia:' + ia
                editions = web.ctx.site.things(q)
            return editions

        def read_from_archive(ia):
            meta_xml = 'http://archive.org/download/' + ia + '/' + ia + '_meta.xml'
            stats.begin("archive.org", url=meta_xml)
            xml_data = urllib2.urlopen(meta_xml, timeout=5)
            item = {}
            try:
                tree = etree.parse(xml_data)
            except etree.XMLSyntaxError:
                return {}
            finally:
                stats.end()
            root = tree.getroot()

            fields = ['title', 'creator', 'publisher', 'date', 'language']

            for k in 'title', 'date', 'publisher':
                v = root.find(k)
                if v is not None:
                    item[k] = v.text

            for k in 'creator', 'language', 'collection':
                v = root.findall(k)
                if len(v):
                    item[k] = [i.text for i in v if i.text]
            return item

        return render_template('search/inside.tmpl', get_results, quote_snippet, editions_from_ia, read_from_archive)

class snippets(delegate.page):
    path = '/search/inside/(.+)'
    def GET(self, ia):
        def find_doc(ia, host, ia_path):
            abbyy_gz = '_abbyy.gz'
            files_xml = 'http://%s%s/%s_files.xml' % (host, ia_path, ia)
            xml_data = urllib2.urlopen(files_xml, timeout=5)
            for e in etree.parse(xml_data).getroot():
                if e.attrib['name'].endswith(abbyy_gz):
                    return e.attrib['name'][:-len(abbyy_gz)]

        def ia_lookup(path):
            h1 = httplib.HTTPConnection("archive.org")

            for attempt in range(5):
                h1.request("GET", path)
                res = h1.getresponse()
                res.read()
                if res.status != 200:
                    break
            assert res.status == 302
            new_url = res.getheader('location')

            re_new_url = re.compile('^http://([^/]+\.us\.archive\.org)(/.+)$')

            m = re_new_url.match(new_url)
            return m.groups()

        def find_matches(ia, q):
            q = escape_q(q)
            host, ia_path = ia_lookup('/download/' + ia)
            doc = find_doc(ia, host, ia_path) or ia

            url = 'http://' + host + '/fulltext/inside.php?item_id=' + ia + '&doc=' + doc + '&path=' + ia_path + '&q=' + web.urlquote(q)
            ret = urllib2.urlopen(url, timeout=5).read().replace('"matches": [],\n}', '"matches": []\n}')
            try:
                return simplejson.loads(ret)
            except:
                re_h1_error = re.compile('<center><h1>(.+?)</h1></center>')
                m = re_h1_error.search(ret)
                # return { 'error': web.htmlunquote(m.group(1)) }
                return { 'error': 'Error finding matches' }
                
        return render_template('search/snippets.tmpl', find_matches, ia)
