import collections
import datetime
import itertools
import logging
import re
import time
import urllib2

try:
    import multiprocessing
except ImportError:
    multiprocessing = None

import simplejson
import web

from openlibrary.core import formats, couch
import engine

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')

class UpdaterContext:
    """The state of the updater.
    
    The updater context contains 3 dicts to store works, editions and seeds.
    """
    def __init__(self):
        self.editions = {}
        self.works = {}
        self.seeds = {}
        
    def add_editions(self, editions):
        for e in editions:
            self.editions[e['key']] = e
            
    def add_seeds(self, seeds):
        for s in seeds:
            self.seeds[s] = None
            
class Timer:
    def __init__(self):
        self.names = collections.defaultdict(lambda: web.storage(time=0.0, count=0))
        
    def start(self, name):
        d = self.names[name]
        d.start = time.time()
    
    def end(self, name):
        d = self.names[name]
        d.count += 1
        d.time += time.time() - d.start
        
    def print_summary(self):
        for k in sorted(self.names, key=lambda name: self.names[name].time):
            d = self.names[name]
            print "%s\t%s\t%s" % (k, d.time, d.count)
             
class CachedDatabase:
    """CouchDB Database that caches some documents locally for faster access.
    """
    def __init__(self, db):
        self.db = db
        self.docs = {}
        self.dirty = {}
        
    def preload(self, keys):
        for row in self.db.view("_all_docs", keys=keys, include_docs=True):
            if "doc" in row:
                self.docs[row.id] = row.doc
        
    def get(self, key, default=None):
        return self.docs.get(key) or self.db.get(key, default)
        
    def view(self, name, **kw):
        if kw.get("stale") != "ok":
            self.commit()
        return self.db.view(name, **kw)
    
    def save(self, doc):
        self.docs[doc['_id']] = doc
        self.dirty[doc['_id']] = doc
        
    def commit(self):
        if self.dirty:
            logging.info("commiting %d docs" % len(self.dirty))
            self.db.update(self.dirty.values())
            self.dirty.clear()
        
    def reset(self):
        self.commit()
        self.docs.clear()
        
    def __getattr__(self, name):
        return getattr(self.db, name)

class Updater:
    def __init__(self, config):
        """Creates an updater instatance from the given configuration.
        
        The config must be a dictionary containing works_db, editions_db and
        seeds_db, each a url of couchdb database.
        """
        def f(name):
            return self.create_db(config[name])
            
        def f2(name):
            return CachedDatabase(f(name))
            
        self.works_db = WorksDB(f2("works_db"))
        #self.works_db = WorksDB(f("works_db"))

        self.editions_db = EditionsDB(f("editions_db"), self.works_db)
        self.seeds_db = SeedsDB(f("seeds_db"), self.works_db)
        
    def create_db(self, url):
        return couch.Database(url)
    
    def process_changesets(self, changesets):
        ctx = UpdaterContext()
        for chunk in web.group(changesets, 50):
            chunk = list(chunk)
            
            works = [work for changeset in chunk 
                          for work in self._get_works(changeset)]

            editions = [e for changeset in chunk 
                        for e in self._get_editions(changeset)]
                        
            keys = [w['key'] for w in works] + [e['works'][0]['key'] for e in editions if e.get('works')] 
            keys = list(set(keys))
            self.works_db.db.preload(keys)
            
            for work in works:
                work = self.works_db.update_work(ctx, work)

            # works have been modified. Commit to update the views.
            logging.info("BEGIN commit works_db")
            self.works_db.db.commit()
            logging.info("END commit works_db")
            
            self.works_db.update_editions(ctx, editions)
            self.editions_db.update_editions(ctx.editions.values())
            
            t = datetime.datetime.utcnow().isoformat()
            if ctx.seeds:
                logging.info("BEGIN commit works_db")
                self.works_db.db.commit()
                logging.info("END commit works_db")
                
                logging.info("BEGIN mark %d seeds for update" % len(ctx.seeds))
                self.seeds_db.mark_seeds_for_update(ctx.seeds.keys())
                logging.info("END mark %d seeds for update" % len(ctx.seeds))
                ctx.seeds.clear()
            
            # reset to limit the make sure the size of cache never grows without any limit.
            if len(self.works_db.db.docs) > 1000:
                self.works_db.db.reset()
                
        self.works_db.db.commit()
        self.works_db.db.reset()
        
    def process_changeset(self, changeset):
        logging.info("processing changeset %s", changeset["id"])
        return self.process_changesets([changeset])
        
        ctx = UpdaterContext()
        
        for work in self._get_works(changeset):
            work = self.works_db.update_work(ctx, work)
            
        for edition in self._get_editions(changeset):
            self.works_db.update_edition(ctx, edition)

        self.seeds_db.update_seeds(ctx.seeds.keys())
        
        self.works_db.db.commit()
        self.works_db.db.reset()
        # TODO: update editions_db   
        
    def _get_works(self, changeset):
        return [doc for doc in changeset.get("docs", []) 
                    if doc['key'].startswith("/works/")]
    
    def _get_editions(self, changeset):
        return [doc for doc in changeset.get("docs", [])
                    if doc['key'].startswith("/books/")]
    
