#!/usr/bin/python

import web, re, sys, codecs
from pprint import pprint

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

web.load()

from infogami.infobase.infobase import Infobase
import infogami.infobase.writequery as writequery
site = Infobase().get_site('openlibrary.org')

re_marc_name = re.compile('^(.*), (.*)$')
re_end_dot = re.compile('[^ ][^ ]\.$', re.UNICODE)
re_odd_dot = re.compile('[^ ][^ ]\. ', re.UNICODE)
re_initial_then_dot = re.compile(r'\b[A-Z]\.')

def find_by_statements(author_key):
    q = {
        'authors': author_key,
        'type': '/type/edition',
    }
    by = []
    for key in site.things(q):
        try:
            by.append(site.withKey(key).by_statement.value)
        except AttributeError:
            pass
    return by

def east_in_by_statement(name, flipped, by_statements):
    assert name.find(', ') != -1
    name = name.replace('.', '')
    name = name.replace(', ', ' ')
    if name == flipped.replace('.', ''):
        return False
    for by in by_statements:
        if by.find(name) != -1:
            return True
    return False

def get_type_id(type):
    w = "key='" + type + "' and site_id=1"
    return web.select('thing', what='id', where=w)[0].id

author_type_id = get_type_id('/type/author')

def get_thing(id):
    sql = "select key, value from datum where thing_id=%d and end_revision=2147483647 and key != 'type'" % id
    iter = web.query(sql)
    thing = {}
    for row in iter:
        thing[row.key] = row.value
    return thing

def get_author_by_name(name):
    sql = "select id from thing, datum where thing.type=$type and thing.id=thing_id and datum.key='name' and datum.value=$name and datum.datatype=2 and datum.end_revision=2147483647"
    iter = web.query(sql, vars={'name': name, 'type': author_type_id})
    return [row.id for row in iter]

def flip_name(name):
    # strip end dots like this: "Smith, John." but not like this: "Smith, J."
    m = re_end_dot.search(name)
    if m:
        name = name[:-1]

    m = re_marc_name.match(name)
    return m.group(2) + ' ' + m.group(1)

def pick_name(a, b, flipped):
    if re_initial_then_dot.search(a):
        return flipped
    else:
        return b

east_list = [line[:-1].lower() for line in open("east")]
east = frozenset(east_list + [flip_name(i) for i in east_list])

def author_dates_match(a, b):
    for k in ['birth_date', 'death_date', 'date']:
        if k in a and k in b and a[k] != b[k]:
            return False
    return True

def get_other_authors(name):
    other = get_author_by_name(name)
    if name.find('.') != -1:
        name = name.replace('.', '')
        other.extend(get_author_by_name(name))
    return other

def key_int(rec):
    return int(web.numify(rec['key']))

def switch_author(old, new):
    q = { 'authors': old['key'], 'type': '/type/edition', }
    for key in site.things(q):
        edition = site.withKey(key)
        authors = []
        for author in edition.authors:
            if author.key == old['key']:
                author_key = new['key']
            else:
                author_key = author.key
            authors.append({ 'key': author_key })

        q = {
            'key': key,
            'authors': { 'connect': 'update_list', 'value': authors }
        }
#        pprint(q)
        site.write(q, comment='fix author name')

def make_redirect(old, new):
    q = {
        'key': old['key'],
        'location': {'connect': 'update', 'value': new['key'] },
        'type': {'connect': 'update', 'value': '/type/redirect' },
    }
    for k in old.iterkeys():
        if k != 'key':
            q[str(k)] = { 'connect': 'update', 'value': None }
#    pprint(q)
    print site.write(q, comment='replace with redirect')

def copy_fields(from_author, to_author, name):
    new_fields = { 'name': name, 'personal_name': name }
    for k, v in from_author.iteritems():
        if k in ('name', 'key'):
            continue
        if k in author:
            assert v == to_author[k]
        else:
            new_fields[k] = v
    return new_fields

def update_author(key, new):
    q = { 'key': key, }
    for k, v in new.iteritems():
        q[k] = { 'connect': 'update', 'value': v }
#    pprint(q)
    print site.write(q, comment='fix author name')

def merge_authors(author, merge_with, name):
    print 'merge author %s:"%s" and %s:"%s"' % (author['key'], author['name'], merge_with['key'], merge_with['name'])
    new_name = pick_name(author['name'], merge_with['name'], name)
    print 'becomes: "%s"' % new_name
    if key_int(author) < key_int(merge_with):
        new_key = author['key']
        print "copy fields from merge_with to", new_key
        new = copy_fields(merge_with, author, new_name)
        update_author(new_key, new)
        switch_author(merge_with, author)
#        print "delete merge_with"
        make_redirect(merge_with, author)
    else:
        new_key = merge_with['key']
        print "copy fields from author to", new_key
        new = copy_fields(merge_with, author, new_name)
        update_author(new_key, new)
        switch_author(author, merge_with)
#        print "delete author"
        make_redirect(author, merge_with)
    print

print 'running query'
# limit for test runs
for thing_row in web.select('thing', what='id, key', where='type='+repr(author_type_id), limit=10000):
    id = thing_row.id
    author = get_thing(id)

    if 'personal_name' not in author \
            or author['personal_name'] != author['name']:
        continue
    if author['name'].find(', ') == -1:
        continue
    if author['name'].lower().replace('.', '') in east:
        continue

    key = author['key']
    name = flip_name(author['name'])
    other = get_other_authors(name)
    if len(other) == 0 and not re_odd_dot.search(author['name']):
        by_statements = find_by_statements(author['key'])
        print author['name'], "by:", ', '.join('"%s"' % i for i in by_statements)
        if east_in_by_statement(author['name'], name, by_statements):
            print("east in by statement")
            continue
        print("rename %s to %s" % (repr(author['name']), repr(name)))
        q = {
            'key': key,
            'name': { 'connect': 'update', 'value': name},
            'personal_name': { 'connect': 'update', 'value': name},
        }
        print(repr(q))
        continue

    if len(other) != 1:
#        print "other length:", other
        continue
    # don't merge authors when more than one like "Smith, John"
    if len(get_author_by_name(author['name'])) > 1:
#        print "found more authors with same name"
        continue

    merge_with = get_thing(other[0])
    try:
        if not author_dates_match(author, merge_with):
            print "date mismatch"
            continue
    except KeyError:
        pprint(author)
        pprint(merge_with)
        raise
    by_statements = find_by_statements(author['key'])
    print author['name'], "by:", ', '.join('"%s"' % i for i in by_statements)
    if east_in_by_statement(author['name'], name, by_statements):
        print "east in by statement"
        print
        continue
    merge_authors(author, merge_with, name)
