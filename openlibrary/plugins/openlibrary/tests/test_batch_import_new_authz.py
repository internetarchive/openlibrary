"""Authorization guards for ``POST /import/batch/new`` (GHSA-wq89-ph2h-pp44).

``/import/batch/new`` is the second CSRF sink flagged alongside the approve
endpoint: an admin's forged cross-site POST would create a batch with status
``pending`` (queued for import, skipping ``needs_review``) rather than the
``needs_review`` a normal user gets.

The actual CSRF control for this sink is the *same* one that protects
``/import/batch/approve``: the auth cookie (``config.login_cookie_name`` ->
``session``) is ``SameSite=Lax``, so a forged cross-site POST never carries the
admin's session -- ``user_key`` is then ``None`` and the handler raises
``Forbidden`` before any batch is created. That cookie attribute is guarded by
``test_session_cookie_is_samesite_lax`` in
``test_batch_import_approve_post_only.py``.

These tests lock the handler-level authorization invariants that make the cookie
control meaningful:

- no authenticated user -> ``Forbidden``, nothing created;
- a non-admin user -> batch created as ``needs_review`` (never ``pending``);
- only an admin user -> batch created as ``pending``.
"""

from unittest.mock import MagicMock, patch

import pytest

from openlibrary.plugins.openlibrary import code
from openlibrary.plugins.openlibrary.code import Forbidden, batch_imports

ADMIN_KEY = "/people/admin"


class _User:
    def __init__(self, key):
        self.key = key


def _patched(user_key, batch_import_spy):
    """Patch the handler's collaborators so POST runs without a web context.

    ``_get_members_of_group`` reports a single admin, so ``ADMIN_KEY`` is the
    only user that reaches the ``pending`` branch.
    """
    user = _User(user_key) if user_key else None
    return [
        patch.object(code, "_get_members_of_group", lambda group: [ADMIN_KEY]),
        patch.object(code.delegate, "context", MagicMock(user=user)),
        patch.object(code, "web", MagicMock(input=lambda **kw: MagicMock(get=lambda k: "{}" if k == "batchImportText" else None))),
        patch.object(code, "batch_import", batch_import_spy),
        patch.object(code, "render_template", lambda *a, **k: ("render", a, k)),
        patch.object(code, "add_flash_message", lambda *a, **k: None),
    ]


def _run_post(patches):
    for p in patches:
        p.start()
    try:
        return batch_imports().POST()
    finally:
        for p in reversed(patches):
            p.stop()


def test_post_requires_login():
    """No authenticated user -> Forbidden, and no batch is created."""
    spy = MagicMock()
    patches = _patched(user_key=None, batch_import_spy=spy)
    with pytest.raises(Forbidden):
        _run_post(patches)
    spy.assert_not_called()


def test_non_admin_batch_is_needs_review():
    """A logged-in non-admin creates a batch that still needs review."""
    spy = MagicMock()
    patches = _patched(user_key="/people/regular", batch_import_spy=spy)
    _run_post(patches)
    assert spy.call_count == 1
    assert spy.call_args.kwargs["import_status"] == "needs_review"


def test_admin_batch_is_pending():
    """Only an admin may create a batch that goes straight to pending."""
    spy = MagicMock()
    patches = _patched(user_key=ADMIN_KEY, batch_import_spy=spy)
    _run_post(patches)
    assert spy.call_count == 1
    assert spy.call_args.kwargs["import_status"] == "pending"
