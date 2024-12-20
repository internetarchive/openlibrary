import os
from datetime import datetime

import pytest

from infogami.infobase.client import Nothing
from infogami.infobase.core import Text
from openlibrary.catalog import add_book
from openlibrary.catalog.add_book import (
    IndependentlyPublished,
    PublicationYearTooOld,
    PublishedInFutureYear,
    RequiredField,
    SourceNeedsISBN,
    build_pool,
    editions_matched,
    find_match,
    isbns_from_record,
    load,
    load_data,
    normalize_import_record,
    should_overwrite_promise_item,
    split_subtitle,
    validate_record,
)
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.parse import read_edition


def open_test_data(filename):
    """Returns a file handle to file with specified filename inside test_data directory."""
    root = os.path.dirname(__file__)
    fullpath = os.path.join(root, 'test_data', filename)
    return open(fullpath, mode='rb')


@pytest.fixture
def ia_writeback(monkeypatch):
    """Prevent ia writeback from making live requests."""
    monkeypatch.setattr(add_book, 'update_ia_metadata_for_ol_edition', lambda olid: {})


def test_isbns_from_record():
    rec = {'title': 'test', 'isbn_13': ['9780190906764'], 'isbn_10': ['0190906766']}
    result = isbns_from_record(rec)
    assert isinstance(result, list)
    assert '9780190906764' in result
    assert '0190906766' in result
    assert len(result) == 2


bookseller_titles = [
    # Original title, title, subtitle
    ['Test Title', 'Test Title', None],
    [
        'Killers of the Flower Moon: The Osage Murders and the Birth of the FBI',
        'Killers of the Flower Moon',
        'The Osage Murders and the Birth of the FBI',
    ],
    ['Pachinko (National Book Award Finalist)', 'Pachinko', None],
    ['Trapped in a Video Game (Book 1) (Volume 1)', 'Trapped in a Video Game', None],
    [
        "An American Marriage (Oprah's Book Club): A Novel",
        'An American Marriage',
        'A Novel',
    ],
    ['A Növel (German Edition)', 'A Növel', None],
    [
        (
            'Vietnam Travel Guide 2019: Ho Chi Minh City - First Journey : '
            '10 Tips For an Amazing Trip'
        ),
        'Vietnam Travel Guide 2019 : Ho Chi Minh City - First Journey',
        '10 Tips For an Amazing Trip',
    ],
    [
        'Secrets of Adobe(r) Acrobat(r) 7. 150 Best Practices and Tips (Russian Edition)',
        'Secrets of Adobe Acrobat 7. 150 Best Practices and Tips',
        None,
    ],
    [
        (
            'Last Days at Hot Slit: The Radical Feminism of Andrea Dworkin '
            '(Semiotext(e) / Native Agents)'
        ),
        'Last Days at Hot Slit',
        'The Radical Feminism of Andrea Dworkin',
    ],
    [
        'Bloody Times: The Funeral of Abraham Lincoln and the Manhunt for Jefferson Davis',
        'Bloody Times',
        'The Funeral of Abraham Lincoln and the Manhunt for Jefferson Davis',
    ],
]


@pytest.mark.parametrize('full_title,title,subtitle', bookseller_titles)
def test_split_subtitle(full_title, title, subtitle):
    assert split_subtitle(full_title) == (title, subtitle)


def test_editions_matched_no_results(mock_site):
    rec = {'title': 'test', 'isbn_13': ['9780190906764'], 'isbn_10': ['0190906766']}
    isbns = isbns_from_record(rec)
    result = editions_matched(rec, 'isbn_', isbns)
    # returns no results because there are no existing editions
    assert result == []


def test_editions_matched(mock_site, add_languages, ia_writeback):
    rec = {
        'title': 'test',
        'isbn_13': ['9780190906764'],
        'isbn_10': ['0190906766'],
        'source_records': ['test:001'],
    }
    load(rec)
    isbns = isbns_from_record(rec)

    result_10 = editions_matched(rec, 'isbn_10', '0190906766')
    assert result_10 == ['/books/OL1M']

    result_13 = editions_matched(rec, 'isbn_13', '9780190906764')
    assert result_13 == ['/books/OL1M']

    # searching on key isbn_ will return a matching record on either isbn_10 or isbn_13 metadata fields
    result = editions_matched(rec, 'isbn_', isbns)
    assert result == ['/books/OL1M']


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
    languages = e.languages
    assert len(languages) == 1
    assert languages[0].key == '/languages/eng'

    assert reply['work']['status'] == 'created'
    w = mock_site.get(reply['work']['key'])
    assert w.title == 'Test item'
    assert w.type.key == '/type/work'


def test_load_deduplicates_authors(mock_site, add_languages, ia_writeback):
    """
    Testings that authors are deduplicated before being added
    This will only work if all the author dicts are identical
    Not sure if that is the case when we get the data for import
    """
    rec = {
        'ocaid': 'test_item',
        'source_records': ['ia:test_item'],
        'authors': [{'name': 'John Brown'}, {'name': 'John Brown'}],
        'title': 'Test item',
        'languages': ['eng'],
    }

    reply = load(rec)
    assert reply['success'] is True
    assert len(reply['authors']) == 1


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
        'authors': [{'name': 'John Döe'}],
        'source_records': 'ia:test_item',
    }
    reply = load(rec)
    assert reply['success'] is True
    w = mock_site.get(reply['work']['key'])
    assert reply['authors'][0]['status'] == 'created'
    assert reply['authors'][0]['name'] == 'John Döe'
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
        'authors': [{'name': 'Döe, John', 'entity_type': 'person'}],
        'source_records': 'ia:test_item1b',
    }
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    assert reply['work']['status'] == 'created'
    akey2 = reply['authors'][0]['key']

    # TODO: There is no code that modifies an author if more data is provided.
    # previously the status implied the record was always 'modified', when a match was found.
    # assert reply['authors'][0]['status'] == 'modified'
    # a = mock_site.get(akey2)
    # assert 'entity_type' in a
    # assert a.entity_type == 'person'

    assert reply['authors'][0]['status'] == 'matched'
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


