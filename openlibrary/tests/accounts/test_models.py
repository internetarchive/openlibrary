import threading
from unittest import mock
from unittest.mock import AsyncMock

import pytest
from requests.models import Response

from openlibrary.accounts import InternetArchiveAccount, OpenLibraryAccount, model


def get_username(account):
    return account and account.value


def test_verify_hash():
    secret_key = b"aqXwLJVOcV"
    hash = model.generate_hash(secret_key, b"foo")
    assert model.verify_hash(secret_key, b"foo", hash)


@mock.patch("openlibrary.accounts.model.get_secret_key", return_value="test-secret-key")
def test_parse_s3_cookie_decrypts_a_valid_token(mock_secret_key):
    token = model.encrypt_s3_keys("AKIA123", "secret456")

    assert model.parse_s3_cookie(token) == {"access": "AKIA123", "secret": "secret456"}


def test_parse_s3_cookie_returns_none_when_absent():
    assert model.parse_s3_cookie(None) is None
    assert model.parse_s3_cookie("") is None


@mock.patch("openlibrary.accounts.model.get_secret_key", return_value="test-secret-key")
def test_parse_s3_cookie_returns_none_for_tampered_token(mock_secret_key):
    assert model.parse_s3_cookie("not-a-real-token") is None


def test_xauth_http_error_without_json(monkeypatch):
    xauth = InternetArchiveAccount.xauth
    resp = Response()
    resp.status_code = 500
    resp._content = b"Internal Server Error"
    monkeypatch.setattr(model.requests, "post", lambda url, **kwargs: resp)
    assert xauth("create", s3_key="_", s3_secret="_") == {
        "code": 500,
        "error": "Internal Server Error",
    }


def test_xauth_http_error_with_json(monkeypatch):
    xauth = InternetArchiveAccount.xauth
    resp = Response()
    resp.status_code = 400
    resp._content = b'{"error": "Unknown Parameter Blah"}'
    monkeypatch.setattr(model.requests, "post", lambda url, **kwargs: resp)
    assert xauth("create", s3_key="_", s3_secret="_") == {"error": "Unknown Parameter Blah"}


@pytest.mark.asyncio
async def test_anonymize_test_mode_awaits_all_sql_models(monkeypatch):
    account = OpenLibraryAccount(_key="/people/testuser")
    methods = {
        "booknotes": (model.Booknotes, "delete_all_by_username", 2),
        "ratings": (model.Ratings, "update_username", 3),
        "observations": (model.Observations, "update_username", 4),
        "bookshelves": (model.Bookshelves, "update_username", 5),
        "edits": (model.CommunityEditsQueue, "update_submitter_name", 6),
        "bestbooks": (model.Bestbook, "update_username", 7),
    }
    mocks = {}
    for key, (klass, name, count) in methods.items():
        async_mock = AsyncMock(return_value=count)
        monkeypatch.setattr(klass, name, async_mock)
        mocks[key] = async_mock

    with mock.patch.object(OpenLibraryAccount, "get_activation_link", return_value=model.Link(code="abc123")):
        result = await account.anonymize(test=True)

    assert result == {
        "new_username": "anonymous-abc123",
        "booknotes_count": 2,
        "ratings_count": 3,
        "observations_count": 4,
        "bookshelves_count": 5,
        "merge_request_count": 6,
        "bestbooks_count": 7,
    }
    mocks["booknotes"].assert_awaited_once_with("testuser", _test=True)
    for key in ("ratings", "observations", "bookshelves", "edits", "bestbooks"):
        mocks[key].assert_awaited_once_with("testuser", "anonymous-abc123", _test=True)


def test_anonymize_sync_deletes_infobase_data_on_calling_thread(monkeypatch):
    # Infobase saves read the request's thread-local web.ctx.ip, which the async bridge thread lacks.
    account = OpenLibraryAccount(_key="/people/testuser")
    threads = []
    monkeypatch.setattr(OpenLibraryAccount, "_delete_infobase_data", lambda self: threads.append(threading.current_thread()))
    monkeypatch.setattr(OpenLibraryAccount, "_anonymize_tables", AsyncMock(return_value={"new_username": "anonymous-abc123"}))

    assert account.anonymize_sync() == {"new_username": "anonymous-abc123"}
    assert threads == [threading.current_thread()]


