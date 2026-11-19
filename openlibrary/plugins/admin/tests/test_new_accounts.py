from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
import web

from openlibrary.core.jinja import render_jinja_template
from openlibrary.plugins.admin import code as admin_code
from openlibrary.plugins.admin import new_accounts
from openlibrary.plugins.admin.new_accounts import build_report, clamp_param, format_duration, scan_recent_changes

# Far from the wall clock, when the mock site saves its type documents.
NOW = datetime(2100, 1, 1, 12, 0, 0)


def signup(site, username: str, when: datetime, bot: bool = False) -> str:
    """Registers and activates an account whose profile was created at `when`."""
    site.register(username=username, email=f"{username}@example.org", password="password", displayname=f"{username} name")
    site.activate_account(username)
    key = f"/people/{username}"
    stamp = {"type": "/type/datetime", "value": when.isoformat()}
    site.docs[key].update(created=stamp, last_modified=stamp, bot=bot)
    # The changeset that created the profile.
    site.changesets[-1]["timestamp"] = when.isoformat()
    return key


def write(site, username: str, key: str, when: datetime, title: str = "A title", kind: str = "add-book", comment: str = ""):
    doc = {"key": key, "type": {"key": "/type/work"}, "title": title}
    site.save(doc, timestamp=when, action=kind, comment=comment, author=web.storage(key=f"/people/{username}"))


@pytest.fixture
def site(mock_site, request_context_fixture):
    request_context_fixture(lang="en")
    return mock_site


