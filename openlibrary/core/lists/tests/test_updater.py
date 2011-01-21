from openlibrary.mocks import mock_couchdb
from openlibrary.core.lists import updater
import re
import os
import simplejson

def read_couchapp(path):
    """Reads the couchapp from repository_root/couchapps/$path.
    """
    import openlibrary
    root = os.path.dirname(openlibrary.__file__) + "/../couchapps/" + path

    def read(path):
        if os.path.isdir(path):
            d = {}
            for f in os.listdir(path):
                name = os.path.splitext(f)[0]
                value = read(os.path.join(path, f))
                d[name] = value
            return d
        else:
            value = open(path).read().strip()
            # special care to make this function compatible with couchapp.
            # couchapp dumps the json after the second nested level.
            if value.startswith("{"):
                value = simplejson.loads(value)
            return value
    
    return read(root)
    
class TestWorksDB:
    def setup_method(self, method):
        db = mock_couchdb.Database()
        db.save(read_couchapp("works/seeds"))
        db['_design/seeds2'] = db['_design/seeds']
        self.works_db = updater.WorksDB(db)
        self.ctx = updater.UpdaterContext()
        
    def _get_doc(self, key):
        doc = self.works_db.db.get(key)
        if doc:
            del doc['_id']
            del doc['_rev']
        return doc
        
    def _add_doc(self, doc):
        doc['_id'] = doc['key']
        doc.setdefault("type", {"key": "/type/work"})
        self.works_db.db.save(doc)
        
    def test_update_work(self):
        # test adding for the first time
        self.works_db.update_work(self.ctx, {
            "key": "/works/OL1W",
            "title": "foo"
        })
        
        assert self._get_doc("/works/OL1W") == {
            "key": "/works/OL1W",
            "title": "foo",
            "editions": []
        }
        
        # test changing the title
        self.works_db.update_work(self.ctx, {
            "key": "/works/OL1W",
            "title": "bar"
        })
        assert self._get_doc('/works/OL1W') == {
            "key": "/works/OL1W",
            "title": "bar",
            "editions": []
        }
        
    def test_update_work_with_editions(self):
        # setup database
        self.works_db.db['/works/OL1W'] = {
            "key": "/works/OL1W",
            "title": "foo",
            "subjects": ["x"],
            "editions": [
                {"key": "/books/OL1M"}
            ]
        }

        self.works_db.update_work(self.ctx, {
            "key": "/works/OL1W",
            "title": "bar",
        })
        
        assert self._get_doc("/works/OL1W") == {
            "key": "/works/OL1W",
            "title": "bar",
            "editions": [
                {"key": "/books/OL1M"}
            ]
        }
        
    def test_update_edition(self):
        self._add_doc({
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "title": "foo",
            "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}
        })
        
        self.works_db.update_edition(self.ctx, {
          "key": "/books/OL1M",
          "works": [{"key": "/works/OL1W"}],
          "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}
        })
        
        assert self._get_doc("/works/OL1W") == {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "title": "foo",
            "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"},
            "editions": [{
                "key": "/books/OL1M",
                "works": [{"key": "/works/OL1W"}],
                "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}                
            }]
        }
    
    def test_mock_view(self):
        """Test to makesure the mock couchdb is working as expected.
        """
        self._add_doc({
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "editions": [{"key": "/books/OL1M"}]
        })
        print self._view("seeds/seeds")
        assert self._view("seeds/seeds") == {
            "total_rows": 2,
            "offset": 0,
            "rows": [
                {"id": "/works/OL1W", "key": "/books/OL1M", "value": [1, 1, 0, "", {}]},
                {"id": "/works/OL1W", "key": "/works/OL1W", "value": [1, 1, 0, "", {}]}
            ]
        }
        
    def _view(self, name, **options):
        results = self.works_db.db.view(name, **options)
        return {
            "total_rows": results.total_rows,
            "offset": results.offset,
            "rows": [dict(row) for row in results.rows]
        }
        
    def test_update_edition_work_change(self):
        self.works_db.db['/works/OL1W'] = {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "editions": [{"key": "/books/OL1M"}],
            "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}
        }
        self.works_db.db['/works/OL2W'] = {
            "key": "/works/OL2W",
            "type": {"key": "/type/work"},
            "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}
        }
        assert self.works_db._get_old_work_key({"key": "/books/OL1M"}) == "/works/OL1W"
        
        self.works_db.update_edition(self.ctx, {
          "key": "/books/OL1M",
          "works": [{"key": "/works/OL2W"}],
          "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}
        })
        
        assert self._get_doc("/works/OL1W") == {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"},
            "editions": []
        }
        assert self._get_doc("/works/OL2W") == {
            "key": "/works/OL2W",
            "type": {"key": "/type/work"},
            "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"},
            "editions": [{
                "key": "/books/OL1M",
                "works": [{"key": "/works/OL2W"}],
                "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}            
            }]
        }
        
