import web
from openlibrary.catalog.utils import expand_record
from openlibrary.catalog.merge.merge_marc import editions_match as threshold_match


threshold = 875


def editions_match(candidate, existing):
    """
    Converts the existing edition into a comparable dict and performs a
    thresholded comparison to decide whether they are the same.
    Used by add_book.load() -> add_book.find_match() to check whether two
    editions match.

    :param dict candidate: Output of expand_record(import record candidate)
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
    for f in (
        'title',
        'subtitle',
        'isbn',
        'isbn_10',
        'isbn_13',
        'lccn',
        'publish_country',
        'publishers',
        'publish_date',
    ):
        if existing.get(f):
            rec2[f] = existing[f]
    # Transfer authors as Dicts str: str
    if existing.authors:
        rec2['authors'] = []
    for a in existing.authors:
        while a.type.key == '/type/redirect':
            a = web.ctx.site.get(a.location)
        if a.type.key == '/type/author':
            author = {'name': a['name']}
            if birth := a.get('birth_date'):
                author['birth_date'] = birth
            if death := a.get('death_date'):
                author['death_date'] = death
            rec2['authors'].append(author)
    e2 = expand_record(rec2)
    return threshold_match(candidate, e2, threshold)
