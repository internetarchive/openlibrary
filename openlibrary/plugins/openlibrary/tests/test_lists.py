import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import web
from starlette.datastructures import URL

from openlibrary.plugins.openlibrary import lists as legacy_lists
from openlibrary.plugins.openlibrary.lists import ListRecord


class TestListRecord:
    def test_from_input_no_data(self):
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
        ):
            mock_web_data.return_value = b""
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": [],
            }
            assert ListRecord.from_input() == ListRecord(
                key=None,
                name="foo",
                description="bar",
                seeds=[],
            )

    def test_from_input_with_data(self):
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
            patch("web.ctx") as mock_web_ctx,
        ):
            mock_web_ctx.env = {}
            mock_web_data.return_value = b"key=/lists/OL1L&name=foo+data&description=bar&seeds--0--key=/books/OL1M&seeds--1--key=/books/OL2M"
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": [],
            }
            assert ListRecord.from_input() == ListRecord(
                key="/lists/OL1L",
                name="foo data",
                description="bar",
                seeds=[{"key": "/books/OL1M"}, {"key": "/books/OL2M"}],
            )

    def test_from_input_with_json_data(self):
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
            patch("web.ctx") as mock_web_ctx,
        ):
            mock_web_ctx.env = {"CONTENT_TYPE": "application/json"}
            mock_web_data.return_value = json.dumps(
                {
                    "name": "foo data",
                    "description": "bar",
                    "seeds": [{"key": "/books/OL1M"}, {"key": "/books/OL2M"}],
                }
            ).encode("utf-8")
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": [],
            }
            assert ListRecord.from_input() == ListRecord(
                key=None,
                name="foo data",
                description="bar",
                seeds=[{"key": "/books/OL1M"}, {"key": "/books/OL2M"}],
            )

    SEED_TESTS: tuple = (
        ([], []),
        (["OL1M"], [{"key": "/books/OL1M"}]),
        (["OL1M", "OL2M"], [{"key": "/books/OL1M"}, {"key": "/books/OL2M"}]),
        (["OL1M,OL2M"], [{"key": "/books/OL1M"}, {"key": "/books/OL2M"}]),
    )

    @pytest.mark.parametrize(("seeds", "expected"), SEED_TESTS)
    def test_from_input_seeds(self, seeds, expected):
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
        ):
            mock_web_data.return_value = b""
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": seeds,
            }
            assert ListRecord.from_input() == ListRecord(
                key=None,
                name="foo",
                description="bar",
                seeds=expected,
            )

    def test_normalize_input_seed(self):
        f = ListRecord.normalize_input_seed

        assert f("/books/OL1M") == {"key": "/books/OL1M"}
        assert f({"key": "/books/OL1M"}) == {"key": "/books/OL1M"}
        assert f("/subjects/love") == "subject:love"
        assert f("subject:love") == "subject:love"

    def test_normalize_input_seed_with_blank_key(self):
        """Test that normalize_input_seed rejects blank keys.

        Blank keys should raise a ValueError instead of
        being accepted and passed through to the database.
        """
        f = ListRecord.normalize_input_seed

        # Blank keys should now raise ValueError
        with pytest.raises(ValueError, match="Seed key cannot be empty"):
            f({"key": ""})

        # Valid keys should still work
        assert f({"key": "/books/OL1M"}) == {"key": "/books/OL1M"}

    def test_from_input_rejects_blank_keys(self):
        """Test that form submission rejects seeds with blank keys.

        Attempting to submit a form with blank keys
        should raise a ValueError during normalization.
        """
        with (
            patch("web.input") as mock_web_input,
            patch("web.data") as mock_web_data,
        ):
            mock_web_data.return_value = b""
            mock_web_input.return_value = {
                "key": None,
                "name": "foo",
                "description": "bar",
                "seeds": [
                    {"key": "/books/OL1M"},  # valid
                    {"key": ""},  # blank key - should raise error
                    {"key": "/books/OL2M"},  # valid
                ],
            }
            # Blank keys should now raise ValueError during normalization
            with pytest.raises(ValueError, match="Seed key cannot be empty"):
                ListRecord.from_input()


