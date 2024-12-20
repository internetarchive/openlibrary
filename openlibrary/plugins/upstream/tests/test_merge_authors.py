import web

from infogami.infobase import client, common
from openlibrary.plugins.upstream.merge_authors import (
    AuthorMergeEngine,
    AuthorRedirectEngine,
    BasicMergeEngine,
    BasicRedirectEngine,
    get_many,
    make_redirect_doc,
    space_squash_and_strip,
)
from openlibrary.utils import dicthash


def setup_module(mod):
    # delegate.fakeload()

    # models module imports openlibrary.code, which imports ol_infobase and that expects db_parameters.
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    from openlibrary.plugins.upstream import models

    models.setup()


class MockSite(client.Site):
    class Seq:
        def next_value(self, name):
            return 1

    def __init__(self):
        self.seq = self.Seq()
        self.store = {}
        self.docs = {}
        self.query_results = {}

    def get(self, key):
        doc = self.docs[key]

        # black magic
        data = self._process_dict(common.parse_query(doc))
        return client.create_thing(self, key, data)

    def things(self, query):
        return self.query_results.get(dicthash(query), [])

    def add_query(self, query, result):
        self.query_results[dicthash(query)] = result

    def get_dict(self, key):
        return self.get(key).dict()

    def get_many(self, keys):
        return [self.get(k) for k in keys]

    def _get_backreferences(self, thing):
        return {}

    def save_many(self, docs, comment=None, data=None, action=None):
        data = data or {}
        self.add(docs)
        return [{'key': d['key'], 'revision': 1} for d in docs]

    def add(self, docs):
        self.docs.update((doc['key'], doc) for doc in docs)


def test_MockSite():
    site = MockSite()
    assert list(site.docs) == []

    site.add(
        [
            {"key": "a", "type": {"key": "/type/object"}},
            {"key": "b", "type": {"key": "/type/object"}},
        ]
    )
    assert list(site.docs) == ["a", "b"]


TEST_AUTHORS = web.storage(
    {
        "a": {"key": "/authors/a", "type": {"key": "/type/author"}, "name": "a"},
        "b": {"key": "/authors/b", "type": {"key": "/type/author"}, "name": "b"},
        "c": {"key": "/authors/c", "type": {"key": "/type/author"}, "name": "c"},
    }
)


def test_make_redirect_doc():
    assert make_redirect_doc("/a", "/b") == {
        "key": "/a",
        "type": {"key": "/type/redirect"},
        "location": "/b",
    }


class TestBasicRedirectEngine:
    def test_update_references(self):
        engine = BasicRedirectEngine()
        doc = {
            "key": "/a",
            "type": {"key": "/type/object"},
            "x1": [{"key": "/b"}],
            "x2": [{"key": "/b"}, {"key": "/c"}],
            "y1": {"a": "foo", "b": {"key": "/b"}},
            "y2": [{"a": "foo", "b": {"key": "/b"}}, {"a": "foo", "b": {"key": "/c"}}],
        }

        assert engine.update_references(doc, "/c", ["/b"]) == {
            "key": "/a",
            "type": {"key": "/type/object"},
            "x1": [{"key": "/c"}],
            "x2": [{"key": "/c"}],
            "y1": {"a": "foo", "b": {"key": "/c"}},
            "y2": [{"a": "foo", "b": {"key": "/c"}}],
        }


class TestBasicMergeEngine:
    def test_merge_property(self):
        engine = BasicMergeEngine(BasicRedirectEngine())

        assert engine.merge_property(None, "hello") == "hello"
        assert engine.merge_property("hello", None) == "hello"
        assert engine.merge_property("foo", "bar") == "foo"
        assert engine.merge_property(["foo"], ["bar"]) == ["foo", "bar"]
        assert engine.merge_property(None, ["bar"]) == ["bar"]


def test_get_many():
    web.ctx.site = MockSite()
    # get_many should handle bad table_of_contents in the edition.
    edition = {
        "key": "/books/OL1M",
        "type": {"key": "/type/edition"},
        "table_of_contents": [{"type": "/type/text", "value": "foo"}],
    }
    type_edition = {"key": "/type/edition", "type": {"key": "/type/type"}}
    web.ctx.site.add([edition, type_edition])

    assert web.ctx.site.get("/books/OL1M").type.key == "/type/edition"

    assert get_many(["/books/OL1M"])[0] == {
        "key": "/books/OL1M",
        "type": {"key": "/type/edition"},
        "table_of_contents": [{"label": "", "level": 0, "pagenum": "", "title": "foo"}],
    }


