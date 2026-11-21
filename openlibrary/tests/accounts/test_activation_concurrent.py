import json
from unittest import mock

import pytest

from infogami.infobase.client import ClientException
from openlibrary.accounts import OpenLibraryAccount, model

CONFLICT = ClientException("409 Conflict", "conflict", json.dumps({"error": "conflict"}))
INTERNAL = ClientException("500 Internal Server Error", "internal error", json.dumps({"error": "internal_error"}))
NOT_FOUND = ClientException("400 Bad Request", "Account activation failed.", json.dumps({"error": "bad_data"}))


@pytest.fixture
def api(monkeypatch):
    api = mock.Mock()
    site = mock.Mock()
    site.get.return_value = api
    monkeypatch.setattr(model, "site", site)
    monkeypatch.setattr(model.time, "sleep", mock.Mock())
    return api


def activate():
    OpenLibraryAccount(_key="account/racer", username="racer").activate()


@pytest.mark.parametrize("error", [CONFLICT, INTERNAL])
def test_a_concurrent_activation_failure_is_retried(api, error):
    api.activate_account.side_effect = [error, None]
    activate()
    assert api.activate_account.call_count == 2


def test_gives_up_after_four_attempts(api):
    api.activate_account.side_effect = CONFLICT
    with pytest.raises(ClientException):
        activate()
    assert api.activate_account.call_count == 4


def test_other_errors_are_not_retried(api):
    api.activate_account.side_effect = NOT_FOUND
    with pytest.raises(ClientException):
        activate()
    api.activate_account.assert_called_once_with(username="racer")
