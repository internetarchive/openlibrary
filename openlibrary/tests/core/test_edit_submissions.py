import pytest

from openlibrary.core.edit_submissions import (
    EditOutcome,
    apply_edit_submission,
    apply_patch,
    extract_patch,
    is_edit_submission,
    validate_edit_submission,
)


class TestIsEditSubmission:
    def test_record_with_key_is_an_edit(self):
        assert is_edit_submission({"key": "/books/OL1M", "v": "1", "title": "x"}) is True

    def test_record_without_key_is_an_import(self):
        # Today's new-record import shape -- no `key`.
        assert is_edit_submission({"title": "x", "source_records": ["amazon:1"]}) is False

    def test_empty_key_is_not_an_edit(self):
        assert is_edit_submission({"key": "", "title": "x"}) is False

    def test_non_dict_is_not_an_edit(self):
        assert is_edit_submission(["key"]) is False
        assert is_edit_submission(None) is False


class TestValidateEditSubmission:
    def test_valid_submission_has_no_errors(self):
        assert validate_edit_submission({"key": "/books/OL1M", "v": "3", "title": "x"}) == []

    def test_integer_v_is_accepted(self):
        assert validate_edit_submission({"key": "/books/OL1M", "v": 3, "title": "x"}) == []

    def test_missing_key_is_an_error(self):
        errors = validate_edit_submission({"v": "3", "title": "x"})
        assert any("key" in e for e in errors)

    def test_key_without_leading_slash_is_an_error(self):
        errors = validate_edit_submission({"key": "books/OL1M", "v": "3", "title": "x"})
        assert any("key" in e for e in errors)

    def test_missing_base_version_is_an_error(self):
        errors = validate_edit_submission({"key": "/books/OL1M", "title": "x"})
        assert any("`v`" in e or "version" in e for e in errors)

    def test_non_integer_version_is_an_error(self):
        errors = validate_edit_submission({"key": "/books/OL1M", "v": "latest", "title": "x"})
        assert any("version" in e for e in errors)

    def test_empty_patch_is_an_error(self):
        # Only control fields, nothing to change.
        errors = validate_edit_submission({"key": "/books/OL1M", "v": "3"})
        assert any("change at least one field" in e for e in errors)


class TestExtractPatch:
    def test_strips_control_and_structural_fields(self):
        record = {
            "key": "/books/OL1M",
            "v": "3",
            "type": {"key": "/type/edition"},
            "revision": 3,
            "created": {"value": "..."},
            "title": "New title",
            "subjects": ["a"],
        }
        assert extract_patch(record) == {"title": "New title", "subjects": ["a"]}


class TestApplyPatch:
    def test_scalar_field_is_replaced(self):
        doc = {"key": "/books/OL1M", "title": "Old", "revision": 1}
        assert apply_patch(doc, {"title": "New"})["title"] == "New"

    def test_patch_does_not_mutate_input_doc(self):
        doc = {"key": "/books/OL1M", "title": "Old"}
        apply_patch(doc, {"title": "New"})
        assert doc["title"] == "Old"

    def test_reserved_fields_in_patch_are_ignored(self):
        doc = {"key": "/books/OL1M", "revision": 5, "title": "Old"}
        merged = apply_patch(doc, {"revision": 99, "key": "/books/EVIL", "title": "New"})
        assert merged["revision"] == 5
        assert merged["key"] == "/books/OL1M"
        assert merged["title"] == "New"

    def test_list_field_is_union_added_not_replaced(self):
        doc = {"key": "/books/OL1M", "subjects": ["Fiction", "History"]}
        merged = apply_patch(doc, {"subjects": ["History", "Science"]})
        # Existing members kept; new member appended; no duplicate.
        assert merged["subjects"] == ["Fiction", "History", "Science"]

    def test_list_of_references_union_add(self):
        doc = {"key": "/works/OL1W", "authors": [{"key": "/authors/OL1A"}]}
        merged = apply_patch(doc, {"authors": [{"key": "/authors/OL1A"}, {"key": "/authors/OL2A"}]})
        assert merged["authors"] == [{"key": "/authors/OL1A"}, {"key": "/authors/OL2A"}]

    def test_new_field_is_added(self):
        doc = {"key": "/books/OL1M", "title": "T"}
        assert apply_patch(doc, {"subtitle": "S"})["subtitle"] == "S"


@pytest.mark.usefixtures("mock_site")
class TestApplyEditSubmission:
    def _save(self, mock_site, key, **fields):
        mock_site.save({"key": key, "type": {"key": "/type/edition"}, **fields})

    def test_applies_patch_when_version_matches(self, mock_site):
        self._save(mock_site, "/books/OL1M", title="Old title")  # revision 1
        result = apply_edit_submission({"key": "/books/OL1M", "v": "1", "title": "New title"})
        assert result.outcome == EditOutcome.APPLIED
        doc = mock_site.get("/books/OL1M")
        assert doc.title == "New title"
        assert doc.revision == 2  # a new version was written

    def test_attributing_comment_is_recorded(self, mock_site):
        self._save(mock_site, "/books/OL1M", title="Old")
        apply_edit_submission(
            {"key": "/books/OL1M", "v": "1", "title": "New"},
            comment="BookWorm edit via Openshelf (patron p42)",
        )
        assert mock_site.changesets[-1]["comment"] == "BookWorm edit via Openshelf (patron p42)"

    def test_conflict_when_live_version_has_drifted(self, mock_site):
        self._save(mock_site, "/books/OL1M", title="v1")  # revision 1
        mock_site.save({"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "v2"})  # revision 2
        result = apply_edit_submission({"key": "/books/OL1M", "v": "1", "title": "patch"})
        assert result.outcome == EditOutcome.CONFLICT
        # Live doc is untouched.
        assert mock_site.get("/books/OL1M").title == "v2"

    def test_missing_target_is_reported(self, mock_site):
        result = apply_edit_submission({"key": "/books/OL404M", "v": "1", "title": "x"})
        assert result.outcome == EditOutcome.MISSING

    def test_invalid_submission_is_reported_and_not_saved(self, mock_site):
        self._save(mock_site, "/books/OL1M", title="Old")
        result = apply_edit_submission({"key": "/books/OL1M", "title": "no version"})
        assert result.outcome == EditOutcome.INVALID
        assert mock_site.get("/books/OL1M").revision == 1  # unchanged
