import pytest
from openlibrary.catalog.merge.merge_marc import (
    build_marc, build_titles,
    compare_authors, compare_publisher,
    editions_match)


class TestAuthors:
    @pytest.mark.xfail(reason=(
        'This expected result taken from the amazon and '
        'merge versions of compare_author, '
        'Current merge_marc.compare_authors() '
        'does NOT take by_statement into account.'))
    def test_compare_authors_by_statement(self):
        # requires db_name to be present on both records.
        rec1 = {
            'full_title': 'Full Title, required',
            'authors': [{
                'name': 'Alistair Smith',
                'db_name': 'Alistair Smith'}]}
        rec2 = {
            'full_title': 'A different Full Title, only matching authors here.',
            'authors': [{
                'db_name': 'National Gallery (Great Britain)',
                'name': 'National Gallery (Great Britain)',
                'entity_type': 'org'}],
            'by_statement': 'Alistair Smith.'}

        result = compare_authors(build_marc(rec1), build_marc(rec2))
        assert result == ('main', 'exact match', 125)

    def test_author_contrib(self):
        rec1 = {
            'authors': [
                {'db_name': 'Bruner, Jerome S.',
                 'name': 'Bruner, Jerome S.'}],
            'full_title': ('Contemporary approaches to cognition '
                           'a symposium held at the University of Colorado.'),
            'number_of_pages': 210,
            'publish_country': 'xxu',
            'publish_date': '1957',
            'publishers': ['Harvard U.P']}

        rec2 = {
            'authors': [
                {'db_name': ('University of Colorado (Boulder campus). '
                             'Dept. of Psychology.'),
                 'name': ('University of Colorado (Boulder campus). '
                          'Dept. of Psychology.')}],
            'contribs': [
                {'db_name': 'Bruner, Jerome S.',
                 'name': 'Bruner, Jerome S.'}],
            'full_title': ('Contemporary approaches to cognition '
                           'a symposium held at the University of Colorado'),
            'lccn': ['57012963'],
            'number_of_pages': 210,
            'publish_country': 'mau',
            'publish_date': '1957',
            'publishers': ['Harvard University Press']}

        e1 = build_marc(rec1)
        e2 = build_marc(rec2)

        assert compare_authors(e1, e2) == ('authors', 'exact match', 125)
        threshold = 875
        assert editions_match(e1, e2, threshold) is True


class TestTitles:
    def test_build_titles(self):
        # Used by openlibrary.catalog.merge.merge_marc.build_marc()
        full_title = 'This is a title.'
        normalized = 'this is a title'
        result = build_titles(full_title)
        assert isinstance(result['titles'], list)
        assert result['full_title'] == full_title
        assert result['short_title'] == normalized
        assert result['normalized_title'] == normalized
        assert result['titles'] == ['This is a title.', 'this is a title']

    def test_build_titles_complex(self):
        # TODO: There are issues with this method
        # see https://github.com/internetarchive/openlibrary/issues/2410
        full_title = 'A test full title : subtitle (parens)'
        full_title_period = 'A test full title : subtitle (parens).'
        titles_period = build_titles(full_title_period)['titles']

        assert isinstance(titles_period, list)
        assert full_title_period in titles_period

        titles = build_titles(full_title)['titles']
        assert full_title in titles

        common_titles = [
            'a test full title subtitle (parens)',
            'test full title subtitle (parens)',
        ]
        for t in common_titles:
            assert t in titles
            assert t in titles_period

        # Missing variations:
        # assert 'test full title subtitle' in a_titles
        assert 'test full title subtitle' in titles
        # assert 'a test full title subtitle' in a_titles
        assert 'a test full title subtitle' in titles

        # Check for duplicates:
        assert len(titles_period) == len(set(titles_period))
        # assert len(titles) == len(set(titles))


def test_build_marc():
    # used in openlibrary.catalog.add_book.load()
    # when trying to find an existing edition match
    edition = {
            'title': 'A test title (parens)',
            'full_title': 'A test full title : subtitle (parens).',  # required, and set by add_book.load()
            'source_records': ['ia:test-source']
            }
    result = build_marc(edition)
    assert isinstance(result['titles'], list)
    assert result['isbn'] == []
    assert result['normalized_title'] == 'a test full title subtitle (parens)'
    assert result['short_title'] == 'a test full title subtitl'


