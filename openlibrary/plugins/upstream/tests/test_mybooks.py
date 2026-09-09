"""Tests for the template helpers in openlibrary.plugins.upstream.mybooks."""

from unittest.mock import patch

import web

from openlibrary.plugins.upstream.mybooks import edition_key_of, reading_state_for, shelf_button_for, work_key_of


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
