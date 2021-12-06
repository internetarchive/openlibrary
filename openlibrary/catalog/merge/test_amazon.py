"""
    Deprecated tests. These exactly duplicate tests in
    openlibrary/catalog/merge/test_merge.py, which are
    preferred to these.

    Additionally test_merge.py nearly matches the code in
    openlibrary/catalog/merge/test_merge_marc.py, which tests
    the code actually used, called from
    openlibrary.catalog.add_book.match
    Unfortunately test tests of the current code are the weakest.
"""

import pytest
from openlibrary.catalog.merge.amazon import attempt_merge

pytestmark = pytest.mark.skip('Skip Legacy Amazon record matching tests.')


def test_merge():
    amazon = {
        'publishers': ['Collins'],
        'isbn': ['0002167360'],
        'number_of_pages': 120,
        'short_title': 'souvenirs',
        'normalized_title': 'souvenirs',
        'full_title': 'Souvenirs',
        'titles': ['Souvenirs', 'souvenirs'],
        'publish_date': '1975',
        'authors': ['David Hamilton', 'Photographer'],
    }
    marc = {
        'publisher': ['Collins'],
        'isbn': ['0002167360'],
        'short_title': 'souvenirs',
        'normalized_title': 'souvenirs',
        'full_title': 'Souvenirs',
        'titles': ['Souvenirs', 'souvenirs'],
        'publish_date': '1978',
        'authors': [
            {
                'birth_date': '1933',
                'db_name': 'Hamilton, David 1933-',
                'entity_type': 'person',
                'name': 'Hamilton, David',
                'personal_name': 'Hamilton, David',
            }
        ],
        'source_record_loc': 'marc_records_scriblio_net/part11.dat:155728070:617',
        'number_of_pages': 120,
    }
    # these records match with threshold = 650, but do not with threshold = 735
    threshold = 735
    assert attempt_merge(amazon, marc, 650)
    assert not attempt_merge(amazon, marc, threshold)


def test_merge2():
    amazon = {
        'publishers': ['Collins'],
        'isbn': ['0002167530'],
        'number_of_pages': 287,
        'short_title': 'sea birds britain ireland',
        'normalized_title': 'sea birds britain ireland',
        'full_title': 'Sea Birds Britain Ireland',
        'titles': ['Sea Birds Britain Ireland', 'sea birds britain ireland'],
        'publish_date': '1975',
        'authors': ['Stanley Cramp'],
    }
    marc = {
        'publisher': ['Collins'],
        'isbn': ['0002167530'],
        'short_title': 'seabirds of britain and i',
        'normalized_title': 'seabirds of britain and ireland',
        'full_title': 'seabirds of Britain and Ireland',
        'titles': [
            'seabirds of Britain and Ireland',
            'seabirds of britain and ireland',
        ],
        'publish_date': '1974',
        'authors': [
            {
                'db_name': 'Cramp, Stanley.',
                'entity_type': 'person',
                'name': 'Cramp, Stanley.',
                'personal_name': 'Cramp, Stanley.',
            }
        ],
        'source_record_loc': 'marc_records_scriblio_net/part08.dat:61449973:855',
    }
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)


@pytest.mark.skip(reason="Did not pass when rescuing tests. Check thresholds.")
def test_merge3():
    amazon = {
        'publishers': ['Intl Specialized Book Service Inc'],
        'isbn_10': ['0002169770'],
        'number_of_pages': 207,
        'short_title': 'women of the north',
        'normalized_title': 'women of the north',
        'full_title': 'Women of the North',
        'titles': ['Women of the North', 'women of the north'],
        'publish_date': '1985',
        'authors': [('Jane Wordsworth', 'Author')],
    }
    marc = {
        'publisher': ['Collins', 'Exclusive distributor ISBS'],
        'isbn_10': ['0002169770'],
        'short_title': 'women of the north',
        'normalized_title': 'women of the north',
        'full_title': 'Women of the North',
        'titles': ['Women of the North', 'women of the north'],
        'publish_date': '1981',
        'number_of_pages': 207,
        'authors': [
            {
                'db_name': 'Wordsworth, Jane.',
                'entity_type': 'person',
                'name': 'Wordsworth, Jane.',
                'personal_name': 'Wordsworth, Jane.',
            }
        ],
        'source_record_loc': 'marc_records_scriblio_net/part17.dat:110989084:798',
    }
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)


@pytest.mark.skip(reason="Did not pass when rescuing tests. Check thresholds.")
def test_merge4():
    amazon = {
        'publishers': ['HarperCollins Publishers Ltd'],
        'isbn_10': ['0002173433'],
        'number_of_pages': 128,
        'short_title': 'd day to victory',
        'normalized_title': 'd day to victory',
        'full_title': 'D-Day to Victory',
        'titles': ['D-Day to Victory', 'd day to victory'],
        'publish_date': '1984',
        'authors': [('Wynfod Vaughan-Thomas', 'Editor, Introduction')],
    }
    marc = {
        'publisher': ['Collins'],
        'isbn_10': ['0002173433'],
        'short_title': 'great front pages  d day ',
        'normalized_title': 'great front pages  d day to victory 1944 1945',
        'full_title': 'Great front pages : D-Day to victory 1944-1945',
        'titles': [
            'Great front pages : D-Day to victory 1944-1945',
            'great front pages  dday to victory 1944 1945',
        ],
        'publish_date': '1984',
        'number_of_pages': 128,
        'by_statement': 'introduced by Wynford Vaughan-Thomas.',
        'source_record_loc': 'marc_records_scriblio_net/part17.dat:102360356:983',
    }
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)


