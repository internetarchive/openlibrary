# Auth & Accounts

> **Status:** partial
> **Sources:** `raw/openlibrary-docs-ai/subsystems/otp_service.md`, code synthesis (`account.py`, `accounts/model.py`)
> **Last ingested:** 2026-06-27

Open Library's auth system covers patron accounts, xauthn (IA cross-auth), S3 credentials, cookies, signup/login flows, and an OTP (one-time password) service used by Lenny (IA's lending service).

---

## Login Flow (Password Path)

When a user submits the login form, `login.POST()` (`plugins/upstream/account.py`) extracts credentials and calls `audit_accounts()`:

```
login.POST()
  → login()
      → audit_accounts(email, password, require_link=True, s3_access_key, s3_secret_key)
```

S3 keys are accepted from form params (`access`, `secret`) **or** HTTP headers (`HTTP_X_S3_ACCESS`, `HTTP_X_S3_SECRET`).

### audit_accounts() step-by-step

**Step 1 — Authenticate with IA:**
- If S3 keys provided → `InternetArchiveAccount.s3auth(access, secret)` — validates keypair against IA S3 auth endpoint
- Otherwise → `InternetArchiveAccount.authenticate(email, password)` — calls xauthn `authenticate` op

**Step 2 — Get IA account info:**
`InternetArchiveAccount.get(email=email)` → xauthn `info` op → returns IA account with `itemname` (e.g. `@patron_username`).

**Step 3 — Find/link OL account:**
- Look up OL account by `ia_account.itemname` (`get_by_link`)
- If not found: look up OL account by email (`get_by_email`)
  - If email-matched account has a *different* itemname → itemname mismatch detected → auto-unlink + re-link to current IA account (logged as error)
- If no OL account found at all → auto-create one:
  - Password: `secrets.token_urlsafe(32)` (IA credentials are primary; OL password not used)
  - Linked immediately; `stats.increment("ol.account.xauth.ia-auto-created-ol")`

**Step 4 — Get S3 keys:**
- Current behavior: `authenticate` response includes `{"values": {"access": ..., "secret": ...}}` directly
- Post-#12942 migration path: `authenticate` returns a `token`; then `issue_key` xauthn op with that token → `{"s3": {"access": ..., "secret": ...]}`
- S3-key login path: keys were already validated in step 1; reused directly

**Step 5 — Set Infobase auth token (the kludge):**
```python
web.ctx.conn.set_auth_token(ol_account.generate_login_code())
```
This **bypasses** the normal `site.get().login()` call (which requires OL credentials). Since users log in with IA credentials, OL credentials aren't available, so the auth token is set directly. This is explicitly called a "kludge" in the source.

**Step 6 — Return audit result:**
```python
return {
    "authenticated": True,
    "special_access": has_special_access,  # Print Disability
    "ia_email": ..., "ol_email": ...,
    "ia_username": ..., "ol_username": ...,
    "link": ol_account.itemname,
    "s3_keys": {"access": ..., "secret": ...},
}
```

### _set_login_cookies()

After `audit_accounts()` returns, `_set_login_cookies(audit, ol_account, remember=remember)` sets:

| Cookie | Value | Notes |
|--------|-------|-------|
| `config.login_cookie_name` | OL auth token | Standard Infobase session |
| `pd` | `"1"` or `""` | Print Disability access flag |
| `s3` | `encrypt_s3_keys(access, secret)` | `secure=True, httponly=True, samesite="Lax"` |
| `sfw` | `"yes"` or `""` | Safe-for-work (SafeMode) preference |

The `s3` cookie carries encrypted S3 credentials for all subsequent IA API calls during the session (borrowing, availability checks, etc).

---

## xauthn

**xauthn** is an internal Internet Archive service that acts as the cross-authentication bridge between OL and IA accounts.

- **Source:** `https://git.archive.org/ia/petabox/tree/master/www/sf/services/xauthn` (internal IA repo)
- **Config:** URL at `lending.config_ia_xauth_api_url`; OL authenticates to xauthn using its own S3 service keypair (`lending.config_ia_ol_xauth_s3`)
- **Protocol:** `POST {url}?op={op}` with JSON body; returns `{"success": bool, "values": {...}}`
- **Error codes:** HTTP 403 → `OLAuthenticationError("security_error")`; HTTP 504 on `create` → propagated as exception

### Operations

| Op | Purpose | OL caller |
|----|---------|-----------|
| `authenticate` | Verify email + password; returns token (+ S3 keys currently) | `audit_accounts()` |
| `info` | Fetch IA account by email | `InternetArchiveAccount.get()` |
| `create` | Create new IA account | signup flow |
| `activate` | Verify email token (account activation) | `InternetArchiveAccount.verify()` |
| `issue_key` | Issue new S3 keypair; requires preceding-auth token | `issue_s3_key()` |
| `issue_otp` | Issue OTP to patron | `issue_otp()` |
| `redeem_otp` | Validate OTP submitted by patron | `redeem_otp()` |

The `issue_key` op was separated from other ops as part of issue #12942 — previously, `authenticate` and `activate` returned S3 keys inline; now callers must request them in a separate step. OL has graceful migration code: tries inline first, falls back to `issue_key`.

---

## S3 Credentials Flow

S3 keypairs are IA's authentication mechanism for their content APIs (loans, availability, etc.).

