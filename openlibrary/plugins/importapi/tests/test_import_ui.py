import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from openlibrary.catalog import add_book
from openlibrary.plugins.importapi import import_ui
from openlibrary.plugins.importapi.code import BookImportError
from openlibrary.plugins.importapi.import_ui import GutenbergMetadataProvider, ImportPreviewRequest, RawJsonMetadataProvider

GUTENBERG_SAMPLE = Path(__file__).parents[3] / "bookworm" / "tests" / "samples" / "gutenberg.json"


@pytest.fixture
def fetched(monkeypatch):
    """Serve the sample publication, recording the URL fetched and the record loaded."""
    calls: dict = {}
    publication = json.loads(GUTENBERG_SAMPLE.read_text())[0]

    def get(url, timeout):
        calls["url"] = url
        response = MagicMock()
        response.json.return_value = publication
        return response

    session = MagicMock()
    session.get.side_effect = get
    monkeypatch.setattr("openlibrary.bookworm.harvest.build_session", lambda: session)

    def load(rec, account_key, save):
        calls["record"] = rec
        calls["save"] = save
        return {"success": True}

    monkeypatch.setattr(import_ui.add_book, "load", load)
    return calls


@pytest.mark.parametrize(
    "identifier",
    ["67979", " 67979 ", "https://www.gutenberg.org/ebooks/67979", "http://gutenberg.org/ebooks/67979/"],
)
def test_gutenberg_preview_fetches_the_publication(fetched, identifier):
    GutenbergMetadataProvider().do_import(identifier, save=False)

    assert fetched["url"] == "https://opds-test.pglaf.org/opds/publications?id=67979"
    assert fetched["save"] is False
    rec = fetched["record"]
    assert rec["identifiers"] == {"project_gutenberg": ["67979"]}
    assert rec["source_records"] == ["project_gutenberg:67979"]
    assert rec["acquisitions"]


@pytest.mark.parametrize("identifier", ["", "abc", "pg67979", "https://evil.test/ebooks/67979"])
def test_gutenberg_preview_rejects_bad_ids(fetched, identifier):
    with pytest.raises(ValueError, match="Invalid Project Gutenberg id"):
        GutenbergMetadataProvider().do_import(identifier, save=False)
    assert "url" not in fetched


def test_gutenberg_is_selectable_by_source_prefix():
    req = ImportPreviewRequest.from_input({"source": "project_gutenberg:67979"})
    assert isinstance(req.metadata_provider, GutenbergMetadataProvider)
    assert req.identifier == "67979"


@pytest.fixture
def loaded(monkeypatch):
    calls: dict = {}

    def load(rec, account_key, save):
        calls["record"] = rec
        calls["save"] = save
        return {"success": True}

    monkeypatch.setattr(import_ui.add_book, "load", load)
    return calls


def test_raw_json_preview_loads_the_record(loaded):
    rec = {
        "title": "A Book",
        "authors": [{"name": "Some Author"}],
        "publish_date": "2001",
        "publishers": ["Pub"],
        "source_records": ["test:123"],
    }
    RawJsonMetadataProvider().do_import(json.dumps(rec, indent=2), save=False)

    assert loaded["save"] is False
    assert loaded["record"]["title"] == "A Book"
    assert loaded["record"]["source_records"] == ["test:123"]


@pytest.mark.parametrize(
    ("identifier", "error"),
    [
        ("", "Invalid JSON"),
        ("not json", "Invalid JSON"),
        ("<?xml version='1.0'?><a/>", "Invalid JSON"),
        ("[1, 2]", "must be a JSON object"),
    ],
)
def test_raw_json_preview_rejects_non_objects(loaded, identifier, error):
    with pytest.raises(ValueError, match=error):
        RawJsonMetadataProvider().do_import(identifier, save=False)
    assert "record" not in loaded


def test_raw_json_is_selectable_by_source_prefix():
    req = ImportPreviewRequest.from_input({"source": 'json:{"title": "a:b"}'})
    assert isinstance(req.metadata_provider, RawJsonMetadataProvider)
    assert req.identifier == '{"title": "a:b"}'


def _failing_request(exc: Exception) -> ImportPreviewRequest:
    provider = MagicMock()
    provider.id_name = "ia"
    provider.do_import.side_effect = exc
    return ImportPreviewRequest(metadata_provider=provider, identifier="foo", save=False)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            BookImportError("not-differentiable", "publishers: Field required"),
            {"success": False, "error_code": "not-differentiable", "error": "publishers: Field required"},
        ),
        (ValueError("Invalid JSON"), {"success": False, "error": "Invalid JSON"}),
        (
            add_book.RequiredFields(["title"]),
            {"success": False, "error_code": "unhandled-exception", "error": "Unexpected RequiredFields; details have been logged."},
        ),
    ],
)
def test_run_reports_import_failures(exc, expected):
    assert _failing_request(exc).run() == expected
