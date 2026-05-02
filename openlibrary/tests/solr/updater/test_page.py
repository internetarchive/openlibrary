import pytest
from unittest.mock import MagicMock

from openlibrary.solr.updater.page import PageSolrBuilder, PageSolrUpdater
from openlibrary.plugins.worksearch.schemes.pages import PageSearchScheme


# ---------------------------------------------------------------------------
# PageSolrBuilder
# ---------------------------------------------------------------------------


class TestPageSolrBuilder:
    def _make(self, data: dict) -> PageSolrBuilder:
        return PageSolrBuilder(data)

    def test_build_full_document(self):
        page = {
            "key": "/librarians",
            "type": {"key": "/type/page"},
            "title": "Librarians",
            "body": {"value": "Welcome to the librarians page."},
            "last_modified": {"value": "2023-01-01T00:00:00"},
        }
        doc = self._make(page).build()
        assert doc["key"] == "/librarians"
        assert doc["type"] == "page"
        assert doc["title"] == "Librarians"
        assert doc["body"] == "Welcome to the librarians page."
        assert doc["last_modified"] == "2023-01-01T00:00:00Z"

    def test_body_as_plain_string(self):
        page = {"key": "/about", "type": {"key": "/type/page"}, "body": "plain text"}
        doc = self._make(page).build()
        assert doc["body"] == "plain text"

    def test_body_missing(self):
        page = {"key": "/about", "type": {"key": "/type/page"}}
        doc = self._make(page).build()
        assert "body" not in doc

    def test_title_missing(self):
        page = {"key": "/about", "type": {"key": "/type/page"}}
        doc = self._make(page).build()
        assert "title" not in doc

    def test_last_modified_as_dict(self):
        page = {
            "key": "/about",
            "type": {"key": "/type/page"},
            "last_modified": {"value": "2023-06-01T12:00:00"},
        }
        doc = self._make(page).build()
        assert doc["last_modified"] == "2023-06-01T12:00:00Z"

    def test_last_modified_as_plain_string_without_z(self):
        page = {
            "key": "/about",
            "type": {"key": "/type/page"},
            "last_modified": "2023-06-01T12:00:00",
        }
        doc = self._make(page).build()
        assert doc["last_modified"] == "2023-06-01T12:00:00Z"

    def test_last_modified_as_plain_string_already_has_z(self):
        page = {
            "key": "/about",
            "type": {"key": "/type/page"},
            "last_modified": "2023-06-01T12:00:00Z",
        }
        doc = self._make(page).build()
        assert doc["last_modified"] == "2023-06-01T12:00:00Z"

    def test_last_modified_missing(self):
        page = {"key": "/about", "type": {"key": "/type/page"}}
        doc = self._make(page).build()
        assert "last_modified" not in doc

    def test_type_is_always_page_string(self):
        page = {"key": "/about", "type": {"key": "/type/page"}}
        doc = self._make(page).build()
        assert doc["type"] == "page"

    def test_key_required(self):
        page = {"key": "/help/faq", "type": {"key": "/type/page"}}
        doc = self._make(page).build()
        assert doc["key"] == "/help/faq"

    def test_last_modified_as_dict_already_has_z(self):
        page = {"key": "/about",
                "type": {"key": "/type/page"},
                "last_modified": {"value": "2023-06-01T12:00:00Z"},
                }
        doc = self._make(page).build()
        assert doc["last_modified"] == "2023-06-01T12:00:00Z"


# ---------------------------------------------------------------------------
# PageSolrUpdater.key_test
# ---------------------------------------------------------------------------


