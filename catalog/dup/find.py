import web, sys
from catalog.read_rc import read_rc
import psycopg2
from catalog.infostore import get_site

# need to use multiple databases
# use psycopg2 to until open library is upgraded to web 3.0

rc = read_rc()

conn = psycopg2.connect("dbname='%s' user='%s' host='%s' password='%s'" \
        % ('ol_merge', rc['user'], rc['host'], rc['pw']));
cur1 = conn.cursor()
cur2 = conn.cursor()

site = get_site()

for line in open('dups'):
    v, num = eval(line)
    cur2.execute('select key from isbn where value=%(v)s', {'v':v})
    print v
    for i in cur2.fetchall():
        key = i[0]
        t = site.withKey(key)
        print '  ', key
        print '    ', t.title.encode('utf-8')
        print '    ', site.versions({'key': key})[0].machine_comment


sys.exit(0)
cur1.execute('select value, count(*) as num from isbn group by value having count(*) > 1')
for i in cur1.fetchall():
    print i
    cur2.execute('select key from isbn where value=%(v)s', {'v':i[0]})
    print cur2.fetchall()
