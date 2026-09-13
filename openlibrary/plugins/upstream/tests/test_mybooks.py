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

    def _save_editions(self, mock_site, *keys):
        for key in keys:
            mock_site.save(
                {
                    "key": f"/books/OL{key}M",
                    "type": {"key": "/type/edition"},
                    "title": f"Edition {key}",
                }
            )

    def _record_get_many_calls(self, mock_site):
        get_many_calls = []
        original_get_many = mock_site.get_many

        def counting_get_many(keys):
            get_many_calls.append(list(keys))
            return original_get_many(keys)

        mock_site.get_many = counting_get_many
        return get_many_calls

    def test_get_notes_fetches_works_and_editions_via_single_get_many_batches(self, mock_site):
        self._save_fixtures(mock_site)
        get_many_calls = self._record_get_many_calls(mock_site)

        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=_make_notes_data()):
            result = _make_patron_booknotes(mock_site).get_notes()

        non_empty_calls = [keys for keys in get_many_calls if keys]
        assert non_empty_calls == [["/works/OL1W"], ["/books/OL123M", "/books/OL456M"]]

        entry = result[0]
        assert entry["work_key"] == "/works/OL1W"
        assert entry["work"].title == "Test Work"
        assert entry["work_details"]["title"] == "Test Work"
        assert set(entry["editions"]) == {123, 456}
        assert entry["editions"][123].title == "Edition 123"
        assert entry["editions"][456].title == "Edition 456"

    def test_get_notes_batches_multiple_work_lookups_and_preserves_ordering(self, mock_site):
        mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Work One"})
        mock_site.save({"key": "/works/OL2W", "type": {"key": "/type/work"}, "title": "Work Two"})

        notes_data = [
            {"work_id": 1, "notes": [{"edition_id": 123, "notes": "note 123"}]},
            {"work_id": 2, "notes": [{"edition_id": 456, "notes": "note 456"}]},
        ]

        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes_data):
            result = _make_patron_booknotes(mock_site).get_notes()

        assert [entry["work"].title for entry in result] == ["Work One", "Work Two"]
        assert [entry["work"] for entry in result] == [
            mock_site.get("/works/OL1W"),
            mock_site.get("/works/OL2W"),
        ]

    def test_get_notes_batches_editions_across_entries_in_single_get_many(self, mock_site):
        mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Work One"})
        mock_site.save({"key": "/works/OL2W", "type": {"key": "/type/work"}, "title": "Work Two"})
        self._save_editions(mock_site, 123, 456, 789)

        notes_data = [
            {
                "work_id": 1,
                "notes": [{"edition_id": 123, "notes": "note 123"}, {"edition_id": 456, "notes": "note 456"}],
            },
            {"work_id": 2, "notes": [{"edition_id": 789, "notes": "note 789"}]},
        ]
        get_many_calls = self._record_get_many_calls(mock_site)

        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes_data):
            result = _make_patron_booknotes(mock_site).get_notes()

        non_empty_calls = [keys for keys in get_many_calls if keys]
        assert non_empty_calls == [
            ["/works/OL1W", "/works/OL2W"],
            ["/books/OL123M", "/books/OL456M", "/books/OL789M"],
        ]

        assert result[0]["work_key"] == "/works/OL1W"
        assert result[1]["work_key"] == "/works/OL2W"
        assert set(result[0]["editions"]) == {123, 456}
        assert result[0]["editions"][123].title == "Edition 123"
        assert result[0]["editions"][456].title == "Edition 456"
        assert set(result[1]["editions"]) == {789}
        assert result[1]["editions"][789].title == "Edition 789"

    def test_get_notes_deduplicates_edition_keys_across_entries(self, mock_site):
        mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Work One"})
        mock_site.save({"key": "/works/OL2W", "type": {"key": "/type/work"}, "title": "Work Two"})
        self._save_editions(mock_site, 123)

        notes_data = [
            {"work_id": 1, "notes": [{"edition_id": 123, "notes": "note 123 (work 1)"}]},
            {"work_id": 2, "notes": [{"edition_id": 123, "notes": "note 123 (work 2)"}]},
        ]
        get_many_calls = self._record_get_many_calls(mock_site)

        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes_data):
            result = _make_patron_booknotes(mock_site).get_notes()

        non_empty_calls = [keys for keys in get_many_calls if keys]
        assert non_empty_calls == [["/works/OL1W", "/works/OL2W"], ["/books/OL123M"]]

        first = result[0]["editions"][123]
        second = result[1]["editions"][123]
        assert first is second
        assert first.title == "Edition 123"

    def test_get_notes_entries_with_no_valid_editions(self, mock_site):
        mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Work One"})

        notes_data = [
            {
                "work_id": 1,
                "notes": [{"edition_id": Booknotes.NULL_EDITION_VALUE, "notes": "work-level note"}],
            },
        ]
        get_many_calls = self._record_get_many_calls(mock_site)

        with patch.object(Booknotes, "get_notes_grouped_by_work", return_value=notes_data):
            result = _make_patron_booknotes(mock_site).get_notes()

        non_empty_calls = [keys for keys in get_many_calls if keys]
        assert non_empty_calls == [["/works/OL1W"]]

        entry = result[0]
        assert entry["editions"] == {}
        assert entry["notes"] == {Booknotes.NULL_EDITION_VALUE: "work-level note"}

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
