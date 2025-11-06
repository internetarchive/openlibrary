"""Tests for the /follows.json API endpoint."""
import pytest
import web

from openlibrary import accounts
from openlibrary.plugins.openlibrary.api import patrons_follows_json


class TestPatronFollowsAPI:
    """Test the /follows.json API endpoint for following/unfollowing patrons."""

    def test_post_follows_nonexistent_publisher_returns_404(self, mock_site, monkeypatch):
        """Test that following a non-existent publisher returns 404.
        
        This test validates that the fix prevents following non-existent publishers.
        """
        # Setup mock user and input
        mock_user = web.storage()
        mock_user.key = '/people/test_user'
        
        mock_input = web.storage(
            publisher='nonexistent_user',
            redir_url='/',
            state='0'  # subscribe
        )
        
        monkeypatch.setattr(web, 'input', lambda: mock_input)
        monkeypatch.setattr(accounts, 'get_current_user', lambda: mock_user)
        
        # Mock accounts.find to return None for nonexistent user
        monkeypatch.setattr(accounts, 'find', lambda **kwargs: None)
        
        # Create the API handler instance
        handler = patrons_follows_json()
        
        # This should now return a 404 after the fix
        with pytest.raises(Exception) as exc_info:
            handler.POST('/people/test_user')
        
        # Check that it's a 404 error (web.notfound)
        assert 'notfound' in str(exc_info.type).lower() or '404' in str(exc_info.value)