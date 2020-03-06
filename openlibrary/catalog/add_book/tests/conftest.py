import pytest


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
