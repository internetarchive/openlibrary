import pytest

from openlibrary.plugins.importapi.import_validator import (import_validator,
                                                            RequiredFieldError)

valid_values = {
    "title": "Beowulf",
    "source_records": ["key:value"],
    "author": {"name": "Tom Robbins"},
    "authors": [{"name": "Tom Robbins"}, {"name": "Dean Koontz"}],
    "publishers": ["Harper Collins", "OpenStax"],
    "publish_date": "December 2018"
}

validator = import_validator()


def test_validate_length():
    # Target list must contain at least as many items as minimally allowed
    test_list = []
    assert validator._validate_length(test_list, 1) is False
    test_list.append("item one")
    assert validator._validate_length(test_list, 1) is True
    assert validator._validate_length(test_list, 2) is False

    # Target string must contain the minimum amount of letters
    test_str = ''
    assert validator._validate_length(test_str, 1) is False
    assert validator._validate_length(test_str, 0) is True
    test_str = 'new string'
    assert validator._validate_length(test_str, 1) is True


def test_validate_type():
    test_string = ""
    assert validator._validate_type(test_string, str) is True
    assert validator._validate_type(test_string, dict) is False
    assert validator._validate_type(test_string, list) is False

    test_dict = dict()
    assert validator._validate_type(test_dict, str) is False
    assert validator._validate_type(test_dict, dict) is True
    assert validator._validate_type(test_dict, list) is False

    test_list = list()
    assert validator._validate_type(test_list, str) is False
    assert validator._validate_type(test_list, dict) is False
    assert validator._validate_type(test_list, list) is True


def test_validate_required_keys():
    test_dict = {
        'a': 10,
        'b': 20,
        'c': 30
    }
    assert validator._validate_required_keys(
        test_dict,
        [{'key': 'a'}]
    ) is True
    assert validator._validate_required_keys(
        test_dict,
        [{'key': 'b'}, {'key': 'c'}]
    ) is True
    assert validator._validate_required_keys(
        test_dict,
        [{'key': 'a', 'type': 'author'}]
    ) is False
    assert validator._validate_required_keys(
        test_dict,
        [{'key': 'missing_key'}]
    ) is False


def test_validate():
    assert validator.validate(valid_values) is True
    invalid_values = valid_values.copy()
    del invalid_values['authors']
    with pytest.raises(RequiredFieldError):
        validator.validate(invalid_values)
