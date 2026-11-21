from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
import web
from markupsafe import Markup

from openlibrary.core.jinja import get_jinja_env, render_jinja_template
from openlibrary.plugins.admin import code as admin_code
from openlibrary.plugins.admin import new_accounts
from openlibrary.plugins.admin.new_accounts import build_report, clamp_param, format_duration

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


@pytest.fixture(autouse=True)
def stub_icon(monkeypatch):
    """The icon sprite macro isn't loaded in tests."""
    monkeypatch.setitem(get_jinja_env().globals, "icon", lambda name, **kwargs: Markup(f'<svg class="ol-icon" data-icon="{name}"></svg>'))


@pytest.fixture
def site(mock_site, request_context_fixture):
    request_context_fixture(lang="en")
    return mock_site


class TestBuildReport:
    def test_no_changes(self, site):
        report = build_report(site, now=NOW)
        assert report.rows == []
        assert report.matching_accounts == 0
        assert not report.capped
        assert report.age_label == "7 days"

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

    def test_edits_before_the_scan_count_only_towards_the_total(self, site):
        signup(site, "returning", NOW - timedelta(days=3))
        write(site, "returning", "/works/OL1W", NOW - timedelta(days=3) + timedelta(minutes=5))
        write(site, "returning", "/works/OL2W", NOW - timedelta(hours=2))
        signup(site, "other", NOW - timedelta(minutes=90))
        write(site, "other", "/works/OL3W", NOW - timedelta(hours=1))

        row = next(row for row in build_report(site, now=NOW, max_changes=3).rows if row.username == "returning")

        assert (row.edits_in_window, row.total_edits, row.total_edits_label) == (1, 2, "2")
        assert row.exact
        # The first write is the one from three days ago, found in the account's own history.
        assert row.first_write_delay == timedelta(minutes=5)
        # A scan that runs out of changes holds every edit.
        assert next(row for row in build_report(site, now=NOW).rows if row.username == "returning").edits_in_window == 2

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

    def test_a_capped_load_says_so(self, site):
        signup(site, "early", NOW - timedelta(hours=10))
        signup(site, "late", NOW - timedelta(hours=10))
        for n in range(3):
            write(site, "early", f"/works/OL1{n}W", NOW - timedelta(hours=9, minutes=-n))
        for n in range(4):
            write(site, "late", f"/works/OL2{n}W", NOW - timedelta(hours=1, minutes=-n))

        report = build_report(site, now=NOW, max_changes=4)

        assert report.capped
        assert report.changes_loaded == 4
        assert report.loaded_back_to_label == "2100-01-01 11:00"
        # `early` only wrote before the cut; `late` signed up before it, so its history is loaded on its own.
        assert [(row.username, row.edits_in_window_label, row.total_edits_label, row.exact) for row in report.rows] == [("late", "4", "4", True)]
        assert not build_report(site, now=NOW, max_changes=4, history_limit=2).rows[0].exact
        assert not build_report(site, now=NOW, max_changes=100).capped

    def test_a_failed_load_names_the_error(self, site, monkeypatch):
        monkeypatch.setattr(new_accounts, "scan_recent_changes", Mock(side_effect=RuntimeError("no pool")))

        report = build_report(site, now=NOW)

        assert report.error.startswith("RuntimeError: no pool (")
        assert report.rows == []

    def test_calls(self, site, monkeypatch):
        for n in range(3):
            signup(site, f"user{n}", NOW - timedelta(hours=2))
            write(site, f"user{n}", f"/works/OL{n}W", NOW - timedelta(hours=1))
        get_many = Mock(side_effect=site.get_many)
        recentchanges = Mock(side_effect=site.recentchanges)
        monkeypatch.setattr(site, "get_many", get_many)
        monkeypatch.setattr(site, "recentchanges", recentchanges)

        assert len(build_report(site, now=NOW).rows) == 3

        # One batch each of profiles, records checked for signals, and titles; one scan page and no per-account history.
        assert get_many.call_count == 3
        assert recentchanges.call_count == 1


