from types import MappingProxyType
from typing import cast

import pytest

from openlibrary.book_providers import IALiteMetadata
from openlibrary.core.lists.model import SeriesDict
from openlibrary.core.models import WorkSeriesEdge
from openlibrary.solr.updater.work import (
    DataProvider,
    WorkSolrBuilder,
    WorkSolrUpdater,
)
from openlibrary.tests.solr.test_update import (
    FakeDataProvider,
    make_author,
    make_edition,
    make_work,
)


def sorted_split_semicolon(s):
    """
    >>> sorted_split_semicolon("z;c;x;a;y;b")
    ['a', 'b', 'c', 'x', 'y', 'z']
    """
    return sorted(s.split(';'))


sss = sorted_split_semicolon


class TestWorkSolrUpdater:
    @pytest.mark.asyncio
    async def test_no_title(self):
        req, _ = await WorkSolrUpdater(FakeDataProvider()).update_key(
            {'key': '/books/OL1M', 'type': {'key': '/type/edition'}}
        )
        assert len(req.deletes) == 0
        assert len(req.adds) == 1
        assert req.adds[0]['title'] == "__None__"

        req, _ = await WorkSolrUpdater(FakeDataProvider()).update_key(
            {'key': '/works/OL23W', 'type': {'key': '/type/work'}}
        )
        assert len(req.deletes) == 0
        assert len(req.adds) == 1
        assert req.adds[0]['title'] == "__None__"

    @pytest.mark.asyncio
    async def test_work_no_title(self):
        work = {'key': '/works/OL23W', 'type': {'key': '/type/work'}}
        ed = make_edition(work)
        ed['title'] = 'Some Title!'
        req, _ = await WorkSolrUpdater(FakeDataProvider([work, ed])).update_key(work)
        assert len(req.deletes) == 0
        assert len(req.adds) == 1
        assert req.adds[0]['title'] == "Some Title!"

    @pytest.mark.asyncio
    async def test_edition_count_when_editions_in_data_provider(self):
        work = make_work()
        req, _ = await WorkSolrUpdater(FakeDataProvider()).update_key(work)
        assert req.adds[0]['edition_count'] == 0

        req, _ = await WorkSolrUpdater(
            FakeDataProvider([work, make_edition(work)])
        ).update_key(work)
        assert req.adds[0]['edition_count'] == 1

        req, _ = await WorkSolrUpdater(
            FakeDataProvider([work, make_edition(work), make_edition(work)])
        ).update_key(work)
        assert req.adds[0]['edition_count'] == 2


def make_work_solr_builder(
    work: dict | None = None,
    editions: list[dict] | None = None,
    authors: list[dict] | None = None,
    series: list[WorkSeriesEdge[SeriesDict]] | None = None,
    data_provider: DataProvider | None = None,
    ia_metadata: dict[str, dict | None] | None = None,
    trending_data: dict | None = None,
):
    return WorkSolrBuilder(
        work=work or {},
        editions=editions or [],
        authors=authors or [],
        series=series or [],
        data_provider=data_provider or FakeDataProvider(),
        # FIXME: Fix the type
        ia_metadata=cast(dict[str, IALiteMetadata | None], ia_metadata) or {},
        trending_data=trending_data or {},
    )


