from typing import cast
from urllib.parse import parse_qsl

import pytest
import web

from openlibrary.accounts.model import (
    OpenLibraryAccount,
)
from openlibrary.plugins.admin import code as admin_code
from openlibrary.plugins.admin.code import revert_all_user_edits


def make_test_account(username: str) -> OpenLibraryAccount:
    web.ctx.site.register(
        username=username,
        email=f"{username}@foo.org",
        password="password",
        displayname=f"{username} User",
    )
    web.ctx.site.activate_account(username)
    return cast(OpenLibraryAccount, OpenLibraryAccount.get_by_username(username))


def make_thing(key: str, title: str = "", thing_type: str | None = None) -> dict:
    if thing_type == "/type/delete":
        return {
            "key": key,
            "type": {"key": "/type/delete"},
        }
    if key.startswith("/works/"):
        return {
            "key": key,
            "type": {"key": "/type/work"},
            "title": title,
        }
    elif "/lists/" in key:
        return {
            "key": key,
            "type": {"key": "/type/list"},
            "name": title,
        }
    else:
        raise NotImplementedError(f"make_thing not implemented for {key} or {thing_type}")


class TestRevertAllUserEdits:
    def test_no_edits(self, mock_site):
        alice = make_test_account("alice")

        revert_all_user_edits(alice)

    def test_deletes_spam_works(self, mock_site):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")

        web.ctx.site.save(
            author=good_alice.get_user(),
            query=make_thing("/works/OL123W", "Good Book Title"),
            action="add-book",
        )
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL789W", "Spammy New Book"),
            action="add-book",
        )
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL345W", "Spammy New Book 2"),
            action="add-book",
        )
        web.ctx.site.save(
            author=good_alice.get_user(),
            query=make_thing("/works/OL12333W", "Good Book Title 2"),
            action="add-book",
        )

        revert_all_user_edits(spam_alice)

        # Good books un-altered
        assert web.ctx.site.get("/works/OL123W").revision == 1
        assert web.ctx.site.get("/works/OL123W").title == "Good Book Title"
        assert web.ctx.site.get("/works/OL12333W").revision == 1
        assert web.ctx.site.get("/works/OL12333W").title == "Good Book Title 2"

        # Spam books deleted
        assert web.ctx.site.get("/works/OL789W").revision == 2
        assert web.ctx.site.get("/works/OL789W").type.key == "/type/delete"
        assert web.ctx.site.get("/works/OL345W").revision == 2
        assert web.ctx.site.get("/works/OL345W").type.key == "/type/delete"

    def test_reverts_spam_edits(self, mock_site):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")

        web.ctx.site.save(
            author=good_alice.get_user(),
            query=make_thing("/works/OL123W", "Good Book Title"),
            action="add-book",
        )
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL123W", "Spammy Book Title"),
            action="edit-book",
        )

        revert_all_user_edits(spam_alice)

        # Reverted back to good edit
        assert web.ctx.site.get("/works/OL123W").revision == 3
        assert web.ctx.site.get("/works/OL123W").title == "Good Book Title"
        assert web.ctx.site.get("/works/OL123W").type.key == "/type/work"

    def test_deletes_spam_lists(self, mock_site):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")

        # Good alice's list should not be touched
        web.ctx.site.save(
            author=good_alice.get_user(),
            query=make_thing("/people/good_alice/lists/OL1L", "Good List"),
            action="lists",
        )

        # Spam alice creates a list (revision 1)
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/spam_alice/lists/OL2L", "Spam List"),
            action="lists",
        )

        revert_all_user_edits(spam_alice)

        # Good list remains
        assert web.ctx.site.get("/people/good_alice/lists/OL1L").type.key == "/type/list"

        # Spam list is deleted
        assert web.ctx.site.get("/people/spam_alice/lists/OL2L").type.key == "/type/delete"

    def test_does_not_delete_edited_lists(self, mock_site):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")

        # Good alice creates a list
        web.ctx.site.save(
            author=good_alice.get_user(),
            query=make_thing("/people/good_alice/lists/OL1L", "Good List"),
            action="lists",
        )

        # Spam alice edits good alice's list (revision 2 — spam alice did NOT create it)
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/good_alice/lists/OL1L", "Vandalized List"),
            action="lists",
        )

        revert_all_user_edits(spam_alice)

        # The list should be reverted (back to good title) but NOT deleted
        reverted = web.ctx.site.get("/people/good_alice/lists/OL1L")
        assert reverted.type.key == "/type/list"
        assert reverted.name == "Good List"

    def test_does_not_undelete(self, mock_site):
        spam_alice = make_test_account("spam_alice")

        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/spam_alice/lists/OL123L", "spam spam spam"),
            action="lists",
        )
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/spam_alice/lists/OL123L", thing_type="/type/delete"),
            action="lists",
        )

        revert_all_user_edits(spam_alice)

        assert web.ctx.site.get("/people/spam_alice/lists/OL123L").revision >= 2
        assert web.ctx.site.get("/people/spam_alice/lists/OL123L").type.key == "/type/delete"

    def test_two_spammy_editors(self, mock_site):
        spam_alice = make_test_account("spam_alice")
        spam_bob = make_test_account("spam_bob")

        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL1W", "Alice is Awesome"),
            action="add-book",
        )
        web.ctx.site.save(
            author=spam_bob.get_user(),
            query=make_thing("/works/OL2W", "Bob is Awesome"),
            action="add-book",
        )

        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL2W", "Bob Sucks"),
            action="edit-book",
        )
        web.ctx.site.save(
            author=spam_bob.get_user(),
            query=make_thing("/works/OL1W", "Alice Sucks"),
            action="edit-book",
        )

        revert_all_user_edits(spam_alice)

        # Reverted back to good edit
        assert web.ctx.site.get("/works/OL1W").revision == 3
        assert web.ctx.site.get("/works/OL1W").type.key == "/type/delete"
        assert web.ctx.site.get("/works/OL2W").revision == 3
        assert web.ctx.site.get("/works/OL2W").title == "Bob is Awesome"

        revert_all_user_edits(spam_bob)

        # Reverted back to good edit
        assert web.ctx.site.get("/works/OL1W").revision == 3
        assert web.ctx.site.get("/works/OL1W").type.key == "/type/delete"
        assert web.ctx.site.get("/works/OL2W").revision == 4
        assert web.ctx.site.get("/works/OL2W").type.key == "/type/delete"


