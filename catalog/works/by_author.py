#!/usr/local/bin/python2.5
import catalog.merge.normalize as merge
import sys, codecs, re
from catalog.get_ia import get_from_archive
from collections import defaultdict
from pprint import pprint
import urllib
import simplejson as json

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

base_url = "http://openlibrary.org:8080/"
query_url = base_url + "query.json?query="

def query(q):
    url = query_url + urllib.quote(json.dumps(q))
    return json.loads(urllib.urlopen(url).read())

def query_iter(q, limit=500, offset=0):
    q['limit'] = limit
    q['offset'] = offset
    while 1:
        ret = query(q)
        if not ret:
            return
        for i in query(q):
            yield i
        q['offset'] += limit

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

re_brackets = re.compile('^(.*)\[.*?\]$')

def mk_norm(title):
    m = re_brackets.match(title)
    if m:
        title = m.group(1)
    norm = merge.normalize(title).strip(' ')
    norm = norm.replace(' and ', ' ')
    if norm.startswith('the '):
        norm = norm[4:]
    elif norm.startswith('a '):
        norm = norm[2:]
    return norm.replace('-', '').replace(' ', '')

def freq_dict_top(d):
    return sorted(d.keys(), reverse=True, key=lambda i:d[i])[0]

def get_books(akey):
    q = {
        'type':'/type/edition',
        'authors': akey,
        '*': None
    }
    for num, e in enumerate(query_iter(q)):
#        print num, e['key'], e['title']

        if 'title' not in e and not e['title']:
            continue
        if 'works' in e:
            continue
        if 'title_prefix' in e and e['title_prefix']:
            prefix = e['title_prefix']
            if prefix[-1] != ' ':
                prefix += ' '
            title = prefix + e['title']
        else:
            title = e['title']

        if title.strip('. ') in ['Publications', 'Works', 'Report', \
                'Letters', 'Calendar', 'Bulletin']:
            continue

        n = mk_norm(title)

        book = {
            'title': title,
            'norm_title': n,
            'key': e['key'],
        }

        if 'languages' in e:
            book['lang'] = [l['key'][3:] for l in e['languages']]

        if 'work_titles' not in e:
            yield book
            continue
        wt = e['work_titles'][0].strip('. ')
        if wt in ('Works', 'Selections'):
            yield book
            continue
        n_wt = mk_norm(wt)
        book['work_title'] = wt
        book['norm_wt'] = n_wt
        yield book

def build_work_title_map(equiv, norm_titles):
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
    equiv = defaultdict(int)
    norm_titles = defaultdict(int)
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
            title = freq_dict_top(rev_wt[n])
        works[n][title].append(b['key'])

    works = sorted([(sum(map(len, w.values() + [work_titles[n]])), n, w) for n, w in works.items()])

    for work_count, norm, w in works:
        if work_count < 3:
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
        yield first, keys

def print_works(works):
    for title, keys in works:
        print len(keys), title

q = { 'type':'/type/author', 'name': None }
for a in query_iter(q):
    akey = a['key']
#    print akey, a['name']
    works = [i for i in find_works(akey) if i[1] > 3]
    if works:
        open('found/' + akey[3:], 'w').write(`works`)
        print akey, a['name']
        print_works(works)
        print
