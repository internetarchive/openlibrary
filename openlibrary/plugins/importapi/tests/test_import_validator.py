import pytest

from pydantic import ValidationError

from openlibrary.plugins.importapi.import_validator import import_validator

valid_values = {
    "title": "Beowulf",
    "source_records": ["key:value"],
    "author": {"name": "Tom Robbins"},
    "authors": [{"name": "Tom Robbins"}, {"name": "Dean Koontz"}],
    "publishers": ["Harper Collins", "OpenStax"],
    "publish_date": "December 2018",
}

validator = import_validator()


def test_validate():
    assert validator.validate(valid_values) is True


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
