import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from openlibrary.plugins.importapi import import_ui
from openlibrary.plugins.importapi.import_ui import GutenbergMetadataProvider, ImportPreviewRequest

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
