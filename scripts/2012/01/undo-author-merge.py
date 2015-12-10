"""Script to undo a bad author-merge.

http://openlibrary.org/recentchanges/2011/05/31/merge-authors/43575781

Usage:
    ./scripts/openlibrary-server openlibrary.yml runscript undo-author-merge.py
"""
import web
import json
import urllib2
import shelve
from infogami.infobase.client import ClientException

change_id = "43575781"


cache = shelve.open("cache.shelve")

def get_doc(key, revision):
    if revision == 0:
        return {
            "key": key,
            "type": {"key": "/type/delete"}
        }
    else:
        kv = "%s@%s" % (key, revision)
        
        if kv not in cache:
            cache[kv] = web.ctx.site.get(key, revision).dict()
        else:
            print kv, "found in cache"
        return cache[kv]
        
def get_work_authors(work):
    authors = work.get('authors') or []
    if authors:
        return [a['author']['key'] for a in authors if 'author' in a]
    else:
        return []
        
def get_work(edition):
    works = edition.get('works')
    return works and works[0]['key'] or None

def main():
    changeset = web.ctx.site.get_change(change_id).dict()
    
    keys = [c['key'] for c in changeset['changes']]
    revs = dict((c['key'], c['revision']) for c in changeset['changes'])
    old_docs = dict((c['key'], get_doc(c['key'], c['revision']-1)) for c in changeset['changes'])
    latest_docs = dict((doc['key'], doc) for doc in web.ctx.site.get_many(keys, raw=True))
    
    undo_docs = {}
    
    def process_keys(keys):
        for key in keys:
            old_doc = old_docs[key]
            new_doc = latest_docs[key]
        
            if new_doc['type']['key'] != old_doc['type']['key']:
                print key, "TYPE CHANGE", old_doc['type']['key'], new_doc['type']['key']
                undo_docs[key] = old_doc
            elif new_doc['type']['key'] == '/type/work' and new_doc.get('authors') != old_doc.get('authors'):
                print key, 'AUTHOR CHANGE', get_work_authors(old_doc), get_work_authors(new_doc)
                doc = dict(new_doc, authors=old_doc.get('authors') or [])
                undo_docs[key] = doc
            elif old_doc['type']['key'] == '/type/edition' and new_doc.get('works') != old_doc.get('works'):
                print key, 'WORK CHANGE', get_work(old_doc), get_work(new_doc)
                doc = dict(new_doc, works=old_doc.get('works') or [])
            
                if doc.get('works'):
                    wkey = doc['works'][0]['key']
                    work = old_docs.get(wkey)
                    if work is not None:
                        doc['authors'] = [{'key': key} for key in get_work_authors(work)]
                        undo_docs[key] = doc
                    else:
                        print key, "IGNORING, WORK NOTFOUND", wkey
                                        
    # process authors, works and books in order
    # XXX: Running all of them together is failing. 
    # Ran the script 3 times enabling just one of the following 3 lines each time.
    process_keys(k for k in keys if k.startswith('/authors/'))
    #process_keys(k for k in keys if k.startswith('/works/'))
    #process_keys(k for k in keys if k.startswith('/books/'))
    
    web.ctx.site.login("AnandBot", "**-change-this-before-running-the-script-**")

    data = {
        "parent_changeset": change_id
    }
    print "saving..."
    web.ctx.ip = '127.0.0.1'
    try:
        web.ctx.site.save_many(undo_docs.values(), action="undo", data=data, comment='Undo merge of "Miguel de Unamuno" and "Miguel de Cervantes Saavedra"') 
    except ClientException, e:
        print 'ERROR', e.json
    
if __name__ == '__main__':
    try:
        main()
    finally:
        cache.close()