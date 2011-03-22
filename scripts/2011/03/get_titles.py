import web

db = web.database( dbn='postgres', host='ol-db', db='openlibrary')

edition_id = list(db.query("select id, key from thing where key='/type/edition'"))[0].id

get_fields = ["'%s'" % i for i in ['title','work_title','work_titles','title_prefix','subtitle']]
sql = "select id, name from property where type=52 and name in (%s)" % ','.join(get_fields)
properties = dict((row.id, row.name) for row in db.query(sql))

print edition_id
print properties

out = open('/1/labs/titles/list', 'w')
keys = ', '.join(`k` for k in properties.keys())
sql = "select key, key_id, value from edition_str, thing where key_id in (%s) and thing_id=thing.id and type=%d" % (keys, edition_id)
db_iter = db.query(sql)

# slow because web.py uses fetchall (maybe)
for row in db_iter:
    print >> out, (row.key, properties[row.key_id], row.value)
out.close()
