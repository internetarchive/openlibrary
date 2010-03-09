#!/usr/bin/python

# find works and create pages on production

import re, sys, codecs, web
from openlibrary.solr.add_covers import add_cover_to_work
from openlibrary.solr.update_work import update_work, solr_update
from openlibrary.catalog.get_ia import get_from_archive, get_data
from openlibrary.catalog.marc.fast_parse import get_subfield_values, get_first_tag, get_tag_lines, get_subfields, BadDictionary
from openlibrary.catalog.utils.query import query_iter, withKey
from openlibrary.catalog.utils import mk_norm
from openlibrary.catalog.read_rc import read_rc
from collections import defaultdict
from pprint import pprint, pformat
from openlibrary.catalog.utils.edit import fix_edition
from openlibrary.catalog.importer.db_read import get_mc
from urllib import urlopen
from openlibrary.api import OpenLibrary, Reference
from lxml import etree
from time import sleep, time
from openlibrary.api import OpenLibrary, unmarshal, Reference
import simplejson as json

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('WorkBot', rc['WorkBot']) 

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon|etc)\.$')
re_work_key = re.compile('^/works/OL(\d+)W$')

re_ia_marc = re.compile('^(?:.*/)?([^/]+)_(marc\.xml|meta\.mrc)(:0:\d+)?$')

ns = '{http://www.loc.gov/MARC21/slim}'
ns_leader = ns + 'leader'
ns_data = ns + 'datafield'

def has_dot(s):
    return s.endswith('.') and not re_skip.search(s)

#set_staging(True)

# sample title: The Dollar Hen (Illustrated Edition) (Dodo Press)
re_parens = re.compile('^(.*?)(?: \(.+ (?:Edition|Press|Print|Novels|Mysteries|Book Series|Classics Library|Classics|Books)\))+$', re.I)

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
        'table_of_contents': None,
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
        root = etree.parse(urlopen(url)).getroot()
    except KeyboardInterrupt:
        raise
    except:
        print 'bad XML', ia
        print url
        return
    #print etree.tostring(root)
    e = root.find(ns_data + "[@tag='240']")
    if e is None:
        print 'no work title', ia
        print url
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
                wt = wt.strip('. ')
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
    print 'work title in OL, but not in MARC'
    print 'http://openlibrary.org' + e['key']
    return e['work_titles'][0].strip('. ')

# don't use any of these as work titles
bad_titles = ['Publications', 'Works', 'Report', \
    'Letters', 'Calendar', 'Bulletin', 'Plays', \
    'Sermons', 'Correspondence', 'Bills']

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
        title_and_subtitle = title
        if e.get('subtitle', None):
            title_and_subtitle += ' ' + e['subtitle']
        if title_and_subtitle in ['Publications', 'Works', 'Report', \
                'Letters', 'Calendar', 'Bulletin', 'Plays', \
                'Sermons', 'Correspondence', 'Bills']:
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
        if 'subtitle' in e:
            book['subtitle'] = e['subtitle']

        wt = get_work_title(e)
        if not wt:
            yield book
            continue
        if wt in bad_titles:
            yield book
            continue
        n_wt = mk_norm(wt)
        book['work_title'] = wt
        book['norm_wt'] = n_wt
        yield book

def build_work_title_map(equiv, norm_titles):
    # map of normalized book titles to normalized work titles
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

def get_first_version(key):
    return json.load(urlopen('http://openlibrary.org' + key + '.json?v=1'))

def get_existing_works(akey):
    q = {
        'type':'/type/work',
        'authors': {'author': {'key': akey}},
        'limit': 500,
    }
    seen = set()
    for wkey in ol.query(q):
        if wkey in seen:
            continue # skip dups
        w = ol.get(wkey)
        if w['type'] == '/type/redirect':
            continue
        yield w

def find_title_redirects(akey):
    title_redirects = {}
    for w in get_existing_works(akey):
        norm_wt = mk_norm(w['title'])
        q = {'type':'/type/redirect', 'location': str(w['key']), 'limit': 500}
        for r in map(get_first_version, ol.query(q)):
            if mk_norm(r['title']) == norm_wt:
                continue
            if r['title'] in title_redirects:
                assert title_redirects[r['title']] == w['title']
            title_redirects[r['title']] = w['title']
    return title_redirects

