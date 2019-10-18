from openlibrary.catalog.merge.merge_marc import build_marc, attempt_merge
import web

threshold = 875

def db_name(a):
    date = None
    if a.birth_date or a.death_date:
        date = a.get('birth_date', '') + '-' + a.get('death_date', '')
    elif a.date:
        date = a.date
    return ' '.join([a['name'], date]) if date else a['name']

# FIXME: badly named. edition_record_equal? (candidate_ed, existing_ed)
def try_merge(e1, edition_key, existing):
    """
    Converts the existing edition into a comparable dict and performs a
    thresholded comparison to decide whether they are the same.
    Used by add_book.load() -> add_book.find_match() to check whether two
    editions match.

    :param dict e1: Output of build_marc(import record candidate)
    :param str edition_key: edition key of existing
    :param Thing existing: Edition object to be tested against e1, the object of edition_key
    :rtype: bool
    :return: Whether e1 is sufficiently the same as the 'existing' edition
    """

    thing_type = existing.type.key
    if thing_type == '/type/delete':
        return False
    # FIXME: will fail if existing is a redirect.
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
            while a.type.key == '/type/redirect':
                a = web.ctx.site.get(a.location)
            if a.type.key == '/type/author':
                assert a['name']
                rec2['authors'].append({'name': a['name'], 'db_name': db_name(a)})
    e2 = build_marc(rec2)
    return attempt_merge(e1, e2, threshold)
