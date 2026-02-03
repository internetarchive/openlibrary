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
        
    def test_has_verification_cookie_when_present(self, monkeypatch):
        """Test that has_verification_cookie returns True when vf cookie is set to 1."""
        def mock_cookies():
            return {'vf': '1'}
        
        monkeypatch.setattr(web, 'cookies', mock_cookies)
        assert code.has_verification_cookie() is True
    
    def test_has_verification_cookie_when_absent(self, monkeypatch):
        """Test that has_verification_cookie returns False when vf cookie is absent."""
        def mock_cookies():
            return {}
        
        monkeypatch.setattr(web, 'cookies', mock_cookies)
        assert code.has_verification_cookie() is False
    
    def test_has_verification_cookie_when_wrong_value(self, monkeypatch):
        """Test that has_verification_cookie returns False when vf cookie has wrong value."""
        def mock_cookies():
            return {'vf': '0'}
        
        monkeypatch.setattr(web, 'cookies', mock_cookies)
        assert code.has_verification_cookie() is False
    
    def test_is_suspicious_visitor_when_logged_in(self, monkeypatch):
        """Test that logged in users are not suspicious."""
        # Mock a logged in user
        mock_user = web.storage(key='/people/test_user')
        web.ctx.site.get_user = lambda: mock_user
        
        # Mock is_bot to return False
        monkeypatch.setattr(code, 'is_bot', lambda: False)
        
        assert code.is_suspicious_visitor() is False
    
    def test_is_suspicious_visitor_when_bot(self, monkeypatch):
        """Test that known bots are not suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None
        
        # Mock is_bot to return True
        monkeypatch.setattr(code, 'is_bot', lambda: True)
        
        assert code.is_suspicious_visitor() is False
    
    def test_is_suspicious_visitor_when_not_logged_in_and_not_bot(self, monkeypatch):
        """Test that non-logged-in non-bots are suspicious."""
        # Mock no logged in user
        web.ctx.site.get_user = lambda: None
        
        # Mock is_bot to return False
        monkeypatch.setattr(code, 'is_bot', lambda: False)
        
        assert code.is_suspicious_visitor() is True
    
    def test_needs_human_verification_with_cookie(self, monkeypatch):
        """Test that verification is not needed when cookie is present."""
        # Mock suspicious visitor
        monkeypatch.setattr(code, 'is_suspicious_visitor', lambda: True)
        
        # Mock verification cookie present
        def mock_cookies():
            return {'vf': '1'}
        monkeypatch.setattr(web, 'cookies', mock_cookies)
        
        assert code.needs_human_verification() is False
    
    def test_needs_human_verification_without_cookie(self, monkeypatch):
        """Test that verification is needed for suspicious visitors without cookie."""
        # Mock suspicious visitor
        monkeypatch.setattr(code, 'is_suspicious_visitor', lambda: True)
        
        # Mock no verification cookie
        def mock_cookies():
            return {}
        monkeypatch.setattr(web, 'cookies', mock_cookies)
        
        assert code.needs_human_verification() is True
    
    def test_needs_human_verification_when_not_suspicious(self, monkeypatch):
        """Test that verification is not needed for non-suspicious visitors."""
        # Mock non-suspicious visitor
        monkeypatch.setattr(code, 'is_suspicious_visitor', lambda: False)
        
        # Mock no verification cookie
        def mock_cookies():
            return {}
        monkeypatch.setattr(web, 'cookies', mock_cookies)
        
        assert code.needs_human_verification() is False
