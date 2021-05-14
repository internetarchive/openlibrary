import web
from deprecated import deprecated
from openlibrary.catalog.merge.merge_marc import (
    build_marc, editions_match as threshold_match)


threshold = 875


def db_name(a):
    date = None
    if a.birth_date or a.death_date:
        date = a.get('birth_date', '') + '-' + a.get('death_date', '')
    elif a.date:
        date = a.date
    return ' '.join([a['name'], date]) if date else a['name']


@deprecated('Use editions_match(candidate, existing) instead.')
def try_merge(candidate, edition_key, existing):
    return editions_match(candidate, existing)


def editions_match(candidate, existing):
    """
    Converts the existing edition into a comparable dict and performs a
    thresholded comparison to decide whether they are the same.
    Used by add_book.load() -> add_book.find_match() to check whether two
    editions match.

    :param dict candidate: Output of build_marc(import record candidate)
    :param Thing existing: Edition object to be tested against candidate
    :rtype: bool
    :return: Whether candidate is sufficiently the same as the 'existing' edition
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
    return threshold_match(candidate, e2, threshold)
