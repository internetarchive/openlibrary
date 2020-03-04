import pytest
from openlibrary.catalog.add_book import load_book
from openlibrary.catalog.add_book.load_book import (
    import_author, build_query, InvalidLanguage)


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
def new_import(monkeypatch):
    monkeypatch.setattr(load_book, 'find_entity', lambda a: None)


# These authors will be imported with natural name order
# The presence of 'personal_name' is what triggers the name swap
natural_names = [
     {'name': 'Forename Surname'},
     {'name': 'Surname, Forename', 'personal_name': 'Surname, Forename'},
     ]


# These authors with be imported with 'name' unchanged
unchanged_names = [
     {'name': 'Forename Surname'},
     {'name': 'Surname, Forename'},
     {'name': 'Surname, Forename', 'entity_type': 'person'},
     {'entity_type': 'org', 'name': 'Organisation, Place'},
     ]


@pytest.mark.parametrize('author', natural_names)
def test_import_author_name_natural_order(author, new_import):
    result = import_author(author)
    assert result['name'] == 'Forename Surname'


@pytest.mark.parametrize('author', natural_names)
def test_import_author_name_unchanged(author, new_import):
    result = import_author(author)
    assert result['name'] == author['name']


def test_build_query(add_languages):
    rec = {
        'title': 'magic',
        'languages': ['eng', 'fre'],
        'authors': [{'name': 'Surname, Forename'}],
        'description': 'test',
    }
    q = build_query(rec)
    assert q['title'] == 'magic'
    assert q['authors'][0]['name'] == 'Surname, Forename'
    assert q['description'] == {'type': '/type/text', 'value': 'test'}
    assert q['type'] == {'key': '/type/edition'}
    assert q['languages'] == [{'key': '/languages/eng'}, {'key': '/languages/fre'}]

    pytest.raises(InvalidLanguage, build_query, {'languages': ['wtf']})
