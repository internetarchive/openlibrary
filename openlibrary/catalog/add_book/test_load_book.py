import pytest
from openlibrary.catalog.add_book import load_book
from openlibrary.catalog.add_book.load_book import import_author, build_query, InvalidLanguage


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


def test_import_author_personal_name(monkeypatch):
    """Name order is only flipped to natural order if 'personal_name' is present.
    """
    monkeypatch.setattr(load_book, 'find_entity', lambda a: None)
    result = import_author({'personal_name': 'Surname, Forename', 'name': 'Surname, Forename'})
    assert result['name'] == 'Forename Surname'


def test_import_author_name_only(monkeypatch):
    monkeypatch.setattr(load_book, 'find_entity', lambda a: None)
    result = import_author({'name': 'Surname, Forename'})
    assert result['name'] == 'Surname, Forename'


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
