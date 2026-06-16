from unittest import mock

from requests.models import Response

from openlibrary.accounts import InternetArchiveAccount, OpenLibraryAccount, model


def get_username(account):
    return account and account.value


def test_verify_hash():
    secret_key = b"aqXwLJVOcV"
    hash = model.generate_hash(secret_key, b"foo")
    assert model.verify_hash(secret_key, b"foo", hash)


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


@mock.patch("openlibrary.accounts.model.web")
def test_get(mock_web):
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
    mock_xauth.return_value = {
        "success": True,
        "values": {
            "email": "test@example.com",
            "itemname": "@test",
            "screenname": "test",
            "s3": {"access": "AKIAIOSFODNN7EXAMPLE", "secret": "wJalrXUtnFEMI"},
        },
    }
    result = InternetArchiveAccount.verify(token="sometoken")
    assert "error" not in result
    assert result["email"] == "test@example.com"
    assert result["s3"]["access"] == "AKIAIOSFODNN7EXAMPLE"
    assert result["s3"]["secret"] == "wJalrXUtnFEMI"


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
