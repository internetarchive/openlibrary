import collections
import itertools
import logging
import re
import urllib2

try:
    import multiprocessing
except ImportError:
    multiprocessing = None

import simplejson
import web

from openlibrary.core import formats, couch

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')

RE_SUBJECT = re.compile("[, _]+")

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
        for chunk in web.group(changesets, 200):
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
            self.works_db.db.commit()
            
            self.works_db.update_editions(ctx, editions)

            self.editions_db.update_editions(ctx.editions.values())
            
            if len(ctx.seeds) > 1000:
                self.works_db.db.commit()

                logging.info("BEGIN updating seeds")
                self.seeds_db.update_seeds(ctx.seeds.keys())
                ctx.seeds.clear()
                logging.info("END updating seeds")
            
            # reset to limit the make sure the size of cache never grows without any limit.
            if len(self.works_db.db.docs) > 1000:
                self.works_db.db.reset()
                
        self.works_db.db.commit()
        self.works_db.db.reset()
        
        logging.info("BEGIN updating seeds")
        self.seeds_db.update_seeds(ctx.seeds.keys())
        ctx.seeds.clear()
        logging.info("END updating seeds")
        
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
            
            old_seeds = set(self.get_seeds(old_work))
        else:
            work['editions'] = []
            old_seeds = set()
            

        work['_id'] = work['key']
        new_seeds = set(self.get_seeds(work))
        
        # Add both old and new seeds to the queue
        ctx.add_seeds(old_seeds)
        ctx.add_seeds(new_seeds)
        
        # Add editions to the queue if any of the seeds are modified
        if old_seeds != new_seeds:
            ctx.add_editions(work['editions'])
            
        save(work)
        return work
        
    def update_editions(self, ctx, editions):
        editions = list(editions)
        logging.info("works_db: update_editions %s", len(editions))
        # remove duplicate entries from editions
        editions = dict((e['key'], e) for e in editions).values()
        keys = [e['key'] for e in editions]
        
        old_works = dict((row.key, row.doc) 
                        for row in self.db.view("seeds2/seeds", keys=keys, include_docs=True) 
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

                old_seeds = self.get_seeds(old_work)
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

            new_seeds = self.get_seeds(work)
            ctx.add_seeds(new_seeds)
            ctx.add_editions([e])
            
    def update_edition(self, ctx, edition):
        self.update_editions(ctx, [edition])
        
    def __update_edition(self, ctx, edition):
        """Adds/updates the given edition in the database and returns the work from the database.
        """
        logging.info("updating edition %s", edition['key'])
        
        old_work_key = self._get_old_work_key(edition)
        
        try:
            work_key = edition.get("works", [])[0]['key']
        except IndexError:
            work_key = None

        # unlink the edition from old work if required
        if old_work_key and old_work_key != work_key:
            old_work = self.db.get(old_work_key)
            self._delete_edtion(old_work, edition)
            self.db.save(old_work)
            
            old_seeds = self.get_seeds(old_work)
            ctx.add_seeds(old_seeds)
            
        if work_key is None:
            return None
        
        # Add/update the edition to the current work
        work = self.db.get(work_key)
        if work is None:
            # That work is not found in the db.
            # Bad data? ignore for now.
            return None
            
        self._add_edition(work, edition)
        self.db.save(work)
        
        new_seeds = self.get_seeds(work)
        ctx.add_seeds(new_seeds)
        return work
        
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
        
    def get_work_counts(self, seed, chunksize=1000):
        rows = couch_iterview(self.db, "counts/counts", key=seed)
        return (row.value for row in rows)
        
    def get_seeds(self, work):
        return [k for k, v in SeedView().map(work)]
        
class EditionsDB:
    def __init__(self, db, works_db):
        self.db = db
        self.works_db = works_db
            
    def update_editions(self, editions):
        logging.info("edition_db: updating %d editions", len(editions))
        
        def get_work_key(e):
            if e.get('works'):
                return e['works'][0]['key']
                        
        work_keys = list(set(get_work_key(e) for e in editions if get_work_key(e) is not None))
        works = dict((row.id, row.doc) 
                    for row in self.works_db.db.view("_all_docs", keys=work_keys, include_docs=True) 
                    if "doc" in row)
                    
        seeds = dict((w['key'], self.works_db.get_seeds(w)) for w in works.values())
        
        for e in editions:
            key = e['key']
            logging.info("edition_db: updating edition %s", key)
            if e['type']['key'] == '/type/edition':
                wkey = get_work_key(e)
                e['seeds'] = seeds.get(wkey) or [e['key']]
            else:
                e.clear()
                e['_deleted'] = True
            e['_id'] = key
        
        couchdb_bulk_save(self.db, editions)
        
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
        counts = self.works_db.db.view("seeds2/seeds", keys=list(seeds))

        docs = dict((seed, self._get_seed_doc(seed, rows))
                    for seed, rows 
                    in itertools.groupby(counts, lambda row: row['key']))
                
        for s in seeds:
            if s not in docs:
                docs[s] = {"_id": s, "_deleted": True}
        
        couchdb_bulk_save(self.db, docs.values())
    
    def _get_seed_doc(self, seed, rows):
        doc = SeedView().reduce(row['value'] for row in rows)
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
    
    db.update(docs)
    
def couch_row_iter(url, keys):
    headers = {"Content-Type": "application/json"}
    
    req = urllib2.Request(url, simplejson.dumps({"keys": keys}), headers)
    f = urllib2.urlopen(req).fp
    f.readline() # skip the first line

    while True:
        line = f.readline().strip()
        if not line:
            break # error?

        if line.endswith(","):
            yield simplejson.loads(line[:-1])
        else:
            # last row
            yield simplejson.loads(line)
            break
    
def couch_iterview(db, viewname, chunksize=100, **options):
    print "couchdb %s: %s, %s, %s" % (db.name, viewname, chunksize, options)
    rows = db.view(viewname, limit=chunksize, **options).rows
    for row in rows:
        yield row
        docid = row.id
        
    while len(rows) == chunksize:
        rows = db.view(viewname, startkey_docid=docid, skip=1, limit=chunksize, **options).rows
        for row in rows:
            yield row
            docid = row.id

class SeedView:
    """Map-reduce view to compute seed info.
    
    This should ideally be part of a couchdb view, but it is too slow to run with couchdb.
    """
    def map(self, work):
        def get_authors(work):
            return [a['author'] for a in work.get('authors', []) if 'author' in a]

        def _get_subject(subject, prefix):
            if isinstance(subject, basestring):
                key = prefix + RE_SUBJECT.sub("_", subject.lower()).strip("_")
                return {"key": key, "name": subject}
                
        def get_subjects(work):
            subjects = [_get_subject(s, "subject:") for s in work.get("subjects", [])]
            places = [_get_subject(s, "place:") for s in work.get("subject_places", [])]
            people = [_get_subject(s, "person:") for s in work.get("subject_people", [])]
            times = [_get_subject(s, "time:") for s in work.get("subject_times", [])]
            d = dict((s['key'], s) for s in subjects + places + people + times if s is not None)
            return d.values()

        type = work.get('type', {}).get('key')
        if type == "/type/work":
            authors = get_authors(work)
            subjects = get_subjects(work)
            editions = work.get('editions', [])

            dates = (doc['last_modified'] for doc in [work] + work.get('editions', [])
                                          if 'last_modified' in doc)
            last_modified = max(date['value'] for date in dates or [""])

            xwork = {
                "works": 1,
                "editions": len(editions),
                "ebooks": sum(1 for e in editions if "ocaid" in e),
                "subjects": subjects,
                "last_modified": last_modified
            }

            yield work['key'], xwork
            for a in authors:
                yield a['key'], xwork

            for e in editions:
                yield e['key'], {
                    'works': 1,
                    'editions': 1,
                    'ebooks': int("ocaid" in e),
                    'last_modified': e['last_modified']['value'],
                    'subjects': subjects,
                }

            for s in subjects:
                yield s['key'], dict(xwork, subjects=[s])
    
    def reduce(self, values):
        d = {
            "works": 0,
            "editions": 0,
            "ebooks": 0,
            "last_modified": "",
        }
        subject_processor = SubjectProcessor()
        
        for v in values:
            d["works"] += v[0]
            d['editions'] += v[1]
            d['ebooks'] += v[2]
            d['last_modified'] = max(d['last_modified'], v[3])
            subject_processor.add_subjects(v[4])
            
        d['subjects'] = subject_processor.top_subjects()
        return d
            
    def _most_used(self, seq):
        d = collections.defaultdict(lambda: 0)
        for x in seq:
            d[x] += 1

        return sorted(d, key=lambda k: d[k], reverse=True)[0]

    def _process_subjects(self, subjects):
        d = collections.defaultdict(list)

        for s in subjects:
            d[s['key']].append(s['name'])

        subjects = [{"key": key, "name": self._most_used(names), "count": len(names)} for key, names in d.items()]
        subjects.sort(key=lambda s: s['count'], reverse=True)
        return subjects
        
    def map_reduce(self, works, key):
        values = (v for work in works 
                    for k, v in self.map(work) 
                    if k == key)
        return self.reduce(values)
        
class SubjectProcessor:
    """Processor to take a dict of subjects, places, people and times and build a list of ranked subjects.
    """
    def __init__(self):
        self.subjects = collections.defaultdict(list)
        
    def add_subjects(self, subjects):
        for s in subjects.get("subjects", []):
            self._add_subject('subject:', s)
            
    def _add_subject(self, prefix, name):
        s = self._get_subject(prefix, name)
        if s:
            self.subjects[s['key']].append(s['name'])
            
    def _get_subject(self, prefix, subject_name):
        if isinstance(subject_name, basestring):
            key = prefix + RE_SUBJECT.sub("_", subject_name.lower()).strip("_")
            return {"key": key, "name": subject_name}
        
    def _most_used(self, seq):
        d = collections.defaultdict(lambda: 0)
        for x in seq:
            d[x] += 1

        return sorted(d, key=lambda k: d[k], reverse=True)[0]
            
    def top_subjects(self, limit=100):
        subjects = [{"key": key, "name": self._most_used(names), "count": len(names)} for key, names in self.subjects.items()]
        subjects.sort(key=lambda s: s['count'], reverse=True)
        return subjects[:limit]

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