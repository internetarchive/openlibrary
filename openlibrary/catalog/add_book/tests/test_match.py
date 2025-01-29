from copy import deepcopy
from types import MappingProxyType

import pytest

from openlibrary.catalog.add_book import load
from openlibrary.catalog.add_book.match import (
    THRESHOLD,
    add_db_name,
    build_titles,
    compare_authors,
    compare_publisher,
    editions_match,
    expand_record,
    mk_norm,
    normalize,
    threshold_match,
)


def test_editions_match_identical_record(mock_site):
    rec = {
        'title': 'Test item',
        'lccn': ['12345678'],
        'authors': [{'name': 'Smith, John', 'birth_date': '1980'}],
        'source_records': ['ia:test_item'],
    }
    reply = load(rec)
    ekey = reply['edition']['key']
    e = mock_site.get(ekey)
    assert editions_match(rec, e) is True


def test_add_db_name():
    authors = [
        {'name': 'Smith, John'},
        {'name': 'Smith, John', 'date': '1950'},
        {'name': 'Smith, John', 'birth_date': '1895', 'death_date': '1964'},
    ]
    orig = deepcopy(authors)
    add_db_name({'authors': authors})
    orig[0]['db_name'] = orig[0]['name']
    orig[1]['db_name'] = orig[1]['name'] + ' 1950'
    orig[2]['db_name'] = orig[2]['name'] + ' 1895-1964'
    assert authors == orig

    rec = {}
    add_db_name(rec)
    assert rec == {}

    # Handle `None` authors values.
    rec = {'authors': None}
    add_db_name(rec)
    assert rec == {'authors': None}


titles = [
    ('Hello this is a           Title', 'hello this is a title'),  # Spaces
    ('Kitāb Yatīmat ud-Dahr', 'kitāb yatīmat ud dahr'),  # Unicode
    ('This and That', 'this and that'),
    ('This & That', 'this and that'),  # ampersand
    ('A Title.', 'a title'),  # period and space stripping
    ('A Title. ', 'a title'),
    ('A Title .', 'a title'),
    ('The Fish and Chips', 'the fish and chips'),
    ('A Fish & Chip shop', 'a fish and chip shop'),
]


@pytest.mark.parametrize(('title', 'normalized'), titles)
def test_normalize(title, normalized):
    assert normalize(title) == normalized


mk_norm_conversions = [
    ("Hello I'm a  title.", "helloi'matitle"),
    ("Hello I'm a  title.", "helloi'matitle"),
    ('Forgotten Titles: A Novel.', 'forgottentitlesanovel'),
    ('Kitāb Yatīmat ud-Dahr', 'kitābyatīmatuddahr'),
    ('The Fish and Chips', 'fishchips'),
    ('A Fish & Chip shop', 'fishchipshop'),
]


@pytest.mark.parametrize(('title', 'expected'), mk_norm_conversions)
def test_mk_norm(title, expected):
    assert mk_norm(title) == expected


mk_norm_matches = [
    ("Your Baby's First Word Will Be DADA", "Your baby's first word will be DADA"),
]


@pytest.mark.parametrize(('a', 'b'), mk_norm_matches)
def test_mk_norm_equality(a, b):
    assert mk_norm(a) == mk_norm(b)


class TestExpandRecord:
    rec = MappingProxyType(
        {
            'title': 'A test full title',
            'subtitle': 'subtitle (parens).',
            'source_records': ['ia:test-source'],
        }
    )

    def test_expand_record(self):
        edition = self.rec.copy()
        expanded_record = expand_record(edition)
        assert isinstance(expanded_record['titles'], list)
        assert self.rec['title'] not in expanded_record['titles']

        expected_titles = [
            edition['full_title'],
            'a test full title subtitle (parens)',
            'test full title subtitle (parens)',
            'a test full title subtitle',
            'test full title subtitle',
        ]
        for t in expected_titles:
            assert t in expanded_record['titles']
        assert len(set(expanded_record['titles'])) == len(set(expected_titles))
        assert (
            expanded_record['normalized_title'] == 'a test full title subtitle (parens)'
        )
        assert expanded_record['short_title'] == 'a test full title subtitl'

    def test_expand_record_publish_country(self):
        edition = self.rec.copy()
        expanded_record = expand_record(edition)
        assert 'publish_country' not in expanded_record
        for publish_country in ('   ', '|||'):
            edition['publish_country'] = publish_country
            assert 'publish_country' not in expand_record(edition)
        for publish_country in ('USA', 'usa'):
            edition['publish_country'] = publish_country
            assert expand_record(edition)['publish_country'] == publish_country

    def test_expand_record_transfer_fields(self):
        edition = self.rec.copy()
        expanded_record = expand_record(edition)
        transfer_fields = (
            'lccn',
            'publishers',
            'publish_date',
            'number_of_pages',
            'authors',
            'contribs',
        )
        for field in transfer_fields:
            assert field not in expanded_record
        for field in transfer_fields:
            edition[field] = []
        expanded_record = expand_record(edition)
        for field in transfer_fields:
            assert field in expanded_record

    def test_expand_record_isbn(self):
        edition = self.rec.copy()
        expanded_record = expand_record(edition)
        assert expanded_record['isbn'] == []
        edition.update(
            {
                'isbn': ['1234567890'],
                'isbn_10': ['123', '321'],
                'isbn_13': ['1234567890123'],
            }
        )
        expanded_record = expand_record(edition)
        assert expanded_record['isbn'] == ['1234567890', '123', '321', '1234567890123']


