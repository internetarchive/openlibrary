#!/usr/bin/python2.5

import sys, codecs, re
from collections import defaultdict
from catalog.merge.normalize import normalize
from catalog.infostore import get_site

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

site = get_site()

def books_by_author(key):
    q = { 'authors': key, 'type': '/type/edition' }
    return (site.withKey(k) for k in site.things(q))

def get_full_title(edition):
    return (edition.title_prefix or '') + edition.title

re_end_paren = re.compile('^(.*) ?\(.*?\)$')

mark_twain = '/a/OL18319A'
carl_sagan = '/a/OL450295A'

titles = defaultdict(list)
for edition in books_by_author(carl_sagan):
    full_title = get_full_title(edition)
    m = re_end_paren.match(full_title)
    if m:
        full_title = m.group(1)

    titles[normalize(full_title)].append(edition)

for k, v in titles.iteritems():
    print len(v), k
