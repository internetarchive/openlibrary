import web, re, os
from db_read import withKey
from openlibrary.catalog.utils import flip_name, author_dates_match, key_int, error_mail
from openlibrary.catalog.utils.query import query_iter
from pprint import pprint
from openlibrary.catalog.read_rc import read_rc
from openlibrary.api import OpenLibrary

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot'])

password = open(os.path.expanduser('~/.openlibrary_db_password')).read()
if password.endswith('\n'):
    password = password[:-1]
db_error = web.database(dbn='postgres', db='ol_errors', host='localhost', user='openlibrary', pw=password)

def walk_redirects(obj, seen):
    # called from find_author
    # uses ol client API
    seen.add(obj['key'])
    while obj['type'] == '/type/redirect':
        assert obj['location'] != obj['key']
        obj = ol.get(obj['location'])
        seen.add(obj['key'])
    return obj

def find_author(name, send_mail=True):
    q = {'type': '/type/author', 'name': name, 'limit': 0}
    reply = list(ol.query(q))
    authors = [ol.get(k) for k in reply]
    if any(a['type'] != '/type/author' for a in authors):
        subject = 'author query redirect: ' + repr(q['name'])
        body = 'Error: author query result should not contain redirects\n\n'
        body += 'query: ' + repr(q) + '\n\nresult\n'
        if send_mail:
            result = ''
            for a in authors:
                if a['type'] == '/type/redirect':
                    result += a['key'] + ' redirects to ' + a['location'] + '\n'
                elif a['type'] == '/type/delete':
                    result += a['key'] + ' is deleted ' + '\n'
                elif a['type'] == '/type/author':
                    result += a['key'] + ' is an author: ' + a['name'] + '\n'
                else:
                    result += a['key'] + 'has bad type' + a + '\n'
            body += result
            addr = 'edward@archive.org'
            #error_mail(addr, [addr], subject, body)
            db_error.insert('errors', query=name, result=result, t=web.SQLLiteral("now()"))
        seen = set()
        authors = [walk_redirects(a, seen) for a in authors if a['key'] not in seen]
    return authors

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
        db_entity = things[0]
#        if db_entity['type']['key'] == '/type/redirect':
#            db_entity = withKey(db_entity['location'])
        assert db_entity['type'] == '/type/author'
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
        assert a['type'] == '/type/author'
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
        assert existing['type'] == '/type/author'
        for k in 'last_modified', 'id', 'revision', 'created':
            if k in existing:
                del existing[k]
        new = existing
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

# {'publishers': [u'D. Obradovi'], 'pagination': u'204p.', 'source_records': [u'ia:zadovoljstvauivo00lubb'], 'title': u'Zadovoljstva u ivotu', 'series': [u'Srpska knjiecna zadruga.  [Izdanja] 133'], 'number_of_pages': {'type': '/type/int', 'value': 204}, 'languages': [{'key': '/languages/ser'}], 'lc_classifications': [u'BJ1571 A819 1910'], 'publish_date': '1910', 'authors': [{'key': '/authors/OL162549A'}], 'ocaid': u'zadovoljstvauivo00lubb', 'publish_places': [u'Beograd'], 'type': {'key': '/type/edition'}}

def build_query(loc, rec):
    if 'table_of_contents' in rec:
        assert not isinstance(rec['table_of_contents'][0], list)
    book = {
        'type': { 'key': '/type/edition'},
    }

    try:
        east = east_in_by_statement(rec)
    except:
        pprint(rec)
        raise
    if east:
        print rec

    langs = rec.get('languages', [])
    print langs
    if any(l['key'] == '/languages/zxx' for l in langs):
        print 'zxx found in langs'
        rec['languages'] = [l for l in langs if l['key'] != '/languages/zxx']
        print 'fixed:', langs

    for l in rec.get('languages', []):
        print l
        if l['key'] == '/languages/ser':
            l['key'] = '/languages/srp'
        if l['key'] in ('/languages/end', '/languages/enk', '/languages/ent', '/languages/enb'):
            l['key'] = '/languages/eng'
        if l['key'] == '/languages/emg':
            l['key'] = '/languages/eng'
        if l['key'] == '/languages/cro':
            l['key'] = '/languages/chu'
        if l['key'] == '/languages/jap':
            l['key'] = '/languages/jpn'
        if l['key'] == '/languages/fra':
            l['key'] = '/languages/fre'
        if l['key'] == '/languages/ila':
            l['key'] = '/languages/ita'
        if l['key'] == '/languages/gwr':
            l['key'] = '/languages/ger'
        if l['key'] == '/languages/fr ':
            l['key'] = '/languages/fre'
        if l['key'] == '/languages/it ':
            l['key'] = '/languages/ita'
        if l['key'] == '/languages/fle': # flemish -> dutch
            l['key'] = '/languages/dut'
        assert withKey(l['key'])

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