@pytest.mark.parametrize(
    ("seed", "expected", "error_match"),
    [
        pytest.param("/subjects/foo", "subject", None, id="subjects-path"),
        pytest.param("/authors/OL1A", "author", None, id="authors-path"),
        pytest.param("/works/OL1W", "work", None, id="works-path"),
        pytest.param("/books/OL1M", "edition", None, id="books-path"),
        pytest.param("subject:ibm_database_2.", "subject", None, id="subject-raw-string"),
        pytest.param("place:london", "subject", None, id="place-raw-string"),
        pytest.param("person:jane_austen", "subject", None, id="person-raw-string"),
        pytest.param("time:20th_century", "subject", None, id="time-raw-string"),
        pytest.param("", None, "Seed key cannot be empty", id="empty-string"),
        pytest.param("/people/alice", None, "Invalid seed key", id="invalid-path-prefix"),
        pytest.param("/lists/OL1L", None, "Invalid seed key", id="invalid-list-path"),
    ],
)
def test_seed_key_to_seed_type(seed, expected, error_match):
    if error_match:
        with pytest.raises(ValueError, match=error_match):
            legacy_lists.seed_key_to_seed_type(seed)
    else:
        assert legacy_lists.seed_key_to_seed_type(seed) == expected


class FakePreviewList:
    def __init__(self, key):
        self.key = key

    def preview(self):
        return {"key": self.key}


class FakeListsDoc:
    def __init__(self, count):
        self._lists = [FakePreviewList(f"/people/alice/lists/OL{index}L") for index in range(count)]

    def get_lists(self, limit=50, offset=0):
        return self._lists[offset : offset + limit]


class TestBuildPaginationLinks:
    """Tests for build_pagination_links function."""

    def test_first_page_has_next_no_prev(self):
        """First page with more results should have next, no prev."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=60, count=50, offset=0, limit=50)
        assert links == {
            "next": "/people/alice/lists.json?limit=50&offset=50",
        }

    def test_middle_page_has_both_next_and_prev(self):
        """A middle paginated page should have both next and prev."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=60, count=25, offset=25, limit=25)
        assert links == {
            "next": "/people/alice/lists.json?limit=25&offset=50",
            "prev": "/people/alice/lists.json?limit=25&offset=0",
        }

    def test_last_page_has_prev_no_next(self):
        """Last page should have prev, no next."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=60, count=10, offset=50, limit=50)
        assert links == {
            "prev": "/people/alice/lists.json?limit=50&offset=0",
        }

    def test_single_page_no_pagination(self):
        """When results fit on one page, no pagination links."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=30, count=30, offset=0, limit=50)
        assert links == {}

    def test_empty_results_no_pagination(self):
        """When there are no results, no pagination links."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=0, count=0, offset=0, limit=50)
        assert links == {}

    def test_prev_offset_never_negative(self):
        """Prev offset should be 0, not negative, when offset < limit."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists.json"), total=100, count=5, offset=5, limit=50)
        assert links["prev"] == "/people/alice/lists.json?limit=50&offset=0"

    def test_works_with_custom_endpoint_path(self):
        """Should work with any endpoint path (e.g., seed paths without .json)."""
        links = legacy_lists.build_pagination_links(URL("/people/alice/lists"), total=60, count=50, offset=0, limit=50)
        assert links == {
            "next": "/people/alice/lists?limit=50&offset=50",
        }

    def test_uses_count_not_limit_for_determining_more(self):
        """Pagination 'next' should depend on count returned, not limit."""
        # Even with limit=50, if only 5 items returned and total=60, there's more
        links = legacy_lists.build_pagination_links(URL("/works/OL42W/lists.json"), total=60, count=5, offset=0, limit=50)
        assert links == {
            "next": "/works/OL42W/lists.json?limit=50&offset=50",
        }


