import web, sys, codecs, os.path
from catalog.read_rc import read_rc
import psycopg2
from catalog.infostore import get_site
from catalog.merge.merge_marc import attempt_merge, build_marc
import catalog.marc.fast_parse as fast_parse

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

# need to use multiple databases
# use psycopg2 to until open library is upgraded to web 3.0

rc = read_rc()
threshold = 875

conn = psycopg2.connect("dbname='%s' user='%s' host='%s' password='%s'" \
        % ('ol_merge', rc['user'], rc['host'], rc['pw']));
cur1 = conn.cursor()
cur2 = conn.cursor()

site = get_site()

marc_path = '/2/pharos/marc/'

def get_marc(loc):
    try:
        filename, p, l = loc.split(':')
    except ValueError:
        return None
    if not os.path.exists(marc_path + filename):
        return None
    f = open(marc_path + filename)
    f.seek(int(p))
    buf = f.read(int(l))
    f.close()
    rec = fast_parse.read_edition(buf)
    if rec:
        return build_marc(rec)

for line in open('dups'):
    v, num = eval(line)
    cur2.execute('select key from isbn where value=%(v)s', {'v':v})
    editions = []
    for i in cur2.fetchall():
        key = i[0]
        t = site.withKey(key)
        mc =  site.versions({'key': key})[0].machine_comment
        editions.append({'key': key, 'title': t.title, 'loc': mc})
    if len(editions) != 2:
        continue
    if any(not i['loc'] or i['loc'].startswith('amazon:') for i in editions):
        continue
    e1 = get_marc(editions[0]['loc'])
    if not e1:
        continue
    e2 = get_marc(editions[1]['loc'])
    if not e2:
        continue

#    print v, [i['title'] for i in editions]
#    print e1
#    print e2
    match = attempt_merge(e1, e2, threshold, debug=False)
    if match:
        print tuple([v] + [i['key'] for i in editions])

sys.exit(0)
cur1.execute('select value, count(*) as num from isbn group by value having count(*) > 1')
for i in cur1.fetchall():
    print i
    cur2.execute('select key from isbn where value=%(v)s', {'v':i[0]})
    print cur2.fetchall()
