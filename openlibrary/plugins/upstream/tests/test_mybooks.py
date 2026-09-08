"""Tests for the template helpers in openlibrary.plugins.upstream.mybooks."""

from unittest.mock import patch

import web

from openlibrary.plugins.upstream.mybooks import reading_state_for, work_key_of


class Thing:
    """The bits of an infogami Thing these helpers touch."""

    def __init__(self, key, works=None):
        self.key = key
        self.works = works

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
