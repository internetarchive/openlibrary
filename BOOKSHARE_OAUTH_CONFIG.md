# Bookshare OAuth Integration Configuration

This document describes the configuration requirements for the Bookshare OAuth integration in Open Library.

## Overview

The Bookshare OAuth integration allows users with print disabilities to automatically qualify for special access by connecting their Bookshare accounts during the registration process.

## Configuration

Add the following configuration to your `olsystem.yml` file:

```yaml
bookshare_oauth:
  client_id: "your_bookshare_client_id"
  client_secret: "your_bookshare_client_secret"
  base_url: "https://api.bookshare.org"  # Optional, defaults to this value
  redirect_uri: "https://your-domain.org/account/bookshare"  # Must match your registered OAuth app
```

## Bookshare Application Setup

1. Register your application with Bookshare Developer Portal
2. Configure the redirect URI to point to `https://your-domain.org/account/bookshare`
3. Request the following scopes: `read` (for user profile information)
4. Obtain your client ID and client secret

## User Flow

1. User creates Open Library account and selects "BookShare" as their qualifying program
2. After email verification and login, user is redirected to `/account/bookshare`
3. User clicks "Connect with Bookshare" and is redirected to Bookshare's OAuth authorization page
4. User authorizes the connection on Bookshare
5. Bookshare redirects back to Open Library with authorization code
6. Open Library exchanges the code for an access token
7. Open Library retrieves user info from Bookshare API to verify eligibility
8. If eligible, user's account is automatically marked as fulfilled for print disability access

## API Endpoints

### Internal Endpoints

- `GET /account/bookshare` - Serves OAuth authorization page or handles OAuth callback
- `GET /account/bookshare/complete` - Completes OAuth flow after user login (for users who weren't logged in during callback)

### Expected Bookshare API Responses

#### User Info Response
```json
{
  "userId": "12345",
  "membershipStatus": "active",
  "hasQualification": true,
  "firstName": "John",
  "lastName": "Doe", 
  "email": "user@example.com"
}
```

## Security Considerations

- OAuth state parameter is used for CSRF protection
- Session storage is used when available for storing OAuth state and temporary data
- Fallback mechanisms handle cases where sessions are not available
- All OAuth communications use HTTPS
- Access tokens are not permanently stored

## Error Handling

The integration includes comprehensive error handling for:
- Invalid OAuth configuration
- Network errors during OAuth flow
- Invalid or expired authorization codes
- Missing or invalid user information
- Users who don't qualify for print disability access
- Session management issues

## Testing

For development/testing environments, ensure:
1. Bookshare OAuth credentials are configured
2. Redirect URI matches your local development server
3. Test with both qualified and unqualified Bookshare accounts
4. Verify integration with existing print disability workflows