def test_load_with_redirected_author(mock_site, add_languages):
    """Test importing existing editions without works
    which have author redirects. A work should be created with
    the final author.
    """
    redirect_author = {
        'type': {'key': '/type/redirect'},
        'name': 'John Smith',
        'key': '/authors/OL55A',
        'location': '/authors/OL10A',
    }
    final_author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL10A',
    }
    orphaned_edition = {
        'title': 'Test item HATS',
        'key': '/books/OL10M',
        'publishers': ['TestPub'],
        'publish_date': '1994',
        'authors': [{'key': '/authors/OL55A'}],
        'type': {'key': '/type/edition'},
    }
    mock_site.save(orphaned_edition)
    mock_site.save(redirect_author)
    mock_site.save(final_author)

    rec = {
        'title': 'Test item HATS',
        'authors': [{'name': 'John Smith'}],
        'publishers': ['TestPub'],
        'publish_date': '1994',
        'source_records': 'ia:test_redir_author',
    }
    reply = load(rec)
    assert reply['edition']['status'] == 'modified'
    assert reply['edition']['key'] == '/books/OL10M'
    assert reply['work']['status'] == 'created'
    e = mock_site.get(reply['edition']['key'])
    assert e.authors[0].key == '/authors/OL10A'
    w = mock_site.get(reply['work']['key'])
    assert w.authors[0].author.key == '/authors/OL10A'


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


class Test_From_MARC:
    def test_from_marc_author(self, mock_site, add_languages):
        ia = 'flatlandromanceo00abbouoft'
        marc = MarcBinary(open_test_data(ia + '_meta.mrc').read())

        rec = read_edition(marc)
        rec['source_records'] = ['ia:' + ia]
        reply = load(rec)
        assert reply['success'] is True
        assert reply['edition']['status'] == 'created'
        a = mock_site.get(reply['authors'][0]['key'])
        assert a.type.key == '/type/author'
        assert a.name == 'Edwin Abbott Abbott'
        assert a.birth_date == '1838'
        assert a.death_date == '1926'
        reply = load(rec)
        assert reply['success'] is True
        assert reply['edition']['status'] == 'matched'

    @pytest.mark.parametrize(
        'ia',
        (
            'coursepuremath00hardrich',
            'roadstogreatness00gall',
            'treatiseonhistor00dixo',
        ),
    )
    def test_from_marc(self, ia, mock_site, add_languages):
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

    def test_author_from_700(self, mock_site, add_languages):
        ia = 'sexuallytransmit00egen'
        data = open_test_data(ia + '_meta.mrc').read()
        rec = read_edition(MarcBinary(data))
        rec['source_records'] = ['ia:' + ia]
        reply = load(rec)
        assert reply['success'] is True
        # author from 700
        akey = reply['authors'][0]['key']
        a = mock_site.get(akey)
        assert a.type.key == '/type/author'
        assert a.name == 'Laura K. Egendorf'
        assert a.birth_date == '1973'

    def test_from_marc_reimport_modifications(self, mock_site, add_languages):
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

    def test_missing_ocaid(self, mock_site, add_languages, ia_writeback):
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

    def test_from_marc_fields(self, mock_site, add_languages):
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
        assert sorted(edition['subjects']) == [
            'Action and adventure films',
            'Cinematography',
            'Miscellanea',
            'Physics',
            'Physics in motion pictures',
            'Popular works',
            'Science fiction films',
            'Special effects',
        ]
        # Edition description from 520
        desc = (
            'Explains the basic laws of physics, covering such topics '
            'as mechanics, forces, and energy, while deconstructing '
            'famous scenes and stunts from motion pictures, including '
            '"Apollo 13" and "Titanic," to determine if they are possible.'
        )
        assert isinstance(edition['description'], Text)
        assert edition['description'] == desc
        # Work description from 520
        work = mock_site.get(reply['work']['key'])
        assert isinstance(work['description'], Text)
        assert work['description'] == desc


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
        'ocaid': ['/books/OL1M'],
    }

    pool = build_pool(
        {
            'lccn': ['234'],
            'oclc_numbers': ['456'],
            'title': 'test',
            'ocaid': 'test00test',
        }
    )
    assert pool == {
        'oclc_numbers': ['/books/OL1M'],
        'title': ['/books/OL1M'],
        'ocaid': ['/books/OL1M'],
    }


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

    reply = load(
        {'title': 'Test item', 'source_records': ['ia:test_item2'], 'lccn': ['456']}
    )
    assert reply['success'] is True
    ekey3 = reply['edition']['key']
    assert ekey3 != ekey1

    reply = load(rec)
    assert reply['success'] is True
    ekey4 = reply['edition']['key']

    assert ekey1 == ekey2 == ekey4