def test_get_lists_data_uses_lists_json_path_for_pagination_links():
    doc = FakeListsDoc(60)
    mock_site = Mock()
    mock_site.get.return_value = doc

    with patch("openlibrary.plugins.openlibrary.lists.site") as mock_site_context:
        mock_site_context.get.return_value = mock_site

        data = legacy_lists.lists_json.get_lists_data(
            "/people/alice",
            limit=50,
            offset=0,
            query_path="/people/alice/lists.json",
        )

    assert data["links"]["self"] == "/people/alice"
    assert data["links"]["next"] == "/people/alice/lists.json?limit=50&offset=50"


def _make_seed(key, type_, document=None):
    return SimpleNamespace(key=key, type=type_, document=document, notes=None, last_update=None)


class TestResolveListViewItems:
    """Unit tests for the seed -> Solr doc -> availability batching."""

    def test_empty_seeds_skips_solr_and_availability(self, monkeypatch):
        solr_mock = Mock()
        availability_mock = Mock()
        monkeypatch.setattr(legacy_lists, "get_solr_works", solr_mock)
        monkeypatch.setattr(legacy_lists, "get_availabilities", availability_mock)

        items = legacy_lists._resolve_list_view_items([])

        assert items == []
        solr_mock.assert_not_called()
        availability_mock.assert_not_called()

    def test_work_seed_resolved_via_solr(self, monkeypatch):
        work_doc = {"key": "/works/OL1W", "editions": {"docs": [{"key": "/books/OL1M"}]}}
        seed = _make_seed("/works/OL1W", "work")

        monkeypatch.setattr(legacy_lists, "get_solr_works", Mock(return_value={"/works/OL1W": work_doc}))
        monkeypatch.setattr(
            legacy_lists,
            "get_availabilities",
            Mock(return_value={"/books/OL1M": {"status": "available"}}),
        )

        items = legacy_lists._resolve_list_view_items([seed])

        assert len(items) == 1
        assert items[0].seed is seed
        assert items[0].doc == work_doc
        assert items[0].availability == {"status": "available"}

    def test_edition_seed_stays_edition_and_is_excluded_from_solr_query(self, monkeypatch):
        edition_doc = {"key": "/books/OL2M"}
        seed = _make_seed("/books/OL2M", "edition", document=edition_doc)

        solr_mock = Mock(return_value={})
        monkeypatch.setattr(legacy_lists, "get_solr_works", solr_mock)
        monkeypatch.setattr(
            legacy_lists,
            "get_availabilities",
            Mock(return_value={"/books/OL2M": {"status": "available"}}),
        )

        items = legacy_lists._resolve_list_view_items([seed])

        # get_solr_works is only ever queried with `work`-type seed keys
        solr_mock.assert_called_once_with(set(), editions=True)
        assert items[0].doc == edition_doc
        assert items[0].availability == {"status": "available"}

    def test_orphan_seed_falls_back_to_document_without_crashing(self, monkeypatch):
        seed = _make_seed("/works/OL3W", "work", document=None)

        monkeypatch.setattr(legacy_lists, "get_solr_works", Mock(return_value={}))
        monkeypatch.setattr(legacy_lists, "get_availabilities", Mock(return_value={}))

        items = legacy_lists._resolve_list_view_items([seed])

        assert items[0].doc is None
        assert items[0].availability is None

    def test_non_work_edition_seed_has_no_doc_or_availability(self, monkeypatch):
        seed = _make_seed("subject:foo", "subject")

        availability_mock = Mock(return_value={})
        monkeypatch.setattr(legacy_lists, "get_solr_works", Mock(return_value={}))
        monkeypatch.setattr(legacy_lists, "get_availabilities", availability_mock)

        items = legacy_lists._resolve_list_view_items([seed])

        assert items[0].doc is None
        assert items[0].availability is None
        # subject/person/place/time seeds never enter the availability batch
        availability_mock.assert_called_once_with([])

    def test_mixed_list_batches_availability_exactly_once(self, monkeypatch):
        work_doc = {"key": "/works/OL1W"}  # no editions block -> falls back to the work doc itself
        seeds = [
            _make_seed("/works/OL1W", "work"),
            _make_seed("/books/OL2M", "edition", document={"key": "/books/OL2M"}),
            _make_seed("subject:foo", "subject"),
        ]

        availability_mock = Mock(
            return_value={
                "/works/OL1W": {"status": "available"},
                "/books/OL2M": {"status": "borrowable"},
            }
        )
        monkeypatch.setattr(legacy_lists, "get_solr_works", Mock(return_value={"/works/OL1W": work_doc}))
        monkeypatch.setattr(legacy_lists, "get_availabilities", availability_mock)

        items = legacy_lists._resolve_list_view_items(seeds)

        assert availability_mock.call_count == 1
        assert [item.availability for item in items] == [
            {"status": "available"},
            {"status": "borrowable"},
            None,
        ]


