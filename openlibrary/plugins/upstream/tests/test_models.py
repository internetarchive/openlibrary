"""
Capture some of the unintuitive aspects of Storage, Things, and Works
"""

from unittest.mock import Mock, patch

import pytest
import web

from infogami.infobase import client
from openlibrary.core.cache import _get_cache
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.utils.request_context import site as site_context

from .. import models


class TestModels:
    def setup_method(self, method):
        web.ctx.site = MockSite()
        self.site_token = site_context.set(web.ctx.site)

    def teardown_method(self):
        site_context.reset(self.site_token)

    def test_setup(self):
        expected_things = {
            "/type/edition": models.Edition,
            "/type/author": models.Author,
            "/type/work": models.Work,
            "/type/subject": models.Subject,
            "/type/place": models.SubjectPlace,
            "/type/person": models.SubjectPerson,
            "/type/user": models.User,
            "/type/tag": models.Tag,
        }
        expected_changesets = {
            None: models.Changeset,
            "merge-authors": models.MergeAuthors,
            "merge-works": models.MergeWorks,
            "undo": models.Undo,
            "add-book": models.AddBookChangeset,
            "new-account": models.NewAccountChangeset,
        }
        models.setup()
        for key, value in expected_things.items():
            assert client._thing_class_registry[key] == value
        for key, value in expected_changesets.items():
            assert client._changeset_class_register[key] == value

    def test_work_without_data(self):
        work = models.Work(web.ctx.site, "/works/OL42679M")
        assert repr(work) == str(work) == "<Work: '/works/OL42679M'>"
        assert isinstance(work, client.Thing)
        assert isinstance(work, models.Work)
        assert work._site == web.ctx.site
        assert work.key == "/works/OL42679M"
        assert work._data is None
        # assert isinstance(work.data, client.Nothing)  # Fails!
        # assert work.data is None  # Fails!
        # assert not work.hasattr('data')  # Fails!
        assert work._revision is None
        # assert work.revision is None  # Fails!
        # assert not work.revision('data')  # Fails!

    def test_work_with_data(self):
        work = models.Work(web.ctx.site, "/works/OL42679M", web.Storage())
        assert repr(work) == str(work) == "<Work: '/works/OL42679M'>"
        assert isinstance(work, client.Thing)
        assert isinstance(work, models.Work)
        assert work._site == web.ctx.site
        assert work.key == "/works/OL42679M"
        assert isinstance(work._data, web.Storage)
        assert isinstance(work._data, dict)
        assert hasattr(work, "data")
        assert isinstance(work.data, client.Nothing)

        assert hasattr(work, "any_attribute")  # hasattr() is True for all keys!
        assert isinstance(work.any_attribute, client.Nothing)
        assert repr(work.any_attribute) == "<Nothing>"
        assert str(work.any_attribute) == ""

        work.new_attribute = "new_attribute"
        assert isinstance(work.data, client.Nothing)  # Still Nothing
        assert work.new_attribute == "new_attribute"
        assert work["new_attribute"] == "new_attribute"
        assert work.get("new_attribute") == "new_attribute"

        assert not work.hasattr("new_attribute")
        assert work._data == {"new_attribute": "new_attribute"}
        assert repr(work.data) == "<Nothing>"
        assert str(work.data) == ""

        assert callable(work.get_sorted_editions)  # Issue #3633
        assert work.get_sorted_editions() == []

    def test_user_settings(self, mock_site):
        user = models.User(mock_site, "user")
        assert user.get_safe_mode() == ""
        user.save_preferences({"safe_mode": "yes"})
        assert user.get_safe_mode() == "yes"
        user.save_preferences({"safe_mode": "no"})
        assert user.get_safe_mode() == "no"
        user.save_preferences({"safe_mode": "yes"})
        assert user.get_safe_mode() == "yes"

    def test_save_preferences_ignores_unknown_keys(self, mock_site):
        user = models.User(mock_site, "user")
        user.save_preferences(
            {
                "public_readlog": "yes",
                "save": "Save",
                "debug": "true",
                "has_fulltext": "true",
            }
        )
        prefs = user.preferences()
        assert prefs.get("public_readlog") == "yes"
        assert "save" not in prefs
        assert "debug" not in prefs
        assert "has_fulltext" not in prefs

    def test_save_preferences_keeps_known_keys(self, mock_site):
        user = models.User(mock_site, "user")
        user.save_preferences({"updates": "yes", "pda": "pda", "rpd": "1", "yrg_banner_pref": "yrg26"})
        prefs = user.preferences()
        assert prefs["updates"] == "yes"
        assert prefs["pda"] == "pda"
        assert prefs["rpd"] == "1"
        assert prefs["yrg_banner_pref"] == "yrg26"


