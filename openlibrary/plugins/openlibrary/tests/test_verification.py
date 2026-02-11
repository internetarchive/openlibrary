"""Tests for human verification challenge functionality."""

import web

from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.plugins.openlibrary import code


class TestHumanVerification:
    """Tests for human verification functions."""

    def setup_method(self):
        """Setup test fixtures."""
        self.setup_web_context()

    def setup_web_context(self):
        """Setup web.py context for testing."""
        # Create a minimal web.py context
        ctx = web.storage()
        ctx.env = {}
        ctx.site = MockSite()
        web.ctx = ctx
        web.webapi.ctx = web.ctx

    def test_is_suspicious_visitor_when_logged_in(self, monkeypatch):
        """Test that logged in users are not suspicious."""
        # Mock a logged in user
        mock_user = web.storage(key='/people/test_user')
        web.ctx.site.get_user = lambda: mock_user

        # Mock is_recognized_bot to return False
        monkeypatch.setattr(code, 'is_recognized_bot', lambda: False)

        # Mock no referer
        web.ctx.env = {}

        # Mock no verification cookie
        def mock_cookies():
            return {}

        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is False

    def test_is_suspicious_visitor_when_bot(self, monkeypatch):
        """Test that known bots are not suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None

        # Mock is_recognized_bot to return True
        monkeypatch.setattr(code, 'is_recognized_bot', lambda: True)

        # Mock no verification cookie
        def mock_cookies():
            return {}

        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is False

    def test_is_suspicious_visitor_with_valid_cookie(self, monkeypatch):
        """Test that visitors with valid signed cookie are not suspicious."""
        from openlibrary.accounts import model

        # Mock no logged in user
        web.ctx.site.get_user = lambda: None

        # Mock is_recognized_bot to return False
        monkeypatch.setattr(code, 'is_recognized_bot', lambda: False)

        # Mock no referer
        web.ctx.env = {}

        # Create a valid signed cookie
        valid_cookie = model.create_verification_cookie_value()

        # Mock verification cookie present
        def mock_cookies():
            return {'vf': valid_cookie}

        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is False

    def test_is_suspicious_visitor_with_referer(self, monkeypatch):
        """Test that visitors with referer are not suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None

        # Mock is_recognized_bot to return False
        monkeypatch.setattr(code, 'is_recognized_bot', lambda: False)

        # Mock referer present
        web.ctx.env = {'HTTP_REFERER': 'https://example.com'}

        # Mock no verification cookie
        def mock_cookies():
            return {}

        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is False

    def test_is_suspicious_visitor_when_all_checks_fail(self, monkeypatch):
        """Test that non-logged-in non-bots without cookie are suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None

        # Mock is_recognized_bot to return False
        monkeypatch.setattr(code, 'is_recognized_bot', lambda: False)

        # Mock no referer
        web.ctx.env = {}

        # Mock no verification cookie
        def mock_cookies():
            return {}

        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is True

    def test_is_suspicious_visitor_with_invalid_cookie(self, monkeypatch):
        """Test that visitors with invalid cookie value are still suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None

        # Mock is_recognized_bot to return False
        monkeypatch.setattr(code, 'is_recognized_bot', lambda: False)

        # Mock no referer
        web.ctx.env = {}

        # Mock verification cookie with invalid value
        def mock_cookies():
            return {'vf': 'invalid_value'}

        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is True