class TestAuthors:
    @pytest.mark.xfail(
        reason=(
            'This expected result taken from the amazon and '
            'merge versions of compare_author, '
            'Current merge_marc.compare_authors() '
            'does NOT take by_statement into account.'
        )
    )
    def test_compare_authors_by_statement(self):
        rec1 = {
            'title': 'Full Title, required',
            'authors': [{'name': 'Alistair Smith'}],
        }
        rec2 = {
            'title': 'A different Full Title, only matching authors here.',
            'authors': [
                {
                    'name': 'National Gallery (Great Britain)',
                    'entity_type': 'org',
                }
            ],
            'by_statement': 'Alistair Smith.',
        }
        result = compare_authors(expand_record(rec1), expand_record(rec2))
        assert result == ('main', 'exact match', 125)

    def test_author_contrib(self):
        rec1 = {
            'authors': [{'name': 'Bruner, Jerome S.'}],
            'title': 'Contemporary approaches to cognition ',
            'subtitle': 'a symposium held at the University of Colorado.',
            'number_of_pages': 210,
            'publish_country': 'xxu',
            'publish_date': '1957',
            'publishers': ['Harvard U.P'],
        }
        rec2 = {
            'authors': [
                {
                    'name': (
                        'University of Colorado (Boulder campus). '
                        'Dept. of Psychology.'
                    )
                }
            ],
            # TODO: the contrib db_name needs to be populated by expand_record() to be useful
            'contribs': [{'name': 'Bruner, Jerome S.', 'db_name': 'Bruner, Jerome S.'}],
            'title': 'Contemporary approaches to cognition ',
            'subtitle': 'a symposium held at the University of Colorado',
            'lccn': ['57012963'],
            'number_of_pages': 210,
            'publish_country': 'mau',
            'publish_date': '1957',
            'publishers': ['Harvard University Press'],
        }
        assert compare_authors(expand_record(rec1), expand_record(rec2)) == (
            'authors',
            'exact match',
            125,
        )
        threshold = 875
        assert threshold_match(rec1, rec2, threshold) is True


class TestTitles:
    def test_build_titles(self):
        # Used by openlibrary.catalog.merge.merge_marc.expand_record()
        full_title = 'This is a title.'  # Input title
        normalized = 'this is a title'  # Expected normalization
        result = build_titles(full_title)
        assert isinstance(result['titles'], list)
        assert result['full_title'] == full_title
        assert result['short_title'] == normalized
        assert result['normalized_title'] == normalized
        assert len(result['titles']) == 2
        assert full_title in result['titles']
        assert normalized in result['titles']

    def test_build_titles_ampersand(self):
        full_title = 'This & that'
        result = build_titles(full_title)
        assert 'this and that' in result['titles']
        assert 'This & that' in result['titles']

    def test_build_titles_complex(self):
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

        assert 'test full title subtitle' in titles
        assert 'a test full title subtitle' in titles

        # Check for duplicates:
        assert len(titles_period) == len(set(titles_period))
        assert len(titles) == len(set(titles))
        assert len(titles) == len(titles_period)


def test_compare_publisher():
    foo = {'publishers': ['foo']}
    bar = {'publishers': ['bar']}
    foo2 = {'publishers': ['foo']}
    both = {'publishers': ['foo', 'bar']}
    assert compare_publisher({}, {}) == ('publisher', 'either missing', 0)
    assert compare_publisher(foo, {}) == ('publisher', 'either missing', 0)
    assert compare_publisher({}, bar) == ('publisher', 'either missing', 0)
    assert compare_publisher(foo, foo2) == ('publisher', 'match', 100)
    assert compare_publisher(foo, bar) == ('publisher', 'mismatch', -51)
    assert compare_publisher(bar, both) == ('publisher', 'match', 100)
    assert compare_publisher(both, foo) == ('publisher', 'match', 100)


