from openlibrary.core.mocks import mock_couchdb
from openlibrary.core.lists import updater
import re
import os

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
            return open(path).read().strip()
    
    return read(root)
    
class TestWorksDB:
    def setup_method(self, method):
        db = mock_couchdb.Database()
        db.save(read_couchapp("works/seeds"))
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
                {"id": "/works/OL1W", "key": "/books/OL1M", "value": None},
                {"id": "/works/OL1W", "key": "/works/OL1W", "value": None}
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

class TestSeedView:
    def test_map(self):
        work = {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "authors": [
                {"author": {"key": "/authors/OL1A"}}
            ],
            "editions": [
                {
                    "key": "/books/OL1M", 
                    "ocaid": "foobar",
                    "last_modified": {"type": "/type/datetime", "value": "2010-11-11 10:20:30"}
                },
                {
                    "key": "/books/OL2M", 
                    "last_modified": {"type": "/type/datetime", "value": "2009-01-02 10:20:30"}
                }
                
            ],
            "subjects": ["Love"],
            "last_modified": {"type": "/type/datetime", "value": "2010-01-02 10:20:30"}
        }
        
        view = updater.SeedView()
        
        rows = dict(view.map(work))
        assert sorted(rows.keys()) == sorted(["/authors/OL1A", "/books/OL1M", "/books/OL2M", "/works/OL1W", "subject:love"])
        
        d = {
            "works": 1,
            "editions": 2,
            "ebooks": 1,
            "last_modified": "2010-11-11 10:20:30",
            "subjects": [
                {"name": "Love", "key": "subject:love"}
            ]
        }
        assert rows['/works/OL1W'] == d
        assert rows['/authors/OL1A'] == d

        assert rows['/books/OL1M'] == dict(d, editions=1)
        assert rows['/books/OL2M'] == dict(d, editions=1, ebooks=0, last_modified="2009-01-02 10:20:30")

    def test_reduce(self):
        d1 = {
            "works": 1,
            "editions": 2,
            "ebooks": 1,
            "last_modified": "2010-11-11 10:20:30",
            "subjects": [
                {"name": "Love", "key": "subject:love"},
                {"name": "Hate", "key": "subject:hate"}
            ]
        }

        d2 = {
            "works": 1,
            "editions": 1,
            "ebooks": 0,
            "last_modified": "2009-01-02 10:20:30",
            "subjects": [
                {"name": "Love", "key": "subject:love"}
            ]
        }
        view = updater.SeedView()
        
        assert view.reduce([d1, d2]) == {
            "works": 2,
            "editions": 3,
            "ebooks": 1,
            "last_modified": "2010-11-11 10:20:30",
            "subjects": [
                {"name": "Love", "key": "subject:love", "count": 2},
                {"name": "Hate", "key": "subject:hate", "count": 1}
            ]
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
        
    def _get_doc(self, dbname, id):
        doc = self.databases[dbname].get(id)
        if doc:
            del doc["_id"]
            del doc["_rev"]
        return doc
        
    def test_process_changeset(self):
        # Add a new book and new work and make sure the works and seeds databases are updated.
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
        
        keys = sorted(self.databases["works"])
        assert keys == ["/works/OL1W", "_design/seeds"]
        
        keys = sorted(self.databases["seeds"])
        assert keys == ["/books/OL1M", "/works/OL1W", "subject:love"]
        
        assert self._get_doc("seeds", "/works/OL1W") == {
            "works": 1,
            "editions": 1,
            "ebooks": 0,
            "last_modified": "2010-10-20 10:20:30",
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
        assert self._get_doc("seeds", "/works/OL1W") == {
            "works": 1,
            "editions": 2,
            "ebooks": 1,
            "last_modified": "2010-10-20 15:25:35",
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
        assert self._get_doc("seeds", "/works/OL1W") == {
            "works": 1,
            "editions": 2,
            "ebooks": 1,
            "last_modified": "2010-10-25 15:25:35",
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
        assert self._get_doc("seeds", "subject:love") == None