class TestWorkSolrBuilder:
    def test_simple_work(self):
        work = {"key": "/works/OL1M", "type": {"key": "/type/work"}, "title": "Foo"}

        wsb = make_work_solr_builder(work)
        assert wsb.key == "/works/OL1M"
        assert wsb.title == "Foo"
        assert wsb.has_fulltext is False
        assert wsb.edition_count == 0

    def test_edition_count_when_editions_on_work(self):
        work = make_work()

        wsb = make_work_solr_builder(work)
        assert wsb.edition_count == 0

        wsb = make_work_solr_builder(work, [make_edition()])
        assert wsb.edition_count == 1

        wsb = make_work_solr_builder(work, [make_edition(), make_edition()])
        assert wsb.edition_count == 2

    def test_edition_key(self):
        wsb = make_work_solr_builder(
            work={},
            editions=[
                {'key': '/books/OL1M'},
                {'key': '/books/OL2M'},
                {'key': '/books/OL3M'},
            ],
        )
        assert wsb.edition_key == ["OL1M", "OL2M", "OL3M"]

    def test_publish_year(self):
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
        wsb = make_work_solr_builder(
            work=work,
            editions=[make_edition(work, publish_date=date) for date in test_dates],
        )
        assert wsb.publish_year == {2000, 2001, 2002, 2003, 2004}
        assert wsb.first_publish_year == 2000

    def test_isbns(self):
        work = make_work()
        wsb = make_work_solr_builder(work, [make_edition(work, isbn_10=["123456789X"])])
        assert wsb.isbn == {'123456789X', '9781234567897'}

        wsb = make_work_solr_builder(
            work, [make_edition(work, isbn_10=["9781234567897"])]
        )
        assert wsb.isbn == {'123456789X', '9781234567897'}

    def test_other_identifiers(self):
        work = make_work()
        wsb = make_work_solr_builder(
            work,
            editions=[
                make_edition(work, oclc_numbers=["123"], lccn=["lccn-1", "lccn-2"]),
                make_edition(work, oclc_numbers=["234"], lccn=["lccn-2", "lccn-3"]),
            ],
        )
        assert wsb.oclc == {'123', '234'}
        assert wsb.lccn == {'lccn-1', 'lccn-2', 'lccn-3'}

    def test_identifiers(self):
        work = make_work()
        d = make_work_solr_builder(
            work=work,
            editions=[
                make_edition(work, identifiers={"librarything": ["lt-1"]}),
                make_edition(work, identifiers={"librarything": ["lt-2"]}),
            ],
        ).build_identifiers()
        assert sorted(d.get('id_librarything', [])) == ['lt-1', 'lt-2']

    def test_ia_boxid(self):
        w = make_work()
        d = make_work_solr_builder(w, [make_edition(w)]).build_legacy_ia_fields()
        assert 'ia_box_id' not in d

        w = make_work()
        d = make_work_solr_builder(
            w, [make_edition(w, ia_box_id='foo')]
        ).build_legacy_ia_fields()
        assert d['ia_box_id'] == ['foo']

    def test_with_one_lending_edition(self):
        w = make_work()
        d = make_work_solr_builder(
            work=w,
            editions=[make_edition(w, key="/books/OL1M", ocaid='foo00bar')],
            ia_metadata={"foo00bar": {"collection": ['inlibrary', 'americana']}},
        )

        assert d.has_fulltext is True
        assert d.public_scan_b is False
        assert d.printdisabled_s is None
        assert d.lending_edition_s == 'OL1M'
        assert d.ia == ['foo00bar']
        assert sorted(d.ia_collection) == sorted(["americana", "inlibrary"])
        assert d.edition_count == 1
        assert d.ebook_count_i == 1

    def test_with_two_lending_editions(self):
        w = make_work()
        d = make_work_solr_builder(
            work=w,
            editions=[
                make_edition(w, key="/books/OL1M", ocaid='foo01bar'),
                make_edition(w, key="/books/OL2M", ocaid='foo02bar'),
            ],
            ia_metadata={
                "foo01bar": {"collection": ['inlibrary', 'americana']},
                "foo02bar": {"collection": ['inlibrary', 'internetarchivebooks']},
            },
        )
        assert d.has_fulltext is True
        assert d.public_scan_b is False
        assert d.printdisabled_s is None
        assert d.lending_edition_s == 'OL1M'
        assert sorted(d.ia) == ['foo01bar', 'foo02bar']
        assert sorted(d.ia_collection) == sorted(
            ["inlibrary", "americana", "internetarchivebooks"]
        )
        assert d.edition_count == 2
        assert d.ebook_count_i == 2

    def test_with_one_inlibrary_edition(self):
        w = make_work()
        d = make_work_solr_builder(
            work=w,
            editions=[make_edition(w, key="/books/OL1M", ocaid='foo00bar')],
            ia_metadata={"foo00bar": {"collection": ['printdisabled', 'inlibrary']}},
        )
        assert d.has_fulltext is True
        assert d.public_scan_b is False
        assert d.printdisabled_s == 'OL1M'
        assert d.lending_edition_s == 'OL1M'
        assert d.ia == ['foo00bar']
        assert sorted(d.ia_collection) == sorted(["printdisabled", "inlibrary"])
        assert d.edition_count == 1
        assert d.ebook_count_i == 1

    def test_with_one_printdisabled_edition(self):
        w = make_work()
        d = make_work_solr_builder(
            work=w,
            editions=[make_edition(w, key="/books/OL1M", ocaid='foo00bar')],
            ia_metadata={"foo00bar": {"collection": ['printdisabled', 'americana']}},
        )
        assert d.has_fulltext is True
        assert d.public_scan_b is False
        assert d.printdisabled_s == 'OL1M'
        assert d.lending_edition_s is None
        assert d.ia == ['foo00bar']
        assert sorted(d.ia_collection) == sorted(["printdisabled", "americana"])
        assert d.edition_count == 1
        assert d.ebook_count_i == 1

    def test_alternative_title(self):
        def f(editions):
            return make_work_solr_builder(
                {'key': '/works/OL1W'}, editions
            ).alternative_title

        no_title = make_work()
        del no_title['title']
        only_title = make_work(title='foo')
        with_subtitle = make_work(title='foo 2', subtitle='bar')

        assert f([]) == set()
        assert f([no_title]) == set()
        assert f([only_title, no_title]) == {'foo'}
        assert f([with_subtitle, only_title]) == {'foo 2: bar', 'foo'}

    def test_with_multiple_editions(self):
        w = make_work()
        d = make_work_solr_builder(
            work=w,
            editions=[
                make_edition(w, key="/books/OL1M"),
                make_edition(w, key="/books/OL2M", ocaid='foo00bar'),
                make_edition(w, key="/books/OL3M", ocaid='foo01bar'),
                make_edition(w, key="/books/OL4M", ocaid='foo02bar'),
            ],
            ia_metadata={
                "foo00bar": {"collection": ['americana']},
                "foo01bar": {"collection": ['inlibrary', 'americana']},
                "foo02bar": {"collection": ['printdisabled', 'inlibrary']},
            },
        )
        assert d.has_fulltext is True
        assert d.public_scan_b is True
        assert d.printdisabled_s == 'OL4M'
        assert d.lending_edition_s == 'OL2M'
        assert sorted(d.ia) == ['foo00bar', 'foo01bar', 'foo02bar']
        assert sorted(d.ia_collection) == sorted(
            ["americana", "inlibrary", "printdisabled"]
        )

        assert d.edition_count == 4
        assert d.ebook_count_i == 3

    def test_subjects(self):
        w = make_work(subjects=["a", "b c"])
        d = make_work_solr_builder(w).build_subjects()

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
        d = make_work_solr_builder(w).build_subjects()

        for k in ['subject', 'person', 'place', 'time']:
            assert d[k] == ['a', "b c"]
            assert d[k + '_facet'] == ['a', "b c"]
            assert d[k + '_key'] == ['a', "b_c"]

    def test_author_info(self):
        authors = [
            {
                'key': "/authors/OL1A",
                'name': "Author One",
                'alternate_names': ["Author 1"],
            },
            {'key': "/authors/OL2A", 'name': "Author Two"},
        ]

        w = make_work(
            authors=[make_author(key='/authors/OL1A'), make_author(key='/authors/OL2A')]
        )
        d = make_work_solr_builder(w, authors=authors)
        assert d.author_name == ["Author One", "Author Two"]
        assert d.author_key == ['OL1A', 'OL2A']
        assert d.author_facet == ['OL1A Author One', 'OL2A Author Two']
        assert d.author_alternative_name == {"Author 1"}

    # {'Test name': (doc_lccs, solr_lccs, sort_lcc_index)}
    LCC_TESTS = MappingProxyType(
        {
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
    )

    @pytest.mark.parametrize(
        ('doc_lccs', 'solr_lccs', 'sort_lcc_index'),
        LCC_TESTS.values(),
        ids=LCC_TESTS.keys(),
    )
    def test_lccs(self, doc_lccs, solr_lccs, sort_lcc_index):
        work = make_work()
        d = make_work_solr_builder(
            work, editions=[make_edition(work, lc_classifications=doc_lccs)]
        )
        if solr_lccs:
            assert d.lcc == set(solr_lccs)
            if sort_lcc_index is not None:
                assert d.lcc_sort == solr_lccs[sort_lcc_index]
        else:
            assert d.lcc == set()
            assert d.lcc_sort is None

    DDC_TESTS = MappingProxyType(
        {
            'Remove dupes': (['123.5', '123.5'], ['123.5'], 0),
            'Handles none': ([], None, None),
            'Handles empty string': ([''], None, None),
            'Stores multiple': (['05', '123.5'], ['005', '123.5'], 1),
            'Handles full DDC': (
                ['j132.452939 [B]'],
                ['132.452939 B', 'j132.452939 B'],
                0,
            ),
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
    )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('doc_ddcs', 'solr_ddcs', 'sort_ddc_index'),
        DDC_TESTS.values(),
        ids=DDC_TESTS.keys(),
    )
    async def test_ddcs(self, doc_ddcs, solr_ddcs, sort_ddc_index):
        work = make_work()
        d = make_work_solr_builder(
            work, [make_edition(work, dewey_decimal_class=doc_ddcs)]
        )
        if solr_ddcs:
            assert d.ddc == set(solr_ddcs)
            assert d.ddc_sort == solr_ddcs[sort_ddc_index]
        else:
            assert d.ddc == set()
            assert d.ddc_sort is None

    def test_contributor(self):
        work = make_work()
        d = make_work_solr_builder(
            work,
            [make_edition(work, contributors=[{'role': 'Illustrator', 'name': 'Foo'}])],
        )

        # For now it should ignore it and not error
        assert d.contributor == set()


class Test_number_of_pages_median:
    def test_no_editions(self):
        wsb = make_work_solr_builder(
            {"key": "/works/OL1W", "type": {"key": "/type/work"}}
        )
        assert wsb.number_of_pages_median is None

    def test_invalid_type(self):
        wsb = make_work_solr_builder(
            {"key": "/works/OL1W", "type": {"key": "/type/work"}},
            [make_edition(number_of_pages='spam')],
        )
        assert wsb.number_of_pages_median is None
        wsb = make_work_solr_builder(
            {"key": "/works/OL1W", "type": {"key": "/type/work"}},
            [make_edition(number_of_pages=n) for n in [123, 122, 'spam']],
        )
        assert wsb.number_of_pages_median == 123

    def test_normal_case(self):
        wsb = make_work_solr_builder(
            {"key": "/works/OL1W", "type": {"key": "/type/work"}},
            [make_edition(number_of_pages=n) for n in [123, 122, 1]],
        )
        assert wsb.number_of_pages_median == 122
        wsb = make_work_solr_builder(
            {"key": "/works/OL1W", "type": {"key": "/type/work"}},
            [make_edition(), make_edition()]
            + [make_edition(number_of_pages=n) for n in [123, 122, 1]],
        )
        assert wsb.number_of_pages_median == 122


class Test_Sort_Editions_Ocaids:
    def test_sort(self):
        wsb = make_work_solr_builder(
            work={},
            editions=[
                {"key": "/books/OL789M", "ocaid": "ocaid_restricted"},
                {"key": "/books/OL567M", "ocaid": "ocaid_printdisabled"},
                {"key": "/books/OL234M", "ocaid": "ocaid_borrowable"},
                {"key": "/books/OL123M", "ocaid": "ocaid_open"},
            ],
            ia_metadata={
                "ocaid_restricted": {
                    "access_restricted_item": "true",
                    'collection': {},
                },
                "ocaid_printdisabled": {
                    "access_restricted_item": "true",
                    "collection": {"printdisabled"},
                },
                "ocaid_borrowable": {
                    "access_restricted_item": "true",
                    "collection": {"inlibrary"},
                },
                "ocaid_open": {
                    "access_restricted_item": "false",
                    "collection": {"americanlibraries"},
                },
            },
        )

        assert wsb.ia == [
            "ocaid_open",
            "ocaid_borrowable",
            "ocaid_printdisabled",
            "ocaid_restricted",
        ]

    def test_goog_deprioritized(self):
        wsb = make_work_solr_builder(
            work={},
            editions=[
                {"key": "/books/OL789M", "ocaid": "foobargoog"},
                {"key": "/books/OL789M", "ocaid": "foobarblah"},
            ],
        )
        assert wsb.ia == [
            "foobarblah",
            "foobargoog",
        ]

    def test_excludes_fav_ia_collections(self):
        wsb = make_work_solr_builder(
            work={},
            editions=[
                {"key": "/books/OL789M", "ocaid": "foobargoog"},
                {"key": "/books/OL789M", "ocaid": "foobarblah"},
            ],
            ia_metadata={
                "foobargoog": {"collection": ['americanlibraries', 'fav-foobar']},
                "foobarblah": {"collection": ['fav-bluebar', 'blah']},
            },
        )

        assert sorted(wsb.ia_collection) == sorted(["americanlibraries", "blah"])
