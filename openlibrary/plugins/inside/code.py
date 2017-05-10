from infogami.utils import delegate, stats
from infogami.utils.view import render_template, public
from infogami import config
from lxml import etree
from openlibrary.utils import escape_bracket
import logging
import re, web, urllib, urllib2, urlparse, simplejson, httplib

def escape_q(q):
    """Hook for future pre-treatment of search query"""
    return q

class search_inside(delegate.page):
    path = '/search/inside'

    def GET(self):
        def get_results(q, offset=0, limit=100):
            q = escape_q(q)
            results = inside_search_select({'q': q, 'from': offset, 'size': limit})
            # If there is any error in gettig the response, return the error
            if 'error' in results:
                return results

            # TODO: This chunk *seems* like it's not achieving anything -- try removing. If all good,
            #       can collapse `if 'error' in results` condition above.
            # ekey_doc = {}
            # for doc in results['hits']['hits']:
            #     ia = doc['fields']['identifier'][0]
            #     q = {'type': '/type/edition', 'ocaid': ia}
            #     ekeys = web.ctx.site.things(q)
            #     if not ekeys:
            #         del q['ocaid']
            #         q['source_records'] = 'ia:' + ia
            #         ekeys = web.ctx.site.things(q)
            #     if ekeys:
            #         ekey_doc[ekeys[0]] = doc
            # editions = web.ctx.site.get_many(ekey_doc.keys())
            # for e in editions:
            #     ekey_doc[e['key']]['edition'] = e

            return results

        def inside_search_select(params):
            if not hasattr(config, 'plugin_inside'):
                return {'error': 'Unable to prepare search engine'}
            search_endpoint = config.plugin_inside['search_endpoint']
            search_select = search_endpoint + '?' + urllib.urlencode(params, 'utf-8')

            # TODO: Update for Elastic
            # stats.begin("solr", url=search_select)

            try:
                json_data = urllib2.urlopen(search_select, timeout=30).read()
                logger = logging.getLogger("openlibrary.inside")
                logger.debug('URL: ' + search_select)
            except:
                return {'error': 'Unable to query search engine'}

            # TODO: Update for Elastic
            # stats.end()

            try:
                return simplejson.loads(json_data)
            except:
                return {'error': 'Error converting search engine data to JSON'}

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
            try:
                xml_data = urllib2.urlopen(meta_xml, timeout=5)
            except:
                stats.end()
                return {}
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
        def find_matches(ia, q):
            q = escape_q(q)
            host, ia_path = ia_lookup('/download/' + ia)
            if host is None or ia_path is None:
                return {'error': 'Could not lookup item info'}
            doc = find_doc(ia, host, ia_path) or ia

            # TODO: Does q really need web.urlquote?
            url = 'http://' + host + '/fulltext/inside.php?item_id=' + ia + '&doc=' + doc + '&path=' + ia_path + '&q=' + web.urlquote(q)
            try:
                ret = urllib2.urlopen(url, timeout=5).read()
                return simplejson.loads(ret)
            except:
                return {'error': 'Error finding matches'}

        def ia_lookup(path):
            """Excecting a 302 redirect, retrying up to 5 times"""
            h1 = httplib.HTTPConnection("archive.org")
            new_url = None
            for attempt in range(5):
                try:
                    h1.request("GET", path)
                except:
                    continue
                res = h1.getresponse()
                res.read()
                if res.status == 302:
                    new_url = res.getheader('location')
                    break
            if new_url is None:
                return (None, None)
            re_new_url = re.compile('^http://([^/]+\.us\.archive\.org)(/.+)$')

            m = re_new_url.match(new_url)
            return m.groups() if m else (None, None)

        def find_doc(ia, host, ia_path):
            abbyy_gz = '_abbyy.gz'
            files_xml = 'http://%s%s/%s_files.xml' % (host, ia_path, ia)
            try:
                xml_data = urllib2.urlopen(files_xml, timeout=5)
                xml = etree.parse(xml_data)
            except:
                return None
            for e in xml.getroot():
                if e.attrib['name'].endswith(abbyy_gz):
                    return e.attrib['name'][:-len(abbyy_gz)]
            return None

        return render_template('search/snippets.tmpl', find_matches, ia)
