import MySQLdb, datetime, re, sys
sys.path.append('/1/src/openlibrary')
from openlibrary.api import OpenLibrary, Reference
from pprint import pprint

conn = MySQLdb.connect(db='merge_editions')
cur = conn.cursor()

re_edition_key = re.compile('^/books/OL(\d+)M$')
re_work_key = re.compile('^/works/OL(\d+)W$')
ol = OpenLibrary('http://openlibrary.org/')
ol.login('EdwardBot', 'As1Wae9b')

re_iso_date = re.compile('^(\d{4})-\d\d-\d\d$')
re_end_year = re.compile('(\d{4})$')

def get_publish_year(d):
    if not d:
        return
    m = re_iso_date.match(d)
    if m:
        return int(m.group(1))
    m = re_end_year.match(d)
    if m:
        return int(m.group(1))

{'lc_classifications': ['PZ7.H558 Ru'], 'dewey_number': ['[E]']}
def merge_works(works):
    master = works.pop(0)
    master_first_publish_year = get_publish_year(master.get('first_publish_date'))
    subtitles = sorted((w['subtitle'] for w in works if w.get('subtitle')), key=lambda s: len(s))
    if subtitles and len(subtitles[-1]) > len(master.get('subtitle', '')):
        master['subtitle'] = subtitles[-1]
    updates = []
    for w in works:
        wkey = w.pop('key')
        q = {'type': '/type/edition', 'works': wkey}
        for ekey in ol.query(q):
            e = ol.get(ekey)
            assert len(e['works']) == 1 and e['works'][0] == wkey
            e['works'] = [Reference(master['key'])]
            updates.append(e)
        assert w['type'] != Reference('/type/redirect')
        updates.append({
            'key': wkey,
            'type': Reference('/type/redirect'),
            'location': master['key'],
        })
        for f in 'covers', 'subjects', 'subject_places', 'subject_people', 'subject_times', 'lc_classifications', 'dewey_number':
            if not w.get(f):
                continue
            assert not isinstance(w[f], basestring)
            for i in w[f]:
                if i not in master.setdefault(f, []):
                    master[f].append(i)

        if w.get('first_sentence') and not master.get('first_sentence'):
            master['first_sentence'] = w['first_sentence']
        if w.get('first_publish_date'):
            if not master.get('first_publish_date'):
                master['first_publish_date'] = w['first_publish_date']
            else:
                publish_year = get_publish_year(w['first_publish_date'])
                if publish_year < master_first_publish_year:
                    master['first_publish_date'] = w['first_publish_date']
                    master_first_publish_year = publish_year

        for excerpt in w.get('exceprts', []):
            master.setdefault('exceprts', []).append(excerpt)

        for f in 'title', 'subtitle', 'created', 'last_modified', 'latest_revision', 'revision', 'number_of_editions', 'type', 'first_sentence', 'authors', 'first_publish_date', 'excerpts', 'covers', 'subjects', 'subject_places', 'subject_people', 'subject_times', 'lc_classifications', 'dewey_number':
            try:
                del w[f]
            except KeyError:
                pass

        print w
        assert not w
    updates.append(master)
    print len(updates), [(doc['key'], doc['type']) for doc in updates]
    # update master
    # update editions to point at master
    # replace works with redirects
    print ol.save_many(updates, 'merge works')

skip = 'seventeenagainst00voig'
skip = 'inlineskatingbas00sava'
skip = 'elephantatwaldor00mira'
skip = 'sybasesqlserverp00paul'
skip = 'karmadunl00dunl'
skip = 'norbychronicles00asim'
skip = 'elizabethbarrett00fors'
skip = None
updates = []
cur.execute('select ia, editions, done, unmerge_count from merge')
for ia, ekeys, done, unmerge_count in cur.fetchall():
    if skip:
        if ia == skip:
            skip = None
        else:
            continue
    ekeys = ['/books/OL%dM' % x for x in sorted(int(re_edition_key.match(ekey).group(1)) for ekey in ekeys.split(' '))]
    editions = [ol.get(ekey) for ekey in ekeys]

    if any('authors' not in e or 'works' not in e for e in editions):
        continue
    author0 = editions[0]['authors'][0]
    work0 = editions[0]['works'][0]
    try:
        if not all(author0 == e['authors'][0] for e in editions[1:]):
            continue
    except:
        print 'editions:', [e['key'] for e in editions]
        raise
    if all(work0 == e['works'][0] for e in editions[1:]):
        continue
    wkeys = []
    for e in editions:
        for wkey in e['works']:
            if wkey not in wkeys:
                wkeys.append(wkey)

    works = []
    for wkey in wkeys:
        w = ol.get(wkey)
        q = {'type': '/type/edition', 'works': wkey, 'limit': 1000}
        w['number_of_editions'] = len(ol.query(q))
        works.append(w)
    title0 = works[0]['title'].lower()
    if not all(w['title'].lower() == title0 for w in works[1:]):
        continue
    print ia, ekeys
    print '  works:', wkeys
    def work_key_int(wkey):
        return int(re_work_key.match(wkey).group(1))
    works = sorted(works, cmp=lambda a,b:-cmp(a['number_of_editions'],b['number_of_editions']) or cmp(work_key_int(a['key']), work_key_int(b['key'])))
    print '  titles:', [(w['title'], w['number_of_editions']) for w in works]
    print author0
    #print [w['authors'][0]['author'] for w in works]
    assert all(author0 == w['authors'][0]['author'] for w in works)
    merge_works(works)
    print

