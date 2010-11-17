from openlibrary.core.mocks.mock_couchdb import Database

class TestMockCouchDB:
    def test_save(self):
        db = Database()
        assert db.get("foo") is None
        
        db.save({"_id": "foo", "name": "foo"})
        
        assert db.get("foo") == {
            "_id": "foo",
            "_rev": "1",
            "name": "foo"
        }
        
    def _view(self, db, name, **options):
        result = db.view(name, wrapper=dict, **options)
        return {
            "total_rows": result.total_rows,
            "offset": result.offset,
            "rows": result.rows
        }

    def test_all_docs(self):
        db = Database()
        assert self._view(db, "_all_docs") == {
            "total_rows": 0,
            "offset": 0,
            "rows": []
        }
        
        for id in "abc":
            db.save({"_id": id})
        
        assert self._view(db, "_all_docs") == {
            "total_rows": 3,
            "offset": 0,
            "rows": [
                {"id": "a", "key": "a", "value": {"rev": "1"}},
                {"id": "b", "key": "b", "value": {"rev": "1"}},
                {"id": "c", "key": "c", "value": {"rev": "1"}},
            ]
        }
        
    def test_view(self):
        db = Database()
        db.save({
            "_id": "_design/names",
            "views": {
                "names": {
                    "map": "" +  
                        "def f(doc):\n" + 
                        "    if 'name' in doc:\n"
                        "        yield doc['name'], None"
                }
            }
        })
        
        db.save({"_id": "a", "name": "a"})
        db.save({"_id": "b", "name": "b"})
        db.save({"_id": "c", "name": "c"})
        
        assert self._view(db, "names/names") == {
            "total_rows": 3,
            "offset": 0,
            "rows": [
                {"id": "a", "key": "a", "value": None},
                {"id": "b", "key": "b", "value": None},
                {"id": "c", "key": "c", "value": None},
            ]
        }

        assert self._view(db, "names/names", key='b') == {
            "total_rows": 3,
            "offset": 1,
            "rows": [
                {"id": "b", "key": "b", "value": None},
            ]
        } 