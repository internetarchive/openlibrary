from urllib import urlopen
from openlibrary.catalog.utils import mk_norm
import json, re, codecs
#import couchdb, sys
#couch = couchdb.Server('http://ol-couch0.us.archive.org:5984/')
#db = couch['editions']

#for num, couch_id in enumerate(db):
#    print couch_id, couch_id, db[id]

re_parens = re.compile('\s*\((.*)\)\s*')

out = codecs.open('/1/labs/titles/list2', 'w', 'utf-8')

def cat_title(prefix, title):
    if not prefix:
        return mk_norm(title)
    if prefix[-1] != ' ':
        prefix += ' '
    return mk_norm(prefix + title)

def process(title_prefix, title, key):
    print >> out, cat_title(title_prefix, title), key
    if '(' in title and ')' in title:
        t1 = cat_title(title_prefix, re_parens.sub(' ', title))
        print >> out, t1, key
        t2 = cat_title(title_prefix, re_parens.sub(lambda m: ' ' + m.group(1) + ' ', title))
        print >> out, t2, key

def iter_editions():
    url = 'http://ol-couch0.us.archive.org:5984/editions/_all_docs?include_docs=true'
    first_line = True
    for line in urlopen(url):
        if first_line:
            print line
            first_line = False
            continue
        line = line.strip()
        assert line[-1] == ','
        line = line[:-1]
        d = json.loads(line)
        title = d['doc'].get('title')
        key = d['key']
        if not title:
            continue
        title_prefix = d['doc'].get('title_prefix')
        process(None, title, key)
        if title_prefix:
            process(title_prefix, title, key)

if __name__ == '__main__':
    iter_editions()

