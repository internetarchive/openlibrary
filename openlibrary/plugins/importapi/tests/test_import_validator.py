import pytest
from pydantic import ValidationError

from openlibrary.plugins.importapi.import_validator import import_validator


# The required fields for a import with a complete record.
complete_values = {
    "title": "Beowulf",
    "source_records": ["key:value"],
    "authors": [{"name": "Tom Robbins"}, {"name": "Dean Koontz"}],
    "publish_date": "December 2018",
}

# The required fields for an import with a title and strong identifier.
valid_values_strong_identifier = {
    "title": "Beowulf",
    "source_records": ["key:value"],
    "isbn_13": ["0123456789012"],
}

validator = import_validator()


def test_validate_complete_record():
    """A complete records should validate."""
    assert validator.validate(complete_values) is True


def test_validate_strong_identifier():
    """A record with a title + strong identifier should validate."""
    assert validator.validate(valid_values_strong_identifier) is True


def test_validate_both_complete_and_strong():
    """
    A record that is both complete and that has a strong identifier should
    validate.
    """
    valid_record = complete_values.copy() | valid_values_strong_identifier.copy()
    assert validator.validate(valid_record) is True


@pytest.mark.parametrize(
    'field', ["title", "source_records", "authors", "publish_date"]
)
def test_validate_record_with_missing_required_fields(field):
    """Ensure a record will not validate as complete without each required field."""
    invalid_values = complete_values.copy()
    del invalid_values[field]
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)


@pytest.mark.parametrize('field', ['title', 'publish_date'])
def test_cannot_validate_with_empty_string_values(field):
    """Ensure the title and publish_date are not mere empty strings."""
    invalid_values = complete_values.copy()
    invalid_values[field] = ""
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)


@pytest.mark.parametrize('field', ['source_records', 'authors'])
def test_cannot_validate_with_with_empty_lists(field):
    """Ensure list values will not validate if they are empty."""
    invalid_values = complete_values.copy()
    invalid_values[field] = []
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)


@pytest.mark.parametrize('field', ['source_records'])
def test_cannot_validate_list_with_an_empty_string(field):
    """Ensure lists will not validate with empty string values."""
    invalid_values = complete_values.copy()
    invalid_values[field] = [""]
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)


@pytest.mark.parametrize('field', ['isbn_10', 'lccn'])
def test_validate_multiple_strong_identifiers(field):
    """Records with more than one strong identifier should still validate."""
    multiple_valid_values = valid_values_strong_identifier.copy()
    multiple_valid_values[field] = ["non-empty"]
    assert validator.validate(multiple_valid_values) is True


@pytest.mark.parametrize('field', ['isbn_13'])
def test_validate_not_complete_no_strong_identifier(field):
    """
    Ensure a record cannot validate if it lacks both (1) complete and (2) a title
    and strong identifier, in addition to a source_records field.
    """
    invalid_values = valid_values_strong_identifier.copy()
    invalid_values[field] = [""]
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)


def test_can_import_a_valid_author() -> None:
    """
    Valid authors, e.g. [{"name": "Hilary Putnam"}, {"name": "Willard V. O. Quine"}],
    will validate.
    """
    record_with_valid_author = complete_values.copy()
    assert validator.validate(record_with_valid_author) is True


@pytest.mark.parametrize(
    "authors",
    [
        ([{"not_name": "Hilary Putnam"}]),  # No `name` key.
        ({"name": "Hilary Putnam"}),  # Not a list
        ([{"name": 1}]),  # `name` value isn't a string.
    ],
)
def test_cannot_import_an_invalid_author(authors) -> None:
    """Authors of the shape [{"name": "Hilary Putnam"}] will validate."""
    record_with_invalid_author = complete_values.copy()
    record_with_invalid_author["authors"] = authors
    with pytest.raises(ValidationError):
        validator.validate(record_with_invalid_author)
