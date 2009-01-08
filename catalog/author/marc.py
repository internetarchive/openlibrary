from catalog.infostore import get_site
from catalog.marc.db.web_marc_db import search_query
from catalog.get_ia import get_data
site = get_site()

name = sys.argv[1] # example: 'Leonardo da Vinci'
author_keys = site.things({'type': '/type/author', 'name': name})
editions_keys = set()
for ak in author_keys:
    edition_keys.update(site.things({'type': '/type/edition', 'authors': ak}))

locs = set()
for ek in edition_keys:
    e = site.withKey(ek)
    for i in e.isbn_10 if e.isbn_10 else []:
        locs.update(search_query('isbn', i))
    for i in e.lccn if e.lccn else []:
        locs.update(search_query('lccn', i))
    for i in e.oclc_numbers if e.oclc_numbers else []:
        locs.update(search_query('oclc', i))
    
for loc in locs:
    print loc
    line = get_first_tag(data, set(['100', '110', '111']))
    print list(get_all_subfields(line))
