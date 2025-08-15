"""Bookshare OAuth integration for print disability qualification."""

import logging
import urllib.parse
from typing import Optional

import requests
import web

from infogami import config

logger = logging.getLogger("openlibrary.core.auth")


class BookshareOAuth:
    """Handles Bookshare OAuth 2.0 authentication flow."""
    
    def __init__(self):
        """Initialize Bookshare OAuth client."""
        oauth_config = config.get('bookshare_oauth', {})
        self.client_id = oauth_config.get('client_id', '')
        self.client_secret = oauth_config.get('client_secret', '')
        self.base_url = oauth_config.get('base_url', 'https://api.bookshare.org')
        self.redirect_uri = oauth_config.get('redirect_uri', 'https://openlibrary.org/account/bookshare')
        
        # Bookshare OAuth endpoints
        self.auth_url = f"{self.base_url}/v2/oauth/authorize"
        self.token_url = f"{self.base_url}/v2/oauth/token"
        self.user_info_url = f"{self.base_url}/v2/user"
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Generate authorization URL for Bookshare OAuth flow.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL to redirect user to Bookshare
        """
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': 'read'
        }
        
        if state:
            params['state'] = state
            
        return f"{self.auth_url}?{urllib.parse.urlencode(params)}"
    
    def exchange_code_for_token(self, code: str, state: Optional[str] = None) -> Optional[dict]:
        """Exchange authorization code for access token.
        
        Args:
            code: Authorization code from Bookshare callback
            state: State parameter for verification
            
        Returns:
            Token response dict or None if failed
        """
        try:
            data = {
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': code,
                'redirect_uri': self.redirect_uri
            }
            
            response = requests.post(self.token_url, data=data, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Error exchanging code for token: {e}")
            return None
    
    def get_user_info(self, access_token: str) -> Optional[dict]:
        """Get user information from Bookshare API.
        
        Args:
            access_token: OAuth access token
            
        Returns:
            User info dict or None if failed
        """
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            }
            
            response = requests.get(self.user_info_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Error getting user info: {e}")
            return None
    
    def verify_bookshare_eligibility(self, user_info: dict) -> bool:
        """Verify if user is eligible for print disability access through Bookshare.
        
        Args:
            user_info: User information from Bookshare API
            
        Returns:
            True if user is eligible for print disability access
        """
        # Check if user has an active Bookshare membership
        # and is qualified for print disability access
        return (
            user_info.get('membershipStatus') == 'active' and
            user_info.get('hasQualification', False)
        )


def get_bookshare_oauth_client() -> BookshareOAuth:
    """Get configured Bookshare OAuth client instance."""
    return BookshareOAuth()