def test_compare_publisher():
    foo = {'publishers': ['foo']}
    bar = {'publishers': ['bar']}
    foo2 = {'publishers': ['foo']}
    both = {'publishers': ['foo', 'bar']}
    assert compare_publisher({}, {}) == ('publisher', 'either missing', 0)
    assert compare_publisher(foo, {}) == ('publisher', 'either missing', 0)
    assert compare_publisher({}, bar) == ('publisher', 'either missing', 0)
    assert compare_publisher(foo, foo2) == ('publisher', 'match', 100)
    assert compare_publisher(foo, bar) == ('publisher', 'mismatch', -25)
    assert compare_publisher(bar, both) == ('publisher', 'match', 100)
    assert compare_publisher(both, foo) == ('publisher', 'match', 100)


class TestRecordMatching:
    def test_match_without_ISBN(self):
        # Same year, different publishers
        # one with ISBN, one without
        bpl = {
            'authors': [
                {'birth_date': '1897',
                 'db_name': 'Green, Constance McLaughlin 1897-',
                 'entity_type': 'person',
                 'name': 'Green, Constance McLaughlin',
                 'personal_name': 'Green, Constance McLaughlin'}],
            'full_title': 'Eli Whitney and the birth of American technology',
            'isbn': ['188674632X'],
            'normalized_title': 'eli whitney and the birth of american technology',
            'number_of_pages': 215,
            'publish_date': '1956',
            'publishers': ['HarperCollins', '[distributed by Talman Pub.]'],
            'short_title': 'eli whitney and the birth',
            'source_record_loc': 'bpl101.mrc:0:1226',
            'titles': [
                'Eli Whitney and the birth of American technology',
                'eli whitney and the birth of american technology']}
        lc = {
            'authors': [
                {'birth_date': '1897',
                 'db_name': 'Green, Constance McLaughlin 1897-',
                 'entity_type': 'person',
                 'name': 'Green, Constance McLaughlin',
                 'personal_name': 'Green, Constance McLaughlin'}],
            'full_title': 'Eli Whitney and the birth of American technology.',
            'isbn': [],
            'normalized_title': 'eli whitney and the birth of american technology',
            'number_of_pages': 215,
            'publish_date': '1956',
            'publishers': ['Little, Brown'],
            'short_title': 'eli whitney and the birth',
            'source_record_loc': 'marc_records_scriblio_net/part04.dat:119539872:591',
            'titles': [
                'Eli Whitney and the birth of American technology.',
                'eli whitney and the birth of american technology']}

        assert compare_authors(bpl, lc) == ('authors', 'exact match', 125)
        threshold = 875
        assert editions_match(bpl, lc, threshold) is True

    def test_match_low_threshold(self):
        # year is off by < 2 years, counts a little
        # build_marc() will place all isbn_ types in the 'isbn' field.
        e1 = build_marc({
            'publishers': ['Collins'],
            'isbn_10': ['0002167530'],
            'number_of_pages': 287,
            'short_title': 'sea birds britain ireland',
            'normalized_title': u'sea birds britain ireland',
            'full_title': 'Sea Birds Britain Ireland',
            'titles': [
                'Sea Birds Britain Ireland',
                'sea birds britain ireland'],
            'publish_date': '1975',
            'authors': [
                {'name': 'Stanley Cramp',
                 'db_name': 'Cramp, Stanley'}]})

        e2 = build_marc({
            'publishers': ['Collins'],
            'isbn_10': ['0002167530'],
            'short_title': 'seabirds of britain and i',
            'normalized_title': 'seabirds of britain and ireland',
            'full_title': 'seabirds of Britain and Ireland',
            'titles': [
                'seabirds of Britain and Ireland',
                'seabirds of britain and ireland'],
            'publish_date': '1974',
            'authors': [
                {'db_name': 'Cramp, Stanley.',
                 'entity_type': 'person',
                 'name': u'Cramp, Stanley.',
                 'personal_name': u'Cramp, Stanley.'}],
            'source_record_loc': 'marc_records_scriblio_net/part08.dat:61449973:855'})
        threshold = 515
        assert editions_match(e1, e2, threshold, debug=True)
        assert editions_match(e1, e2, threshold + 1) is False