def find_works(akey, book_iter, existing={}):
    equiv = defaultdict(int) # normalized title and work title pairs
    norm_titles = defaultdict(int) # frequency of titles
    books_by_key = {}
    books = []
    # normalized work title to regular title
    rev_wt = defaultdict(lambda: defaultdict(int))

    print 'find_works'

    for book in book_iter:
        if 'norm_wt' in book:
            pair = (book['norm_title'], book['norm_wt'])
            equiv[pair] += 1
            rev_wt[book['norm_wt']][book['work_title']] +=1
        norm_titles[book['norm_title']] += 1
        books_by_key[book['key']] = book
        books.append(book)

    title_map = build_work_title_map(equiv, norm_titles)

    for a, b in existing.items():
        norm_a = mk_norm(a)
        norm_b = mk_norm(b)
        rev_wt[norm_b][norm_a] +=1
        title_map[norm_a] = norm_b

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
        toc_iter = ((k, books_by_key[k].get('table_of_contents', None)) for k in keys)
        toc = dict((k, v) for k, v in toc_iter if v)
        editions = [books_by_key[k] for k in keys]
        subtitles = defaultdict(lambda: defaultdict(int))
        edition_count = 0
        with_subtitle_count = 0
        for e in editions:
            edition_count += 1
            subtitle = e['subtitle'] or ''
            if subtitle != '':
                with_subtitle_count += 1
            norm_subtitle = mk_norm(subtitle)
            subtitles[norm_subtitle][subtitle] += 1
        #print len(editions), first
        use_subtitle = None
        for k, v in subtitles.iteritems():
            if k.strip(' .').lower() in ('', 'roman'):
                continue
            num = sum(v.values())
            overall = float(num) / float(edition_count)
            ratio = float(num) / float(with_subtitle_count)
            if ratio > 0.5:
                use_subtitle = freq_dict_top(v)
                #use_subtitle = dict(v)
            #print '  ', k, overall, ratio, num, dict(v)
        w = {'title': first, 'editions': editions}
        if use_subtitle:
            w['subtitle'] = use_subtitle
        if toc:
            w['toc'] = toc
        yield w

def print_works(works):
    for w in works:
        print len(w['editions']), w['title']
        print '   ', w.get('subtitle', None)

def books_from_cache():
    for line in open('book_cache'):
        yield eval(line)

def update_works(akey, do_updates = False)
    title_redirects = find_title_redirects(akey)
    works = find_works(akey, get_books(akey, books_query(akey)), existing=title_redirects)

    # we can now look up all works by an author   
    while True: # until redirects repaired
        q = {'type':'/type/edition', 'authors': akey, 'works': None}
        work_to_edition = defaultdict(set)
        edition_to_work = defaultdict(set)
        for e in query_iter(q):
            if e.get('works', None):
                for w in e['works']:
                    work_to_edition[w['key']].add(e['key'])
                    edition_to_work[e['key']].add(w['key'])

        work_title = {}
        fix_redirects = []
        for k, editions in work_to_edition.items():
            w = withKey(k)
            if w['type']['key'] == '/type/redirect':
                print 'redirect found'
                wkey = w['location']
                assert re_work_key.match(wkey)
                for ekey in editions:
                    e = withKey(ekey)
                    e['works'] = [Reference(wkey)]
                    fix_redirects.append(e)
                continue
            work_title[k] = w['title']
        if not fix_redirects:
            print 'no redirects left'
            break
        print 'save redirects'
        ol.save_many(fix_redirects, "merge works")

#    open('OL32983A_works', 'w').write(`list(works)`)

    all_existing = set()
    work_keys = []
    print 'edition_to_work'
    for k, v in edition_to_work.iteritems():
        print '  %s: %s' % (k, v)
    for w in works:
        print
        print w['title'], len(w['editions'])
        existing = set()
        for e in w['editions']:
            existing.update(edition_to_work[e['key']])
        print 'existing:', existing
        if not existing: # editions have no existing work
            if do_updates:
                wkey = ol.new({'title': w['title'], 'type': '/type/work'})
                work_keys.append(wkey)
                print 'new work:', wkey, `w['title']`
            else:
                print 'new work:', `w['title']`
            update = []
            for e in w['editions']:
                e = ol.get(e['key'])
                if do_updates:
                    e['works'] = [Reference(wkey)]
                update.append(e)
            if do_updates:
                ol.save_many(update, "add editions to new work")
        elif len(existing) == 1:
            key = list(existing)[0]
            work_keys.append(key)
            if work_title[key] == w['title']:
                print 'no change:', key, `w['title']`
            else:
                print 'new title:', key, `work_title[key]`, '->', `w['title']`
                print sorted(work_to_edition[key])
                print w['editions']
                existing_work = ol.get(key)
                existing_work['title'] = w['title']
                if do_updates:
                    ol.save(key, existing_work, 'update work title')
        else:
            use_key = min(existing, key=lambda i: int(re_work_key.match(i).group(1)))
            work_keys.append(use_key)
            print 'merge work:', key, `w['title']`, 'to', use_key
            update = [{'type': '/type/redirect', 'location': use_key, 'key': wkey} for wkey in existing if wkey != use_key]
            for wkey in existing:
                for ekey in work_to_edition[wkey]:
                    e = ol.get(ekey)
                    e['works'] = [Reference(use_key)]
                    update.append(e)
            if work_title[use_key] != w['title']:
                print 'update work title', `work_title[use_key]`, '->', `w['title']`
                existing_work = ol.get(use_key)
                existing_work['title'] = w['title']
                update.append(existing_work)
            if do_updates:
                ol.save_many(update, 'merge works')
        all_existing.update(existing)
        for wkey in existing:
            cur = work_title[wkey]
            print '  ', wkey, cur == w['title'], `cur`

    print len(work_to_edition), len(all_existing)
    assert len(work_to_edition) == len(all_existing)

    if not do_updates:
        return

    for key in work_keys:
        w = ol.get(key)
        add_cover_to_work(w)
        if 'cover_edition' not in w:
            print 'no cover found'
        update_work(withKey(key), debug=True)

    requests = ['<commit />']
    solr_update(requests, debug=True)

if __name__ == '__main__':
    akey = '/a/' + sys.argv[1]

    update_works(akey, do_updates=False)
