from openlibrary.catalog.utils.query import query_iter, set_staging, get_mc
from openlibrary.catalog.get_ia import get_data
from openlibrary.catalog.marc.fast_parse import get_tag_lines, get_all_subfields, get_subfields

from pprint import pprint
from identify_people import read_people
from build_object import build_person_object
import sys
from collections import defaultdict

set_staging(True)

def work_and_marc():
    i = 0
    skip = True
    for w in query_iter({'type': '/type/work', 'title': None}):
        if skip:
            if w['key'] == '/w/OL56814W':
                skip = False
            else:
                continue
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
        else:
            print 'no marc:', w


def read_works():
    i = 0
    pages = {}
    page_marc = {}

    for work, marc in work_and_marc():
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
        work['lines'] = lines
        i += 1
        print i, work['key'], work['title']

        try:
            people, marc_alt = read_people(j[1] for j in lines)
        except AssertionError:
            print work['lines']
            continue
        except KeyError:
            print work['lines']
            continue

        marc_alt_reverse = defaultdict(set)
        for k, v in marc_alt.items():
            marc_alt_reverse[v].add(k)

        w = ol.get(work['key'])
        w['subject_people'] = []
        for p, num in people.iteritems():
            print '  %2d %s' % (num, ' '.join("%s: %s" % (k, v) for k, v in p))
            print '     ', p
            if p in page_marc:
                w['subject_people'].append({'key': '/subjects/people/' + page_marc[p]})
                continue
            obj = build_person_object(p, marc_alt_reverse.get(p, []))
            key = obj['name'].replace(' ', '_')
            full_key = '/subjects/people/' + key
            w['subject_people'].append({'key': full_key})

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
            obj_for_db['type'] = '/type/person'
            print ol.save(full_key.encode('utf-8'), obj_for_db, 'create a new person page')

        print w
        print ol.save(w['key'], w, 'add links to people that this work is about')

def from_sample():
    i = 0
    pages = {}
    page_marc = {}
    for line in open('work_and_marc5'):
        i += 1
        w = eval(line)
#        print i, w['key'], w['title']
#        print w['lines']
        try:
            people, marc_alt = read_people(j[1] for j in w['lines'])
        except AssertionError:
            print [j[1] for j in w['lines']]
            raise
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
#                print key
#                print p
#                for m in pages[key]['marc']:
#                    print m
#                print
                pages[key]['marc'].append(p)
            else:
                pages[key] = obj
#                pprint(obj)
#                continue
                if obj['name'][1].isdigit():
                    print [j[1] for j in w['lines']]
                    pprint(obj)
#                assert not obj['name'][1].isdigit()

from_sample()
#read_works()
