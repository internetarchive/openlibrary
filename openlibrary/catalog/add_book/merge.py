from openlibrary.catalog.merge.merge_marc import build_marc

threshold = 875

def try_merge(e1, edition_key, thing):
    thing_type = thing.type.key
    if thing_type == '/type/delete':
        return False
    assert thing_type == '/type/edition'

    ia = thing.get('ocaid')

    rec2 = None

    # code to load rec2 goes here
    return

    e2 = build_marc(rec2)
    return attempt_merge(e1, e2, threshold, debug=False)
