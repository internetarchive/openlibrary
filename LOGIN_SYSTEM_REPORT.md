# Open Library Login System - Comprehensive Technical Report

## TODO: Delete this before merging, it's just for local understanding and fully AI generated.

## Executive Summary

This document provides a complete technical analysis of the Open Library authentication system, including the login flow, cookie encoding/decoding mechanism, files involved, and dependencies. This report is essential for understanding the system before migration.

---

## Working Curl Command to Login

```bash
curl -v -X POST http://localhost:8080/account/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=openlibrary@example.com&password=admin123&remember=true" \
  -c /tmp/cookies.txt -b /tmp/cookies.txt
```

**Expected Response:**
- HTTP 303 redirect
- Sets `session` cookie (the login cookie)
- Sets `pd` cookie (print disability flag)
- Redirects to `/account/books` (or configured redirect URL)

**Verifying Authentication:**
```bash
# Check if logged in
curl http://localhost:8080/account/books -b /tmp/cookies.txt
# Should return 303 and redirect to /people/openlibrary/books if authenticated
```

---

## Login Flow Architecture

### 1. Login Request Endpoint

**URL:** `/account/login`
**Method:** POST
**Content-Type:** `application/x-www-form-urlencoded`

**Form Fields:**
- `username` - Email address (acts as username)
- `password` - Password
- `remember` - Checkbox (optional, extends cookie expiration)
- `redirect` - Hidden field (URL to redirect after successful login)
- `action` - Hidden field (for post-login actions like following publishers)
- `access` - Hidden field (S3 access key for API authentication)
- `secret` - Hidden field (S3 secret key for API authentication)

### 2. Login Flow Sequence

```
User submits form
    ↓
account_login.POST() in /openlibrary/plugins/upstream/account.py
    ↓
audit_accounts() function in /openlibrary/accounts/model.py
    ↓
├─ Validates email format
├─ Authenticates with Internet Archive (via xauth API)
│  ├─ If S3 keys provided: InternetArchiveAccount.s3auth()
│  └─ If email/password: InternetArchiveAccount.authenticate()
│     └─ Calls InternetArchiveAccount.xauth('authenticate', ...)
│        └─ POST to IA xauth API
├─ Finds/creates OpenLibrary account
│  ├─ Links IA account to OL account via itemname
│  └─ Auto-creates OL account if it doesn't exist
└─ Returns audit result
    ↓
Set authentication cookies
    ├─ web.setcookie('pd', ...)  # Print disability flag
    └─ web.setcookie(config.login_cookie_name, web.ctx.conn.get_auth_token())
        ↓
        Account.generate_login_code() creates:
        "/people/{username},{ISO_TIMESTAMP},{SALT}${HASH}"
        ↓
        Hash format: HMAC-MD5(secret_key, salt + text)
        where text = "/people/{username},{ISO_TIMESTAMP}"
    ↓
Redirect user to target page
```

---

## Cookie Encoding/Decoding Mechanism

### Cookie Structure

**Cookie Name:** `session` (configurable via `config.login_cookie_name`)
**Cookie Value Format:** `/people/{username},{timestamp},{salt}${hash}`

**Example:**
```
/people/openlibrary,2026-01-18T17:25:46,7897f$841a3bd2f8e9a5ca46f505fa557d57bd
```

### Cookie Generation (encode)

**Location:** `openlibrary/accounts/model.py`, `Account.generate_login_code()`

```python
def generate_login_code(self) -> str:
    """Returns a string that can be set as login cookie to log in as this user."""
    user_key = "/people/" + self.username
    t = datetime.datetime(*time.gmtime()[:6]).isoformat()
    text = f"{user_key},{t}"
    return text + "," + generate_hash(get_secret_key(), text)
```

**Hash Generation:**

```python
def generate_hash(secret_key, text, salt=None) -> str:
    if not isinstance(secret_key, bytes):
        secret_key = secret_key.encode('utf-8')
    salt = (
        salt
        or hmac.HMAC(
            secret_key, str(random.random()).encode('utf-8'), hashlib.md5
        ).hexdigest()[:5]
    )
    hash = hmac.HMAC(
        secret_key, (salt + web.safestr(text)).encode('utf-8'), hashlib.md5
    ).hexdigest()
    return f'{salt}${hash}'
```