class TestPageSolrUpdaterKeyTest:
    def setup_method(self):
        self.updater = PageSolrUpdater(data_provider=MagicMock())

    def test_accepts_simple_page_key(self):
        assert self.updater.key_test("/librarians") is True

    def test_accepts_nested_page_key(self):
        assert self.updater.key_test("/help/faq") is True

    def test_rejects_works(self):
        assert self.updater.key_test("/works/OL123W") is False

    def test_rejects_books(self):
        assert self.updater.key_test("/books/OL123M") is False

    def test_rejects_authors(self):
        assert self.updater.key_test("/authors/OL123A") is False

    def test_rejects_type_prefix(self):
        assert self.updater.key_test("/type/page") is False

    def test_rejects_people(self):
        assert self.updater.key_test("/people/testuser") is False

    def test_rejects_lists(self):
        assert self.updater.key_test("/lists/OL123L") is False

    def test_rejects_languages(self):
        assert self.updater.key_test("/languages/eng") is False

    def test_rejects_subjects(self):
        assert self.updater.key_test("/subjects/history") is False

    def test_rejects_search(self):
        assert self.updater.key_test("/search") is False

    def test_rejects_admin(self):
        assert self.updater.key_test("/admin/anything") is False

    def test_rejects_series(self):
        assert self.updater.key_test("/series/OL123S") is False

    def test_rejects_publishers(self):
        assert self.updater.key_test("/publishers/OL123P") is False

    def test_rejects_collections(self):
        assert self.updater.key_test("/collections/OL123C") is False

# ---------------------------------------------------------------------------
# PageSolrUpdater.update_key
# ---------------------------------------------------------------------------


class TestPageSolrUpdaterUpdateKey:
    def setup_method(self):
        self.updater = PageSolrUpdater(data_provider=MagicMock())

    @pytest.mark.asyncio
    async def test_returns_empty_for_wrong_type(self):
        thing = {"key": "/about", "type": {"key": "/type/work"}}
        req, keys = await self.updater.update_key(thing)
        assert req.adds == []
        assert keys == []

    @pytest.mark.asyncio
    async def test_returns_doc_for_page_type(self):
        thing = {
            "key": "/about",
            "type": {"key": "/type/page"},
            "title": "About",
            "body": {"value": "About Open Library."},
        }
        req, keys = await self.updater.update_key(thing)
        assert len(req.adds) == 1
        assert req.adds[0]["key"] == "/about"
        assert req.adds[0]["title"] == "About"
        assert keys == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_missing_type(self):
        thing = {"key": "/about"}
        req, keys = await self.updater.update_key(thing)
        assert req.adds == []
        assert keys == []

# ---------------------------------------------------------------------------
# PageSearchScheme
# ---------------------------------------------------------------------------


class TestPageSearchScheme:
    def setup_method(self):
        self.scheme = PageSearchScheme()

    def test_universe_filters_to_type_page(self):
        assert 'type:page' in self.scheme.universe

    def test_q_to_solr_params_uses_edismax(self):
        params = self.scheme.q_to_solr_params('librarians', set(), [])
        param_dict = dict(params)
        assert param_dict['defType'] == 'edismax'

    def test_q_to_solr_params_searches_body_and_title(self):
        params = self.scheme.q_to_solr_params('librarians', set(), [])
        param_dict = dict(params)
        assert 'body' in param_dict['qf']
        assert 'title' in param_dict['qf']

    def test_q_to_solr_params_uses_and_operator(self):
        params = self.scheme.q_to_solr_params('help faq', set(), [])
        param_dict = dict(params)
        assert param_dict['q.op'] == 'AND'

    def test_default_fetched_fields_excludes_body(self):
        # body can be very large; it should not be fetched by default
        assert 'body' not in self.scheme.default_fetched_fields

    def test_default_fetched_fields_includes_key_and_title(self):
        assert 'key' in self.scheme.default_fetched_fields
        assert 'title' in self.scheme.default_fetched_fields

    def test_no_facet_fields(self):
        assert len(self.scheme.facet_fields) == 0

    def test_q_to_solr_params_boosts_title(self):
        params = self.scheme.q_to_solr_params('librarians', set(), [])
        param_dict = dict(params)
        assert 'title^5' in param_dict['qf']

    def test_q_to_solr_params_filters_to_page_type(self):
        params = self.scheme.q_to_solr_params('librarians', set(), [])
        fq_values = [v for k, v in params if k == 'fq']
        assert 'type:page' in fq_values
