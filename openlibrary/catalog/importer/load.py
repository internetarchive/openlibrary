import web, re
from db_read import get_things, withKey
from openlibrary.catalog.utils import flip_name, author_dates_match, key_int
from openlibrary.catalog.utils.query import query_iter

def find_author(name):
    q = {'type': '/type/author', 'name': name}
    return [a['key'] for a in query_iter(q)]

def do_flip(author):
    # given an author name flip it in place
    if 'personal_name' not in author:
        return
    if author['personal_name'] != author['name']:
        return
    first_comma = author['name'].find(', ')
    if first_comma == -1:
        return
    # e.g: Harper, John Murdoch, 1845-
    if author['name'].find(',', first_comma + 1) != -1:
        return
    if author['name'].find('i.e.') != -1:
        return
    if author['name'].find('i. e.') != -1:
        return
    name = flip_name(author['name'])
    author['name'] = name
    author['personal_name'] = name

def pick_from_matches(author, match):
    maybe = []
    if 'birth_date' in author and 'death_date' in author:
        maybe = [m for m in match if 'birth_date' in m and 'death_date' in m]
    elif 'date' in author:
        maybe = [m for m in match if 'date' in m]
    if not maybe:
        maybe = match
    if len(maybe) == 1:
        return maybe[0]
    return min(maybe, key=key_int)

def find_entity(author):
    name = author['name']
    things = find_author(name)
    if author['entity_type'] != 'person':
        if not things:
            return None
        db_entity = withKey(things[0])
        if db_entity['type']['key'] == '/type/redirect':
            db_entity = withKey(db_entity['location'])
        assert db_entity['type']['key'] == '/type/author'
        return db_entity
    if ', ' in name:
        things += find_author(flip_name(name))
    match = []
    seen = set()
    for key in things:
        if key in seen:
            continue
        seen.add(key)
        db_entity = withKey(key)
        if db_entity['type']['key'] == '/type/redirect':
            key = db_entity['location']
            if key in seen:
                continue
            seen.add(key)
            db_entity = withKey(key)
        if db_entity['type']['key'] == '/type/delete':
            continue
        try:
            assert db_entity['type']['key'] == '/type/author'
        except:
            print name, key, db_entity
            raise
        if 'birth_date' in author and 'birth_date' not in db_entity:
            continue
        if 'birth_date' not in author and 'birth_date' in db_entity:
            continue
        if not author_dates_match(author, db_entity):
            continue
        match.append(db_entity)
    if not match:
        return None
    if len(match) == 1:
        return match[0]
    try:
        return pick_from_matches(author, match)
    except ValueError:
        print 'author:', author
        print 'match:', match
        raise

def import_author(author, eastern=False):
    existing = find_entity(author)
    if existing:
        existing['key'] = existing['key'].replace('\/', '/')
        existing['type']['key'] = existing['type']['key'].replace('\/', '/')
        if existing['type']['key'] != '/type/author':
            print author
            print existing
        assert existing['type']['key'] == '/type/author'
        for k in 'last_modified', 'id', 'revision', 'created':
            if k in existing:
                del existing[k]
        new = existing
#        new["create"] = "unless_exists"
        if 'death_date' in author and 'death_date' not in existing:
            new['death_date'] = {
                'connect': 'update',
                'value': author['death_date'],
            }
        return new
    else:
        if not eastern:
            do_flip(author)
        a = {
#            'create': 'unless_exists',
            'type': { 'key': '/type/author' },
            'name': author['name']
        }
        for f in 'title', 'personal_name', 'enumeration', 'birth_date', 'death_date', 'date':
            if f in author:
                a[f] = author[f]
        return a

type_map = {
    'description': 'text',
    'notes': 'text',
    'number_of_pages': 'int',
}

def east_in_by_statement(rec):
    if 'by_statement' not in rec:
        return False
    if 'authors' not in rec:
        return False
    name = rec['authors'][0]['name']
    flipped = flip_name(name)
    name = name.replace('.', '')
    name = name.replace(', ', '')
    if name == flipped.replace('.', ''):
        return False
    return rec['by_statement'].find(name) != -1

def check_if_loaded(loc): # unused
    return bool(get_versions({'machine_comment': loc}))

def build_query(loc, rec):
    if 'table_of_contents' in rec:
        assert not isinstance(rec['table_of_contents'][0], list)
    book = {
        'type': { 'key': '/type/edition'},
    }

    east = east_in_by_statement(rec)
    if east:
        print rec

    for k, v in rec.iteritems():
        if k == 'authors':
            book[k] = [import_author(v[0], eastern=east)]
            continue
        if k in type_map:
            t = '/type/' + type_map[k]
            if isinstance(v, list):
                book[k] = [{'type': t, 'value': i} for i in v]
            else:
                book[k] = {'type': t, 'value': v}
        else:
            book[k] = v

    assert 'title' in book
    return book

def add_keys(q): # unused
    if 'authors' in q:
        for a in q['authors']:
            a.setdefault('key', '/a/OL%dA' % (get_author_num(web) + 1))
    q['key'] = '/b/OL%dM' % (get_book_num(web) + 1)
