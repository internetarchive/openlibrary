import re, web
from catalog.importer.db_read import get_mc

re_meta_mrc = re.compile('^([^/]*)_meta.mrc:0:\d+$')
re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon)\.$')

db_amazon = web.database(dbn='postgres', db='amazon')
db_amazon.printing = False

def amazon_source_records(asin):
    iter = db_amazon.select('amazon', where='asin = $asin', vars={'asin':asin})
    return ["amazon:%s:%s:%d:%d" % (asin, r.seg, r.start, r.length) for r in iter]

def has_dot(s):
    return s.endswith('.') and not re_skip.search(s)

def fix_toc(e):
    toc = e.get('table_of_contents', None)
    if not toc:
        return
    if isinstance(toc[0], dict) and toc[0]['type'] == '/type/toc_item':
        if len(toc) == 1 and 'title' not in toc[0]:
            del e['table_of_contents'] # remove empty toc
        return
    new_toc = [{'title': unicode(i), 'type': '/type/toc_item'} for i in toc if i != u'']
    e['table_of_contents'] = new_toc

def fix_subject(e):
    if e.get('subjects', None) and any(has_dot(s) for s in e['subjects']):
        subjects = [s[:-1] if has_dot(s) else s for s in e['subjects']]
        e['subjects'] = subjects

def get_and_fix_edition(key, e):
    existing = get_mc(key)
    if 'source_records' not in e and existing:
        amazon = 'amazon:'
        if existing.startswith('ia:'):
            sr = [existing]
        elif existing.startswith(amazon):
            sr = amazon_source_records(existing[len(amazon):]) or [existing]
        else:
            m = re_meta_mrc.match(existing)
            sr = ['marc:' + existing if not m else 'ia:' + m.group(1)]
        e['source_records'] = sr

    fix_toc(e)
    fix_subject(e)
    return e
