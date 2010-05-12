import web, re
import simplejson as json

db = web.database(dbn='mysql', user='root', passwd='', db='openlibrary')
db.printing = False

re_work_key = re.compile('^/works/OL(\d+)W$')

total = 13941626
num = 0
for line in open('work_file'):
    num += 1
    if num % 10000 == 0:
        print "%d %d %.2f%%" % (num, total, (float(num) * 100.0) / total)
    #src_w = json.loads(line[:-1])
    w = eval(line)
    wkey = int(re_work_key.match(w['key']).group(1))
    vars={'k':wkey, 'title':w['title']}
    db.query('replace into works (wkey, title) values ($k, $title)', vars=vars)
