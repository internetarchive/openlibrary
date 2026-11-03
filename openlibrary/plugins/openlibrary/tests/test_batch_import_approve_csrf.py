"""Regression tests for the batch-import approval CSRF fix (GHSA-wq89-ph2h-pp44).

Approving a batch import used to run as a side-effecting GET on
``/import/batch/approve/<id>``, so a crawler, a prefetch, or a link an admin was
tricked into visiting could silently approve a batch (CSRF). These tests are
written to FAIL against the unfixed source:

- ``test_get_does_not_change_state`` fails because the old GET runs the UPDATE.
- the POST tests fail because the old handler has no POST handler at all.

With the fix the state change lives only on POST, which additionally requires an
admin session and a same-origin request (defense in depth atop SameSite=Lax).
"""

from unittest.mock import MagicMock, patch

import pytest

from openlibrary.plugins.openlibrary import code
from openlibrary.plugins.openlibrary.code import (
    BatchImportApprove,
    Forbidden,
    _is_same_origin_request,
)

ADMIN_KEY = "/people/admin"
BATCH_ID = "5"


class _User:
    def __init__(self, key):
        self.key = key


def _fake_ctx(origin=None, referer=None, host="openlibrary.org"):
    env = {}
    if origin is not None:
        env["HTTP_ORIGIN"] = origin
    if referer is not None:
        env["HTTP_REFERER"] = referer
    ctx = MagicMock()
    ctx.env = env
    ctx.host = host
    return ctx


def _patched(db_mock, user_key=ADMIN_KEY, ctx=None):
    """Patch the handler's collaborators: db spy, admin group, current user,
    and the redirect helpers (so no real web context is required)."""
    patches = [
        patch.object(code, "db", db_mock),
        patch.object(code, "_get_members_of_group", lambda group: [ADMIN_KEY]),
        patch.object(code.delegate, "context", MagicMock(user=_User(user_key))),
        patch.object(code.web, "seeother", lambda url: ("seeother", url)),
        patch.object(code.web, "found", lambda url: ("found", url)),
    ]
    if ctx is not None:
        patches.append(patch.object(code.web, "ctx", ctx))
    return patches


def _enter(patches):
    for p in patches:
        p.start()


def _exit(patches):
    for p in reversed(patches):
        p.stop()


def test_get_does_not_change_state():
    """The core CSRF fix: a GET must never run the approval UPDATE."""
    db_mock = MagicMock()
    patches = _patched(db_mock, ctx=_fake_ctx())
    _enter(patches)
    try:
        BatchImportApprove().GET(BATCH_ID)
        db_mock.query.assert_not_called()
    finally:
        _exit(patches)


def test_post_same_origin_admin_approves():
    db_mock = MagicMock()
    patches = _patched(db_mock, ctx=_fake_ctx(origin="https://openlibrary.org"))
    _enter(patches)
    try:
        BatchImportApprove().POST(BATCH_ID)
        assert db_mock.query.call_count == 1
        assert "UPDATE import_item" in db_mock.query.call_args[0][0]
    finally:
        _exit(patches)


def test_post_cross_origin_is_blocked_without_touching_state():
    db_mock = MagicMock()
    patches = _patched(db_mock, ctx=_fake_ctx(origin="https://evil.example.com"))
    _enter(patches)
    try:
        with pytest.raises(Forbidden):
            BatchImportApprove().POST(BATCH_ID)
        db_mock.query.assert_not_called()
    finally:
        _exit(patches)


def test_post_requires_admin():
    db_mock = MagicMock()
    patches = _patched(
        db_mock,
        user_key="/people/not_admin",
        ctx=_fake_ctx(origin="https://openlibrary.org"),
    )
    _enter(patches)
    try:
        with pytest.raises(Forbidden):
            BatchImportApprove().POST(BATCH_ID)
        db_mock.query.assert_not_called()
    finally:
        _exit(patches)


@pytest.mark.parametrize(
    ("origin", "referer", "expected"),
    [
        ("https://openlibrary.org", None, True),  # same-origin Origin
        ("https://evil.example.com", None, False),  # cross-origin Origin
        (None, "https://openlibrary.org/import/batch/5", True),  # Referer fallback, same
        (None, "https://evil.example.com/x", False),  # Referer fallback, cross
        (None, None, True),  # absent -> allowed (SameSite=Lax is the primary control)
    ],
)
def test_is_same_origin_request(origin, referer, expected):
    with patch.object(code.web, "ctx", _fake_ctx(origin=origin, referer=referer)):
        assert _is_same_origin_request() is expected
