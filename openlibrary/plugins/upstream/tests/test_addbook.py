"""py.test tests for addbook"""

import pytest
import web

from openlibrary import accounts
from openlibrary.mocks.mock_infobase import MockSite

from .. import addbook


def strip_nones(d):
    return {k: v for k, v in d.items() if v is not None}


def mock_user():
    return type(
        "MockUser",
        (object,),
        {
            "is_admin": lambda slf: False,
            "is_super_librarian": lambda slf: False,
            "is_super_librarian_or_higher": lambda slf: slf.is_admin() or slf.is_super_librarian(),
            "is_librarian": lambda slf: False,
            "is_usergroup_member": lambda slf, grp: False,
        },
    )()


class TestSaveBookHelper:
    def setup_method(self, method):
        web.ctx.site = MockSite()

    def test_authors(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        s = addbook.SaveBookHelper(None, None)

        def f(data):
            return strip_nones(s.process_work(web.storage(data)))

        assert f({}) == {}
        assert f({"authors": []}) == {}
        assert f({"authors": [{"type": "/type/author_role"}]}) == {}

    def test_editing_orphan_creates_work(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                }
            ]
        )
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "",
                "work--title": "Original Edition Title",
                "edition--title": "Original Edition Title",
            }
        )

        s = addbook.SaveBookHelper(None, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 2
        assert web.ctx.site.get("/works/OL1W") is not None
        assert web.ctx.site.get("/works/OL1W").title == "Original Edition Title"

    def test_never_create_an_orphan(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )
        edition = web.ctx.site.get("/books/OL1M")
        work = web.ctx.site.get("/works/OL1W")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Original Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)
        print(web.ctx.site.get("/books/OL1M").title)
        assert web.ctx.site.get("/books/OL1M").works[0].key == "/works/OL1W"

    def test_moving_orphan(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                }
            ]
        )
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "",
                "work--title": "Original Edition Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(None, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 1
        assert web.ctx.site.get("/books/OL1M").works[0].key == "/works/OL1W"

    def test_moving_orphan_ignores_work_edits(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                },
            ]
        )
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "",
                "work--title": "Modified Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(None, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Original Work Title"

    def test_editing_work(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Modified Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Modified Work Title"
        assert web.ctx.site.get("/books/OL1M").title == "Original Edition Title"

    def test_editing_edition(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Original Work Title",
                "edition--title": "Modified Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Original Work Title"
        assert web.ctx.site.get("/books/OL1M").title == "Modified Edition Title"

    def test_editing_work_and_edition(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Modified Work Title",
                "edition--title": "Modified Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Modified Work Title"
        assert web.ctx.site.get("/books/OL1M").title == "Modified Edition Title"

    def test_moving_edition(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Original Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL2W",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/books/OL1M").works[0].key == "/works/OL2W"

    def test_moving_edition_ignores_changes_to_work(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Modified Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL2W",  # Changing work
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Original Work Title"

    def test_moving_edition_to_new_work(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL100W",
                    "title": "Original Work Title",
                    "authors": [{"key": "/authors/OL123A"}],
                    "subjects": [{"key": "/subjects/Horror"}],
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL100W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL100W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL100W",
                "work--title": "FOO BAR",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "__new__",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 3
        # Should create new work with edition data
        assert web.ctx.site.get("/works/OL1W") is not None
        new_work = web.ctx.site.get("/books/OL1M").works[0]
        assert new_work.key == "/works/OL1W"
        assert new_work.title == "Original Edition Title"
        # Should ignore edits to work data
        assert web.ctx.site.get("/works/OL100W").title == "Original Work Title"
        # Should ignore authors/subjects by default
        assert not new_work.authors
        assert not new_work.subjects

    def test_moving_edition_to_new_work_can_copy_data(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL100W",
                    "title": "Original Work Title",
                    "authors": [{"key": "/authors/OL123A"}],
                    "subjects": [{"key": "/subjects/Horror"}],
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL100W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL100W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL100W",
                "work--title": "FOO BAR",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "__new__",
                "new_work_options--copy_authors": "yes",
                "new_work_options--copy_subjects": "yes",
            }
        )
        # But if we pass in the authors/subjects, it should use them
        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 3
        old_work = web.ctx.site.get("/works/OL100W")
        new_work = web.ctx.site.get("/books/OL1M").works[0]
        assert new_work.key != old_work.key
        # Should ignore authors/subjects by default
        assert new_work.authors == old_work.authors
        assert new_work.subjects == old_work.subjects

    def test_moving_edition_to_new_work_copy_when_none(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL100W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL100W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL100W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL100W",
                "work--title": "FOO BAR",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "__new__",
                "new_work_options--copy_authors": "yes",
                "new_work_options--copy_subjects": "yes",
            }
        )
        # But if we pass in the authors/subjects, it should use them
        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 3
        old_work = web.ctx.site.get("/works/OL100W")
        new_work = web.ctx.site.get("/books/OL1M").works[0]
        assert new_work.key != old_work.key
        # Should ignore authors/subjects by default
        assert not new_work.authors
        assert not new_work.subjects


class TestProcessManagedTags:
    """``SaveBookHelper.process_managed_tags`` merges the genre Tag selection
    posted from the work edit page into a list of refs, validating only
    additions so an unrelated edit never silently drops a stored genre."""

    def setup_method(self, method):
        web.ctx.site = MockSite()
        web.ctx.site.save_many(
            [
                {"type": {"key": "/type/tag"}, "key": "/tags/OL1T", "name": "Fantasy", "tag_type": "genres"},
                {"type": {"key": "/type/tag"}, "key": "/tags/OL2T", "name": "Horror", "tag_type": "genres"},
                # A Tag of a different type — must never be accepted as a genre.
                {"type": {"key": "/type/tag"}, "key": "/tags/OL9T", "name": "Novel", "tag_type": "content_formats"},
                # A real genre Tag carrying the LEGACY singular tag_type — it
                # would fail today's validation, but must survive once stored.
                {"type": {"key": "/type/tag"}, "key": "/tags/OL84T", "name": "Legacy", "tag_type": "genre"},
                # A non-Tag document sharing the key space.
                {"type": {"key": "/type/work"}, "key": "/works/OL5W", "title": "Not a tag"},
            ]
        )

    def process(self, values, stored=None):
        return addbook.SaveBookHelper.process_managed_tags(values, "genres", stored)

    def test_valid_key_strings_become_refs(self):
        assert self.process(["/tags/OL1T", "/tags/OL2T"]) == [
            {"key": "/tags/OL1T"},
            {"key": "/tags/OL2T"},
        ]

    def test_accepts_ref_shaped_input(self):
        # Works from the scripted backfill store plain strings; later saves store
        # refs. Both shapes, mixed, must normalise to refs.
        assert self.process([{"key": "/tags/OL1T"}, "/tags/OL2T"]) == [
            {"key": "/tags/OL1T"},
            {"key": "/tags/OL2T"},
        ]

    def test_drops_unknown_added_keys(self):
        # /tags/OL404T does not exist: a ref to a missing Tag would fail the
        # atomic save, so an added one is dropped rather than persisted.
        assert self.process(["/tags/OL1T", "/tags/OL404T"]) == [{"key": "/tags/OL1T"}]

    def test_drops_wrong_tag_type_when_added(self):
        # OL9T is a real Tag, but a content_formats one — not a genre.
        assert self.process(["/tags/OL1T", "/tags/OL9T"]) == [{"key": "/tags/OL1T"}]

    def test_drops_non_tag_documents_when_added(self):
        # OL5W resolves, but it is a work, not a Tag.
        assert self.process(["/tags/OL1T", "/works/OL5W"]) == [{"key": "/tags/OL1T"}]

    def test_deduplicates_preserving_order(self):
        assert self.process(["/tags/OL2T", "/tags/OL1T", "/tags/OL2T"]) == [
            {"key": "/tags/OL2T"},
            {"key": "/tags/OL1T"},
        ]

    def test_empty_and_absent_yield_empty_list(self):
        assert self.process([]) == []
        assert self.process(None) == []

    def test_preserves_stored_key_that_fails_validation_today(self):
        # OL84T is a genre Tag with the legacy singular tag_type "genre"; if it is
        # already stored, re-posting it unchanged (e.g. on a title edit) must keep
        # it — validating stored keys would be a silent data migration.
        assert self.process(
            ["/tags/OL1T", "/tags/OL84T"],
            stored=["/tags/OL1T", "/tags/OL84T"],
        ) == [{"key": "/tags/OL1T"}, {"key": "/tags/OL84T"}]

    def test_preserves_stored_key_stored_as_plain_string(self):
        # A backfilled work stores plain strings; re-posting them converts to refs
        # and preserves them, even the legacy-typed one.
        assert self.process(
            ["/tags/OL84T"],
            stored=["/tags/OL84T"],
        ) == [{"key": "/tags/OL84T"}]

    def test_still_rejects_an_added_wrong_type_key_when_others_stored(self):
        # A newly ADDED wrong-type key is still dropped even while a valid key is
        # passed through from storage.
        assert self.process(
            ["/tags/OL1T", "/tags/OL9T"],
            stored=["/tags/OL1T"],
        ) == [{"key": "/tags/OL1T"}]

    def test_removes_key_dropped_from_the_picker(self):
        # A stored key no longer in the posted set was removed by the editor.
        assert self.process(
            ["/tags/OL1T"],
            stored=["/tags/OL1T", "/tags/OL2T"],
        ) == [{"key": "/tags/OL1T"}]

    def test_save_persists_genres_as_refs(self, monkeypatch):
        """End-to-end through save(): the indexed form shape the edit page posts
        (``work--genres--N--key``) lands on the work as a list of refs."""
        monkeypatch.setattr(accounts, "get_current_user", mock_user)
        web.ctx.site.save_many(
            [
                {"type": {"key": "/type/work"}, "key": "/works/OL10W", "title": "A Work"},
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL10M",
                    "title": "A Work",
                    "works": [{"key": "/works/OL10W"}],
                },
            ]
        )
        work = web.ctx.site.get("/works/OL10W")
        edition = web.ctx.site.get("/books/OL10M")

        formdata = web.storage(
            {
                "work--key": "/works/OL10W",
                "work--title": "A Work",
                "work--_genres_present": "1",
                "work--genres--0--key": "/tags/OL1T",
                "work--genres--1--key": "/tags/OL2T",
                "edition--title": "A Work",
                "edition--works--0--key": "/works/OL10W",
            }
        )

        addbook.SaveBookHelper(work, edition).save(formdata)

        # Assert on the persisted shape (what the indexer in #13753 reads), not
        # the Thing refs MockSite rehydrates on get().
        assert web.ctx.site.docs["/works/OL10W"]["genres"] == [
            {"key": "/tags/OL1T"},
            {"key": "/tags/OL2T"},
        ]

    def test_save_drops_an_invalid_added_key(self, monkeypatch):
        """Validation runs on the real save path, not just the helper: an added
        key that is not an existing genre Tag is dropped before it is persisted
        (otherwise it would ride through on unflatten's raw refs and, once
        /type/work declares genres, reject the atomic save)."""
        monkeypatch.setattr(accounts, "get_current_user", mock_user)
        web.ctx.site.save_many(
            [
                {"type": {"key": "/type/work"}, "key": "/works/OL14W", "title": "A Work"},
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL14M",
                    "title": "A Work",
                    "works": [{"key": "/works/OL14W"}],
                },
            ]
        )
        work = web.ctx.site.get("/works/OL14W")
        edition = web.ctx.site.get("/books/OL14M")

        formdata = web.storage(
            {
                "work--key": "/works/OL14W",
                "work--title": "A Work",
                "work--_genres_present": "1",
                "work--genres--0--key": "/tags/OL1T",  # valid genre
                "work--genres--1--key": "/tags/OL404T",  # does not exist
                "work--genres--2--key": "/tags/OL9T",  # exists, but content_formats
                "edition--title": "A Work",
                "edition--works--0--key": "/works/OL14W",
            }
        )

        addbook.SaveBookHelper(work, edition).save(formdata)

        assert web.ctx.site.docs["/works/OL14W"]["genres"] == [{"key": "/tags/OL1T"}]

    def test_save_clears_genres_when_none_posted(self, monkeypatch):
        """With the Genres section present but empty, saving clears the field."""
        monkeypatch.setattr(accounts, "get_current_user", mock_user)
        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL11W",
                    "title": "A Work",
                    "genres": [{"key": "/tags/OL1T"}],
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL11M",
                    "title": "A Work",
                    "works": [{"key": "/works/OL11W"}],
                },
            ]
        )
        work = web.ctx.site.get("/works/OL11W")
        edition = web.ctx.site.get("/books/OL11M")

        formdata = web.storage(
            {
                "work--key": "/works/OL11W",
                "work--title": "A Work",
                "work--_genres_present": "1",
                "edition--title": "A Work",
                "edition--works--0--key": "/works/OL11W",
            }
        )

        addbook.SaveBookHelper(work, edition).save(formdata)

        assert not web.ctx.site.docs["/works/OL11W"].get("genres")

    def test_save_preserves_stored_genres_on_an_unrelated_title_edit(self, monkeypatch):
        """A title edit that re-posts the stored genres must keep them all — even
        a plain-string-stored, legacy-typed genre that would fail validation."""
        monkeypatch.setattr(accounts, "get_current_user", mock_user)
        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL12W",
                    "title": "Old Title",
                    # plain-string shape, and OL84T is legacy singular-typed
                    "genres": ["/tags/OL1T", "/tags/OL84T"],
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL12M",
                    "title": "Old Title",
                    "works": [{"key": "/works/OL12W"}],
                },
            ]
        )
        work = web.ctx.site.get("/works/OL12W")
        edition = web.ctx.site.get("/books/OL12M")

        formdata = web.storage(
            {
                "work--key": "/works/OL12W",
                "work--title": "New Title",
                "work--_genres_present": "1",
                "work--genres--0--key": "/tags/OL1T",
                "work--genres--1--key": "/tags/OL84T",
                "edition--title": "Old Title",
                "edition--works--0--key": "/works/OL12W",
            }
        )

        addbook.SaveBookHelper(work, edition).save(formdata)

        saved = web.ctx.site.docs["/works/OL12W"]
        assert saved["title"] == "New Title"
        assert saved["genres"] == [{"key": "/tags/OL1T"}, {"key": "/tags/OL84T"}]

    def test_save_without_genres_section_leaves_genres_untouched(self, monkeypatch):
        """A form that doesn't carry the Genres section (no presence marker) must
        not clear a work's genres."""
        monkeypatch.setattr(accounts, "get_current_user", mock_user)
        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL13W",
                    "title": "A Work",
                    "genres": [{"key": "/tags/OL1T"}],
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL13M",
                    "title": "A Work",
                    "works": [{"key": "/works/OL13W"}],
                },
            ]
        )
        work = web.ctx.site.get("/works/OL13W")
        edition = web.ctx.site.get("/books/OL13M")

        formdata = web.storage(
            {
                "work--key": "/works/OL13W",
                "work--title": "A Work",
                "edition--title": "A Work",
                "edition--works--0--key": "/works/OL13W",
            }
        )

        addbook.SaveBookHelper(work, edition).save(formdata)

        assert web.ctx.site.docs["/works/OL13W"]["genres"] == [{"key": "/tags/OL1T"}]


