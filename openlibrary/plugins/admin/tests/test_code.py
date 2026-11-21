from typing import cast
from unittest.mock import Mock
from urllib.parse import parse_qsl

import pytest
import web

from openlibrary.accounts.model import (
    Account,
    OpenLibraryAccount,
)
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.plugins.admin import code as admin_code
from openlibrary.plugins.admin.code import LIST_CREATE_ACTIONS, RevertProgress, revert_all_user_edits
from openlibrary.utils.request_context import site


def make_test_account(username: str) -> OpenLibraryAccount:
    site.get().register(
        username=username,
        email=f"{username}@foo.org",
        password="password",
        displayname=f"{username} User",
    )
    site.get().activate_account(username)
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

        mock_site.save(
            author=good_alice.get_user(),
            query=make_thing("/works/OL123W", "Good Book Title"),
            action="add-book",
        )
        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL789W", "Spammy New Book"),
            action="add-book",
        )
        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL345W", "Spammy New Book 2"),
            action="add-book",
        )
        mock_site.save(
            author=good_alice.get_user(),
            query=make_thing("/works/OL12333W", "Good Book Title 2"),
            action="add-book",
        )

        revert_all_user_edits(spam_alice)

        # Good books un-altered
        assert mock_site.get("/works/OL123W").revision == 1
        assert mock_site.get("/works/OL123W").title == "Good Book Title"
        assert mock_site.get("/works/OL12333W").revision == 1
        assert mock_site.get("/works/OL12333W").title == "Good Book Title 2"

        # Spam books deleted
        assert mock_site.get("/works/OL789W").revision == 2
        assert mock_site.get("/works/OL789W").type.key == "/type/delete"
        assert mock_site.get("/works/OL345W").revision == 2
        assert mock_site.get("/works/OL345W").type.key == "/type/delete"

    def test_reverts_spam_edits(self, mock_site):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")

        mock_site.save(
            author=good_alice.get_user(),
            query=make_thing("/works/OL123W", "Good Book Title"),
            action="add-book",
        )
        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL123W", "Spammy Book Title"),
            action="edit-book",
        )

        revert_all_user_edits(spam_alice)

        # Reverted back to good edit
        assert mock_site.get("/works/OL123W").revision == 3
        assert mock_site.get("/works/OL123W").title == "Good Book Title"
        assert mock_site.get("/works/OL123W").type.key == "/type/work"

    def test_deletes_spam_lists(self, mock_site):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")

        # Good alice's list should not be touched
        mock_site.save(
            author=good_alice.get_user(),
            query=make_thing("/people/good_alice/lists/OL1L", "Good List"),
            action="lists",
        )

        # Spam alice creates a list (revision 1)
        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/spam_alice/lists/OL2L", "Spam List"),
            action="lists",
        )

        revert_all_user_edits(spam_alice)

        # Good list remains
        assert mock_site.get("/people/good_alice/lists/OL1L").type.key == "/type/list"

        # Spam list is deleted
        assert mock_site.get("/people/spam_alice/lists/OL2L").type.key == "/type/delete"

    @pytest.mark.parametrize("action", ["create-list", "create-series"])
    def test_deletes_spam_lists_with_create_actions(self, mock_site, action):
        spam_alice = make_test_account("spam_alice")

        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/spam_alice/lists/OL2L", "Spam List"),
            action=action,
        )

        revert_all_user_edits(spam_alice)

        assert mock_site.get("/people/spam_alice/lists/OL2L").type.key == "/type/delete"

    @pytest.mark.parametrize("action", LIST_CREATE_ACTIONS)
    def test_does_not_delete_edited_lists(self, mock_site, action):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")

        # Good alice creates a list
        mock_site.save(
            author=good_alice.get_user(),
            query=make_thing("/people/good_alice/lists/OL1L", "Good List"),
            action=action,
        )

        # Spam alice edits good alice's list (revision 2 — spam alice did NOT create it)
        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/good_alice/lists/OL1L", "Vandalized List"),
            action=action,
        )

        revert_all_user_edits(spam_alice)

        # The list should be reverted (back to good title) but NOT deleted
        reverted = mock_site.get("/people/good_alice/lists/OL1L")
        assert reverted.type.key == "/type/list"
        assert reverted.name == "Good List"

    def test_does_not_undelete(self, mock_site):
        spam_alice = make_test_account("spam_alice")

        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/spam_alice/lists/OL123L", "spam spam spam"),
            action="lists",
        )
        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/spam_alice/lists/OL123L", thing_type="/type/delete"),
            action="lists",
        )

        revert_all_user_edits(spam_alice)

        assert mock_site.get("/people/spam_alice/lists/OL123L").revision >= 2
        assert mock_site.get("/people/spam_alice/lists/OL123L").type.key == "/type/delete"

    def test_two_spammy_editors(self, mock_site):
        spam_alice = make_test_account("spam_alice")
        spam_bob = make_test_account("spam_bob")

        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL1W", "Alice is Awesome"),
            action="add-book",
        )
        mock_site.save(
            author=spam_bob.get_user(),
            query=make_thing("/works/OL2W", "Bob is Awesome"),
            action="add-book",
        )

        mock_site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL2W", "Bob Sucks"),
            action="edit-book",
        )
        mock_site.save(
            author=spam_bob.get_user(),
            query=make_thing("/works/OL1W", "Alice Sucks"),
            action="edit-book",
        )

        revert_all_user_edits(spam_alice)

        # Reverted back to good edit
        assert mock_site.get("/works/OL1W").revision == 3
        assert mock_site.get("/works/OL1W").type.key == "/type/delete"
        assert mock_site.get("/works/OL2W").revision == 3
        assert mock_site.get("/works/OL2W").title == "Bob is Awesome"

        revert_all_user_edits(spam_bob)

        # Reverted back to good edit
        assert mock_site.get("/works/OL1W").revision == 3
        assert mock_site.get("/works/OL1W").type.key == "/type/delete"
        assert mock_site.get("/works/OL2W").revision == 4
        assert mock_site.get("/works/OL2W").type.key == "/type/delete"


