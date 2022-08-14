import web
import re
import json

db = web.database(dbn='mysql', user='root', passwd='', db='openlibrary')
db.printing = False

re_work_key = re.compile(r'^/works/OL(\d+)W$')

total = 13941626

for num, line in enumerate(open('work_file')):
    if num % 10000 == 0:
        print("%d %d %.2f%%" % (num, total, (float(num) * 100.0) / total))
    # src_w = json.loads(line[:-1])
    w = eval(line)
    match = re_work_key.match(w['key'])
    assert match
    wkey = int(match.group(1))
    vars = {'k': wkey, 'title': w['title']}
    db.query('replace into works (wkey, title) values ($k, $title)', vars=vars)
