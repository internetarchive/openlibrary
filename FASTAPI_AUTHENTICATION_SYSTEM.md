# FastAPI Authentication System - Technical Documentation

## Overview

This document describes the FastAPI authentication system for Open Library, which enables FastAPI endpoints running on port 18080 to authenticate users using the existing Open Library session cookies from the legacy web.py application (port 8080).

## Architecture

### Design Philosophy

The FastAPI authentication system is designed to:

1. **Read-Only Cookie Validation**: Read and validate existing session cookies without creating new ones
2. **Compatibility**: Work seamlessly with the legacy web.py authentication system
3. **FastAPI Best Practices**: Use FastAPI dependencies and middleware patterns
4. **Backward Compatible**: Maintain the same cookie format and validation logic

### System Components

```
Legacy App (Port 8080)          FastAPI App (Port 18080)
┌─────────────────┐            ┌──────────────────────┐
│  Login Form     │            │  FastAPI Endpoints   │
│  /account/login │            │  - /account/test.json│
│                 │            │  - /search.json      │
├─────────────────�            ├──────────────────────┤
│  Set Cookie     │            │  Auth Middleware     │
│  session=...    │────────────│  - Read cookie       │
│                 │            │  - Validate HMAC     │
│                 │            │  - Set request.state │
└─────────────────┘            └──────────────────────┘
                                       │
                                       ↓
                                ┌─────────────────┐
                                │  Dependencies    │
                                │  - get_user()    │
                                │  - require_auth()│
                                └─────────────────┘
```

## Cookie Format

The FastAPI system reads the same cookie format as the legacy system:

```
session=/people/{username},{timestamp},{salt}${hash}
```

**Example:**
```
/people/openlibrary,2026-01-18T17:25:46,7897f$841a3bd2f8e9a5ca46f505fa557d57bd
```

**Components:**
- **User Key**: `/people/username`
- **Timestamp**: ISO 8601 format (e.g., `2026-01-18T17:25:46`)
- **Salt**: 5-character random string
- **Hash**: HMAC-MD5 signature

**Validation:**
```python
hash = HMAC-MD5(secret_key, salt + "/people/username,timestamp")
```

## Implementation

### File Structure

```
openlibrary/
├── fastapi/
│   ├── auth.py          # Authentication middleware and dependencies
│   ├── account.py       # Account test endpoints
│   ├── search.py        # Search endpoints (can use auth)
│   └── languages.py     # Language endpoints (can use auth)
└── asgi_app.py          # FastAPI app initialization
```

### Core Components

#### 1. Authentication Middleware (`openlibrary/fastapi/auth.py`)

**Purpose**: Automatically decode session cookie and add user to `request.state`

**Function**: `add_authentication_middleware(app)`

This middleware:
1. Reads the session cookie from each request
2. Decodes and validates the cookie
3. Adds user information to `request.state.user`
4. Works transparently for all endpoints

**Usage**:
```python
# In asgi_app.py
add_authentication_middleware(app)
```

**Access in endpoints**:
```python
@router.get("/example")
async def example(request: Request):
    user = request.state.user
    if user.is_authenticated:
        return {"username": user.username}
    else:
        return {"message": "Not authenticated"}
```

#### 2. Authentication Dependencies

**Dependency: `get_authenticated_user`**

Returns `AuthenticatedUser` or `UnauthenticatedUser` based on cookie validity.

```python
from fastapi import Depends
from openlibrary.fastapi.auth import get_authenticated_user

@router.get("/endpoint")
async def my_endpoint(
    user: AuthenticatedUser | UnauthenticatedUser = Depends(get_authenticated_user)
):
    if user.is_authenticated:
        return {"hello": user.username}
    else:
        return {"error": user.error}
```

**Dependency: `require_authenticated_user`**

Requires authentication, returns 401 if not valid.

```python
from openlibrary.fastapi.auth import require_authenticated_user

@router.get("/protected")
async def protected(
    user: AuthenticatedUser = Depends(require_authenticated_user)
):
    return {"secret": f"Data for {user.username}"}
```

#### 3. Test Endpoint (`openlibrary/fastapi/account.py`)

**Endpoint: `GET /account/test.json`**

Purpose: Test authentication without requiring login flow.

**Response**:
```json
{
  "username": "openlibrary",
  "user_key": "/people/openlibrary",
  "timestamp": "2026-01-18T17:25:46",
  "is_authenticated": true,
  "error": null,
  "cookie_name": "session",
  "cookie_value": "/people/openlibrary,2026-01-18T17:25:46,7897f$84...",
  "cookie_parsed": {
    "raw_decoded": "/people/openlibrary,2026-01-18T17:25:46,7897f$841a3bd2f8e9a5ca46f505fa557d57bd",
    "parts": ["/people/openlibrary", "2026-01-18T17:25:46", "7897f$841a3bd2f8e9a5ca46f505fa557d57bd"],
    "num_parts": 3,
    "user_key": "/people/openlibrary",
    "timestamp": "2026-01-18T17:25:46",
    "hash": "7897f$841a3bd2f8e9a..."
  }
}
```

