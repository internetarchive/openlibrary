#!/usr/bin/python

import web, re, sys, codecs
from pprint import pprint

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

web.load()

from infogami.infobase.infobase import Infobase
import infogami.infobase.writequery as writequery
site = Infobase().get_site('openlibrary.org')

user = site.get_account_manager().get_user()
ctx = writequery.Context(site, author=user, ip=web.ctx.get('ip'), timestamp=None)

re_marc_name = re.compile('^(.*), (.*)$')
re_end_dot = re.compile('[^ ][^ ]\.$', re.UNICODE)
re_odd_dot = re.compile('[^ ][^ ]\. ', re.UNICODE)

author_type_id = get_type_id('/type/author')

def get_thing(id):
    sql = "select key, value from datum where thing_id=%d and end_revision=2147483647 and key != 'type'" % id
    iter = web.query(sql)
    thing = {}
    for row in iter:
        thing[row.key] = row.value
    return thing

def get_author_by_name(name):
    sql = "select d1.thing_id as id from thing, datum where thing.type=$type and and thing.id=datum and thing_id and datum.key='name' and datum.value=$name and datum.datatype=2 and datum.end_revision=2147483647"
    iter = web.query(sql, vars={'name': name, 'type': author_type_id})
    return [row.id for row in iter]

def flip_name(name):
    m = re_end_dot.search(name)
    if m: # strip dot
        name = name[:-1]

    m = re_marc_name.match(name)
    return m.group(2) + ' ' + m.group(1)

east_list = [line[:-1].lower() for line in open("east")]
east = frozenset(east_list + [flip_name(i) for i in east_list])

def author_dates_match(a, b):
    for k in ['birth_date', 'death_date', 'date']:
        if k in b and a[k] != b[k]:
            return False
    return True

def get_type_id(type):
    w = "key='" + type + "' and site_id=1"
    return web.select('thing', what='id', where=w)[0].id

print 'running query'
# limit for test runs
for thing_row in web.select('thing', what='id, key', where='type='+`author_type_id`, limit=10000):
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
    if not name:
        continue
    other = get_author_by_name(name)
    other_no_dot = []
    if name.find('.') != -1:
        name_no_dot = name.replace('.', '')
        other_no_dot = get_author_by_name(name_no_dot)
    if len(other) == 0 and len(other_no_dot) == 0 and not re_odd_dot.search(author['name']):
        continue
        print "rename %s to %s" % (`author['name']`, `name`)
        author['type'] = { 'key': '/type/author' }
        author['personal_name'] = { 'connect': 'delete' }
        author['name'] = name
        pprint(author)
#        q = ctx.make_query({'key': key, 'name': { 'connect': 'update', 'value': name}})
#        print `q`
        continue
    if (len(other) + len(other_no_dot)) != 1:
        continue
    same_name = get_author_by_name(author['name'])
    if len(same_name) > 1:
        continue
    if other_no_dot:
        other = other_no_dot
        name = name_no_dot
    author2 = get_thing(other[0])
    if not author_dates_match(author, author2):
        continue
    print 'merge author %s and %s' % (`author['name']`, `name`)
    del author['personal_name']
    pprint(author)
    pprint(author2)
    author['name'] == author2['name']
#    for k, v in author.iteritems():
#        if k in ('name', 'key'):
#            continue
#        if k in author2:
#            assert v == author2[k]
#            continue
#        author2[k] = v
    pprint(author2)

