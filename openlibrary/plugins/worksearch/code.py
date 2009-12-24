import web, re, urllib
from lxml.etree import parse, tostring
from infogami.utils import delegate
from infogami import config
from openlibrary.catalog.utils import flip_name

solr_host = config.plugin_worksearch.get('solr')
solr_select_url = "http://" + solr_host + "/solr/works/select"

trans = {'&':'amp','<':'lt','>':'gt', '"': 'quot'}
re_html_replace = re.compile('([&<>"])')

def esc(s):
    if not isinstance(s, basestring):
        return s
    return re_html_replace.sub(lambda m: "&%s;" % trans[m.group(1)], s)

def search_url(params, exclude = set()):
    url = []
    for k, v in params.items():
        if isinstance(v, list):
            for i in v:
                if (k, i) not in exclude:
                    url.append(k + "=" + i)
            continue
        if (k, v) not in exclude:
            url.append(k + "=" + v)
    return '?' + '&'.join(url)

def url_quote(s):
    if not s:
        return ''
    return urllib.quote_plus(s.encode('utf-8'))

re_baron = re.compile(r'^([A-Z][a-z]+), (.+) \1 Baron$')
def tidy_name(s):
    if s is None:
        return '<em>name missing</em>'
    if s == 'Mao, Zedong':
        return 'Mao Zedong'
    m = re_baron.match(s)
    if m:
        return m.group(2) + ' ' + m.group(1)
    if ' Baron ' in s:
        s = s[:s.find(' Baron ')]
    elif s.endswith(' Sir'):
        s = s[:-4]
    return flip_name(s)

def read_highlight(root):
    e_highlight = root.find("lst[@name='highlighting']")
    highlight_titles = {}
    for e_lst in e_highlight:
        if len(e_lst) == 0:
            continue
        e_arr = e_lst[0]
        e_str = e_arr[0]
        assert e_lst.tag == 'lst' and len(e_lst) == 1 \
            and e_arr.tag == 'arr' and e_arr.attrib['name'] == 'title' and len(e_arr) == 1 \
            and e_str.tag == 'str'
        work_key = e_lst.attrib['name']
        highlight_titles[work_key] = e_str.text.replace('em>','b>')
    return highlight_titles

def read_facets(root):
    e_facet_counts = root.find("lst[@name='facet_counts']")
    e_facet_fields = e_facet_counts.find("lst[@name='facet_fields']")
    facets = {}
    for e_lst in e_facet_fields:
        assert e_lst.tag == 'lst'
        name = e_lst.attrib['name']
        facets[name] = [(e.attrib['name'], e.text) for e in e_lst]
    return facets