## Usage Examples

### Example 1: Optional Authentication

```python
from fastapi import APIRouter, Depends
from openlibrary.fastapi.auth import get_authenticated_user

router = APIRouter()

@router.get("/api/books")
async def get_books(
    user: AuthenticatedUser | None = Depends(get_authenticated_user)
):
    """Endpoint that works for both authenticated and anonymous users."""
    if user:
        # Get personalized recommendations
        books = await get_personalized_books(user.username)
    else:
        # Get generic recommendations
        books = await get_generic_books()

    return {"books": books}
```

### Example 2: Required Authentication

```python
from openlibrary.fastapi.auth import require_authenticated_user

@router.post("/api/lists")
async def create_list(
    data: ListCreateRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user)
):
    """Endpoint that requires authentication."""
    # At this point, user is guaranteed to be authenticated
    new_list = await create_user_list(user.username, data)
    return new_list
```

### Example 3: Using Request State

```python
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/api/reading-log")
async def get_reading_log(request: Request):
    """Access user from request.state set by middleware."""
    user = request.state.user

    if not user.is_authenticated:
        raise HTTPException(status_code=401, detail="Login required")

    log = await get_reading_log(user.username)
    return {"log": log}
```

### Example 4: Conditional Behavior

```python
from fastapi import APIRouter, Depends
from openlibrary.fastapi.auth import get_authenticated_user, AuthenticatedUser

@router.put("/api/books/{book_id}/rating")
async def rate_book(
    book_id: str,
    rating: int,
    user: AuthenticatedUser | None = Depends(get_authenticated_user)
):
    """Allow anonymous viewing but require auth for rating."""

    # Get the book (works for everyone)
    book = await get_book(book_id)

    # Rating requires authentication
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="You must be logged in to rate books"
        )

    # Save rating
    await save_rating(user.username, book_id, rating)

    return {"book": book, "user_rating": rating}
```

## Data Models

### AuthenticatedUser

```python
class AuthenticatedUser(BaseModel):
    username: str              # Username without /people/ prefix
    user_key: str              # Full key: /people/username
    timestamp: str             # Cookie timestamp
```

**Note:** Unauthenticated users are represented as `None` rather than a separate model. This follows FastAPI best practices and keeps the API simple and idiomatic. The `is_authenticated` status is determined by checking `user is not None` rather than a field on the model.

## Testing

### Manual Testing with Curl

#### 1. Login to Get Session Cookie

```bash
# Login via legacy app
curl -v -X POST http://localhost:8080/account/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=openlibrary@example.com&password=admin123&remember=true" \
  -c /tmp/cookies.txt
```

#### 2. Test Authentication Endpoint

```bash
# Test with valid session
curl -v http://localhost:18080/account/test.json \
  -b /tmp/cookies.txt

# Expected response (formatted)
{
  "username": "openlibrary",
  "user_key": "/people/openlibrary",
  "timestamp": "2026-01-18T17:25:46",
  "is_authenticated": true,
  "error": null,
  "cookie_name": "session",
  "cookie_value": "/people/openlibrary,2026-01-18T17:25:46,7897f$84...",
  "cookie_parsed": {
    "raw_decoded": "/people/openlibrary,2026-01-18T17:25:46,7897f$841a3bd2f8e9a5ca46f505fa557d57bd",
    "parts": ["/people/openlibrary", "2026-01-18T17:25:46", "7897f$841a3bd2f8e9a5ca46f505fa557d57bd"],
    "num_parts": 3,
    "user_key": "/people/openlibrary",
    "timestamp": "2026-01-18T17:25:46",
    "hash": "7897f$841a3bd2f8e9a..."
  }
}
```

#### 3. Test Protected Endpoint

```bash
# Test protected endpoint (requires auth)
curl -v http://localhost:18080/account/protected.json \
  -b /tmp/cookies.txt

# Expected response
{
  "message": "Hello openlibrary!",
  "user_key": "/people/openlibrary",
  "timestamp": "2026-01-18T17:25:46",
  "is_authenticated": true
}
```

#### 4. Test Without Authentication

```bash
# Test without cookie
curl -v http://localhost:18080/account/test.json

# Expected response
{
  "username": null,
  "user_key": null,
  "timestamp": null,
  "is_authenticated": false,
  "error": "No session cookie provided",
  "cookie_name": "session",
  "cookie_value": null,
  "cookie_parsed": {}
}

# Test protected endpoint without auth (should return 401)
curl -v http://localhost:18080/account/protected.json

# Expected response
{
  "detail": "Authentication required"
}
```

