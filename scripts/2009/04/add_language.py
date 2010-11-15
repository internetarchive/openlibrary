from catalog.utils.query import query_iter, set_staging, withKey, get_mc
import sys, codecs, re
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, Reference
from catalog.read_rc import read_rc
from catalog.get_ia import get_from_archive, get_from_local
from catalog.marc.fast_parse import get_first_tag, get_all_subfields
rc = read_rc()

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
set_staging(True)

ol = OpenLibrary("http://dev.openlibrary.org")
ol.login('EdwardBot', rc['EdwardBot'])

q = { 'type': '/type/edition', 'table_of_contents': None, 'subjects': None }
queue = []
count = 0
for e in query_iter(q, limit=100):
    key = e['key']
    mc = get_mc(key)
    if not mc:
        continue
    data = get_from_local(mc)
    line = get_first_tag(data, set(['041']))
    if not line:
        continue
    print key, line[0:2], list(get_all_subfields(line))