class TestPeopleEditsPost:
    def test_revert_redirects_back_to_the_same_page(self, monkeypatch):
        reverted = []
        monkeypatch.setattr(admin_code, "revert_changesets", lambda ids, comment: reverted.append(ids))
        monkeypatch.setattr(
            web,
            "input",
            lambda **defaults: web.storage(defaults, changesets=["123"], action="revert"),
        )
        for name, value in {
            "home": "http://localhost",
            "path": "/admin/people/spammer/edits",
            "fullpath": "/admin/people/spammer/edits?page=3",
            "headers": [],
            "status": None,
        }.items():
            monkeypatch.setattr(web.ctx, name, value, raising=False)

        with pytest.raises(web.SeeOther):
            admin_code.people_edits().POST("spammer")

        assert reverted == [["123"]]
        assert web.ctx.status == "303 See Other"
        assert (
            "Location",
            "http://localhost/admin/people/spammer/edits?page=3",
        ) in web.ctx.headers


class TestPeopleEditsTemplate:
    @pytest.fixture
    def render_edits(self, monkeypatch, render_template):
        account = web.storage(
            username="spammer",
            displayname="Spammer",
            get_user=lambda: web.storage(key="/people/spammer"),
            get_edit_count=lambda: 250,
        )
        monkeypatch.setitem(web.template.Template.globals, "recentchanges", lambda query: [])
        monkeypatch.setitem(web.template.Template.globals, "request", web.storage(path="/admin/people/spammer/edits"))
        monkeypatch.setitem(web.template.Template.globals, "macros", web.storage(OlPagination=lambda page, total_pages: f"pager:{page}/{total_pages}"))

        def render(query_string):
            monkeypatch.setattr(web, "input", lambda _m=None, **defaults: web.storage(defaults, **dict(parse_qsl(query_string))))
            return render_template("admin/people/edits", account)

        return render

    @pytest.mark.parametrize(
        ("query_string", "pager"),
        [
            ("", "pager:1/3"),
            ("page=2&limit=50", "pager:2/5"),
            ("page=0", "pager:1/3"),
            ("page=-2", "pager:1/3"),
            ("page=abc", "pager:1/3"),
            ("limit=0", "pager:1/3"),
            ("limit=-5", "pager:1/3"),
            ("limit=abc", "pager:1/3"),
        ],
    )
    def test_bad_page_and_limit_fall_back_to_defaults(self, render_edits, query_string, pager):
        assert pager in render_edits(query_string)
