"""Tests for edit submissions on the /api/import endpoint (#14750).

The batch-review drain (manage-imports -> /api/import) applies queued items by
POSTing their data to ``importapi``. An edit submission (a patch on an existing
versioned record) must be applied against the live document here rather than
mis-parsed as an incomplete new-record import.
"""

import contextlib
import json

import pytest
import web

from openlibrary.plugins.importapi import code


class TestTryJsonObject:
    def test_parses_a_json_object(self):
        assert code._try_json_object(b'{"key": "/books/OL1M"}') == {"key": "/books/OL1M"}

    def test_rejects_non_object_json(self):
        assert code._try_json_object(b"[1, 2, 3]") is None

    def test_rejects_non_json(self):
        assert code._try_json_object(b"00123cam a2200000") is None
        assert code._try_json_object(b"<?xml version='1.0'?>") is None

    def test_rejects_malformed_json(self):
        assert code._try_json_object(b'{"key": ') is None


@pytest.mark.usefixtures("mock_site")
class TestImportApiEditDispatch:
    def _post(self, monkeypatch, mock_site, body: dict, preview: bool = False):
        monkeypatch.setattr(code, "can_write", lambda: True)
        monkeypatch.setattr(web, "header", lambda *a, **k: None)
        monkeypatch.setattr(web, "data", lambda: json.dumps(body).encode("utf-8"))
        monkeypatch.setattr(web, "input", lambda *a, **k: web.storage(preview="true" if preview else "false"))
        return code.importapi().POST()

    def test_applies_edit_when_version_matches(self, monkeypatch, mock_site):
        mock_site.save({"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "Old"})  # rev 1
        reply = self._post(monkeypatch, mock_site, {"key": "/books/OL1M", "v": "1", "title": "New"})
        parsed = json.loads(reply)
        assert parsed["success"] is True
        assert parsed["edition"] == {"key": "/books/OL1M", "status": "modified"}
        assert mock_site.get("/books/OL1M").title == "New"

    def test_version_conflict_is_an_error_and_does_not_mutate(self, monkeypatch, mock_site):
        mock_site.save({"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "v1"})
        mock_site.save({"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "v2"})  # rev 2
        with pytest.raises(web.HTTPError) as exc_info:
            self._post(monkeypatch, mock_site, {"key": "/books/OL1M", "v": "1", "title": "patch"})
        assert json.loads(exc_info.value.data)["error_code"] == "version-conflict"
        assert mock_site.get("/books/OL1M").title == "v2"  # untouched

    def test_missing_target_is_an_error(self, monkeypatch, mock_site):
        with pytest.raises(web.HTTPError) as exc_info:
            self._post(monkeypatch, mock_site, {"key": "/books/OL404M", "v": "1", "title": "x"})
        assert json.loads(exc_info.value.data)["error_code"] == "edit-target-missing"

    def test_preview_does_not_mutate(self, monkeypatch, mock_site):
        mock_site.save({"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "Old"})
        reply = self._post(monkeypatch, mock_site, {"key": "/books/OL1M", "v": "1", "title": "New"}, preview=True)
        assert json.loads(reply)["edit"]["status"] == "preview"
        assert mock_site.get("/books/OL1M").title == "Old"  # unchanged
        assert mock_site.get("/books/OL1M").revision == 1

    def test_non_edit_json_still_goes_to_the_import_parser(self, monkeypatch, mock_site):
        # A new-record import (no top-level `key`) must not be treated as an edit.
        # It should reach parse_data; signal that by making parse_data observable.
        called = {}
        monkeypatch.setattr(code, "parse_data", lambda data: (called.setdefault("hit", True), (None, None))[1])
        # parse_data returning (None, None) triggers an error response; that's fine.
        with contextlib.suppress(web.HTTPError):
            self._post(monkeypatch, mock_site, {"title": "A new book", "source_records": ["amazon:1"]})
        assert called.get("hit") is True