def search(param = {}, facets=True, rows=50, merge=False, show_total=True):
    q_title = param.get('title', None)
    q_author = param.get('author', None)
    q_all = not param or (not q_author and q_title == '*')
    q_language = param.get('language', [])
    q_author_facet = param.get('author_facet', [])
    q_work_key = param.get('key', None)
    q_author_key = param.get('author_key', None)
    page = int(param.get('page', 1))
    sort = param.get('sort', None)
    if 'has_fulltext' in param:
        q_has_fulltext = param['has_fulltext'].lower()
        if q_has_fulltext not in ('true', 'false'):
            q_has_fulltext = None
    else:
        q_has_fulltext = None
    
    query_params = {
        'title': url_quote(q_title),
        'author': url_quote(q_author),
    }

    q_list = []
    if q_title:
        q_list.append('title:(' + q_title + ')')
    if q_author:
        q_list.append('(author_name:(' + q_author + ') OR author_key:(' + q_author + '))')
    if q_work_key:
        q_list.append('key:(' + q_work_key + ')')
    if q_author_key:
        q_list.append('author_key:(' + q_author_key + ')')
    offset = rows * (page - 1)
    q = url_quote(' AND '.join(q_list)) if not q_all else '*:*'

    solr_select = solr_select_url + "?indent=on&version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*%%2Cscore&qt=standard&wt=standard&explainOther=&hl=on&hl.fl=title" % (q, offset, rows)
    if facets:
        solr_select += "&facet=true&facet.field=has_fulltext&facet.field=author_facet&facet.field=language&facet.field=publisher_facet"
    if q_has_fulltext:
        query_params['has_fulltext'] = q_has_fulltext
        solr_select += '&fq=has_fulltext:%s' % q_has_fulltext
    if q_language:
        query_params['language'] = q_language
        solr_select += ''.join('&fq=language:%s' % l for l in q_language)
    if q_author_facet:
        query_params['author_facet'] = q_author_facet
        solr_select += ''.join('&fq=author_key:"%s"' % a for a in q_author_facet)

    ret = 'Sort by: '
    sort_url = search_url(query_params) # first page
    if sort == 'score':
        ret += '<a href="%s">number of editions</a> OR <b>relevance</b>' % sort_url
    else:
        solr_select += "&sort=edition_count+desc"
        ret += '<b>number of editions</b> OR <a href="%s&sort=score">relevance</a>' % sort_url

    ret += '<p>\n'

    # FIXME: merge
    # if len(param.get('author_facet', [])) == 1 and not merge:
    #    ret += '<a href="/merge%s">merge works</a><p>' % search_url(query_params)

    if merge:
        ret += '<form>'
        ret += '<input type="submit" value="Merge"><p>'

    if 'debug' in param:
        ret += esc(solr_select) + '<br>\n'


    reply = urllib.urlopen(solr_select)
    root = parse(reply).getroot()
    result = root.find('result')
    if result is None:
        return esc(solr_select) + '<br>no results found'
    num_found = int(result.attrib['numFound'])

    highlight_titles = read_highlight(root)
    if facets:
        facet_counts = read_facets(root)

        ebook_facet = dict(facet_counts['has_fulltext'])
    if facets:
        ret += '<table><tr><td valign="top">'
        ret += '<table>'
        ret += '<tr><td colspan="3"><b>eBook?</b></td></tr>'
        if q_has_fulltext == 'true':
            ret += '<tr><td colspan="2">yes <a href="%s">x</a></td><td align="right">%s</td>' % (search_url(query_params) + "&has_fulltext=true", ebook_facet.get('true', '0'))
        else:
            ret += '<tr><td colspan="2"><a href="%s">yes</a></td><td align="right">%s</td>' % (search_url(query_params) + "&has_fulltext=true", ebook_facet.get('true', '0'))

        ret += '<tr><td colspan="2"><a href="%s">no</a></td><td align="right">%s</td>' % (search_url(query_params) + "&has_fulltext=false", ebook_facet.get('false', '0'))
        header_map = {
            'language': 'Language',
            'author_facet': 'Author',
        }
        for header, counts in facet_counts.items():
            if header in ('has_fulltext', 'publisher_facet'):
                continue
            label = header_map.get(header, header)
            if header == 'author_facet':
                ret += '<tr><td colspan="3"><b>Author</b></td></tr>'
                # FIXME: merge
                # ret += '<tr><td colspan="3"><b>Author</b> - <a href="/author_merge?k=%s">(merge authors)</a></td></tr>' % keys
            else:
                ret += '<tr><td colspan="3"><b>%s</b></td></tr>' % label
            for k, count in counts[:10]:
                if count == '0':
                    continue
                if header == 'language':
                    if k in q_language:
                        ret += '<tr><td colspan="2">%s <a href="%s">x</a></td><td align="right">%s</td>' % (k, search_url(query_params, set([('language', k)])), count)
                    else:
                        ret += '<tr><td colspan="2"><a href="%s&language=%s">%s</a></td><td align="right">%s</td>' % (search_url(query_params), k, k, count)
                elif header == 'author_facet':
                    akey, aname = eval(k)
                    if akey in q_author_facet:
                        ret += '<tr><td>%s</td><td> <a href="%s">x</a> <a href="http://upstream.openlibrary.org/authors/%s">#</a></td><td align="right">%s</td>' % (tidy_name(aname), search_url(query_params, set([('author_facet', akey)])), akey[3:], count)
                    else:
                        ret += '<tr><td><a href="%s&author_facet=%s">%s</a></td><td><a href="http://upstream.openlibrary.org/authors/%s">#</a></td><td align="right">%s</td>' % (search_url(query_params), akey, tidy_name(aname), akey[3:], count)
                else:
                    ret += '<tr><td>%s</td><td>%s</td>' % (esc(k), count)
        ret += '</table>'
        ret += '</td><td valign="top">'

