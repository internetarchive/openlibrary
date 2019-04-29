from __future__ import print_function
from load_book import build_query, InvalidLanguage
from . import load, RequiredField, build_pool, add_db_name
from .. import add_book
import os
import pytest
from infogami.infobase.core import Text
from openlibrary.catalog.merge.merge_marc import build_marc
from openlibrary.catalog.marc.parse import read_edition
from openlibrary.catalog.marc.marc_binary import MarcBinary, BadLength, BadMARC
from merge import try_merge
from copy import deepcopy
from urllib import urlopen
from collections import defaultdict

def open_test_data(filename):
    """Returns a file handle to file with specified filename inside test_data directory.
    """
    root = os.path.dirname(__file__)
    fullpath = os.path.join(root, 'test_data', filename)
    return open(fullpath)

@pytest.fixture
def add_languages(mock_site):
    languages = [
        ('eng', 'English'),
        ('spa', 'Spanish'),
        ('fre', 'French'),
        ('yid', 'Yiddish'),
    ]
    for code, name in languages:
        mock_site.save({
            'key': '/languages/' + code,
            'name': name,
            'type': {'key': '/type/language'},
        })

@pytest.fixture
def ia_writeback(monkeypatch):
    """Prevent ia writeback from making live requests.
    """
    monkeypatch.setattr(add_book, 'update_ia_metadata_for_ol_edition', lambda olid: {})

def test_build_query(add_languages):
    rec = {
        'title': 'magic',
        'languages': ['eng', 'fre'],
        'authors': [{}],
        'description': 'test',
    }
    q = build_query(rec)
    assert q['title'] == 'magic'
    assert q['description'] == {'type': '/type/text', 'value': 'test'}
    assert q['type'] == {'key': '/type/edition'}
    assert q['languages'] == [{'key': '/languages/eng'}, {'key': '/languages/fre'}]

    pytest.raises(InvalidLanguage, build_query, {'languages': ['wtf']})

def test_load_without_required_field():
    rec = {'ocaid': 'test item'}
    pytest.raises(RequiredField, load, {'ocaid': 'test_item'})

def test_load_test_item(mock_site, add_languages, ia_writeback):
    rec = {
        'ocaid': 'test_item',
        'source_records': ['ia:test_item'],
        'title': 'Test item',
        'languages': ['eng'],
    }
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    e = mock_site.get(reply['edition']['key'])
    assert e.type.key == '/type/edition'
    assert e.title == 'Test item'
    assert e.ocaid == 'test_item'
    assert e.source_records == ['ia:test_item']
    l = e.languages
    assert len(l) == 1 and l[0].key == '/languages/eng'

    assert reply['work']['status'] == 'created'
    w = mock_site.get(reply['work']['key'])
    assert w.title == 'Test item'
    assert w.type.key == '/type/work'

def test_load_with_subjects(mock_site, ia_writeback):
    rec = {
        'ocaid': 'test_item',
        'title': 'Test item',
        'subjects': ['Protected DAISY', 'In library'],
        'source_records': 'ia:test_item',
    }
    reply = load(rec)
    assert reply['success'] is True
    w = mock_site.get(reply['work']['key'])
    assert w.title == 'Test item'
    assert w.subjects == ['Protected DAISY', 'In library']

