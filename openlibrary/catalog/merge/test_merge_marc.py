import pytest
from openlibrary.catalog.merge.merge_marc import attempt_merge, build_marc, build_titles, compare_authors

@pytest.mark.xfail(reason='Taken from openlibrary.catalog.merge.merge.compare_authors -- does not find a match.')
def test_compare_authors_by_statement():
    # requires db_name to be present on both records.
    rec1 = {
            'full_title': 'Full Title, required',
            'authors': [{
                'name': 'Alistair Smith',
                'db_name': 'Alistair Smith'}]}
    rec2 = {
            'full_title': 'A different Full Title, only matching authors here.',
            'authors': [{
                'db_name': u'National Gallery (Great Britain)',
                'name': u'National Gallery (Great Britain)',
                'entity_type': 'org'}],
            'by_statement': 'Alistair Smith.'}

    result = compare_authors(build_marc(rec1), build_marc(rec2))
    # This expected result taken from the amazon and merge versions of compare_author,
    # Current merge_marc.compare_authors() does not take by_statement into account.
    assert result == ('main', 'exact match', 125)

def test_build_titles():
    # Used by build_marc()
    a = 'This is a title.'
    normalized = 'this is a title'
    result = build_titles(a)
    assert isinstance(result['titles'], list)
    assert result['full_title'] == a
    assert result['short_title'] == normalized
    assert result['normalized_title'] == normalized
    assert result['titles'] == ['This is a title.', 'this is a title']

def test_build_titles_complex():
    # TODO: There are issues with this method
    # see https://github.com/internetarchive/openlibrary/issues/2410
    a = 'A test full title : subtitle (parens).'
    b = 'A test full title : subtitle (parens)'
    a_result = build_titles(a)
    a_titles = a_result['titles']
    assert a in a_titles

    b_result = build_titles(b)
    b_titles = b_result['titles']
    assert b in b_titles

    common_titles = [
            'a test full title subtitle (parens)',
            'test full title subtitle (parens)',
            ]
    for title in common_titles:
        assert title in a_titles
        assert title in b_titles

    # Missing variations:
    #assert 'test full title subtitle' in a_titles
    assert 'test full title subtitle' in b_titles
    #assert 'a test full title subtitle' in a_titles
    assert 'a test full title subtitle' in b_titles

    # Check for duplicates:
    assert len(a_titles) == len(set(a_titles))
    #assert len(b_titles) == len(set(b_titles))

def test_build_marc():
    # used in add_book.load() when trying to find an existing edition match
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

def test_author_contrib():
    rec1 = {'authors': [{'db_name': u'Bruner, Jerome S.', 'name': u'Bruner, Jerome S.'}],
    'full_title': u'Contemporary approaches to cognition a symposium held at the University of Colorado.',
    'number_of_pages': 210,
    'publish_country': 'xxu',
    'publish_date': '1957',
    'publishers': [u'Harvard U.P']}

    rec2 = {'authors': [{'db_name': u'University of Colorado (Boulder campus). Dept. of Psychology.',
                'name': u'University of Colorado (Boulder campus). Dept. of Psychology.'}],
    'contribs': [{'db_name': u'Bruner, Jerome S.', 'name': u'Bruner, Jerome S.'}],
    'full_title': u'Contemporary approaches to cognition a symposium held at the University of Colorado',
    'lccn': ['57012963'],
    'number_of_pages': 210,
    'publish_country': 'mau',
    'publish_date': '1957',
    'publishers': [u'Harvard University Press']}

    e1 = build_marc(rec1)
    e2 = build_marc(rec2)

    assert compare_authors(e1, e2) == ('authors', 'exact match', 125)
    threshold = 875
    assert attempt_merge(e1, e2, threshold) is True

def test_merge():
    bpl = {'authors': [{'birth_date': u'1897',
                      'db_name': u'Green, Constance McLaughlin 1897-',
                      'entity_type': 'person',
                      'name': u'Green, Constance McLaughlin',
                      'personal_name': u'Green, Constance McLaughlin'}],
         'full_title': u'Eli Whitney and the birth of American technology',
         'isbn': [u'188674632X'],
         'normalized_title': u'eli whitney and the birth of american technology',
         'number_of_pages': 215,
         'publish_date': '1956',
         'publishers': [u'HarperCollins', u'[distributed by Talman Pub.]'],
         'short_title': u'eli whitney and the birth',
         'source_record_loc': 'bpl101.mrc:0:1226',
         'titles': [u'Eli Whitney and the birth of American technology',
                    u'eli whitney and the birth of american technology']}
    lc = {'authors': [{'birth_date': u'1897',
                     'db_name': u'Green, Constance McLaughlin 1897-',
                     'entity_type': 'person',
                     'name': u'Green, Constance McLaughlin',
                     'personal_name': u'Green, Constance McLaughlin'}],
        'full_title': u'Eli Whitney and the birth of American technology.',
        'isbn': [],
        'normalized_title': u'eli whitney and the birth of american technology',
        'number_of_pages': 215,
        'publish_date': '1956',
        'publishers': ['Little, Brown'],
        'short_title': u'eli whitney and the birth',
        'source_record_loc': 'marc_records_scriblio_net/part04.dat:119539872:591',
        'titles': [u'Eli Whitney and the birth of American technology.',
                   u'eli whitney and the birth of american technology']}

    assert compare_authors(bpl, lc) == ('authors', 'exact match', 125)
    threshold = 875
    assert attempt_merge(bpl, lc, threshold) is True


@pytest.mark.skip(reason="Failed because test data authors do not have `db_name`, may be a sign of a real issue. Also fails on threshold.")
def test_merge2():
    amazon = {'publishers': [u'Collins'], 'isbn_10': ['0002167530'], 'number_of_pages': 287, 'short_title': u'sea birds britain ireland', 'normalized_title': u'sea birds britain ireland', 'full_title': u'Sea Birds Britain Ireland', 'titles': [u'Sea Birds Britain Ireland', u'sea birds britain ireland'], 'publish_date': u'1975',
            'authors': [{'name': 'Stanley Cramp', 'db_name': 'Cramp, Stanley'}]}

    marc = {'publisher': [u'Collins'], 'isbn_10': [u'0002167530'], 'short_title': u'seabirds of britain and i', 'normalized_title': u'seabirds of britain and ireland', 'full_title': u'seabirds of Britain and Ireland', 'titles': [u'seabirds of Britain and Ireland', u'seabirds of britain and ireland'], 'publish_date': '1974', 'authors': [{'db_name': u'Cramp, Stanley.', 'entity_type': 'person', 'name': u'Cramp, Stanley.', 'personal_name': u'Cramp, Stanley.'}], 'source_record_loc': 'marc_records_scriblio_net/part08.dat:61449973:855'}
    threshold = 875
    # build_marc() will place all isbn_ types in the 'isbn' field.
    # compare_author_fields() expects all authors to have a db_name
    assert attempt_merge(build_marc(amazon), build_marc(marc), threshold, debug=True)
