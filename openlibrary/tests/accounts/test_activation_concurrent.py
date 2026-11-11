import threading
import json
from unittest import mock

import pytest

from infogami.infobase.client import ClientException
from openlibrary.accounts import OpenLibraryAccount, model

# Helper to build a ClientException with a JSON payload containing a "code"
def make_client_exception(status: str, message: str, code: str | None = None) -> ClientException:
    payload = {"code": code} if code is not None else {}
    json_data = json.dumps(payload) if payload else None
    return ClientException(status, message, json_data)

# Fixture for a simple mock site that mimics the subset of Infobase API used by
# OpenLibraryAccount.activate():
@pytest.fixture
def mock_site():
    site = mock.Mock()
    # ``site.get()`` returns a mock representing the Infobase API.
    api = mock.Mock()
    site.get.return_value = api
    return site

# Utility to configure the mock API's ``get`` method for profile and account lookups.
def configure_profile_and_account_lookup(
    api, username: str, *, profile_exists: bool = True, account_active: bool = True
):
    """Set ``api.get`` side‑effects.

    * ``/people/<username>`` returns a minimal profile document when
      ``profile_exists`` is True, otherwise ``None``.
    * ``/account/<username>`` returns an account document with a ``status`` field
      equal to ``"active"`` when ``account_active`` is True, otherwise ``"pending"``.
    """
    def get_side_effect(key):
        if key == f"/people/{username}":
            return {"key": f"/people/{username}"} if profile_exists else None
        if key == f"/account/{username}":
            return {
                "key": f"/account/{username}",
                "status": "active" if account_active else "pending",
            }
        raise KeyError(key)
    api.get.side_effect = get_side_effect

# ---------------------------------------------------------------------------
# 1. Concurrent activation – two threads race on the same account.
# ---------------------------------------------------------------------------
def test_concurrent_activation(mock_site, monkeypatch):
    username = "raceuser"
    api = mock_site.get.return_value

    # Set up a barrier that the mock RPC will wait on, ensuring both threads
    # reach the activation call before either receives a result.
    barrier = threading.Barrier(2)
    call_counter = {'count': 0}

    def activate_side_effect(*args, **kwargs):
        # Wait until both threads have invoked the RPC.
        try:
            barrier.wait(timeout=5)
        except threading.BrokenBarrierError:
            raise RuntimeError("Barrier broken in activate_side_effect")
        # First invocation raises the race exception, second succeeds.
        if call_counter['count'] == 0:
            call_counter['count'] += 1
            raise make_client_exception(
                "400 Bad Request", "duplicate", code="unique_violation"
            )
        else:
            call_counter['count'] += 1
            return "ok"

    api.activate_account.side_effect = activate_side_effect
    configure_profile_and_account_lookup(
        api, username, profile_exists=True, account_active=True
    )
    monkeypatch.setattr(model, "site", mock_site)

    excs = []

    def worker():
        try:
            OpenLibraryAccount(_key=f"/people/{username}", username=username).activate()
        except Exception as e:
            excs.append(e)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # Ensure both threads completed without propagating an exception.
    assert excs == []
    assert api.activate_account.call_count == 2

# ---------------------------------------------------------------------------
# 2. Already‑active account – the RPC raises a known race error but the
#    account is already active.
# ---------------------------------------------------------------------------
def test_activation_already_active(mock_site, monkeypatch):
    username = "already_active"
    api = mock_site.get.return_value
    api.activate_account.side_effect = make_client_exception(
        "400 Bad Request", "already active", code="unique_violation"
    )
    configure_profile_and_account_lookup(
        api, username, profile_exists=True, account_active=True
    )
    monkeypatch.setattr(model, "site", mock_site)

    # Should return without raising.
    OpenLibraryAccount(_key=f"/people/{username}", username=username).activate()
    api.activate_account.assert_called_once_with(username=username)

# ---------------------------------------------------------------------------
# 3. Unrelated error – a different error code must propagate unchanged.
# ---------------------------------------------------------------------------
def test_unrelated_error_propagates(mock_site, monkeypatch):
    username = "bad_user"
    api = mock_site.get.return_value
    api.activate_account.side_effect = make_client_exception(
        "500 Internal Server Error", "boom", code="server_error"
    )
    configure_profile_and_account_lookup(
        api, username, profile_exists=True, account_active=True
    )
    monkeypatch.setattr(model, "site", mock_site)

    with pytest.raises(ClientException) as exc_info:
        OpenLibraryAccount(_key=f"/people/{username}", username=username).activate()
    assert exc_info.value.get_data()["code"] == "server_error"

# ---------------------------------------------------------------------------
# 4. Profile/account lookup failure – the wrapper must not swallow the lookup
#    exception.
# ---------------------------------------------------------------------------
def test_lookup_failure_propagates(mock_site, monkeypatch):
    username = "lookup_fail"
    api = mock_site.get.return_value
    api.activate_account.side_effect = make_client_exception(
        "400 Bad Request", "duplicate", code="unique_violation"
    )
    # Simulate a failure when trying to fetch the profile.
    def broken_get(key):
        raise RuntimeError("lookup broken")
    api.get.side_effect = broken_get
    monkeypatch.setattr(model, "site", mock_site)

    with pytest.raises(RuntimeError, match="lookup broken"):
        OpenLibraryAccount(_key=f"/people/{username}", username=username).activate()

# ---------------------------------------------------------------------------
# 5. Pending account – profile exists but account status is not "active".
#    The original activation exception should be re‑raised.
# ---------------------------------------------------------------------------
def test_pending_account_propagates_original_error(mock_site, monkeypatch):
    username = "pending_user"
    api = mock_site.get.return_value
    api.activate_account.side_effect = make_client_exception(
        "400 Bad Request", "duplicate", code="unique_violation"
    )
    # Profile exists, but the account document reports status "pending".
    configure_profile_and_account_lookup(
        api, username, profile_exists=True, account_active=False
    )
    monkeypatch.setattr(model, "site", mock_site)

    with pytest.raises(ClientException) as exc_info:
        OpenLibraryAccount(_key=f"/people/{username}", username=username).activate()
    # Verify the original error code is retained.
    assert exc_info.value.get_data()["code"] == "unique_violation"