def test_load_with_new_author(mock_site, ia_writeback):
    rec = {
        'ocaid': 'test_item',
        'title': 'Test item',
        'authors': [{'name': 'John Doe'}],
        'source_records': 'ia:test_item',
    }
    reply = load(rec)
    assert reply['success'] is True
    w = mock_site.get(reply['work']['key'])
    assert reply['authors'][0]['status'] == 'created'
    assert reply['authors'][0]['name'] == 'John Doe'
    akey1 = reply['authors'][0]['key']
    assert akey1 == '/authors/OL1A'
    a = mock_site.get(akey1)
    assert w.authors
    assert a.type.key == '/type/author'

    # Tests an existing author is modified if an Author match is found, and more data is provided
    # This represents an edition of another work by the above author.
    rec = {
        'ocaid': 'test_item1b',
        'title': 'Test item1b',
        'authors': [{'name': 'Doe, John', 'entity_type': 'person'}],
        'source_records': 'ia:test_item1b',
    }
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    assert reply['work']['status'] == 'created'
    assert reply['authors'][0]['status'] == 'modified'
    akey2 = reply['authors'][0]['key']
    assert akey1 == akey2 == '/authors/OL1A'

    # Tests same title with different ocaid and author is not overwritten
    rec = {
        'ocaid': 'test_item2',
        'title': 'Test item',
        'authors': [{'name': 'James Smith'}],
        'source_records': 'ia:test_item2',
    }
    reply = load(rec)
    akey3 = reply['authors'][0]['key']
    assert akey3 == '/authors/OL2A'
    assert reply['authors'][0]['status'] == 'created'
    assert reply['work']['status'] == 'created'
    assert reply['edition']['status'] == 'created'
    w = mock_site.get(reply['work']['key'])
    e = mock_site.get(reply['edition']['key'])
    assert e.ocaid == 'test_item2'
    assert len(w.authors) == 1
    assert len(e.authors) == 1

def test_duplicate_ia_book(mock_site, add_languages, ia_writeback):
    rec = {
        'ocaid': 'test_item',
        'source_records': ['ia:test_item'],
        'title': 'Test item',
        'languages': ['eng'],
    }
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    e = mock_site.get(reply['edition']['key'])
    assert e.type.key == '/type/edition'
    assert e.source_records == ['ia:test_item']

    rec = {
        'ocaid': 'test_item',
        'source_records': ['ia:test_item'],
        # Titles MUST match to be considered the same
        'title': 'Test item',
        'languages': ['fre'],
    }
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'matched'

def test_from_marc_3(mock_site, add_languages):
    ia = 'treatiseonhistor00dixo'
    data = open_test_data(ia + '_meta.mrc').read()
    assert len(data) == int(data[:5])
    rec = read_edition(MarcBinary(data))
    rec['source_records'] = ['ia:' + ia]
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    e = mock_site.get(reply['edition']['key'])
    assert e.type.key == '/type/edition'

def test_from_marc_2(mock_site, add_languages):
    ia = 'roadstogreatness00gall'
    data = open_test_data(ia + '_meta.mrc').read()
    assert len(data) == int(data[:5])
    rec = read_edition(MarcBinary(data))
    rec['source_records'] = ['ia:' + ia]
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    e = mock_site.get(reply['edition']['key'])
    assert e.type.key == '/type/edition'
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'matched'

def test_from_marc(mock_site, add_languages):
    ia = 'flatlandromanceo00abbouoft'
    data = open_test_data(ia + '_meta.mrc').read()
    assert len(data) == int(data[:5])
    rec = read_edition(MarcBinary(data))
    reply = load(rec)
    assert reply['success'] is True
    akey1 = reply['authors'][0]['key']
    a = mock_site.get(akey1)
    assert a.type.key == '/type/author'
    assert a.name == 'Edwin Abbott Abbott'
    assert a.birth_date == '1838'
    assert a.death_date == '1926'

