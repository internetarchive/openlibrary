import web, re, os
from openlibrary.catalog.utils import flip_name, author_dates_match, key_int, error_mail
from openlibrary.catalog.importer.load import do_flip, east_in_by_statement

password = open(os.path.expanduser('~/.openlibrary_db_password')).read()
if password.endswith('\n'):
    password = password[:-1]

def find_author(name, send_mail=True):
    def walk_redirects(obj, seen):
        seen.add(obj['key'])
        while obj['type']['key'] == '/type/redirect':
            assert obj['location'] != obj['key']
            obj = web.ctx.site.get(obj['location'])
            seen.add(obj['key'])
        return obj

    q = {'type': '/type/author', 'name': name} # FIXME should have no limit
    reply = list(web.ctx.site.things(q))
    authors = [web.ctx.site.get(k) for k in reply]
    if any(a['type']['key'] != '/type/author' for a in authors):
        seen = set()
        authors = [walk_redirects(a, seen) for a in authors if a['key'] not in seen]
    return authors

def pick_from_matches(author, match): # no DB calls in this function
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

def find_entity(author): # no direct DB calls
    name = author['name']
    things = find_author(name)
    if author['entity_type'] != 'person':
        if not things:
            return None
        db_entity = things[0]
        assert db_entity['type']['key'] == '/type/author'
        return db_entity
    if ', ' in name:
        things += find_author(flip_name(name))
    match = []
    seen = set()
    for a in things:
        key = a['key']
        if key in seen:
            continue
        seen.add(key)
        orig_key = key
        assert a['type']['key'] == '/type/author'
        if 'birth_date' in author and 'birth_date' not in a:
            continue
        if 'birth_date' not in author and 'birth_date' in a:
            continue
        if not author_dates_match(author, a):
            continue
        match.append(a)
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
        assert existing['type']['key'] == '/type/author'
        for k in 'last_modified', 'id', 'revision', 'created':
            if k in existing:
                del existing[k]
        new = existing
        if 'death_date' in author and 'death_date' not in existing:
            new['death_date'] = author['death_date']
        return new
    if not eastern:
        do_flip(author)
    a = { 'type': { 'key': '/type/author' } }
    for f in 'name', 'title', 'personal_name', 'birth_date', 'death_date', 'date':
        if f in author:
            a[f] = author[f]
    return a

class InvalidLanguage(Exception):
    def __init__(self, code):
        self.code = code
    def __str__(self):
        return "invalid language code: '%s'" % self.code

type_map = { 'description': 'text', 'notes': 'text', 'number_of_pages': 'int' }

def build_query(rec):
    book = {
        'type': { 'key': '/type/edition'},
    }

    east = east_in_by_statement(rec)

    for k, v in rec.iteritems():
        if k == 'authors':
            book[k] = [import_author(v[0], eastern=east)]
            continue
        if k == 'languages':
            langs = []
            for l in v:
                if web.ctx.site.get('/languages/' + l) is None:
                    raise InvalidLanguage(l)
            book[k] = [{'key': l} for l in v]
            continue
        if k in type_map:
            t = '/type/' + type_map[k]
            if isinstance(v, list):
                book[k] = [{'type': t, 'value': i} for i in v]
            else:
                book[k] = {'type': t, 'value': v}
        else:
            book[k] = v

    return book
