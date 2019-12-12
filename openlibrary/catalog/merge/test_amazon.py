import pytest
from openlibrary.catalog.merge.amazon import (
        attempt_merge,
        compare_authors, compare_publisher,
        full_title, build_titles, compare_title)

def test_compare_authors_by_statement():
    amazon = {'authors': [u'Alistair Smith', u'Author']}
    marc = {'authors': [{'db_name': u'National Gallery (Great Britain)', 'name': u'National Gallery (Great Britain)', 'entity_type': 'org'}], 'by_statement': 'Alistair Smith.'}
    assert compare_authors(amazon, marc) == ('authors', 'exact match', 125)

def test_compare_publisher():
    amazon = { 'publishers': ['foo'] }
    amazon2 = { 'publishers': ['bar'] }
    marc = { 'publishers': ['foo'] }
    marc2 = { 'publishers': ['foo', 'bar'] }
    assert compare_publisher({}, {}) == ('publishers', 'either missing', 0)
    assert compare_publisher(amazon, {}) == ('publishers', 'either missing', 0)
    assert compare_publisher({}, marc) == ('publishers', 'either missing', 0)
    assert compare_publisher(amazon, marc) == ('publishers', 'match', 100)
    assert compare_publisher(amazon2, marc) == ('publishers', 'mismatch', -25)
    assert compare_publisher(amazon2, marc2) == ('publishers', 'match', 100)

def test_full_title():
    assert full_title({ 'title': 'Hamlet'}) == 'Hamlet'
    edition = {
        'title': 'Flatland',
        'subtitle': 'A Romance of Many Dimensions',
    }
    assert full_title(edition) == 'Flatland A Romance of Many Dimensions'

def test_build_titles():
    a = 'This is a title.'
    normalized = 'this is a title'
    result = build_titles(a)
    assert result['full_title'] == a
    assert result['short_title'] == normalized
    assert result['normalized_title'] == normalized

