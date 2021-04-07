import web, sys, codecs, re, urllib2
from catalog.get_ia import read_marc_file
from catalog.read_rc import read_rc
from catalog.marc.fast_parse import get_tag_lines, get_all_subfields, get_first_tag
from catalog.marc.new_parser import read_edition
from catalog.utils.query import query_iter
from catalog.marc.utils import files
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, unmarshal
import simplejson as json
from catalog.importer.load import build_query, east_in_by_statement, import_author

rc = read_rc()
marc_index = web.database(dbn='postgres', db='marc_index')
marc_index.printing = False

ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot'])

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

#ocm04775229
re_oclc = re.compile ('^oc[mn]0*(\d+)$')

def get_keys(loc):
    assert loc.startswith('marc:')
    vars = {'loc': loc[5:]}
    db_iter = marc_index.query('select k from machine_comment where v=$loc', vars)
    mc = list(db_iter)
    if mc:
        return [r.k for r in mc]
    iter = query_iter({'type': '/type/edition', 'source_records': loc})
    return [e['key'] for e in iter]

re_meta_mrc = re.compile('^([^/]*)_meta.mrc:0:\d+$')

def fix_toc(e):
    toc = e.get('table_of_contents', None)
    if not toc:
        return
    if isinstance(toc[0], dict) and toc[0]['type'] == '/type/toc_item':
        return
    return [{'title': unicode(i), 'type': '/type/toc_item'} for i in toc if i != u'']

re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon)\.$')

def has_dot(s):
    return s.endswith('.') and not re_skip.search(s)

def undelete_authors(key):
    a = ol.get(key)
    if a['type'] == '/type/author':
        return
    assert a['type'] == '/type/delete'
    url = 'http://openlibrary.org' + key + '.json?v=' + str(a['revision'] - 1)
    prev = unmarshal(json.load(urllib2.urlopen(url)))
    assert prev['type'] == '/type/author'
    ol.save(key, prev, 'undelete author')

def author_from_data(loc, data):
    edition = read_edition(loc, data)
    assert 'authors' in edition
    east = east_in_by_statement(edition)
    assert len(edition['authors']) == 1
    print(repr(edition['authors'][0]))
    a = import_author(edition['authors'][0], eastern=east)
    if 'key' in a:
        return {'key': a['key']}
    ret = ol.new(a, comment='new author')
    print 'ret:', ret
    assert isinstance(ret, basestring)
    return {'key': ret}


def add_oclc(key, sr, oclc, data):
    assert sr and oclc
    e = ol.get(key)
    if 'oclc_numbers' in e:
        return
    e['oclc_numbers'] = [oclc]
    if 'source_records' not in e:
        e['source_records'] = [sr]

    # fix other bits of the record as well
    new_toc = fix_toc(e)
    if new_toc:
        e['table_of_contents'] = new_toc
    if e.get('subjects', None) and any(has_dot(s) for s in e['subjects']):
        subjects = [s[:-1] if has_dot(s) else s for s in e['subjects']]
        e['subjects'] = subjects
    if 'authors' in e:
        if any(a=='None' for a in e['authors']):
            assert len(e['authors']) == 1
            new_author = author_from_data(sr, data)
            e['authors'] = [new_author]
        else:
            for a in e['authors']:
                undelete_authors(a)

    print ol.save(key, e, 'add OCLC number')
    if new_toc:
        new_edition = ol.get(key)
        # [{u'type': <ref: u'/type/toc_item'>}, ...]
        assert 'title' in new_edition['table_of_contents'][0]

skipping = True
for name, part, size in files():
    f = open(name)
    print part
    if skipping:
        if part != 'marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc':
            print 'skipping'
            continue
    for pos, loc, data in read_marc_file(part, f):
        if skipping:
            if loc.startswith('marc:marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:668652795:1299'):
                skipping = False
            continue

        if str(data)[6:8] != 'am': # only want books
            continue
        tag_003 = get_first_tag(data, ['003'])
        if not tag_003 or not tag_003.lower().startswith('ocolc'):
            continue
        oclc = get_first_tag(data, ['001'])
        if not oclc:
#            print get_first_tag(data, ['010'])
            continue
        assert oclc[-1] == '\x1e'
        oclc = oclc[:-1].strip()
        if not oclc.isdigit():
            m = re_oclc.match(oclc)
            if not m:
                print("can't read:", repr(oclc))
                continue
            oclc = m.group(1)
        keys = get_keys(loc)
        if not keys:
            continue
        print loc, keys, oclc
        for key in keys:
            add_oclc(key, loc, oclc, data)