class TestRecordMatching:
    def test_match_without_ISBN(self):
        # Same year, different publishers
        # one with ISBN, one without
        bpl = {
            'authors': [
                {
                    'birth_date': '1897',
                    'entity_type': 'person',
                    'name': 'Green, Constance McLaughlin',
                    'personal_name': 'Green, Constance McLaughlin',
                }
            ],
            'title': 'Eli Whitney and the birth of American technology',
            'isbn': ['188674632X'],
            'number_of_pages': 215,
            'publish_date': '1956',
            'publishers': ['HarperCollins', '[distributed by Talman Pub.]'],
            'source_records': ['marc:bpl/bpl101.mrc:0:1226'],
        }
        lc = {
            'authors': [
                {
                    'birth_date': '1897',
                    'entity_type': 'person',
                    'name': 'Green, Constance McLaughlin',
                    'personal_name': 'Green, Constance McLaughlin',
                }
            ],
            'title': 'Eli Whitney and the birth of American technology.',
            'isbn': [],
            'number_of_pages': 215,
            'publish_date': '1956',
            'publishers': ['Little, Brown'],
            'source_records': [
                'marc:marc_records_scriblio_net/part04.dat:119539872:591'
            ],
        }
        assert compare_authors(expand_record(bpl), expand_record(lc)) == (
            'authors',
            'exact match',
            125,
        )
        threshold = 875
        assert threshold_match(bpl, lc, threshold) is True

    def test_match_low_threshold(self):
        # year is off by < 2 years, counts a little
        e1 = {
            'publishers': ['Collins'],
            'isbn_10': ['0002167530'],
            'number_of_pages': 287,
            'title': 'Sea Birds Britain Ireland',
            'publish_date': '1975',
            'authors': [{'name': 'Stanley Cramp'}],
        }
        e2 = {
            'publishers': ['Collins'],
            'isbn_10': ['0002167530'],
            'title': 'seabirds of Britain and Ireland',
            'publish_date': '1974',
            'authors': [
                {
                    'entity_type': 'person',
                    'name': 'Stanley Cramp.',
                    'personal_name': 'Cramp, Stanley.',
                }
            ],
            'source_records': [
                'marc:marc_records_scriblio_net/part08.dat:61449973:855'
            ],
        }
        threshold = 515
        assert threshold_match(e1, e2, threshold) is True
        assert threshold_match(e1, e2, threshold + 1) is False

    def test_matching_title_author_and_publish_year_but_not_publishers(self) -> None:
        """
        Matching only title, author, and publish_year should not be sufficient for
        meeting the match threshold if the publisher is truthy and doesn't match,
        as a book published in different publishers in the same year would easily meet
        the criteria.
        """
        existing_edition = {
            'authors': [{'name': 'Edgar Lee Masters'}],
            'publish_date': '2022',
            'publishers': ['Creative Media Partners, LLC'],
            'title': 'Spoon River Anthology',
        }

        potential_match1 = {
            'authors': [{'name': 'Edgar Lee Masters'}],
            'publish_date': '2022',
            'publishers': ['Standard Ebooks'],
            'title': 'Spoon River Anthology',
        }
        assert threshold_match(existing_edition, potential_match1, THRESHOLD) is False

        potential_match2 = {
            'authors': [{'name': 'Edgar Lee Masters'}],
            'publish_date': '2022',
            'title': 'Spoon River Anthology',
        }

        # If there is no publisher and nothing else to match, the editions should be
        # indistinguishable, and therefore matches.
        assert threshold_match(existing_edition, potential_match2, THRESHOLD) is True

    def test_noisbn_record_should_not_match_title_only(self):
        # An existing light title + ISBN only record
        existing_edition = {
            # NO author
            # NO date
            #'publishers': ['Creative Media Partners, LLC'],
            'title': 'Just A Title',
            'isbn_13': ['9780000000002'],
        }
        potential_match = {
            'authors': [{'name': 'Bob Smith'}],
            'publish_date': '1913',
            'publishers': ['Early Editions'],
            'title': 'Just A Title',
            'source_records': ['marc:somelibrary/some_marc.mrc'],
        }
        assert threshold_match(existing_edition, potential_match, THRESHOLD) is False