@mock.patch("openlibrary.accounts.model.site")
@mock.patch("openlibrary.accounts.model.web")
def test_get(mock_web, mock_site):
    mock_site.get.return_value = mock_web.ctx.site
    test = True
    email = "test@example.com"
    account = OpenLibraryAccount.get_by_email(email)
    assert account is None

    test_account = OpenLibraryAccount.create(
        username="test",
        email=email,
        password="password",
        displayname="Test User",
        verified=True,
        retries=0,
        test=True,
    )

    mock_site = mock_web.ctx.site
    mock_site.store.get.return_value = {
        "username": "test",
        "itemname": "@test",
        "email": "test@example.com",
        "displayname": "Test User",
        "test": test,
    }

    key = "test/test"
    test_username = test_account.username

    retrieved_account = OpenLibraryAccount.get_by_email(email)
    assert retrieved_account == test_account

    mock_site = mock_web.ctx.site
    mock_site.store.values.return_value = [
        {
            "username": "test",
            "itemname": "@test",
            "email": "test@example.com",
            "displayname": "Test User",
            "test": test,
            "type": "account",
            "name": "internetarchive_itemname",
            "value": test_username,
        }
    ]

    retrieved_account = OpenLibraryAccount.get_by_link(test_username)
    assert retrieved_account
    retrieved_username = get_username(retrieved_account)
    assert retrieved_username == test_username

    mock_site.store.values.return_value[0]["name"] = "username"

    retrieved_account = OpenLibraryAccount.get_by_username(test_username)
    assert retrieved_account
    retrieved_username = get_username(retrieved_account)
    assert retrieved_username == test_username

    key = f"test/{retrieved_username}"
    retrieved_account = OpenLibraryAccount.get_by_key(key)
    assert retrieved_account


# --- InternetArchiveAccount.verify() ---


@mock.patch.object(InternetArchiveAccount, "xauth")
def test_verify_success(mock_xauth):
    # activate response includes token; issue_key is called with it
    mock_xauth.side_effect = [
        {
            "success": True,
            "values": {
                "email": "test@example.com",
                "itemname": "@test",
                "screenname": "test",
                "token": "tok_abc123",
            },
        },
        {"s3": {"access": "AKIAIOSFODNN7EXAMPLE", "secret": "wJalrXUtnFEMI"}, "ttl": 3600},
    ]
    result = InternetArchiveAccount.verify(token="sometoken")
    assert "error" not in result
    assert result["email"] == "test@example.com"
    assert result["s3"]["access"] == "AKIAIOSFODNN7EXAMPLE"
    assert result["s3"]["secret"] == "wJalrXUtnFEMI"
    # Confirm token from activate was forwarded to issue_key as issuer_token
    issue_key_call = mock_xauth.call_args_list[1]
    assert issue_key_call.kwargs.get("issuer_token") == "tok_abc123"


@mock.patch.object(InternetArchiveAccount, "xauth")
def test_verify_issue_key_failure_returns_error(mock_xauth):
    """If issue_key fails after activation, verify() returns an error dict."""
    mock_xauth.side_effect = [
        {
            "success": True,
            "values": {"email": "test@example.com", "itemname": "@test", "screenname": "test"},
        },
        {"success": False, "error": "issue_key_failed"},
    ]
    result = InternetArchiveAccount.verify(token="sometoken")
    assert result.get("error") == "s3_key_issue_failed"


@mock.patch.object(InternetArchiveAccount, "xauth")
def test_verify_invalid_token(mock_xauth):
    mock_xauth.return_value = {"success": False, "values": {"reason": "invalid_token"}}
    result = InternetArchiveAccount.verify(token="badtoken")
    assert result.get("error") == "invalid_token"


@mock.patch.object(InternetArchiveAccount, "xauth")
def test_verify_already_activated(mock_xauth):
    mock_xauth.return_value = {
        "success": False,
        "values": {"reason": "account_already_activated"},
    }
    result = InternetArchiveAccount.verify(token="usedtoken")
    assert result.get("error") == "account_already_activated"


@mock.patch.object(InternetArchiveAccount, "xauth")
def test_verify_xauth_failure_returns_generic_error(mock_xauth):
    mock_xauth.return_value = {"success": False, "error": "server_error"}
    result = InternetArchiveAccount.verify(token="anytoken")
    assert result.get("error") == "server_error"


@mock.patch.object(InternetArchiveAccount, "xauth")
def test_verify_xauth_sends_activate_op(mock_xauth):
    """Confirm the xauthn activate op and token are forwarded correctly."""
    mock_xauth.return_value = {"success": False, "values": {"reason": "invalid_token"}}
    InternetArchiveAccount.verify(token="mytoken")
    assert mock_xauth.called
    call_kwargs = mock_xauth.call_args.kwargs
    assert call_kwargs["op"] == "activate"
    assert call_kwargs["token"] == "mytoken"
