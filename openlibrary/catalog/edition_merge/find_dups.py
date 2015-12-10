#!/usr/bin/python

from openlibrary.api import OpenLibrary
from subprocess import Popen, PIPE
import MySQLdb

ia_db_host = 'dbmeta.us.archive.org'
ia_db_user = 'archive'
ia_db_pass = Popen(["/opt/.petabox/dbserver"], stdout=PIPE).communicate()[0]

ol = OpenLibrary('http://openlibrary.org/')

local_db = MySQLdb.connect(db='merge_editions')
local_cur = conn.cursor()

archive_db = MySQLdb.connect(host=ia_db_host, user=ia_db_user, \
        passwd=ia_db_pass, db='archive')
archive_cur = conn.cursor()

fields = ['identifier', 'updated', 'collection']
sql_fields = ', '.join(fields)

archive_cur.execute("select " + sql_fields + \
    " from metadata" + \
    " where scanner is not null and mediatype='texts'" + \
        " and (not curatestate='dark' or curatestate is null)" + \
        " and collection is not null and boxid is not null and identifier not like 'zdanh_test%' and scandate is not null " + \
        " order by updated")

for num, (ia, updated, collection) in enumerate(cur.fetchall()):
    if 'lending' not in collection and 'inlibrary' not in collection:
        continue
    q = {'type': '/type/edition', 'ocaid': ia}
    editions = set(str(i) for i in ol.query(q))
    q = {'type': '/type/edition', 'source_records': 'ia:' + ia}
    editions.update(str(i) for i in ol.query(q))
    if len(editions) > 1:
        print (ia, list(editions))
        local_cur.execute('replace into merge (ia, editions) values (%s, %s)', [ia, ' '.join(editions)])
