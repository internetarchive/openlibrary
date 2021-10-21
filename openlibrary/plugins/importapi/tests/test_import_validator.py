import pytest
from openlibrary.plugins.importapi.import_validator import import_validator

valid_values = {
    "title": "Beowulf",
    "source_records": ["key:value"],
    "author": {"name": "Tom Robbins"},
    "authors": [{"name": "Tom Robbins"}, {"name": "Dean Koontz"}],
    "publishers": ["Harper Collins", "OpenStax"],
    "publish_date": "December 2018"
}

validator = import_validator()

def test_validate_title():
    # Title must be a string of length greater than 0
    assert validator._validate_title(valid_values["title"]) == True
    assert validator._validate_title("") == False
    assert validator._validate_title(['a']) == False

def test_validate_source_records():
    # source_records must be a non-empty list of strings
    assert validator._validate_source_records(valid_values["source_records"]) == True
    assert validator._validate_source_records([]) == False
    assert validator._validate_source_records(17) == False

def test_validate_author():
    # Author is a dict with key-value pair ("name" : str)
    assert validator._validate_author(valid_values["author"]) == True
    assert validator._validate_author({"name": 17}) == False
    assert validator._validate_author({"title": "Duke"}) == False
    assert validator._validate_author({}) == False
    assert validator._validate_author("Dean Koontz") == False

def test_validate_author_list():
    # The author list must be non-empty and contain only valid authors
    assert validator._validate_authors(valid_values["authors"]) == True
    assert validator._validate_authors([{"name": "Tom Robbins"}, {"title": "Sir"}]) == False
    assert validator._validate_authors([]) == False
    assert validator._validate_authors("") == False
    assert validator._validate_authors(17) == False

def test_validate_publisher_list():
    # Publisher lists must be non-empty and contain only strings
    assert validator._validate_publishers(valid_values["publishers"]) == True
    assert validator._validate_publishers(["Harper Collins"]) == True
    assert validator._validate_publishers([]) == False
    assert validator._validate_publishers([17]) == False
    assert validator._validate_publishers("Harper Collins") == False

def test_validate_publish_date():
    # Publish date must be a date string
    assert validator._validate_publish_date(valid_values["publish_date"]) == True
    assert validator._validate_publish_date("2018") == True
    assert validator._validate_publish_date(2018) == False
    assert validator._validate_publish_date("") == False

def test_validate():
    assert validator.validate(valid_values) == True
    invalid_values = valid_values.copy()
    del invalid_values['authors']
    assert validator.validate(invalid_values) == False