class WorksDB:
    """The works db contains the denormalized works.
    
    This class provides methods to update the database whenever a work or an
    edition is updated.
    """
    def __init__(self, db):
        self.db = db
        
    def update_works(self, ctx, works):
        pass
        
    def update_work(self, ctx, work, get=None, save=None):
        """Adds/Updates the given work in the database.
        """
        get = get or self.db.get
        save = save or self.db.save
        
        logging.info("works_db: updating work %s", work['key'])
        
        key = work['key']
        old_work = get(key, {})
        if old_work:
            if "_rev" in old_work:  # ugly side-effect of CachedDatabase.
                work['_rev'] = old_work['_rev']
            work['editions'] = old_work.get('editions', [])
            
            old_seeds = set(engine.get_seeds(old_work))
        else:
            work['editions'] = []
            old_seeds = set()

        work['_id'] = work['key']
        new_seeds = set(engine.get_seeds(work))
        
        # Add both old and new seeds to the queue
        ctx.add_seeds(old_seeds)
        ctx.add_seeds(new_seeds)
        
        def non_edition_seeds(seeds):
            return sorted(seed for seed in seeds if not seed.startswith("/books"))
        
        # Add editions to the queue if any of the seeds are modified
        if non_edition_seeds(old_seeds) != non_edition_seeds(new_seeds):
            ctx.add_editions(work['editions'])
            
        save(work)
        return work
        
    def update_editions(self, ctx, editions):
        editions = list(editions)
        logging.info("works_db: BEGIN update_editions %s", len(editions))
        # remove duplicate entries from editions
        editions = dict((e['key'], e) for e in editions).values()
        keys = [e['key'] for e in editions]
        
        old_works = dict((row.key, row.doc) 
                        for row in self.db.view("seeds/seeds", keys=keys, include_docs=True) 
                        if "doc" in row)
                        
        def get_work_key(e):
            if e.get('works'):
                return e['works'][0]['key']
                        
        work_keys = list(set(get_work_key(e) for e in editions if get_work_key(e) is not None))
        works = dict((row.id, row.doc) 
                    for row in self.db.view("_all_docs", keys=work_keys, include_docs=True) 
                    if "doc" in row)

        for e in editions:
            key = e['key']
            logging.info("works_db: updating edition %s", key)
            work_key = get_work_key(e)
            
            if key in old_works:
                old_work = old_works[key]
            else:
                old_work = None
            
            # unlink the edition from old work if required
            if old_work and old_work['key'] != work_key:
                self._delete_edtion(old_work, e)
                self.db.save(old_work)

                old_seeds = engine.get_seeds(old_work)
                ctx.add_seeds(old_seeds)
            
            if work_key is None:
                continue
            
            # Add/update the edition to the current work
            work = works.get(work_key)
            if work is None:
                # That work is not found in the db.
                # Bad data? ignore for now.
                return None

            self._add_edition(work, e)
            self.db.save(work)

            new_seeds = engine.get_seeds(work)
            ctx.add_seeds(new_seeds)
            ctx.add_editions([e])

        logging.info("works_db: END update_editions %s", len(editions))
            
    def update_edition(self, ctx, edition):
        self.update_editions(ctx, [edition])
        
    def _delete_edtion(self, work, edition):
        editions = dict((e['key'], e) for e in work.get('editions', []))
        
        key = edition['key']
        if key in editions:
            del editions[key]
            work['editions'] = editions.values()
        
    def _add_edition(self, work, edition):
        editions = dict((e['key'], e) for e in work.get('editions', []))
        editions[edition['key']] = edition
        work['editions'] = editions.values()
                
    def _get_work(self, edition):
        works = edition.get('works', [])
        if works:
            work_key = works[0]['key']
            return self.db.get(work_key)
        
    def _get_old_work_key(self, edition):
        try:
            return self.db.view("seeds/seeds", key=edition['key']).rows[0].id
        except IndexError:
            return None
            
    def get_works(self, seed, chunksize=1000):
        rows = self.db.view("seeds/seeds", key=seed, include_docs=True).rows
        return (row.doc for row in rows)
                        
