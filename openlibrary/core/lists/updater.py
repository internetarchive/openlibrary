import re
import collections
import logging
import couchdb

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')

RE_SUBJECT = re.compile("[, _]+")

class Updater:
    def __init__(self, config):
        """Creates an updater instatance from the given configuration.
        
        The config must be a dictionary containing works_db, editions_db and
        seeds_db, each a url of couchdb database.
        """
        def f(name):
            return self.create_db(config[name])
            
        self.works_db = WorksDB(f("works_db"))
        self.editions_db = EditionsDB(f("editions_db"))
        self.seeds_db = SeedsDB(f("seeds_db"), self.works_db)
        
    def create_db(self, url):
        return couchdb.Database(url)
        
    def process_changeset(self, changeset):
        works = {}
        
        for work in self._get_works(changeset):
            self.works_db.update_work(work)
            works[work['key']] = work
            
        for edition in self._get_editions(changeset):
            work = self.works_db.update_edition(edition)
            works[work['key']] = work

        seeds = set(seed for work in works.values() 
                         for seed in self._get_seeds(work))
        self.seeds_db.update_seeds(seeds)
    
    def update_work(self, work):
        key = work['key']
        
        # update the works db
        work2 = self.works_db.get(key, {})
        works2.update(work)
        
        self.works_db[key] = work2
        
        seeds = _get_seeds(work2)
        
        # update all editions in the editions db
        for e in work2.get("editions", []):
            self.update_edition_in_editions_db(e, seeds)
            
        for seed in seeds:
            self.update_seeds_db(seed)
        
    def update_edition(self, edition):
        work = self.update_edition_in_works_db(edition)
        seeds = self._get_seeds(work)
        self.update_edition_in_editions_db(edition, seeds)

    def update_edition_in_works_db(self, edition):
        old_work = self._find()
        self.works_db.view("seeds/seeds", key=edition['key'])
        
    def update_edition_in_editions_db(self, edition, seeds=None):
        pass
        
    def update_seeds_db(self, seed):
        pass
        
    def _get_works(self, changeset):
        return [doc for doc in changeset.get("docs", []) 
                    if doc['key'].startswith("/works/")]
        
    def _get_editions(self, changeset):
        return [doc for doc in changeset.get("docs", []) 
                    if doc['key'].startswith("/books/")]
        
    def _get_seeds(self, work):
        return [k for k, v in SeedView().map(work)]
        
    def _find_old_work(self, edition_key):
        """Returns the key of the work that has this edition by querying the works_db.
        """
        pass

class WorksDB:
    """The works db contains the denormalized works.
    
    This class provides methods to update the database whenever a work or an
    edition is updated.
    """
    def __init__(self, db):
        self.db = db
        
    def update_work(self, work):
        """Adds/Updates the given work in the database.
        """
        logging.info("updating work %s", work['key'])
        
        key = work['key']
        work2 = self.db.get(key, {})
        if work2:
            work['_rev'] = work2['_rev']
        
        work['editions'] = work2.get('editions', [])
        self.db[key] = work
        
    def update_edition(self, edition):
        """Adds/updates the given edition in the database.
        """
        logging.info("updating edition %s", edition['key'])
        
        old_work_key = self._get_old_work_key(edition)
        
        try:
            work_key = edition.get("works", [])[0]['key']
        except IndexError:
            work_key = None

        # unlink the edition from old work if required
        if old_work_key and old_work_key != work_key:
            old_work = self.db[old_work_key]
            self._delete_edtion(old_work, edition)
            self.db.save(old_work)
        
        # Add/update the edition to the current work
        try:
            work = self.db[work_key]
        except KeyError:
            # That work is not found in the db.
            # Bad data? ignore for now.
            return None
            
        self._add_edition(work, edition)
        self.db.save(work)
        return work
        
    def _delete_edtion(self, work, edition):
        editions = dict((e['key'], e) for e in work.get('editions', []))
        del editions[edition['key']]
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
            
    def get_works(self, seed):
        return [row.doc for row in self.db.view("seeds/seeds", key=seed, include_docs=True)]
            
class EditionsDB:
    def __init__(self, db):
        self.db = db
        
    def update_edition(self, edition, seeds, changeset):
        edition['seeds'] = seeds
        self.db[edition['key']] = edition

class SeedsDB:
    """The seed db stores summary like work_count, edition_count, ebook_count,
    last_update, subjects etc for each seed.
    
    The class provides methods to update the seeds database by reprocessing
    the associated work docs from works db.
    """
    def __init__(self, db, works_db):
        self.db = db
        self.works_db = works_db
        
    def update_seeds(self, seeds):
        logging.info("update_seeds %s", seeds)
        docs = [self._get_seed_doc(seed) for seed in seeds]
        couchdb_bulk_save(self.db, docs)

    def _get_seed_doc(self, seed):
        works = self.works_db.get_works(seed)
        doc = SeedView().map_reduce(works, seed)
        doc['_id'] = seed
        return doc

def couchdb_bulk_save(db, docs):
    """Saves/updates the given docs into the given couchdb database using bulk save.
    """
    keys = [doc["_id"] for doc in docs if "_id" in doc]
    revs = dict((row.key, row.value["rev"]) for row in db.view("_all_docs", keys=keys)) 
    
    for doc in docs:
        id = doc.get('_id')
        if id in revs:
            doc['_rev'] = revs[id]
    
    db.update(docs)
    
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
            return [s for s in subjects + places + people + times if s is not None]

        type = work.get('type', {}).get('key')
        if type == "/type/work":
            authors = get_authors(work)
            subjects = get_subjects(work)
            editions = work.get('editions', [])

            last_modified = max(date['value'] for date in [work['last_modified']] + [e['last_modified'] for e in work.get('editions', [])])

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
            "subjects": []
        }
        for v in values:
            d["works"] += v['works']
            d['editions'] += v['editions']
            d['ebooks'] += v['ebooks']
            d['subjects'] += v['subjects']
            d['last_modified'] = max(d['last_modified'], v['last_modified'])
            
        d['subjects'] = self._process_subjects(d['subjects'])
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
        values = (v for work in works for k, v in self.map(work) if k == key)
        return self.reduce(values)
