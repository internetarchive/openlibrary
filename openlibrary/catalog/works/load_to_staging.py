import sys
sys.path.remove('/usr/local/lib/python2.5/site-packages/web.py-0.23-py2.5.egg')
from staging_save import Infogami
from catalog.read_rc import read_rc
import catalog.importer.db_read as db_read
import re, sys, codecs

db_read.set_staging(True)

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

rc = read_rc()
infogami = Infogami()
infogami.login('edward', rc['edward'])

for line in open('works_for_staging'):
    work_key, title, authors, editions = eval(line)
    if not all(db_read.withKey('/a/' + a) for a in authors):
        continue
    work = db_read.withKey(work_key)
    print work_key
    if work:
        continue
    if not work:
        q = {
            'create': 'unless_exists',
            'type': { 'key': '/type/work' },
            'key': work_key,
            'title': title,
            'authors': [{'key': '/a/' + a} for a in authors],
        }
        ret = infogami.write(q, comment='create work')
        print ret
    for edition_key in editions:
        edition = db_read.withKey(edition_key)
        if not edition: continue
        if 'works' in edition: continue
        q = {
            'key': edition_key,
            'works': { 'connect': 'update_list', 'value': [{'key': work_key}]}
        }
        ret = infogami.write(q, comment='add work to edition')
        print edition_key, ret
        assert ret['result']['updated']
