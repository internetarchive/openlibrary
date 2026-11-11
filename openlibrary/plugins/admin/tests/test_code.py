from typing import cast
from unittest.mock import Mock
from urllib.parse import parse_qsl

import pytest
import web

from openlibrary.accounts.model import (
    OpenLibraryAccount,
)
from openlibrary.mocks.mock_infobase import MockSite
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


class TestSiteContextMigration:
    @pytest.fixture(params=["missing", "different"])
    def current(self, mock_site, monkeypatch, request):
        # The normal fixture sets both handles; keep only the ContextVar current.
        if request.param == "missing":
            monkeypatch.delitem(web.ctx, "site")
        else:
            monkeypatch.setitem(web.ctx, "site", MockSite())
        for key, value in {"home": "http://openlibrary.org", "path": "/admin/block", "method": "GET", "ip": "192.0.2.1"}.items():
            monkeypatch.setitem(web.ctx, key, value)
        monkeypatch.setattr(admin_code, "render_template", Mock())
        monkeypatch.setattr(admin_code, "render", Mock())
        monkeypatch.setattr(admin_code, "add_flash_message", Mock())
        monkeypatch.setattr(admin_code.context, "user", None, raising=False)
        return mock_site

    @pytest.mark.parametrize("allowed", [False, True])
    def test_admin_dispatch_uses_current_membership(self, current, monkeypatch, allowed):
        members = [{"key": "/people/alice"}]
        current.quicksave("/usergroup/admin", members=members if allowed else [])
        if legacy := web.ctx.get("site"):
            legacy.quicksave("/usergroup/admin", members=[] if allowed else members)
        user = Mock(key="/people/alice", is_librarian=lambda: False, is_super_librarian=lambda: False)
        monkeypatch.setattr(admin_code.context, "user", user)
        page = Mock()
        result = admin_code.admin().handle(lambda: page)
        if allowed:
            page.GET.assert_called_once_with()
            assert result is page.GET.return_value
            admin_code.render.permission_denied.assert_not_called()
        else:
            page.GET.assert_not_called()
            admin_code.render.permission_denied.assert_called_once_with("/admin/block", "Permission denied.")

    def test_spam_cleanup_reverts_edits_and_deletes_created_records(self, current):
        current.quicksave("/works/OL1W", "/type/work", title="Keep this")
        current.quicksave("/works/OL1W", "/type/work", title="Spam edit")
        edited = current.get_change(current.changesets[-1]["id"])
        current.quicksave("/works/OL2W", "/type/work", title="Spam book")
        added = current.get_change(current.changesets[-1]["id"])
        current.quicksave("/works/OL3W", "/type/delete")
        deleted = current.get_change(current.changesets[-1]["id"])
        # Treat the new book as an add-book changeset, as the real form does.
        added.kind = "add-book"
        account = Mock(get_recentchanges=Mock(return_value=[edited, added, deleted]))
        edits, deletions = admin_code.revert_all_user_edits(account)
        assert (edits, deletions) == (1, 1)
        assert current.get("/works/OL1W").title == "Keep this"
        assert current.get("/works/OL2W").type.key == "/type/delete"
        assert current.get("/works/OL3W").type.key == "/type/delete"
        assert current.changesets[-1]["comment"] == "Delete spam"
        assert current.changesets[-1]["kind"] == "bulk-revert-spam"
        account.get_recentchanges.assert_called_once_with(limit=100, offset=0)

    def test_stats_read_and_save_use_current_site(self, current, monkeypatch):
        connection = Mock()
        connection.request.return_value = '{"edits": 7}'
        monkeypatch.setattr(current, "_conn", connection, raising=False)
        monkeypatch.setattr(current, "name", "current-site", raising=False)
        monkeypatch.setattr(current, "_request", Mock(return_value=web.storage(edits=7, edits_by_bots=2, new_accounts=3)), raising=False)
        assert admin_code.stats().GET("2026-11-11").rawtext == '{"edits": 7}'
        connection.request.assert_called_once_with("current-site", "/get", "GET", {"key": "/admin/stats/2026-11-11"})
        with pytest.raises(web.HTTPError, match="303 See Other"):
            admin_code.stats().POST("2026-11-11")
        doc = current.get("/admin/stats/2026-11-11")
        assert (doc.edits.human, doc.edits.bot, doc.edits.total, doc.members) == (5, 2, 7, 3)
        assert current.changesets[-1]["kind"] == "create-stats"

    def test_block_list_read_and_save_use_current_site(self, current, monkeypatch):
        monkeypatch.setattr(web, "input", lambda: web.storage(ips=" 192.0.2.1 \n192.0.2.2"))
        with pytest.raises(web.HTTPError, match="303 See Other"):
            admin_code.block().POST()
        assert admin_code.get_blocked_ips() == ["192.0.2.1", "192.0.2.2"]
        assert current.changesets[-1]["kind"] == "edit-blocked-ips"
        admin_code.block().GET()
        assert admin_code.render_template.call_args.args[1]._site is current
        monkeypatch.setitem(web.ctx, "path", "/books/OL1M/edit")
        handler = Mock()
        admin_code.block_ip_processor(handler)
        handler.assert_not_called()

    @pytest.mark.parametrize("by_key", [False, True])
    def test_inspect_queries_current_store(self, current, monkeypatch, by_key):
        current.store["account/alice"] = {"type": "account", "username": "alice"}
        current.store["other/1"] = {"type": "other"}
        monkeypatch.setattr(web, "input", lambda **defaults: web.storage(key="account/alice" if by_key else None, type="account", name=None, value=None))
        admin_code.inspect().GET_store()
        assert [doc["_key"] for doc in admin_code.render_template.call_args.args[1]] == ["account/alice"]

    def test_permission_update_uses_current_documents(self, current, monkeypatch):
        current.quicksave("/works", "/type/page", title="Keep title", child_permission={"key": "/permission/open"})
        monkeypatch.setattr(web, "input", lambda **defaults: web.storage(perm_pages="/permission/open", perm_records="/permission/loggedinusers"))
        admin_code.permissions().POST()
        assert current.get("/works").title == "Keep title"
        for key in ["/", "/works", "/books", "/authors"]:
            doc = current.get(key)
            assert doc.permission.key == "/permission/restricted"
            assert doc.child_permission.key == ("/permission/open" if key == "/" else "/permission/loggedinusers")
        assert current.changesets[-1]["kind"] == "bulk-edit-permissions"
        assert current.changesets[-1]["comment"] == "Updated edit policy."

    def test_solr_update_uses_current_store(self, current, monkeypatch):
        monkeypatch.setattr(web, "input", lambda **defaults: web.storage(keys=" /works/OL1W \n /books/OL2M "))
        admin_code.solr().POST()
        assert current.store["solr-force-update"] == {
            "_key": "solr-force-update",
            "type": "solr-force-update",
            "keys": ["/works/OL1W", "/books/OL2M"],
            "_rev": None,
        }
