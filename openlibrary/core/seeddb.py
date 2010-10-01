"""Library to manage the database of seed info that is used by lists.

The seeddb contains 2 tables.

create table seed_editions (
    id serial primary key,
    seed text,
    work text,
    edition text,
    ebook boolean
);

create table seed_updates (
    id serial primary key,
    tx_id int references transaction,
    seed text,
    timestamp timestamp,
    
    UNIQUE(seed, tx_id)
);

"""

class SeedDB:
    def __init__(self, db):
        self.db = db
        
    def seed_edition(self, edition, works):
        """Updates the seed_editions table for the given edition.
        
        The works argument must be a dictionary containing works of the given edition.
        """
        self.seed_multiple_editions([editon], works)
        
    def seed_multiple_editions(self, editions, works):
        """Updates the seed_editions table for all the provided list of editions.
        
        The works argument must be a dictionary containing works of all the editions
        provided.
        """
        engine = SeedEngine()
        
        data = [dict(seed=seed, work=work, edition=edition, ebook=ebook)
            for seed, work, edition, ebook in engine.process_edition(e, works)
            for e in editions]
            
        edition_keys = [e['key'] for e in editions]
        
        t = self.db.transaction()
        self.db.query(
            "DELETE seed_editions WHERE edition in $edition_keys", 
            vars=locals())
        self.db.multiple_insert("seed_editions", data, seqname=False)
        
        
class SeedEngine:
    """Engine to compute the seed info from docs and updates.
    """
    
    def process_edition(self, edition, works):
        """Returns a generator with (seed, work, edition, ebook) rows.
        
        :param edition: the edition to process
        :param works: dictionary containing the works of edition
        :rtype: generator with (seed, work, edition, ebook) rows
        """
        ebook = bool(edition.get("ocaid"))
        
        edition_key = edition['key']
        
        if edition.get("works"):
            for w in edition['works']:
                work_key = w['key']
                work = works[work_key]
                yield edition_key, work_key, edition_key, ebook

                for seed in self.find_work_seeds(work):
                    yield seed, work_key, edition_key, ebook
        else:
            # the edition is not linked to any work
            yield edition_key, None, edition_key, ebook
                
    def find_work_seeds(self, work):
        """Returns all seeds of the given work.
        
        The seeds of a work includes the work, all authors and subjects.
        """
        yield work['key']
        
        for a in work.get('authors', []):
            # take key from {"author": {"key": "/authors/OL1M"}}
            seed = a.get('author', {}).get('key')
            if seed:
                yield seed
                
        def get_subjects(name, prefix):
            for s in work.get(name, []):
                if isinstance(s, basestring):
                    yield prefix + self.process_subject(s) 
                
        for seed in get_subjects("subjects", prefix="subject:"):
            yield seed
        
        for seed in get_subjects("subject_places", prefix="place:"):
            yield seed
            
        for seed in get_subjects("subject_people", prefix="person:"):
            yield seed
        
        for seed in get_subjects("subject_times", prefix="time:"):
            yield seed
    
    def process_subject(self, subject):
        return subject.lower().replace(' ', '_').replace(',','')