#### 5. Test with Invalid Cookie

```bash
# Test with invalid cookie
curl -v http://localhost:18080/account/test.json \
  -b "session=invalid_cookie"

# Expected response
{
  "username": null,
  "user_key": null,
  "timestamp": null,
  "is_authenticated": false,
  "error": "Invalid cookie signature",
  "cookie_name": "session",
  "cookie_value": "invalid_cookie",
  "cookie_parsed": {
    "raw_decoded": "invalid_cookie",
    "parts": ["invalid_cookie"],
    "num_parts": 1
  }
}
```

### Automated Testing

```python
import pytest
from httpx import AsyncClient

async def test_authenticated_request(async_client: AsyncClient):
    """Test with valid session cookie"""
    response = await async_client.get(
        "/account/test.json",
        cookies={"session": "/people/openlibrary,2026-01-18T17:25:46,7897f$841a3bd2f8e9a5ca46f505fa557d57bd"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] == True
    assert data["username"] == "openlibrary"

async def test_unauthenticated_request(async_client: AsyncClient):
    """Test without session cookie"""
    response = await async_client.get("/account/test.json")

    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] == False
    assert data["username"] is None

async def test_protected_endpoint_requires_auth(async_client: AsyncClient):
    """Test that protected endpoint returns 401 without auth"""
    response = await async_client.get("/account/protected.json")

    assert response.status_code == 401

async def test_protected_endpoint_with_auth(async_client: AsyncClient):
    """Test that protected endpoint works with valid auth"""
    response = await async_client.get(
        "/account/protected.json",
        cookies={"session": "/people/openlibrary,2026-01-18T17:25:46,7897f$841a3bd2f8e9a5ca46f505fa557d57bd"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] == True
```

## Security Considerations

### Current Implementation

1. **Read-Only Validation**: FastAPI only reads cookies, doesn't create them
2. **HMAC-MD5**: Same hash algorithm as legacy system
3. **Secret Key**: Uses the same secret key from `conf/infobase.yml`
4. **No Session Creation**: Login still happens via legacy app

### Security Properties

✅ **Secure**:
- Cookie signature prevents tampering
- Uses constant-time comparison (`hmac.compare_digest`)
- Secret key never exposed in API responses

⚠️ **Considerations**:
- MD5 is cryptographically weak (inherited from legacy system)
- No server-side session expiration
- Cookies transmitted over HTTP (unless HTTPS enforced)

### Recommendations for Migration

1. **Upgrade Hash Algorithm**: When migrating, upgrade to HMAC-SHA256
2. **Add Expiration**: Implement server-side session expiration
3. **HTTPS Only**: Enforce HTTPS in production
4. **CSRF Protection**: Add CSRF tokens for state-changing operations

## Configuration

### Required Settings

The authentication system reads these settings from the legacy config:

**`conf/openlibrary.yml`:**
```yaml
login_cookie_name: session  # Cookie name to read
infobase_config_file: infobase.yml
```

**`conf/infobase.yml`:**
```yaml
secret_key: xxx  # Must match the legacy system
```

### Environment Variables

Currently, the system uses config files. For future migration to environment variables:

```python
import os

SECRET_KEY = os.getenv("OL_AUTH_SECRET_KEY")
COOKIE_NAME = os.getenv("OL_AUTH_COOKIE_NAME", "session")
```

## Troubleshooting

### Common Issues

#### 1. "Invalid cookie signature"

**Cause**: Secret key mismatch between systems

**Solution**:
```bash
# Check secret key in config
grep secret_key conf/infobase.yml

# Ensure both systems use same config file
echo $OL_CONFIG
```

#### 2. "No session cookie provided"

**Cause**: Cookie not being sent

**Solution**:
```bash
# Check cookie is being sent
curl -v http://localhost:18080/account/test.json \
  -b "session=YOUR_COOKIE_VALUE"

# Check cookie name matches config
grep login_cookie_name conf/openlibrary.yml
```

#### 3. Middleware not adding user to request.state

**Cause**: Middleware not registered

**Solution**:
```python
# In asgi_app.py, ensure this is called:
add_authentication_middleware(app)
```

#### 4. Type checker errors with union types

**Cause**: Type checker can't narrow union types

**Solution**:
```python
# Use isinstance() to narrow types
if isinstance(user, UnauthenticatedUser):
    raise HTTPException(status_code=401)

# Or use require_authenticated_user dependency
user: AuthenticatedUser = Depends(require_authenticated_user)
```

## Integration with Legacy System

### Cookie Sharing

Both systems share the same cookie:

```
┌─────────────────────────────────────┐
│         Browser                      │
│  Cookie: session=...                 │
└────────┬──────────────┬──────────────┘
         │              │
         │              │
    Port 8080       Port 18080
    (Legacy)        (FastAPI)
         │              │
    Read & Write    Read Only
```

