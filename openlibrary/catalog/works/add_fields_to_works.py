#!/usr/local/bin/python2.5
import sys, urllib, re, codecs
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary
import simplejson as json
from collections import defaultdict
from catalog.read_rc import read_rc
from catalog.utils.query import query, query_iter, set_staging, base_url
from catalog.utils import mk_norm, get_title

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
set_staging(True)

rc = read_rc()

ol = OpenLibrary(base_url())
ol.login('EdwardBot', rc['EdwardBot'])

re_year = re.compile('(\d{3,})$')

queue = []

def iter_works(fields):
    q = { 'type':'/type/work', 'key': None }
    for f in fields: q[f] = None
    return query_iter(q)

def dates():
    f = 'first_publish_date'
    for w in iter_works([f, 'title']):
        if f in w:
            continue
        q = { 'type':'/type/edition', 'works': w['key'], 'publish_date': None }
        years = defaultdict(list)
        for e in query_iter(q):
            date = e.get('publish_date', None)
            if not date or date == '0000':
                continue
            m = re_year.match(date)
            if not m:
                continue
            year = int(m.group(1))
            years[year].append(e['key'])
        if not years:
            continue
        first = min(years.keys())
        assert first != 0
        print(w['key'], repr(w['title']), first)
        q = {
            'key': w['key'],
            f: { 'connect': 'update', 'value': str(first)}
        }
        queue.append(q)
        if len(queue) == 200:
            print ol.write(queue, comment='add first publish date')
            queue = []
    print ol.write(queue, comment='add first publish date')

def lang():
    f = 'original_languages'
    queue = []
    for w in iter_works([f, 'title']):
        if f in w and w[f]:
            continue
        q = {
            'type':'/type/edition',
            'works': w['key'],
            'languages': None,
            'title': None,
            'title_prefix': None
        }
        editions = [e for e in query_iter(q) if e['languages']]
        title = mk_norm(w['title'])
        if not editions or any(len(e['languages']) != 1 for e in editions):
            continue
        lang = [e['languages'][0]['key'] for e in editions if mk_norm(get_title(e)) == title]
        if len(lang) < 2:
            continue
        first = lang[0]
        if any(l != first for l in lang):
            continue
        print(w['key'], repr(w['title']), first, len(lang))
        q = {
            'key': w['key'],
            f: { 'connect': 'update_list', 'value': [first]}
        }
        queue.append(q)
        if len(queue) == 200:
            print ol.write(queue, comment='add original language')
            queue = []
    print ol.write(queue, comment='add original language')

def toc_items(toc_list):
    return [{'title': item, 'type': '/type/toc_item'} for item in toc_list]

def add_fields():
    comment = 'add fields to works'
    queue = []
    seen = set()
    fields = ['genres', 'first_sentence', 'dewey_number', \
            'lc_classifications', 'publish_date'] #, 'table_of_contents']
    for w in iter_works(fields + ['title']):
        if w['key'] in seen or all(w.get(f, None) for f in fields):
            continue
        seen.add(w['key'])
        q = { 'type':'/type/edition', 'works': w['key']}
        for f in fields: q[f] = None
        editions = list(query_iter(q))

        found = {}

        for f in fields:
            if not w.get(f, None):
                if f == 'publish_date':
                    years = defaultdict(list)
                    for e in editions:
                        date = e.get(f, None)
                        if not date or date == '0000':
                            continue
                        m = re_year.match(date)
                        if not m:
                            continue
                        year = int(m.group(1))
                        years[year].append(e['key'])
                    if years:
                        found[f] = str(min(years.keys()))
                    continue
                if f == 'genres':
                    found_list = [[g.strip('.') for g in e[f]] for e in editions \
                        if e.get(f, None) and not any('translation' in i for i in e[f])]
                if f == 'table_of_contents':
                    found_list = []
                    for e in query_iter(q):
                        if not e.get(f, None):
                            continue
                        toc = e[f]
                        print e['key'], toc
                        print e
                        print
                        if isinstance(toc[0], basestring):
                            found_list.append(toc_items(toc))
                        else:
                            assert isinstance(toc[0], dict)
                            if toc[0]['type'] == '/type/text':
                                found_list.append(toc_items([i['value'] for i in toc]))
                            else:
                                assert toc[0]['type']['key'] == '/type/toc_item'
                                found_list.append(toc)
                else:
                    found_list = [e[f] for e in query_iter(q) if e.get(f, None)]
                if found_list:
                    first = found_list[0]
                    if all(i == first for i in found_list):
                        found[f] = first

        if not found:
            continue

        print len(queue) + 1, w['key'], len(editions), w['title']
        print found

        q = { 'key': w['key'], }
        for f in fields:
            if not f in found:
                continue
            if f == 'publish_date':
                q['first_publish_date'] = { 'connect': 'update', 'value': found[f]}
            elif f == 'first_sentence':
                q[f] = { 'connect': 'update', 'value': found[f]}
            else:
                q[f] = { 'connect': 'update_list', 'value': found[f]}
        queue.append(q)
        if len(queue) == 200:
            print ol.write(queue, comment=comment)
            queue = []
    print ol.write(queue, comment=comment)

add_fields()
