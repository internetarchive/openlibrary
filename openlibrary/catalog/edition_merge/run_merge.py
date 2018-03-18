import MySQLdb, datetime, re, sys
from openlibrary.api import OpenLibrary, Reference
from collections import defaultdict

re_edition_key = re.compile('^/books/OL(\d+)M$')
re_nonword = re.compile(r'\W', re.U)

conn = MySQLdb.connect(db='merge_editions')
cur = conn.cursor()
cur2 = conn.cursor()

ol = OpenLibrary('http://openlibrary.org/')
ol.login('EdwardBot', 'As1Wae9b')

cur.execute('select ia, editions, done from merge where done is null and unmerge_count=0')
for ia, ekeys, done in cur.fetchall():
    updates = []
    ekeys = ['/books/OL%dM' % x for x in sorted(int(re_edition_key.match(ekey).group(1)) for ekey in ekeys.split(' '))]
    print (ia, ekeys)
    min_ekey = ekeys[0]
    editions = [ol.get(ekey) for ekey in ekeys]
    master = editions[0]

    for e in editions:
        for k in 'classifications', 'identifiers', 'table_of_contents':
            if k in e and not e[k]:
                del e[k]

    all_keys = set()
    for e in editions:
        all_keys.update(k for k, v in e.items() if v)
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

    k = 'publish_date'
    publish_dates = set(e[k] for e in editions if k in e and len(e[k]) != 4)

    k = 'pagination'
    all_pagination = set(e[k].strip(':.') for e in editions if e.get(k))

    one_item_lists = {}
    for k in 'lc_classifications', 'publishers', 'contributions', 'series':
        one_item_lists[k] = set(e[k][0].strip('.') for e in editions if e.get(k) and len(set(e[k])) == 1)


    master.setdefault('source_records', [])
    for k in 'source_records', 'ia_box_id', 'other_titles','isbn_10','series':
        for e in editions[1:]:
            if not e.get(k):
                continue
            for i in e[k]:
                if i not in master.setdefault(k, []):
                    master[k].append(i)

    k = 'ocaid'
    for e in editions[1:]:
        if e.get(k) and 'ia:' + e[k] not in master['source_records']:
            master['source_records'].append(e[k])

    k = 'identifiers'
    if any(k in e for e in editions):
        master.setdefault(k, {})
        for e in editions[1:]:
            if k not in e:
                continue
            for a, b in e[k].items():
                for c in b:
                    if c in master[k].setdefault(a, []):
                        continue
                    master[k][a].append(c)

    any_publish_country = False
    k = 'publish_country'
    if k in all_keys:
        for e in editions:
            if e.get(k) and not e[k].strip().startswith('xx'):
                any_publish_country = True

    no_merge = False
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

        if len(uniq) == 0:
            continue
        if len(uniq) == 1:
            master[k] = editions[uniq.values()[0][0]][k]
            continue

        if k == 'covers':
            assert all(isinstance(e[k], list) for e in editions if k in e)
            covers = set()
            for e in editions:
                if k in e:
                    covers.update(c for c in e[k] if c != -1)
            master['covers'] = sorted(covers)
            continue

        if k == 'notes':
            master['notes'] = ''
            for e in editions:
                if e.get('notes'):
                    master['notes'] += e['notes'] + '\n'
            continue

        if k == 'ocaid':
            for e in editions:
                if e.get('ocaid'):
                    if e['ocaid'].endswith('goog'):
                        print e['key'], e['ocaid'], ia
                    master['ocaid'] = e['ocaid']
                    break
            assert master['ocaid']
            continue

        if k == 'authors':
            min_author = set(min((e.get('authors', []) for e in editions), key=len))
            if all(min_author <= set(e.get('authors', [])) for e in editions):
                master[k] = max((e.get('authors', []) for e in editions), key=len)
                continue

        print 'unmerged field:', k
        print [e.get(k) for e in editions]
        no_merge = True
    if no_merge:
        continue
    if 'location' in master and isinstance(master['location'], basestring) and master['location'].startswith('/books/'):
        del master['location']
    updates.append(master)
    for e in editions[1:]:
        redirect = {
            'type': Reference('/type/redirect'),
            'location': min_ekey,
            'key': e['key'],
        }
        updates.append(redirect)
    print len(updates), min_ekey
    try:
        print ol.save_many(updates, 'merge lending editions')
    except:
        for i in updates:
            print i
        raise
    cur2.execute('update merge set done=now() where ia=%s', [ia])
