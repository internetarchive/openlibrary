from openlibrary.catalog.merge.merge_marc import build_marc, attempt_merge
from pprint import pprint
import web

threshold = 875

def db_name(a):
    date = None
    if a.birth_date or a.death_date:
        date = a.get('birth_date', '') + '-' + a.get('death_date', '')
    elif a.date:
        #assert not a.birth_date and not a.death_date 
        date = a.date
    return ' '.join([a['name'], date]) if date else a['name']

def undelete_author(a):
    a = web.ctx.site.get(a.key, revision=a.revision-1)
    author_type = a.type.key
    assert author_type == '/type/author'
    web.ctx.site.save(a.dict(), comment='undelete author')
    return web.ctx.site.get(a.key)

def try_merge(e1, edition_key, existing):
    thing_type = existing.type.key
    if thing_type == '/type/delete':
        return False
    assert thing_type == '/type/edition'

    rec2 = {}
    rec2['full_title'] = existing.title
    if existing.subtitle:
        rec2['full_title'] += ' ' + existing.subtitle
    for f in 'isbn', 'isbn_10', 'isbn_13', 'lccn', 'publish_country', 'publishers', 'publish_date':
        if existing.get(f):
            rec2[f] = existing[f]
    if existing.authors:
        rec2['authors'] = []
        for a in existing.authors:
            author_type = a.type.key
            while author_type == '/type/delete' or author_type == '/type/redirect':
                if author_type == '/type/delete':
                    a = undelete_author(a)
                    author_type = a.type.key
                    continue
                if author_type == '/type/redirect':
                    a = web.ctx.site.get(a.location)
                    author_type = a.type.key
                    continue
            assert author_type == '/type/author'
            assert a['name']
            rec2['authors'].append({'name': a['name'], 'db_name': db_name(a)})

    e2 = build_marc(rec2)
    return attempt_merge(e1, e2, threshold, debug=False)