class TestUpdater:
    def setup_method(self, method):
        
        databases = {}
        self.databases = databases

        databases["works"] = mock_couchdb.Database()
        databases["editions"] = mock_couchdb.Database()
        databases["seeds"] = mock_couchdb.Database()
        
        
        class Updater(updater.Updater):
            def create_db(self, url):
                return databases[url]
                
        config = dict(works_db="works", editions_db="editions", seeds_db="seeds")
        self.updater = Updater(config)
        
        databases["works"].save(read_couchapp("works/seeds"))
        databases['works']['_design/seeds2'] = databases['works']['_design/seeds']
        databases['seeds'].save(read_couchapp("seeds/sort"))
        databases['seeds'].save(read_couchapp("seeds/dirty"))
        
    def _get_doc(self, dbname, id):
        doc = self.databases[dbname].get(id)
        if doc:
            del doc["_id"]
            del doc["_rev"]
        return doc
        
    def _update_pending_seeds(self):
        seeds = [row.id for row in self.databases['seeds'].view("dirty/dirty")]
        self.updater.update_seeds(seeds)
        
    def test_process_changeset(self):
        # Add a new book and new work and make sure the works, editions and seeds databases are updated.
        changeset = {
            "id": "1234",
            "author": {"key": "/people/anand"},
            "docs": [{
                "key": "/works/OL1W",
                "type": {"key": "/type/work"},
                "subjects": ["Love"],
                "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}
            }, {
                "key": "/books/OL1M",
                "type": {"key": "/type/edition"},
                "works": [{"key": "/works/OL1W"}],
                "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}
            }]
        }
        
        self.updater.process_changeset(changeset)
        self._update_pending_seeds()
        
        def get_docids(db):
            return sorted(k for k in db if not k.startswith("_"))
        
        assert get_docids(self.databases['works']) == ["/works/OL1W"]
        assert get_docids(self.databases['editions']) == ["/books/OL1M"]
        assert get_docids(self.databases['seeds']) == ["/books/OL1M", "/works/OL1W", "subject:love"]
        
        assert self._get_doc("editions", "/books/OL1M") == {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "works": [{"key": "/works/OL1W"}],
            "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"},
            "seeds": ["/works/OL1W", "subject:love", "/books/OL1M"]
        }
        
        assert self._get_doc("seeds", "/works/OL1W") == {
            "works": 1,
            "editions": 1,
            "ebooks": 0,
            "last_update": "2010-10-20 10:20:30",
            "subjects": [
                {"name": "Love", "key": "subject:love", "count": 1}
            ]
        }
        
        # Add a new book to the same work and make sure the seed info is updated
        changeset = {
            "id": "1235",
            "author": {"key": "/people/anand"},
            "docs": [{
                "key": "/books/OL2M",
                "type": {"key": "/type/edition"},
                "works": [{"key": "/works/OL1W"}],
                "ocaid": "foobar",
                "last_modified": {"type": "/type/datetime", "value": "2010-10-20 15:25:35"}
            }]
        }
        
        self.updater.process_changeset(changeset)
        self._update_pending_seeds()
        
        assert self._get_doc("seeds", "/works/OL1W") == {
            "works": 1,
            "editions": 2,
            "ebooks": 1,
            "last_update": "2010-10-20 15:25:35",
            "subjects": [
                {"name": "Love", "key": "subject:love", "count": 1}
            ]
        }
        
        # Update an old edition and make sure the seed info is updated
        changeset = {
            "id": "1236",
            "author": {"key": "/people/anand"},
            "docs": [{
                "key": "/books/OL1M",
                "type": {"key": "/type/edition"},
                "works": [{"key": "/works/OL1W"}],
                "last_modified": {"type": "/type/datetime", "value": "2010-10-25 15:25:35"}
            }]
        }
        self.updater.process_changeset(changeset)
        self._update_pending_seeds()
        
        assert self._get_doc("seeds", "/works/OL1W") == {
            "works": 1,
            "editions": 2,
            "ebooks": 1,
            "last_update": "2010-10-25 15:25:35",
            "subjects": [
                {"name": "Love", "key": "subject:love", "count": 1}
            ]
        }

    def test_process_changeset_old_seed(self):
        # save a book and work 
        changeset = {
            "id": "1234",
            "author": {"key": "/people/anand"},
            "docs": [{
                "key": "/works/OL1W",
                "type": {"key": "/type/work"},
                "subjects": ["Love"],
                "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}
            }, {
                "key": "/books/OL1M",
                "type": {"key": "/type/edition"},
                "works": [{"key": "/works/OL1W"}],
                "last_modified": {"type": "/type/datetime", "value": "2010-10-20 10:20:30"}
            }]
        }
        self.updater.process_changeset(changeset)
        self._update_pending_seeds()
        
        # change the subject and make sure the counts of old changeset are updated
        changeset = {
            "id": "1235",
            "author": {"key": "/people/anand"},
            "docs": [{
                "key": "/works/OL1W",
                "type": {"key": "/type/work"},
                "last_modified": {"type": "/type/datetime", "value": "2010-10-20 15:25:35"}
            }]
        }
        self.updater.process_changeset(changeset)
        self._update_pending_seeds()
        
        assert self._get_doc("seeds", "subject:love") == None