class TestDaisyPage:
    def setup_method(self, method):
        web.ctx.site = MockSite()

    def test_redirects_to_archive_item_for_edition_with_ocaid(self, monkeypatch):
        web.ctx.site.save(
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Accessible Book",
                "ocaid": "testitem00archive",
            }
        )

        redirects = []

        def seeother(url):
            redirects.append(url)
            raise RuntimeError("redirect")

        monkeypatch.setattr(addbook.web, "seeother", seeother)

        with pytest.raises(RuntimeError, match="redirect"):
            addbook.daisy().GET("/books/OL1M")
        assert redirects == ["https://archive.org/details/testitem00archive"]

    def test_redirect_escapes_archive_item_identifier(self, monkeypatch):
        web.ctx.site.save(
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Accessible Book",
                "ocaid": "test item/archive",
            }
        )

        redirects = []

        def seeother(url):
            redirects.append(url)
            raise RuntimeError("redirect")

        monkeypatch.setattr(addbook.web, "seeother", seeother)

        with pytest.raises(RuntimeError, match="redirect"):
            addbook.daisy().GET("/books/OL1M")
        assert redirects == ["https://archive.org/details/test%20item%2Farchive"]


class TestMakeWork:
    def test_make_author_adds_the_correct_key(self):
        author_key = "OL123A"
        author_name = "Samuel Clemens"
        author = web.ctx.site.new(
            "/authors/OL123A",
            {"key": author_key, "type": {"key": "/type/author"}, "name": author_name},
        )
        assert addbook.make_author(author_key, author_name) == author

    def test_make_work_does_indeed_make_a_work(self):
        doc = {
            "author_key": ["OL123A"],
            "author_name": ["Samuel Clemens"],
            "key": "/works/OL123W",
            "type": "work",
            "language": ["eng"],
            "title": "The Celebrated Jumping Frog of Calaveras County",
        }

        author_key = "OL123A"
        author_name = "Samuel Clemens"
        author = web.ctx.site.new(
            "/authors/OL123A",
            {"key": author_key, "type": {"key": "/type/author"}, "name": author_name},
        )

        web_doc = web.Storage(
            {
                "author_key": ["OL123A"],
                "author_name": ["Samuel Clemens"],
                "key": "/works/OL123W",
                "type": "work",
                "language": ["eng"],
                "title": "The Celebrated Jumping Frog of Calaveras County",
                "authors": [author],
                "cover_url": "/static/images/icons/avatar_book-sm.png",
                "ia": [],
                "first_publish_year": None,
            }
        )

        assert addbook.make_work(doc) == web_doc

    def test_make_work_handles_no_author(self):
        doc = {
            "key": "/works/OL123W",
            "type": "work",
            "language": ["eng"],
            "title": "The Celebrated Jumping Frog of Calaveras County",
        }

        web_doc = web.Storage(
            {
                "key": "/works/OL123W",
                "type": "work",
                "language": ["eng"],
                "title": "The Celebrated Jumping Frog of Calaveras County",
                "authors": [],
                "cover_url": "/static/images/icons/avatar_book-sm.png",
                "ia": [],
                "first_publish_year": None,
            }
        )

        assert addbook.make_work(doc) == web_doc