class TestSignals:
    def save(self, site, username: str, doc: dict, minutes_ago: int, kind: str = "add-book"):
        site.save(doc, timestamp=NOW - timedelta(minutes=minutes_ago), action=kind, author=web.storage(key=f"/people/{username}"))

    def work(self, n: int, **fields) -> dict:
        return {"key": f"/works/OL{n}W", "type": {"key": "/type/work"}, "title": "A title", **fields}

    def signals(self, site, **kwargs) -> dict[str, list[tuple[str, bool]]]:
        return {row.username: [(s.code, s.strong) for s in row.signals] for row in build_report(site, now=NOW, **kwargs).rows}

    def test_a_reader_filling_lists_has_none(self, site):
        signup(site, "reader", NOW - timedelta(hours=2))
        reading_list = {"key": "/people/reader/lists/OL1L", "type": {"key": "/type/list"}, "name": "To read"}
        self.save(site, "reader", reading_list, 110, kind="create-list")
        for n in range(30):
            self.save(site, "reader", reading_list, 100 - n, kind="edit-list-seeds")

        assert self.signals(site) == {"reader": []}
        assert build_report(site, now=NOW, show="likely").rows == []

    @pytest.mark.parametrize(
        "description",
        [
            "Call 1-888-314-1997 to change your flight",
            "Reach us on +44 (20) 7946 0958 any time",
        ],
    )
    def test_phone_numbers(self, site, description):
        signup(site, "support", NOW - timedelta(hours=2))
        self.save(site, "support", self.work(1, description=description), 100)

        assert self.signals(site) == {"support": [("phone", True)]}

    @pytest.mark.parametrize("description", ["ISBN 0-14-118776-1, published 1997", "9780141187761", "Printed 1997 2001 2005"])
    def test_isbns_and_years_are_not_phone_numbers(self, site, description):
        signup(site, "librarian", NOW - timedelta(hours=2))
        self.save(site, "librarian", self.work(1, description=description), 100)

        assert self.signals(site) == {"librarian": []}

    def test_a_phone_number_next_to_catalog_work_is_only_worth_a_look(self, site):
        signup(site, "publisher", NOW - timedelta(hours=2))
        self.save(site, "publisher", self.work(1, description="Orders: 555 123 4567 89"), 100)
        self.save(site, "publisher", self.work(1, description="Orders: 555 123 4567 89", covers=[1]), 90, kind="add-cover")

        [row] = build_report(site, now=NOW).rows
        assert ([(s.code, s.strong) for s in row.signals], row.tier) == ([("phone", False)], "look")

    def test_phone_numbers_count_in_records_edited_but_links_dont(self, site):
        site.save(self.work(1, description="See www.publisher.example.com"), timestamp=NOW - timedelta(days=30))
        signup(site, "vandal", NOW - timedelta(hours=2))
        signup(site, "editor", NOW - timedelta(hours=2))
        self.save(site, "vandal", self.work(1, description="Expedia help line 1 888 555 0100 01"), 100, kind="edit-book")
        site.save(self.work(2, description="See www.publisher.example.com"), timestamp=NOW - timedelta(days=30))
        self.save(site, "editor", self.work(2, description="See www.publisher.example.com", subtitle="Fixed"), 100, kind="edit-book")

        assert self.signals(site) == {"vandal": [("phone", True)], "editor": []}

    @pytest.mark.parametrize(
        "title", ["Delta Airlines customer service number", "Viral Vue promo code SOFIA10", "Buy Ativan 1mg online", "How to talk to a live person"]
    )
    def test_sales_wording(self, site, title):
        signup(site, "seller", NOW - timedelta(hours=2))
        self.save(site, "seller", self.work(1, title=title), 100)

        assert ("sales", True) in self.signals(site)["seller"]

    @pytest.mark.parametrize("title", ["Flight Behavior", "The Cruise of the Cachalot", "Customer Service for Dummies", "Online Learning"])
    def test_book_titles_are_not_sales_wording(self, site, title):
        signup(site, "reader", NOW - timedelta(hours=2))
        self.save(site, "reader", self.work(1, title=title), 100)

        assert self.signals(site) == {"reader": []}

    def test_spam_words(self, site):
        signup(site, "spammer", NOW - timedelta(hours=2))
        self.save(site, "spammer", self.work(1, title="Best Kittens"), 100)

        assert self.signals(site, spam_words=["kittens"]) == {"spammer": [("spam-words", True)]}
        assert self.signals(site, spam_words=["unrelated"]) == {"spammer": []}

    def test_many_lists(self, site):
        signup(site, "lister", NOW - timedelta(hours=2))
        signup(site, "reader", NOW - timedelta(hours=2))
        for n in range(new_accounts.MANY_LISTS):
            self.save(site, "lister", {"key": f"/people/lister/lists/OL{n}L", "type": {"key": "/type/list"}, "name": "L"}, 100 - n, kind="lists")
        for n in range(new_accounts.MANY_LISTS - 1):
            self.save(site, "reader", {"key": f"/people/reader/lists/OL{n}L", "type": {"key": "/type/list"}, "name": "L"}, 100 - n, kind="create-list")

        assert self.signals(site) == {"lister": [("lists", True)], "reader": []}

    def test_a_profile_link_as_the_only_edit_is_likely_spam(self, site):
        signup(site, "seo", NOW - timedelta(hours=2))
        signup(site, "author", NOW - timedelta(hours=2))
        self.save(site, "seo", {"key": "/people/seo", "type": {"key": "/type/user"}, "website": ["https://88bet.example.vip"]}, 119, kind="default-update")
        self.save(site, "author", {"key": "/people/author", "type": {"key": "/type/user"}, "website": ["https://author.example.com"]}, 110, kind="default-update")
        self.save(site, "author", self.work(1), 100)

        assert self.signals(site) == {"seo": [("profile-link", True)], "author": [("links", False)]}

    def test_reference_links_are_not_promotion(self, site):
        signup(site, "librarian", NOW - timedelta(hours=2))
        self.save(site, "librarian", self.work(1, description="See https://en.wikipedia.org/wiki/Book"), 100)

        assert self.signals(site) == {"librarian": []}

    def test_article_formatting(self, site):
        signup(site, "writer", NOW - timedelta(hours=2))
        self.save(site, "writer", self.work(1, description="## Why it matters\n**Great** read"), 100)

        assert self.signals(site) == {"writer": [("markdown", False)]}

    def test_deleted_catalog_records(self, site):
        signup(site, "spammer", NOW - timedelta(hours=2))
        self.save(site, "spammer", self.work(1, title="Junk"), 100)
        site.save({"key": "/works/OL1W", "type": {"key": "/type/delete"}}, timestamp=NOW - timedelta(minutes=10))

        assert self.signals(site) == {"spammer": [("deleted", True)]}

    def test_a_record_created_then_edited_is_still_its_own(self, site):
        signup(site, "spammer", NOW - timedelta(hours=2))
        self.save(site, "spammer", self.work(1, title="Junk"), 100)
        self.save(site, "spammer", self.work(1, title="Junk", description="## Why it matters\n**Great** read"), 90, kind="edit-book")

        assert self.signals(site) == {"spammer": [("markdown", False)]}

        site.save({"key": "/works/OL1W", "type": {"key": "/type/delete"}}, timestamp=NOW - timedelta(minutes=10))
        assert self.signals(site) == {"spammer": [("deleted", True)]}

    def test_burst_after_signup(self, site):
        signup(site, "fast", NOW - timedelta(hours=3))
        signup(site, "steady", NOW - timedelta(hours=3))
        for n in range(new_accounts.BURST_RECORDS):
            self.save(site, "fast", self.work(10 + n), 170 - n)
            self.save(site, "steady", self.work(30 + n), 100 - n)

        assert self.signals(site) == {"fast": [("burst", False)], "steady": []}

    def test_tiers_order_the_rows_and_filter_them(self, site):
        signup(site, "reader", NOW - timedelta(hours=2))
        signup(site, "author", NOW - timedelta(hours=2))
        signup(site, "spammer", NOW - timedelta(hours=2))
        for n in range(5):
            self.save(site, "reader", {"key": "/people/reader/lists/OL1L", "type": {"key": "/type/list"}, "name": "L"}, 100 - n, kind="edit-list-seeds")
        self.save(site, "author", self.work(1, description="More at author.example.com"), 100)
        self.save(site, "spammer", self.work(2, title="Promo code SAVE10"), 100)

        report = build_report(site, now=NOW)

        assert [(row.username, row.tier) for row in report.rows] == [("spammer", "likely"), ("author", "look"), ("reader", "none")]
        assert (report.rows[2].list_additions, report.rows[2].other_edits) == (5, 0)
        assert (report.matching_accounts, report.likely_accounts, report.look_accounts) == (3, 1, 1)
        assert [row.username for row in build_report(site, now=NOW, show="likely").rows] == ["spammer"]
        assert [row.username for row in build_report(site, now=NOW, show="look").rows] == ["author"]

    def test_reviewed_accounts_leave_the_queue(self, site):
        for name in ("spammer", "author", "other"):
            signup(site, name, NOW - timedelta(hours=2))
        self.save(site, "spammer", self.work(1, title="Promo code SAVE10"), 100)
        self.save(site, "author", self.work(2, description="More at author.example.com"), 100)
        self.save(site, "other", self.work(3, title="Promo code SAVE20"), 100)
        site.update_account("spammer", status="blocked")
        site.store["account/author"]["tags"] = ["trusted-user"]

        report = build_report(site, now=NOW, show="likely")

        assert [row.username for row in report.rows] == ["other"]
        assert (report.likely_accounts, report.look_accounts, report.reviewed_accounts) == (1, 0, 2)
        reviewed = build_report(site, now=NOW, show="reviewed").rows
        assert sorted((row.username, row.review) for row in reviewed) == [("author", "trusted"), ("spammer", "blocked")]


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
        assert "No accounts under 7 days old made any of these edits." in html
        assert "<table" not in html
        assert "<strong>Spam review</strong>" in html  # the admin menu, on its current page

    def test_rows_carry_what_an_admin_needs(self, site, render):
        signup(site, "spammer", NOW - timedelta(hours=1))
        write(site, "spammer", "/works/OL1W", NOW - timedelta(minutes=58), title="BingX referral code", comment="Created new book")

        html = render()

        assert 'href="/people/spammer"\n' in html
        assert 'title="spammer">spammer</a>' in html
        assert 'href="/admin/people/spammer"' in html
        assert '<a href="/people/spammer">Profile</a>' in html
        assert 'href="/admin/people/spammer/edits"' in html
        assert "spammer@example.org" in html
        assert '<span class="new-accounts__minor new-accounts__fast">2.0 min to first edit</span>' in html
        assert 'title="BingX referral code">BingX referral code</a>' in html
        assert "Created new book" in html
        assert 'name="username"' in html
        assert 'value="spammer"' in html
        for action in ("block_account", "block_account_and_revert", "mark_trusted"):
            assert f'value="{action}"' in html
        assert html.count('method="post"') == 1

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

    def test_reviewed_accounts_say_how(self, site, render):
        for n, name in enumerate(("blocked", "reverted", "trusted")):
            signup(site, name, NOW - timedelta(hours=1))
            write(site, name, f"/works/OL{n}W", NOW - timedelta(minutes=58))
        site.update_account("blocked", status="blocked")
        site.update_account("reverted", status="blocked")
        # A revert saves the record again.
        site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Reverted"}, timestamp=NOW, action="revert")
        site.store["account/trusted"]["tags"] = ["trusted-user"]

        html = render(show="reviewed")

        assert 'class="new-accounts__row--blocked"' in html
        assert 'class="new-accounts__row--reverted"' in html
        assert 'class="new-accounts__row--trusted"' in html
        assert "Blocked, edits reverted" in html
        assert ">Trusted<" in html

    def test_notices_how_far_back_and_how_many(self, site, render):
        for name in ("one", "two"):
            signup(site, name, NOW - timedelta(hours=2))
        for minutes in (60, 30):
            write(site, "one", f"/works/OL1{minutes}W", NOW - timedelta(minutes=minutes))
            write(site, "two", f"/works/OL2{minutes}W", NOW - timedelta(minutes=minutes))

        html = render(max_changes=3, max_accounts=1)

        assert "Accounts under 7 days old in the newest 3 edits, back to 2100-01-01 11:00." in html
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

        result = request_as(user_key, method=method, username=["spammer"], action="block_account_and_revert")

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
        assert page["title"] == "[Admin Center] Spam review"
        # By default only likely spam is listed; ?show=all lists the rest.
        assert "None of the 1 accounts under 7 days old" in page["__body__"]
        assert "How accounts are flagged" in page["__body__"]
        assert "veteran" in request_as("/people/admin", show="all")["__body__"]
        assert "veteran" not in request_as("/people/admin", show="bogus")["__body__"]

        assert "No accounts under 3 days old" in request_as("/people/admin", days="3")["__body__"]
        # An override that can't be used falls back to the default.
        assert "Accounts under 7 days old" in request_as("/people/admin", days="abc")["__body__"]

    def test_block_returns_to_the_list(self, site, request_as):
        signup(site, "spammer", NOW - timedelta(hours=1))

        with pytest.raises(web.SeeOther):
            request_as("/people/admin", method="POST", fullpath="/admin/new-accounts?days=3", username=["spammer"], action="block_account")

        assert site.store["account/spammer"]["status"] == "blocked"
        assert [value for name, value in web.ctx.headers if name == "Location"] == ["http://localhost/admin/new-accounts?days=3"]
        admin_code.add_flash_message.assert_called_once_with("info", "Blocked 1 account.")

    def test_block_and_revert_many(self, site, request_as, monkeypatch):
        for name in ("one", "two"):
            signup(site, name, NOW - timedelta(hours=1))
        revert = Mock(return_value=(4, 2))
        monkeypatch.setattr(admin_code, "revert_all_user_edits", revert)

        with pytest.raises(web.SeeOther):
            request_as("/people/admin", method="POST", username=["one", "two", "one", "nobody"], action="block_account_and_revert")

        assert site.store["account/one"]["status"] == site.store["account/two"]["status"] == "blocked"
        assert [call.args[0].username for call in revert.call_args_list] == ["one", "two"]
        admin_code.add_flash_message.assert_called_once_with("info", "Blocked 2 accounts. Reverted 8 edits and deleted 4 records.")

    def test_mark_trusted(self, site, request_as):
        signup(site, "author", NOW - timedelta(hours=1))

        with pytest.raises(web.SeeOther):
            request_as("/people/admin", method="POST", username=["author"], action="mark_trusted")

        assert site.store["account/author"]["tags"] == ["trusted-user"]
        assert site.store["account/author"]["status"] == "active"

    @pytest.mark.parametrize("action", ["", "su", "unblock_account", "anonymize_account", "update_password", "POST_su"])
    def test_other_people_actions_are_refused(self, site, request_as, action):
        signup(site, "spammer", NOW - timedelta(hours=1))

        with pytest.raises(web.HTTPError, match="400"):
            request_as("/people/admin", method="POST", username=["spammer"], action=action)

        assert site.store["account/spammer"]["status"] == "active"

    def test_nothing_selected(self, site, request_as):
        with pytest.raises(web.SeeOther):
            request_as("/people/admin", method="POST", username=["nobody"], action="block_account")

        admin_code.add_flash_message.assert_called_once_with("error", "Select at least one account.")
