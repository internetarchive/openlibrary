#!/usr/local/bin/python2.5
import re, sys, codecs, web
from openlibrary.catalog.get_ia import get_from_archive
from openlibrary.catalog.marc.fast_parse import get_subfield_values, get_first_tag, get_tag_lines, get_subfields
from openlibrary.catalog.utils.query import query_iter, set_staging, query
from openlibrary.catalog.utils import mk_norm
from openlibrary.catalog.read_rc import read_rc
from collections import defaultdict
from pprint import pprint, pformat
from catalog.utils.edit import fix_edition
import urllib
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, Reference
import olapi

rc = read_rc()

ol = OpenLibrary("http://dev.openlibrary.org")
ol.login('EdwardBot', rc['EdwardBot'])

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon|etc)\.$')

base_url = "http://dev.openlibrary.org"
query_url = base_url + "/query.json?query="

work_num = 184076

set_staging(True)

def withKey(key):
    url = base_url + key + ".json"
    return urllib.urlopen(url).read()

def find_new_work_key():
    global work_num
    while 1:
        key = "/w/OL%dW" % work_num
        ret = withKey(key)
        if ret.startswith("Not Found:"):
            return work_num
        work_num += 1

def next_work_key():
    global work_num
    key = "/w/OL%dW" % work_num
    ret = withKey(key)
    while not ret.startswith("Not Found:"):
        work_num += 1
        key = "/w/OL%dW" % work_num
        ret = withKey(key)
    work_num += 1
    return key

# sample title: The Dollar Hen (Illustrated Edition) (Dodo Press)
re_parens = re.compile('^(.*?)(?: \(.+ (?:Edition|Press)\))+$')

def top_rev_wt(d):
    d_sorted = sorted(d.keys(), cmp=lambda i, j: cmp(d[j], d[i]) or cmp(len(j), len(i)))
    return d_sorted[0]

def books_query(akey): # live version
    q = {
        'type':'/type/edition',
        'authors': akey,
        '*': None
    }
    return query_iter(q)

def freq_dict_top(d):
    return sorted(d.keys(), reverse=True, key=lambda i:d[i])[0]


def get_work_title(e):
    if e['key'] not in marc:
        assert not e.get('work_titles', [])
        return
#    assert e.get('work_titles', [])
    data = marc[e['key']][1]
    line = get_first_tag(data, set(['240']))
    if not line:
        assert not e.get('work_titles', [])
        return
    return ' '.join(get_subfield_values(line, ['a'])).strip('. ')

def get_books(akey):
    for e in books_query(akey):
        if not e.get('title', None):
            continue
        if len(e.get('authors', [])) != 1:
            continue
#        if 'works' in e:
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

        if 'languages' in e:
            book['lang'] = [l['key'][3:] for l in e['languages']]

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

def find_works(akey):
    equiv = defaultdict(int) # title and work title pairs
    norm_titles = defaultdict(int) # frequency of titles
    books_by_key = {}
    books = []
    rev_wt = defaultdict(lambda: defaultdict(int))

    for book in get_books(akey):
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
        if work_count < 2:
            continue
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

def add_works(akey, works):
    queue = []
    for w in works:
        w['key'] = next_work_key()
        q = {
            'authors': [akey],
            'create': 'unless_exists',
            'type': '/type/work',
            'key': w['key'],
            'title': w['title']
        }
        #queue.append(q)
        print ol.write(q, comment='create work')
        for ekey in w['editions']:
            e = ol.get(ekey)
            fix_edition(ekey, e, ol)
            e['works'] = [Reference(w['key'])]
            try:
                ol.save(ekey, e, 'found a work')
            except olapi.OLError:
                print ekey
                print e
                raise

def by_authors():
    find_new_work_key()

    skipping = False
    skipping = True
    q = { 'type':'/type/author', 'name': None, 'works': None }
    for a in query_iter(q, offset=215000):
        akey = a['key']
        if skipping:
            print 'skipping:', akey, a['name']
            if akey == '/a/OL218496A':
                skipping = False
            continue

        q = {
            'type':'/type/work',
            'authors': akey,
        }
        if query(q):
            print akey, `a['name']`, 'has works'
            continue

    #    print akey, a['name']
        found = find_works(akey)
        works = [i for i in found if len(i['editions']) > 2]
        if works:
            #open('found/' + akey[3:], 'w').write(`works`)
            print akey, `a['name']`
            #pprint(works)
            #print_works(works)
            add_works(akey, works)
            print

by_authors()
sys.exit(0)
akey = '/a/OL27695A'
akey = '/a/OL2527041A'
akey = '/a/OL17005A'
akey = '/a/OL117645A'
print akey
works = list(find_works(akey))
pprint(works)
