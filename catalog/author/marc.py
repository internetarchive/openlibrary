from catalog.infostore import get_site
from catalog.marc.db.web_marc_db import search_query
from catalog.get_ia import get_data
from catalog.marc.fast_parse import get_all_subfields, get_tag_lines, get_first_tag, get_subfields
import sys
site = get_site()

name = sys.argv[1] # example: 'Leonardo da Vinci'
author_keys = site.things({'type': '/type/author', 'name': name})
print len(author_keys), 'authors found'

edition_keys = set()
for ak in author_keys:
    edition_keys.update(site.things({'type': '/type/edition', 'authors': ak}))
print len(edition_keys), 'editions found'

locs = set()
for ek in edition_keys:
    e = site.withKey(ek)
    for i in e.isbn_10 if e.isbn_10 else []:
        locs.update(search_query('isbn', i))
    for i in e.lccn if e.lccn else []:
        locs.update(search_query('lccn', i))
    for i in e.oclc_numbers if e.oclc_numbers else []:
        locs.update(search_query('oclc', i))
print len(locs), 'MARC records found'

def ldv(line):
    for s in ('1452', '1519', 'eonard', 'inci'):
        if line.find(s) != -1:
            return True
    return False
    
for loc in locs:
#    print loc
    data = get_data(loc)
    if not data:
        print "couldn't get"
        continue
    line = get_first_tag(data, set(['100', '110', '111']))
    if line and ldv(line):
        print list(get_all_subfields(line))

    line = get_first_tag(data, set(['700', '710', '711']))
    if line and ldv(line):
        print list(get_all_subfields(line))