class TestRevertLargeAccount:
    """Block-and-revert on an account with more changesets than one batch, or one request, can handle."""

    @pytest.fixture
    def spam_account(self, mock_site, monkeypatch):
        """An account with 37 changesets: 25 new works, then 5 new lists, then 7 edits to someone else's works."""
        monkeypatch.setattr(admin_code, "REVERT_BATCH_SIZE", 10)
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")
        spammer = spam_alice.get_user()
        for n in range(7):
            mock_site.save(author=good_alice.get_user(), query=make_thing(f"/works/OL{n}W", "Good Title"), action="add-book")
        for n in range(100, 125):
            mock_site.save(author=spammer, query=make_thing(f"/works/OL{n}W", "Spam Book"), action="add-book")
        for n in range(5):
            mock_site.save(author=spammer, query=make_thing(f"/people/spam_alice/lists/OL{n}L", "Spam List"), action="create-list")
        for n in range(7):
            mock_site.save(author=spammer, query=make_thing(f"/works/OL{n}W", "Spam Title"), action="edit-book")
        return spam_alice

    def assert_spam_deleted_exactly_once(self, mock_site):
        for key in [f"/works/OL{n}W" for n in range(100, 125)] + [f"/people/spam_alice/lists/OL{n}L" for n in range(5)]:
            doc = mock_site.get(key)
            # created, then deleted: a third revision would be a second delete
            assert (key, doc.type.key, doc.revision) == (key, "/type/delete", 2)

    def assert_edits_reverted_exactly_once(self, mock_site):
        for n in range(7):
            work = mock_site.get(f"/works/OL{n}W")
            # created, spammed, reverted: a fourth revision would be a second revert
            assert (work.title, work.revision) == ("Good Title", 3)

    def test_finishes_in_one_run_when_time_allows(self, mock_site, spam_account):
        progress = revert_all_user_edits(spam_account)

        assert progress == RevertProgress(reverted=7, deleted=30, lists_deleted=5, next_offset=None)
        self.assert_spam_deleted_exactly_once(mock_site)
        self.assert_edits_reverted_exactly_once(mock_site)

    def test_stops_when_out_of_time_and_resumes_from_next_offset(self, mock_site, spam_account):
        # With no time left, a run handles one batch: here the 7 edits and the 3 newest lists
        runs = [revert_all_user_edits(spam_account, time_budget=0)]
        assert runs[0] == RevertProgress(reverted=7, deleted=3, lists_deleted=3, next_offset=10)
        # That batch is saved even though the job is unfinished
        assert mock_site.get("/works/OL0W").title == "Good Title"
        assert mock_site.get("/people/spam_alice/lists/OL4L").type.key == "/type/delete"
        assert mock_site.get("/works/OL100W").type.key == "/type/work"

        while (offset := runs[-1].next_offset) is not None:
            runs.append(revert_all_user_edits(spam_account, offset=offset, time_budget=0))

        assert [run.next_offset for run in runs] == [10, 20, 30, None]
        assert sum(run.reverted for run in runs) == 7
        assert sum(run.deleted for run in runs) == 30
        assert sum(run.lists_deleted for run in runs) == 5
        self.assert_spam_deleted_exactly_once(mock_site)
        self.assert_edits_reverted_exactly_once(mock_site)

    def test_run_killed_partway_keeps_its_work_and_a_rerun_finishes(self, mock_site, monkeypatch, spam_account):
        save_many = mock_site.save_many
        saves = []

        def save_many_until_killed(*args, **kwargs):
            if len(saves) == 3:
                raise TimeoutError("worker killed")
            saves.append(args)
            return save_many(*args, **kwargs)

        monkeypatch.setattr(mock_site, "save_many", save_many_until_killed)
        with pytest.raises(TimeoutError):
            revert_all_user_edits(spam_account)
        monkeypatch.setattr(mock_site, "save_many", save_many)

        # The two batches that completed are kept: all 5 lists and the 8 newest works
        assert all(mock_site.get(f"/people/spam_alice/lists/OL{n}L").type.key == "/type/delete" for n in range(5))
        assert [n for n in range(100, 125) if mock_site.get(f"/works/OL{n}W").type.key == "/type/delete"] == list(range(117, 125))

        # Starting again from the top, with no offset, deletes only what is left
        progress = revert_all_user_edits(spam_account)

        assert (progress.deleted, progress.lists_deleted, progress.next_offset) == (17, 0, None)
        self.assert_spam_deleted_exactly_once(mock_site)
        assert all(mock_site.get(f"/works/OL{n}W").title == "Good Title" for n in range(7))

    def test_repeat_run_on_a_finished_account_deletes_nothing(self, mock_site, spam_account):
        revert_all_user_edits(spam_account)

        progress = revert_all_user_edits(spam_account)

        assert (progress.deleted, progress.lists_deleted, progress.next_offset) == (0, 0, None)
        self.assert_spam_deleted_exactly_once(mock_site)

    def test_does_not_undelete_when_a_batch_has_over_20_deleted_records(self, mock_site):
        # Infobase's `things` returns 20 keys by default, so the 21st deleted record used to be missed
        spam_alice = make_test_account("spam_alice")
        keys = [f"/people/spam_alice/lists/OL{n}L" for n in range(25)]
        for key in keys:
            mock_site.save(author=spam_alice.get_user(), query=make_thing(key, "Spam List"), action="lists")
            mock_site.save(author=spam_alice.get_user(), query=make_thing(key, "Spam List, edited"), action="lists")
            mock_site.save(query=make_thing(key, thing_type="/type/delete"))

        progress = revert_all_user_edits(spam_alice)

        assert progress == RevertProgress()
        for key in keys:
            assert (key, mock_site.get(key).type.key, mock_site.get(key).revision) == (key, "/type/delete", 3)

    def test_reverts_the_live_records_of_a_changeset_that_has_a_deleted_one(self, mock_site):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")
        for key in ("/works/OL1W", "/works/OL2W"):
            mock_site.save(author=good_alice.get_user(), query=make_thing(key, "Good Title"), action="add-book")
        mock_site.save_many(
            [make_thing("/works/OL1W", "Spam Title"), make_thing("/works/OL2W", "Spam Title")],
            author=spam_alice.get_user(),
            action="edit-book",
        )
        mock_site.save(query=make_thing("/works/OL2W", thing_type="/type/delete"))

        progress = revert_all_user_edits(spam_alice)

        assert progress == RevertProgress(reverted=1)
        assert mock_site.get("/works/OL1W").title == "Good Title"
        assert (mock_site.get("/works/OL2W").type.key, mock_site.get("/works/OL2W").revision) == ("/type/delete", 3)

    def test_revert_does_not_refetch_changesets_it_already_listed(self, mock_site, monkeypatch, spam_account):
        monkeypatch.setattr(mock_site, "get_change", Mock(side_effect=AssertionError("one request per changeset")))

        assert revert_all_user_edits(spam_account).next_offset is None