class TestGetAvatarUrl:
    def setup_method(self, method):
        web.ctx.site = MockSite()
        site_context.set(web.ctx.site)
        _get_cache("memcache").memcache.flush_all()

    def test_returns_correct_avatar_url(self):
        web.ctx.site.save({"key": "/people/testuser", "type": {"key": "/type/user"}})
        web.ctx.site.store["account/testuser"] = {
            "internetarchive_itemname": "@testuser-archive",
        }
        url = models.User.get_avatar_url("testuser")
        assert url == "https://archive.org/services/img/@testuser-archive"

    def test_caches_result_for_same_username(self, monkeypatch):
        web.ctx.site.save({"key": "/people/cachetest_user", "type": {"key": "/type/user"}})
        web.ctx.site.store["account/cachetest_user"] = {
            "internetarchive_itemname": "@cachetest_user-archive",
        }
        call_count = 0
        original_get = web.ctx.site.get

        def counting_get(key, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_get(key, *args, **kwargs)

        monkeypatch.setattr(web.ctx.site, "get", counting_get)
        models.User.get_avatar_url("cachetest_user")
        models.User.get_avatar_url("cachetest_user")
        assert call_count == 1

    def test_caches_independently_per_username(self):
        for username in ("alice", "bob"):
            web.ctx.site.save({"key": f"/people/{username}", "type": {"key": "/type/user"}})
            web.ctx.site.store[f"account/{username}"] = {
                "internetarchive_itemname": f"@{username}-archive",
            }
        assert models.User.get_avatar_url("alice") == "https://archive.org/services/img/@alice-archive"
        assert models.User.get_avatar_url("bob") == "https://archive.org/services/img/@bob-archive"


class TestEdition:
    def setup_method(self, method):
        web.ctx.site = MockSite()
        models.setup()

    def _make_edition(self, ocaid=None):
        data = {"key": "/books/OL1M", "type": {"key": "/type/edition"}}
        if ocaid:
            data["ocaid"] = ocaid
        web.ctx.site.save(data)
        return web.ctx.site.get("/books/OL1M")

    def test_get_available_loans_no_ocaid(self):
        ed = self._make_edition()
        assert ed.get_available_loans() == []

    def test_get_available_loans_returns_bookreader(self):
        ed = self._make_edition(ocaid="testitem00archive")
        with (
            patch("openlibrary.core.lending.is_loaned_out", return_value=False),
            patch("openlibrary.plugins.upstream.models.lending.is_loaned_out_on_ia", return_value=False),
        ):
            loans = ed.get_available_loans()
        assert len(loans) == 1
        assert loans[0]["resource_type"] == "bookreader"
        assert loans[0]["resource_id"] == "bookreader:testitem00archive"

    def test_get_available_loans_checked_out(self):
        ed = self._make_edition(ocaid="testitem00archive")
        with patch("openlibrary.core.lending.is_loaned_out", return_value=True):
            loans = ed.get_available_loans()
        assert loans == []

    def test_set_providers_rejects_an_unsafe_url(self):
        ed = self._make_edition()
        with pytest.raises(client.ClientException):
            ed.set_providers([{"url": "javascript:alert(1)", "format": "web"}])

    def test_set_providers_accepts_an_http_url(self):
        ed = self._make_edition()
        ed.set_providers([{"url": "https://example.com/b", "format": "web"}])
        assert ed.providers[0]["url"] == "https://example.com/b"

    def test_set_providers_allows_a_blank_url_row(self):
        # Empty rows are a normal artefact of the edit form; they are harmless
        # and must not break the save.
        ed = self._make_edition()
        ed.set_providers([{"url": "", "format": "web"}])
        assert ed.providers[0]["url"] == ""

    def test_get_ia_meta_fields_no_external_identifier(self):
        ed = self._make_edition(ocaid="testitem00archive")
        with patch("openlibrary.core.ia.get_metadata", return_value={"collection": ["inlibrary"]}):
            meta = ed.get_ia_meta_fields()
        assert "external-identifier" not in meta
        assert "collection" in meta


class TestSiteContextMigration:
    @pytest.fixture(params=["missing", "different"])
    def current(self, mock_site, monkeypatch, request):
        # Separate the handles so these tests cannot silently use the legacy site.
        if request.param == "missing":
            monkeypatch.delitem(web.ctx, "site")
        else:
            monkeypatch.setitem(web.ctx, "site", MockSite())
        return mock_site

    def test_follow_redirect_uses_current_site(self, current):
        current.quicksave("/authors/OL1A", "/type/redirect", location="/authors/OL2A")
        current.quicksave("/authors/OL2A", "/type/author", name="Current author")
        assert models.follow_redirect("/a/OL1A").name == "Current author"

    def test_work_editions_and_covers_use_current_site(self, current, monkeypatch):
        work = current.quicksave("/works/OL1W", "/type/work", title="Work", covers=[1])
        current.quicksave("/books/OL1M", "/type/edition", title="Older", works=[{"key": work.key}], publish_date="1990", covers=[2])
        current.quicksave("/books/OL2M", "/type/edition", title="Newer", works=[{"key": work.key}], publish_date="2020", covers=[1])
        work._solr_data = {"cover_edition_key": "OL1M"}
        monkeypatch.setattr(models.lending, "get_availability", lambda *args: {})
        assert [cover.id for cover in work.get_covers_from_solr()] == [2]
        assert [ed.key for ed in work.get_sorted_editions()] == ["/books/OL2M", "/books/OL1M"]
        assert [cover.id for cover in work.get_edition_covers()] == [2]

    def test_user_history_and_admin_info_use_current_site(self, current, monkeypatch):
        user = current.quicksave("/people/alice", "/type/user", displayname="Alice")
        history = [web.storage(ip="192.0.2.1", created="2020-01-01")]
        versions = Mock(return_value=history)
        count = Mock(return_value=7)
        monkeypatch.setattr(current, "versions", versions)
        monkeypatch.setattr(current, "_request", count, raising=False)
        monkeypatch.setitem(web.ctx, "path", "/admin/people/alice")
        assert user.get_edit_history(limit=5, offset=10) == history
        assert versions.call_args.args[0] == {"author": user.key, "limit": 5, "offset": 10}
        assert user.get_creation_info() == {"ip": "192.0.2.1", "member_since": "2020-01-01"}
        assert user.get_edit_count() == 7
        count.assert_called_once_with("/count_edits_by_user", data={"key": user.key})

    def test_changeset_undo_and_links_use_current_site(self, current, monkeypatch):
        current.quicksave("/works/OL1W", "/type/work", title="Before")
        current.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "After"}, comment="edit")
        change = current.get_change(current.changesets[-1]["id"])
        assert change.get_undo_error() is None
        change._undo()
        assert current.get("/works/OL1W").title == "Before"
        assert current.changesets[-1]["kind"] == "undo"
        assert current.changesets[-1]["comment"] == "undo edit"
        undo = models.Undo(current, current.changesets[-1])
        undo.data["undo_of"] = change.id
        assert undo.get_parent_changeset().id == change.id
        assert undo.get_undo_of().id == change.id
        recent = Mock(return_value=[undo])
        monkeypatch.setattr(current, "recentchanges", recent)
        assert change.get_undo_changeset() is undo
        recent.assert_called_once_with({"kind": "undo", "data": {"parent_changeset": change.id}})
