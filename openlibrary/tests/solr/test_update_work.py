from openlibrary.solr import update_work
from openlibrary.solr.data_provider import DataProvider
from openlibrary.solr.update_work import build_data
from StringIO import StringIO

author_counter = 0
edition_counter = 0
work_counter = 0

def make_author(**kw):
    """
    Create a fake author

    :param kw: author data
    :rtype: dict
    """
    global author_counter
    author_counter += 1
    kw.setdefault("key", "/authors/OL%dA" % author_counter)
    kw.setdefault("type", {"key": "/type/author"})
    kw.setdefault("name", "Foo")
    return kw

def make_edition(work=None, **kw):
    """
    Create a fake edition

    :param dict work: Work dict which this is an edition of
    :param kw: edition data
    :rtype: dict
    """
    global edition_counter
    edition_counter += 1
    kw.setdefault("key", "/books/OL%dM" % edition_counter)
    kw.setdefault("type", {"key": "/type/edition"})
    kw.setdefault("title", "Foo")
    if work:
        kw.setdefault("works", [{"key": work["key"]}])
    return kw

def make_work(**kw):
    """
    Create a fake work

    :param kw:
    :rtype: dict
    """
    global work_counter
    work_counter += 1
    kw.setdefault("key", "/works/OL%dW" % work_counter)
    kw.setdefault("type", {"key": "/type/work"})
    kw.setdefault("title", "Foo")
    return kw

class FakeDataProvider(DataProvider):
    """Stub data_provider and methods which are used by build_data."""
    docs = []
    docs_by_key = {}

    def __init__(self, docs=list()):
        """
        :param list[dict] docs: Documents in the DataProvider
        """
        self.docs = docs
        self.docs_by_key = {doc["key"]: doc for doc in docs}

    def find_redirects(self, key):
        return []

    def get_document(self, key):
        return self.docs_by_key.get(key)

    def get_editions_of_work(self, work):
        return [doc for doc in self.docs
                if {"key": work["key"]} in doc.get("works", [])]

    def get_metadata(self, id):
        return {}

