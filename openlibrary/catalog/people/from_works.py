from openlibrary.catalog.utils.query import query_iter, set_staging, get_mc
from openlibrary.catalog.utils import flip_name, pick_first_date
from openlibrary.catalog.get_ia import get_data
from openlibrary.catalog.marc.fast_parse import get_tag_lines, get_all_subfields, get_subfields

from pprint import pprint
from identify_people import read_people
import sys
from collections import defaultdict
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, unmarshal

#ol = OpenLibrary("http://dev.openlibrary.org")
#ol.login('EdwardBot', rc['EdwardBot']) 

set_staging(True)

def build_person_object(p, marc_alt):
    ab = [(k, v.strip(' /,;:')) for k, v in p if k in 'ab']

    name = ' '.join(flip_name(v) if k == 'a' else v for k, v in ab)
    c = ' '.join(v for k, v in p if k == 'c')
    of_count = c.count('of ')
    if of_count == 1 and 'of the ' not in c and 'Emperor of ' not in c:
        name += ' ' + c[c.find('of '):]
    elif ' ' not in name and of_count > 1:
        name += ', ' + c
    elif c.endswith(' of') or c.endswith(' de') and any(k == 'a' and ', ' in v for k, v in p):
        name = ' '.join(v for k, v in ab)
        c += ' ' + name[:name.find(', ')]
        name = name[name.find(', ') + 2:] + ', ' + c

    person = {}
    d = [v for k, v in p if k =='d']
    if d:
        person = pick_first_date(d)
    person['name'] = name
    person['sort_name'] = ' '.join(v for k, v in p if k == 'a')

    if any(k=='b' for k, v in p):
        person['numeration'] = ' '.join(v for k, v in p if k == 'b')

    if c:
        person['title'] = c
    person['marc'] = [p] + list(marc_alt)

    return person

def work_and_marc():
    i = 0
    for w in query_iter({'type': '/type/work', 'title': None}):
        marc = set()
        q = {'type': '/type/edition', 'works': w['key'], 'title': None, 'source_records': None}
        for e in query_iter(q):
            if e.get('source_records', []):
                marc.update(i[5:] for i in e['source_records'] if i.startswith('marc:'))
            mc = get_mc(e['key'])
            if mc and not mc.startswith('ia:') and not mc.startswith('amazon:'):
                marc.add(mc)
        if marc:
            yield w, marc


def read_works():
    i = 0
    pages = {}
    page_marc = {}

    for w, marc in work_and_marc():
        lines = []
        for loc in marc:
            data = get_data(loc)
            if not data:
                continue
            found = [v for k, v in get_tag_lines(data, set(['600']))]
            if found:
                lines.append((loc, found))
        if not lines:
            continue
        w['lines'] = lines
        i += 1
        print i, w['key'], w['title']

        try:
            people, marc_alt = read_people(j[1] for j in lines)
        except AssertionError:
            print w['lines']
            continue

        marc_alt_reverse = defaultdict(set)
        for k, v in marc_alt.items():
            marc_alt_reverse[v].add(k)

        w = ol.get(w['key'])
        w['subject_people'] = []
        for p, num in people.iteritems():
            print '  %2d %s' % (num, ' '.join("%s: %s" % (k, v) for k, v in p))
            print '     ', p
            if p in page_marc:
                w['subject_people'].append('/subjects/people/' + page_marc[p])
                continue
            obj = build_person_object(p, marc_alt_reverse.get(p, []))
            key = obj['name'].replace(' ', '_')
            full_key = '/subjects/people/' + key
            w['subject_people'].append(full_key)

            if key in pages:
                print key
                pages[key]['marc'].append(p)
                continue

            for m in obj['marc']:
                page_marc[m] = key

            pages[key] = obj
            obj_for_db = obj.copy()
            del obj_for_db['marc']
            obj_for_db['key'] = full_key
            print ol.save(full_key, obj_for_db, 'create a new person page')

        print ol.save(w['key'], w, 'add links to people that this work is about')

def from_sample():
    i = 0
    pages = {}
    page_marc = {}
    for line in open('sample'):
        i += 1
        w = eval(line)
        #print i, w['key'], w['title']
        people, marc_alt = read_people(j[1] for j in w['lines'])

        marc_alt_reverse = defaultdict(set)
        for k, v in marc_alt.items():
            marc_alt_reverse[v].add(k)

        for p, num in people.iteritems():
            if p in page_marc:
                continue
            obj = build_person_object(p, marc_alt_reverse.get(p, []))
            key = obj['name'].replace(' ', '_')
            for m in obj['marc']:
                page_marc[m] = key
            if key in pages:
                print key
                pages[key]['marc'].append(p)
            else:
                pages[key] = obj
                pprint(obj)

from_sample()
