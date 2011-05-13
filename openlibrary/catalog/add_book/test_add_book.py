from load_book import build_query, InvalidLanguage
from . import load, RequiredField
import py.test

def test_build_query(mock_site):
    mock_site.save({'key': '/languages/eng', 'name': 'English'})
    mock_site.save({'key': '/languages/fre', 'name': 'French'})
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
    rec = {'ocaid': 'test item'}
    py.test.raises(RequiredField, load, {'ocaid': 'test_item'})

    rec = {
        'ocaid': 'test_item',
        'title': 'Test item'
    }
    reply = load(rec)
    assert reply['success'] == True

    assert reply['edition']['status'] == 'created'
    e = mock_site.get(reply['edition']['key'])
    assert e.title == 'Test item'
    assert e.ocaid == 'test_item'

    assert reply['work']['status'] == 'created'
    w = mock_site.get(reply['work']['key'])
    assert w.title == 'Test item'

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
        'authors': [{'name': 'John Doe', 'entity_type': 'person'}],
    }
    reply = load(rec)
    assert reply['success'] == True
    assert reply['authors'][0]['status'] == 'created'


