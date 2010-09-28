from catalog.utils.query import query_iter, set_staging, withKey
import sys, codecs, re
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, Reference
from catalog.read_rc import read_rc
rc = read_rc()

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
set_staging(True)

ol = OpenLibrary("http://dev.openlibrary.org")
ol.login('EdwardBot', rc['EdwardBot'])

re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon)\.$')

def has_dot(s):
    return s.endswith('.') and not re_skip.search(s)

q = { 'type': '/type/edition', 'table_of_contents': None, 'subjects': None }
queue = []
count = 0
for e in query_iter(q):
    if not e.get('subjects', None) or not any(has_dot(s) for s in e['subjects']):
        continue
    subjects = [s[:-1] if has_dot(s) else s for s in e['subjects']]
    q = {
        'key': e['key'],
        'subjects': {'connect': 'update_list', 'value': subjects },
    }
    # need to fix table_of_contents to pass validation
    toc = e['table_of_contents']
    if toc and (isinstance(toc[0], basestring) or toc[0]['type'] == '/type/text'):
        if isinstance(toc[0], basestring):
            assert all(isinstance(i, basestring) for i in toc)
            new_toc = [{'title': i, 'type': '/type/toc_item'} for i in toc]
        else:
            assert all(i['type'] == '/type/text' for i in toc)
            new_toc = [{'title': i['value'], 'type': '/type/toc_item'} for i in toc]
        q['table_of_contents'] = {'connect': 'update_list', 'value': new_toc }
    queue.append(q)
    count += 1
    if len(queue) == 100:
        print count, 'writing to db'
        print ol.write(queue, "remove trailing period from subjects")
        queue = []

print ol.write(queue, "remove trailing period from subjects")