**How a patron's S3 keys reach OL:**
1. Login → xauthn `authenticate` op → keys returned (current) or `issue_key` op (post-#12942)
2. Keys are AES-encrypted and stored in the `s3` cookie for the session
3. Borrow/lending flows read the `s3` cookie and pass keys to `lending.s3_loan_api()`

**How OL's own service key is used:**
- `lending.config_ia_ol_xauth_s3` holds a service-level S3 keypair for OL to authenticate as a service to xauthn
- These are separate from patron keys — they identify OL as an authorized caller of the xauthn API
- Config values live in olsystem (excluded from this KB per security policy — see [[infrastructure]])

**S3 validation path:**
`InternetArchiveAccount.s3auth(access_key, secret_key)` → `GET {lending.config_ia_s3_auth_url}` with `Authorization: LOW {access}:{secret}` header → IA validates and returns `{"authorized": True, "username": ...}`.

---

## OTP Service

Open Library acts as a TOTP (Timed One-Time Password) provider for **Lenny**, the Internet Archive book-lending service. Lenny requests an OTP → OL generates one and emails it to the patron → patron enters it in Lenny → Lenny forwards it back to OL for verification.

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/account/otp/issue` | Generate and email an OTP to a patron |
| `POST` | `/account/otp/redeem` | Verify an OTP submitted by a patron |

Both endpoints read `service_ip` from `X-Forwarded-For`. Return JSON.

### Key implementation details

- **Class**: `openlibrary/core/auth.py::TimedOneTimePassword` — generate, validate, rate-limit
- **Routes**: `openlibrary/plugins/upstream/account.py::otp_service_issue` + `otp_service_redeem`
- **Valid window**: `VALID_MINUTES = 10` (rolling 1-minute windows)
- **Rate limiting**: Memcache-backed, applied per client and per email/ip
- **`service_ip` must match** between issue and redeem requests

### Local testing

```bash
# 1. Add otp_seed to dev config (conf/openlibrary.yml)
# otp_seed: "dev-secret-seed"

# 2. Start stack
docker compose up

# 3. Issue an OTP (sendmail=false skips SMTP)
curl -s -X POST http://localhost:8080/account/otp/issue \
  -H 'X-Forwarded-For: 1.2.3.4' \
  -d 'email=patron@example.com&ip=5.6.7.8&sendmail=false'
# → {"success": "issued"}

# 4. Compute the OTP locally (since email isn't sent)
docker compose exec web python3 - <<'EOF'
from openlibrary.core.auth import TimedOneTimePassword as OTP
print(OTP.generate("1.2.3.4", "patron@example.com", "5.6.7.8"))
EOF

# 5. Redeem the OTP
curl -s -X POST http://localhost:8080/account/otp/redeem \
  -H 'X-Forwarded-For: 1.2.3.4' \
  -d 'email=patron@example.com&ip=5.6.7.8&otp=<OTP_FROM_STEP_4>'
# → {"success": "redeemed"}
```

---

## What's Non-obvious / Fragile

- **OL password is unused for existing patrons.** IA credentials are primary. OL account passwords are random tokens (`secrets.token_urlsafe(32)`).
- **The auth kludge.** `web.ctx.conn.set_auth_token(ol_account.generate_login_code())` bypasses the normal Infobase `site.get().login()` — called a kludge in the source at `accounts/model.py:1166`.
- **Auto-account creation.** If you log in with valid IA credentials but no linked OL account exists, one is silently created. Stats: `ol.account.xauth.ia-auto-created-ol`.
- **Itemname mismatch recovery.** If OL's itemname for an account doesn't match the IA account's current itemname (e.g. IA account was deleted and recreated), `audit_accounts` auto-unlinks and re-links. This is logged as an error.
- **Print Disability flag.** The `pda` cookie (set elsewhere) is checked at login time; if the IA account has `has_disability_access=True`, PD status is updated to `FULFILLED`.
- **Issue #12942 migration in progress.** S3 keys may come from the `authenticate` response directly OR from a separate `issue_key` call. Both paths coexist in production until #12942 is fully deployed.

---

## Key Files

| File | Purpose |
|------|---------|
| `openlibrary/plugins/upstream/account.py` | Login routes, `login.POST()`, `_set_login_cookies()`, OTP endpoints |
| `openlibrary/accounts/model.py` | `audit_accounts()`, `InternetArchiveAccount.xauth()`, `s3auth()`, `issue_s3_key()` |
| `openlibrary/core/auth.py` | `TimedOneTimePassword` — OTP generate/validate/rate-limit |
| `conf/openlibrary.yml` | `otp_seed`, `affiliate_server`, xauthn URL config (prod values in olsystem) |

---

## Dependencies

**Depends on:**
- [[core-operations]] — web.py routing; Infobase session/auth token
- [[infrastructure]] — Memcache for rate limiting; olsystem for production secrets (xauthn URL, service S3 keys)
- [[lending]] — S3 keys from auth flow are consumed by the lending borrow flow; HMAC for BookReader login also uses IA credentials

**Depended on by:**
- [[lending]] — OTP issued to patrons as part of the IA lending flow; S3 keys used in `s3_loan_api()`
- [[features]] — patron account identity for bookshelves, ratings, etc.

---

*Sources: `raw/openlibrary-docs-ai/subsystems/otp_service.md` · code synthesis: `account.py`, `accounts/model.py` · See [[README]] · [[METHODOLOGY]]*
