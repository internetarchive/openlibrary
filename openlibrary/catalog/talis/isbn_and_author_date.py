# read Talis, find books with ISBN and author date, add date to author

from catalog.read_rc import read_rc
from catalog.marc.fast_parse import *
from catalog.infostore import get_site
from catalog.merge.names import match_name
from catalog.marc.build_record import read_author_person

import re

site = get_site()

re_author_date_subfield = re.compile('\x1f[az]')
re_isbn_subfield = re.compile('\x1f[az]')

rc = read_rc()
filename = rc['marc_path'] + 'talis_openlibrary_contribution/talis-openlibrary-contribution.mrc'

seen = set()

def build_fields(data):
    fields = {}
    for tag, line in get_tag_lines(data, ['020', '100']):
        if tag in fields:
            return {}
        fields[tag] = line
    if '020' not in fields or '100' not in fields:
        return {}
    if fields['100'].find('\x1fd') == -1:
        return {}
    if not re_isbn_subfield.search(fields['020']):
        return {}
    return fields

def find_authors(isbn_list, name):
    edition_keys = []
    for isbn in isbn_list:
        edition_keys.extend(site.things({'type': '/type/edition', 'isbn_10': isbn}))
    authors = set()
    for k in edition_keys:
        t = site.withKey(k)
        if t.authors:
            authors.update(t.authors)
    for a in authors:
        if not match_name(a.name, name, last_name_only_ok=False):
            continue
        books = site.things({'type': '/type/edition', 'authors': a.key})
        print(repr(a.key, a.name, a.birth_date, a.death_date, len(books)))

for data, length in read_file(open(filename)):
    fields = build_fields(data)
    if not fields:
        continue
    isbn_list = read_isbn(fields['020'])
    if not isbn_list:
        continue

    if any(isbn in seen for isbn in isbn_list):
        continue
    seen.update(isbn_list)
    person = read_author_person(fields['100'])
    print list(get_all_subfields(fields['100']))
    print person
    print isbn_list
    find_authors(isbn_list, person['personal_name'])
#        fields.append(tag, list(get_all_subfields(line)))
