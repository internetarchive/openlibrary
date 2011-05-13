from load_book import build_query, InvalidLanguage
from . import load, RequiredField
import py.test

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
        'title': 'Test item',
        'languages': ['eng'],
    }
    reply = load(rec)
    assert reply['success'] == True

    assert reply['edition']['status'] == 'created'
    e = mock_site.get(reply['edition']['key'])
    print
    print 'edition type:', `e.type`
    print
    assert e.type.key == '/type/edition'
    assert e.title == 'Test item'
    assert e.ocaid == 'test_item'
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
