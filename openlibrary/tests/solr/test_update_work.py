import json
import httpx
from httpx import ConnectError, Response
import pytest
from unittest.mock import MagicMock

from openlibrary.solr import update_work
from openlibrary.solr.data_provider import DataProvider
from openlibrary.solr.update_work import (
    CommitRequest,
    SolrProcessor,
    build_data,
    pick_cover_edition,
    pick_number_of_pages_median,
    solr_update,
)

author_counter = 0
edition_counter = 0
work_counter = 0


def sorted_split_semicolon(s):
    """
    >>> sorted_split_semicolon("z;c;x;a;y;b")
    ['a', 'b', 'c', 'x', 'y', 'z']
    """
    return sorted(s.split(';'))


sss = sorted_split_semicolon


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

    docs: list = []
    docs_by_key: dict = {}

    def __init__(self, docs=None):
        docs = docs or []
        """
        :param list[dict] docs: Documents in the DataProvider
        """
        self.docs = docs
        self.docs_by_key = {doc["key"]: doc for doc in docs}

    def find_redirects(self, key):
        return []

    async def get_document(self, key):
        return self.docs_by_key.get(key)

    def get_editions_of_work(self, work):
        return [
            doc for doc in self.docs if {"key": work["key"]} in doc.get("works", [])
        ]

    def get_metadata(self, id):
        return {}


