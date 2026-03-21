"""
Capture some of the unintuitive aspects of Storage, Things, and Works
"""

from datetime import datetime

import pytest
import web

import openlibrary.core.lists.model as list_model
from infogami.infobase import client
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
            "undo-single-duplicate": models.UndoSingleDuplicate,
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

    def _mock_recentchanges_func(self, query):
        kind = query.get("kind")
        data = query.get("data") or {}
        return [
            models.Changeset(web.ctx.site, changeset)
            for changeset in reversed(web.ctx.site.changesets)
            if (not kind or changeset.get("kind") == kind) and all(changeset.get("data", {}).get(k) == v for k, v in data.items())
        ]

    def _seed_single_duplicate_merge_change(self, duplicate_keys):
        site = web.ctx.site

        site.recentchanges = self._mock_recentchanges_func

        changes = []
        for duplicate_key in duplicate_keys:
            site.save({"key": duplicate_key, "type": {"key": "/type/work"}, "title": "Before merge"})
            site.save({"key": duplicate_key, "type": {"key": "/type/redirect"}, "location": "/works/OL1W"})
            changes.append(web.storage({"key": duplicate_key, "revision": 2}))

        merge_changeset = site._make_changeset(
            timestamp=datetime.now(),
            kind="merge-works",
            comment="merge works",
            data={"master": "/works/OL1W", "duplicates": duplicate_keys},
            changes=changes,
        )
        site.changesets.append(merge_changeset)
        return site.get_change(merge_changeset["id"])

    def _assert_single_duplicate_undo(self, change, before_count, result, duplicate_key):
        assert result is None
        assert len(web.ctx.site.changesets) == before_count + 1
        undo_changeset = web.ctx.site.changesets[-1]
        change_doc = undo_changeset["changes"][0]

        assert undo_changeset["kind"] == "undo-single-duplicate"
        assert undo_changeset["data"]["parent_changeset"] == change.id
        assert undo_changeset["data"]["duplicate_key"] == duplicate_key
        assert len(undo_changeset["changes"]) == 1
        assert change_doc["key"] == duplicate_key
        assert change_doc["revision"] == 3

    @pytest.mark.parametrize(
        ("duplicate_keys", "target_duplicate_key"),
        [
            (["/works/OL2W"], "/works/OL2W"),
            (["/works/OL2W", "/works/OL3W"], "/works/OL2W"),
        ],
    )
    def test_single_duplicate_undo_saves_changeset(self, duplicate_keys, target_duplicate_key):
        change = self._seed_single_duplicate_merge_change(duplicate_keys)

        before_count = len(web.ctx.site.changesets)
        result = change._undo_single_duplicate(target_duplicate_key)

        self._assert_single_duplicate_undo(
            change,
            before_count,
            result,
            target_duplicate_key,
        )

    def test_single_duplicate_undo_is_idempotent(self):
        duplicate_key = "/works/OL2W"
        change = self._seed_single_duplicate_merge_change([duplicate_key])

        change._undo_single_duplicate(duplicate_key)
        first_count = len(web.ctx.site.changesets)
        existing_undo = change._undo_single_duplicate(duplicate_key)

        assert isinstance(existing_undo, models.Changeset)
        assert existing_undo.kind == "undo-single-duplicate"
        assert existing_undo.data["duplicate_key"] == duplicate_key
        assert len(web.ctx.site.changesets) == first_count

    def test_single_duplicate_get_undone_keys(self):
        duplicate_key = "/works/OL2W"
        change = self._seed_single_duplicate_merge_change([duplicate_key])

        assert change.get_undone_duplicate_keys() == set()
        change._undo_single_duplicate(duplicate_key)
        assert change.get_undone_duplicate_keys() == {duplicate_key}
