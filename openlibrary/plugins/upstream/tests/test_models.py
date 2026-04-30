"""
Capture some of the unintuitive aspects of Storage, Things, and Works
"""

import web
from infogami.infobase import client

import openlibrary.core.lists.model as list_model
from openlibrary.core.cache import _get_cache
from openlibrary.mocks.mock_infobase import MockSite

from .. import models


class TestModels:
    def setup_method(self, method):
        web.ctx.site = MockSite()

    def test_setup(self):
        expected_things = {
            "/type/edition": models.Edition,
            "/type/author": models.Author,
            "/type/work": models.Work,
            "/type/subject": models.Subject,
            "/type/place": models.SubjectPlace,
            "/type/person": models.SubjectPerson,
            "/type/user": models.User,
            "/type/list": list_model.List,
        }
        expected_changesets = {
            None: models.Changeset,
            "merge-authors": models.MergeAuthors,
            "undo": models.Undo,
            "add-book": models.AddBookChangeset,
            "lists": list_model.ListChangeset,
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

    def test_user_settings(self):
        user = models.User(web.ctx.site, "user")
        assert user.get_safe_mode() == ""
        user.save_preferences({"safe_mode": "yes"})
        assert user.get_safe_mode() == "yes"
        user.save_preferences({"safe_mode": "no"})
        assert user.get_safe_mode() == "no"
        user.save_preferences({"safe_mode": "yes"})
        assert user.get_safe_mode() == "yes"


class TestGetAvatarUrl:
    def setup_method(self, method):
        web.ctx.site = MockSite()
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
