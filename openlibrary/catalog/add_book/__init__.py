from openlibrary.catalog.merge.merge_marc import build_marc
from load_book import build_query, import_author, east_in_by_statement
import web, re
from merge import try_merge
from openlibrary.catalog.utils import mk_norm
from pprint import pprint

type_map = {
    'description': 'text',
    'notes': 'text',
    'number_of_pages': 'int',
}

class RequiredField(Exception):
    def __init__(self, f):
        self.f = f
    def __str__(self):
        return "missing required field: '%s'" % self.f

# don't use any of these as work titles
bad_titles = set(('Publications', 'Works. English', 'Missal', 'Works', 'Report', \
    'Letters', 'Calendar', 'Bulletin', 'Plays', 'Sermons', 'Correspondence', \
    'Bill', 'Bills', 'Selections', 'Selected works', 'Selected works. English', \
    'The Novels', 'Laws, etc'))

subject_fields = ['subjects', 'subject_places', 'subject_times', 'subject_people' ] 

def get_title(e):
    if not e.get('work_titles'):
        return e['title']
    wt = e['work_titles'][0]
    return e['title'] if wt in bad_titles else e['title']

def find_matching_work(e):
    norm_title = mk_norm(get_title(e))

    seen = set()
    for a in e['authors']:
        q = {
            'type':'/type/work',
            'authors.author': a['key'],
        }
        work_keys = list(web.ctx.site.things(q))
        for wkey in work_keys:
            w = web.ctx.site.get(wkey)
            if wkey in seen:
                continue
            seen.add(wkey)
            if not w.get('title'):
                continue
            if mk_norm(w['title']) == norm_title:
                assert w.type.key == '/type/work'
                return wkey
            else:
                print 'title:', w['title'], '!=', get_title(e)

def build_author_reply(author_in):
    authors = []
    author_reply = []
    for a in author_in:
        new_author = 'key' not in a
        if new_author:
            a['key'] = web.ctx.site.new_key('/type/author')
            web.ctx.site.save(a, comment='new author')
        authors.append({'key': a['key']})
        author_reply.append({
            'key': a['key'],
            'name': a['name'],
            'status': ('created' if new_author else 'modified'),
        })
    return (authors, author_reply)

def load_data(rec):
    q = build_query(rec)

    reply = {}
    author_in = q.get('authors', [])
    (authors, author_reply) = build_author_reply(author_in)

    #q['source_records'] = [loc]
    if authors:
        q['authors'] = authors
        reply['authors'] = author_reply

    wkey = None
    #subjects = subjects_for_work(rec)
    subjects = {}
#    subjects.setdefault('subjects', []).append('Accessible book')
#
#    if 'printdisabled' in collections:
#        subjects['subjects'].append('Protected DAISY')
#    elif 'lendinglibrary' in collections:
#        subjects['subjects'] += ['Protected DAISY', 'Lending library']
#    elif 'inlibrary' in collections:
#        subjects['subjects'] += ['Protected DAISY', 'In library']

    work_state = 'created'
    if 'authors' in q:
        wkey = find_matching_work(q)
    if wkey:
        w = web.ctx.site.get(wkey)
        work_state = 'matched'
        found_wkey_match = True
        need_update = False
        for k in subject_fields:
            if k not in rec:
                continue
            for s in rec[k]:
                if s not in w.get(k, []):
                    w.setdefault(k, []).append(s)
                    need_update = True
        if need_update:
            work_state = 'modified'
            web.ctx.site.save(w, wkey, 'add subjects from new record')
    else:
        w = {
            'type': {'key': '/type/work'},
            'title': get_title(q),
        }
        for s in subject_fields:
            if s in rec:
                w[s] = rec[s]
        if 'authors' in q:
            w['authors'] = [{'type':{'key': '/type/author_role'}, 'author': akey} for akey in q['authors']]
        w.update(subjects)

        wkey = web.ctx.site.new_key('/type/work')

        w['key'] = wkey
        web.ctx.site.save(w, comment='initial import')

    q['works'] = [{'key': wkey}]
    ekey = web.ctx.site.new_key('/type/edition')
    q['key'] = ekey
    web.ctx.site.save(q, comment='initial import')

    #pool.update(ekey, q)

    #print 'add_cover_image'
    #if 'cover' in rec:
    #    add_cover_image(ekey, rec['cover'])

    reply['success'] = True
    reply['edition'] = { 'key': ekey, 'status': 'created', }
    reply['work'] = { 'key': wkey, 'status': work_state, }
    return reply

def is_redirect(i):
    if not i:
        return False
    return i.type.key == '/type/redirect'

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
            #print (e1, edition_key, thing)
            if try_merge(e1, edition_key, thing):
                #add_source_records(edition_key, ia)
                return edition_key
    return None