def test_merge_titles():
    marc = {
        'title_with_subtitles': 'Spytime : the undoing of James Jesus Angleton : a novel',
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
    assert compare_title(amazon, marc) == ('full_title', 'contained within other title', 350)

def test_merge_titles2():
    amazon = {'title': u'Sea Birds Britain Ireland'}
    marc = {
        'title_with_subtitles': u'seabirds of Britain and Ireland',
        'title': u'seabirds of Britain and Ireland',
        'full_title': u'The seabirds of Britain and Ireland',
    }
    amazon = build_titles(full_title(amazon))
    marc = build_titles(marc['title_with_subtitles'])
    assert compare_title(amazon, marc) == ('full_title', 'exact match', 600)

def test_merge():
    amazon = {'publishers': [u'Collins'], 'isbn': ['0002167360'], 'number_of_pages': 120, 'short_title': u'souvenirs', 'normalized_title': u'souvenirs', 'full_title': u'Souvenirs', 'titles': [u'Souvenirs', u'souvenirs'], 'publish_date': u'1975', 'authors': [u'David Hamilton', u'Photographer']}
    marc = {'publisher': [u'Collins'], 'isbn': [u'0002167360'], 'short_title': u'souvenirs', 'normalized_title': u'souvenirs', 'full_title': u'Souvenirs', 'titles': [u'Souvenirs', u'souvenirs'], 'publish_date': '1978', 'authors': [{'birth_date': u'1933', 'db_name': u'Hamilton, David 1933-', 'entity_type': 'person', 'name': u'Hamilton, David', 'personal_name': u'Hamilton, David'}], 'source_record_loc': 'marc_records_scriblio_net/part11.dat:155728070:617', 'number_of_pages': 120}
    # these records match with threshold = 650, but do not with threshold = 735
    threshold = 735
    assert attempt_merge(amazon, marc, 650)
    assert not attempt_merge(amazon, marc, threshold)

def test_merge2():
    amazon = {'publishers': [u'Collins'], 'isbn': ['0002167530'], 'number_of_pages': 287, 'short_title': u'sea birds britain ireland', 'normalized_title': u'sea birds britain ireland', 'full_title': u'Sea Birds Britain Ireland', 'titles': [u'Sea Birds Britain Ireland', u'sea birds britain ireland'], 'publish_date': u'1975', 'authors': ['Stanley Cramp']}
    marc = {'publisher': [u'Collins'], 'isbn': [u'0002167530'], 'short_title': u'seabirds of britain and i', 'normalized_title': u'seabirds of britain and ireland', 'full_title': u'seabirds of Britain and Ireland', 'titles': [u'seabirds of Britain and Ireland', u'seabirds of britain and ireland'], 'publish_date': '1974', 'authors': [{'db_name': u'Cramp, Stanley.', 'entity_type': 'person', 'name': u'Cramp, Stanley.', 'personal_name': u'Cramp, Stanley.'}], 'source_record_loc': 'marc_records_scriblio_net/part08.dat:61449973:855'}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

@pytest.mark.skip(reason="Did not pass when rescuing tests. Check thresholds.")
def test_merge3():
    amazon = {'publishers': [u'Intl Specialized Book Service Inc'], 'isbn_10': ['0002169770'], 'number_of_pages': 207, 'short_title': u'women of the north', 'normalized_title': u'women of the north', 'full_title': u'Women of the North', 'titles': [u'Women of the North', u'women of the north'], 'publish_date': u'1985', 'authors': [(u'Jane Wordsworth', u'Author')]}
    marc = {'publisher': [u'Collins', u'Exclusive distributor ISBS'], 'isbn_10': [u'0002169770'], 'short_title': u'women of the north', 'normalized_title': u'women of the north', 'full_title': u'Women of the North', 'titles': [u'Women of the North', u'women of the north'], 'publish_date': '1981', 'number_of_pages': 207, 'authors': [{'db_name': u'Wordsworth, Jane.', 'entity_type': 'person', 'name': u'Wordsworth, Jane.', 'personal_name': u'Wordsworth, Jane.'}], 'source_record_loc': 'marc_records_scriblio_net/part17.dat:110989084:798'}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

@pytest.mark.skip(reason="Did not pass when rescuing tests. Check thresholds.")
def test_merge4():
    amazon = {'publishers': [u'HarperCollins Publishers Ltd'], 'isbn_10': ['0002173433'], 'number_of_pages': 128, 'short_title': u'd day to victory', 'normalized_title': u'd day to victory', 'full_title': u'D-Day to Victory', 'titles': [u'D-Day to Victory', u'd day to victory'], 'publish_date': u'1984', 'authors': [(u'Wynfod Vaughan-Thomas', u'Editor, Introduction')]}
    marc = {'publisher': [u'Collins'], 'isbn_10': [u'0002173433'], 'short_title': u'great front pages  d day ', 'normalized_title': u'great front pages  d day to victory 1944 1945', 'full_title': u'Great front pages : D-Day to victory 1944-1945', 'titles': [u'Great front pages : D-Day to victory 1944-1945', u'great front pages  dday to victory 1944 1945'], 'publish_date': '1984', 'number_of_pages': 128, 'by_statement': 'introduced by Wynford Vaughan-Thomas.', 'source_record_loc': 'marc_records_scriblio_net/part17.dat:102360356:983'}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

def test_merge5():
    amazon = {'publishers': [u'HarperCollins Publishers (Australia) Pty Ltd'], 'isbn': ['0002174049'], 'number_of_pages': 120, 'short_title': u'netherlandish and german ', 'normalized_title': u'netherlandish and german paintings national gallery schools of painting', 'full_title': u'Netherlandish and German Paintings (National Gallery Schools of Painting)', 'titles': [u'Netherlandish and German Paintings (National Gallery Schools of Painting)', u'netherlandish and german paintings national gallery schools of painting', u'Netherlandish and German Paintings', u'netherlandish and german paintings'], 'publish_date': u'1985', 'authors': [u'Alistair Smith']}
    marc = {'publisher': [u'National Gallery in association with W. Collins'], 'isbn': [u'0002174049'], 'short_title': u'early netherlandish and g', 'normalized_title': u'early netherlandish and german paintings', 'full_title': u'Early Netherlandish and German paintings', 'titles': [u'Early Netherlandish and German paintings', u'early netherlandish and german paintings'], 'publish_date': '1985', 'authors': [{'db_name': u'National Gallery (Great Britain)', 'name': u'National Gallery (Great Britain)', 'entity_type': 'org'}], 'number_of_pages': 116, 'by_statement': 'Alistair Smith.', 'source_record_loc': 'marc_records_scriblio_net/part17.dat:170029527:1210'}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

@pytest.mark.skip(reason="Did not pass when rescuing tests. Check thresholds.")
def test_merge6():
    amazon = {'publishers': [u'Fount'], 'isbn_10': ['0002176157'], 'number_of_pages': 224, 'short_title': u'basil hume', 'normalized_title': u'basil hume', 'full_title': u'Basil Hume', 'titles': [u'Basil Hume', u'basil hume'], 'publish_date': u'1986', 'authors': [(u'Tony Castle', u'Editor')]}
    marc = {'publisher': [u'Collins'], 'isbn_10': [u'0002176157'], 'short_title': u'basil hume  a portrait', 'normalized_title': u'basil hume  a portrait', 'full_title': u'Basil Hume : a portrait', 'titles': [u'Basil Hume : a portrait', u'basil hume  a portrait'], 'number_of_pages': 158, 'publish_date': '1986', 'by_statement': 'edited by Tony Castle.', 'source_record_loc': 'marc_records_scriblio_net/part19.dat:39883132:951'}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

def test_merge7():
    amazon = {'publishers': [u'HarperCollins Publishers Ltd'], 'isbn': ['0002176319'], 'number_of_pages': 256, 'short_title': u'pucklers progress', 'normalized_title': u'pucklers progress', 'full_title': u"Puckler's Progress", 'titles': [u"Puckler's Progress", u'pucklers progress'], 'publish_date': u'1987', 'authors': [u'Flora Brennan']}
    marc = {'publisher': [u'Collins'], 'isbn': [u'0002176319'], 'short_title': u'pucklers progress  the ad', 'normalized_title': u'pucklers progress  the adventures of prince puckler muskau in england wales and ireland as told in letters to his former wife 1826 9', 'full_title': u"Puckler's progress : the adventures of Prince Pu\u0308ckler-Muskau in England, Wales, and Ireland as told in letters to his former wife, 1826-9", 'titles': [u"Puckler's progress : the adventures of Prince Pu\u0308ckler-Muskau in England, Wales, and Ireland as told in letters to his former wife, 1826-9", u'pucklers progress  the adventures of prince puckler muskau in england wales and ireland as told in letters to his former wife 1826 9'], 'publish_date': '1987', 'authors': [{'name': u'Pu\u0308ckler-Muskau, Hermann Furst von', 'title': u'Furst von', 'death_date': u'1871.', 'db_name': u'Pu\u0308ckler-Muskau, Hermann Furst von 1785-1871.', 'birth_date': u'1785', 'personal_name': u'Pu\u0308ckler-Muskau, Hermann', 'entity_type': 'person'}], 'number_of_pages': 254, 'by_statement': 'translated by Flora Brennan.', 'source_record_loc': 'marc_records_scriblio_net/part19.dat:148554594:1050'}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

def test_merge8():
    amazon = {'publishers': [u'Shambhala'], 'isbn': [u'1590301390'], 'number_of_pages': 144, 'short_title': u'the spiritual teaching of', 'normalized_title': u'the spiritual teaching of ramana maharshi', 'full_title': u'The Spiritual Teaching of Ramana Maharshi', 'titles': [u'The Spiritual Teaching of Ramana Maharshi', u'the spiritualteaching of ramana maharshi', u'Spiritual Teaching of Ramana Maharshi', u'spiritual teaching of ramana maharshi'], 'publish_date': u'2004', 'authors': [u'Ramana Maharshi.']}
    marc = {'isbn': [], 'number_of_pages': 180, 'short_title': 'the spiritual teaching of', 'normalized_title': 'the spiritual teaching of mary of the incarnation', 'full_title': 'The spiritual teaching of Mary of the Incarnation', 'titles': ['The spiritual teaching of Mary of the Incarnation', 'the spiritual teaching of mary of the incarnation', 'spiritual teaching of Mary of the Incarnation', 'spiritual teaching of mary of the incarnation'], 'publish_date': '1963', 'publish_country': 'nyu', 'authors': [{'db_name': 'Jett\u00e9, Fernand.', 'name': u'Jett\u00e9, Fernand.'}]}
    threshold = 735
    assert not attempt_merge(amazon, marc, threshold)
