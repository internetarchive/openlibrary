from openlibrary.catalog.merge.merge_marc import build_marc
from load_book import build_query
from openlibrary.catalog.importer.merge import try_merge

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
    loc = 'ia:' + rec['ocaid']
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

    if 'authors' in q and False:
        wkey = find_matching_work(q)
    if wkey and False:
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

        wkey = web.ctx.site.new(w, comment='initial import')

    q['works'] = [{'key': wkey}]
    ret = web.ctx.site.new(q, comment='initial import')

    assert isinstance(ret, basestring)
    key = '/b/' + re_edition_key.match(ret).group(1)
    pool.update(key, q)

    print 'add_cover_image'
    if 'cover' in rec:
        add_cover_image(ret, rec['cover'])

def is_redirect(i):
    return i['type']['key'] == redirect

def find_match(e1, edition_pool):
    seen = set()
    for k, v in edition_pool.iteritems():
        for edition_key in v:
            if edition_key in seen:
                continue
            thing = None
            found = True
            while not thing or is_redirect(thing):
                seen.add(edition_key)
                thing = web.ctx.site.get(edition_key)
                if thing is None:
                    found = False
                    break
                if is_redirect(thing):
                    print 'following redirect %s => %s' % (edition_key, thing['location'])
                    edition_key = thing['location']
            if not found:
                continue
            if try_merge(e1, edition_key, thing):
                add_source_records(edition_key, ia)
                return edition_key
    return None

def load(rec):
    #edition_pool = pool.build(rec)
    load_data(rec) # 'no books in pool, loading'
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
