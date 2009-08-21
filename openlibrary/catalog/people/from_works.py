from openlibrary.catalog.utils.query import query_iter, set_staging, get_mc
from openlibrary.catalog.get_ia import get_data
from openlibrary.catalog.marc.fast_parse import get_tag_lines, get_all_subfields, get_subfields

from identify_people import read_people
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, unmarshal

ol = OpenLibrary("http://dev.openlibrary.org")
ol.login('EdwardBot', rc['EdwardBot']) 

set_staging(True)

def build_person_object(p, marc_alt):
    print 'p:', p
    print 'marc_alt:', marc_alt

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
i = 0
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
    print >> out, w
    print i, w['key'], w['title']
    try:
        people, marc_alt = read_people(j[1] for j in lines)
    except AssertionError:
        print w['lines']
        raise
    marc_alt_reverse = defaultdict(set)
    for k, v in marc_alt.items():
        marc_alt_reverse[v].add(k)

    for p, num in people.iteritems():
#        print '  %2d %s' % (num, ' '.join("%s: %s" % (k, v) for k, v in p))
#        print '     ', p
        build_person_object(p, marc_alt_reverse)

    print

out.close()
