# This will be moved to core soon.
import json

from infogami import config
from openlibrary.plugins.openlibrary import connection as connections


class MockConnection:
    def __init__(self):
        self.docs = {}

    def request(self, sitename, path, method="GET", data=None):
        data = data or {}
        if path == "/get":
            key = data["key"]
            if key in self.docs:
                return json.dumps(self.docs[key])
        if path == "/get_many":
            keys = json.loads(data["keys"])
            return json.dumps({k: self.docs[k] for k in keys})
        else:
            return None


class TestMigrationMiddleware:
    def test_title_prefix(self):
        conn = connections.MigrationMiddleware(MockConnection())

        def add(doc):
            conn.conn.docs[doc["key"]] = doc

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
            conn.conn.docs[doc["key"]] = doc

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


class TestOLConnection:
    def _configure(self, monkeypatch):
        monkeypatch.setattr(config, "connection_type", "hybrid", raising=False)
        monkeypatch.setattr(config, "memcache_servers", None, raising=False)
        monkeypatch.setattr(config, "upstream_to_www_migration", False, raising=False)
        monkeypatch.setattr(config, "infobase_server", "infobase:7000", raising=False)
        monkeypatch.setattr(connections.web.config, "db_parameters", {}, raising=False)
        monkeypatch.setattr(connections, "_update_infobase_config", lambda: None)

    def test_in_process_writes_use_local_connection(self, monkeypatch):
        self._configure(monkeypatch)
        monkeypatch.setattr(config, "in_process_writes", True, raising=False)
        calls = []

        def connect(**kwargs):
            calls.append(kwargs)
            return object()

        monkeypatch.setattr(connections.client, "connect", connect)

        conn = connections.OLConnection()

        assert [call["type"] for call in calls] == ["local"]
        assert not isinstance(conn.conn, connections.HybridConnection)

    def test_hybrid_remains_default(self, monkeypatch):
        self._configure(monkeypatch)
        monkeypatch.setattr(config, "in_process_writes", False, raising=False)
        calls = []

        def connect(**kwargs):
            calls.append(kwargs)
            return object()

        monkeypatch.setattr(connections.client, "connect", connect)

        conn = connections.OLConnection()

        assert [call["type"] for call in calls] == ["local", "remote"]
        assert isinstance(conn.conn, connections.HybridConnection)


class TestMemcacheInvalidation:
    def test_document_writes_invalidate_shared_unversioned_cache(self, monkeypatch):
        class FakeMemcache:
            def __init__(self):
                self.values = {}

            def get(self, key):
                return self.values.get(key)

            def get_multi(self, keys):
                return {key: self.values[key] for key in keys if key in self.values}

            def set_multi(self, mapping):
                self.values.update(mapping)

            def delete(self, key):
                self.values.pop(key, None)

            def delete_multi(self, keys):
                for key in keys:
                    self.delete(key)

        class WriteConnection(MockConnection):
            def request(self, sitename, path, method="GET", data=None):
                if path == "/get_many":
                    keys = json.loads(data["keys"])
                    return json.dumps({key: self.docs[key] for key in keys})

                if path.startswith("/save/"):
                    docs = [json.loads(data)]
                elif path in ("/save_many", "/write"):
                    query = data["query"]
                    docs = json.loads(query) if isinstance(query, (str, bytes)) else query
                    docs = docs if isinstance(docs, list) else [docs]
                else:
                    return super().request(sitename, path, method, data)

                for doc in docs:
                    self.docs[doc["key"]] = doc
                return json.dumps(docs)

        cache = FakeMemcache()
        monkeypatch.setattr(
            connections.MemcacheMiddleware,
            "get_memcache",
            lambda _self, _servers: cache,
        )
        middleware = connections.MemcacheMiddleware(WriteConnection(), "unused")

        writes = [
            (
                "/save/works/OL1W",
                "POST",
                json.dumps({"key": "/works/OL1W", "title": "updated by save"}),
                ["/works/OL1W"],
            ),
            (
                "/save_many",
                "POST",
                {"query": json.dumps([{"key": "/works/OL2W", "title": "updated by save_many"}])},
                ["/works/OL2W"],
            ),
            (
                "/write",
                "POST",
                {"query": json.dumps({"key": "/works/OL3W", "title": "updated by write"})},
                ["/works/OL3W"],
            ),
        ]

        for path, method, payload, keys in writes:
            for key in keys:
                middleware.conn.docs[key] = {"key": key, "title": "old"}

            middleware.request(
                "openlibrary.org",
                "/get_many",
                data={"keys": json.dumps(keys)},
            )
            assert all(key in cache.values for key in keys)

            middleware.request("openlibrary.org", path, method=method, data=payload)

            assert all(key not in cache.values for key in keys)
            fresh = json.loads(
                middleware.request(
                    "openlibrary.org",
                    "/get_many",
                    data={"keys": json.dumps(keys)},
                )
            )
            assert [fresh[key]["title"] for key in keys] == [middleware.conn.docs[key]["title"] for key in keys]