def test_from_marc_fields(mock_site, add_languages):
    ia = 'isbn_9781419594069'
    data = open_test_data(ia + '_meta.mrc').read()
    rec = read_edition(MarcBinary(data))
    rec['source_records'] = ['ia:' + ia]
    reply = load(rec)
    assert reply['success'] is True
    # author from 100
    assert reply['authors'][0]['name'] == 'Adam Weiner'

    edition = mock_site.get(reply['edition']['key'])
    # Publish place, publisher, & publish date - 260$a, $b, $c
    assert edition['publishers'][0] == 'Kaplan Publishing'
    assert edition['publish_date'] == '2007'
    assert edition['publish_places'][0] == 'New York'
    # Pagination 300
    assert edition['number_of_pages'] == 264
    assert edition['pagination'] == 'viii, 264 p.'
    # 8 subjects, 650
    assert len(edition['subjects']) == 8
    assert edition['subjects'] == [u'Action and adventure films',
                                   u'Miscellanea',
                                   u'Physics',
                                   u'Cinematography',
                                   u'Special effects',
                                   u'Physics in motion pictures',
                                   u'Science fiction films',
                                   u'Popular works']
    # Edition description from 520
    desc = 'Explains the basic laws of physics, covering such topics as mechanics, forces, and energy, while deconstructing famous scenes and stunts from motion pictures, including "Apollo 13" and "Titanic," to determine if they are possible.'
    assert isinstance(edition['description'], Text)
    assert edition['description'] == desc
    # Work description from 520
    #work = mock_site.get(reply['work']['key'])
    #assert work['description'] == desc

def test_build_pool(mock_site):
    assert build_pool({'title': 'test'}) == {}
    etype = '/type/edition'
    ekey = mock_site.new_key(etype)
    e = {
        'title': 'test',
        'type': {'key': etype},
        'lccn': ['123'],
        'oclc_numbers': ['456'],
        'ocaid': 'test00test',
        'key': ekey,
    }

    mock_site.save(e)
    pool = build_pool(e)
    assert pool == {
        'lccn': ['/books/OL1M'],
        'oclc_numbers': ['/books/OL1M'],
        'title': ['/books/OL1M'],
        'ocaid': ['/books/OL1M']
    }

    pool = build_pool({'lccn': ['234'], 'oclc_numbers': ['456'], 'title': 'test', 'ocaid': 'test00test'})
    assert pool == { 'oclc_numbers': ['/books/OL1M'], 'title': ['/books/OL1M'], 'ocaid': ['/books/OL1M'] }

def test_try_merge(mock_site):
    rec = {
        'title': 'Test item',
        'lccn': ['123'],
        'authors': [{'name': 'Smith, John', 'birth_date': '1980'}],
        'source_records': ['ia:test_item'],
    }
    reply = load(rec)
    ekey = reply['edition']['key']
    e = mock_site.get(ekey)

    rec['full_title'] = rec['title']
    e1 = build_marc(rec)
    add_db_name(e1)
    result = try_merge(e1, ekey, e)
    assert result is True

def test_load_multiple(mock_site):
    rec = {
        'title': 'Test item',
        'lccn': ['123'],
        'source_records': ['ia:test_item'],
        'authors': [{'name': 'Smith, John', 'birth_date': '1980'}],
    }
    reply = load(rec)
    assert reply['success'] is True
    ekey1 = reply['edition']['key']

    reply = load(rec)
    assert reply['success'] is True
    ekey2 = reply['edition']['key']
    assert ekey1 == ekey2

    reply = load({'title': 'Test item', 'source_records': ['ia:test_item2'], 'lccn': ['456']})
    assert reply['success'] is True
    ekey3 = reply['edition']['key']
    assert ekey3 != ekey1

    reply = load(rec)
    assert reply['success'] is True
    ekey4 = reply['edition']['key']

    assert ekey1 == ekey2 == ekey4

