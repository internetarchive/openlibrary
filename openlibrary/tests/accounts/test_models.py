from unittest import mock

import pytest
import web
from requests.models import Response

from openlibrary.accounts import InternetArchiveAccount, OpenLibraryAccount, RunAs, model
from openlibrary.mocks.mock_infobase import MockConnection, MockSite
from openlibrary.plugins.upstream import models
from openlibrary.utils.request_context import site as site_context


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


class TestRunAs:
    """Tests for the RunAs context manager - simplified to match script behavior."""

    def setup_method(self):
        """Set up mock site and context for each test."""

        self.mock_site = MockSite()
        models.setup()

        # Create test user in the mock store
        self.mock_site.store.put(
            "account/testuser",
            {
                "username": "testuser",
                "lusername": "testuser",
                "email": "testuser@example.com",
                "displayname": "Test User",
                "type": "account",
            },
        )

        # Set up web.ctx with proper initialization
        old_ctx = dict(web.ctx)
        web.ctx.clear()
        web.ctx.site = self.mock_site
        site_context.set(self.mock_site)
        web.ctx.conn = MockConnection()
        web.ctx.infobase_auth_token = None
        self.mock_site._conn = MockConnection()

        self.old_ctx = old_ctx

    def teardown_method(self):
        """Restore original context after each test."""
        web.ctx.clear()
        web.ctx.update(self.old_ctx)

    def test_runas_with_web_ctx_site(self):
        """Test RunAs works with web.ctx.site.get() - matches script Case 1."""
        with RunAs("testuser") as user:
            assert user.username == "testuser"
            # Verify we can access the site via web.ctx.site
            account_doc = web.ctx.site.store.get("account/testuser")
            assert account_doc is not None

    def test_runas_with_site_context(self):
        """Test RunAs works with site.get() - matches script Case 2."""
        with RunAs("testuser") as user:
            assert user.username == "testuser"
            # Verify we can access the site via context vars
            account_doc = site_context.get().store.get("account/testuser")
            assert account_doc is not None

    def test_runas_with_invalid_username_raises_keyerror(self):
        """Test RunAs raises KeyError for non-existent username."""
        with pytest.raises(KeyError) as exc_info:
            RunAs("nonexistent_user")
        assert "Invalid username" in str(exc_info.value)

    def test_runas_restores_auth_token(self):
        """Test RunAs sets new auth token and restores original after exit."""
        # Set initial auth token on both connections (simulating a logged-in user)
        web.ctx.conn.set_auth_token("/people/admin")
        site_context.get()._conn.set_auth_token("/people/admin")
        assert web.ctx.conn.get_auth_token() == "/people/admin"
        assert site_context.get()._conn.get_auth_token() == "/people/admin"

        # Enter RunAs - should change to testuser's token
        with RunAs("testuser"):
            # Inside RunAs, token should be set to target user on BOTH connections
            # Check site.get()._conn (the one that gets set in __enter__)
            assert "/people/testuser" in site_context.get()._conn.get_auth_token()
            # Also check web.ctx.conn - should also be set inside RunAs context
            # This will fail if web.ctx.conn.set_auth_token is commented out in __enter__
            assert "/people/testuser" in web.ctx.conn.get_auth_token()

        # After exiting, should restore to original token on BOTH connections
        assert web.ctx.conn.get_auth_token() == "/people/admin"
        assert site_context.get()._conn.get_auth_token() == "/people/admin"

    def test_runas_restores_auth_token_on_exception(self):
        """Test RunAs restores original auth token even if exception occurs."""
        # Set initial auth token on both connections
        web.ctx.conn.set_auth_token("/people/admin")
        site_context.get()._conn.set_auth_token("/people/admin")
        original_token = web.ctx.conn.get_auth_token()
        original_site_token = site_context.get()._conn.get_auth_token()

        try:
            with RunAs("testuser"):
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Token should still be restored even after exception on BOTH connections
        assert web.ctx.conn.get_auth_token() == original_token
        assert site_context.get()._conn.get_auth_token() == original_site_token
