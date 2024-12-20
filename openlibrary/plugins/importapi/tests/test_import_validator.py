import pytest
from pydantic import ValidationError

from openlibrary.plugins.importapi.import_validator import Author, import_validator


def test_create_an_author_with_no_name():
    Author(name="Valid Name")
    with pytest.raises(ValidationError):
        Author(name="")


valid_values = {
    "title": "Beowulf",
    "source_records": ["key:value"],
    "author": {"name": "Tom Robbins"},
    "authors": [{"name": "Tom Robbins"}, {"name": "Dean Koontz"}],
    "publishers": ["Harper Collins", "OpenStax"],
    "publish_date": "December 2018",
}

valid_values_strong_identifier = {
    "title": "Beowulf",
    "source_records": ["key:value"],
    "isbn_13": ["0123456789012"],
}

validator = import_validator()


def test_validate():
    assert validator.validate(valid_values) is True


def test_validate_strong_identifier_minimal():
    """The least amount of data for a strong identifier record to validate."""
    assert validator.validate(valid_values_strong_identifier) is True


@pytest.mark.parametrize(
    'field', ["title", "source_records", "authors", "publishers", "publish_date"]
)
def test_validate_record_with_missing_required_fields(field):
    invalid_values = valid_values.copy()
    del invalid_values[field]
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)


@pytest.mark.parametrize('field', ['title', 'publish_date'])
def test_validate_empty_string(field):
    invalid_values = valid_values.copy()
    invalid_values[field] = ""
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)


@pytest.mark.parametrize('field', ['source_records', 'authors', 'publishers'])
def test_validate_empty_list(field):
    invalid_values = valid_values.copy()
    invalid_values[field] = []
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)


@pytest.mark.parametrize('field', ['source_records', 'publishers'])
def test_validate_list_with_an_empty_string(field):
    invalid_values = valid_values.copy()
    invalid_values[field] = [""]
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)


@pytest.mark.parametrize('field', ['isbn_10', 'lccn'])
def test_validate_multiple_strong_identifiers(field):
    """More than one strong identifier should still validate."""
    multiple_valid_values = valid_values_strong_identifier.copy()
    multiple_valid_values[field] = ["non-empty"]
    assert validator.validate(multiple_valid_values) is True


@pytest.mark.parametrize('field', ['isbn_13'])
def test_validate_not_complete_no_strong_identifier(field):
    """An incomplete record without a strong identifier won't validate."""
    invalid_values = valid_values_strong_identifier.copy()
    invalid_values[field] = [""]
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)
