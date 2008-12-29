from urllib2 import urlopen, Request
import cjson, web
from catalog.merge.merge_index import add_to_indexes

# need to use multiple databases
# use psycopg2 to until open library is upgraded to web 3.0

import psycopg2
from catalog.read_rc import read_rc
rc = read_rc()
conn = psycopg2.connect("dbname='%s' user='%s' host='%s' password='%s'" \
        % ('ol_merge', rc['user'], rc['host'], rc['pw']));
cur = conn.cursor()

index_path = '/1/pharos/edward/index/2/'

pool_url = 'http://wiki-beta.us.archive.org:9020/'

db_fields = ('isbn', 'title', 'oclc', 'lccn')

def pool_build(fields):
    params = dict((k, '_'.join(v)) for k, v in fields.iteritems() if k != 'author')
    url = pool_url + "?" + web.http.urlencode(params)
    ret = cjson.decode(urlopen(url).read())
    return ret['pool']

def pool_update(key, q):
    q['key'] = key
    req = Request(pool_url, cjson.encode(q))
    urlopen(req).read()

def build(index_fields):
    pool = {}
    for field in db_fields:
        if not field in index_fields:
            continue
        for v in index_fields[field]:
            if field == 'isbn' and len(v) < 10:
                continue
            cur.execute('select key from ' + field + ' where value=%(v)s', {'v': v})
            pool.setdefault(field, set()).update(i[0] for i in cur.fetchall())
    return dict((k, sorted(v)) for k, v in pool.iteritems())

def update(key, q):
    seen = set()
    for field, value in add_to_indexes(q):
        vars = {'key': key, 'value': value }
        if (field, value) in seen:
            print (key, field, value)
            print seen
            print q
        assert (field, value) not in seen
        seen.add((field, value))
#        cur.execute('select * from ' + field + ' where key=%(key)s and value=%(value)s', vars)
#        if len(cur.fetchall()) != 0:
#            print "key dup: key=%s, value=%s" % (key, value)
#            print q
#            continue
        cur.execute('insert into ' + field + ' (key, value) values (%(key)s, %(value)s)', vars)
    q['key']

def post_progress(archive_id, q):
    url = pool_url + "store/" + archive_id
    req = Request(url, cjson.encode(q))
    urlopen(req).read()

def get_start(archive_id):
    url = pool_url + "store/" + archive_id
    data = urlopen(url).read()
    return cjson.decode(data)
