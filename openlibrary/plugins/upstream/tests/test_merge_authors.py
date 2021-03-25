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

    # models module imports openlibrary.code, which imports ol_infobase and
    # that expects db_parameters.
    web.config.db_parameters = dict(dbn="sqlite", db=":memory:")
    from openlibrary.plugins.upstream import models
    models.setup()


class MockSite(client.Site):

    class Seq(object):
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

    site.add([{
            "key": "å",
            "type": {"key": "/type/object"}
        }, {
            "key": "ß",
            "type": {"key": "/type/object"}
        }
    ])
    assert list(site.docs) == ["å", "ß"]


TEST_AUTHORS = web.storage({
    "OL100A": {
        "key": "/authors/OL100A",
        "type": {"key": "/type/author"},
        "name": "Üñîçø∂é OL100A'"
    },
    "OL200A": {
        "key": "/authors/OL200A",
        "type": {"key": "/type/author"},
        "name": "Üñîçø∂é OL200A'"
    },
    "OL300A": {
        "key": "/authors/OL300A'",
        "type": {"key": "/type/author"},
        "name": "Üñîçø∂é OL300A'"
    }
})


def test_make_redirect_doc():
    assert make_redirect_doc("/å", "/ß") == {
        "key": "/å",
        "type": {"key": "/type/redirect"},
        "location": "/ß"
    }


class TestBasicRedirectEngine:
    def test_update_references(self):
        engine = BasicRedirectEngine()
        doc = {
            "key": "/å",
            "type": {"key": "/type/object"},
            "x1": [{"key": "/ß"}],
            "x2": [{"key": "/ß"}, {"key": "/ç"}],
            "y1": {
                "å": "føø",
                "ß": {"key": "/ß"}
            },
            "y2": [{
                "å": "føø",
                "ß": {"key": "/ß"}
            }, {
                "å": "føø",
                "ß": {"key": "/ç"}
            }]
        }

        assert engine.update_references(doc, "/ç", ["/ß"]) == {
            "key": "/å",
            "type": {"key": "/type/object"},
            "x1": [{"key": "/ç"}],
            "x2": [{"key": "/ç"}],
            "y1": {
                "å": "føø",
                "ß": {"key": "/ç"}
            },
            "y2": [{
                "å": "føø",
                "ß": {"key": "/ç"}
            }]
        }


class TestBasicMergeEngine:
    def test_merge_property(self):
        engine = BasicMergeEngine(BasicRedirectEngine())

        assert engine.merge_property(None, "héllo") == "héllo"
        assert engine.merge_property("héllo", None) == "héllo"
        assert engine.merge_property("føo", "bår") == "føo"
        assert engine.merge_property(["føo"], ["bår"]) == ["føo", "bår"]
        assert engine.merge_property(None, ["bår"]) == ["bår"]


def test_get_many():
    web.ctx.site = MockSite()
    # get_many should handle bad table_of_contents in the edition.
    edition = {
        "key": "/books/OL1M",
        "type": {"key": "/type/edition"},
        "table_of_contents": [{
            "type": "/type/text",
            "value": "føø"
        }]
    }
    type_edition = {
        "key": "/type/edition",
        "type": {"key": "/type/type"}
    }
    web.ctx.site.add([edition, type_edition])

    assert web.ctx.site.get("/books/OL1M").type.key == "/type/edition"

    assert get_many(["/books/OL1M"])[0] == {
        "key": "/books/OL1M",
        "type": {"key": "/type/edition"},
        "table_of_contents": [{
            "label": "",
            "level": 0,
            "pagenum": "",
            "title": "føø"
        }]
    }


class TestAuthorRedirectEngine:
    def setup_method(self, method):
        web.ctx.site = MockSite()

    def test_fix_edition(self):
        update_references = AuthorRedirectEngine().update_references
        edition = {
            "key": "/books/OL2M",
            "authors": [{"key": "/authors/OL2A"}],
            "title": "böök 1"
        }

        # edition having duplicate author
        assert update_references(edition, "/authors/OL1A", ["/authors/OL2A"]) == {
            "key": "/books/OL2M",
            "authors": [{"key": "/authors/OL1A"}],
            "title": "böök 1"
        }

        # edition not having duplicate author
        assert update_references(edition, "/authors/OL1A", ["/authors/OL3A"]) == {
            "key": "/books/OL2M",
            "authors": [{"key": "/authors/OL2A"}],
            "title": "böök 1"
        }

    def test_fix_work(self):
        update_references = AuthorRedirectEngine().update_references
        work = {
            "key": "/works/OL2W",
            "authors": [{
                "type": {"key": "/type/author_role"},
                "author": {"key": "/authors/OL2A"}
            }],
            "title": "böök 1"
        }

        # work having duplicate author
        assert update_references(work, "/authors/OL1A", ["/authors/OL2A"]) == {
            "key": "/works/OL2W",
            "authors": [{
                "type": {"key": "/type/author_role"},
                "author": {"key": "/authors/OL1A"}
            }],
            "title": "böök 1"
        }

        # work not having duplicate author
        assert update_references(work, "/authors/OL1A", ["/authors/OL3A"]) == {
            "key": "/works/OL2W",
            "authors": [{
                "type": {"key": "/type/author_role"},
                "author": {"key": "/authors/OL2A"}
            }],
            "title": "böök 1"
        }