class EditionsDB:
    def __init__(self, db, works_db):
        self.db = db
        self.works_db = works_db
            
    def update_editions(self, editions):
        logging.info("edition_db: BEGIN updating %d editions", len(editions))
        
        def get_work_key(e):
            if e.get('works'):
                return e['works'][0]['key']
                        
        work_keys = list(set(get_work_key(e) for e in editions if get_work_key(e) is not None))
        works = dict((row.id, row.doc) 
                    for row in self.works_db.db.view("_all_docs", keys=work_keys, include_docs=True) 
                    if "doc" in row)
                    
        def get_seeds(work):
            """Return non edition seeds of a work."""
            return [seed for seed in engine.get_seeds(w) if not seed.startswith("/books/")]
                    
        seeds = dict((w['key'], get_seeds(w)) for w in works.values())
        
        for e in editions:
            key = e['key']
            logging.info("edition_db: updating edition %s", key)
            if e['type']['key'] == '/type/edition':
                wkey = get_work_key(e)
                e['seeds'] = seeds.get(wkey) + [e['key']]
            else:
                e.clear()
                e['_deleted'] = True
            e['_id'] = key
        
        logging.info("edition_db: saving...")
        couchdb_bulk_save(self.db, editions)
        logging.info("edition_db: END updating %d editions", len(editions))

class SeedsDB:
    """The seed db stores summary like work_count, edition_count, ebook_count,
    last_update, subjects etc for each seed.
    
    The class provides methods to update the seeds database by reprocessing
    the associated work docs from works db.
    """
    def __init__(self, db, works_db):
        self.db = db
        self.works_db = works_db
        self._big_seeds = None
        
    def mark_seeds_for_update(self, seeds):
        docs = []
        t = datetime.datetime.utcnow().isoformat()
        
        for row in self.db.view("_all_docs", keys=seeds, include_docs=True).rows:
            if 'error' in row:
                doc = {"_id": row.key}
            else:
                doc = row.doc
            doc['dirty'] = t
            docs.append(doc)
        
        couchdb_bulk_save(self.db, docs)
    
    def update_seeds(self, seeds, chunksize=50):
        big_seeds = self.get_big_seeds()
        seeds2 = sorted(seed for seed in seeds if seed not in big_seeds)
        
        logging.info("update_seeds %s", len(seeds2))
        logging.info("ignored %d big seeds", len(seeds)-len(seeds2))

        for i, chunk in enumerate(web.group(seeds2, chunksize)):
            chunk = list(chunk)
            logging.info("update_seeds %d %d", i, len(chunk))
            self._update_seeds(chunk)
        
    def _update_seeds(self, seeds):
        counts = self.works_db.db.view("seeds/seeds", keys=list(seeds))

        docs = dict((seed, self._get_seed_doc(seed, rows))
                    for seed, rows 
                    in itertools.groupby(counts, lambda row: row['key']))
                
        for s in seeds:
            if s not in docs:
                docs[s] = {"_id": s, "_deleted": True}
        
        couchdb_bulk_save(self.db, docs.values())
    
    def _get_seed_doc(self, seed, rows):
        doc = engine.reduce_seeds(row['value'] for row in rows)
        doc['_id'] = seed
        return doc
        
    def get_big_seeds(self):
        if not self._big_seeds:
            # consider seeds having more than 500 works as big ones
            self._big_seeds =  set(row.key for row in self.db.view("sort/by_work_count", endkey=500, descending=True, stale="ok"))
            logging.info("found %d big seeds", len(self._big_seeds))
        return self._big_seeds
                
def couchdb_bulk_save(db, docs):
    """Saves/updates the given docs into the given couchdb database using bulk save.
    """
    keys = [doc["_id"] for doc in docs if "_id" in doc]
    revs = dict((row.key, row.value["rev"]) for row in db.view("_all_docs", keys=keys) if "value" in row) 
    
    for doc in docs:
        id = doc.get('_id')
        if id in revs:
            doc['_rev'] = revs[id]
    
    return db.update(docs)

def main(configfile):
    """Creates an updater using the config files and calls it with changesets read from stdin.
    
    Expects one changeset per line in JSON format.
    """
    config = formats.load_yaml(open(configfile).read())
    updater = Updater(config)
    
    changesets = (simplejson.loads(line.strip()) for line in sys.stdin)
    updater.process_changesets(changesets)

if __name__ == "__main__":
    import sys
    main(sys.argv[1])