def test_merge5():
    amazon = {
        'publishers': ['HarperCollins Publishers (Australia) Pty Ltd'],
        'isbn': ['0002174049'],
        'number_of_pages': 120,
        'short_title': 'netherlandish and german ',
        'normalized_title': 'netherlandish and german paintings national gallery schools of painting',
        'full_title': 'Netherlandish and German Paintings (National Gallery Schools of Painting)',
        'titles': [
            'Netherlandish and German Paintings (National Gallery Schools of Painting)',
            'netherlandish and german paintings national gallery schools of painting',
            'Netherlandish and German Paintings',
            'netherlandish and german paintings',
        ],
        'publish_date': '1985',
        'authors': ['Alistair Smith'],
    }
    marc = {
        'publisher': ['National Gallery in association with W. Collins'],
        'isbn': ['0002174049'],
        'short_title': 'early netherlandish and g',
        'normalized_title': 'early netherlandish and german paintings',
        'full_title': 'Early Netherlandish and German paintings',
        'titles': [
            'Early Netherlandish and German paintings',
            'early netherlandish and german paintings',
        ],
        'publish_date': '1985',
        'authors': [
            {
                'db_name': 'National Gallery (Great Britain)',
                'name': 'National Gallery (Great Britain)',
                'entity_type': 'org',
            }
        ],
        'number_of_pages': 116,
        'by_statement': 'Alistair Smith.',
        'source_record_loc': 'marc_records_scriblio_net/part17.dat:170029527:1210',
    }
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)


@pytest.mark.skip(reason="Did not pass when rescuing tests. Check thresholds.")
def test_merge6():
    amazon = {
        'publishers': ['Fount'],
        'isbn_10': ['0002176157'],
        'number_of_pages': 224,
        'short_title': 'basil hume',
        'normalized_title': 'basil hume',
        'full_title': 'Basil Hume',
        'titles': ['Basil Hume', 'basil hume'],
        'publish_date': '1986',
        'authors': [('Tony Castle', 'Editor')],
    }
    marc = {
        'publisher': ['Collins'],
        'isbn_10': ['0002176157'],
        'short_title': 'basil hume  a portrait',
        'normalized_title': 'basil hume  a portrait',
        'full_title': 'Basil Hume : a portrait',
        'titles': ['Basil Hume : a portrait', 'basil hume  a portrait'],
        'number_of_pages': 158,
        'publish_date': '1986',
        'by_statement': 'edited by Tony Castle.',
        'source_record_loc': 'marc_records_scriblio_net/part19.dat:39883132:951',
    }
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)


def test_merge7():
    amazon = {
        'publishers': ['HarperCollins Publishers Ltd'],
        'isbn': ['0002176319'],
        'number_of_pages': 256,
        'short_title': 'pucklers progress',
        'normalized_title': 'pucklers progress',
        'full_title': "Puckler's Progress",
        'titles': ["Puckler's Progress", 'pucklers progress'],
        'publish_date': '1987',
        'authors': ['Flora Brennan'],
    }
    marc = {
        'publisher': ['Collins'],
        'isbn': ['0002176319'],
        'short_title': 'pucklers progress  the ad',
        'normalized_title': 'pucklers progress  the adventures of prince puckler muskau in england wales and ireland as told in letters to his former wife 1826 9',
        'full_title': "Puckler's progress : the adventures of Prince Pu\u0308ckler-Muskau in England, Wales, and Ireland as told in letters to his former wife, 1826-9",
        'titles': [
            "Puckler's progress : the adventures of Prince Pu\u0308ckler-Muskau in England, Wales, and Ireland as told in letters to his former wife, 1826-9",
            'pucklers progress  the adventures of prince puckler muskau in england wales and ireland as told in letters to his former wife 1826 9',
        ],
        'publish_date': '1987',
        'authors': [
            {
                'name': 'Pu\u0308ckler-Muskau, Hermann Furst von',
                'title': 'Furst von',
                'death_date': '1871.',
                'db_name': 'Pu\u0308ckler-Muskau, Hermann Furst von 1785-1871.',
                'birth_date': '1785',
                'personal_name': 'Pu\u0308ckler-Muskau, Hermann',
                'entity_type': 'person',
            }
        ],
        'number_of_pages': 254,
        'by_statement': 'translated by Flora Brennan.',
        'source_record_loc': 'marc_records_scriblio_net/part19.dat:148554594:1050',
    }
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)


def test_merge8():
    amazon = {
        'publishers': ['Shambhala'],
        'isbn': ['1590301390'],
        'number_of_pages': 144,
        'short_title': 'the spiritual teaching of',
        'normalized_title': 'the spiritual teaching of ramana maharshi',
        'full_title': 'The Spiritual Teaching of Ramana Maharshi',
        'titles': [
            'The Spiritual Teaching of Ramana Maharshi',
            'the spiritualteaching of ramana maharshi',
            'Spiritual Teaching of Ramana Maharshi',
            'spiritual teaching of ramana maharshi',
        ],
        'publish_date': '2004',
        'authors': ['Ramana Maharshi.'],
    }
    marc = {
        'isbn': [],
        'number_of_pages': 180,
        'short_title': 'the spiritual teaching of',
        'normalized_title': 'the spiritual teaching of mary of the incarnation',
        'full_title': 'The spiritual teaching of Mary of the Incarnation',
        'titles': [
            'The spiritual teaching of Mary of the Incarnation',
            'the spiritual teaching of mary of the incarnation',
            'spiritual teaching of Mary of the Incarnation',
            'spiritual teaching of mary of the incarnation',
        ],
        'publish_date': '1963',
        'publish_country': 'nyu',
        'authors': [
            {'db_name': 'Jett\u00e9, Fernand.', 'name': 'Jett\u00e9, Fernand.'}
        ],
    }
    threshold = 735
    assert not attempt_merge(amazon, marc, threshold)
