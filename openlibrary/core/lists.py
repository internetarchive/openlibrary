"""Library to perform offline operations for managing lists.

The data for lists is maintained in the seed_* tables. These tables can be
part of the openlibrary database or a separate dabatase.
"""

import web
import simplejson

from infogami.infobase import client
from openlibrary.plugins.openlibrary import connection

SCHEMA = """
create table seed_editions (
    id serial primary key,
    seed text,
    work text,
    edition text,
    ebook boolean
);
create index seed_editions_seed_idx on seed_editions(seed);
create index seed_editions_edition_idx on seed_editions(edition);

create table seed_updates (
    id serial primary key,
    tx_id int,
    seed text,
    timestamp timestamp,

    UNIQUE(seed, tx_id)
);
"""

class ListsEngine:
    """Engine to perform all offline updates for lists.
    
    This engine works with settings. 
    
        {
            "db": {
                "db": "openlibrary",
                "user": "openlibrary",
                "pw": ""
            },
            "infobase_server": "localhost:7000",
            "lists_db": {
                "db": "ol_lists",
                "user": "openlibrary",
                "pw": ""
            },
            "memcache_servers": [
                "localhost:11211"
            ],
        }
    """
    def __init__(self, settings):
        """Creates lists engine with the given settings.
        """
        if "infobase_server" in settings:
            self.infobase_conn = client.RemoteConnection(settings["infobase_server"])
        elif "db" in settings:
            web.config.db_parameters = settings['db']
            self.infobase_conn = client.LocalConnection(**settings["db"])
        else:
            raise Exception("Either infobase_server or db must be specified in the settings.")
        
        if "memcache_servers" in settings:
            self.infobase_conn = connection.MemcacheMiddleware(self.infobase_conn, settings['memcache_servers'])
            
            # Looks like memcache still has the old data. MigrationMiddleware corrects it.
            self.infobase_conn = connection.MigrationMiddleware(self.infobase_conn)
            
        if "lists_db" in settings:
            db_params = settings['lists_db'].copy()
            db_params.setdefault("dbn", "postgres")
            self.db = web.database(**db_params)
        else:
            raise Exception("lists_db is not specified in the settings.")
        
    def index_editions(self, edition_keys):
        """Takes a list of edition keys, loads the edition docs and work docs
        from memcache/db and indexed them in seed_editions table.
        """
        editions = self._get_docs(edition_keys).values()
        work_keys = [w['key'] 
                    for e in editions
                    for w in e.get('works', [])]
        works = self._get_docs(work_keys)
        self._index_edition_docs(editions, works)
        
    def index_updates(self, changeset_ids):
        pass
        
    def _index_edition_docs(self, editions, works):
        """Takes a list of editions and a dict of works of those editions and
        updates the seed_editions table.
        """
        if not editions:
            return

        p = EditionProcessor()
        
        data = [dict(seed=seed, work=work, edition=edition, ebook=ebook)
            for e in editions
            for seed, work, edition, ebook in p.process_edition(e, works)
            if e.get("type", {}).get("key") == "/type/edition"
            ]
            
        edition_keys = [e['key'] for e in editions]
        
        t = self.db.transaction()
        try:
            self.db.query(
                "DELETE FROM seed_editions WHERE edition in $edition_keys", 
                vars=locals())
            self.db.multiple_insert("seed_editions", data, seqname=False)
        except:
            t.rollback()
            raise
        else:
            t.commit()
        
    def _get_docs(self, keys):
        """Returns docs for the specified keys as a dictionary.
        """
        docs = {}
        
        for keys2 in web.group(keys, 500):
            json = self.infobase_conn.request(
                sitename="openlibrary.org",
                path="/get_many",
                data={"keys": simplejson.dumps(keys2)})
            docs2 = simplejson.loads(json)
            docs.update(docs2)
        return docs    
        
class EditionProcessor:
    """Computes seed info for an edition.
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