def test_extra_author(mock_site, add_languages):
    mock_site.save(
        {
            "name": "Hubert Howe Bancroft",
            "death_date": "1918.",
            "alternate_names": ["HUBERT HOWE BANCROFT", "Hubert Howe Bandcroft"],
            "key": "/authors/OL563100A",
            "birth_date": "1832",
            "personal_name": "Hubert Howe Bancroft",
            "type": {"key": "/type/author"},
        }
    )

    mock_site.save(
        {
            "title": "The works of Hubert Howe Bancroft",
            "covers": [6060295, 5551343],
            "first_sentence": {
                "type": "/type/text",
                "value": (
                    "When it first became known to Europe that a new continent had "
                    "been discovered, the wise men, philosophers, and especially the "
                    "learned ecclesiastics, were sorely perplexed to account for such "
                    "a discovery.",
                ),
            },
            "subject_places": [
                "Alaska",
                "America",
                "Arizona",
                "British Columbia",
                "California",
                "Canadian Northwest",
                "Central America",
                "Colorado",
                "Idaho",
                "Mexico",
                "Montana",
                "Nevada",
                "New Mexico",
                "Northwest Coast of North America",
                "Northwest boundary of the United States",
                "Oregon",
                "Pacific States",
                "Texas",
                "United States",
                "Utah",
                "Washington (State)",
                "West (U.S.)",
                "Wyoming",
            ],
            "excerpts": [
                {
                    "excerpt": (
                        "When it first became known to Europe that a new continent "
                        "had been discovered, the wise men, philosophers, and "
                        "especially the learned ecclesiastics, were sorely perplexed "
                        "to account for such a discovery."
                    )
                }
            ],
            "first_publish_date": "1882",
            "key": "/works/OL3421434W",
            "authors": [
                {
                    "type": {"key": "/type/author_role"},
                    "author": {"key": "/authors/OL563100A"},
                }
            ],
            "subject_times": [
                "1540-1810",
                "1810-1821",
                "1821-1861",
                "1821-1951",
                "1846-1850",
                "1850-1950",
                "1859-",
                "1859-1950",
                "1867-1910",
                "1867-1959",
                "1871-1903",
                "Civil War, 1861-1865",
                "Conquest, 1519-1540",
                "European intervention, 1861-1867",
                "Spanish colony, 1540-1810",
                "To 1519",
                "To 1821",
                "To 1846",
                "To 1859",
                "To 1867",
                "To 1871",
                "To 1889",
                "To 1912",
                "Wars of Independence, 1810-1821",
            ],
            "type": {"key": "/type/work"},
            "subjects": [
                "Antiquities",
                "Archaeology",
                "Autobiography",
                "Bibliography",
                "California Civil War, 1861-1865",
                "Comparative Literature",
                "Comparative civilization",
                "Courts",
                "Description and travel",
                "Discovery and exploration",
                "Early accounts to 1600",
                "English essays",
                "Ethnology",
                "Foreign relations",
                "Gold discoveries",
                "Historians",
                "History",
                "Indians",
                "Indians of Central America",
                "Indians of Mexico",
                "Indians of North America",
                "Languages",
                "Law",
                "Mayas",
                "Mexican War, 1846-1848",
                "Nahuas",
                "Nahuatl language",
                "Oregon question",
                "Political aspects of Law",
                "Politics and government",
                "Religion and mythology",
                "Religions",
                "Social life and customs",
                "Spanish",
                "Vigilance committees",
                "Writing",
                "Zamorano 80",
                "Accessible book",
                "Protected DAISY",
            ],
        }
    )

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
    mock_site.save(
        {
            'key': '/authors/OL592898A',
            'name': 'Michael Robert Marrus',
            'personal_name': 'Michael Robert Marrus',
            'type': {'key': '/type/author'},
        }
    )

    mock_site.save(
        {
            'authors': [
                {'author': '/authors/OL592898A', 'type': {'key': '/type/author_role'}}
            ],
            'key': '/works/OL16029710W',
            'subjects': [
                'Nuremberg Trial of Major German War Criminals, Nuremberg, Germany, 1945-1946',
                'Protected DAISY',
                'Lending library',
            ],
            'title': 'The Nuremberg war crimes trial, 1945-46',
            'type': {'key': '/type/work'},
        }
    )

    mock_site.save(
        {
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
            "subjects": [
                "Nuremberg Trial of Major German War Criminals, Nuremberg, Germany, 1945-1946"
            ],
            "publish_country": "mau",
            "by_statement": "[compiled by] Michael R. Marrus.",
            "type": {"key": "/type/edition"},
            "uris": ["http://www.h-net.org/review/hrev-a0a6c9-aa"],
            "publishers": ["Bedford Books"],
            "ia_box_id": ["IA127618"],
            "key": "/books/OL1023483M",
            "authors": [{"key": "/authors/OL592898A"}],
            "publish_places": ["Boston"],
            "pagination": "xi, 276 p. :",
            "lccn": ["96086777"],
            "notes": {
                "type": "/type/text",
                "value": "Includes bibliographical references (p. 262-268) and index.",
            },
            "identifiers": {"goodreads": ["326638"], "librarything": ["1114474"]},
            "url": ["http://www.h-net.org/review/hrev-a0a6c9-aa"],
            "isbn_10": ["031216386X", "0312136919"],
            "publish_date": "1997",
            "works": [{"key": "/works/OL16029710W"}],
        }
    )

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
        "subjects": [
            "Economics",
            "Alberta",
            "Political Science / State & Local Government",
            "Government policy",
            "Old age pensions",
            "Pensions",
            "Social security",
        ],
        "type": {"key": "/type/edition"},
        "physical_dimensions": "9 x 6 x 0.2 inches",
        "publishers": ["The University of Alberta Press"],
        "physical_format": "Paperback",
        "key": "/books/OL1M",
        "authors": [{"key": "/authors/OL1A"}],
        "identifiers": {"goodreads": ["4340973"], "librarything": ["5580522"]},
        "isbn_13": ["9780888643513"],
        "isbn_10": ["0888643519"],
        "publish_date": "May 1, 2000",
        "works": [{"key": "/works/OL1W"}],
    }
    mock_site.save(edition)

    src = 'v39.i34.records.utf8--186503-1413'
    marc = MarcBinary(open_test_data(src).read())
    rec = read_edition(marc)
    rec['source_records'] = ['marc:' + src]

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'modified'
    assert reply['work']['status'] == 'modified'
    assert 'authors' not in reply

    assert reply['edition']['key'] == edition['key']
    assert reply['work']['key'] == work['key']

    e = mock_site.get(reply['edition']['key'])
    w = mock_site.get(reply['work']['key'])

    assert 'source_records' in e
    assert 'subjects' in w
    assert len(e['authors']) == 1
    assert len(w['authors']) == 1