class Test_build_data:
    @classmethod
    def setup_class(cls):
        update_work.data_provider = FakeDataProvider()

    @pytest.mark.asyncio
    async def test_simple_work(self):
        work = {"key": "/works/OL1M", "type": {"key": "/type/work"}, "title": "Foo"}

        d = await build_data(work)
        assert d["key"] == "/works/OL1M"
        assert d["title"] == "Foo"
        assert d["has_fulltext"] is False
        assert d["edition_count"] == 0

    @pytest.mark.asyncio
    async def test_edition_count_when_editions_on_work(self):
        work = make_work()

        d = await build_data(work)
        assert d['edition_count'] == 0

        work['editions'] = [make_edition()]
        d = await build_data(work)
        assert d['edition_count'] == 1

        work['editions'] = [make_edition(), make_edition()]
        d = await build_data(work)
        assert d['edition_count'] == 2

    @pytest.mark.asyncio
    async def test_edition_count_when_editions_in_data_provider(self):
        work = make_work()
        d = await build_data(work)
        assert d['edition_count'] == 0

        update_work.data_provider = FakeDataProvider([work, make_edition(work)])

        d = await build_data(work)
        assert d['edition_count'] == 1

        update_work.data_provider = FakeDataProvider(
            [work, make_edition(work), make_edition(work)]
        )

        d = await build_data(work)
        assert d['edition_count'] == 2

    @pytest.mark.asyncio
    async def test_edition_key(self):
        work = make_work()
        update_work.data_provider = FakeDataProvider(
            [
                work,
                make_edition(work, key="/books/OL1M"),
                make_edition(work, key="/books/OL2M"),
                make_edition(work, key="/books/OL3M"),
            ]
        )

        d = await build_data(work)
        assert d['edition_key'] == ["OL1M", "OL2M", "OL3M"]

    @pytest.mark.asyncio
    async def test_publish_year(self):
        test_dates = [
            "2000",
            "Another 2000",
            "2001-01-02",  # ISO 8601 formatted dates now supported
            "01-02-2003",
            "2004 May 23",
            "Jan 2002",
            "Bad date 12",
            "Bad date 123412314",
        ]
        work = make_work()
        update_work.data_provider = FakeDataProvider(
            [work] + [make_edition(work, publish_date=date) for date in test_dates]
        )

        d = await build_data(work)
        assert sorted(d['publish_year']) == ["2000", "2001", "2002", "2003", "2004"]
        assert d["first_publish_year"] == 2000

    @pytest.mark.asyncio
    async def test_isbns(self):
        work = make_work()
        update_work.data_provider = FakeDataProvider(
            [work, make_edition(work, isbn_10=["123456789X"])]
        )
        d = await build_data(work)
        assert sorted(d['isbn']) == ['123456789X', '9781234567897']

        update_work.data_provider = FakeDataProvider(
            [work, make_edition(work, isbn_10=["9781234567897"])]
        )
        d = await build_data(work)
        assert sorted(d['isbn']) == ['123456789X', '9781234567897']

    @pytest.mark.asyncio
    async def test_other_identifiers(self):
        work = make_work()
        update_work.data_provider = FakeDataProvider(
            [
                work,
                make_edition(work, oclc_numbers=["123"], lccn=["lccn-1", "lccn-2"]),
                make_edition(work, oclc_numbers=["234"], lccn=["lccn-2", "lccn-3"]),
            ]
        )
        d = await build_data(work)
        assert sorted(d['oclc']) == ['123', '234']
        assert sorted(d['lccn']) == ['lccn-1', 'lccn-2', 'lccn-3']

    @pytest.mark.asyncio
    async def test_identifiers(self):
        work = make_work()
        update_work.data_provider = FakeDataProvider(
            [
                work,
                make_edition(work, identifiers={"librarything": ["lt-1"]}),
                make_edition(work, identifiers={"librarything": ["lt-2"]}),
            ]
        )
        d = await build_data(work)
        assert sorted(d['id_librarything']) == ['lt-1', 'lt-2']

    @pytest.mark.asyncio
    async def test_ia_boxid(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider([w, make_edition(w)])
        d = await build_data(w)
        assert 'ia_box_id' not in d

        w = make_work()
        update_work.data_provider = FakeDataProvider(
            [w, make_edition(w, ia_box_id='foo')]
        )
        d = await build_data(w)
        assert 'ia_box_id' in d
        assert d['ia_box_id'] == ['foo']

    @pytest.mark.asyncio
    async def test_with_one_lending_edition(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider(
            [w, make_edition(w, key="/books/OL1M", ocaid='foo00bar')]
        )
        ia_metadata = {"foo00bar": {"collection": ['inlibrary', 'americana']}}
        d = await build_data(w, ia_metadata)
        assert d['has_fulltext'] is True
        assert d['public_scan_b'] is False
        assert 'printdisabled_s' not in d
        assert d['lending_edition_s'] == 'OL1M'
        assert d['ia'] == ['foo00bar']
        assert sss(d['ia_collection_s']) == sss("americana;inlibrary")
        assert d['edition_count'] == 1
        assert d['ebook_count_i'] == 1

    @pytest.mark.asyncio
    async def test_with_two_lending_editions(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider(
            [
                w,
                make_edition(w, key="/books/OL1M", ocaid='foo01bar'),
                make_edition(w, key="/books/OL2M", ocaid='foo02bar'),
            ]
        )
        ia_metadata = {
            "foo01bar": {"collection": ['inlibrary', 'americana']},
            "foo02bar": {"collection": ['inlibrary', 'internetarchivebooks']},
        }
        d = await build_data(w, ia_metadata)
        assert d['has_fulltext'] is True
        assert d['public_scan_b'] is False
        assert 'printdisabled_s' not in d
        assert d['lending_edition_s'] == 'OL1M'
        assert sorted(d['ia']) == ['foo01bar', 'foo02bar']
        assert sss(d['ia_collection_s']) == sss(
            "inlibrary;americana;internetarchivebooks"
        )
        assert d['edition_count'] == 2
        assert d['ebook_count_i'] == 2

    @pytest.mark.asyncio
    async def test_with_one_inlibrary_edition(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider(
            [w, make_edition(w, key="/books/OL1M", ocaid='foo00bar')]
        )
        ia_metadata = {"foo00bar": {"collection": ['printdisabled', 'inlibrary']}}
        d = await build_data(w, ia_metadata)
        assert d['has_fulltext'] is True
        assert d['public_scan_b'] is False
        assert d['printdisabled_s'] == 'OL1M'
        assert d['lending_edition_s'] == 'OL1M'
        assert d['ia'] == ['foo00bar']
        assert sss(d['ia_collection_s']) == sss("printdisabled;inlibrary")
        assert d['edition_count'] == 1
        assert d['ebook_count_i'] == 1

    @pytest.mark.asyncio
    async def test_with_one_printdisabled_edition(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider(
            [w, make_edition(w, key="/books/OL1M", ocaid='foo00bar')]
        )
        ia_metadata = {"foo00bar": {"collection": ['printdisabled', 'americana']}}
        d = await build_data(w, ia_metadata)
        assert d['has_fulltext'] is True
        assert d['public_scan_b'] is False
        assert d['printdisabled_s'] == 'OL1M'
        assert 'lending_edition_s' not in d
        assert d['ia'] == ['foo00bar']
        assert sss(d['ia_collection_s']) == sss("printdisabled;americana")
        assert d['edition_count'] == 1
        assert d['ebook_count_i'] == 1

    def test_get_alternate_titles(self):
        f = SolrProcessor.get_alternate_titles

        no_title = {}
        only_title = {'title': 'foo'}
        with_subtitle = {'title': 'foo 2', 'subtitle': 'bar'}

        assert f([]) == set()
        assert f([no_title]) == set()
        assert f([only_title, no_title]) == {'foo'}
        assert f([with_subtitle, only_title]) == {'foo 2: bar', 'foo'}

    @pytest.mark.asyncio
    async def test_with_multiple_editions(self):
        w = make_work()
        update_work.data_provider = FakeDataProvider(
            [
                w,
                make_edition(w, key="/books/OL1M"),
                make_edition(w, key="/books/OL2M", ocaid='foo00bar'),
                make_edition(w, key="/books/OL3M", ocaid='foo01bar'),
                make_edition(w, key="/books/OL4M", ocaid='foo02bar'),
            ]
        )
        ia_metadata = {
            "foo00bar": {"collection": ['americana']},
            "foo01bar": {"collection": ['inlibrary', 'americana']},
            "foo02bar": {"collection": ['printdisabled', 'inlibrary']},
        }
        d = await build_data(w, ia_metadata)
        assert d['has_fulltext'] is True
        assert d['public_scan_b'] is True
        assert d['printdisabled_s'] == 'OL4M'
        assert d['lending_edition_s'] == 'OL2M'
        assert sorted(d['ia']) == ['foo00bar', 'foo01bar', 'foo02bar']
        assert sss(d['ia_collection_s']) == sss("americana;inlibrary;printdisabled")

        assert d['edition_count'] == 4
        assert d['ebook_count_i'] == 3

    @pytest.mark.asyncio
    async def test_subjects(self):
        w = make_work(subjects=["a", "b c"])
        d = await build_data(w)

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
            subject_times=["a", "b c"],
        )
        d = await build_data(w)

        for k in ['subject', 'person', 'place', 'time']:
            assert d[k] == ['a', "b c"]
            assert d[k + '_facet'] == ['a', "b c"]
            assert d[k + '_key'] == ['a', "b_c"]

    @pytest.mark.asyncio
    async def test_author_info(self):
        w = make_work(
            authors=[
                {
                    "author": make_author(
                        key="/authors/OL1A",
                        name="Author One",
                        alternate_names=["Author 1"],
                    )
                },
                {"author": make_author(key="/authors/OL2A", name="Author Two")},
            ]
        )
        d = await build_data(w)
        assert d['author_name'] == ["Author One", "Author Two"]
        assert d['author_key'] == ['OL1A', 'OL2A']
        assert d['author_facet'] == ['OL1A Author One', 'OL2A Author Two']
        assert d['author_alternative_name'] == ["Author 1"]

    # {'Test name': (doc_lccs, solr_lccs, sort_lcc_index)}
    LCC_TESTS = {
        'Remove dupes': (['A', 'A'], ['A--0000.00000000'], 0),
        'Ignores garbage': (['$9.99'], None, None),
        'Handles none': ([], None, None),
        'Handles empty string': ([''], None, None),
        'Stores multiple': (
            ['A123', 'B42'],
            ['A--0123.00000000', 'B--0042.00000000'],
            None,
        ),
        'Handles full LCC': (
            ['PT2603.0.E46 Z589 1991'],
            ['PT-2603.00000000.E46 Z589 1991'],
            0,
        ),
        'Stores longest for sorting': (
            ['A123.C14', 'B42'],
            ['A--0123.00000000.C14', 'B--0042.00000000'],
            0,
        ),
        'Ignores ISBNs/DDCs': (
            ['9781234123411', 'ML410', '123.4'],
            ['ML-0410.00000000'],
            0,
        ),
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "doc_lccs,solr_lccs,sort_lcc_index", LCC_TESTS.values(), ids=LCC_TESTS.keys()
    )
    async def test_lccs(self, doc_lccs, solr_lccs, sort_lcc_index):
        work = make_work()
        update_work.data_provider = FakeDataProvider(
            [
                work,
                make_edition(work, lc_classifications=doc_lccs),
            ]
        )
        d = await build_data(work)
        if solr_lccs:
            assert sorted(d.get('lcc')) == solr_lccs
            if sort_lcc_index is not None:
                assert d.get('lcc_sort') == solr_lccs[sort_lcc_index]
        else:
            assert 'lcc' not in d
            assert 'lcc_sort' not in d

    DDC_TESTS = {
        'Remove dupes': (['123.5', '123.5'], ['123.5'], 0),
        'Handles none': ([], None, None),
        'Handles empty string': ([''], None, None),
        'Stores multiple': (['05', '123.5'], ['005', '123.5'], 1),
        'Handles full DDC': (['j132.452939 [B]'], ['132.452939 B', 'j132.452939 B'], 0),
        'Handles alternate DDCs': (['132.52 153.6'], ['132.52', '153.6'], 0),
        'Stores longest for sorting': (
            ['123.4', '123.41422'],
            ['123.4', '123.41422'],
            1,
        ),
        'Ignores ISBNs/LCCs': (['9781234123411', 'ML410', '132.3'], ['132.3'], 0),
        'Ignores superfluous 920s': (['123.5', '920'], ['123.5'], 0),
        'Ignores superfluous 92s': (['123.5', '92'], ['123.5'], 0),
        'Ignores superfluous 92s (2)': (['123.5', 'B', '92'], ['123.5'], 0),
        'Skips 920s': (['920', '123.5'], ['123.5'], 0),
        'Skips 92s': (['92', '123.5'], ['123.5'], 0),
        'Skips 092s': (['092', '123.5'], ['123.5'], 0),
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "doc_ddcs,solr_ddcs,sort_ddc_index", DDC_TESTS.values(), ids=DDC_TESTS.keys()
    )
    async def test_ddcs(self, doc_ddcs, solr_ddcs, sort_ddc_index):
        work = make_work()
        update_work.data_provider = FakeDataProvider(
            [
                work,
                make_edition(work, dewey_decimal_class=doc_ddcs),
            ]
        )
        d = await build_data(work)
        if solr_ddcs:
            assert sorted(d.get('ddc')) == solr_ddcs
            assert d.get('ddc_sort') == solr_ddcs[sort_ddc_index]
        else:
            assert 'ddc' not in d
            assert 'ddc_sort' not in d


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data


class Test_update_items:
    @classmethod
    def setup_class(cls):
        update_work.data_provider = FakeDataProvider()

    @pytest.mark.asyncio
    async def test_delete_author(self):
        update_work.data_provider = FakeDataProvider(
            [make_author(key='/authors/OL23A', type={'key': '/type/delete'})]
        )
        requests = await update_work.update_author('/authors/OL23A')
        assert requests[0].to_json_command() == '"delete": ["/authors/OL23A"]'

    @pytest.mark.asyncio
    async def test_redirect_author(self):
        update_work.data_provider = FakeDataProvider(
            [make_author(key='/authors/OL24A', type={'key': '/type/redirect'})]
        )
        requests = await update_work.update_author('/authors/OL24A')
        assert requests[0].to_json_command() == '"delete": ["/authors/OL24A"]'

    @pytest.mark.asyncio
    async def test_update_author(self, monkeypatch):
        update_work.data_provider = FakeDataProvider(
            [make_author(key='/authors/OL25A', name='Somebody')]
        )
        empty_solr_resp = MockResponse(
            {
                "facet_counts": {
                    "facet_fields": {
                        "place_facet": [],
                        "person_facet": [],
                        "subject_facet": [],
                        "time_facet": [],
                    }
                },
                "response": {"numFound": 0},
            }
        )

        monkeypatch.setattr(
            update_work.requests, 'get', lambda url, **kwargs: empty_solr_resp
        )
        requests = await update_work.update_author('/authors/OL25A')
        assert len(requests) == 1
        assert isinstance(requests[0], update_work.AddRequest)
        assert requests[0].doc['key'] == "/authors/OL25A"

    def test_delete_requests(self):
        olids = ['/works/OL1W', '/works/OL2W', '/works/OL3W']
        json_command = update_work.DeleteRequest(olids).to_json_command()
        assert '"delete": ["/works/OL1W", "/works/OL2W", "/works/OL3W"]' == json_command


class TestUpdateWork:
    @classmethod
    def setup_class(cls):
        update_work.data_provider = FakeDataProvider()

    @pytest.mark.asyncio
    async def test_delete_work(self):
        requests = await update_work.update_work(
            {'key': '/works/OL23W', 'type': {'key': '/type/delete'}}
        )
        assert len(requests) == 1
        assert requests[0].to_json_command() == '"delete": ["/works/OL23W"]'

    @pytest.mark.asyncio
    async def test_delete_editions(self):
        requests = await update_work.update_work(
            {'key': '/works/OL23M', 'type': {'key': '/type/delete'}}
        )
        assert len(requests) == 1
        assert requests[0].to_json_command() == '"delete": ["/works/OL23M"]'

    @pytest.mark.asyncio
    async def test_redirects(self):
        requests = await update_work.update_work(
            {'key': '/works/OL23W', 'type': {'key': '/type/redirect'}}
        )
        assert len(requests) == 1
        assert requests[0].to_json_command() == '"delete": ["/works/OL23W"]'

    @pytest.mark.asyncio
    async def test_no_title(self):
        requests = await update_work.update_work(
            {'key': '/books/OL1M', 'type': {'key': '/type/edition'}}
        )
        assert len(requests) == 1
        assert requests[0].doc['title'] == "__None__"
        requests = await update_work.update_work(
            {'key': '/works/OL23W', 'type': {'key': '/type/work'}}
        )
        assert len(requests) == 1
        assert requests[0].doc['title'] == "__None__"

    @pytest.mark.asyncio
    async def test_work_no_title(self):
        work = {'key': '/works/OL23W', 'type': {'key': '/type/work'}}
        ed = make_edition(work)
        ed['title'] = 'Some Title!'
        update_work.data_provider = FakeDataProvider([work, ed])
        requests = await update_work.update_work(work)
        assert len(requests) == 1
        assert requests[0].doc['title'] == "Some Title!"


class Test_pick_cover_edition:
    def test_no_editions(self):
        assert pick_cover_edition([], 123) is None
        assert pick_cover_edition([], None) is None

    def test_no_work_cover(self):
        ed_w_cover = {'covers': [123]}
        ed_wo_cover = {}
        ed_w_neg_cover = {'covers': [-1]}
        ed_w_posneg_cover = {'covers': [-1, 123]}
        assert pick_cover_edition([ed_w_cover], None) == ed_w_cover
        assert pick_cover_edition([ed_wo_cover], None) is None
        assert pick_cover_edition([ed_w_neg_cover], None) is None
        assert pick_cover_edition([ed_w_posneg_cover], None) == ed_w_posneg_cover
        assert pick_cover_edition([ed_wo_cover, ed_w_cover], None) == ed_w_cover
        assert pick_cover_edition([ed_w_neg_cover, ed_w_cover], None) == ed_w_cover

    def test_prefers_work_cover(self):
        ed_w_cover = {'covers': [123]}
        ed_w_work_cover = {'covers': [456]}
        assert pick_cover_edition([ed_w_cover, ed_w_work_cover], 456) == ed_w_work_cover

    def test_prefers_eng_covers(self):
        ed_no_lang = {'covers': [123]}
        ed_eng = {'covers': [456], 'languages': [{'key': '/languages/eng'}]}
        ed_fra = {'covers': [789], 'languages': [{'key': '/languages/fra'}]}
        assert pick_cover_edition([ed_no_lang, ed_fra, ed_eng], 456) == ed_eng

    def test_prefers_anything(self):
        ed = {'covers': [123]}
        assert pick_cover_edition([ed], 456) == ed


class Test_pick_number_of_pages_median:
    def test_no_editions(self):
        assert pick_number_of_pages_median([]) is None

    def test_invalid_type(self):
        ed = {'number_of_pages': 'spam'}
        assert pick_number_of_pages_median([ed]) is None
        eds = [{'number_of_pages': n} for n in [123, 122, 'spam']]
        assert pick_number_of_pages_median(eds) == 123

    def test_normal_case(self):
        eds = [{'number_of_pages': n} for n in [123, 122, 1]]
        assert pick_number_of_pages_median(eds) == 122
        eds = [{}, {}] + [{'number_of_pages': n} for n in [123, 122, 1]]
        assert pick_number_of_pages_median(eds) == 122


class Test_Sort_Editions_Ocaids:
    def test_sort(self):
        editions = [
            {"key": "/books/OL789M", "ocaid": "ocaid_restricted"},
            {"key": "/books/OL567M", "ocaid": "ocaid_printdisabled"},
            {"key": "/books/OL234M", "ocaid": "ocaid_borrowable"},
            {"key": "/books/OL123M", "ocaid": "ocaid_open"},
        ]
        ia_md = {
            "ocaid_restricted": {
                "access_restricted_item": "true",
                'collection': [],
            },
            "ocaid_printdisabled": {
                "access_restricted_item": "true",
                "collection": ["printdisabled"],
            },
            "ocaid_borrowable": {
                "access_restricted_item": "true",
                "collection": ["inlibrary"],
            },
            "ocaid_open": {
                "access_restricted_item": "false",
                "collection": ["americanlibraries"],
            },
        }

        assert SolrProcessor.get_ebook_info(editions, ia_md)['ia'] == [
            "ocaid_open",
            "ocaid_borrowable",
            "ocaid_printdisabled",
            "ocaid_restricted",
        ]

    def test_goog_deprioritized(self):
        editions = [
            {"key": "/books/OL789M", "ocaid": "foobargoog"},
            {"key": "/books/OL789M", "ocaid": "foobarblah"},
        ]
        assert SolrProcessor.get_ebook_info(editions, {})['ia'] == [
            "foobarblah",
            "foobargoog",
        ]

    def test_excludes_fav_ia_collections(self):
        doc = {}
        editions = [
            {"key": "/books/OL789M", "ocaid": "foobargoog"},
            {"key": "/books/OL789M", "ocaid": "foobarblah"},
        ]
        ia_md = {
            "foobargoog": {"collection": ['americanlibraries', 'fav-foobar']},
            "foobarblah": {"collection": ['fav-bluebar', 'blah']},
        }

        doc = SolrProcessor.get_ebook_info(editions, ia_md)
        assert doc['ia_collection_s'] == "americanlibraries;blah"


class TestSolrUpdate:
    def sample_response_200(self):
        return Response(
            200,
            request=MagicMock(),
            content=json.dumps(
                {
                    "responseHeader": {
                        "errors": [],
                        "maxErrors": -1,
                        "status": 0,
                        "QTime": 183,
                    }
                }
            ),
        )

    def sample_global_error(self):
        return Response(
            400,
            request=MagicMock(),
            content=json.dumps(
                {
                    'responseHeader': {
                        'errors': [],
                        'maxErrors': -1,
                        'status': 400,
                        'QTime': 76,
                    },
                    'error': {
                        'metadata': [
                            'error-class',
                            'org.apache.solr.common.SolrException',
                            'root-error-class',
                            'org.apache.solr.common.SolrException',
                        ],
                        'msg': "Unknown key 'key' at [14]",
                        'code': 400,
                    },
                }
            ),
        )

    def sample_individual_error(self):
        return Response(
            400,
            request=MagicMock(),
            content=json.dumps(
                {
                    'responseHeader': {
                        'errors': [
                            {
                                'type': 'ADD',
                                'id': '/books/OL1M',
                                'message': '[doc=/books/OL1M] missing required field: type',
                            }
                        ],
                        'maxErrors': -1,
                        'status': 0,
                        'QTime': 10,
                    }
                }
            ),
        )

    def sample_response_503(self):
        return Response(
            503,
            request=MagicMock(),
            content=b"<html><body><h1>503 Service Unavailable</h1>",
        )

    def test_successful_response(self, monkeypatch, monkeytime):
        mock_post = MagicMock(return_value=self.sample_response_200())
        monkeypatch.setattr(httpx, "post", mock_post)

        solr_update(
            [CommitRequest()],
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count == 1

    def test_non_json_solr_503(self, monkeypatch, monkeytime):
        mock_post = MagicMock(return_value=self.sample_response_503())
        monkeypatch.setattr(httpx, "post", mock_post)

        solr_update(
            [CommitRequest()],
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count > 1

    def test_solr_offline(self, monkeypatch, monkeytime):
        mock_post = MagicMock(side_effect=ConnectError('', request=None))
        monkeypatch.setattr(httpx, "post", mock_post)

        solr_update(
            [CommitRequest()],
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count > 1

    def test_invalid_solr_request(self, monkeypatch, monkeytime):
        mock_post = MagicMock(return_value=self.sample_global_error())
        monkeypatch.setattr(httpx, "post", mock_post)

        solr_update(
            [CommitRequest()],
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count == 1

    def test_bad_apple_in_solr_request(self, monkeypatch, monkeytime):
        mock_post = MagicMock(return_value=self.sample_individual_error())
        monkeypatch.setattr(httpx, "post", mock_post)

        solr_update(
            [CommitRequest()],
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count == 1

    def test_other_non_ok_status(self, monkeypatch, monkeytime):
        mock_post = MagicMock(
            return_value=Response(500, request=MagicMock(), content="{}")
        )
        monkeypatch.setattr(httpx, "post", mock_post)

        solr_update(
            [CommitRequest()],
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count > 1
