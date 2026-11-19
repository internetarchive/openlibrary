"""Spam and abuse checks for edits, in one place.

Three layers, checked in order by `check_contribution`:
- who: `account_restriction` (read-only, deleted, blocked, or spam-domain accounts)
- what: `content_restriction` (admin-managed spam words at /admin/spamwords)
- proof: the captcha, which `needs_captcha` asks of accounts we don't trust yet
"""

import datetime as dt
import logging
import re
from collections.abc import Iterable
from enum import StrEnum

import web

from infogami import config
from openlibrary.plugins.recaptcha import recaptcha
from openlibrary.plugins.upstream.utils import render_template
from openlibrary.utils.request_context import site

logger = logging.getLogger("openlibrary.spamcheck")

# Accounts younger than this must solve a captcha unless trusted.
CAPTCHA_ACCOUNT_AGE_DAYS = 30


class SpamReason(StrEnum):
    READ_ONLY = "read-only"
    DELETED = "deleted"
    SPAM_EMAIL = "spam-email"
    BLOCKED = "blocked"
    SPAM_WORDS = "spam-words"
    CAPTCHA = "captcha"


def get_spam_words() -> list[str]:
    doc = site.get().store.get("spamwords") or {}
    return doc.get("spamwords", [])


def get_spam_domains() -> list[str]:
    doc = site.get().store.get("spamwords") or {}
    return doc.get("domains", [])


def set_spam_words(words: Iterable[str]) -> None:
    words = [w.strip() for w in words]
    _update_spam_doc(spamwords=words)


def set_spam_domains(domains: Iterable[str]) -> None:
    domains = [d.strip() for d in domains]
    _update_spam_doc(domains=domains)


def _update_spam_doc(**kwargs) -> None:
    doc = site.get().store.get("spamwords") or {}
    doc.update(_key="spamwords", **kwargs)
    site.get().store["spamwords"] = doc


def is_privileged(user) -> bool:
    """Admins and librarians skip the spam-word check and the captcha."""
    return bool(user and (user.is_admin() or user.is_librarian()))


def is_trusted(user) -> bool:
    """Privileged users, plus accounts a librarian has tagged `trusted-user`."""
    account = user and user.get_account()
    return bool(account and (is_privileged(user) or account.has_tag("trusted-user")))


def account_age_days(user) -> int | None:
    account = user and user.get_account()
    if not account:
        return None
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    return (now - account.creation_time()).days


def account_restriction(user) -> SpamReason | None:
    """Why this account may not edit at all, if it may not. Anonymous users pass."""
    if not user:
        return None
    if user.is_read_only():
        return SpamReason.READ_ONLY
    if user.type.key == "/type/delete":
        return SpamReason.DELETED
    if is_spam_email(user.get_email() or ""):
        return SpamReason.SPAM_EMAIL
    # Blocking an account doesn't stop its session from saving, so check the status here.
    account = user.get_account()
    if account and account.get("status") != "active":
        return SpamReason.BLOCKED
    return None


def content_restriction(i) -> SpamReason | None:
    text = str(dict(i)).lower()
    if any(re.search(w.lower(), text) for w in get_spam_words()):
        return SpamReason.SPAM_WORDS
    return None


def spam_reason(i, allow_privileged_edits: bool = False) -> SpamReason | None:
    user = site.get().get_user()
    if allow_privileged_edits and is_privileged(user):
        return None
    reason = account_restriction(user) or content_restriction(i)
    if reason:
        logger.info("Spam check refused %s: %s", user.key if user else "anonymous", reason)
    return reason


def is_spam(i, allow_privileged_edits: bool = False) -> bool:
    return spam_reason(i, allow_privileged_edits) is not None


def is_spam_email(email: str) -> bool:
    # Without the emptiness check, a blank line in the admin list blocked every account with no email.
    domain = email.rsplit("@", maxsplit=1)[-1].lower()
    return bool(domain) and domain in get_spam_domains()


def needs_captcha(user) -> bool:
    if not user or not user.get_account():
        return True
    if is_trusted(user):
        return False
    return (account_age_days(user) or 0) <= CAPTCHA_ACCOUNT_AGE_DAYS


def get_recaptcha() -> recaptcha.Recaptcha | None:
    """The captcha the current user must solve, or None if they're exempt."""
    if needs_captcha(site.get().get_user()):
        keys = config.get("plugin_recaptcha")
        return recaptcha.Recaptcha(keys.public_key, keys.private_key)
    return None


def check_contribution(i, *, captcha: bool = True) -> SpamReason | None:
    """The standard gate for an edit form: account and content checks, then the captcha if the user needs one."""
    if reason := spam_reason(i, allow_privileged_edits=True):
        return reason
    if captcha and (recap := get_recaptcha()) and not recap.validate_response(i.get("g-recaptcha-response"), web.ctx.ip):
        logger.info("Captcha failed for %s", (user := site.get().get_user()) and user.key)
        return SpamReason.CAPTCHA
    return None


def render_rejection(reason: SpamReason):
    """The page shown for a refused edit. Spam is told nothing specific, so it can't tune around the check."""
    if reason == SpamReason.CAPTCHA:
        return render_template(
            "message.html",
            "Recaptcha solution was incorrect",
            'Please <a href="javascript:history.back()">go back</a> and try again.',
        )
    return render_template("message.html", "Oops", "Something went wrong. Please try again later.")