### Login Flow

```
User           Legacy (8080)          FastAPI (18080)
 │                    │                     │
 │─ POST /account/login ─>│                     │
 │                    │                     │
 │<─ Set session cookie ─│                     │
 │                    │                     │
 │─ GET /account/test.json ─────────────────>│
 │                    │                     │
 │<─ User info ─────────────────────────────│
```

### Session Management

- **Creation**: Only via legacy `/account/login`
- **Reading**: Both systems can read
- **Deletion**: Only via legacy `/account/logout`

## Performance Considerations

### Middleware Overhead

The authentication middleware adds minimal overhead:

1. **Cookie Reading**: O(1) - Simple dict lookup
2. **URL Decoding**: O(n) - Where n is cookie length
3. **HMAC Verification**: O(1) - Fixed-time operation
4. **Total**: < 1ms per request

### Caching

The current implementation doesn't cache decoded cookies because:

1. Decoding is very fast (< 1ms)
2. Cookies vary per request
3. Simplicity is preferred for migration

If performance becomes an issue, consider caching:

```python
from functools import lru_cache

@lru_cache(maxsize=1024)
def decode_cached(cookie_value: str):
    return authenticate_user_from_cookie(cookie_value)
```

## Migration Path

### Phase 1: Current State (Read-Only)

✅ **Done**:
- FastAPI can read legacy cookies
- No login functionality in FastAPI
- Login happens via legacy system

### Phase 2: Shared Auth (Near Future)

🔄 **Planned**:
- Add more authenticated endpoints
- Implement rate limiting
- Add API key authentication

### Phase 3: Full Migration (Future)

📋 **To Do**:
- Implement login in FastAPI
- Upgrade to SHA-256
- Add session expiration
- Implement refresh tokens

## Best Practices

### DO ✅

1. **Use Dependencies**: Prefer `Depends(get_authenticated_user)` over direct cookie access
2. **Type Narrowing**: Use `isinstance()` to narrow union types
3. **Error Handling**: Always check `user.is_authenticated` before using user data
4. **Test Both Cases**: Test both authenticated and unauthenticated scenarios
5. **Use Middleware**: Let middleware handle automatic user injection

### DON'T ❌

1. **Don't Create Cookies**: FastAPI only reads, doesn't create session cookies
2. **Don't Bypass Validation**: Always use dependencies, don't manually decode cookies
3. **Don't Ignore Errors**: Always handle unauthenticated users appropriately
4. **Don't Hardcode Cookie Names**: Use `config.login_cookie_name`
5. **Don't Expose Secrets**: Never include secret key in error messages or logs

## API Reference

### Dependencies

#### `get_authenticated_user`

```python
async def get_authenticated_user(
    request: Request,
    session: str | None = Cookie(None, alias=config.get("login_cookie_name", "session"))
) -> AuthenticatedUser | None
```

Returns authenticated user if cookie is valid, None otherwise.

**Returns**:
- `AuthenticatedUser` if cookie is valid
- `None` if cookie is missing or invalid

#### `require_authenticated_user`

```python
async def require_authenticated_user(
    user: AuthenticatedUser | None = Depends(get_authenticated_user)
) -> AuthenticatedUser
```

Requires authentication, raises 401 if not valid.

**Raises**:
- `HTTPException(401)` if user is None (not authenticated)

**Returns**:
- `AuthenticatedUser` (guaranteed)

### Middleware

#### `add_authentication_middleware`

```python
def add_authentication_middleware(app: FastAPI) -> None
```

Adds authentication middleware to the FastAPI app.

**Side Effects**:
- Sets `request.state.user` on every request
- `request.state.user` is `AuthenticatedUser` or `None`

### Endpoints

#### `GET /account/test.json`

Test endpoint for authentication.

**Response**: `AuthTestResponse`

#### `GET /account/protected.json`

Example protected endpoint (requires auth).

**Response**: JSON with user info

**Raises**: 401 if not authenticated

#### `GET /account/optional.json`

Example endpoint with optional auth.

**Response**: JSON with different data based on auth status

## Summary

The FastAPI authentication system provides:

1. ✅ **Seamless Integration**: Reads legacy session cookies
2. ✅ **Type Safety**: Pydantic models for request/response
3. ✅ **FastAPI Best Practices**: Dependencies and middleware
4. ✅ **Easy Testing**: Test endpoint for debugging
5. ✅ **Flexible Usage**: Optional or required authentication
6. ✅ **Migration Ready**: Prepared for future enhancements

The system is production-ready and can be used to add authenticated endpoints to the FastAPI application immediately.

---

**Document Version**: 1.0
**Last Updated**: 2026-01-18
**Author**: Open Library Team
**Purpose**: FastAPI Authentication System Documentation
