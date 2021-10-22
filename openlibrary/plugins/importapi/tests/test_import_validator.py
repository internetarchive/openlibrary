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
    assert validator._validate_title(valid_values["title"]) is True
    assert validator._validate_title("") is False
    assert validator._validate_title(['a']) is False


def test_validate_source_records():
    # source_records must be a non-empty list of strings
    assert validator._validate_source_records(
        valid_values["source_records"]
    ) is True
    assert validator._validate_source_records([]) is False
    assert validator._validate_source_records(17) is False


def test_validate_author():
    # Author is a dict with key-value pair ("name" : str)
    assert validator._validate_author(valid_values["author"]) is True
    assert validator._validate_author({"name": 17}) is False
    assert validator._validate_author({"title": "Duke"}) is False
    assert validator._validate_author({}) is False
    assert validator._validate_author("Dean Koontz") is False


def test_validate_author_list():
    # The author list must be non-empty and contain only valid authors
    assert validator._validate_authors(valid_values["authors"]) is True
    assert validator._validate_authors(
        [
            {"name": "Tom Robbins"},
            {"title": "Sir"}
        ]
    ) is False
    assert validator._validate_authors([]) is False
    assert validator._validate_authors("") is False
    assert validator._validate_authors(17) is False


def test_validate_publisher_list():
    # Publisher lists must be non-empty and contain only strings
    assert validator._validate_publishers(valid_values["publishers"]) is True
    assert validator._validate_publishers(["Harper Collins"]) is True
    assert validator._validate_publishers([]) is False
    assert validator._validate_publishers([17]) is False
    assert validator._validate_publishers("Harper Collins") is False


def test_validate_publish_date():
    # Publish date must be a date string
    assert validator._validate_publish_date(
        valid_values["publish_date"]
    ) is True
    assert validator._validate_publish_date("2018") is True
    assert validator._validate_publish_date(2018) is False
    assert validator._validate_publish_date("") is False


def test_validate():
    assert validator.validate(valid_values) is True
    invalid_values = valid_values.copy()
    del invalid_values['authors']
    assert validator.validate(invalid_values) is False