def is_blocked(username: str) -> bool:
    return cast(OpenLibraryAccount, OpenLibraryAccount.get_by_username(username)).is_blocked()


class TestBlockAccountAndRevertPost:
    @pytest.fixture
    def flashes(self, mock_site, monkeypatch) -> list[str]:
        messages: list[str] = []
        monkeypatch.setattr(admin_code, "add_flash_message", lambda kind, message: messages.append(message))
        monkeypatch.setattr(Account, "get_edit_count", lambda self: 950)
        for name, value in {"home": "http://localhost", "path": "/admin/people/spam_alice", "status": None}.items():
            monkeypatch.setitem(web.ctx, name, value)
        return messages

    def post(self, monkeypatch, **form) -> str:
        """Posts the form for spam_alice and returns where it redirects to."""
        monkeypatch.setattr(web, "input", lambda **defaults: web.storage(defaults, action="block_account_and_revert", **form))
        with pytest.raises(web.SeeOther):
            admin_code.people_view().POST("spam_alice")
        return dict(web.ctx.headers)["Location"]

    def test_blocks_the_account_before_reverting(self, flashes, monkeypatch):
        make_test_account("spam_alice")
        blocked_during_revert = []

        def revert(account, offset=0):
            blocked_during_revert.append(is_blocked("spam_alice"))
            return RevertProgress()

        monkeypatch.setattr(admin_code, "revert_all_user_edits", revert)
        self.post(monkeypatch)

        assert blocked_during_revert == [True]

    def test_account_stays_blocked_when_the_revert_dies(self, flashes, monkeypatch):
        make_test_account("spam_alice")
        monkeypatch.setattr(admin_code, "revert_all_user_edits", Mock(side_effect=TimeoutError("worker killed")))
        monkeypatch.setattr(web, "input", lambda **defaults: web.storage(defaults, action="block_account_and_revert"))

        with pytest.raises(TimeoutError):
            admin_code.people_view().POST("spam_alice")

        assert is_blocked("spam_alice")

    def test_reports_a_finished_revert(self, flashes, monkeypatch):
        make_test_account("spam_alice")
        monkeypatch.setattr(admin_code, "revert_all_user_edits", lambda account, offset=0: RevertProgress(reverted=3, deleted=40, lists_deleted=12))

        assert self.post(monkeypatch) == "http://localhost/admin/people/spam_alice"
        assert flashes == ["Blocked the account, reverted 3 edits and deleted 40 records (12 of them lists). All of its edits have been handled."]

    def test_reports_how_far_an_unfinished_revert_got(self, flashes, monkeypatch):
        make_test_account("spam_alice")
        monkeypatch.setattr(
            admin_code, "revert_all_user_edits", lambda account, offset=0: RevertProgress(reverted=3, deleted=40, lists_deleted=12, next_offset=200)
        )

        # The redirect carries the offset, which the page puts back in the form
        assert self.post(monkeypatch) == "http://localhost/admin/people/spam_alice?revert_offset=200"
        assert flashes == [
            (
                "The account is blocked. This pass reverted 3 edits and deleted 40 records (12 of them lists). "
                '750 of its 950 changesets are still to do: press "continue reverting edits" to carry on.'
            )
        ]

    @pytest.mark.parametrize(("revert_offset", "expected"), [(None, 0), ("200", 200), ("-5", 0), ("abc", 0)])
    def test_continues_from_the_posted_offset(self, flashes, monkeypatch, revert_offset, expected):
        make_test_account("spam_alice")
        revert = Mock(return_value=RevertProgress())
        monkeypatch.setattr(admin_code, "revert_all_user_edits", revert)

        self.post(monkeypatch, **({"revert_offset": revert_offset} if revert_offset else {}))

        assert revert.call_args.kwargs == {"offset": expected}

    def test_large_account_is_cleaned_up_by_pressing_continue(self, flashes, mock_site, monkeypatch):
        monkeypatch.setattr(admin_code, "REVERT_BATCH_SIZE", 10)
        monkeypatch.setattr(admin_code, "REVERT_TIME_BUDGET_SECONDS", 0)
        spammer = make_test_account("spam_alice").get_user()
        for n in range(25):
            mock_site.save(author=spammer, query=make_thing(f"/works/OL{n}W", "Spam Book"), action="add-book")

        locations = [self.post(monkeypatch)]
        while "revert_offset=" in locations[-1]:
            locations.append(self.post(monkeypatch, revert_offset=locations[-1].split("revert_offset=")[1]))

        assert [location.partition("?")[2] for location in locations] == ["revert_offset=10", "revert_offset=20", ""]
        assert all(mock_site.get(f"/works/OL{n}W").revision == 2 for n in range(25))
        assert is_blocked("spam_alice")


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


