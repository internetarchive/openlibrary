from merge_marc import attempt_merge, build_marc, compare_authors

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