#    ret += '<br>' + solr_select + '<br>'
    if show_total:
        ret += 'Number found: %d<br>' % num_found
    ret += '<table>'
    if facets and ebook_facet.get('true', None) != '0':
        ret += '<tr><td colspan="4" align="right">eBook?</td></tr>'
    for doc in result:
        work_key = doc.find("str[@name='key']").text
        title = doc.find("str[@name='title']").text
        e_fs = doc.find("arr[@name='first_sentence']")
        first_sentences = [e.text for e in (e_fs if e_fs is not None else [])]
        fulltext = doc.find("bool[@name='has_fulltext']").text == 'true'
        edition_count = int(doc.find("int[@name='edition_count']").text)
        e_ia = doc.find("arr[@name='ia']")
        ia_list = [e.text for e in (e_ia if e_ia is not None else [])]
        author_key = []
        author_name = []
        for e_str in doc.find("arr[@name='author_key']"):
            assert e_str.tag == 'str'
            author_key.append(e_str.text)
        for e_str in doc.find("arr[@name='author_name']"):
            assert e_str.tag == 'str'
            author_name.append(e_str.text)
        #authors = ', '.join('<a href="http://upstream.openlibrary.org%s">%s</a> (<a href="?author=&quot;%s&quot;">search</a>)' % (i, tidy_name(j), j) for i, j in zip(author_key, author_name))
        authors = ', '.join('<a href="http://upstream.openlibrary.org%s">%s</a> (<a href="?author=&quot;%s&quot;">search</a>)' % (i, j, j) for i, j in zip(author_key, author_name))
        ret += '<tr>'
        if merge:
            ret += '<td><input type="checkbox" name="merge" value="%s"></td>' % work_key[7:]
        ret += u'<td><a href="http://upstream.openlibrary.org%s">%s</a>' % (work_key, highlight_titles.get(work_key, title))
        ret += '</td>'
        ret += '<td>by %s</td>' % authors
        ret += '<td align="right">%d&nbsp;editions</td>' % edition_count
        if fulltext:
            # FIXME: scanned books
            # ret += '<td align="right"><a href="%s">%d&nbsp;eBook%s</td>' % (work_key, len(ia_list), "s" if len(ia_list) != 1 else "")
            ret += '<td align="right">%d&nbsp;eBook%s</td>' % (len(ia_list), "s" if len(ia_list) != 1 else "")
        ret += '</tr>'
        if first_sentences:
            ret += '<tr>'
            if merge:
                ret += '<td></td>'
            ret += u'<td colspan="2">%s</td></tr>' % '<br>'.join(esc(i) for i in first_sentences)
    ret += '</table>'
    if merge:
        ret += '<input type="submit" value="Merge"><p>'
        ret += '</form>'
    if facets:
        ret += '</td></tr></table>'

    if page * rows < num_found:
        next_page_url = search_url(query_params) + '&page=%d' % (page + 1,)

        ret += '<br><a href="%s">Next page</a>' % esc(next_page_url)

    return ret

def textfield(i, name):
    if i.get(name, None):
        return '<input name="%s" value="%s" size="30">' % (name, esc(i.get(name)))
    else:
        return '<input name="%s" size="30">' % name

class work_search(delegate.page):
    def GET(self):
        i = web.input(language=[], author_facet=[])
        param = {}
        for p in 'title', 'author', 'page', 'sort', 'has_fulltext', 'language', 'author_facet', 'debug':
            if i.get(p, None):
                param[p] = i.get(p)

        ret = '<a name="top"></a>'
        ret += '<form><table>'
        ret += '<tr><td>Title</td><td>' + textfield(i, 'title') + '</td></tr>\n'
        ret += '<tr><td>Author</td><td>' + textfield(i, 'author') + '</td></tr>\n'
        ret += '<tr><td></td><td><input type="submit" value="Search"></td></table></form>'
        if param.get('title', None) or param.get('author', None) or 'author_facet' in param:
            ret += search(param, facets=True)
        return ret
