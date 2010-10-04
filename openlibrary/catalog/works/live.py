#!/usr/bin/python

# find works and create pages on production

import re, sys, codecs, web
from openlibrary.catalog.get_ia import get_from_archive, get_data
from openlibrary.catalog.marc.fast_parse import get_subfield_values, get_first_tag, get_tag_lines, get_subfields, BadDictionary
from openlibrary.catalog.utils.query import query_iter, set_staging, query
from openlibrary.catalog.utils import mk_norm
from openlibrary.catalog.read_rc import read_rc
from collections import defaultdict
from pprint import pprint, pformat
from openlibrary.catalog.utils.edit import fix_edition
from openlibrary.catalog.importer.db_read import get_mc
import urllib2
from openlibrary.api import OpenLibrary, Reference
from lxml import etree
from time import sleep, time

rc = read_rc()

ol = OpenLibrary("http://openlibrary.org")
ol.login('WorkBot', rc['WorkBot'])

def write_log(cat, key, title):
    print >> fh_log, (("%.2f" % time()), cat, key, title)
    fh_log.flush()

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon|etc)\.$')

re_ia_marc = re.compile('^(?:.*/)?([^/]+)_(marc\.xml|meta\.mrc)(:0:\d+)?$')

ns = '{http://www.loc.gov/MARC21/slim}'
ns_leader = ns + 'leader'
ns_data = ns + 'datafield'

def has_dot(s):
    return s.endswith('.') and not re_skip.search(s)

#set_staging(True)

# sample title: The Dollar Hen (Illustrated Edition) (Dodo Press)
re_parens = re.compile('^(.*?)(?: \(.+ (?:Edition|Press)\))+$')

def key_int(key):
    # extract the number from a key like /a/OL1234A
    return int(web.numify(key))

def update_work_edition(ekey, wkey, use):
    print (ekey, wkey, use)
    e = ol.get(ekey)
    works = []
    for w in e['works']:
        if w == wkey:
            if use not in works:
                works.append(Reference(use))
        else:
            if w not in works:
                works.append(w)

    if e['works'] == works:
        return
    print 'before:', e['works']
    print 'after:', works
    e['works'] = works
    print ol.save(e['key'], e, 'remove duplicate work page')

def top_rev_wt(d):
    d_sorted = sorted(d.keys(), cmp=lambda i, j: cmp(d[j], d[i]) or cmp(len(j), len(i)))
    return d_sorted[0]

def books_query(akey): # live version
    q = {
        'type':'/type/edition',
        'authors': akey,
        'source_records': None,
        'title': None,
        'work_title': None,
        'languages': None,
        'title_prefix': None,
        'subtitle': None,
    }
    return query_iter(q)

def freq_dict_top(d):
    return sorted(d.keys(), reverse=True, key=lambda i:d[i])[0]

def get_marc_src(e):
    mc = get_mc(e['key'])
    if mc and mc.startswith('amazon:'):
        mc = None
    if mc and mc.startswith('ia:'):
        yield 'ia', mc[3:]
    elif mc:
        m = re_ia_marc.match(mc)
        if m:
            #print 'IA marc match:', m.group(1)
            yield 'ia', m.group(1)
        else:
            yield 'marc', mc
    source_records = e.get('source_records', [])
    if not source_records:
        return
    for src in source_records:
        if src.startswith('ia:'):
            if not mc or src != mc:
                yield 'ia', src[3:]
            continue
        if src.startswith('marc:'):
            if not mc or src != 'marc:' + mc:
                yield 'marc', src[5:]
            continue

def get_ia_work_title(ia):
    url = 'http://www.archive.org/download/' + ia + '/' + ia + '_marc.xml'
    try:
        root = etree.parse(urllib2.urlopen(url)).getroot()
    except KeyboardInterrupt:
        raise
    except:
        #print 'bad XML', ia
        #print url
        return
    #print etree.tostring(root)
    e = root.find(ns_data + "[@tag='240']")
    if e is None:
        return
    #print e.tag
    wt = ' '.join(s.text for s in e if s.attrib['code'] == 'a' and s.text)
    return wt