class TestPeopleViewTemplate:
    @pytest.fixture
    def render_view(self, monkeypatch, render_template):
        monkeypatch.setitem(web.ctx, "path", "/admin/people/spammer")

        def render(status, query_string=""):
            monkeypatch.setattr(web, "input", lambda _m=None, **defaults: web.storage(defaults, **dict(parse_qsl(query_string))))
            person = web.storage(
                username="spammer",
                displayname="Spammer",
                email="spammer@example.com",
                status=status,
                activated_on=None,
                last_login=None,
                get_user=lambda: None,
                get_links=list,
                get_edit_count=lambda: 950,
                has_tag=lambda tag: False,
            )
            return render_template("admin/people/view", person)

        return render

    def test_blocked_account_can_still_have_its_edits_reverted(self, render_view):
        html = render_view("blocked")

        assert "revert all edits" in html
        assert 'name="revert_offset" value="0"' in html
        assert "unblock this account" in html

    def test_unfinished_revert_offers_to_continue_from_its_offset(self, render_view):
        html = render_view("blocked", "revert_offset=200")

        assert "continue reverting edits" in html
        assert 'name="revert_offset" value="200"' in html

    def test_bad_offset_starts_from_the_top(self, render_view):
        assert 'name="revert_offset" value="0"' in render_view("blocked", "revert_offset=-5")


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
        progress = admin_code.revert_all_user_edits(account)
        assert progress == RevertProgress(reverted=1, deleted=1)
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

    def test_block_list_save_updates_existing_doc(self, current):
        current.quicksave("/admin/block", "/type/object", ips=[{"ip": "192.0.2.9"}], note="keep me")
        admin_code.block().block_ips(["192.0.2.1"])
        doc = current.get("/admin/block")
        assert [d.ip for d in doc.ips] == ["192.0.2.1"]
        assert doc.note == "keep me"

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
