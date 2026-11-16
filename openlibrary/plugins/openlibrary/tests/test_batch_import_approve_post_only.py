"""Regression tests for the batch-import approval CSRF fix (GHSA-wq89-ph2h-pp44).

Approving a batch import used to run as a side-effecting GET on
``/import/batch/approve/<id>``, so a crawler, a prefetch, or a link an admin was
tricked into visiting could silently approve a batch (CSRF). The fix is minimal:
the state change moves to a POST that keeps the existing admin check, and the GET
is made inert.

There is no CSRF token -- protection rests on the browser *not* attaching the
admin's auth cookie to a forged cross-site POST. That only holds if the auth
cookie is ``SameSite=Lax``. The auth cookie is ``config.login_cookie_name``
(``session`` in ``conf/openlibrary.yml``), NOT ``s3`` (``s3`` carries archive.org
API keys, not the Open Library session). ``test_session_cookie_is_samesite_lax``
is the tripwire guarding that the *session* cookie stays ``SameSite=Lax``.

Written to FAIL against the unfixed source:
- ``test_get_does_not_change_state`` fails because the old GET runs the UPDATE.
- the POST tests fail because the old handler has no POST handler at all.
- ``test_session_cookie_is_samesite_lax`` fails because web.py's
  ``_set_login_cookies`` set the ``session`` cookie with no ``samesite``.
"""

from unittest.mock import MagicMock, patch

import pytest

from openlibrary.plugins.openlibrary import code
from openlibrary.plugins.openlibrary.code import BatchImportApprove, Forbidden

ADMIN_KEY = "/people/admin"
BATCH_ID = "5"


class _User:
    def __init__(self, key):
        self.key = key


def _patched(db_mock, user_key=ADMIN_KEY):
    """Patch the handler's collaborators: db spy, admin group, current user, and
    the redirect helper (so no real web context is required)."""
    return [
        patch.object(code, "db", db_mock),
        patch.object(code, "_get_members_of_group", lambda group: [ADMIN_KEY]),
        patch.object(code.delegate, "context", MagicMock(user=_User(user_key))),
        patch.object(code.web, "seeother", lambda url: ("seeother", url)),
        patch.object(code.web, "found", lambda url: ("found", url)),
    ]


def _enter(patches):
    for p in patches:
        p.start()


def _exit(patches):
    for p in reversed(patches):
        p.stop()


def test_get_does_not_change_state():
    """The core CSRF fix: a GET must never run the approval UPDATE."""
    db_mock = MagicMock()
    patches = _patched(db_mock)
    _enter(patches)
    try:
        BatchImportApprove().GET(BATCH_ID)
        db_mock.query.assert_not_called()
    finally:
        _exit(patches)


def test_post_admin_approves():
    db_mock = MagicMock()
    patches = _patched(db_mock)
    _enter(patches)
    try:
        BatchImportApprove().POST(BATCH_ID)
        assert db_mock.query.call_count == 1
        assert "UPDATE import_item" in db_mock.query.call_args[0][0]
    finally:
        _exit(patches)


def test_post_requires_admin():
    db_mock = MagicMock()
    patches = _patched(db_mock, user_key="/people/not_admin")
    _enter(patches)
    try:
        with pytest.raises(Forbidden):
            BatchImportApprove().POST(BATCH_ID)
        db_mock.query.assert_not_called()
    finally:
        _exit(patches)


def test_session_cookie_is_samesite_lax():
    """Tripwire: the approve fix is a bare POST + admin check, which is safe only
    because the *auth* cookie (``config.login_cookie_name`` -> ``session``) is
    ``SameSite=Lax``. If that attribute is ever dropped, a forged cross-site POST
    would carry the admin's session and the CSRF protection would be gone -- so
    this must fail loudly.

    Note: this asserts the ``session`` cookie, NOT ``s3``. ``s3`` holds
    archive.org API keys and is not the Open Library session; asserting ``s3``
    (as an earlier version of this test did) is a false green that leaves the
    actual auth cookie unguarded.
    """
    from openlibrary.plugins.upstream import account

    recorded = {}

    def fake_setcookie(name, value, **kwargs):
        recorded[name] = kwargs

    fake_config = MagicMock()
    fake_config.login_cookie_name = "session"

    with (
        patch.object(account.web, "setcookie", fake_setcookie),
        patch.object(account.web, "ctx", MagicMock()),
        patch.object(account, "config", fake_config),
        patch.object(account, "encrypt_s3_keys", lambda a, s: "tok"),
    ):
        account._set_login_cookies(
            {"s3_keys": {"access": "a", "secret": "s"}, "special_access": False},
            ol_account=None,
        )

    assert recorded["session"]["samesite"] == "Lax"