def test_same_twice(mock_site, add_languages):
    rec = {
        'source_records': ['ia:test_item'],
        "publishers": ["Ten Speed Press"],
        "pagination": "20 p.",
        "description": (
            "A macabre mash-up of the children's classic Pat the Bunny and the "
            "present-day zombie phenomenon, with the tactile features of the original "
            "book revoltingly re-imagined for an adult audience.",
        ),
        "title": "Pat The Zombie",
        "isbn_13": ["9781607740360"],
        "languages": ["eng"],
        "isbn_10": ["1607740362"],
        "authors": [
            {
                "entity_type": "person",
                "name": "Aaron Ximm",
                "personal_name": "Aaron Ximm",
            }
        ],
        "contributions": ["Kaveh Soofi (Illustrator)"],
    }
    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    assert reply['work']['status'] == 'created'

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'matched'
    assert reply['work']['status'] == 'matched'


def test_existing_work(mock_site, add_languages):
    author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL20A',
    }
    existing_work = {
        'authors': [{'author': '/authors/OL20A', 'type': {'key': '/type/author_role'}}],
        'key': '/works/OL16W',
        'title': 'Finding existing works',
        'type': {'key': '/type/work'},
    }
    mock_site.save(author)
    mock_site.save(existing_work)
    rec = {
        'source_records': 'non-marc:test',
        'title': 'Finding Existing Works',
        'authors': [{'name': 'John Smith'}],
        'publishers': ['Black Spot'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1250144051'],
    }

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    assert reply['work']['status'] == 'matched'
    assert reply['work']['key'] == '/works/OL16W'
    assert reply['authors'][0]['status'] == 'matched'
    e = mock_site.get(reply['edition']['key'])
    assert e.works[0]['key'] == '/works/OL16W'


def test_existing_work_with_subtitle(mock_site, add_languages):
    author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL20A',
    }
    existing_work = {
        'authors': [{'author': '/authors/OL20A', 'type': {'key': '/type/author_role'}}],
        'key': '/works/OL16W',
        'title': 'Finding existing works',
        'type': {'key': '/type/work'},
    }
    mock_site.save(author)
    mock_site.save(existing_work)
    rec = {
        'source_records': 'non-marc:test',
        'title': 'Finding Existing Works',
        'subtitle': 'the ongoing saga!',
        'authors': [{'name': 'John Smith'}],
        'publishers': ['Black Spot'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1250144051'],
    }

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    assert reply['work']['status'] == 'matched'
    assert reply['work']['key'] == '/works/OL16W'
    assert reply['authors'][0]['status'] == 'matched'
    e = mock_site.get(reply['edition']['key'])
    assert e.works[0]['key'] == '/works/OL16W'


def test_subtitle_gets_split_from_title(mock_site) -> None:
    """
    Ensures that if there is a subtitle (designated by a colon) in the title
    that it is split and put into the subtitle field.
    """
    rec = {
        'source_records': 'non-marc:test',
        'title': 'Work with a subtitle: not yet split',
        'publishers': ['Black Spot'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1250144051'],
    }

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'created'
    assert reply['work']['status'] == 'created'
    assert reply['work']['key'] == '/works/OL1W'
    e = mock_site.get(reply['edition']['key'])
    assert e.works[0]['title'] == "Work with a subtitle"
    assert isinstance(
        e.works[0]['subtitle'], Nothing
    )  # FIX: this is presumably a bug. See `new_work` not assigning 'subtitle'
    assert e['title'] == "Work with a subtitle"
    assert e['subtitle'] == "not yet split"


# This documents the fact that titles DO NOT have trailing periods stripped (at this point)
def test_title_with_trailing_period_is_stripped() -> None:
    rec = {
        'source_records': 'non-marc:test',
        'title': 'Title with period.',
    }
    normalize_import_record(rec)
    assert rec['title'] == 'Title with period.'


def test_find_match_is_used_when_looking_for_edition_matches(mock_site) -> None:
    """
    This tests the case where there is an edition_pool, but `find_quick_match()`
    finds no matches. This should return a match from `find_threshold_match()`.

    This also indirectly tests `add_book.match.editions_match()`
    """
    author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL20A',
    }
    existing_work = {
        'authors': [
            {'author': {'key': '/authors/OL20A'}, 'type': {'key': '/type/author_role'}}
        ],
        'key': '/works/OL16W',
        'title': 'Finding Existing',
        'subtitle': 'sub',
        'type': {'key': '/type/work'},
    }

    existing_edition_1 = {
        'key': '/books/OL16M',
        'title': 'Finding Existing',
        'subtitle': 'sub',
        'publishers': ['Black Spot'],
        'type': {'key': '/type/edition'},
        'source_records': ['non-marc:test'],
        'works': [{'key': '/works/OL16W'}],
    }

    existing_edition_2 = {
        'key': '/books/OL17M',
        'source_records': ['non-marc:test'],
        'title': 'Finding Existing',
        'subtitle': 'sub',
        'publishers': ['Black Spot'],
        'type': {'key': '/type/edition'},
        'publish_country': 'usa',
        'publish_date': 'Jan 09, 2011',
        'works': [{'key': '/works/OL16W'}],
    }
    mock_site.save(author)
    mock_site.save(existing_work)
    mock_site.save(existing_edition_1)
    mock_site.save(existing_edition_2)
    rec = {
        'source_records': ['non-marc:test'],
        'title': 'Finding Existing',
        'subtitle': 'sub',
        'authors': [{'name': 'John Smith'}],
        'publishers': ['Black Spot substring match'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1250144051'],
        'publish_country': 'usa',
    }
    reply = load(rec)
    assert reply['edition']['key'] == '/books/OL17M'
    e = mock_site.get(reply['edition']['key'])
    assert e['key'] == '/books/OL17M'


def test_covers_are_added_to_edition(mock_site, monkeypatch) -> None:
    """Ensures a cover from rec is added to a matched edition."""
    author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL20A',
    }

    existing_work = {
        'authors': [
            {'author': {'key': '/authors/OL20A'}, 'type': {'key': '/type/author_role'}}
        ],
        'key': '/works/OL16W',
        'title': 'Covers',
        'type': {'key': '/type/work'},
    }

    existing_edition = {
        'key': '/books/OL16M',
        'title': 'Covers',
        'publishers': ['Black Spot'],
        # TODO: only matches if the date is exact. 2011 != Jan 09, 2011
        #'publish_date': '2011',
        'publish_date': 'Jan 09, 2011',
        'type': {'key': '/type/edition'},
        'source_records': ['non-marc:test'],
        'works': [{'key': '/works/OL16W'}],
    }

    mock_site.save(author)
    mock_site.save(existing_work)
    mock_site.save(existing_edition)

    rec = {
        'source_records': ['non-marc:test'],
        'title': 'Covers',
        'authors': [{'name': 'John Smith'}],
        'publishers': ['Black Spot'],
        'publish_date': 'Jan 09, 2011',
        'cover': 'https://www.covers.org/cover.jpg',
    }

    monkeypatch.setattr(add_book, "add_cover", lambda _, __, account_key: 1234)
    reply = load(rec)

    assert reply['success'] is True
    assert reply['edition']['status'] == 'modified'
    e = mock_site.get(reply['edition']['key'])
    assert e['covers'] == [1234]


def test_add_description_to_work(mock_site) -> None:
    """
    Ensure that if an edition has a description, and the associated work does
    not, that the edition's description is added to the work.
    """
    author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL20A',
    }

    existing_work = {
        'authors': [{'author': '/authors/OL20A', 'type': {'key': '/type/author_role'}}],
        'key': '/works/OL16W',
        'title': 'Finding Existing Works',
        'type': {'key': '/type/work'},
    }

    existing_edition = {
        'key': '/books/OL16M',
        'title': 'Finding Existing Works',
        'publishers': ['Black Spot'],
        'type': {'key': '/type/edition'},
        'source_records': ['non-marc:test'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1250144051'],
        'works': [{'key': '/works/OL16W'}],
        'description': 'An added description from an existing edition',
    }

    mock_site.save(author)
    mock_site.save(existing_work)
    mock_site.save(existing_edition)

    rec = {
        'source_records': 'non-marc:test',
        'title': 'Finding Existing Works',
        'authors': [{'name': 'John Smith'}],
        'publishers': ['Black Spot'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1250144051'],
    }

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'matched'
    assert reply['work']['status'] == 'modified'
    assert reply['work']['key'] == '/works/OL16W'
    e = mock_site.get(reply['edition']['key'])
    assert e.works[0]['key'] == '/works/OL16W'
    assert e.works[0]['description'] == 'An added description from an existing edition'


def test_add_subjects_to_work_deduplicates(mock_site) -> None:
    """
    Ensure a rec's subjects, after a case insensitive check, are added to an
    existing Work if not already present.
    """
    author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL1A',
    }

    existing_work = {
        'authors': [{'author': '/authors/OL1A', 'type': {'key': '/type/author_role'}}],
        'key': '/works/OL1W',
        'subjects': ['granite', 'GRANITE', 'Straße', 'ΠΑΡΆΔΕΙΣΟΣ'],
        'title': 'Some Title',
        'type': {'key': '/type/work'},
    }

    existing_edition = {
        'key': '/books/OL1M',
        'title': 'Some Title',
        'publishers': ['Black Spot'],
        'type': {'key': '/type/edition'},
        'source_records': ['non-marc:test'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1250144051'],
        'works': [{'key': '/works/OL1W'}],
    }

    mock_site.save(author)
    mock_site.save(existing_work)
    mock_site.save(existing_edition)

    rec = {
        'authors': [{'name': 'John Smith'}],
        'isbn_10': ['1250144051'],
        'publish_date': 'Jan 09, 2011',
        'publishers': ['Black Spot'],
        'source_records': 'non-marc:test',
        'subjects': [
            'granite',
            'Granite',
            'SANDSTONE',
            'sandstone',
            'strasse',
            'παράδεισος',
        ],
        'title': 'Some Title',
    }

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'matched'
    assert reply['work']['status'] == 'modified'
    assert reply['work']['key'] == '/works/OL1W'
    w = mock_site.get(reply['work']['key'])

    def get_casefold(item_list: list[str]):
        return [item.casefold() for item in item_list]

    expected = ['granite', 'Straße', 'ΠΑΡΆΔΕΙΣΟΣ', 'sandstone']
    got = w.subjects
    assert get_casefold(got) == get_casefold(expected)


def test_add_identifiers_to_edition(mock_site) -> None:
    """
    Ensure a rec's identifiers that are not present in a matched edition are
    added to that matched edition.
    """
    author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL20A',
    }

    existing_work = {
        'authors': [{'author': '/authors/OL20A', 'type': {'key': '/type/author_role'}}],
        'key': '/works/OL19W',
        'title': 'Finding Existing Works',
        'type': {'key': '/type/work'},
    }

    existing_edition = {
        'key': '/books/OL19M',
        'title': 'Finding Existing Works',
        'publishers': ['Black Spot'],
        'type': {'key': '/type/edition'},
        'source_records': ['non-marc:test'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1250144051'],
        'works': [{'key': '/works/OL19W'}],
    }

    mock_site.save(author)
    mock_site.save(existing_work)
    mock_site.save(existing_edition)

    rec = {
        'source_records': 'non-marc:test',
        'title': 'Finding Existing Works',
        'authors': [{'name': 'John Smith'}],
        'publishers': ['Black Spot'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1250144051'],
        'identifiers': {'goodreads': ['1234'], 'librarything': ['5678']},
    }

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'modified'
    assert reply['work']['status'] == 'matched'
    assert reply['work']['key'] == '/works/OL19W'
    e = mock_site.get(reply['edition']['key'])
    assert e.works[0]['key'] == '/works/OL19W'
    assert e.identifiers._data == {'goodreads': ['1234'], 'librarything': ['5678']}


def test_adding_list_field_items_to_edition_deduplicates_input(mock_site) -> None:
    """
    Ensure a rec's edition_list_fields that are not present in a matched
    edition are added to that matched edition.
    """
    author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL1A',
    }

    existing_work = {
        'authors': [{'author': '/authors/OL1A', 'type': {'key': '/type/author_role'}}],
        'key': '/works/OL1W',
        'title': 'Some Title',
        'type': {'key': '/type/work'},
    }

    existing_edition = {
        'isbn_10': ['1250144051'],
        'key': '/books/OL1M',
        'lccn': ['agr25000003'],
        'publish_date': 'Jan 09, 2011',
        'publishers': ['Black Spot'],
        'source_records': ['non-marc:test'],
        'title': 'Some Title',
        'type': {'key': '/type/edition'},
        'works': [{'key': '/works/OL1W'}],
    }

    mock_site.save(author)
    mock_site.save(existing_work)
    mock_site.save(existing_edition)

    rec = {
        'authors': [{'name': 'John Smith'}],
        'isbn_10': ['1250144051'],
        'lccn': ['AGR25000003', 'AGR25-3'],
        'publish_date': 'Jan 09, 2011',
        'publishers': ['Black Spot', 'Second Publisher'],
        'source_records': ['NON-MARC:TEST', 'ia:someid'],
        'title': 'Some Title',
    }

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'modified'
    assert reply['work']['status'] == 'matched'
    assert reply['work']['key'] == '/works/OL1W'
    e = mock_site.get(reply['edition']['key'])
    assert e.works[0]['key'] == '/works/OL1W'
    assert e.lccn == ['agr25000003']
    assert e.source_records == ['non-marc:test', 'ia:someid']


@pytest.mark.parametrize(
    'name, rec, error',
    [
        (
            "Books prior to 1400 CANNOT be imported if from a bookseller requiring additional validation",
            {
                'title': 'a book',
                'source_records': ['amazon:123'],
                'publish_date': '1399',
                'isbn_10': ['1234567890'],
            },
            PublicationYearTooOld,
        ),
        (
            "Books published on or after 1400 CE+ can be imported from any source",
            {
                'title': 'a book',
                'source_records': ['amazon:123'],
                'publish_date': '1400',
                'isbn_10': ['1234567890'],
            },
            None,
        ),
        (
            "Trying to import a book from a future year raises an error",
            {'title': 'a book', 'source_records': ['ia:ocaid'], 'publish_date': '3000'},
            PublishedInFutureYear,
        ),
        (
            "Independently published books CANNOT be imported",
            {
                'title': 'a book',
                'source_records': ['ia:ocaid'],
                'publishers': ['Independently Published'],
            },
            IndependentlyPublished,
        ),
        (
            "Non-independently published books can be imported",
            {
                'title': 'a book',
                'source_records': ['ia:ocaid'],
                'publishers': ['Best Publisher'],
            },
            None,
        ),
        (
            "Import sources that require an ISBN CANNOT be imported without an ISBN",
            {'title': 'a book', 'source_records': ['amazon:amazon_id'], 'isbn_10': []},
            SourceNeedsISBN,
        ),
        (
            "Can import sources that require an ISBN and have ISBN",
            {
                'title': 'a book',
                'source_records': ['amazon:amazon_id'],
                'isbn_10': ['1234567890'],
            },
            None,
        ),
        (
            "Can import from sources that don't require an ISBN",
            {'title': 'a book', 'source_records': ['ia:wheeee'], 'isbn_10': []},
            None,
        ),
    ],
)
def test_validate_record(name, rec, error) -> None:
    if error:
        with pytest.raises(error):
            validate_record(rec)
    else:
        assert validate_record(rec) is None, f"Test failed: {name}"  # type: ignore [func-returns-value]


def test_reimport_updates_edition_and_work_description(mock_site) -> None:
    author = {
        'type': {'key': '/type/author'},
        'name': 'John Smith',
        'key': '/authors/OL1A',
    }

    existing_work = {
        'authors': [{'author': '/authors/OL1A', 'type': {'key': '/type/author_role'}}],
        'key': '/works/OL1W',
        'title': 'A Good Book',
        'type': {'key': '/type/work'},
    }

    existing_edition = {
        'key': '/books/OL1M',
        'title': 'A Good Book',
        'publishers': ['Black Spot'],
        'type': {'key': '/type/edition'},
        'source_records': ['ia:someocaid'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1234567890'],
        'works': [{'key': '/works/OL1W'}],
    }

    mock_site.save(author)
    mock_site.save(existing_work)
    mock_site.save(existing_edition)

    rec = {
        'source_records': 'ia:someocaid',
        'title': 'A Good Book',
        'authors': [{'name': 'John Smith'}],
        'publishers': ['Black Spot'],
        'publish_date': 'Jan 09, 2011',
        'isbn_10': ['1234567890'],
        'description': 'A genuinely enjoyable read.',
    }

    reply = load(rec)
    assert reply['success'] is True
    assert reply['edition']['status'] == 'modified'
    assert reply['work']['status'] == 'modified'
    assert reply['work']['key'] == '/works/OL1W'
    edition = mock_site.get(reply['edition']['key'])
    work = mock_site.get(reply['work']['key'])
    assert edition.description == "A genuinely enjoyable read."
    assert work.description == "A genuinely enjoyable read."


@pytest.mark.parametrize(
    "name, edition, marc, expected",
    [
        (
            "Overwrites revision 1 promise items with MARC data",
            {'revision': 1, 'source_records': ['promise:bwb_daily_pallets_2022-03-17']},
            True,
            True,
        ),
        (
            "Doesn't overwrite rev 1 promise items WITHOUT MARC data",
            {'revision': 1, 'source_records': ['promise:bwb_daily_pallets_2022-03-17']},
            False,
            False,
        ),
        (
            "Doesn't overwrite non-revision 1 promise items",
            {'revision': 2, 'source_records': ['promise:bwb_daily_pallets_2022-03-17']},
            True,
            False,
        ),
        (
            "Doesn't overwrite revision 1 NON-promise items",
            {'revision': 1, 'source_records': ['ia:test']},
            True,
            False,
        ),
        (
            "Can handle editions with an empty source record",
            {'revision': 1, 'source_records': ['']},
            True,
            False,
        ),
        ("Can handle editions without a source record", {'revision': 1}, True, False),
        (
            "Can handle editions without a revision",
            {'source_records': ['promise:bwb_daily_pallets_2022-03-17']},
            True,
            False,
        ),
    ],
)
def test_overwrite_if_rev1_promise_item(name, edition, marc, expected) -> None:
    """
    Specifically unit test the function that determines if a promise
    item should be overwritten.
    """
    result = should_overwrite_promise_item(edition=edition, from_marc_record=marc)
    assert (
        result == expected
    ), f"Test {name} failed. Expected {expected}, but got {result}"


@pytest.fixture
def setup_load_data(mock_site):
    existing_author = {
        'key': '/authors/OL1A',
        'name': 'John Smith',
        'type': {'key': '/type/author'},
    }

    existing_work = {
        'authors': [{'author': '/authors/OL1A', 'type': {'key': '/type/author_role'}}],
        'key': '/works/OL1W',
        'title': 'Finding Existing Works',
        'type': {'key': '/type/work'},
    }

    existing_edition = {
        'isbn_10': ['1234567890'],
        'key': '/books/OL1M',
        'publish_date': 'Jan 1st, 3000',
        'publishers': ['BOOK BOOK BOOK'],
        'source_records': ['promise:bwb_daily_pallets_2022-03-17'],
        'title': 'Originally A Promise Item',
        'type': {'key': '/type/edition'},
        'works': [{'key': '/works/OL1W'}],
    }

    incoming_rec = {
        'authors': [{'name': 'John Smith'}],
        'description': 'A really fun book.',
        'dewey_decimal_class': ['853.92'],
        'identifiers': {'goodreads': ['1234'], 'librarything': ['5678']},
        'isbn_10': ['1234567890'],
        'ocaid': 'newlyscannedpromiseitem',
        'publish_country': 'fr',
        'publish_date': '2017',
        'publish_places': ['Paris'],
        'publishers': ['Gallimard'],
        'series': ['Folio, Policier : roman noir -- 820'],
        'source_records': ['ia:newlyscannedpromiseitem'],
        'title': 'Originally A Promise Item',
        'translated_from': ['yid'],
    }

    mock_site.save(existing_author)
    mock_site.save(existing_work)
    mock_site.save(existing_edition)

    return incoming_rec


class TestLoadDataWithARev1PromiseItem:
    """
    Test the process of overwriting a rev1 promise item by passing it, and
    an incoming record with MARC data, to load_data.
    """

    def test_passing_edition_to_load_data_overwrites_edition_with_rec_data(
        self, mock_site, add_languages, ia_writeback, setup_load_data
    ) -> None:
        rec: dict = setup_load_data
        edition = mock_site.get('/books/OL1M')

        reply = load_data(rec=rec, existing_edition=edition)
        assert reply['edition']['status'] == 'modified'
        assert reply['success'] is True
        assert reply['work']['key'] == '/works/OL1W'
        assert reply['work']['status'] == 'matched'

        edition = mock_site.get(reply['edition']['key'])
        assert edition.dewey_decimal_class == ['853.92']
        assert edition.publish_date == '2017'
        assert edition.publish_places == ['Paris']
        assert edition.publishers == ['Gallimard']
        assert edition.series == ['Folio, Policier : roman noir -- 820']
        assert edition.source_records == [
            'promise:bwb_daily_pallets_2022-03-17',
            'ia:newlyscannedpromiseitem',
        ]
        assert edition.works[0]['key'] == '/works/OL1W'


class TestNormalizeImportRecord:
    @pytest.mark.parametrize(
        'year, expected',
        [
            ("2000-11-11", True),
            (str(datetime.now().year), True),
            (str(datetime.now().year + 1), False),
            ("9999-01-01", False),
        ],
    )
    def test_future_publication_dates_are_deleted(self, year, expected):
        """It should be impossible to import books publish_date in a future year."""
        rec = {
            'title': 'test book',
            'source_records': ['ia:blob'],
            'publish_date': year,
        }
        normalize_import_record(rec=rec)
        result = 'publish_date' in rec
        assert result == expected

    @pytest.mark.parametrize(
        'rec, expected',
        [
            (
                {
                    'title': 'first title',
                    'source_records': ['ia:someid'],
                    'publishers': ['????'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': '2000',
                },
                {
                    'title': 'first title',
                    'source_records': ['ia:someid'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': '2000',
                },
            ),
            (
                {
                    'title': 'second title',
                    'source_records': ['ia:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': '2000',
                },
                {
                    'title': 'second title',
                    'source_records': ['ia:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': '2000',
                },
            ),
        ],
    )
    def test_dummy_data_to_satisfy_parse_data_is_removed(self, rec, expected):
        normalize_import_record(rec=rec)
        assert rec == expected

    @pytest.mark.parametrize(
        ["rec", "expected"],
        [
            (
                # 1900 publication from non AMZ/BWB is okay.
                {
                    'title': 'a title',
                    'source_records': ['ia:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': '1900',
                },
                {
                    'title': 'a title',
                    'source_records': ['ia:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': '1900',
                },
            ),
            (
                # 1900 publication from AMZ disappears.
                {
                    'title': 'a title',
                    'source_records': ['amazon:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': '1900',
                },
                {
                    'title': 'a title',
                    'source_records': ['amazon:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                },
            ),
            (
                # 1900 publication from bwb item disappears.
                {
                    'title': 'a title',
                    'source_records': ['bwb:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': '1900',
                },
                {
                    'title': 'a title',
                    'source_records': ['bwb:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                },
            ),
            (
                # 1900 publication from promise item disappears.
                {
                    'title': 'a title',
                    'source_records': ['promise:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': 'January 1, 1900',
                },
                {
                    'title': 'a title',
                    'source_records': ['promise:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                },
            ),
            (
                # An otherwise valid date from AMZ is okay.
                {
                    'title': 'a title',
                    'source_records': ['amazon:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': 'January 2, 1900',
                },
                {
                    'title': 'a title',
                    'source_records': ['amazon:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': 'January 2, 1900',
                },
            ),
            (
                # An otherwise valid date from promise is okay.
                {
                    'title': 'a title',
                    'source_records': ['promise:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': 'January 2, 1900',
                },
                {
                    'title': 'a title',
                    'source_records': ['promise:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                    'publish_date': 'January 2, 1900',
                },
            ),
            (
                # Handle records without publish_date.
                {
                    'title': 'a title',
                    'source_records': ['promise:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                },
                {
                    'title': 'a title',
                    'source_records': ['promise:someid'],
                    'publishers': ['a publisher'],
                    'authors': [{'name': 'an author'}],
                },
            ),
        ],
    )
    def test_year_1900_removed_from_amz_and_bwb_promise_items(self, rec, expected):
        """
        A few import sources (e.g. promise items, BWB, and Amazon) have `publish_date`
        values that are known to be inaccurate, so those `publish_date` values are
        removed.
        """
        normalize_import_record(rec=rec)
        assert rec == expected


def test_find_match_title_only_promiseitem_against_noisbn_marc(mock_site):
    # An existing light title + ISBN only record
    existing_edition = {
        'key': '/books/OL113M',
        # NO author
        # NO date
        # NO publisher
        'title': 'Just A Title',
        'isbn_13': ['9780000000002'],
        'source_records': ['promise:someid'],
        'type': {'key': '/type/edition'},
    }
    marc_import = {
        'authors': [{'name': 'Bob Smith'}],
        'publish_date': '1913',
        'publishers': ['Early Editions'],
        'title': 'Just A Title',
        'source_records': ['marc:somelibrary/some_marc.mrc'],
    }
    mock_site.save(existing_edition)
    result = find_match(marc_import, {'title': [existing_edition['key']]})
    assert result != '/books/OL113M'
    assert result is None