def test_add_db_name():
    authors = [
        {'name': 'Smith, John' },
        {'name': 'Smith, John', 'date': '1950' },
        {   'name': 'Smith, John',
            'birth_date': '1895',
            'death_date': '1964' },
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

def test_from_marc(mock_site, add_languages):
    ia = 'coursepuremath00hardrich'
    marc = MarcBinary(open_test_data(ia + '_meta.mrc').read())
    rec = read_edition(marc)
    rec['source_records'] = ['ia:' + ia]
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'matched'

    ia = 'flatlandromanceo00abbouoft'
    marc = MarcBinary(open_test_data(ia + '_meta.mrc').read())

    rec = read_edition(marc)
    rec['source_records'] = ['ia:' + ia]
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'matched'

def test_real_example(mock_site, add_languages):
    src = 'v38.i37.records.utf8--16478504-1254'
    marc = MarcBinary(open_test_data(src).read())
    rec = read_edition(marc)
    rec['source_records'] = ['marc:' + src]
    reply = load(rec)
    assert reply['success'] is True
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'matched'

    src = 'v39.i28.records.utf8--5362776-1764'
    marc = MarcBinary(open_test_data(src).read())
    rec = read_edition(marc)
    rec['source_records'] = ['marc:' + src]
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'modified'

def test_missing_ocaid(mock_site, add_languages, ia_writeback):
    ia = 'descendantsofhug00cham'
    src = ia + '_meta.mrc'
    marc = MarcBinary(open_test_data(src).read())
    rec = read_edition(marc)
    rec['source_records'] = ['marc:testdata.mrc']
    reply = load(rec)
    assert reply['success'] is True
    rec['source_records'] = ['ia:' + ia]
    rec['ocaid'] = ia
    reply = load(rec)
    assert reply['success'] is True
    e = mock_site.get(reply['edition']['key'])
    assert e.ocaid == ia
    assert 'ia:' + ia in e.source_records

def test_extra_author(mock_site, add_languages):
    mock_site.save({
        "name": "Hubert Howe Bancroft",
        "death_date": "1918.",
        "alternate_names": ["HUBERT HOWE BANCROFT", "Hubert Howe Bandcroft"],
        "key": "/authors/OL563100A",
        "birth_date": "1832",
        "personal_name": "Hubert Howe Bancroft",
        "type": {"key": "/type/author"},
    })

    mock_site.save({
        "title": "The works of Hubert Howe Bancroft",
        "covers": [6060295, 5551343],
        "first_sentence": {"type": "/type/text", "value": "When it first became known to Europe that a new continent had been discovered, the wise men, philosophers, and especially the learned ecclesiastics, were sorely perplexed to account for such a discovery."},
        "subject_places": ["Alaska", "America", "Arizona", "British Columbia", "California", "Canadian Northwest", "Central America", "Colorado", "Idaho", "Mexico", "Montana", "Nevada", "New Mexico", "Northwest Coast of North America", "Northwest boundary of the United States", "Oregon", "Pacific States", "Texas", "United States", "Utah", "Washington (State)", "West (U.S.)", "Wyoming"],
        "excerpts": [{"excerpt": "When it first became known to Europe that a new continent had been discovered, the wise men, philosophers, and especially the learned ecclesiastics, were sorely perplexed to account for such a discovery."}],
        "first_publish_date": "1882",
        "key": "/works/OL3421434W",
        "authors": [{"type": {"key": "/type/author_role"}, "author": {"key": "/authors/OL563100A"}}],
        "subject_times": ["1540-1810", "1810-1821", "1821-1861", "1821-1951", "1846-1850", "1850-1950", "1859-", "1859-1950", "1867-1910", "1867-1959", "1871-1903", "Civil War, 1861-1865", "Conquest, 1519-1540", "European intervention, 1861-1867", "Spanish colony, 1540-1810", "To 1519", "To 1821", "To 1846", "To 1859", "To 1867", "To 1871", "To 1889", "To 1912", "Wars of Independence, 1810-1821"],
        "type": {"key": "/type/work"},
        "subjects": ["Antiquities", "Archaeology", "Autobiography", "Bibliography", "California Civil War, 1861-1865", "Comparative Literature", "Comparative civilization", "Courts", "Description and travel", "Discovery and exploration", "Early accounts to 1600", "English essays", "Ethnology", "Foreign relations", "Gold discoveries", "Historians", "History", "Indians", "Indians of Central America", "Indians of Mexico", "Indians of North America", "Languages", "Law", "Mayas", "Mexican War, 1846-1848", "Nahuas", "Nahuatl language", "Oregon question", "Political aspects of Law", "Politics and government", "Religion and mythology", "Religions", "Social life and customs", "Spanish", "Vigilance committees", "Writing", "Zamorano 80", "Accessible book", "Protected DAISY"]
    })

    ia = 'workshuberthowe00racegoog'
    src = ia + '_meta.mrc'
    marc = MarcBinary(open_test_data(src).read())
    rec = read_edition(marc)
    rec['source_records'] = ['ia:' + ia]

    reply = load(rec)
    assert reply['success'] is True

    w = mock_site.get(reply['work']['key'])

    reply = load(rec)
    assert reply['success'] is True
    w = mock_site.get(reply['work']['key'])
    assert len(w['authors']) == 1

def test_missing_source_records(mock_site, add_languages):
    mock_site.save({
        'key': '/authors/OL592898A',
        'name': 'Michael Robert Marrus',
        'personal_name': 'Michael Robert Marrus',
        'type': { 'key': '/type/author' }
    })

    mock_site.save({
        'authors': [{'author': '/authors/OL592898A', 'type': { 'key': '/type/author_role' }}],
        'key': '/works/OL16029710W',
        'subjects': ['Nuremberg Trial of Major German War Criminals, Nuremberg, Germany, 1945-1946', 'Protected DAISY', 'Lending library'],
        'title': 'The Nuremberg war crimes trial, 1945-46',
        'type': { 'key': '/type/work' },
    })

    mock_site.save({
        "number_of_pages": 276,
        "subtitle": "a documentary history",
        "series": ["The Bedford series in history and culture"],
        "covers": [6649715, 3865334, 173632],
        "lc_classifications": ["D804.G42 N87 1997"],
        "ocaid": "nurembergwarcrim00marr",
        "contributions": ["Marrus, Michael Robert."],
        "uri_descriptions": ["Book review (H-Net)"],
        "title": "The Nuremberg war crimes trial, 1945-46",
        "languages": [{"key": "/languages/eng"}],
        "subjects": ["Nuremberg Trial of Major German War Criminals, Nuremberg, Germany, 1945-1946"],
        "publish_country": "mau", "by_statement": "[compiled by] Michael R. Marrus.",
        "type": {"key": "/type/edition"},
        "uris": ["http://www.h-net.org/review/hrev-a0a6c9-aa"],
        "publishers": ["Bedford Books"],
        "ia_box_id": ["IA127618"],
        "key": "/books/OL1023483M",
        "authors": [{"key": "/authors/OL592898A"}],
        "publish_places": ["Boston"],
        "pagination": "xi, 276 p. :",
        "lccn": ["96086777"],
        "notes": {"type": "/type/text", "value": "Includes bibliographical references (p. 262-268) and index."},
        "identifiers": {"goodreads": ["326638"], "librarything": ["1114474"]},
        "url": ["http://www.h-net.org/review/hrev-a0a6c9-aa"],
        "isbn_10": ["031216386X", "0312136919"],
        "publish_date": "1997",
        "works": [{"key": "/works/OL16029710W"}]
    })

    ia = 'nurembergwarcrim1997marr'
    src = ia + '_meta.mrc'
    marc = MarcBinary(open_test_data(src).read())
    rec = read_edition(marc)
    rec['source_records'] = ['ia:' + ia]

    reply = load(rec)
    assert reply['success'] is True
    e = mock_site.get(reply['edition']['key'])
    assert 'source_records' in e

def test_no_extra_author(mock_site, add_languages):
    author = {
        "name": "Paul Michael Boothe",
        "key": "/authors/OL1A",
        "type": {"key": "/type/author"},
    }
    mock_site.save(author)

    work = {
        "title": "A Separate Pension Plan for Alberta",
        "covers": [1644794],
        "key": "/works/OL1W",
        "authors": [{"type": "/type/author_role", "author": {"key": "/authors/OL1A"}}],
        "type": {"key": "/type/work"},
    }
    mock_site.save(work)

    edition = {
        "number_of_pages": 90,
        "subtitle": "Analysis and Discussion (Western Studies in Economic Policy, No. 5)",
        "weight": "6.2 ounces",
        "covers": [1644794],
        "latest_revision": 6,
        "title": "A Separate Pension Plan for Alberta",
        "languages": [{"key": "/languages/eng"}],
        "subjects": ["Economics", "Alberta", "Political Science / State & Local Government", "Government policy", "Old age pensions", "Pensions", "Social security"],
        "type": {"key": "/type/edition"},
        "physical_dimensions": "9 x 6 x 0.2 inches",
        "publishers": ["The University of Alberta Press"],
        "physical_format": "Paperback",
        "key": "/books/OL1M",
        "authors": [{"key": "/authors/OL2894448A"}],
        "identifiers": {"goodreads": ["4340973"], "librarything": ["5580522"]},
        "isbn_13": ["9780888643513"],
        "isbn_10": ["0888643519"],
        "publish_date": "May 1, 2000",
        "works": [{"key": "/works/OL1W"}]
    }
    mock_site.save(edition)

    src = 'v39.i34.records.utf8--186503-1413'
    marc = MarcBinary(open_test_data(src).read())
    rec = read_edition(marc)
    rec['source_records'] = ['marc:' + src]
    reply = load(rec)
    assert reply['success'] is True

    a = mock_site.get(reply['authors'][0]['key'])

    assert reply['authors'][0]['key'] == author['key']
    assert reply['edition']['key'] == edition['key']
    assert reply['work']['key'] == work['key']

    e = mock_site.get(reply['edition']['key'])
    w = mock_site.get(reply['work']['key'])
    assert 'source_records' in e
    assert len(e['authors']) == 1
    assert len(w['authors']) == 1

def test_don_quixote(mock_site):
    """
    All of these items are by 'Miguel de Cervantes Saavedra',
    only one Author should be created. Some items have bad
    MARC length, others are missing binary MARC altogether
    and raise BadMARC exceptions.
    """
    pytest.skip("This test make live requests to archive.org")

    dq = [u'lifeexploitsofin01cerv', u'cu31924096224518',
        u'elingeniosedcrit04cerv', u'ingeniousgentlem01cervuoft',
        u'historyofingenio01cerv', u'lifeexploitsofin02cerviala',
        u'elingeniosohidal03cervuoft', u'nybc209000', u'elingeniosohidal11cerv',
        u'elingeniosohidal01cervuoft', u'elingeniosoh01cerv',
        u'donquixotedelama00cerviala', u'1896elingeniosohid02cerv',
        u'ingeniousgentlem04cervuoft', u'cu31924027656978', u'histoiredeladmir01cerv',
        u'donquijotedelama04cerv', u'cu31924027657075', u'donquixotedelama03cervuoft',
        u'aventurasdedonqu00cerv', u'p1elingeniosohid03cerv',
        u'geshikhefundonik01cervuoft', u'historyofvalorou02cerviala',
        u'ingeniousgentlem01cerv', u'donquixotedelama01cervuoft',
        u'ingeniousgentlem0195cerv', u'firstpartofdelig00cervuoft',
        u'p4elingeniosohid02cerv', u'donquijote00cervuoft', u'cu31924008863924',
        u'c2elingeniosohid02cerv', u'historyofvalorou03cerviala',
        u'historyofingenio01cerviala', u'historyadventure00cerv',
        u'elingeniosohidal00cerv', u'lifeexploitsofin01cervuoft',
        u'p2elingeniosohid05cerv', u'nybc203136', u'elingeniosohidal00cervuoft',
        u'donquixotedelama02cervuoft', u'lingnieuxcheva00cerv',
        u'ingeniousgentlem03cerv', u'vidayhechosdeli00siscgoog',
        u'lifeandexploits01jarvgoog', u'elingeniosohida00puiggoog',
        u'elingeniosohida00navagoog', u'donquichottedel02florgoog',
        u'historydonquixo00cogoog', u'vidayhechosdeli01siscgoog',
        u'elingeniosohida28saavgoog', u'historyvalorous00brangoog',
        u'elingeniosohida01goog', u'historyandadven00unkngoog',
        u'historyvalorous01goog', u'ingeniousgentle11saavgoog',
        u'elingeniosohida10saavgoog', u'adventuresdonqu00jarvgoog',
        u'historydonquixo04saavgoog', u'lingnieuxcheval00rouxgoog',
        u'elingeniosohida19saavgoog', u'historyingeniou00lalagoog',
        u'elingeniosohida00ormsgoog', u'historyandadven01smolgoog',
        u'elingeniosohida27saavgoog', u'elingeniosohida21saavgoog',
        u'historyingeniou00mottgoog', u'historyingeniou03unkngoog',
        u'lifeandexploits00jarvgoog', u'ingeniousgentle00conggoog',
        u'elingeniosohida00quixgoog', u'elingeniosohida01saavgoog',
        u'donquixotedelam02saavgoog', u'adventuresdonqu00gilbgoog',
        u'historyingeniou02saavgoog', u'donquixotedelam03saavgoog',
        u'elingeniosohida00ochogoog', u'historyingeniou08mottgoog',
        u'lifeandexploits01saavgoog', u'firstpartdeligh00shelgoog',
        u'elingeniosohida00castgoog', u'elingeniosohida01castgoog',
        u'adventofdonquixo00cerv', u'portablecervante00cerv',
        u'firstpartofdelig14cerv', u'donquixotemanofl00cerv',
        u'firstpartofdelig00cerv']

    bad_length = []
    bad_marc = []

    add_languages(mock_site)
    edition_status_counts = defaultdict(int)
    work_status_counts = defaultdict(int)
    author_status_counts = defaultdict(int)

    for ocaid in dq:
        marc_url = 'https://archive.org/download/%s/%s_meta.mrc' % (ocaid, ocaid)
        data = urlopen(marc_url).read()
        try:
            marc = MarcBinary(data)
        except BadLength:
            bad_length.append(ocaid)
            continue
        except BadMARC:
            bad_marc.append(ocaid)
            continue

        rec = read_edition(marc)
        rec['source_records'] = ['ia:' + ocaid]
        reply = load(rec)

        q = {
            'type': '/type/work',
            'authors.author': '/authors/OL1A',
        }
        work_keys = list(mock_site.things(q))
        author_keys = list(mock_site.things({'type': '/type/author'}))
        print("\nReply for %s: %s" % (ocaid, reply))
        print("Work keys: %s" % work_keys)
        assert author_keys == ['/authors/OL1A']
        assert reply['success'] is True

        # Increment status counters
        edition_status_counts[reply['edition']['status']] += 1
        work_status_counts[reply['work']['status']] += 1
        if (reply['work']['status'] != 'matched') and (reply['edition']['status'] != 'modified'):
            # No author key in response if work is 'matched'
            # No author key in response if edition is 'modified'
            author_status_counts[reply['authors'][0]['status']] += 1

    print("BAD MARC LENGTH items: %s" % bad_length)
    print("BAD MARC items: %s" % bad_marc)
    print("Edition status counts: %s" % edition_status_counts)
    print("Work status counts: %s" % work_status_counts)
    print("Author status counts: %s" % author_status_counts)

def test_same_twice(mock_site, add_languages):
    rec = {
            'source_records': ['ia:test_item'],
            "publishers": ["Ten Speed Press"], "pagination": "20 p.", "description": "A macabre mash-up of the children's classic Pat the Bunny and the present-day zombie phenomenon, with the tactile features of the original book revoltingly re-imagined for an adult audience.", "title": "Pat The Zombie", "isbn_13": ["9781607740360"], "languages": ["eng"], "isbn_10": ["1607740362"], "authors": [{"entity_type": "person", "name": "Aaron Ximm", "personal_name": "Aaron Ximm"}], "contributions": ["Kaveh Soofi (Illustrator)"]}
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    assert reply['work']['status'] == 'created'

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'matched'
    assert reply['work']['status'] == 'matched'
