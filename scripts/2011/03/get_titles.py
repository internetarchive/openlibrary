import web, psycopg2, sys

conn = psycopg2.connect("dbname='openlibrary' host='ol-db'")
cur = conn.cursor()

cur.execute("select id, key from thing where key='/type/edition'")
edition_id = cur.fetchone()[0]
print edition_id

get_fields = ["'%s'" % i for i in ['title','work_title','work_titles','title_prefix','subtitle']]
sql = "select id, name from property where type=52 and name in (%s)" % ','.join(get_fields)
print sql
cur.execute(sql)
properties = dict(cur.fetchall())
print properties

keys = ', '.join(repr(k) for k in properties.keys())
#sql = "select key, key_id, value, ordering from edition_str, thing where key_id in (%s) and thing_id=thing.id and type=%d" % (keys, edition_id)
sql = "select thing_id, key_id, value, ordering from edition_str where key_id in (%s)" % (keys,)
print sql
cur.execute(sql)

out = open('/1/labs/titles/list', 'w')
rows = cur.fetchmany()
while rows:
    for key, key_id, value, ordering in rows:
        print >> out, (key, properties[key_id], value, ordering)
    rows = cur.fetchmany()
out.close()