**Algorithm:**
1. Generate random 5-character salt (or use provided salt)
2. Create HMAC-MD5 hash: `HMAC(secret_key, salt + text)`
3. Return format: `{salt}${hash}`
4. Full cookie: `{user_key},{timestamp},{salt}${hash}`

**Secret Key Location:**
- Config: `config.infobase['secret_key']`
- File: `conf/infobase.yml` → `secret_key: xxx`

### Cookie Verification (decode)

**Location:** Infobase client (external dependency: infogami)

The verification happens automatically when the infobase client processes requests:
1. Extract cookie from request headers
2. Parse: `/people/{username},{timestamp},{salt}${hash}`
3. Recompute HMAC with secret_key and salt
4. Compare with provided hash
5. If valid, set user context in `web.ctx.site`

**Key Configuration:**
- Cookie name: `conf/openlibrary.yml` → `login_cookie_name: session`
- Secret key: `conf/infobase.yml` → `secret_key: xxx`

### Cookie Security Features

1. **HMAC-MD5 Signing:** Prevents tampering
2. **Timestamp:** Can be used for expiration (though server-side verification varies)
3. **Salt:** Prevents rainbow table attacks
4. **URL Encoding:** Cookie values are URL-encoded when set

---

## Files Involved in Login System

### Core Authentication Files

#### 1. `/openlibrary/plugins/upstream/account.py`
**Purpose:** Main login/logout endpoint handlers

**Key Classes/Functions:**
- `account_login` class (line ~500)
  - `POST()` method - Handles login form submission
  - `GET()` method - Renders login form
- `account_logout` class (line ~670)
- `account_login_json` class (line ~490) - JSON API for login
- `_set_account_cookies()` - Sets additional cookies (sfw, yrg_banner_pref)

**Key Logic:**
```python
def POST(self):
    i = web.input(username="", password="", remember=False, redirect="/", ...)
    email = i.username
    audit = audit_accounts(email, i.password, ...)

    if error := audit.get('error'):
        return self.render_error(error, i)

    # Set cookies
    expires = 3600 * 24 * 365 if i.remember else ""
    web.setcookie(config.login_cookie_name, web.ctx.conn.get_auth_token(), expires=expires)

    # Redirect
    raise web.seeother(i.redirect)
```

#### 2. `/openlibrary/accounts/model.py`
**Purpose:** Account data models and authentication logic

**Key Classes:**
- `Account` (base class)
  - `generate_login_code()` - Creates auth token
  - `verify_password()` - Verifies password hash
  - `login()` - Attempts login with username/password
- `OpenLibraryAccount(Account)`
  - `get_by_email()` - Find account by email
  - `get_by_username()` - Find account by username
  - `get_by_link()` - Find account by IA itemname
  - `authenticate()` - Authenticate with OL credentials
  - `link()` - Link to IA account
  - `unlink()` - Unlink from IA account
- `InternetArchiveAccount`
  - `create()` - Create new IA account
  - `xauth()` - Call IA xauth API
  - `s3auth()` - Authenticate with S3 keys
  - `get()` - Get IA account info
  - `authenticate()` - Authenticate with email/password

**Key Functions:**
- `audit_accounts()` - Main authentication audit function
- `generate_hash()` - Generate HMAC-MD5 hash
- `verify_hash()` - Verify hash
- `get_secret_key()` - Get secret key from config

#### 3. `/openlibrary/accounts/__init__.py`
**Purpose:** Public API for account operations

**Key Functions:**
- `get_current_user()` - Get currently logged-in user
- `find()` - Find account by username/email
- `login()` - Login user
- `update_account()` - Update account details

### Supporting Files

#### 4. `/openlibrary/plugins/upstream/forms.py`
**Purpose:** Form definitions

**Key Forms:**
- `Login` - Login form (username, password, redirect, action fields)
- `RegisterForm` - Registration form
- `ForgotPassword` - Forgot password form

#### 5. `/openlibrary/templates/login.html`
**Purpose:** Login page template

