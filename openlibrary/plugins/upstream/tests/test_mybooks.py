"""Tests for the template helpers in openlibrary.plugins.upstream.mybooks."""

from unittest.mock import patch

import web

from infogami.infobase.client import LazyObject
from openlibrary.core.booknotes import Booknotes
from openlibrary.plugins.upstream.mybooks import PatronBooknotes, edition_key_of, reading_state_for, shelf_button_for, work_key_of


class Thing:
    """The bits of an infogami Thing these helpers touch."""

    def __init__(self, key, works=None, title=None):
        self.key = key
        self.works = works
        self.title = title

    def get(self, name, default=None):
        return getattr(self, name, default)


class TestWorkKeyOf:
    def test_a_solr_work_doc_is_its_own_work(self):
        assert work_key_of(web.storage(key="/works/OL1W")) == "/works/OL1W"

    def test_a_plain_dict_works_too(self):
        assert work_key_of({"key": "/works/OL1W"}) == "/works/OL1W"

    def test_an_edition_points_at_its_work(self):
        assert work_key_of(Thing("/books/OL2M", works=[Thing("/works/OL1W")])) == "/works/OL1W"
        assert work_key_of({"key": "/books/OL2M", "works": [{"key": "/works/OL1W"}]}) == "/works/OL1W"

    def test_anything_without_a_work_has_no_key(self):
        assert work_key_of(Thing("/books/OL2M")) is None
        assert work_key_of(Thing("/authors/OL3A")) is None
        assert work_key_of({}) is None

    def test_a_carousel_hands_an_edition_doc_its_work(self):
        assert work_key_of({"key": "/books/OL2M", "work_key": "/works/OL1W"}) == "/works/OL1W"


class TestEditionKeyOf:
    def test_an_edition_is_its_own(self):
        assert edition_key_of(Thing("/books/OL2M")) == "/books/OL2M"
        assert edition_key_of({"key": "/books/OL2M", "work_key": "/works/OL1W"}) == "/books/OL2M"

    def test_a_solr_result_selected_an_edition(self):
        assert edition_key_of({"key": "/works/OL1W", "editions": [{"key": "/books/OL2M"}]}) == "/books/OL2M"
        assert edition_key_of({"key": "/works/OL1W", "editions": {"docs": [web.storage(key="/books/OL2M")]}}) == "/books/OL2M"

    def test_a_logged_edition_beats_the_first_edition_key(self):
        assert edition_key_of({"key": "/works/OL1W", "logged_edition": "/books/OL9M", "edition_key": ["OL2M"]}) == "/books/OL9M"
        assert edition_key_of({"key": "/works/OL1W", "edition_key": ["OL2M", "OL3M"]}) == "/books/OL2M"

    def test_none_without_one(self):
        assert edition_key_of({"key": "/works/OL1W"}) is None
        assert edition_key_of({"key": "/works/OL1W", "editions": LazyObject(lambda: [Thing("/books/OL2M")])}) is None
        assert edition_key_of(Thing("/works/OL1W")) is None


FINISHED = {"shelf": 3, "rating": 4, "read_date": "2026-08", "event_id": 7}


