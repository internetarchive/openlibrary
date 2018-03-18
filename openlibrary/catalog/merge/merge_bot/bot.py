#!/usr/bin/python

import sys
import web
import sys, codecs
from catalog.utils.query import query_iter, set_staging, withKey

from catalog.merge.merge_marc import *
from catalog.utils.query import get_mc, withKey
import catalog.merge.amazon as merge_amazon
import catalog.merge.merge_marc as merge_marc
from catalog.merge.merge_bot.merge import amazon_and_marc, get_record
from pprint import pformat

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
#set_staging(True)

urls = (
    '/', 'index'
)
app = web.application(urls, globals())

threshold = 875

#def text_box(k, input): return k

def list_to_html(l):
    def blue(s):
        return ' <span style="color:blue; font-weight:bold">%s</span> ' % s
    return blue('[') + blue('|').join(l) + blue(']')

def as_html(x):
    return list_to_html(x) if isinstance(x, list) else x

class index:
    def head(self, title):
        style = '''
body { font-family: Arial,Helvectica,Sans-serif }
th { text-align: left; }
td { background: #eee; }
'''
        return '<html>\n<head>\n<title>' + title + '</title>\n' + \
            '<style>' + style + '</style>\n</head>\n<body>'

    def tail(self):
        return '</body>\n</html>\n'

    def text_box(self, k):
        if self.input[k]:
            v = web.htmlquote(self.input[k])
            return '<input type="text" name="%s" value="%s">' % (k, v)
        else:
            return '<input type="text" name="%s">' % k

    def form(self):
        return '<form>' \
            + 'ISBN: ' + self.text_box('isbn') \
            + ' or OCLC: ' + self.text_box('oclc') \
            + ' <input type="submit" value="search">' \
            + '</form>'

    def field_table(self, input, rec_amazon, rec_marc):
        yield '<table>'
        yield '''<tr>
<th>Field</th>
<th>match</th>
<th>score</th>
<th>Amazon</th>
<th>MARC</th>
</tr>'''
        total = 0
        for field, match, score in input:
            yield '<tr>'
            yield '<td>%s</td>' % field
            yield '<td>%s</td>' % web.htmlquote(match)
            yield '<td>%s</td>' % score
            yield '<td>%s</td>' % as_html(rec_amazon.get(field, None))
#            if field == 'number_of_pages':
#                yield '<td>%s</td>' % (web.htmlquote(rec_marc['pagination']) if 'pagination' in rec_marc else '<i>pagination missing</i>')
            if field == 'authors':
                authors = rec_marc.get(field, [])
                yield '<td>%s</td>' % list_to_html(web.htmlquote(a['name']) for a in authors)
            else:
                yield '<td>%s</td>' % as_html(rec_marc.get(field, None))
            yield '</tr>'
            total += score
        yield '</table>'
        yield 'threshold %d, total: %d, ' % (threshold, total)
        yield (('match' if total >= threshold else 'no match') + '<br>')

    def marc_compare(self, editions):
        key1 = editions[0]['key']
        mc1 = get_mc(key1)
        rec1 = get_record(key1, mc1)
        key2 = editions[1]['key']
        mc2 = get_mc(key2)
        rec2 = get_record(key2, mc2)

        yield '<h2>Level 1</h2>'
        l1 = merge_marc.level1_merge(rec1, rec2)
        for i in self.field_table(l1, rec1, rec2):
            yield i

        yield '<h2>Level 2</h2>'
        l2 = merge_marc.level2_merge(rec1, rec2)
        for i in self.field_table(l2, rec1, rec2):
            yield i

    def amazon_compare(self, editions):
        key1 = editions[0]['key']
        key2 = editions[1]['key']
        try:
            (rec_amazon, rec_marc) = amazon_and_marc(key1, key2)
        except AssertionError:
            yield 'must be one amazon and one marc edition'
            return
        yield '<h2>Level 1</h2>'
        l1 = merge_amazon.level1_merge(rec_amazon, rec_marc)
        for i in self.field_table(l1, rec_amazon, rec_marc):
            yield i

        yield '<h2>Level 2</h2>'
        l2 = merge_amazon.level2_merge(rec_amazon, rec_marc)
        for i in self.field_table(l2, rec_amazon, rec_marc):
            yield i

    def search(self, editions):
        yield str(len(editions)) + ' editions found<p>'
        yield '<table>'
        yield '<tr><th>Key</th><th>OCLC</th><th>ISBN</th><th>title</th><th>subtitle</th></tr>'
        for e in editions:
            url = 'http://openlibrary.org' + e['key']
            title = web.htmlquote(e['title']) if e['title'] else 'no title'
            yield '<tr><td><a href="%s">%s</a></td>' % (url, e['key'])
            yield '<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (e['oclc_numbers'], e['isbn_10'], title, (web.htmlquote(e['subtitle']) if e.get('subtitle', None) else '<i>no subtitle</i>'))
        yield '</table><p>'

        if len(editions) == 2:
            yield '2 editions found, lets compare them<br>'
            for i in self.marc_compare(editions):
                yield i

    def isbn_search(self, v):
        q = {'type': '/type/edition', 'isbn_10': v, 'title': None, 'subtitle': None}
        editions = []
        for e in query_iter(q):
            e['isbn_10'] = v
            editions.append(e)
        yield 'searching for ISBN ' + web.htmlquote(v) + ': '
        for i in self.search(editions):
            yield i

    def oclc_search(self, v):
        q = {'type': '/type/edition', 'oclc_numbers': v, 'title': None, 'subtitle': None, 'isbn_10': None}
        editions = []
        print q
        for e in query_iter(q):
            e['oclc_numbers'] = v
            editions.append(e)
        yield 'searching for OCLC ' + web.htmlquote(v) + ': '
        for i in self.search(editions):
            yield i

    def title_search(self, v):
        q = {'type': '/type/edition', 'isbn_10': None, 'title': v}
        editions = []
        for e in query_iter(q):
            e['title'] = v
            editions.append(e)
        yield 'searcing for title "' + web.htmlquote(v) + '": '
        for i in self.search(editions):
            yield i

    def GET(self):
        #self.input = web.input(ol=None, isbn=None, title=None)
        self.input = web.input(isbn=None, oclc=None)
        ret = self.head('Merge debug')
#        ret += web.htmlquote(repr(dict(self.input)))
        for i in self.form():
            ret += i
        if self.input.isbn:
            isbn = self.input.isbn
            for i in self.isbn_search(isbn):
                ret += i
        elif self.input.oclc:
            oclc = self.input.oclc
            for i in self.oclc_search(oclc):
                ret += i
#        elif self.input.title:
#            title = self.input.title
#            for i in self.title_search(title):
#                ret += i
        ret += '</body>\n</html>\n'
        return ret

if __name__ == "__main__":
    app.run()