**Key Elements:**
- Form with action="/account/login"
- Fields: username (email), password, remember
- Hidden fields: redirect, action, access, secret
- Links to forgot password and signup

#### 6. `/openlibrary/plugins/openlibrary/connection.py`
**Purpose:** Database connection middleware

**Key Classes:**
- `ConnectionMiddleware` - Base middleware
- `IAMiddleware` - IA-specific operations
- `MemcacheMiddleware` - Caching layer
- `HybridConnection` - Local + remote connections

**Key Methods:**
- `get_auth_token()` - Get current auth token
- `set_auth_token()` - Set auth token

#### 7. `/conf/openlibrary.yml`
**Purpose:** Open Library configuration

**Key Settings:**
```yaml
login_cookie_name: session
infobase_config_file: infobase.yml
ia_xauth_api_url: http://web:8080/internal/fake/xauth  # Dev mode
ia_ol_xauth_s3:
  s3_key: XXX
  s3_secret: XXX
```

#### 8. `/conf/infobase.yml`
**Purpose:** Infobase configuration

**Key Settings:**
```yaml
secret_key: xxx  # Used for cookie signing
db_parameters:
  engine: postgres
  database: openlibrary
```

---

## Libraries and Dependencies

### Authentication & Security

1. **web.py** (git+https://github.com/webpy/webpy.git)
   - Web framework
   - Request/response handling
   - Cookie management (`web.setcookie()`, `web.cookies()`)

2. **requests** (2.32.4)
   - HTTP client for Internet Archive API calls
   - Used in `InternetArchiveAccount.xauth()` and `s3auth()`

3. **validate_email** (1.3)
   - Email validation in registration
   - Used in `valid_email()` function

### Cryptography

1. **hmac** (Python standard library)
   - HMAC-MD5 for cookie signing
   - Used in `generate_hash()`

2. **hashlib** (Python standard library)
   - MD5 hashing for HMAC
   - Used in `generate_hash()`

3. **secrets** (Python standard library)
   - Random password generation
   - Used in `OpenLibraryAccount.create()`

### Database & Storage

1. **psycopg2** (2.9.6)
   - PostgreSQL adapter
   - Stores account data in Postgres

2. **python-memcached** (1.59)
   - Memcache client
   - Caches account data via `MemcacheMiddleware`

### Framework & Infrastructure

1. **infogami** (external dependency, not in requirements.txt)
   - Core database abstraction layer
   - Account management
   - Authentication token verification

2. **gunicorn** (23.0.0)
   - WSGI server
   - Handles HTTP requests

### Additional Dependencies

- **PyYAML** (6.0.1) - Config file parsing
- **simplejson** (3.19.1) - JSON encoding/decoding
- **python-dateutil** (2.8.2) - Date/time handling

---

## Authentication Methods

Open Library supports multiple authentication methods:

### 1. Email/Password (Internet Archive Credentials)

**Flow:**
```
User submits email/password
    ↓
InternetArchiveAccount.authenticate(email, password)
    ↓
POST to IA xauth API with op='authenticate'
    ↓
IA validates credentials
    ↓
Returns success/failure with S3 keys
    ↓
S3 keys saved to OL account
    ↓
OL session created
```

**Configuration:**
- `ia_xauth_api_url` - IA xauth endpoint
- Dev mode uses: `http://web:8080/internal/fake/xauth`
- Production uses: `https://archive.org/services/xauthn`

### 2. S3 Keys (API Authentication)

**Flow:**
```
Client provides S3 access/secret keys
    ↓
InternetArchiveAccount.s3auth(access_key, secret_key)
    ↓
GET to IA S3 auth endpoint with LOW authorization header
    ↓
IA validates S3 keys
    ↓
Returns username and itemname
    ↓
OL finds/creates account
    ↓
OL session created
```

**Use Case:** API authentication, programmatic access

### 3. OL Username/Password (Legacy)

**Flow:**
```
User submits OL username/password
    ↓
OpenLibraryAccount.authenticate(email, password)
    ↓
web.ctx.site.login(username, password)
    ↓
Infobase validates against OL account store
    ↓
OL session created
```

**Note:** This is being phased out in favor of IA credentials

---

## Cookie Management

### Cookie Types

1. **session** (login cookie)
   - Name: `session` (configurable)
   - Format: `/people/{username},{timestamp},{salt}${hash}`
   - Expiration: Session or 1 year if "remember me" checked

2. **pd** (print disability)
   - Name: `pd`
   - Value: "1" or empty
   - Purpose: Flag for special access

3. **sfw** (safe mode)
   - Name: `sfw`
   - Value: "yes" or empty
   - Purpose: Content filtering

### Cookie Security

**Protection Mechanisms:**
1. HMAC-MD5 signature prevents tampering
2. Secret key known only to server
3. Salt prevents rainbow table attacks
4. Timestamp enables expiration checks

**Vulnerabilities:**
- MD5 is considered weak for cryptographic purposes
- No expiration enforcement in cookie itself
- Cookies sent over HTTP (unless HTTPS enforced)

---

## Internet Archive Integration

### xauth API

**Purpose:** Internet Archive authentication service

**Operations:**
1. **authenticate** - Validate email/password
   ```python
   InternetArchiveAccount.xauth('authenticate', email='...', password='...')
   ```

2. **info** - Get account info
   ```python
   InternetArchiveAccount.xauth('info', itemname='@username')
   ```

3. **create** - Create new account
   ```python
   InternetArchiveAccount.xauth('create', email='...', password='...', screenname='...')
   ```

**Response Format:**
```json
{
  "success": true,
  "values": {
    "access": "s3_access_key",
    "secret": "s3_secret_key",
    "itemname": "@username",
    "screenname": "Display Name",
    "email": "user@example.com"
  }
}
```

### Account Linkage

**Concept:** OL accounts are linked to IA accounts via `itemname`

**Schema:**
```javascript
// OL Account document (in store)
{
  "_key": "account/username",
  "type": "account",
  "username": "username",
  "email": "user@example.com",
  "internetarchive_itemname": "@ia_username",  // Link to IA
  "s3_keys": {
    "access": "...",
    "secret": "..."
  },
  "status": "active",
  "created_on": "2026-01-18T17:25:46",
  "last_login": "2026-01-18T17:25:46"
}
```

**Linking Process:**
1. User authenticates with IA credentials
2. `audit_accounts()` finds/creates OL account
3. Sets `internetarchive_itemname` on OL account
4. Stores S3 keys for future API calls
5. Creates seamless single sign-on experience

---

## Error Handling

### Common Error Codes

**Location:** `get_login_error()` in `/openlibrary/plugins/upstream/account.py`

| Error Key | Description |
|-----------|-------------|
| `invalid_email` | Email format is invalid |
| `account_blocked` | Account has been blocked |
| `account_locked` | Account has been locked |
| `account_not_found` | No account found with this email |
| `account_incorrect_password` | Password is incorrect |
| `account_bad_password` | Wrong password |
| `account_not_verified` | OL account not verified |
| `ia_account_not_verified` | IA account not verified |
| `missing_fields` | Required fields missing |
| `email_registered` | Email already registered |
| `username_registered` | Username already taken |
| `invalid_s3keys` | Invalid S3 credentials |
| `request_timeout` | IA servers timeout |
| `undefined_error` | Unknown error |

### Error Display

Errors are displayed on the login form via `form.note`:
```python
f = forms.Login()
f.note = get_login_error(error_key)
return render.login(f)
```

---

## Development vs Production

### Development Mode

**Configuration:** `conf/openlibrary.yml`

**Special Features:**
```yaml
features:
  dev: enabled

# Uses fake IA endpoints for testing
ia_xauth_api_url: http://web:8080/internal/fake/xauth
ia_loan_api_url: http://web:8080/internal/fake/loans
```

**Fake xauth Endpoint:**
- Location: `/openlibrary/plugins/upstream/account.py`, `xauth` class
- Path: `/internal/fake/xauth`
- Always returns success for testing
- Allows bypassing real IA authentication

### Production Mode

**Configuration:**
```yaml
ia_xauth_api_url: https://archive.org/services/xauthn
ia_base_url: https://archive.org
```

**Real IA Integration:**
- Actual calls to archive.org
- Real email verification
- Real S3 key generation

---

## Migration Considerations

### Critical Components to Migrate

1. **Account Data**
   - PostgreSQL database (infobase)
   - Account documents in store
   - Email linking documents

2. **Authentication Logic**
   - `audit_accounts()` function
   - Cookie generation/verification
   - IA xauth integration

3. **Configuration**
   - Secret key (for cookie signing)
   - IA API endpoints
   - Cookie names

4. **Session Management**
   - Cookie format
   - Auth token handling
   - "Remember me" functionality

### Dependencies on External Systems

1. **Internet Archive xauth API**
   - Required for user authentication
   - Provides S3 keys for API access
   - Must remain available or be replaced

2. **Infobase**
   - Core database layer
   - Account storage
   - Auth token verification

### Data Schema

**Account Document:**
```
Type: account
Key: account/{username}

Fields:
- username (string)
- email (string)
- enc_password (string) - Hashed password
- status (string) - active/blocked/pending
- internetarchive_itemname (string) - Link to IA
- s3_keys (object) - {access, secret}
- created_on (datetime)
- last_login (datetime)
```

**Email Link Document:**
```
Type: account-email
Key: account-email/{email}

Fields:
- username (string)
- email (string)
```

---

## Testing the Login System

### Manual Testing with Curl

```bash
# 1. Login
curl -v -X POST http://localhost:8080/account/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=openlibrary@example.com&password=admin123&remember=true" \
  -c /tmp/cookies.txt

# 2. Verify authentication
curl -v http://localhost:8080/account/books \
  -b /tmp/cookies.txt

# 3. Logout
curl -v -X POST http://localhost:8080/account/logout \
  -b /tmp/cookies.txt

# 4. Verify logout
curl -v http://localhost:8080/account/books \
  -b /tmp/cookies.txt
```

### Unit Tests

**Location:** `openlibrary/tests/accounts/test_models.py`

**Key Test Functions:**
- `test_verify_hash()` - Hash generation/verification
- `test_xauth_http_error_without_json()` - xauth error handling
- Account creation tests
- Authentication tests

---

## Security Recommendations

### Current Security Posture

**Strengths:**
- HMAC signing prevents cookie tampering
- Salted hashes prevent rainbow tables
- Integration with IA provides centralized auth
- S3 keys for API authentication

**Weaknesses:**
- MD5 is cryptographically weak (use SHA-256)
- No server-side session expiration
- Cookies transmitted over HTTP (unless HTTPS enforced)
- Secret key in config file (should use env vars)

### Migration Security Improvements

1. **Upgrade Hash Algorithm**
   - Replace HMAC-MD5 with HMAC-SHA256
   - Update `generate_hash()` function

2. **Implement Session Expiration**
   - Add expiration check in cookie verification
   - Use timestamp for absolute expiration

3. **Environment Variables**
   - Move secret key to environment variables
   - Don't store in config files

4. **HTTPS Enforcement**
   - Redirect all HTTP to HTTPS
   - Set `Secure` flag on cookies

5. **CSRF Protection**
   - Add CSRF tokens to forms
   - Verify on POST

---

## Summary

The Open Library login system is a sophisticated authentication mechanism that:

1. **Leverages Internet Archive** for centralized user management
2. **Uses HMAC-signed cookies** for session management
3. **Supports multiple auth methods** (email/password, S3 keys)
4. **Links OL and IA accounts** via `itemname` field
5. **Provides seamless SSO** experience for users

**Key Files:**
- `/openlibrary/plugins/upstream/account.py` - Login endpoints
- `/openlibrary/accounts/model.py` - Auth logic
- `/conf/openlibrary.yml` - Configuration
- `/conf/infobase.yml` - Secret key

**Key Dependencies:**
- web.py (web framework)
- requests (HTTP client)
- infogami (database layer)
- Internet Archive xauth API

**Migration Priorities:**
1. Preserve account data structure
2. Maintain cookie format compatibility
3. Update secret key management
4. Consider security improvements
5. Plan IA xauth API dependency

---

**Report Generated:** 2026-01-18
**Open Library Version:** Current master branch
**Purpose:** Migration planning and system documentation
