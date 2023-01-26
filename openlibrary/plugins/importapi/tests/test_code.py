from .. import code
from openlibrary.catalog.add_book.tests.conftest import add_languages
import web
import pytest


def test_get_ia_record(monkeypatch, mock_site, add_languages) -> None:  # noqa F811
    """
    Try to test every field that get_ia_record() reads.
    """
    monkeypatch.setattr(web, "ctx", web.storage())
    web.ctx.lang = "eng"
    web.ctx.site = mock_site

    ia_metadata = {
        "creator": "Drury, Bob",
        "date": "2013",
        "description": [
            "The story of the great Ogala Sioux chief Red Cloud",
        ],
        "identifier": "heartofeverythin0000drur_j2n5",
        "isbn": [
            "9781451654684",
            "1451654685",
        ],
        "language": "French",
        "lccn": "2013003200",
        "oclc-id": "1226545401",
        "publisher": "New York : Simon & Schuster",
        "subject": [
            "Red Cloud, 1822-1909",
            "Oglala Indians",
        ],
        "title": "The heart of everything that is",
        "imagecount": "454",
    }

    expected_result = {
        "authors": [{"name": "Drury, Bob"}],
        "description": ["The story of the great Ogala Sioux chief Red Cloud"],
        "isbn_10": ["1451654685"],
        "isbn_13": ["9781451654684"],
        "languages": ["fre"],
        "lccn": ["2013003200"],
        "number_of_pages": 450,
        "oclc": "1226545401",
        "publish_date": "2013",
        "publish_places": ["New York"],
        "publishers": ["Simon & Schuster"],
        "subjects": ["Red Cloud, 1822-1909", "Oglala Indians"],
        "title": "The heart of everything that is",
    }

    result = code.ia_importapi.get_ia_record(ia_metadata)
    assert result == expected_result


def test_get_ia_record_handles_string_publishers(monkeypatch, mock_site) -> None:
    """Some IA records have a single string for the publisher, but it should be a list."""
    monkeypatch.setattr(web, "ctx", web.storage())
    web.ctx.lang = "eng"
    web.ctx.site = mock_site

    # Testing publisher is a string.
    ia_metadata = {
        "creator": "The Author",
        "date": "2013",
        "identifier": "ia_frisian001",
        "publisher": "The Publisher",
        "title": "Frisian is Fun",
    }

    expected_result = {
        "authors": [{"name": "The Author"}],
        "publish_date": "2013",
        "publishers": ["The Publisher"],
        "title": "Frisian is Fun",
    }

    result = code.ia_importapi.get_ia_record(ia_metadata)
    assert result == expected_result

    # Testing publisher is a list.
    ia_metadata = {
        "creator": "The Author",
        "date": "2013",
        "identifier": "ia_frisian001",
        "publisher": ["The Publisher"],  # type: ignore [dict-item]
        "title": "Frisian is Fun",
    }

    expected_result = {
        "authors": [{"name": "The Author"}],
        "publish_date": "2013",
        "publishers": ["The Publisher"],
        "title": "Frisian is Fun",
    }

    result = code.ia_importapi.get_ia_record(ia_metadata)
    assert result == expected_result


def test_get_ia_record_handles_isbn_10_and_isbn_13() -> None:
    """
    IA records have an `isbn` field with potentially both ISBN 10 and ISBN 13.
    But Open Library needs them sorted into `isbn_10` and `isbn_13` lists.
    """
    ia_metadata = {
        "creator": "The Author",
        "date": "2013",
        "identifier": "ia_frisian001",
        "isbn": ["1280711191", "9781280711190", "1576079457", "9781576079454"],
        "publisher": ["The Publisher"],
        "title": "Frisian is Fun",
    }

    expected_result = {
        "authors": [{"name": "The Author"}],
        "publish_date": "2013",
        "isbn_10": ["1280711191", "1576079457"],
        "isbn_13": ["9781280711190", "9781576079454"],
        "publishers": ["The Publisher"],
        "title": "Frisian is Fun",
    }

    result = code.ia_importapi.get_ia_record(ia_metadata)
    assert result == expected_result


def test_get_ia_record_handles_publishers_with_places() -> None:
    """
    Some IA records have the format:
        "publisher": "New York : Simon & Schuster"

    Split on ` : ` and put the place into `publish_places: list[str]`
    """
    ia_metadata = {
        "creator": "The Author",
        "date": "2013",
        "identifier": "ia_frisian001",
        "publisher": ["New York : Simon & Schuster"],
        "title": "Frisian is Fun",
    }

    expected_result = {
        "authors": [{"name": "The Author"}],
        "publish_date": "2013",
        "publishers": ["Simon & Schuster"],
        "publish_places": ["New York"],
        "title": "Frisian is Fun",
    }

    result = code.ia_importapi.get_ia_record(ia_metadata)
    assert result == expected_result


@pytest.mark.parametrize(
    "tc,exp",
    [("Frisian", "Multiple language matches"), ("Fake Lang", "No language matches")],
)
def test_get_ia_record_logs_warning_when_language_has_multiple_matches(
    mock_site, monkeypatch, add_languages, caplog, tc, exp  # noqa F811
) -> None:
    """
    When the IA record uses the language name rather than the language code,
    get_ia_record() should log a warning if there are multiple name matches,
    and set no language for the edition.
    """
    monkeypatch.setattr(web, "ctx", web.storage())
    web.ctx.lang = "eng"
    web.ctx.site = mock_site

    ia_metadata = {
        "creator": "The Author",
        "date": "2013",
        "identifier": "ia_frisian001",
        "language": f"{tc}",
        "publisher": "The Publisher",
        "title": "Frisian is Fun",
    }

    expected_result = {
        "authors": [{"name": "The Author"}],
        "publish_date": "2013",
        "publishers": ["The Publisher"],
        "title": "Frisian is Fun",
    }

    result = code.ia_importapi.get_ia_record(ia_metadata)

    assert result == expected_result
    assert exp in caplog.text


@pytest.mark.parametrize("tc,exp", [(5, 1), (4, 4), (3, 3)])
def test_get_ia_record_handles_very_short_books(tc, exp) -> None:
    """
    Because scans have extra images for the cover, etc, and the page count from
    the IA metadata is based on `imagecount`, 4 pages are subtracted from
    number_of_pages. But make sure this doesn't go below 1.
    """
    ia_metadata = {
        "creator": "The Author",
        "date": "2013",
        "identifier": "ia_frisian001",
        "imagecount": f"{tc}",
        "publisher": "The Publisher",
        "title": "Frisian is Fun",
    }

    result = code.ia_importapi.get_ia_record(ia_metadata)
    assert result.get("number_of_pages") == exp
