#!/usr/local/bin/python2.5
import web, anydbm, sys
import cjson
from catalog.load import add_keys
from copy import deepcopy
from catalog.merge.index import *
import psycopg2

web.config.db_parameters = dict(dbn='postgres', db='infobase_production', user='edward', pw='', host='pharosdb.us.archive.org')
web.load()
web.ctx.ip = '127.0.0.1'

from infogami.infobase.infobase import Infobase, NotFound
import infogami.infobase.writequery as writequery
site = Infobase().get_site('openlibrary.org')

path = '/1/pharos/edward/index/'
dbm_fields = ('lccn', 'oclc', 'isbn', 'title')
dbm = dict((i, anydbm.open(path + i + '.dbm', flag='w')) for i in dbm_fields)

urls = (
    '/', 'index'
)

def build_pool(index_fields):
    pool = {}
    for field in dbm_fields:
        if not field in index_fields:
            continue
        for v in index_fields[field]:
            if field == 'isbn' and len(v) < 10:
                continue
            try:
                v = str(v)
            except UnicodeEncodeError:
                print index_fields
                print `field, v`
                print v
                raise
            if v not in dbm[field]:
                continue
            found = [int(i) for i in dbm[field][v].split(' ')]
            pool.setdefault(field, set()).update(found)
    return dict((k, sorted(v)) for k, v in pool.iteritems())

def add_to_indexes(record, id, dbm):
    id = str(id)
    if 'title' not in record or record['title'] is None:
        return
    if 'subtitle' in record and record['subtitle'] is not None:
        title = record['title'] + ' ' + record['subtitle']
    else:
        title = record['title']
    st = str(short_title(title))
#    if st in dbm['title'] and id in dbm['title'][st].split(' '):
#        return # already done
    add_to_index(dbm['title'], st, id)
    if 'title_prefix' in record and record['title_prefix'] is not None:
        title2 = short_title(record['title_prefix'] + title)
        add_to_index(dbm['title'], title2, id)

    fields = [
        ('lccn', 'lccn', clean_lccn),
        ('oclc_numbers', 'oclc', None),
        ('isbn_10', 'isbn', None),
        ('isbn_13', 'isbn', None),
    ]
    for a, b, clean in fields:
        if a not in record:
            continue
        for v in record[a]:
            if not v:
                continue
            if clean:
                v = clean(v)
            add_to_index(dbm[b], v, id)

def add_to_database(orig, loc):
    # login as ImportBot
    site.get_account_manager().set_auth_token(site.withKey('/user/ImportBot'))

    while True:
        q = deepcopy(orig)
        add_keys(web, q)
        try:
            site.write(q, comment='initial import', machine_comment=loc)
            return q['key']
        except psycopg2.IntegrityError:
            pass

class index:
    def GET(self):
        web.header('Content-Type','application/json; charset=utf-8', unique=True)
        q = web.input()
        fields = dict((f, q[f].split('_')) for f in dbm_fields if f in q)
        pool = build_pool(fields)
        print cjson.encode({'fields': fields, 'pool': pool})
    def POST(self):
        q = cjson.decode(web.data())
        loc = q.pop('loc')
        key = add_to_database(q, loc)
        id = site.withKey(key).id
        add_to_indexes(q, id, dbm)
        print key
        
if __name__ == '__main__':
    try:
        web.run(urls, globals(), web.reloader)
    except:
        print "closing dbm files"
        print "closed"
        raise
