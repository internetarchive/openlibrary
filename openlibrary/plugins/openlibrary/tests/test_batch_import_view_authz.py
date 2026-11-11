"""Regression tests for the batch-import view authorization fix (GHSA-w6f5-2h26-x83f).

Two batch-import views had NO authorization and were readable by anyone:
- ``/import/batch/<id>`` (BatchImportView) exposed a batch's import rows and the
  submitter's identity;
- ``/import/batch/pending`` (BatchImportPendingView) listed every pending batch
  and its submitter.

The fix:
- a single batch is viewable by its submitter or an admin; everyone else gets an
  identical 403 whether or not the batch exists (no existence oracle);
- the pending list is admin-only.

Written to FAIL against the unfixed source, which renders for anyone (and
IndexErrors on a missing batch).
"""

import types
from unittest.mock import MagicMock, patch

import pytest

from openlibrary.plugins.openlibrary import code
from openlibrary.plugins.openlibrary.code import (
    BatchImportPendingView,
    BatchImportView,
    Forbidden,
)

ADMIN_KEY = "/people/admin"
OWNER_KEY = "/people/owner"
OWNER_USERNAME = "owner"
OTHER_KEY = "/people/other"
BATCH_ID = "5"


class _NotFound(Exception):
    """Stand-in for web.notfound() so the test can assert a 404 (not a 403)."""


class _User:
    def __init__(self, key, username):
        self.key = key
        self._username = username

    def get_username(self):
        return self._username


def _batch(submitter=OWNER_USERNAME):
    return types.SimpleNamespace(id=BATCH_ID, submitter=submitter, name="b", submit_time=None)


def _make_db(batch=None):
    db_mock = MagicMock()
    db_mock.select.side_effect = lambda table, **kw: ([batch] if batch is not None else []) if table == "import_batch" else []
    db_mock.query.return_value = [MagicMock(count=0)]
    return db_mock


def _patches(db_mock, user):
    ctx = MagicMock()
    ctx.user = user
    return [
        patch.object(code, "db", db_mock),
        patch.object(code, "_get_members_of_group", lambda group: [ADMIN_KEY]),
        patch.object(code.delegate, "context", ctx),
        patch.object(code, "render_template", MagicMock(return_value="RENDERED")),
        patch.object(
            code.web,
            "input",
            lambda **kw: types.SimpleNamespace(page="1", limit="10", sort="added_time asc"),
        ),
        patch.object(code.web, "notfound", _NotFound),
    ]


def _enter(ps):
    for p in ps:
        p.start()


def _exit(ps):
    for p in reversed(ps):
        p.stop()


# --- single batch view: /import/batch/<id> ---------------------------------


def test_single_batch_anonymous_is_forbidden():
    db_mock = _make_db(batch=_batch())
    ps = _patches(db_mock, user=None)
    _enter(ps)
    try:
        with pytest.raises(Forbidden):
            BatchImportView().GET(BATCH_ID)
        code.render_template.assert_not_called()
    finally:
        _exit(ps)


def test_single_batch_non_owner_non_admin_is_forbidden():
    db_mock = _make_db(batch=_batch(submitter=OWNER_USERNAME))
    ps = _patches(db_mock, user=_User(OTHER_KEY, "other"))
    _enter(ps)
    try:
        with pytest.raises(Forbidden):
            BatchImportView().GET(BATCH_ID)
        code.render_template.assert_not_called()
    finally:
        _exit(ps)


def test_single_batch_missing_is_same_forbidden_for_non_admin():
    # No batch row -> a non-admin gets the SAME 403 as the not-owner case, so
    # batch existence cannot be probed via this endpoint.
    db_mock = _make_db(batch=None)
    ps = _patches(db_mock, user=_User(OTHER_KEY, "other"))
    _enter(ps)
    try:
        with pytest.raises(Forbidden):
            BatchImportView().GET(BATCH_ID)
    finally:
        _exit(ps)


def test_single_batch_owner_can_view():
    db_mock = _make_db(batch=_batch(submitter=OWNER_USERNAME))
    ps = _patches(db_mock, user=_User(OWNER_KEY, OWNER_USERNAME))
    _enter(ps)
    try:
        assert BatchImportView().GET(BATCH_ID) == "RENDERED"
    finally:
        _exit(ps)


def test_single_batch_admin_can_view():
    db_mock = _make_db(batch=_batch(submitter=OWNER_USERNAME))
    ps = _patches(db_mock, user=_User(ADMIN_KEY, "admin"))
    _enter(ps)
    try:
        assert BatchImportView().GET(BATCH_ID) == "RENDERED"
    finally:
        _exit(ps)


def test_single_batch_admin_missing_is_notfound_not_forbidden():
    # An admin IS allowed to learn a batch does not exist -> 404, not 403.
    db_mock = _make_db(batch=None)
    ps = _patches(db_mock, user=_User(ADMIN_KEY, "admin"))
    _enter(ps)
    try:
        with pytest.raises(_NotFound):
            BatchImportView().GET(BATCH_ID)
    finally:
        _exit(ps)


# --- pending list: /import/batch/pending -----------------------------------


def test_pending_anonymous_is_forbidden():
    db_mock = _make_db()
    ps = _patches(db_mock, user=None)
    _enter(ps)
    try:
        with pytest.raises(Forbidden):
            BatchImportPendingView().GET()
        code.render_template.assert_not_called()
    finally:
        _exit(ps)


def test_pending_non_admin_is_forbidden():
    db_mock = _make_db()
    ps = _patches(db_mock, user=_User(OWNER_KEY, OWNER_USERNAME))
    _enter(ps)
    try:
        with pytest.raises(Forbidden):
            BatchImportPendingView().GET()
        code.render_template.assert_not_called()
    finally:
        _exit(ps)


def test_pending_admin_can_view():
    db_mock = _make_db()
    ps = _patches(db_mock, user=_User(ADMIN_KEY, "admin"))
    _enter(ps)
    try:
        assert BatchImportPendingView().GET() == "RENDERED"
    finally:
        _exit(ps)
