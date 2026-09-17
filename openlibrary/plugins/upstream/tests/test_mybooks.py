from unittest.mock import patch

from openlibrary.core.booknotes import Booknotes
from openlibrary.plugins.upstream.mybooks import PatronBooknotes


def _make_user(mock_site):
    mock_site.save({"key": "/people/testuser", "type": {"key": "/type/user"}})
    return mock_site.get("/people/testuser")


def _make_notes_data(*entries):
    """Build the raw list-of-dicts format that Booknotes.get_notes_grouped_by_work returns."""
    return [{"work_id": wid, "notes": notes} for wid, notes in entries]


def _make_patron_booknotes(mock_site):
    return PatronBooknotes(_make_user(mock_site))


def _save_fixtures(mock_site):
    mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Test Work"})
    mock_site.save({"key": "/books/OL123M", "type": {"key": "/type/edition"}, "title": "Edition 123"})
    mock_site.save({"key": "/books/OL456M", "type": {"key": "/type/edition"}, "title": "Edition 456"})


class TestGetNotes:
    def test_notes_grouped_into_dict_by_edition(self, mock_site):
        """Notes list-of-dicts is transformed into a dict keyed by edition_id."""
        _save_fixtures(mock_site)
        notes = _make_notes_data(
            (
                1,
                [
                    {"edition_id": 123, "notes": "note A"},
                    {"edition_id": 456, "notes": "note B"},
                ],
            ),
        )
        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes):
            result = _make_patron_booknotes(mock_site).get_notes()

        entry = result[0]
        assert entry["notes"] == {123: "note A", 456: "note B"}

    def test_work_and_editions_attached(self, mock_site):
        """Each entry carries the matching work and edition objects from the store."""
        _save_fixtures(mock_site)
        notes = _make_notes_data(
            (
                1,
                [
                    {"edition_id": 123, "notes": "note A"},
                    {"edition_id": 456, "notes": "note B"},
                ],
            ),
        )
        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes):
            result = _make_patron_booknotes(mock_site).get_notes()

        entry = result[0]
        assert entry["work_key"] == "/works/OL1W"
        assert entry["work"].key == "/works/OL1W"
        assert entry["work"].title == "Test Work"
        assert 123 in entry["editions"]
        assert 456 in entry["editions"]
        assert entry["editions"][123].key == "/books/OL123M"

    def test_work_level_note_excluded_from_editions(self, mock_site):
        """A note with NULL_EDITION_VALUE appears in notes but not in editions dict."""
        _save_fixtures(mock_site)
        notes = _make_notes_data(
            (
                1,
                [
                    {"edition_id": 123, "notes": "edition note"},
                    {"edition_id": Booknotes.NULL_EDITION_VALUE, "notes": "work-level note"},
                ],
            ),
        )
        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes):
            result = _make_patron_booknotes(mock_site).get_notes()

        entry = result[0]
        assert Booknotes.NULL_EDITION_VALUE in entry["notes"]
        assert entry["notes"][Booknotes.NULL_EDITION_VALUE] == "work-level note"
        assert Booknotes.NULL_EDITION_VALUE not in entry["editions"]

    def test_edition_not_in_store_is_none(self, mock_site):
        """An edition referenced in notes but absent from the store is represented as None."""
        mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "W"})
        notes = _make_notes_data(
            (
                1,
                [
                    {"edition_id": 999, "notes": "orphan note"},
                ],
            ),
        )
        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes):
            result = _make_patron_booknotes(mock_site).get_notes()

        entry = result[0]
        assert entry["notes"] == {999: "orphan note"}
        assert entry["editions"] == {999: None}

    def test_empty_notes_does_not_lookup_works_or_editions(self, mock_site, monkeypatch):
        get_many_calls = []
        original_get_many = mock_site.get_many

        def tracking_get_many(keys):
            get_many_calls.append(keys)
            return original_get_many(keys)

        monkeypatch.setattr(mock_site, "get_many", tracking_get_many)
        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=[]):
            result = _make_patron_booknotes(mock_site).get_notes()

        assert result == []
        assert get_many_calls == []

    def test_multiple_works(self, mock_site):
        """Each work gets its own entry with the correct work and edition objects."""
        mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Work One"})
        mock_site.save({"key": "/works/OL2W", "type": {"key": "/type/work"}, "title": "Work Two"})
        mock_site.save({"key": "/books/OL10M", "type": {"key": "/type/edition"}, "title": "Ed 10"})
        mock_site.save({"key": "/books/OL20M", "type": {"key": "/type/edition"}, "title": "Ed 20"})
        notes = _make_notes_data(
            (1, [{"edition_id": 10, "notes": "note on work 1"}]),
            (2, [{"edition_id": 20, "notes": "note on work 2"}]),
        )
        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes):
            result = _make_patron_booknotes(mock_site).get_notes()

        assert len(result) == 2
        assert result[0]["work_key"] == "/works/OL1W"
        assert result[0]["work"].title == "Work One"
        assert result[0]["notes"] == {10: "note on work 1"}
        assert result[1]["work_key"] == "/works/OL2W"
        assert result[1]["work"].title == "Work Two"
        assert result[1]["notes"] == {20: "note on work 2"}

    def test_empty_notes(self, mock_site):
        """When the patron has no notes, an empty list is returned."""
        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=[]):
            result = _make_patron_booknotes(mock_site).get_notes()
        assert result == []
