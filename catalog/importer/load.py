import web, re
from db_read import get_things, withKey

re_end_dot = re.compile('[^ ][^ ]\.$', re.UNICODE)
re_marc_name = re.compile('^(.*), (.*)$')
re_year = re.compile(r'\b(\d{4})\b')

def flip_name(name):
    # strip end dots like this: "Smith, John." but not like this: "Smith, J."
    m = re_end_dot.search(name)
    if m:
        name = name[:-1]

    if name.find(', ') == -1:
        return name
    m = re_marc_name.match(name)
    return m.group(2) + ' ' + m.group(1)

def do_flip(author):
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

def author_dates_match(a, b):
    for k in ['birth_date', 'death_date', 'date']:
        if k not in a or k not in b:
            continue
        if a[k] == b[k] or a[k].startswith(b[k]) or b[k].startswith(a[k]):
            continue
        m1 = re_year.search(a[k])
        if not m1:
            return False
        m2 = re_year.search(b[k])
        if m2 and m1.group(1) == m2.group(1):
            continue
        return False
    return True

def key_int(rec):
    return int(web.numify(rec['key']))

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
    things = get_things({'name': name, 'type': '/type/author'})
    if author['entity_type'] != 'person':
        return withKey(things[0]) if things else None
    if name.find(', ') != -1:
        flipped = flip_name(name)
        things += get_things({'name': flipped, 'type': '/type/author'})
    match = []
    for key in things:
        db_entity = withKey(key)
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
        for k in 'last_modified', 'id', 'revision', 'created':
            if k in existing:
                del existing[k]
        new = existing
        new["create"] = "unless_exists"
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
            'create': 'unless_exists',
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

def check_if_loaded(loc):
    return bool(get_versions({'machine_comment': loc}))

def build_query(loc, rec):
    if 'table_of_contents' in rec:
        assert not isinstance(rec['table_of_contents'][0], list)
    book = {
        'create': 'unless_exists',
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

def add_keys(q):
    if 'authors' in q:
        for a in q['authors']:
            a.setdefault('key', '/a/OL%dA' % (get_author_num(web) + 1))
    q['key'] = '/b/OL%dM' % (get_book_num(web) + 1)
