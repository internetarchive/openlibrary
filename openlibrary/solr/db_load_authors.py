import json
import web
import re

re_author_key = re.compile(r'^/a/OL(\d+)A$')

db = web.database(dbn='mysql', db='openlibrary')
db.printing = False

total = 6540759

sizes = dict(name=512, birth_date=256, death_date=256, date=256)

num = 0
for line in open('author_file'):
    num += 1
    if num % 10000 == 0:
        print("%d %d %.2f%%" % (num, total, (float(num) * 100.0) / total))
    src_a = json.loads(line[:-1])
    m = re_author_key.match(src_a['key'])
    assert m
    akey_num = int(m.group(1))
    db_a = {'akey': akey_num}

    for f in 'name', 'birth_date', 'death_date', 'date':
        if not src_a.get(f, None):
            continue
        db_a[f] = src_a[f]
        if len(db_a[f]) > sizes[f] - 1:  # type: ignore[arg-type]
            print(f, len(db_a[f]), db_a[f])  # type: ignore[arg-type]

    if 'alternate_names' in src_a:
        assert all('\t' not in n for n in src_a['alternate_names'])
        db_a['alt_names'] = '\t'.join(src_a['alternate_names'])  # type: ignore[assignment]
    db.insert('authors', **db_a)