class Test_build_data:
    @classmethod
    def setup_class(cls):
        update_work.data_provider = FakeDataProvider()

    def test_simple_work(self):
        work = {
            "key": "/works/OL1M",
            "type": {"key": "/type/work"},
            "title": "Foo"
        }

        d = build_data(work)
        assert d["key"] == "/works/OL1M"
        assert d["title"] == "Foo"
        assert d["has_fulltext"] == False
        assert d["edition_count"] == 0

    def test_edition_count_when_editions_on_work(self):
        work = make_work()

        d = build_data(work)
        assert d['edition_count'] == 0

        work['editions'] = [make_edition()]
        d = build_data(work)
        assert d['edition_count'] == 1

        work['editions'] = [make_edition(), make_edition()]
        d = build_data(work)
        assert d['edition_count'] == 2

    def test_edition_count_when_editions_in_data_provider(self):
        work = make_work()
        d = build_data(work)
        assert d['edition_count'] == 0

        update_work.data_provider = FakeDataProvider([
            work,
            make_edition(work)
        ])

        d = build_data(work)
        assert d['edition_count'] == 1

        update_work.data_provider = FakeDataProvider([
            work,
            make_edition(work),
            make_edition(work)
        ])

        d = build_data(work)
        assert d['edition_count'] == 2

    def test_edition_key(self):
        work = make_work()
        update_work.data_provider = FakeDataProvider([
            work,
            make_edition(work, key="/books/OL1M"),
            make_edition(work, key="/books/OL2M"),
            make_edition(work, key="/books/OL3M")
        ])

        d = build_data(work)
        assert d['edition_key'] == ["OL1M", "OL2M", "OL3M"]

    def test_publish_year(self):
        test_dates = [
            "2000",
            "Another 2000",
            "2001-01-02",  # Doesn't seems to be handling this case
            "01-02-2003",
            "Jan 2002",
            "Bad date 12"
        ]
        work = make_work()
        update_work.data_provider = FakeDataProvider(
            [work] +
            [make_edition(work, publish_date=date) for date in test_dates])

        d = build_data(work)
        assert sorted(d['publish_year']) == ["2000", "2002", "2003"]
        assert d["first_publish_year"] == 2000

    def test_isbns(self):
        work = make_work()
        update_work.data_provider = FakeDataProvider([
            work,
            make_edition(work, isbn_10=["123456789X"])
        ])
        d = build_data(work)
        assert d['isbn'] == ['123456789X', '9781234567897']

        update_work.data_provider = FakeDataProvider([
            work,
            make_edition(work, isbn_10=["9781234567897"])
        ])
        d = build_data(work)
        assert d['isbn'] == ['123456789X', '9781234567897']

    def test_other_identifiers(self):
        work = make_work()
        update_work.data_provider = FakeDataProvider([
            work,
            make_edition(work, oclc_numbers=["123"], lccn=["lccn-1", "lccn-2"]),
            make_edition(work, oclc_numbers=["234"], lccn=["lccn-2", "lccn-3"]),
        ])
        d = build_data(work)
        assert sorted(d['oclc']) == ['123', '234']
        assert sorted(d['lccn']) == ['lccn-1', 'lccn-2', 'lccn-3']

    def test_identifiers(self):
        work = make_work()
        update_work.data_provider = FakeDataProvider([
            work,
            make_edition(work, identifiers={"librarything": ["lt-1"]}),
            make_edition(work, identifiers={"librarything": ["lt-2"]})
        ])
        d = build_data(work)
        assert sorted(d['id_librarything']) == ['lt-1', 'lt-2']

    def test_ia_boxid(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider([w, make_edition(w)])
        d = build_data(w)
        assert 'ia_box_id' not in d

        w = make_work()
        update_work.data_provider = FakeDataProvider([w, make_edition(w, ia_box_id='foo')])
        d = build_data(w)
        assert 'ia_box_id' in d
        assert d['ia_box_id'] == ['foo']

    def test_with_one_lending_edition(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider([
            w,
            make_edition(w, key="/books/OL1M", ocaid='foo00bar',
                         _ia_meta={"collection": ['lendinglibrary', 'americana']})
        ])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == False
        assert 'printdisabled_s' not in d
        assert d['lending_edition_s'] == 'OL1M'
        assert d['ia'] == ['foo00bar']
        assert d['ia_collection_s'] == "lendinglibrary;americana"
        assert d['edition_count'] == 1
        assert d['ebook_count_i'] == 1

    def test_with_two_lending_editions(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider([
            w,
            make_edition(w, key="/books/OL1M", ocaid='foo01bar',
                         _ia_meta={"collection": ['lendinglibrary', 'americana']}),
            make_edition(w, key="/books/OL2M", ocaid='foo02bar',
                         _ia_meta={"collection": ['lendinglibrary', 'internetarchivebooks']})
        ])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == False
        assert 'printdisabled_s' not in d
        assert d['lending_edition_s'] == 'OL1M'
        assert d['ia'] == ['foo01bar', 'foo02bar']
        assert d['ia_collection_s'] == "lendinglibrary;americana;internetarchivebooks"
        assert d['edition_count'] == 2
        assert d['ebook_count_i'] == 2

    def test_with_one_inlibrary_edition(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider([
            w,
            make_edition(w, key="/books/OL1M", ocaid='foo00bar',
                         _ia_meta={"collection": ['printdisabled', 'inlibrary']})
        ])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == False
        assert d['printdisabled_s'] == 'OL1M'
        assert d['lending_edition_s'] == 'OL1M'
        assert d['ia'] == ['foo00bar']
        assert d['ia_collection_s'] == "printdisabled;inlibrary"
        assert d['edition_count'] == 1
        assert d['ebook_count_i'] == 1

    def test_with_one_printdisabled_edition(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider([
            w,
            make_edition(w, key="/books/OL1M", ocaid='foo00bar',
                         _ia_meta={"collection": ['printdisabled', 'americana']})
        ])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == False
        assert d['printdisabled_s'] == 'OL1M'
        assert 'lending_edition_s' not in d
        assert d['ia'] == ['foo00bar']
        assert d['ia_collection_s'] == "printdisabled;americana"
        assert d['edition_count'] == 1
        assert d['ebook_count_i'] == 1

    def test_with_multiple_editions(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider([
            w,
            make_edition(w, key="/books/OL1M"),
            make_edition(w, key="/books/OL2M", ocaid='foo00bar', _ia_meta={"collection": ['americana']}),
            make_edition(w, key="/books/OL3M", ocaid='foo01bar', _ia_meta={"collection": ['lendinglibrary', 'americana']}),
            make_edition(w, key="/books/OL4M", ocaid='foo02bar', _ia_meta={"collection": ['printdisabled', 'inlibrary']})
        ])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == True
        assert d['printdisabled_s'] == 'OL4M'
        assert d['lending_edition_s'] == 'OL3M'
        assert d['ia'] == ['foo00bar', 'foo01bar', 'foo02bar']
        assert sorted(d['ia_collection_s'].split(";")) == ["americana", "inlibrary", "lendinglibrary", "printdisabled"]

        assert d['edition_count'] == 4
        assert d['ebook_count_i'] == 3

    def test_subjects(self):
        w = make_work(subjects=["a", "b c"])
        d = build_data(w)

        assert d['subject'] == ['a', "b c"]
        assert d['subject_facet'] == ['a', "b c"]
        assert d['subject_key'] == ['a', "b_c"]

        assert "people" not in d
        assert "place" not in d
        assert "time" not in d

        w = make_work(
                subjects=["a", "b c"],
                subject_places=["a", "b c"],
                subject_people=["a", "b c"],
                subject_times=["a", "b c"])
        d = build_data(w)

        for k in ['subject', 'person', 'place', 'time']:
            assert d[k] == ['a', "b c"]
            assert d[k + '_facet'] == ['a', "b c"]
            assert d[k + '_key'] == ['a', "b_c"]

    def test_language(self):
        pass

    def test_author_info(self):
        w = make_work(authors=[
                {"author": make_author(key="/authors/OL1A", name="Author One", alternate_names=["Author 1"])},
                {"author": make_author(key="/authors/OL2A", name="Author Two")}
            ])
        d = build_data(w)
        assert d['author_name'] == ["Author One", "Author Two"]
        assert d['author_key'] == ['OL1A', 'OL2A']
        assert d['author_facet'] == ['OL1A Author One', 'OL2A Author Two']
        assert d['author_alternative_name'] == ["Author 1"]

class Test_update_items():
    @classmethod
    def setup_class(cls):
        update_work.data_provider = FakeDataProvider()

    def test_delete_author(self):
        update_work.data_provider = FakeDataProvider([
            make_author(key='/authors/OL23A', type={'key': '/type/delete'})
        ])
        requests = update_work.update_author('/authors/OL23A')
        assert isinstance(requests, list)
        assert isinstance(requests[0], update_work.DeleteRequest)
        assert requests[0].toxml() == '<delete><query>key:/authors/OL23A</query></delete>'

    def test_redirect_author(self):
        update_work.data_provider = FakeDataProvider([
            make_author(key='/authors/OL24A', type={'key': '/type/redirect'})
        ])
        requests = update_work.update_author('/authors/OL24A')
        assert isinstance(requests, list)
        assert isinstance(requests[0], update_work.DeleteRequest)
        assert requests[0].toxml() == '<delete><query>key:/authors/OL24A</query></delete>'

    def test_update_author(self, monkeypatch):
        update_work.data_provider = FakeDataProvider([
            make_author(key='/authors/OL25A', name='Somebody')
        ])
        # Minimal Solr response, author not found in Solr
        solr_response = """{
            "facet_counts": {
                "facet_fields": {
                    "place_facet": [], "person_facet": [], "subject_facet": [], "time_facet": []
                }
            },
            "response": {"numFound": 0}
        }"""
        monkeypatch.setattr(update_work, 'urlopen', lambda url: StringIO(solr_response))
        requests = update_work.update_author('/authors/OL25A')
        assert len(requests) == 1
        assert isinstance(requests, list)
        assert isinstance(requests[0], update_work.UpdateRequest)
        assert requests[0].toxml().startswith('<add>')
        assert '<field name="key">/authors/OL25A</field>' in requests[0].toxml()

    def test_delete_edition(self):
        editions = update_work.update_edition({'key': '/books/OL23M', 'type': {'key': '/type/delete'}})
        assert editions == [], "Editions are not indexed by Solr, expecting empty set regardless of input. Got: %s" % editions

    def test_update_edition(self):
        editions = update_work.update_edition({'key': '/books/OL23M', 'type': {'key': '/type/edition'}})
        assert editions == [], "Editions are not indexed by Solr, expecting empty set regardless of input. Got: %s" % editions

    def test_delete_requests(self):
        olids = ['/works/OL1W', '/works/OL2W', '/works/OL3W']
        del_req = update_work.DeleteRequest(olids)
        assert isinstance(del_req, update_work.DeleteRequest)
        assert del_req.toxml().startswith("<delete>")
        for olid in olids:
            assert "<query>key:%s</query>" % olid in del_req.toxml()

    def test_delete_work(self):
        del_work = update_work.update_work({'key': '/works/OL23W', 'type': {'key': '/type/delete'}})
        del_edition = update_work.update_work({'key': '/works/OL23M', 'type': {'key': '/type/delete'}})
        assert len(del_work) == 1
        assert len(del_edition) == 1
        assert isinstance(del_work, list)
        assert isinstance(del_work[0], update_work.DeleteRequest)
        assert del_work[0].toxml() == '<delete><query>key:/works/OL23W</query></delete>'
        assert isinstance(del_edition[0], update_work.DeleteRequest)
        assert del_edition[0].toxml() == '<delete><query>key:/works/OL23M</query></delete>'
