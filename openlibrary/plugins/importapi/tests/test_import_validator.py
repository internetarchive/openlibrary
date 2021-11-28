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
    invalid_values = valid_values.copy()
    del invalid_values['authors']
    with pytest.raises(ValidationError):
        validator.validate(invalid_values)
