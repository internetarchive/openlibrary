import os, re, sys, codecs
from openlibrary.catalog.read_rc import read_rc
from openlibrary.catalog.importer.db_read import get_mc

sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, unmarshal, marshal

rc = read_rc()
ol = OpenLibrary("http://dev.openlibrary.org")
ol.login('EdwardBot', rc['EdwardBot']) 

test_dir = '/home/edward/ol/test_data'

re_edition = re.compile('^/b/OL\d+M$')

re_meta_mrc = re.compile('^([^/]*)_meta.mrc:0:\d+$')

#out = open('source_records', 'w')
for f in os.listdir(test_dir):
    key = f.replace('_', '/')
    if not re_edition.match(key):
        continue
    print key
    continue
    mc = get_mc(key)
    print key, mc
    if not mc:
        continue
    e = ol.get(key)
    if e.get('source_records', []):
        continue
    if mc.startswith('ia:') or mc.startswith('amazon:'):
        sr = mc
    else:
        m = re_meta_mrc.match(mc)
        sr = 'marc:' + mc if not m else 'ia:' + m.group(1)
    e['source_records'] = [sr]
    print >> out, (key, sr)
    print ol.save(key, e, 'add source record')
#out.close()