pool_fields = ('isbn', 'title', 'oclc_numbers', 'lccn')

def build_pool(rec):
    pool = {}
    for field in pool_fields:
        if field not in rec:
            continue
        for v in (rec[field] if field != 'title' else [rec[field]]):
            #print (field, v)
            found = web.ctx.site.things({field: v, 'type': '/type/edition'})
            pool.setdefault(field, set()).update(found)
    return dict((k, list(v)) for k, v in pool.iteritems() if v)

def add_db_name(rec):
    if 'authors' not in rec:
        return

    for a in rec['authors']:
        date = None
        if 'date' in a:
            assert 'birth_date' not in a and 'death_date' not in a
            date = a['date']
        elif 'birth_date' in a or 'death_date' in a:
            date = a.get('birth_date', '') + '-' + a.get('death_date', '')
        a['db_name'] = ' '.join([a['name'], date]) if date else a['name']

re_lang = re.compile('^/languages/([a-z]{3})$')

def find_exact_match(rec, edition_pool):
    seen = set()
    for field, editions in edition_pool.iteritems():
        for ekey in editions:
            if ekey in seen:
                continue
            seen.add(ekey)
            existing = web.ctx.site.get(ekey)
            match = True
            for k, v in rec.items():
                existing_value = existing.get(k)
                if not existing_value:
                    continue
                if k == 'languages':
                     existing_value = [str(re_lang.match(l.key).group(1)) for l in existing_value]
                if k == 'authors':
                     existing_value = [dict(a) for a in existing_value]
                     for a in existing_value:
                         del a['type']
                         del a['key']
                     for a in v:
                         if 'entity_type' in a:
                            del a['entity_type']

                if existing_value != v:
                    match = False
                    break
            if match:
                return ekey
    return False

def load(rec):
    if not rec.get('title'):
        raise RequiredField('title')
    edition_pool = build_pool(rec)
    #print 'pool:', edition_pool
    if not edition_pool:
        return load_data(rec) # 'no books in pool, loading'

    #matches = set(item for sublist in edition_pool.values() for item in sublist)
    #if len(matches) == 1:
    #    return {'success': True, 'edition': {'key': list(matches)[0]}}

    match = find_exact_match(rec, edition_pool)

    if not match:
        rec['full_title'] = rec['title']
        if rec.get('subtitle'):
            rec['full_title'] += ' ' + rec['subtitle']
        e1 = build_marc(rec)
        add_db_name(e1)

        #print
        #print 'e1', e1
        #print 
        #print 'pool', edition_pool
        match = find_match(e1, edition_pool)

    if match: # 'match found:', match, rec['ia']
        e = web.ctx.site.get(match)
        w = e['works'][0]
        reply = {
            'success': True,
            'edition': {'key': match, 'status': 'matched'},
            'work': {'key': w.key, 'status': 'matched'},
        }

        need_work_save = False
        need_edition_save = False
        if rec.get('authors'):
            reply['authors'] = []
            east = east_in_by_statement(rec)
            work_authors = list(w.authors)
            edition_authors = list(e.authors)
            author_in = [import_author(a, eastern=east) for a in rec['authors']]
            for a in author_in:
                new_author = 'key' not in a
                add_to_work = False
                add_to_edition = False
                if new_author:
                    a['key'] = web.ctx.site.new_key('/type/author')
                    aobj = web.ctx.site.save(a, comment='new author')
                    add_to_work = True
                    add_to_edition = True
                else:
                    if not any(i.author.key == a['key'] for i in work_authors):
                        add_to_work = True
                    if not any(i.key == a['key'] for i in edition_authors):
                        add_to_edition = True
                if add_to_work:
                    need_work_save = True
                    work_authors.append({
                        'type': {'key': '/type/author_role'},
                        'author': {'key': a['key'] },
                    })
                if add_to_edition:
                    need_edition_save = True
                    edition_authors.append({'key': a['key'] })

                reply['authors'].append({
                    'key': a['key'],
                    'name': a['name'],
                    'status': ('created' if new_author else 'modified'),
                })
            w.authors = work_authors
            e.authors = edition_authors
        if 'subjects' in rec:
            work_subjects = list(w.subjects)
            for s in rec['subjects']:
                if s not in w.subjects:
                    #print 'w.subjects.append(%s)' % s
                    work_subjects.append(s)
                    need_work_save = True
            if need_work_save:
                w.subjects = work_subjects
        if need_edition_save:
            reply['edition']['status'] = 'modified'
            web.ctx.site.save(e, match, 'update edition')
        if need_work_save:
            reply['work']['status'] = 'modified'
            web.ctx.site.save(w, w.key, 'update work')
        return reply
        #add_source_records(match, ia)
    else: # 'no match found', rec['ia']
        return load_data(rec)
