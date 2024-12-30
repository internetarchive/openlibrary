import pytest
from pydantic import ValidationError

from openlibrary.plugins.importapi.import_validator import import_validator

# To import, records must be complete, or they must have a title and strong identifier.
# They must also have a source_records field.

# The required fields for a import with a complete record.
complete_values = {
    "title": "Beowulf",
    "source_records": ["key:value"],
    "authors": [{"name": "Tom Robbins"}, {"name": "Dean Koontz"}],
    "publishers": ["Harper Collins", "OpenStax"],
    "publish_date": "December 2018",
}

# The required fields for an import with a title and strong identifier.
valid_values_strong_identifier = {
    "title": "Beowulf",
    "source_records": ["key:value"],
    "isbn_13": ["0123456789012"],
}

validator = import_validator()


def test_validate_both_complete_and_strong():
    """
    A record that is both complete and that has a strong identifier should
    validate.
    """
    valid_record = complete_values.copy() | valid_values_strong_identifier.copy()
    assert validator.validate(valid_record) is True


@pytest.mark.parametrize(
    'field', ["title", "source_records", "authors", "publishers", "publish_date"]
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


class TestMinimalDifferentiableStrongIdRecord:
    """
    A minimal differentiable record has a:
        1. title;
        2. ISBN 10 or ISBN 13 or LCCN; and
        3. source_records entry.
    """

    @pytest.mark.parametrize(
        ("isbn", "differentiable"),
        [
            # ISBN 10 is a dictionary with a non-empty string.
            ({"isbn_10": ["0262670011"]}, True),
            # ISBN 13 is a dictionary with a non-empty string.
            ({"isbn_13": ["9780262670012"]}, True),
            # ISBN 10 is an empty string.
            ({"isbn_10": [""]}, False),
            # ISBN 13 is an empty string.
            ({"isbn_13": [""]}, False),
            # ISBN 10 is None.
            ({"isbn_10": [None]}, False),
            # ISBN 13 is None.
            ({"isbn_13": [None]}, False),
            # ISBN 10 is None.
            ({"isbn_10": None}, False),
            # ISBN 13 is None.
            ({"isbn_13": None}, False),
            # ISBN 10 is an empty list.
            ({"isbn_10": []}, False),
            # ISBN 13 is an empty list.
            ({"isbn_13": []}, False),
            # ISBN 10 is a string.
            ({"isbn_10": "0262670011"}, False),
            # ISBN 13 is a string.
            ({"isbn_13": "9780262670012"}, False),
            # There is no ISBN key.
            ({}, False),
        ],
    )
    def test_isbn_case(self, isbn: dict, differentiable: bool) -> None:
        """Test different ISBN values with the specified record."""
        record = {
            "title": "Word and Object",
            "source_records": ["bwb:0123456789012"],
        }
        record = record | isbn

        if differentiable:
            assert validator.validate(record) is True
        else:
            with pytest.raises(ValidationError):
                validator.validate(record)

    @pytest.mark.parametrize(
        ("lccn", "differentiable"),
        [
            # LCCN is a dictionary with a non-empty string.
            ({"lccn": ["60009621"]}, True),
            # LCCN is an empty string.
            ({"lccn": [""]}, False),
            # LCCN is None.
            ({"lccn": [None]}, False),
            # LCCN is None.
            ({"lccn": None}, False),
            # LCCN is an empty list.
            ({"lccn": []}, False),
            # LCCN is a string.
            ({"lccn": "60009621"}, False),
            # There is no ISBN key.
            ({}, False),
        ],
    )
    def test_lccn_case(self, lccn: dict, differentiable: bool) -> None:
        """Test different LCCN values with the specified record."""
        record = {
            "title": "Word and Object",
            "source_records": ["bwb:0123456789012"],
        }
        record = record | lccn

        if differentiable:
            assert validator.validate(record) is True
        else:
            with pytest.raises(ValidationError):
                validator.validate(record)


def test_minimal_complete_record() -> None:
    """
    A minimal complete record has a:
        1. title;
        2. authors;
        3. publishers;
        4. publish_date; and
        5. source_records entry.
    """
    record = {
        "title": "Word and Object",
        "authors": [{"name": "Williard Van Orman Quine"}],
        "publishers": ["MIT Press"],
        "publish_date": "1960",
        "source_records": ["bwb:0123456789012"],
    }

    assert validator.validate(record) is True


class TestRecordTooMinimal:
    """
    These records are incomplete because they lack one or more required fields.
    """

    @pytest.mark.parametrize(
        "authors",
        [
            # No `name` key.
            ({"authors": [{"not_name": "Willard Van Orman Quine"}]}),
            # Not a list.
            ({"authors": {"name": "Williard Van Orman Quine"}}),
            # `name` value isn't a string.
            ({"authors": [{"name": 1}]}),
            # Name is None.
            ({"authors": {"name": None}}),
            # No authors key.
            ({}),
        ],
    )
    def test_record_must_have_valid_author(self, authors) -> None:
        """Only authors of the shape [{"name": "Williard Van Orman Quine"}] will validate."""
        record = {
            "title": "Word and Object",
            "publishers": ["MIT Press"],
            "publish_date": "1960",
            "source_records": ["bwb:0123456789012"],
        }

        record = record | authors

        with pytest.raises(ValidationError):
            validator.validate(record)

    @pytest.mark.parametrize(
        ("publish_date"),
        [
            # publish_date is an int.
            ({"publish_date": 1960}),
            # publish_date is None.
            ({"publish_date": None}),
            # no publish_date.
            ({}),
        ],
    )
    def test_must_have_valid_publish_date_type(self, publish_date) -> None:
        """Only records with string publish_date fields are valid."""
        record = {
            "title": "Word and Object",
            "authors": [{"name": "Willard Van Orman Quine"}],
            "publishers": ["MIT Press"],
            "source_records": ["bwb:0123456789012"],
        }

        record = record | publish_date

        with pytest.raises(ValidationError):
            validator.validate(record)


@pytest.mark.parametrize(
    ("publish_date"),
    [
        ({"publish_date": "1900"}),
        ({"publish_date": "January 1, 1900"}),
        ({"publish_date": "1900-01-01"}),
        ({"publish_date": "01-01-1900"}),
        ({"publish_date": "????"}),
    ],
)
def test_records_with_substantively_bad_dates_should_not_validate(
    publish_date: dict,
) -> None:
    """
    Certain publish_dates are known to be suspect, so remove them prior to
    attempting validation. If a date is removed, the record will fail to validate
    as a complete record (but could still validate with title + ISBN).
    """
    record = {
        "title": "Word and Object",
        "authors": [{"name": "Williard Van Orman Quine"}],
        "publishers": ["MIT Press"],
        "source_records": ["bwb:0123456789012"],
    }

    record = record | publish_date

    with pytest.raises(ValidationError):
        validator.validate(record)


@pytest.mark.parametrize(
    ("authors", "should_error"),
    [
        ({"authors": [{"name": "N/A"}, {"name": "Willard Van Orman Quine"}]}, False),
        ({"authors": [{"name": "Unknown"}]}, True),
        ({"authors": [{"name": "unknown"}]}, True),
        ({"authors": [{"name": "n/a"}]}, True),
    ],
)
def test_records_with_substantively_bad_authors_should_not_validate(
    authors: dict, should_error: bool
) -> None:
    """
    Certain author names are known to be bad and should be removed prior to
    validation. If all author names are removed the record will not validate
    as complete.
    """
    record = {
        "title": "Word and Object",
        "publishers": ["MIT Press"],
        "publish_date": "1960",
        "source_records": ["bwb:0123456789012"],
    }

    record = record | authors

    if should_error:
        with pytest.raises(ValidationError):
            validator.validate(record)
    else:
        assert validator.validate(record) is True
