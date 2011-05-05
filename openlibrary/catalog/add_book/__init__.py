from openlibrary.catalog.merge.merge_marc import build_marc
from load_book import build_query

type_map = {
    'description': 'text',
    'notes': 'text',
    'number_of_pages': 'int',
}

class InvalidLanguage(Exception):
    def __init__(self, code):
        self.code = code
    def __str__(self):
        return "invalid language code: '%s'" % self.code

def load_data(rec):
    loc = 'ia:' + rec['ia']
    q = build_query(rec)

    for a in q.get('authors', []):
        if 'key' in a:
            authors.append({'key': a['key']})
        else:
            try:
                ret = ol.new(a, comment='new author')
            except:
                print a
                raise
            print 'ret:', ret
            assert isinstance(ret, basestring)
            authors.append({'key': ret})
    q['source_records'] = [loc]
    if authors:
        q['authors'] = authors

    wkey = None
    subjects = subjects_for_work(rec)
    subjects.setdefault('subjects', []).append('Accessible book')

    if 'printdisabled' in collections:
        subjects['subjects'].append('Protected DAISY')
    elif 'lendinglibrary' in collections:
        subjects['subjects'] += ['Protected DAISY', 'Lending library']
    elif 'inlibrary' in collections:
        subjects['subjects'] += ['Protected DAISY', 'In library']

    if 'authors' in q:
        wkey = find_matching_work(q)
    if wkey:
        w = ol.get(wkey)
        need_update = False
        for k, subject_list in subjects.items():
            for s in subject_list:
                if s not in w.get(k, []):
                    w.setdefault(k, []).append(s)
                    need_update = True
        if need_update:
            ol.save(wkey, w, 'add subjects from new record')
    else:
        w = {
            'type': '/type/work',
            'title': q['title'],
        }
        if 'authors' in q:
            w['authors'] = [{'type':'/type/author_role', 'author': akey} for akey in q['authors']]
        w.update(subjects)

        wkey = ol.new(w, comment='initial import')

    q['works'] = [{'key': wkey}]
    for attempt in range(50):
        if attempt > 0:
            print 'retrying'
        try:
            pprint(q)
            ret = ol.new(q, comment='initial import')
        except httplib.BadStatusLine:
            sleep(30)
            continue
        except: # httplib.BadStatusLine
            print q
            raise
        break
    print 'ret:', ret
    assert isinstance(ret, basestring)
    key = '/b/' + re_edition_key.match(ret).group(1)
    pool.update(key, q)

    print 'add_cover_image'
    if 'cover' in rec:
        add_cover_image(ret, rec['cover'])


def load(rec):
    edition_pool = pool.build(rec)
    if not edition_pool:
        load_data(rec) # 'no books in pool, loading'

    rec['full_title'] = rec['title']
    if rec.get('subtitle'):
        rec['full_title'] += ' ' + rec['subtitle']
    e1 = build_marc(rec)

    if 'authors' in e1:
        for a in e1['authors']:
            date = None
            if 'date' in a:
                assert 'birth_date' not in a and 'death_date' not in a
                date = a['date']
            elif 'birth_date' in a or 'death_date' in a:
                date = a.get('birth_date', '') + '-' + a.get('death_date', '')
            a['db_name'] = ' '.join([a['name'], date]) if date else a['name']

    match = find_match(e1, edition_pool)

    if match: # 'match found:', match, rec['ia']
        add_source_records(match, ia)
    else: # 'no match found', rec['ia']
        load_data(rec)

    return {'note': 'loaded'}
