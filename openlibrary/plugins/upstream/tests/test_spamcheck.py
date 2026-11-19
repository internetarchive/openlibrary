import datetime as dt
from types import SimpleNamespace

import pytest
import web

from openlibrary.plugins.upstream import spamcheck
from openlibrary.plugins.upstream.spamcheck import SpamReason


class FakeAccount(dict):
    def __init__(self, age_days=365, tags=(), status="active"):
        super().__init__(status=status)
        self.age_days = age_days
        self.tags = set(tags)

    def has_tag(self, tag):
        return tag in self.tags

    def creation_time(self):
        return dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=self.age_days, hours=1)


def make_user(*, admin=False, librarian=False, read_only=False, deleted=False, email="a@example.com", account=None):
    account = FakeAccount() if account is None else account
    return SimpleNamespace(
        key="/people/alice",
        type=SimpleNamespace(key="/type/delete" if deleted else "/type/user"),
        is_admin=lambda: admin,
        is_librarian=lambda: librarian,
        is_read_only=lambda: read_only,
        get_email=lambda: email,
        get_account=lambda: account or None,
    )


@pytest.fixture
def current(monkeypatch):
    """Set the current user and the admin spam lists."""
    state = SimpleNamespace(user=None, store={"spamwords": {"spamwords": ["promo code"], "domains": ["spam.example"]}})
    fake_site = SimpleNamespace(get_user=lambda: state.user, store=state.store)
    monkeypatch.setattr(spamcheck, "site", SimpleNamespace(get=lambda: fake_site))
    monkeypatch.setattr(web.ctx, "ip", "127.0.0.1", raising=False)
    return state


class TestSpamReason:
    @pytest.mark.parametrize(
        ("user_kwargs", "expected"),
        [
            ({}, None),
            ({"read_only": True}, SpamReason.READ_ONLY),
            ({"deleted": True}, SpamReason.DELETED),
            ({"email": "bot@spam.example"}, SpamReason.SPAM_EMAIL),
            ({"account": FakeAccount(status="blocked")}, SpamReason.BLOCKED),
        ],
    )
    def test_account_rules(self, current, user_kwargs, expected):
        current.user = make_user(**user_kwargs)
        assert spamcheck.spam_reason({"title": "A real book"}) == expected

    def test_spam_words(self, current):
        current.user = make_user()
        assert spamcheck.spam_reason({"title": "BingX PROMO CODE"}) == SpamReason.SPAM_WORDS

    def test_anonymous_is_only_word_checked(self, current):
        assert spamcheck.spam_reason({"title": "A real book"}) is None
        assert spamcheck.spam_reason({"title": "promo code"}) == SpamReason.SPAM_WORDS

    @pytest.mark.parametrize("role", ["admin", "librarian"])
    def test_privileged_edits_skip_every_check_when_allowed(self, current, role):
        current.user = make_user(read_only=True, **{role: True})
        assert spamcheck.spam_reason({"title": "promo code"}, allow_privileged_edits=True) is None
        assert spamcheck.spam_reason({"title": "promo code"}) == SpamReason.READ_ONLY

    def test_is_spam_matches_spam_reason(self, current):
        current.user = make_user()
        assert spamcheck.is_spam({"title": "promo code"}) is True
        assert spamcheck.is_spam({"title": "A real book"}) is False

    def test_blank_domain_in_admin_list_does_not_block_accounts_without_email(self, current):
        current.store["spamwords"]["domains"] = ["spam.example", ""]
        current.user = make_user(email=None)
        assert spamcheck.spam_reason({"title": "A real book"}) is None
        assert spamcheck.is_spam_email("") is False


class TestNeedsCaptcha:
    @pytest.mark.parametrize(
        ("user", "expected"),
        [
            (None, True),
            (make_user(account=False), True),
            (make_user(account=FakeAccount(age_days=2)), True),
            (make_user(account=FakeAccount(age_days=30)), True),
            (make_user(account=FakeAccount(age_days=31)), False),
            (make_user(account=FakeAccount(age_days=2, tags={"trusted-user"})), False),
            (make_user(librarian=True, account=FakeAccount(age_days=2)), False),
            (make_user(admin=True, account=FakeAccount(age_days=2)), False),
        ],
    )
    def test_who_needs_a_captcha(self, user, expected):
        assert spamcheck.needs_captcha(user) is expected


class TestCheckContribution:
    @pytest.fixture
    def captcha(self, monkeypatch):
        """Make the captcha required, and solved only by the token "ok"."""
        recap = SimpleNamespace(validate_response=lambda response, ip: response == "ok")
        monkeypatch.setattr(spamcheck, "get_recaptcha", lambda: recap)

    def test_spam_is_refused_before_the_captcha(self, current, captcha):
        current.user = make_user()
        assert spamcheck.check_contribution({"title": "promo code", "g-recaptcha-response": "ok"}) == SpamReason.SPAM_WORDS

    def test_failed_captcha(self, current, captcha):
        current.user = make_user()
        assert spamcheck.check_contribution({"title": "A real book"}) == SpamReason.CAPTCHA
        assert spamcheck.check_contribution({"title": "A real book", "g-recaptcha-response": "ok"}) is None

    def test_captcha_can_be_skipped(self, current, captcha):
        current.user = make_user()
        assert spamcheck.check_contribution({"title": "A real book"}, captcha=False) is None

    def test_privileged_users_pass_the_word_check(self, current, monkeypatch):
        monkeypatch.setattr(spamcheck, "get_recaptcha", lambda: None)
        current.user = make_user(librarian=True)
        assert spamcheck.check_contribution({"title": "promo code"}) is None


class TestCallSites:
    def test_author_edit_refuses_spam(self, current, monkeypatch):
        from openlibrary import accounts
        from openlibrary.plugins.upstream import addbook

        current.user = make_user(account=FakeAccount(status="blocked"))
        monkeypatch.setattr(accounts, "get_current_user", lambda: current.user)
        monkeypatch.setattr(addbook, "site", SimpleNamespace(get=lambda: SimpleNamespace(get=lambda key: {"key": key})))
        monkeypatch.setattr(web, "input", lambda **kw: web.storage(kw, _save="Save"))
        monkeypatch.setattr(spamcheck, "render_rejection", lambda reason: reason)
        assert addbook.author_edit().POST("/authors/OL1A") == SpamReason.BLOCKED

    def test_cover_upload_refuses_blocked_accounts(self, current, monkeypatch):
        from openlibrary.plugins.upstream import covers

        user = make_user(account=FakeAccount(status="blocked"))
        monkeypatch.setattr(covers.accounts, "get_current_user", lambda: user)
        monkeypatch.setattr(web.ctx, "headers", [], raising=False)
        monkeypatch.setattr(covers, "site", SimpleNamespace(get=lambda: SimpleNamespace(get=lambda key: {"key": key})))
        with pytest.raises(web.HTTPError, match="403"):
            covers.add_cover().POST("/books/OL1M")