def get_work_title(e):
    # use first work title we find in source MARC records
    wt = None
    for src_type, src in get_marc_src(e):
        if src_type == 'ia':
            wt = get_ia_work_title(src)
            if wt:
                break
            continue
        assert src_type == 'marc'
        data = None
        #print 'get from archive:', src
        try:
            data = get_data(src)
        except ValueError:
            print 'bad record source:', src
            print 'http://openlibrary.org' + e['key']
            continue
        except urllib2.HTTPError, error:
            print 'HTTP error:', error.code, error.msg
            print e['key']
        if not data:
            continue
        try:
            line = get_first_tag(data, set(['240']))
        except BadDictionary:
            print 'bad dictionary:', src
            print 'http://openlibrary.org' + e['key']
            continue
        if line:
            wt = ' '.join(get_subfield_values(line, ['a'])).strip('. ')
            break
    if wt:
        return wt
    if not e.get('work_titles', []):
        return
    print 'work title in MARC, but not in OL'
    print 'http://openlibrary.org' + e['key']
    return e['work_titles'][0]

def get_books(akey, query):
    for e in query:
        if not e.get('title', None):
            continue
#        if len(e.get('authors', [])) != 1:
#            continue
        if 'title_prefix' in e and e['title_prefix']:
            prefix = e['title_prefix']
            if prefix[-1] != ' ':
                prefix += ' '
            title = prefix + e['title']
        else:
            title = e['title']

        title = title.strip(' ')
        if has_dot(title):
            title = title[:-1]
        if title.strip('. ') in ['Publications', 'Works', 'Report', \
                'Letters', 'Calendar', 'Bulletin', 'Plays', 'Sermons', 'Correspondence']:
            continue

        m = re_parens.match(title)
        if m:
            title = m.group(1)

        n = mk_norm(title)

        book = {
            'title': title,
            'norm_title': n,
            'key': e['key'],
        }

        lang = e.get('languages', [])
        if lang:
            book['lang'] = [l['key'][3:] for l in lang]

        if e.get('table_of_contents', None):
            if isinstance(e['table_of_contents'][0], basestring):
                book['table_of_contents'] = e['table_of_contents']
            else:
                assert isinstance(e['table_of_contents'][0], dict)
                if e['table_of_contents'][0]['type'] == '/type/text':
                    book['table_of_contents'] = [i['value'] for i in e['table_of_contents']]

        wt = get_work_title(e)
        if not wt:
            yield book
            continue
        if wt in ('Works', 'Selections'):
            yield book
            continue
        n_wt = mk_norm(wt)
        book['work_title'] = wt
        book['norm_wt'] = n_wt
        yield book

def build_work_title_map(equiv, norm_titles):
    # map of book titles to work titles
    title_to_work_title = defaultdict(set)
    for (norm_title, norm_wt), v in equiv.items():
        if v != 1:
            title_to_work_title[norm_title].add(norm_wt)

    title_map = {}
    for title, v in title_to_work_title.items():
        if len(v) == 1:
            title_map[title] = list(v)[0]
            continue
        most_common_title = max(v, key=lambda i:norm_titles[i])
        if title != most_common_title:
            title_map[title] = most_common_title
        for i in v:
            if i != most_common_title:
                title_map[i] = most_common_title
    return title_map

def find_works(akey, book_iter):
    equiv = defaultdict(int) # title and work title pairs
    norm_titles = defaultdict(int) # frequency of titles
    books_by_key = {}
    books = []
    rev_wt = defaultdict(lambda: defaultdict(int))

    for book in book_iter:
        if 'norm_wt' in book:
            pair = (book['norm_title'], book['norm_wt'])
            equiv[pair] += 1
            rev_wt[book['norm_wt']][book['work_title']] +=1
        norm_titles[book['norm_title']] += 1
        books_by_key[book['key']] = book
        books.append(book)

    title_map = build_work_title_map(equiv, norm_titles)

    works = defaultdict(lambda: defaultdict(list))
    work_titles = defaultdict(list)
    for b in books:
        if 'eng' not in b.get('lang', []) and 'norm_wt' in b:
            work_titles[b['norm_wt']].append(b['key'])
            continue
        n = b['norm_title']
        title = b['title']
        if n in title_map:
            n = title_map[n]
            title = top_rev_wt(rev_wt[n])
        works[n][title].append(b['key'])

    works = sorted([(sum(map(len, w.values() + [work_titles[n]])), n, w) for n, w in works.items()])

    for work_count, norm, w in works:
#        if work_count < 2:
#            continue
        first = sorted(w.items(), reverse=True, key=lambda i:len(i[1]))[0][0]
        titles = defaultdict(int)
        for key_list in w.values():
            for ekey in key_list:
                b = books_by_key[ekey]
                title = b['title']
                titles[title] += 1
        keys = work_titles[norm]
        for values in w.values():
            keys += values
        assert work_count == len(keys)
        title = max(titles.keys(), key=lambda i:titles[i])
        toc = [(k, books_by_key[k].get('table_of_contents', None)) for k in keys]
        yield {'title': first, 'editions': keys, 'toc': dict((k, v) for k, v in toc if v)}