class TestBuildReport:
    def test_no_changes(self, site):
        report = build_report(site, now=NOW)
        assert report.rows == []
        assert report.matching_accounts == 0
        assert report.changes_scanned == 0
        assert not report.scan_capped
        assert (report.age_label, report.window_label) == ("7 days", "24 hours")

    def test_groups_by_author_and_puts_the_busiest_first(self, site):
        signup(site, "quiet", NOW - timedelta(hours=5))
        signup(site, "busy", NOW - timedelta(hours=3))
        write(site, "quiet", "/works/OL1W", NOW - timedelta(hours=4))
        for n in range(3):
            write(site, "busy", f"/works/OL{n + 10}W", NOW - timedelta(hours=2, minutes=-n))

        report = build_report(site, now=NOW)

        assert [(row.username, row.edits_in_window, row.total_edits) for row in report.rows] == [("busy", 3, 3), ("quiet", 1, 1)]
        assert report.matching_accounts == 2

    def test_ties_put_the_fastest_first_write_first(self, site):
        signup(site, "slow", NOW - timedelta(hours=5))
        signup(site, "fast", NOW - timedelta(hours=5))
        write(site, "slow", "/works/OL1W", NOW - timedelta(hours=1))
        write(site, "fast", "/works/OL2W", NOW - timedelta(hours=4, minutes=58))

        assert [row.username for row in build_report(site, now=NOW).rows] == ["fast", "slow"]

    def test_signup_to_first_write(self, site):
        signup(site, "spammer", NOW - timedelta(hours=1))
        write(site, "spammer", "/works/OL1W", NOW - timedelta(minutes=58))
        write(site, "spammer", "/works/OL2W", NOW - timedelta(minutes=30))

        [row] = build_report(site, now=NOW).rows

        assert row.first_write_delay == timedelta(minutes=2)
        assert row.first_write_label == "2.0 min"
        assert row.first_write_is_fast
        assert row.exact
        assert (row.age, row.created_label) == ("1.0 h", "2100-01-01 11:00")

    def test_a_slow_first_write_is_not_flagged(self, site):
        signup(site, "patron", NOW - timedelta(hours=5))
        write(site, "patron", "/works/OL1W", NOW - timedelta(hours=1))

        [row] = build_report(site, now=NOW).rows

        assert row.first_write_label == "4.0 h"
        assert not row.first_write_is_fast

    def test_the_signup_changeset_is_not_a_write(self, site):
        signup(site, "lurker", NOW - timedelta(hours=1))
        assert site.changesets[-1]["kind"] == "new-account"

        assert build_report(site, now=NOW).rows == []

    def test_old_accounts_are_left_out(self, site):
        signup(site, "veteran", NOW - timedelta(days=8))
        signup(site, "newcomer", NOW - timedelta(days=6))
        write(site, "veteran", "/works/OL1W", NOW - timedelta(hours=1))
        write(site, "newcomer", "/works/OL2W", NOW - timedelta(hours=1))

        assert [row.username for row in build_report(site, now=NOW).rows] == ["newcomer"]
        assert {row.username for row in build_report(site, now=NOW, days=10).rows} == {"veteran", "newcomer"}
        assert build_report(site, now=NOW, days=3).rows == []

    def test_bots_are_left_out(self, site):
        signup(site, "importbot", NOW - timedelta(hours=2), bot=True)
        write(site, "importbot", "/works/OL1W", NOW - timedelta(hours=1))

        report = build_report(site, now=NOW)

        assert report.rows == []
        assert report.changes_scanned == 0

    def test_edits_outside_the_window_count_only_towards_the_total(self, site):
        signup(site, "returning", NOW - timedelta(days=3))
        write(site, "returning", "/works/OL1W", NOW - timedelta(days=3) + timedelta(minutes=5))
        write(site, "returning", "/works/OL2W", NOW - timedelta(hours=2))

        [row] = build_report(site, now=NOW).rows

        assert (row.edits_in_window, row.total_edits, row.total_edits_label) == (1, 2, "2")
        assert row.exact
        # The first write is the one from three days ago, found in the account's own history.
        assert row.first_write_delay == timedelta(minutes=5)
        assert build_report(site, now=NOW, hours=1).rows == []

    def test_counts_by_kind(self, site):
        signup(site, "spammer", NOW - timedelta(hours=1))
        for n in range(3):
            write(site, "spammer", f"/works/OL{n}W", NOW - timedelta(minutes=50 - n))
        write(site, "spammer", "/people/spammer/lists/OL1L", NOW - timedelta(minutes=40), kind="create-list")
        write(site, "spammer", "/works/OL9W", NOW - timedelta(minutes=30), kind="edit-book")

        [row] = build_report(site, now=NOW).rows

        assert (row.edits_in_window, row.books_added, row.lists_created, row.other_edits) == (5, 3, 1, 1)

    def test_last_three_edits(self, site):
        signup(site, "spammer", NOW - timedelta(hours=1))
        for n in range(5):
            write(site, "spammer", f"/works/OL{n}W", NOW - timedelta(minutes=50 - n), title=f"Promo code {n}", comment=f"comment {n}")

        [row] = build_report(site, now=NOW).rows

        assert [(e.kind, e.key, e.title, e.comment) for e in row.recent_edits] == [
            ("add-book", "/works/OL4W", "Promo code 4", "comment 4"),
            ("add-book", "/works/OL3W", "Promo code 3", "comment 3"),
            ("add-book", "/works/OL2W", "Promo code 2", "comment 2"),
        ]
        assert row.recent_edits[0].ago == "46 min"
        assert not row.recent_edits[0].deleted

    def test_last_edits_show_the_work_of_a_changeset_and_flag_deleted_records(self, site):
        signup(site, "spammer", NOW - timedelta(hours=1))
        author = web.storage(key="/people/spammer")
        docs = [
            {"key": "/authors/OL1A", "type": {"key": "/type/author"}, "name": "Someone"},
            {"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "The edition"},
            {"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "The work"},
        ]
        site.save_many(docs, timestamp=NOW - timedelta(minutes=50), action="add-book", author=author)
        write(site, "spammer", "/works/OL2W", NOW - timedelta(minutes=40), title="Gone")
        site.save({"key": "/works/OL2W", "type": {"key": "/type/delete"}}, timestamp=NOW - timedelta(minutes=5))

        [row] = build_report(site, now=NOW).rows

        assert [(e.key, e.title, e.deleted) for e in row.recent_edits] == [("/works/OL2W", None, True), ("/works/OL1W", "The work", False)]

    def test_status_and_email_come_from_the_account(self, site):
        signup(site, "spammer", NOW - timedelta(hours=1))
        signup(site, "blocked", NOW - timedelta(hours=1))
        write(site, "spammer", "/works/OL1W", NOW - timedelta(minutes=50))
        write(site, "spammer", "/works/OL2W", NOW - timedelta(minutes=49))
        write(site, "blocked", "/works/OL3W", NOW - timedelta(minutes=50))
        site.update_account("blocked", status="blocked")

        active, blocked = build_report(site, now=NOW).rows

        assert (active.displayname, active.email, active.status, active.can_block) == ("spammer name", "spammer@example.org", "active", True)
        assert (blocked.status, blocked.can_block) == ("blocked", False)

    def test_only_the_busiest_accounts_are_shown(self, site):
        for n in range(4):
            signup(site, f"user{n}", NOW - timedelta(hours=2))
            for m in range(n + 1):
                write(site, f"user{n}", f"/works/OL{n}{m}W", NOW - timedelta(minutes=30 + m))

        report = build_report(site, now=NOW, max_accounts=2)

        assert [row.username for row in report.rows] == ["user3", "user2"]
        assert report.matching_accounts == 4

    def test_scan_stops_at_the_cap(self, site):
        signup(site, "early", NOW - timedelta(hours=10))
        signup(site, "late", NOW - timedelta(hours=10))
        for n in range(3):
            write(site, "early", f"/works/OL1{n}W", NOW - timedelta(hours=9, minutes=-n))
        for n in range(4):
            write(site, "late", f"/works/OL2{n}W", NOW - timedelta(hours=1, minutes=-n))

        report = build_report(site, now=NOW, max_changes=4, page_size=2)

        assert report.scan_capped
        assert report.changes_scanned == 4
        assert report.scanned_back_to_label == "2100-01-01 11:00"
        # `early` only wrote before the scan's reach.
        assert [(row.username, row.edits_in_window_label) for row in report.rows] == [("late", "4")]
        assert not build_report(site, now=NOW, max_changes=100, page_size=2).scan_capped

    def test_an_account_with_more_history_than_is_loaded_shows_minimums(self, site):
        signup(site, "prolific", NOW - timedelta(days=3))
        for n in range(4):
            write(site, "prolific", f"/works/OL{n}W", NOW - timedelta(days=2, minutes=-n))
        write(site, "prolific", "/works/OL9W", NOW - timedelta(hours=1))

        [row] = build_report(site, now=NOW, history_limit=3).rows

        assert not row.exact
        assert (row.edits_in_window_label, row.total_edits_label) == ("1", "3+")
        assert row.first_write_label.startswith("at most ")

    def test_accounts_inside_the_scan_cost_no_calls_of_their_own(self, site, monkeypatch):
        for n in range(3):
            signup(site, f"user{n}", NOW - timedelta(hours=2))
            write(site, f"user{n}", f"/works/OL{n}W", NOW - timedelta(hours=1))
        recentchanges = Mock(side_effect=site.recentchanges)
        get_many = Mock(side_effect=site.get_many)
        monkeypatch.setattr(site, "recentchanges", recentchanges)
        monkeypatch.setattr(site, "get_many", get_many)

        assert len(build_report(site, now=NOW).rows) == 3

        # One page of the scan, then one batch of profiles and one batch of titles.
        assert recentchanges.call_count == 1
        assert get_many.call_count == 2


class TestScanRecentChanges:
    def test_pages_until_the_window_is_exhausted(self, site):
        signup(site, "writer", NOW - timedelta(hours=2))
        for n in range(5):
            write(site, "writer", f"/works/OL{n}W", NOW - timedelta(minutes=50 - n))

        changes, capped = scan_recent_changes(site, NOW - timedelta(hours=1), max_changes=10, page_size=2)

        assert [c.changes[0]["key"] for c in changes] == [f"/works/OL{n}W" for n in (4, 3, 2, 1, 0)]
        assert not capped

    def test_changes_seen_twice_are_kept_once(self):
        first, second, third = (Mock(id=n) for n in range(3))
        # A change arriving mid-scan pushes `second` onto the next page too.
        site = Mock(recentchanges=Mock(side_effect=[[first, second], [second, third], []]))

        changes, capped = scan_recent_changes(site, NOW, max_changes=10, page_size=2)

        assert changes == [first, second, third]
        assert not capped


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0 s"),
        (-5, "0 s"),
        (45, "45 s"),
        (126, "2.1 min"),
        (34 * 60, "34 min"),
        (3.5 * 3600, "3.5 h"),
        (26 * 3600, "26 h"),
        (3 * 86400, "3.0 d"),
        (12 * 86400, "12 d"),
    ],
)
def test_format_duration(request_context_fixture, seconds, expected):
    assert format_duration(timedelta(seconds=seconds)) == expected