class TestAuthorMergeEngine:
    def setup_method(self, method):
        self.engine = AuthorMergeEngine(AuthorRedirectEngine())
        web.ctx.site = MockSite()

    def test_redirection(self):
        web.ctx.site.add([
            TEST_AUTHORS.OL100A, TEST_AUTHORS.OL200A, TEST_AUTHORS.OL300A
        ])
        self.engine.merge("/authors/OL100A", ["/authors/OL200A", "/authors/OL300A"])

        # assert redirection
        assert web.ctx.site.get("/authors/OL200A").dict() == {
            "key": "/authors/OL200A",
            "type": {"key": "/type/redirect"},
            "location": "/authors/OL100A"
        }
        assert web.ctx.site.get("/authors/OL300A").dict() == {
            "key": "/authors/OL300A",
            "type": {"key": "/type/redirect"},
            "location": "/authors/OL100A"
        }

    def test_alternate_names(self):
        web.ctx.site.add([
            TEST_AUTHORS.OL100A, TEST_AUTHORS.OL200A, TEST_AUTHORS.OL300A
        ])
        self.engine.merge("/authors/OL100A", ["/authors/OL200A", "/authors/OL300A"])
        assert web.ctx.site.get("/authors/OL100A").alternate_names == [
            "Üñîçø∂é OL200A", "Üñîçø∂é OL300A"
        ]

    def test_photos(self):
        OL100A = dict(TEST_AUTHORS.OL100A, photos=[1, 2])
        OL200A = dict(TEST_AUTHORS.OL200A, photos=[3, 4])

        web.ctx.site.add([OL100A, OL200A])
        self.engine.merge("/authors/OL100A", ["/authors/OL200A"])

        photos = web.ctx.site.get("/authors/OL100A").photos
        assert photos == [1, 2, 3, 4]

    def test_links(self):
        link_OL100A = {
            "title": "link OL100A",
            "url": "http://example.com/OL100A"
        }
        link_OL200A = {
            "title": "link OL200A",
            "url": "http://example.com/OL200A"
        }

        OL100A = dict(TEST_AUTHORS.OL100A, links=[link_OL100A])
        OL200A = dict(TEST_AUTHORS.OL200A, links=[link_OL200A])
        web.ctx.site.add([OL100A, OL200A])

        self.engine.merge("/authors/OL100A", ["/authors/OL200A"])
        links = web.ctx.site.get("/authors/OL100A").dict()['links']
        assert links == [link_OL100A, link_OL200A]

    def test_new_field(self):
        """When the duplicate has a new field which is not there in the master,
        the new filed must be copied to the master.
        """
        birth_date = "1910-01-02"
        OL100A = TEST_AUTHORS.OL100A
        OL200A = dict(TEST_AUTHORS.OL200A, birth_date=birth_date)
        web.ctx.site.add([OL100A, OL200A])

        self.engine.merge("/authors/OL100A", ["/authors/OL200A"])
        master_birth_date = web.ctx.site.get("/authors/OL100A").get('birth_date')
        assert master_birth_date == birth_date

    def test_work_authors(self):
        OL100A = TEST_AUTHORS.OL100A
        OL200A = TEST_AUTHORS.OL200A
        work_OL200A = {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "authors": [{
                "type": "/type/author_role",
                "author": {"key": "/authors/OL200A"}
            }]
        }
        web.ctx.site.add([OL100A, OL200A, work_OL200A])

        q = {
            "type": "/type/work",
            "authors": {
                "author": {"key": "/authors/OL200A"}
            },
            "limit": 10000
        }
        web.ctx.site.add_query(q, ["/works/OL1W"])

        self.engine.merge("/authors/OL100A", ["/authors/OL200A"])
        assert web.ctx.site.get_dict("/works/OL1W") == {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "authors": [{
                "type": "/type/author_role",
                "author": {"key": "/authors/OL100A"}
            }]
        }


def test_dicthash():
    assert dicthash({"å": 1}) == dicthash({"å": 1})
    assert dicthash({"å": 1, "ß": 2}) == dicthash({"ß": 2, "å": 1})
    assert dicthash({}) != dicthash({"å": 1})
    assert dicthash({"ß": 1}) != dicthash({"å": 1})


def test_space_squash_and_strip():
    f = space_squash_and_strip
    assert f("Héllo") == f("Héllo")
    assert f("Héllo") != f("héllo")
    assert f("") == f("")
    assert f("héllo wörld") == f("  héllo    wörld  ")
