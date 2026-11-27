import pytest

from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme, partial_date_bounds


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1842", ("1842-01-01T00:00:00Z", "1843-01-01T00:00:00Z")),
        ("673", ("0673-01-01T00:00:00Z", "0674-01-01T00:00:00Z")),
        ("1842-05", ("1842-05-01T00:00:00Z", "1842-06-01T00:00:00Z")),
        ("1842-12", ("1842-12-01T00:00:00Z", "1843-01-01T00:00:00Z")),
        ("1842-05-31", ("1842-05-31T00:00:00Z", "1842-06-01T00:00:00Z")),
        ("18*", ("1800-01-01T00:00:00Z", "1900-01-01T00:00:00Z")),
        ("184*", ("1840-01-01T00:00:00Z", "1850-01-01T00:00:00Z")),
        ("9*", ("9000-01-01T00:00:00Z", "*")),
        ("264BC", ("-0263-01-01T00:00:00Z", "-0262-01-01T00:00:00Z")),
        ("1 bce", ("0000-01-01T00:00:00Z", "0001-01-01T00:00:00Z")),
        ("9999", None),
        ("0", None),
        ("1842-13", None),
        ("1842-02-30", None),
        ("1842-01-01T00:00:00Z", None),
        ("*", None),
        ("Twain", None),
    ],
)
def test_partial_date_bounds(value, expected):
    assert partial_date_bounds(value) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("birth_timestamp:1842", "birth_timestamp:[1842-01-01T00:00:00Z TO 1843-01-01T00:00:00Z}"),
        ('birth_timestamp:"1842"', "birth_timestamp:[1842-01-01T00:00:00Z TO 1843-01-01T00:00:00Z}"),
        ("death_timestamp:1910-04", "death_timestamp:[1910-04-01T00:00:00Z TO 1910-05-01T00:00:00Z}"),
        ("birth_timestamp:18*", "birth_timestamp:[1800-01-01T00:00:00Z TO 1900-01-01T00:00:00Z}"),
        # Inclusive bounds cover the whole period; exclusive ones exclude it
        ("birth_timestamp:[1800 TO 1900]", "birth_timestamp:[1800-01-01T00:00:00Z TO 1901-01-01T00:00:00Z}"),
        ("birth_timestamp:{1800 TO 1900}", "birth_timestamp:[1801-01-01T00:00:00Z TO 1900-01-01T00:00:00Z}"),
        ("birth_timestamp:[* TO 1000]", "birth_timestamp:[* TO 1001-01-01T00:00:00Z}"),
        ("birth_timestamp:[1800-01-01T00:00:00Z TO 1900]", "birth_timestamp:[1800-01-01T00:00:00Z TO 1901-01-01T00:00:00Z}"),
        (
            "birth_timestamp:(1842 OR 1850)",
            "birth_timestamp:([1842-01-01T00:00:00Z TO 1843-01-01T00:00:00Z} OR [1850-01-01T00:00:00Z TO 1851-01-01T00:00:00Z})",
        ),
        ("Twain birth_timestamp:18*", "Twain birth_timestamp:[1800-01-01T00:00:00Z TO 1900-01-01T00:00:00Z}"),
        ("birth_timestamp:[500BC TO 1]", "birth_timestamp:[-0499-01-01T00:00:00Z TO 0002-01-01T00:00:00Z}"),
        ('birth_timestamp:"264 BC"', "birth_timestamp:[-0263-01-01T00:00:00Z TO -0262-01-01T00:00:00Z}"),
        # Left alone
        ("birth_timestamp:[1800-01-01T00:00:00Z TO *]", "birth_timestamp:[1800-01-01T00:00:00Z TO *]"),
        ("birth_timestamp:[* TO *]", "birth_timestamp:[* TO *]"),
        ("birth_date:1842", "birth_date:1842"),
        ("1842", "1842"),
    ],
)
def test_date_field_transform(query, expected):
    assert AuthorSearchScheme(lang="en").process_user_query(query) == expected
