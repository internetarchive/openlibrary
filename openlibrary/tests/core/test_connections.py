# This will be moved to core soon.
import json

from openlibrary.plugins.openlibrary import connection as connections


class MockConnection:
    def __init__(self):
        self.docs = {}

    def request(self, sitename, path, method="GET", data=None):
        data = data or {}
        if path == "/get":
            key = data['key']
            if key in self.docs:
                return json.dumps(self.docs[key])
        if path == "/get_many":
            keys = json.loads(data['keys'])
            return json.dumps({k: self.docs[k] for k in keys})
        else:
            return None


class TestMigrationMiddleware:
    def test_title_prefix(self):
        conn = connections.MigrationMiddleware(MockConnection())

        def add(doc):
            conn.conn.docs[doc['key']] = doc

        def get(key):
            json_data = conn.request("openlibrary.org", "/get", data={"key": key})
            return json.loads(json_data)

        add(
            {
                "key": "/books/OL1M",
                "type": {"key": "/type/edition"},
                "title_prefix": "The",
                "title": "Book",
            }
        )

        assert get("/books/OL1M") == {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title": "The Book",
        }

        add(
            {
                "key": "/books/OL2M",
                "type": {"key": "/type/edition"},
                "title_prefix": "The ",
                "title": "Book",
            }
        )

        assert get("/books/OL2M") == {
            "key": "/books/OL2M",
            "type": {"key": "/type/edition"},
            "title": "The Book",
        }

        add(
            {
                "key": "/books/OL3M",
                "type": {"key": "/type/edition"},
                "title_prefix": "The Book",
            }
        )

        assert get("/books/OL3M") == {
            "key": "/books/OL3M",
            "type": {"key": "/type/edition"},
            "title": "The Book",
        }

    def test_authors(self):
        conn = connections.MigrationMiddleware(MockConnection())

        def add(doc):
            conn.conn.docs[doc['key']] = doc

        def get(key):
            json_data = conn.request("openlibrary.org", "/get", data={"key": key})
            return json.loads(json_data)

        def get_many(keys):
            data = {"keys": json.dumps(keys)}
            json_data = conn.request("openlibrary.org", "/get_many", data=data)
            return json.loads(json_data)

        add(
            {
                "key": "/works/OL1W",
                "type": {"key": "/type/work"},
                "authors": [{"type": {"key": "/type/author_role"}}],
            }
        )

        assert get("/works/OL1W") == {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "authors": [],
        }
        assert get_many(["/works/OL1W"]) == {
            "/works/OL1W": {
                "key": "/works/OL1W",
                "type": {"key": "/type/work"},
                "authors": [],
            }
        }

        OL2W = {
            "key": "/works/OL2W",
            "type": {"key": "/type/work"},
            "authors": [
                {
                    "type": {"key": "/type/author_role"},
                    "author": {"key": "/authors/OL2A"},
                }
            ],
        }
        add(OL2W)

        assert get("/works/OL2W") == OL2W