class TestShelfButtonFor:
    def render(self, doc, **kwargs):
        with (
            patch("openlibrary.plugins.upstream.mybooks.accounts.get_current_user", return_value=web.storage(key="/people/tester")),
            patch("openlibrary.plugins.upstream.mybooks.get_reading_state", return_value={1: FINISHED}) as get_state,
        ):
            html = shelf_button_for(doc, **kwargs)
        return html, get_state

    def test_nothing_for_a_doc_that_is_neither_book_nor_author(self):
        html, get_state = self.render(Thing("/subjects/fantasy"))
        assert html == ""
        assert shelf_button_for({}) == ""
        get_state.assert_not_called()

    def test_a_row_gets_the_reader_and_their_state(self):
        html, _ = self.render(web.storage(key="/works/OL1W", title="Dune", edition_key=["OL2M"]))
        assert 'variant="split"' in html
        assert 'work-key="/works/OL1W"' in html
        assert 'book-title="Dune"' in html
        assert 'edition-key="OL2M"' in html
        assert 'user-key="/people/tester"' in html
        assert "data-hydrated" in html
        assert 'shelf="3"' in html
        assert 'rating="4"' in html
        assert 'read-date="2026-08" event-id="7"' in html

    def test_the_page_state_is_used_when_given(self):
        html, get_state = self.render(web.storage(key="/works/OL1W", title="Dune"), reading_state={"/works/OL1W": {"shelf": 1}})
        assert 'shelf="1"' in html
        get_state.assert_not_called()

    def test_an_edition_shelves_its_work_under_the_work_title(self):
        html, _ = self.render(Thing("/books/OL2M", works=[Thing("/works/OL1W", title="Dune")], title="Dune (1st ed.)"))
        assert 'work-key="/works/OL1W"' in html
        assert 'edition-key="OL2M"' in html
        assert 'book-title="Dune"' in html

    def test_a_cached_card_carries_no_reader(self):
        html, get_state = self.render({"key": "/books/OL2M", "work_key": "/works/OL1W", "title": "Dune"}, variant="icon", cached=True)
        assert 'variant="icon"' in html
        assert 'edition-key="OL2M"' in html
        assert "user-key" not in html
        assert "data-hydrated" not in html
        assert "shelf=" not in html
        get_state.assert_not_called()

    def test_the_title_is_escaped(self):
        html, _ = self.render(web.storage(key="/works/OL1W", title='Say "hi" <b>'))
        assert 'book-title="Say &#34;hi&#34; &lt;b&gt;"' in html

    def test_an_author_gets_the_lists_only_control_under_their_name(self):
        # An author's `title` is an honorific, not a name.
        html, get_state = self.render(web.storage(key="/authors/OL3A", name="Ursula K. Le Guin", title="OBE"))
        assert "lists-only" in html
        assert 'work-key="/authors/OL3A"' in html
        assert 'book-title="Ursula K. Le Guin"' in html
        assert 'user-key="/people/tester"' in html
        assert "edition-key" not in html
        assert "shelf=" not in html
        get_state.assert_not_called()

    def test_an_orphaned_edition_can_only_join_a_list(self):
        html, _ = self.render(Thing("/books/OL2M", title="Orphan"))
        assert "lists-only" in html
        assert 'work-key="/books/OL2M"' in html
        assert "edition-key" not in html


class TestReadingStateFor:
    def test_signed_out_is_empty_without_querying(self):
        with (
            patch("openlibrary.plugins.upstream.mybooks.accounts.get_current_user", return_value=None),
            patch("openlibrary.plugins.upstream.mybooks.get_reading_state") as get_state,
        ):
            assert reading_state_for([{"key": "/works/OL1W"}]) == {}
        get_state.assert_not_called()

    def test_keys_the_result_by_work_key(self):
        docs = [
            web.storage(key="/works/OL1W"),
            Thing("/books/OL5M", works=[Thing("/works/OL2W")]),
            Thing("/authors/OL3A"),
            web.storage(key="/works/OL1W"),  # the same work twice on a page
        ]
        states = {
            1: {"shelf": 1, "rating": None, "read_date": None, "event_id": None},
            2: {"shelf": None, "rating": 3, "read_date": None, "event_id": None},
        }
        with (
            patch("openlibrary.plugins.upstream.mybooks.accounts.get_current_user", return_value=web.storage(key="/people/tester")),
            patch("openlibrary.plugins.upstream.mybooks.get_reading_state", return_value=states) as get_state,
        ):
            result = reading_state_for(docs)

        assert result == {"/works/OL1W": states[1], "/works/OL2W": states[2]}
        username, work_ids = get_state.call_args.args
        assert username == "tester"
        assert sorted(work_ids) == [1, 2]


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
