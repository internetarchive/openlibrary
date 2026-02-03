"""Tests for human verification challenge functionality."""

import pytest
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

        # Mock is_bot to return False
        monkeypatch.setattr(code, 'is_bot', lambda: False)

        # Mock no verification cookie
        def mock_cookies():
            return {}
        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is False

    def test_is_suspicious_visitor_when_bot(self, monkeypatch):
        """Test that known bots are not suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None

        # Mock is_bot to return True
        monkeypatch.setattr(code, 'is_bot', lambda: True)

        # Mock no verification cookie
        def mock_cookies():
            return {}
        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is False

    def test_is_suspicious_visitor_with_cookie(self, monkeypatch):
        """Test that visitors with vf=1 cookie are not suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None

        # Mock is_bot to return False
        monkeypatch.setattr(code, 'is_bot', lambda: False)

        # Mock verification cookie present
        def mock_cookies():
            return {'vf': '1'}
        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is False

    def test_is_suspicious_visitor_when_all_checks_fail(self, monkeypatch):
        """Test that non-logged-in non-bots without cookie are suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None

        # Mock is_bot to return False
        monkeypatch.setattr(code, 'is_bot', lambda: False)

        # Mock no verification cookie
        def mock_cookies():
            return {}
        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is True

    def test_is_suspicious_visitor_with_wrong_cookie_value(self, monkeypatch):
        """Test that visitors with wrong cookie value are still suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None

        # Mock is_bot to return False
        monkeypatch.setattr(code, 'is_bot', lambda: False)

        # Mock verification cookie with wrong value
        def mock_cookies():
            return {'vf': '0'}
        monkeypatch.setattr(web, 'cookies', mock_cookies)

        assert code.is_suspicious_visitor() is True
