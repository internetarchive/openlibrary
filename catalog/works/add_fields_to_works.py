#!/usr/local/bin/python2.5
import sys, urllib, re
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary
import simplejson as json
from collections import defaultdict
from catalog.read_rc import read_rc
from catalog.utils.query import query, query_iter, set_staging, base_url
from catalog.utils import mk_norm, get_title

set_staging(True)

rc = read_rc()

ol = OpenLibrary(base_url())
ol.login('EdwardBot', rc['EdwardBot'])

re_year = re.compile('(\d{3,})$')

queue = []

def iter_works(fields):
    q = { 'type':'/type/work', 'key': None }
    for f in fields:
        q[f] = None
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
        print w['key'], `w['title']`, first
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
        print w['key'], `w['title']`, first, len(lang)
        q = {
            'key': w['key'],
            f: { 'connect': 'update_list', 'value': [first]}
        }
        queue.append(q)
        if len(queue) == 200:
            print ol.write(queue, comment='add original language')
            queue = []
    print ol.write(queue, comment='add original language')

def genres():
    f = 'genres'
    queue = []
    for w in iter_works([f, 'title']):
        if w.get(f, None):
            continue
        q = { 'type':'/type/edition', 'works': w['key'], f: None }
        editions = [[g.strip('.') for g in e['genres']] for e in query_iter(q) \
            if e.get(f, None) and not any('ranslation' in i for i in e[f])]
        if not editions:
            continue
        first = editions[0]
        assert 'ranslation' not in first
        if any(e != first for e in editions):
            continue
        print len(queue) + 1, w['key'], `w['title']`, first, len(editions)
        q = {
            'key': w['key'],
            f: { 'connect': 'update_list', 'value': first}
        }
        queue.append(q)
        if len(queue) == 200:
            print ol.write(queue, comment='add genre')
            queue = []
    print ol.write(queue, comment='add genre')

genres()
