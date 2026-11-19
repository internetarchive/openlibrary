import datetime as dt
import hashlib
import hmac
import json
import logging
import re
import time
from collections.abc import Iterable, MutableMapping

import web

from infogami.utils.view import public
from openlibrary.accounts.model import get_secret_key
from openlibrary.core import stats
from openlibrary.utils.request_context import site


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


def is_spam(i, allow_privileged_edits: bool = False) -> bool:
    user = site.get().get_user()

    if user:
        # Allow admins and librarians to make edits:
        if allow_privileged_edits and (user.is_admin() or user.is_librarian()):
            return False
        if user.is_read_only():
            return True
        # Prevent deleted users from making edits:
        if user.type.key == "/type/delete":
            return True

    email = (user and user.get_email()) or ""
    if is_spam_email(email):
        return True

    # For some odd reason, blocked accounts are still allowed to make edits.
    # Hack to stop that.
    account = user and user.get_account()
    if account and account.get("status") != "active":
        return True

    spamwords = get_spam_words()
    text = str(dict(i)).lower()
    return any(re.search(w.lower(), text) for w in spamwords)


def is_spam_email(email: str) -> bool:
    domain = email.rsplit("@", maxsplit=1)[-1].lower()
    return domain in get_spam_domains()


# Log-only form signals: a honeypot field and a signed rendered-at token (templates/lib/form_signals.html).
# Nothing here refuses or changes a submission; the thresholds only decide how one is labelled in the log.
HONEYPOT_FIELD = "ol_extra_notes"
FORM_TOKEN_FIELD = "ol_form_token"
FAST_SUBMIT_SECONDS = 5
STALE_TOKEN_SECONDS = 24 * 60 * 60
HONEYPOT_SAMPLE_CHARS = 40

signals_logger = logging.getLogger("openlibrary.spam_signals")


def _current_username() -> str:
    user = site.get().get_user()
    return user.key.split("/")[-1] if user else ""


def _sign_form_token(surface: str, username: str, rendered_at: str) -> str:
    msg = f"form-token|{surface}|{username}|{rendered_at}"
    return hmac.new(get_secret_key().encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


@public
def make_form_token(surface: str) -> str:
    """A "surface|rendered-at|hmac" token for the form being rendered, bound to the current user. Blank if it can't be signed."""
    try:
        rendered_at = f"{time.time():.3f}"
        return f"{surface}|{rendered_at}|{_sign_form_token(surface, _current_username(), rendered_at)}"
    except Exception:
        signals_logger.exception("Could not sign a form token for %s", surface)
        return ""


def _read_form_token(token: str, surface: str) -> tuple[str, str, float | None]:
    """Returns (timing label, surface the form was rendered for, elapsed seconds)."""
    if not token:
        return "missing", surface, None
    try:
        token_surface, rendered_at, signature = token.split("|")
        # A page of the same flow may label itself, e.g. "add-book-check" posting to "add-book".
        if token_surface != surface and not token_surface.startswith(f"{surface}-"):
            return "invalid", surface, None
        if not hmac.compare_digest(signature, _sign_form_token(token_surface, _current_username(), rendered_at)):
            return "invalid", surface, None
        elapsed = time.time() - float(rendered_at)
    except ValueError, TypeError:
        return "invalid", surface, None
    if elapsed < FAST_SUBMIT_SECONDS:
        return "fast", token_surface, elapsed
    return ("stale" if elapsed > STALE_TOKEN_SECONDS else "ok"), token_surface, elapsed


def _log_submission(surface: str, timing: str, elapsed: float | None = None, honeypot: str = "") -> None:
    user = site.get().get_user()
    created = getattr(user, "created", None)
    record = {
        "surface": surface,
        "username": user.key.split("/")[-1] if user else None,
        "account_age_days": (dt.datetime.now() - created.replace(tzinfo=None)).days if isinstance(created, dt.datetime) else None,
        "honeypot_filled": bool(honeypot.strip()),
        "timing": timing,
        "elapsed_seconds": None if elapsed is None else round(elapsed, 1),
    }
    if record["honeypot_filled"]:
        record["honeypot_sample"] = honeypot.strip()[:HONEYPOT_SAMPLE_CHARS]
        stats.increment(f"ol.spam_signals.{surface}.honeypot_filled")
    stats.increment(f"ol.spam_signals.{surface}.timing.{timing}")
    signals_logger.info("form_signals %s", json.dumps(record, sort_keys=True))


def record_form_signals(surface: str, form: MutableMapping | None = None) -> None:
    """Log whether the honeypot was filled and how long the form took to come back. Never refuses, never raises.

    Takes both fields out of `form` (default: `web.input()`), so they can't reach the spam-word check or a saved record.
    """
    try:
        if form is None:
            form = web.input()
        honeypot = str(form.pop(HONEYPOT_FIELD, "") or "")
        token = str(form.pop(FORM_TOKEN_FIELD, "") or "")
        timing, token_surface, elapsed = _read_form_token(token, surface)
        _log_submission(token_surface, timing, elapsed, honeypot)
    except Exception:
        signals_logger.exception("Could not record form signals for %s", surface)


def record_formless_submission(surface: str) -> None:
    """Count a write that has no HTML form to measure (a JSON API), so the form signals have a denominator. Never raises."""
    try:
        _log_submission(surface, "no-form")
    except Exception:
        signals_logger.exception("Could not record a submission for %s", surface)
