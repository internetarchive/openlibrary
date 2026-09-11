from unittest.mock import patch

from openlibrary.core.booknotes import Booknotes
from openlibrary.plugins.upstream.mybooks import PatronBooknotes


def _make_user(mock_site):
    mock_site.save({"key": "/people/testuser", "type": {"key": "/type/user"}})
    return mock_site.get("/people/testuser")


def _make_notes_data():
    return [
        {
            "work_id": 1,
            "notes": [
                {"edition_id": 123, "notes": "note for 123"},
                {"edition_id": 456, "notes": "note for 456"},
                {"edition_id": Booknotes.NULL_EDITION_VALUE, "notes": "work-level note"},
            ],
        }
    ]


def _make_patron_booknotes(mock_site):
    return PatronBooknotes(_make_user(mock_site))


class TestGetNotes:
    def _save_fixtures(self, mock_site):
        mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Test Work"})
        mock_site.save(
            {
                "key": "/books/OL123M",
                "type": {"key": "/type/edition"},
                "title": "Edition 123",
            }
        )
        mock_site.save(
            {
                "key": "/books/OL456M",
                "type": {"key": "/type/edition"},
                "title": "Edition 456",
            }
        )

    def test_get_notes_fetches_editions_with_single_get_many_call(self, mock_site):
        self._save_fixtures(mock_site)

        get_many_calls = []
        original_get_many = mock_site.get_many

        def counting_get_many(keys):
            get_many_calls.append(list(keys))
            return original_get_many(keys)

        mock_site.get_many = counting_get_many

        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=_make_notes_data()):
            result = _make_patron_booknotes(mock_site).get_notes()

        non_empty_calls = [keys for keys in get_many_calls if keys]
        assert non_empty_calls == [["/books/OL123M", "/books/OL456M"]]

        entry = result[0]
        assert set(entry["editions"]) == {123, 456}
        assert entry["editions"][123].title == "Edition 123"
        assert entry["editions"][456].title == "Edition 456"

    def test_get_notes_skips_null_edition_and_missing_editions(self, mock_site):
        self._save_fixtures(mock_site)

        notes_data = [
            {
                "work_id": 1,
                "notes": [
                    {"edition_id": 123, "notes": "note for 123"},
                    {"edition_id": 999, "notes": "note for missing edition"},
                    {"edition_id": Booknotes.NULL_EDITION_VALUE, "notes": "work-level note"},
                ],
            }
        ]

        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes_data):
            result = _make_patron_booknotes(mock_site).get_notes()

        entry = result[0]
        assert set(entry["editions"]) == {123}
        assert entry["editions"][123].title == "Edition 123"
