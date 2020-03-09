import pytest
from openlibrary.catalog.add_book import load_book
from openlibrary.catalog.add_book.load_book import (
    import_author, build_query, InvalidLanguage)


@pytest.fixture
def new_import(monkeypatch):
    monkeypatch.setattr(load_book, 'find_entity', lambda a: None)


# These authors will be imported with natural name order
# i.e. => Forename Surname
natural_names = [
     {'name': 'Forename Surname'},
     {'name': 'Surname, Forename', 'personal_name': 'Surname, Forename'},
     {'name': 'Surname, Forename'},
     {'name': 'Surname, Forename', 'entity_type': 'person'},
     ]


# These authors will be imported with 'name' unchanged
unchanged_names = [
     {'name': 'Forename Surname'},
     {'name': 'Smith, John III, King of Coats, and Bottles',
         'personal_name': 'Smith, John'},
     {'name': 'Smith, John III, King of Coats, and Bottles'},
     {'name': 'Harper, John Murdoch, 1845-'},
     {'entity_type': 'org', 'name': 'Organisation, Place'},
     ]


@pytest.mark.parametrize('author', natural_names)
def test_import_author_name_natural_order(author, new_import):
    result = import_author(author)
    assert result['name'] == 'Forename Surname'


@pytest.mark.parametrize('author', unchanged_names)
def test_import_author_name_unchanged(author, new_import):
    expect = author['name']
    result = import_author(author)
    assert result['name'] == expect


def test_build_query(add_languages):
    rec = {
        'title': 'magic',
        'languages': ['eng', 'fre'],
        'authors': [{'name': 'Surname, Forename'}],
        'description': 'test',
    }
    q = build_query(rec)
    assert q['title'] == 'magic'
    assert q['authors'][0]['name'] == 'Forename Surname'
    assert q['description'] == {'type': '/type/text', 'value': 'test'}
    assert q['type'] == {'key': '/type/edition'}
    assert q['languages'] == [{'key': '/languages/eng'}, {'key': '/languages/fre'}]

    pytest.raises(InvalidLanguage, build_query, {'languages': ['wtf']})
