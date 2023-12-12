import pytest

from openlibrary.catalog.merge.merge import (
    attempt_merge,
    full_title,
    build_titles,
    compare_title,
)

""" These tests seem to be duplicates of those in test_amazon.py,
    which in turn are duplicates of methods that are actually used
    by Open Library in openlibrary.catalog.merge.merge_marc
    Investigate and clean up!
    """


def test_full_title():
    assert full_title({'title': "Hamlet"}) == "Hamlet"
    edition = {
        'title': 'Flatland',
        'subtitle': 'A Romance of Many Dimensions',
    }
    assert full_title(edition) == "Flatland A Romance of Many Dimensions"


def test_merge_titles():
    marc = {
        'title_with_subtitles': (
            'Spytime : the undoing of James Jesus Angleton : a novel'
        ),
        'title': 'Spytime',
        'full_title': 'Spytime : the undoing of James Jesus Angleton : a novel',
    }
    amazon = {
        'subtitle': 'The Undoing oF James Jesus Angleton',
        'title': 'Spytime',
    }

    amazon = build_titles(full_title(amazon))
    marc = build_titles(marc['title_with_subtitles'])
    assert amazon['short_title'] == marc['short_title']
    assert compare_title(amazon, marc) == (
        'full-title',
        'contained within other title',
        350,
    )


def test_merge_titles2():
    amazon = {'title': 'Sea Birds Britain Ireland'}
    marc = {
        'title_with_subtitles': 'seabirds of Britain and Ireland',
        'title': 'seabirds of Britain and Ireland',
        'full_title': 'The seabirds of Britain and Ireland',
    }
    amazon = build_titles(full_title(amazon))
    marc = build_titles(marc['title_with_subtitles'])
    assert compare_title(amazon, marc) == ('full-title', 'exact match', 600)


@pytest.mark.skip(reason="Did not pass when rescuing tests. Check thresholds.")
def test_merge():
    amazon = {
        'publisher': 'Collins',
        'isbn_10': ['0002167360'],
        'number_of_pages': 120,
        'short_title': 'souvenirs',
        'normalized_title': 'souvenirs',
        'full_title': 'Souvenirs',
        'titles': ['Souvenirs', 'souvenirs'],
        'publish_date': '1975',
        'authors': [('David Hamilton', 'Photographer')],
    }
    marc = {
        'publisher': ['Collins'],
        'isbn_10': ['0002167360'],
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

    threshold = 735
    assert attempt_merge(amazon, marc, threshold)


@pytest.mark.skip(reason="Should be tested on openlibrary.catalog.merge.merge_marc.")
def test_merge2():
    amazon = {
        'publisher': 'Collins',
        'isbn_10': ['0002167530'],
        'number_of_pages': 287,
        'short_title': 'sea birds britain ireland',
        'normalized_title': 'sea birds britain ireland',
        'full_title': 'Sea Birds Britain Ireland',
        'titles': ['Sea Birds Britain Ireland', 'sea birds britain ireland'],
        'publish_date': '1975',
        'authors': [('Stanley Cramp', 'Author')],
    }
    marc = {
        'publisher': ['Collins'],
        'isbn_10': ['0002167530'],
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
        'publisher': 'Intl Specialized Book Service Inc',
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
        'publisher': 'HarperCollins Publishers Ltd',
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


@pytest.mark.skip(reason="Should be tested on openlibrary.catalog.merge.merge_marc.")
def test_merge5():
    amazon = {
        'publisher': 'HarperCollins Publishers (Australia) Pty Ltd',
        'isbn_10': ['0002174049'],
        'number_of_pages': 120,
        'short_title': 'netherlandish and german ',
        'normalized_title': (
            'netherlandish and german paintings national gallery schools of painting'
        ),
        'full_title': (
            'Netherlandish and German Paintings (National Gallery Schools of Painting)'
        ),
        'titles': [
            'Netherlandish and German Paintings (National Gallery Schools of Painting)',
            'netherlandish and german paintings national gallery schools of painting',
            'Netherlandish and German Paintings',
            'netherlandish and german paintings',
        ],
        'publish_date': '1985',
        'authors': [('Alistair Smith', 'Author')],
    }
    marc = {
        'publisher': ['National Gallery in association with W. Collins'],
        'isbn_10': ['0002174049'],
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
        'publisher': 'Fount',
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


@pytest.mark.skip(reason="Should be tested on openlibrary.catalog.merge.merge_marc.")
def test_merge7():
    amazon = {
        'publisher': 'HarperCollins Publishers Ltd',
        'isbn_10': ['0002176319'],
        'number_of_pages': 256,
        'short_title': 'pucklers progress',
        'normalized_title': 'pucklers progress',
        'full_title': "Puckler's Progress",
        'titles': ["Puckler's Progress", 'pucklers progress'],
        'publish_date': '1987',
        'authors': [('Flora Brennan', 'Editor')],
    }
    marc = {
        'publisher': ['Collins'],
        'isbn_10': ['0002176319'],
        'short_title': 'pucklers progress  the ad',
        'normalized_title': (
            'pucklers progress  the adventures of prince puckler muskau in england '
            'wales and ireland as told in letters to his former wife 1826 9'
        ),
        'full_title': (
            "Puckler's progress : the adventures of Prince Pu\u0308ckler-Muskau in "
            "England, Wales, and Ireland as told in letters to his former wife, 1826-9"
        ),
        'titles': [
            "Puckler's progress : the adventures of Prince Pu\u0308ckler-Muskau in "
            "England, Wales, and Ireland as told in letters to his former wife, 1826-9",
            'pucklers progress  the adventures of prince puckler muskau in england '
            'wales and ireland as told in letters to his former wife 1826 9',
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