def print_works(works):
    for w in works:
        print len(w['editions']), w['title']

def toc_items(toc_list):
    return [{'title': unicode(item), 'type': Reference('/type/toc_item')} for item in toc_list] 

def add_works(works):
    q = []
    for w in works:
        cur = {
            'authors': [{'author': Reference(w['author'])}],
            'type': '/type/work',
            'title': w['title']
        }
        if 'subjects' in w:
            cur['subjects'] = w['subjects']
        q.append(cur)
    try:
        return ol.new(q, comment='create work page')
    except:
        print q
        raise

def add_work(akey, w):
    q = {
        'authors': [{'author': Reference(akey)}],
        'type': '/type/work',
        'title': w['title']
    }
    try:
        wkey = ol.new(q, comment='create work page')
    except:
        print q
        raise
    write_log('work', wkey, w['title'])
    assert isinstance(wkey, basestring)
    for ekey in w['editions']:
        e = ol.get(ekey)
        fix_edition(ekey, e, ol)
        #assert 'works' not in e
        write_log('edition', ekey, e.get('title', 'title missing'))
        e['works'] = [Reference(wkey)]
        yield e

def save_editions(queue):
    print 'saving'
    try:
        print ol.save_many(queue, 'add edition to work page')
    except:
        print 'ol.save_many() failed, trying again in 30 seconds'
        sleep(30)
        print ol.save_many(queue, 'add edition to work page')
    print 'saved'

def merge_works(work_keys):
    use = "/works/OL%dW" % min(key_int(w) for w in work_keys)
    for wkey in work_keys:
        if wkey == use:
            continue
        w_query = {'type':'/type/edition', 'works':wkey, 'limit':False}
        for e in ol.query(w_query): # returns strings?
            print e
            update_work_edition(e, wkey, use)
        w = ol.get(wkey)
        assert w['type'] == '/type/work'
        w['type'] = '/type/redirect'
        w['location'] = use
        print ol.save(wkey, w, 'delete duplicate work page')

def update_edition(ekey, wkey):
    e = ol.get(ekey)
    fix_edition(ekey, e, ol)
    write_log('edition', ekey, e.get('title', 'title missing'))
    if e.get('works', []):
        assert len(e['works']) == 1
        if e['works'][0] != wkey:
            print 'e:', e
            print 'wkey:', wkey
            print 'ekey:', ekey
            print 'e["works"]:', e['works']
            #merge_works([e['works'][0], wkey])
        #assert e['works'][0] == wkey
        return None
    e['works'] = [Reference(wkey)]
    return e

def run_queue(queue):
    work_keys = add_works(queue)
    for w, wkey in zip(queue, work_keys):
        w['key'] = wkey
        write_log('work', wkey, w['title'])
        for ekey in w['editions']:
            e = update_edition(ekey, wkey)
            if e:
                yield e

def get_work_key(title, akey):
    q = {
        'type': '/type/work',
        'title': title,
        'authors': None,
    }
    matches = [w for w in ol.query(q) if any(a['author'] == akey for a in w['authors'])]
    if not matches:
        return None
    if len(matches) != 1:
        print 'time to fix duplicate works'
        print `title`
        print 'http://openlibrary.org' + akey
        print matches
    assert len(matches) == 1
    return matches[0]['key']

def by_authors():
    skip = '/a/OL25755A'
    q = { 'type':'/type/author', 'name': None }
    for a in query_iter(q):
        akey = a['key']
        if skip:
            if akey == skip:
                skip = None
            else:
                continue
        write_log('author', akey, a.get('name', 'name missing'))

        works = find_works(akey, get_books(akey, books_query(akey)))
        print akey, `a['name']`

        for w in works:
            w['author'] = akey
            wkey = get_work_key(w['title'], akey)
            if wkey:
                w['key'] = wkey
            yield w

if __name__ == '__main__':
    fh_log = open('/1/edward/logs/WorkBot', 'a')
    edition_queue = []
    work_queue = []

    for w in by_authors():
        if 'key' in w:
            for ekey in w['editions']:
                e = update_edition(ekey, w['key'])
                if e:
                    edition_queue.append(e)
            continue

        work_queue.append(w)
        if len(work_queue) > 1000:
            for e in run_queue(work_queue):
                print e['key'], `e['title']`
                edition_queue.append(e)
                if len(edition_queue) > 1000:
                    save_editions(edition_queue)
                    edition_queue = []
                    sleep(5)
            work_queue = []

    print 'almost finished'
    for e in run_queue(work_queue):
        edition_queue.append(e)
    save_editions(edition_queue)
    print 'finished'

    fh_log.close()
