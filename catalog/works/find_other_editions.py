#!/usr/local/bin/python2.5
import sys, codecs
from catalog.merge.names import match_name
from catalog.utils import fmt_author, get_title, mk_norm
from catalog.utils.query import query_iter, set_staging, withKey

# find duplicate authors and other editions of works

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
set_staging(True)

def other_editions(title, wkey, work_author):
    # look for other editions with the same title
    wakey = work_author['key']
    q = { 'type': '/type/edition', 'title': title }
    for k in 'works', 'title_prefix', 'key', 'authors':
        q[k] = None
    found = []
    for e in query_iter(q):
        if not e.get('authors', None):
            continue
        if e.get('works', None) and any(i['key'] == wkey for i in e['works']):
            continue
        if any(i['key'] == wakey for i in e['authors']):
            continue
        for akey in (a['key'] for a in e.get('authors', [])):
            a = withKey(akey)
            name = a.get('name', '')
            if match_name(name, work_author['name'], last_name_only_ok=True):
                yield (e, a)

q = { 'type':'/type/work' }
for k in 'key', 'title', 'authors':
    q[k] = None

for w in query_iter(q):
    wkey = w['key']
    titles = set([w['title']])
    q = { 'type': '/type/edition', 'works': wkey }
    for k in 'title', 'title_prefix', 'key', 'authors':
        q[k] = None

    wakey = w['authors'][0]['key']
    work_author = withKey(wakey)

    for e in query_iter(q):
        if not e.get('title', None): 
            continue
        titles.update([get_title(e), e['title']])

    found = []
    for title in titles:
        found += list(other_editions(title, wkey, work_author))

    if not found:
        continue
    print w
    print titles
    print wakey + ':', fmt_author(work_author)
    for e, a in found:
        print '  ', a['key'] + ": ", fmt_author(a)
        print '  ', e
    print
