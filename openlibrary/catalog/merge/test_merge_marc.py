import pytest
from openlibrary.catalog.merge.merge_marc import attempt_merge, build_marc, build_titles, compare_authors

def test_build_marc():
    # TODO: this is used via add_book.load() ->
    # Needs to be tested.
    pass

def test_build_titles():
    # Used by build_marc()
    a = 'This is a title.'
    normalized = 'this is a title'
    result = build_titles(a)
    assert result['full_title'] == a
    assert result['short_title'] == normalized
    assert result['normalized_title'] == normalized

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
    threshold = 735
    assert attempt_merge(bpl, lc, threshold) is True

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

@pytest.mark.skip(reason="Fails because test data authors do not have `db_name`, may be a sign of a real issue.")
def test_merge2():
    amazon = {'publishers': [u'Collins'], 'isbn_10': ['0002167530'], 'number_of_pages': 287, 'short_title': u'sea birds britain ireland', 'normalized_title': u'sea birds britain ireland', 'full_title': u'Sea Birds Britain Ireland', 'titles': [u'Sea Birds Britain Ireland', u'sea birds britain ireland'], 'publish_date': u'1975',
            'authors': [{'name': u'Stanley Cramp'}]}

    marc = {'publisher': [u'Collins'], 'isbn_10': [u'0002167530'], 'short_title': u'seabirds of britain and i', 'normalized_title': u'seabirds of britain and ireland', 'full_title': u'seabirds of Britain and Ireland', 'titles': [u'seabirds of Britain and Ireland', u'seabirds of britain and ireland'], 'publish_date': '1974', 'authors': [{'db_name': u'Cramp, Stanley.', 'entity_type': 'person', 'name': u'Cramp, Stanley.', 'personal_name': u'Cramp, Stanley.'}], 'source_record_loc': 'marc_records_scriblio_net/part08.dat:61449973:855'}
    threshold = 735
    # build_marc() will place all isbn_ types in the 'isbn' field.
    # compare_author_fields() expects all authors to have a db_name
    assert attempt_merge(build_marc(amazon), build_marc(marc), threshold)