@pytest.mark.parametrize(("value", "expected"), [(None, 7), ("", 7), ("3", 3), ("30", 30), ("31", 7), ("0", 7), ("-2", 7), ("abc", 7), ("2.5", 7)])
def test_clamp_param(value, expected):
    assert clamp_param(value, 7, 30) == expected


class TestTemplate:
    @pytest.fixture
    def render(self, site, render_template, monkeypatch):
        monkeypatch.setitem(web.template.Template.globals, "request", web.storage(path="/admin/new-accounts"))
        return lambda **kwargs: render_jinja_template("admin/new_accounts.html.jinja", report=build_report(site, now=NOW, **kwargs))

    def test_empty(self, render):
        html = render()
        assert "No accounts under 7 days old have made edits in the last 24 hours." in html
        assert "<table" not in html
        assert "<strong>New accounts</strong>" in html  # the admin menu, on its current page

    def test_rows_carry_what_an_admin_needs(self, site, render):
        signup(site, "spammer", NOW - timedelta(hours=1))
        write(site, "spammer", "/works/OL1W", NOW - timedelta(minutes=58), title="BingX referral code", comment="Created new book")

        html = render()

        assert '<a class="new-accounts__name" href="/people/spammer">spammer</a>' in html
        assert 'href="/admin/people/spammer"' in html
        assert 'href="/admin/people/spammer/edits"' in html
        assert "spammer@example.org" in html
        assert '<span class="new-accounts__figure new-accounts__figure--fast">2.0 min</span>' in html
        assert '<a class="new-accounts__title" href="/works/OL1W">BingX referral code</a>' in html
        assert "Created new book" in html
        assert '<input type="hidden" name="username" value="spammer">' in html
        assert 'value="block_account"' in html
        assert 'value="block_account_and_revert"' in html
        assert html.count('class="do-confirm"') == 2
        assert 'method="post"' in html

    def test_user_text_is_escaped_and_not_linked(self, site, render):
        signup(site, "spammer", NOW - timedelta(hours=1))
        title = '<script>alert(1)</script> <a href="https://spam.example">win</a>'
        write(site, "spammer", "/works/OL1W", NOW - timedelta(minutes=58), title=title, comment="<b>https://spam.example</b>")
        site.docs["/people/spammer"]["displayname"] = "<img src=x onerror=alert(1)>"

        html = render()

        assert "<script>" not in html
        assert "<img" not in html
        assert "<b>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert 'href="https://spam.example"' not in html

    def test_blocked_accounts_get_no_buttons(self, site, render):
        signup(site, "spammer", NOW - timedelta(hours=1))
        write(site, "spammer", "/works/OL1W", NOW - timedelta(minutes=58))
        site.update_account("spammer", status="blocked")

        html = render()

        assert "<form" not in html
        assert "new-accounts__status--inactive" in html

    def test_notices_when_capped(self, site, render):
        for name in ("one", "two"):
            signup(site, name, NOW - timedelta(hours=2))
        for minutes in (60, 30):
            write(site, "one", f"/works/OL1{minutes}W", NOW - timedelta(minutes=minutes))
            write(site, "two", f"/works/OL2{minutes}W", NOW - timedelta(minutes=minutes))

        html = render(max_changes=3, page_size=3, max_accounts=1)

        assert "Only the newest 3 edits were scanned, back to 2100-01-01 11:00." in html
        assert "Showing the 1 busiest of 2 accounts." in html


