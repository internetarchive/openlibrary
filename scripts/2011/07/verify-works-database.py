"""Script to makes sure the works coucudb database is up-to-date.
"""
import web
import sys
import logging
import datetime

from infogami import config
import couchdb

from openlibrary.core.lists import engine, updater

LIMIT = 1000

logger = logging.getLogger("openlibrary.script")

@web.memoize
def get_works_db():
    """Returns couchdb databse for storing works.
    """
    db_url = config.get("lists", {}).get("works_db")
    return couchdb.Database(db_url)
    
@web.memoize
def get_editions_db():
    db_url = config.get("lists", {}).get("editions_db")
    return couchdb.Database(db_url)
    
@web.memoize
def get_seeds_engine():
    """Returns updater.SeedsDB instance."""
    db_url = config.get("lists", {}).get("seeds_db")
    db = couchdb.Database(db_url)
    return updater.SeedsDB(db, web.storage(db=get_works_db()))
    
def query(site, q):
    q["limit"] = LIMIT
    keys = site.things(q)
    
    # qeury for remaning if there are still more keys
    if len(keys) == LIMIT:
        q["offset"] = q.get("offset", 0) + LIMIT
        keys += query(q)
    return keys
    
def get_work(site, key):
    """Returns work dict with editions filled in.
    """
    work = site.get(key).dict()
    edition_keys = query(site, {"type": "/type/edition", "works": key})
    work['editions'] = [doc.dict() for doc in site.get_many(edition_keys)]
    return work
    
def _couch_save(db, doc):
    logger.info("Adding %s to %s db", doc['_id'], db.name)
    
    olddoc = db.get(doc['_id'])
    if olddoc:
        doc['_rev'] = olddoc['_rev']
    db.save(doc)
    
def update_work(work):
    db = get_works_db()
    work['_id'] = work['key']
    _couch_save(db, work)    

def update_editions(work):
    """Adds add editions of this work to editions db.
    """
    seeds = engine.get_seeds(work)
    db = get_editions_db()

    for e in work['editions']:
        e = dict(e, seeds=seeds, _id=e['key'])
        _couch_save(db, e)

def update_seeds(work):
    seeds = engine.get_seeds(work)
    logger.info("updating seeds: %s", seeds)
    get_seeds_engine().update_seeds(seeds)
    
def uniq(values):
    """Returns uniq values while preserving the order.
    """
    uniq_values = []
    visited = set()
    
    for v in values:
        if v not in visited:
            visited.add(v)
            uniq_values.append(v)
            
    return uniq_values
    
def get_work_keys(site, keys):
    """Substitutes edition keys with their work keys.
    """
    work_keys = [k for k in keys if k.startswith("/works/")]
    edition_keys = [k for k in keys if k.startswith("/books/")]
    if edition_keys:
        editions = [doc.dict() for doc in site.get_many(edition_keys)]
        for e in editions:
            for w in e.get("works", []):
                work_keys.append(w['key'])
    
    return uniq(work_keys)
    
def update(site, keys):
    """Updates the entries for gives keys in the list databases.
    
    For a work:
        * the work is updated in the works_db
        * all its editions are updated in editions_db
        * all the seeds are updated in seeds_db
    
    Updating an edition is same as updating its work.
    """
    logger.info("BEGIN update")
    keys = get_work_keys(site, keys)
    
    for key in keys:
        work = get_work(site, key)
        update_work(work)
        update_editions(work)
        update_seeds(work)
    logger.info("END update")
    
def verify_doc(doc):
    if doc['type']['key'] == '/type/work':
        db = get_works_db()
    elif doc['type']['key'] == '/type/edition':
        db = get_editions_db()
    else:
        return True
        
    rev = doc['revision']
    doc2 = db.get(doc['key'])
    rev2 = doc2 and doc2['revision'] or 0
    
    if rev2 < rev:
        logger.error("db has stale entry for %s (%s < %s)", doc['key'], rev2, rev)
        return False
    
    return True

def verify(site, keys):
    """Verifies the freshness of the docs in the couchdb and returns the list of stale keys.
    """
    docs = web.ctx.site.get_many(keys)
    
    stale = []
    for doc in docs:
        if not verify_doc(doc):
            stale.append(doc['key'])
            
    return stale
        
def verify_day(site, day, do_update=False):
    logger.info("BEGIN verify_day %s", day)
    changes = get_modifications(site, day)
    changes = (k for k in changes if k.startswith("/works/") or k.startswith("/books/"))
    
    stale_count = 0
    total_count = 0
    
    for keys in web.group(changes, 1000):
        stale = verify(site, keys)
        if do_update and stale:
            logger.info("updating %s stale docs", len(stale))
            update(site, stale)
        else:
            logger.info("found %s/%d stale docs", len(stale), len(keys))
            
        stale_count += len(stale)
        total_count += len(keys)
        
    logger.info("END verify_day. found %d/%d stale docs", stale_count, total_count)
        
def get_modifications(site, day):
    """Returns an iterator over all the modified docs in a given day (as string).
    """
    limit = 100
    
    n = limit
    offset = 0
    
    yyyy, mm, dd = map(int, day.split("-"))
    
    begin_date = datetime.date(yyyy, mm, dd)
    end_date = begin_date + datetime.timedelta(days=1)
    
    while n == limit:
        changes = site.recentchanges({"begin_date": begin_date.isoformat(), "end_date": end_date.isoformat(), "limit": limit, "offset": offset})
        changes = [c.dict() for c in changes]
        n = len(changes)
        offset += n
        for c in changes:
            for x in c['changes']:
                yield x['key']
                
        break
                
def main():
    #update(web.ctx.site, sys.argv[1:])
    verify_day(web.ctx.site, sys.argv[1], "--update" in sys.argv)

if __name__ == '__main__':
    web.config.debug = True
    main()