from load_book import build_query, InvalidLanguage
from . import load, RequiredField, build_pool, add_db_name
import py.test
from pprint import pprint
from openlibrary.catalog.merge.merge_marc import build_marc
from openlibrary.catalog.marc.parse import read_edition
from openlibrary.catalog.marc.marc_binary import MarcBinary
from merge import try_merge
from copy import deepcopy

def add_languages(mock_site):
    languages = [
        ('eng', 'English'),
        ('fre', 'Frech'),
    ]
    for code, name in languages:
        mock_site.save({
            'key': '/languages/' + code,
            'name': name,
            'type': {'key': '/type/language'},
        })

def test_build_query(mock_site):
    add_languages(mock_site)
    rec = {
        'title': 'magic',
        'languages': ['eng', 'fre'],
        'authors': [{}],
        'description': 'test',
    }
    q = build_query(rec)
    assert q['title'] == 'magic'
    assert q['description'] == { 'type': '/type/text', 'value': 'test' }
    assert q['type'] == {'key': '/type/edition'}
    assert q['languages'] == [{'key': '/languages/eng'}, {'key': '/languages/fre'}]

    py.test.raises(InvalidLanguage, build_query, {'languages': ['wtf']})

def test_load(mock_site):
    add_languages(mock_site)
    rec = {'ocaid': 'test item'}
    py.test.raises(RequiredField, load, {'ocaid': 'test_item'})

    rec = {
        'ocaid': 'test_item',
        'source_records': ['ia:test_item'],
        'title': 'Test item',
        'languages': ['eng'],
    }
    reply = load(rec)
    assert reply['success'] == True

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

    rec = {
        'ocaid': 'test_item',
        'title': 'Test item',
        'subjects': ['Protected DAISY', 'In library'],
    }
    reply = load(rec)
    assert reply['success'] == True
    w = mock_site.get(reply['work']['key'])
    assert w.title == 'Test item'
    assert w.subjects == ['Protected DAISY', 'In library']

    rec = {
        'ocaid': 'test_item',
        'title': 'Test item',
        'authors': [{'name': 'John Doe'}],
    }
    reply = load(rec)
    assert reply['success'] == True
    assert reply['authors'][0]['status'] == 'created'
    assert reply['authors'][0]['name'] == 'John Doe'
    akey1 = reply['authors'][0]['key']
    a = mock_site.get(akey1)
    assert a.type.key == '/type/author'

    rec = {
        'ocaid': 'test_item',
        'title': 'Test item',
        'authors': [{'name': 'Doe, John', 'entity_type': 'person'}],
    }
    reply = load(rec)
    assert reply['success'] == True
    assert reply['authors'][0]['status'] == 'modified'
    akey2 = reply['authors'][0]['key']
    assert akey1 == akey2


#def test_author_matching(mock_site):

def test_from_marc(mock_site):
    from openlibrary.catalog.marc.marc_binary import MarcBinary
    from openlibrary.catalog.marc.parse import read_edition

    add_languages(mock_site)
    data = open('test_data/flatlandromanceo00abbouoft_meta.mrc').read()
    assert len(data) == int(data[:5])
    rec = read_edition(MarcBinary(data))
    reply = load(rec)
    assert reply['success'] == True
    akey1 = reply['authors'][0]['key']
    a = mock_site.get(akey1)
    assert a.type.key == '/type/author'
    assert a.name == 'Edwin Abbott Abbott'
    assert a.birth_date == '1838'
    assert a.death_date == '1926'

def test_build_pool(mock_site):
    assert build_pool({}) == {}
    etype = '/type/edition'
    ekey = mock_site.new_key(etype)
    e = {
        'type': {'key': etype},
        'lccn': ['123'],
        'oclc_numbers': ['456'],
        'key': ekey,
    }

    mock_site.save(e)
    pool = build_pool(e)
    assert pool == {
        'lccn': ['/books/OL1M'],
        'oclc_numbers': ['/books/OL1M'],
    }

    pool = build_pool({'lccn': ['234'], 'oclc_numbers': ['456']})
    assert pool == { 'oclc_numbers': ['/books/OL1M'], }

def test_try_merge(mock_site):
    rec = {
        'title': 'Test item',
        'lccn': ['123'],
        'authors': [{'name': 'Smith, John', 'birth_date': '1980'}],
    }
    reply = load(rec)
    ekey = reply['edition']['key']
    e = mock_site.get(ekey)

    rec['full_title'] = rec['title']
    if rec.get('subtitle'):
        rec['full_title'] += ' ' + rec['subtitle']
    e1 = build_marc(rec)
    add_db_name(e1)

    assert try_merge(e1, ekey, e)

def test_load_multiple(mock_site):
    rec = {
        'title': 'Test item',
        'lccn': ['123'],
        'authors': [{'name': 'Smith, John', 'birth_date': '1980'}],
    }
    reply = load(rec)
    assert reply['success'] == True
    ekey1 = reply['edition']['key']

    reply = load(rec)
    assert reply['success'] == True
    ekey2 = reply['edition']['key']
    assert ekey1 == ekey2

    reply = load({'title': 'Test item', 'lccn': ['456']})
    assert reply['success'] == True
    ekey3 = reply['edition']['key']
    assert ekey3 != ekey1

    reply = load(rec)
    assert reply['success'] == True
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

def test_from_marc(mock_site):
    add_languages(mock_site)
    marc = MarcBinary(open('test_data/coursepuremath00hardrich_meta.mrc').read())
    rec = read_edition(marc)
    reply = load(rec)
    assert reply['success'] == True
    reply = load(rec)
    assert reply['success'] == True
    assert reply['edition']['status'] == 'match'