class TestNewAccountsView:
    @pytest.fixture
    def request_as(self, site, monkeypatch):
        """Sends a request to /admin/new-accounts through the admin dispatcher, as an admin or not."""
        site.quicksave("/usergroup/admin", "/type/usergroup", members=[{"key": "/people/admin"}])
        monkeypatch.setattr(admin_code, "render", Mock())
        monkeypatch.setattr(admin_code, "add_flash_message", Mock())

        def send(user_key: str | None, method: str = "GET", fullpath: str = "/admin/new-accounts", **params):
            ctx: dict[str, object] = {
                "home": "http://localhost",
                "path": "/admin/new-accounts",
                "fullpath": fullpath,
                "method": method,
                "headers": [],
                "status": None,
            }
            for name, value in ctx.items():
                monkeypatch.setitem(web.ctx, name, value)
            user = user_key and Mock(key=user_key, is_librarian=lambda: False, is_super_librarian=lambda: True)
            monkeypatch.setattr(admin_code.context, "user", user, raising=False)
            monkeypatch.setattr(web, "input", lambda **defaults: web.storage(defaults, **params))
            return admin_code.admin().delegate()

        return send

    @pytest.mark.parametrize("user_key", [None, "/people/patron"])
    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_refuses_non_admins(self, site, request_as, monkeypatch, user_key, method):
        signup(site, "spammer", NOW - timedelta(hours=1))
        build = Mock()
        revert = Mock()
        monkeypatch.setattr(new_accounts, "build_report", build)
        monkeypatch.setattr(admin_code, "revert_all_user_edits", revert)

        result = request_as(user_key, method=method, username="spammer", action="block_account_and_revert")

        admin_code.render.permission_denied.assert_called_once_with("/admin/new-accounts", "Permission denied.")
        assert result is admin_code.render.permission_denied.return_value
        build.assert_not_called()
        revert.assert_not_called()
        assert site.store["account/spammer"]["status"] == "active"

    def test_page_renders_for_admins(self, site, request_as, render_template, monkeypatch):
        monkeypatch.setitem(web.template.Template.globals, "request", web.storage(path="/admin/new-accounts"))
        monkeypatch.setattr(new_accounts, "utcnow", lambda: NOW)
        signup(site, "veteran", NOW - timedelta(days=5))
        write(site, "veteran", "/works/OL1W", NOW - timedelta(hours=1))

        page = request_as("/people/admin")
        assert "veteran" in page["__body__"]
        assert page["title"] == "[Admin Center] New accounts"

        assert "No accounts under 3 days old" in request_as("/people/admin", days="3")["__body__"]
        # An override that can't be used falls back to the default.
        assert "Accounts under 7 days old" in request_as("/people/admin", days="abc", hours="-1")["__body__"]

    def test_block_returns_to_the_list(self, site, request_as):
        signup(site, "spammer", NOW - timedelta(hours=1))

        with pytest.raises(web.SeeOther):
            request_as("/people/admin", method="POST", fullpath="/admin/new-accounts?days=3", username="spammer", action="block_account")

        assert site.store["account/spammer"]["status"] == "blocked"
        assert [value for name, value in web.ctx.headers if name == "Location"] == ["http://localhost/admin/new-accounts?days=3"]

    def test_block_and_revert_runs_the_existing_action(self, site, request_as, monkeypatch):
        signup(site, "spammer", NOW - timedelta(hours=1))
        revert = Mock(return_value=(4, 2))
        monkeypatch.setattr(admin_code, "revert_all_user_edits", revert)

        with pytest.raises(web.SeeOther):
            request_as("/people/admin", method="POST", username="spammer", action="block_account_and_revert")

        assert site.store["account/spammer"]["status"] == "blocked"
        assert revert.call_args.args[0].username == "spammer"
        admin_code.add_flash_message.assert_called_once_with("info", "Blocked the account and reverted all 4 edits. 2 records deleted.")
        assert [value for name, value in web.ctx.headers if name == "Location"] == ["http://localhost/admin/new-accounts"]

    @pytest.mark.parametrize("action", ["", "su", "unblock_account", "anonymize_account", "update_password", "POST_su"])
    def test_other_people_actions_are_refused(self, site, request_as, action):
        signup(site, "spammer", NOW - timedelta(hours=1))

        with pytest.raises(web.HTTPError, match="400"):
            request_as("/people/admin", method="POST", username="spammer", action=action)

        assert site.store["account/spammer"]["status"] == "active"

    def test_unknown_account(self, site, request_as):
        with pytest.raises(web.HTTPError, match="404"):
            request_as("/people/admin", method="POST", username="nobody", action="block_account")