class TestListViewGet:
    """Tests for the list_view HTML handler."""

    def test_non_html_encoding_returns_406(self, monkeypatch):
        monkeypatch.setattr(web.ctx, "encoding", "json", raising=False)

        with pytest.raises(web.HTTPError):
            legacy_lists.list_view().GET("/lists/OL1L")

    def test_missing_list_raises_notfound(self, monkeypatch):
        monkeypatch.setattr(web.ctx, "encoding", None, raising=False)
        monkeypatch.setattr(web, "input", lambda **kw: web.storage(v=None))
        monkeypatch.setattr(web.ctx, "headers", [], raising=False)

        mock_site = Mock()
        mock_site.get.return_value = None
        with patch("openlibrary.plugins.openlibrary.lists.site") as mock_site_context:
            mock_site_context.get.return_value = mock_site

            with pytest.raises(web.HTTPError):
                legacy_lists.list_view().GET("/lists/OL999L")

    def test_deleted_list_renders_delete_template_with_404(self, monkeypatch):
        monkeypatch.setattr(web.ctx, "encoding", None, raising=False)
        monkeypatch.setattr(web, "input", lambda **kw: web.storage(v=None))

        deleted = SimpleNamespace(type=SimpleNamespace(key="/type/delete"))
        mock_site = Mock()
        mock_site.get.return_value = deleted

        render_mock = Mock(return_value="rendered")
        with (
            patch("openlibrary.plugins.openlibrary.lists.site") as mock_site_context,
            patch("openlibrary.plugins.openlibrary.lists.render_template", render_mock),
        ):
            mock_site_context.get.return_value = mock_site

            result = legacy_lists.list_view().GET("/lists/OL1L")

        assert result == "rendered"
        render_mock.assert_called_once_with("type/delete/view", deleted)

    def test_only_current_page_seeds_are_resolved(self, monkeypatch):
        """Batch resolution must only ever see the seeds on the requested page."""
        monkeypatch.setattr(web.ctx, "encoding", None, raising=False)
        monkeypatch.setattr(web, "input", lambda **kw: web.storage(v=None, page="2", sort=None))

        all_seeds = [_make_seed(f"/works/OL{i}W", "work") for i in range(120)]
        lst = SimpleNamespace(
            type=SimpleNamespace(key="/type/list"),
            get_seeds=Mock(return_value=all_seeds),
        )
        mock_site = Mock()
        mock_site.get.return_value = lst

        resolve_mock = Mock(return_value=[])
        render_mock = Mock(return_value="rendered")
        with (
            patch("openlibrary.plugins.openlibrary.lists.site") as mock_site_context,
            patch("openlibrary.plugins.openlibrary.lists._resolve_list_view_items", resolve_mock),
            patch("openlibrary.plugins.openlibrary.lists.render_template", render_mock),
        ):
            mock_site_context.get.return_value = mock_site

            legacy_lists.list_view().GET("/lists/OL1L")

        # page=2 (1-indexed in the query string) -> zero-indexed page 1 ->
        # seeds[50:100], i.e. exactly LIST_VIEW_PAGE_SIZE items, never the full list.
        resolve_mock.assert_called_once_with(all_seeds[50:100])
        render_mock.assert_called_once_with("type/list/view", lst, [], 1, 50, None)

    def test_page_zero_query_param_preserves_preexisting_slicing_quirk(self, monkeypatch):
        """`?page=0` -> page=-1 -> a negative-start slice that yields no items.

        safeint(query_param('page'), 1) - 1 has no lower bound; the quirk is
        preserved intentionally rather than fixed as a silent side effect.
        """
        monkeypatch.setattr(web.ctx, "encoding", None, raising=False)
        monkeypatch.setattr(web, "input", lambda **kw: web.storage(v=None, page="0", sort=None))

        all_seeds = [_make_seed(f"/works/OL{i}W", "work") for i in range(10)]
        lst = SimpleNamespace(
            type=SimpleNamespace(key="/type/list"),
            get_seeds=Mock(return_value=all_seeds),
        )
        mock_site = Mock()
        mock_site.get.return_value = lst

        resolve_mock = Mock(return_value=[])
        render_mock = Mock(return_value="rendered")
        with (
            patch("openlibrary.plugins.openlibrary.lists.site") as mock_site_context,
            patch("openlibrary.plugins.openlibrary.lists._resolve_list_view_items", resolve_mock),
            patch("openlibrary.plugins.openlibrary.lists.render_template", render_mock),
        ):
            mock_site_context.get.return_value = mock_site

            legacy_lists.list_view().GET("/lists/OL1L")

        # page=0 -> page=-1 -> seeds[-50:0], which Python clamps to an empty
        # slice here.
        resolve_mock.assert_called_once_with(all_seeds[-50:0])
        assert all_seeds[-50:0] == []

    def test_non_view_mode_is_delegated_to_mode_machinery(self, monkeypatch):
        """?m=history (and any other non-view mode) is handed back to the
        mode machinery, which the page registration would otherwise shadow."""
        monkeypatch.setattr(web.ctx, "encoding", None, raising=False)
        monkeypatch.setattr(web, "input", lambda **kw: web.storage(v=None, m="history"))

        fake_mode = Mock()
        fake_mode.return_value.GET.return_value = "history page"
        monkeypatch.setattr(legacy_lists, "find_mode", lambda: (fake_mode, ["/lists/OL1L"]))

        result = legacy_lists.list_view().GET("/lists/OL1L")

        assert result == "history page"
        fake_mode.return_value.GET.assert_called_once_with("/lists/OL1L")

    def test_unknown_mode_redirects_to_default_view(self, monkeypatch):
        """An unregistered mode falls back the way delegate() does:
        seeother to m=None."""
        monkeypatch.setattr(web.ctx, "encoding", None, raising=False)
        monkeypatch.setattr(web.ctx, "path", "/lists/OL1L", raising=False)
        monkeypatch.setattr(web.ctx, "home", "", raising=False)
        monkeypatch.setattr(web.ctx, "headers", [], raising=False)
        monkeypatch.setattr(web, "input", lambda **kw: web.storage(v=None, m="bogus"))
        monkeypatch.setattr(web, "changequery", lambda **kw: "/lists/OL1L")
        monkeypatch.setattr(legacy_lists, "find_mode", lambda: (None, None))

        with pytest.raises(web.HTTPError) as excinfo:
            legacy_lists.list_view().GET("/lists/OL1L")

        assert excinfo.value.args[0] == "303 See Other"
        assert any(h[0] == "Location" and h[1] == "/lists/OL1L" for h in web.ctx.headers)

    def test_sort_last_modified_is_forwarded_to_get_seeds(self, monkeypatch):
        monkeypatch.setattr(web.ctx, "encoding", None, raising=False)
        monkeypatch.setattr(web, "input", lambda **kw: web.storage(v=None, page=None, sort="last_modified"))

        lst = SimpleNamespace(
            type=SimpleNamespace(key="/type/list"),
            get_seeds=Mock(return_value=[]),
        )
        mock_site = Mock()
        mock_site.get.return_value = lst

        with (
            patch("openlibrary.plugins.openlibrary.lists.site") as mock_site_context,
            patch("openlibrary.plugins.openlibrary.lists.render_template", Mock(return_value="rendered")),
        ):
            mock_site_context.get.return_value = mock_site

            legacy_lists.list_view().GET("/lists/OL1L")

        lst.get_seeds.assert_called_once_with(sort=True, resolve_redirects=True)