class TestAuthorRedirectEngine:
    def setup_method(self, method):
        web.ctx.site = MockSite()

    def test_fix_edition(self):
        update_references = AuthorRedirectEngine().update_references
        edition = {
            "key": "/books/OL2M",
            "authors": [{"key": "/authors/OL2A"}],
            "title": "book 1",
        }

        # edition having duplicate author
        assert update_references(edition, "/authors/OL1A", ["/authors/OL2A"]) == {
            "key": "/books/OL2M",
            "authors": [{"key": "/authors/OL1A"}],
            "title": "book 1",
        }

        # edition not having duplicate author
        assert update_references(edition, "/authors/OL1A", ["/authors/OL3A"]) == {
            "key": "/books/OL2M",
            "authors": [{"key": "/authors/OL2A"}],
            "title": "book 1",
        }

    def test_fix_work(self):
        update_references = AuthorRedirectEngine().update_references
        work = {
            "key": "/works/OL2W",
            "authors": [
                {
                    "type": {"key": "/type/author_role"},
                    "author": {"key": "/authors/OL2A"},
                }
            ],
            "title": "book 1",
        }

        # work having duplicate author
        assert update_references(work, "/authors/OL1A", ["/authors/OL2A"]) == {
            "key": "/works/OL2W",
            "authors": [
                {
                    "type": {"key": "/type/author_role"},
                    "author": {"key": "/authors/OL1A"},
                }
            ],
            "title": "book 1",
        }

        # work not having duplicate author
        assert update_references(work, "/authors/OL1A", ["/authors/OL3A"]) == {
            "key": "/works/OL2W",
            "authors": [
                {
                    "type": {"key": "/type/author_role"},
                    "author": {"key": "/authors/OL2A"},
                }
            ],
            "title": "book 1",
        }


class TestAuthorMergeEngine:
    def setup_method(self, method):
        self.engine = AuthorMergeEngine(AuthorRedirectEngine())
        web.ctx.site = MockSite()

    def test_redirection(self):
        web.ctx.site.add([TEST_AUTHORS.a, TEST_AUTHORS.b, TEST_AUTHORS.c])
        self.engine.merge("/authors/a", ["/authors/b", "/authors/c"])

        # assert redirection
        assert web.ctx.site.get("/authors/b").dict() == {
            "key": "/authors/b",
            "type": {"key": "/type/redirect"},
            "location": "/authors/a",
        }
        assert web.ctx.site.get("/authors/c").dict() == {
            "key": "/authors/c",
            "type": {"key": "/type/redirect"},
            "location": "/authors/a",
        }

    def test_alternate_names(self):
        web.ctx.site.add([TEST_AUTHORS.a, TEST_AUTHORS.b, TEST_AUTHORS.c])
        self.engine.merge("/authors/a", ["/authors/b", "/authors/c"])
        assert web.ctx.site.get("/authors/a").alternate_names == ["b", "c"]

    def test_photos(self):
        a = dict(TEST_AUTHORS.a, photos=[1, 2])
        b = dict(TEST_AUTHORS.b, photos=[3, 4])

        web.ctx.site.add([a, b])
        self.engine.merge("/authors/a", ["/authors/b"])

        photos = web.ctx.site.get("/authors/a").photos
        assert photos == [1, 2, 3, 4]

    def test_links(self):
        link_a = {"title": "link a", "url": "http://example.com/a"}
        link_b = {"title": "link b", "url": "http://example.com/b"}

        a = dict(TEST_AUTHORS.a, links=[link_a])
        b = dict(TEST_AUTHORS.b, links=[link_b])
        web.ctx.site.add([a, b])

        self.engine.merge("/authors/a", ["/authors/b"])
        links = web.ctx.site.get("/authors/a").dict()['links']
        assert links == [link_a, link_b]

    def test_new_field(self):
        """When the duplicate has a new field which is not there in the master,
        the new filed must be copied to the master.
        """
        birth_date = "1910-01-02"
        a = TEST_AUTHORS.a
        b = dict(TEST_AUTHORS.b, birth_date=birth_date)
        web.ctx.site.add([a, b])

        self.engine.merge("/authors/a", ["/authors/b"])
        master_birth_date = web.ctx.site.get("/authors/a").get('birth_date')
        assert master_birth_date == birth_date

    def test_work_authors(self):
        a = TEST_AUTHORS.a
        b = TEST_AUTHORS.b
        work_b = {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "authors": [{"type": "/type/author_role", "author": {"key": "/authors/b"}}],
        }
        web.ctx.site.add([a, b, work_b])

        q = {
            "type": "/type/work",
            "authors": {"author": {"key": "/authors/b"}},
            "limit": 10000,
        }
        web.ctx.site.add_query(q, ["/works/OL1W"])

        self.engine.merge("/authors/a", ["/authors/b"])
        assert web.ctx.site.get_dict("/works/OL1W") == {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "authors": [{"type": "/type/author_role", "author": {"key": "/authors/a"}}],
        }


def test_dicthash():
    assert dicthash({}) == dicthash({})
    assert dicthash({"a": 1}) == dicthash({"a": 1})
    assert dicthash({"a": 1, "b": 2}) == dicthash({"b": 2, "a": 1})
    assert dicthash({}) != dicthash({"a": 1})
    assert dicthash({"b": 1}) != dicthash({"a": 1})


def test_space_squash_and_strip():
    f = space_squash_and_strip
    assert f("Hello") == f("Hello")
    assert f("Hello") != f("hello")
    assert f("") == f("")
    assert f("hello world") == f("hello    world  ")
