import MySQLdb, datetime, re, sys
sys.path.append('/1/src/openlibrary')
from openlibrary.api import OpenLibrary, Reference
from collections import defaultdict
from pprint import pprint

re_edition_key = re.compile('^/books/OL(\d+)M$')
re_nonword = re.compile(r'\W', re.U)
re_edition = re.compile(' ed edition$')

ol = OpenLibrary('http://openlibrary.org/')

conn = MySQLdb.connect(db='merge_editions')
cur = conn.cursor()

skip = 'guineapigscomple00elwa'
skip = None
total = 5601
cur.execute("select ia, editions, done, unmerge_count from merge where unmerge_count != 0") # and ia='hantayo00hillrich'")
unmerge_field_counts = defaultdict(int)
num = 0
for ia, ekeys, done, unmerge_count in cur.fetchall():
#    if unmerge_count == 0:
#        continue
    num += 1
    if num % 100 == 0:
        print '%d/%d %.2f%%' % (num, total, ((float(num) * 100) / total)), ia
    if skip:
        if skip == ia:
            skip = None
        continue
    ekeys = ['/books/OL%dM' % x for x in sorted(int(re_edition_key.match(ekey).group(1)) for ekey in ekeys.split(' '))]
    min_ekey = ekeys[0]

    if len(ekeys) > 3:
        print ia, ekeys
    editions = [ol.get(ekey) for ekey in ekeys]
    all_keys = set()
    for e in editions:
        for k in 'classifications', 'identifiers', 'table_of_contents':
            if k in e and not e[k]:
                del e[k]
    for e in editions:
        all_keys.update(e.keys())
    for k in 'latest_revision', 'revision', 'created', 'last_modified', 'key', 'type', 'genres':
        if k in all_keys:
            all_keys.remove(k)

    for k in all_keys.copy():
        if k.startswith('subject'):
            all_keys.remove(k)

    for e in editions: # resolve redirects
        if 'authors' not in e:
            continue
        new_authors = []
        for akey in e['authors']:
            a = ol.get(akey)
            if a['type'] == Reference('/type/redirect'):
                akey = Reference(a['location'])
            else:
                assert a['type'] == Reference('/type/author')
            new_authors.append(akey)
        e['authors'] = new_authors

    merged = {}
    k = 'publish_date'
    publish_dates = set(e[k] for e in editions if k in e and len(e[k]) != 4)

    k = 'pagination'
    all_pagination = set(e[k].strip(':.') for e in editions if e.get(k))

    one_item_lists = {}
    for k in 'lc_classifications', 'publishers', 'contributions', 'series', 'authors':
        one_item_lists[k] = set(e[k][0].strip('.') for e in editions if e.get(k) and len(set(e[k])) == 1)

    for k in 'source_records', 'ia_box_id':
        merged[k] = []
        for e in editions:
            for sr in e.get(k, []):
                if sr not in merged[k]:
                    merged[k].append(sr)

    for k in ['other_titles', 'isbn_10', 'series', 'oclc_numbers', 'publishers']:
        if k not in all_keys:
            continue
        merged[k] = []
        for e in editions:
            for sr in e.get(k, []):
                if sr not in merged[k]:
                    merged[k].append(sr)

    k = 'ocaid'
    for e in editions:
        if e.get(k) and 'ia:' + e[k] not in merged['source_records']:
            merged['source_records'].append(e[k])

    k = 'identifiers'
    if k in all_keys:
        merged[k] = {}
        for e in editions:
            if k not in e:
                continue
            for a, b in e[k].items():
                for c in b:
                    if c in merged[k].setdefault(a, []):
                        continue
                    merged[k][a].append(c)

    any_publish_country = False
    k = 'publish_country'
    if k in all_keys:
        for e in editions:
            if e.get(k) and not e[k].strip().startswith('xx'):
                any_publish_country = True

    skip_fields = set(['source_records', 'ia_box_id', 'identifiers', 'ocaid', 'other_titles', 'series', 'isbn_10'])
    for k in all_keys:
        if k in skip_fields:
            continue

        uniq = defaultdict(list)
        for num, e in enumerate(editions):
            if e.get(k):
                if k == 'publish_date' and len(e[k]) == 4 and e[k].isdigit and any(e[k] in pd for pd in publish_dates):
                    continue
                if k == 'pagination' and any(len(i) > len(e[k].strip('.:')) and e[k].strip('.:') in i for i in all_pagination):
                    continue
                if k in one_item_lists and len(set(e.get(k, []))) == 1 and any(len(i) > len(e[k][0].strip('.')) and e[k][0].strip('.') in i for i in one_item_lists[k]):
                    continue
                if k == 'publish_country' and any_publish_country and e.get(k, '').strip().startswith('xx'):
                    continue
                if k == 'edition_name' and e[k].endswith(' ed edition'):
                    e[k] = e[k][:-len(' edition')]
                uniq[re_nonword.sub('', repr(e[k]).lower())].append(num)

        if len(uniq) == 1:
            merged[k] = uniq.keys()[0]
            merged[k] = editions[uniq.values()[0][0]][k]
            continue

        if k == 'covers':
            assert all(isinstance(e[k], list) for e in editions if k in e)
            covers = set()
            for e in editions:
                if k in e:
                    covers.update(c for c in e[k] if c != -1)
            merged['covers'] = sorted(covers)
            continue

        if k == 'notes':
            merged['notes'] = ''
            for e in editions:
                if e.get('notes'):
                    merged['notes'] += e['notes'] + '\n'
            continue

        if k == 'ocaid':
            for e in editions:
                if e.get('ocaid'):
                    if e['ocaid'].endswith('goog'):
                        print e['key'], e['ocaid'], ia
                    merged['ocaid'] = e['ocaid']
                    break
            assert merged['ocaid']
            continue

        if k =='authors':
            min_author = set(min((e.get('authors', []) for e in editions), key=len))
            if all(min_author <= set(e.get('authors', [])) for e in editions):
                merged[k] = max((e.get('authors', []) for e in editions), key=len)
                continue
        merged[k] = None
    unmerged = len([1 for v in merged.values() if v is None])
    if unmerged == 1:
        assert len([k for k, v in merged.items() if v is None]) == 1
        for k, v in merged.items():
            if v is None:
                if k == 'series':
                    print ia, [e[k] for e in editions if e.get(k)]
                unmerge_field_counts[k] += 1
    #print 'unmerged count', unmerged, ia, ekeys
    cur.execute('update merge set unmerge_count=%s where ia=%s', [unmerged, ia])

print dict(unmerge_field_counts)
print unmerge_field_counts.items()
for k,v in sorted(unmerge_field_counts.items(), key=lambda i:i[1]):
    print '%30s: %d' % (k, v)
