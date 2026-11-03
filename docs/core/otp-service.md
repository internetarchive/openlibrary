# OTP Auth Service

Open Library acts as a TOTP (Timed One-Time Password) provider for Lenny, the Internet Archive book-lending service. Lenny requests an OTP, Open Library generates one and emails it to the patron, and the patron enters it in Lenny, which forwards it back to Open Library for verification.

**Relevant files:**
- `openlibrary/core/auth.py` — `TimedOneTimePassword` class (generate, validate, rate-limit)
- `openlibrary/plugins/upstream/account.py` — `otp_service_issue` and `otp_service_redeem` endpoints

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/account/otp/issue` | Generate and email an OTP to a patron |
| POST | `/account/otp/redeem` | Verify an OTP submitted by a patron |

Both endpoints read `service_ip` from the `X-Forwarded-For` request header (set automatically by nginx in production/docker). They return JSON.

## Local Docker Testing

**1. Add `otp_seed` to the dev config** (`conf/openlibrary.yml`):

```yaml
otp_seed: "dev-secret-seed"
```

**2. Start the stack:**

```bash
docker compose up
```

**3. Issue an OTP** (pass `sendmail=false` to skip SMTP in local dev):

```bash
curl -s -X POST http://localhost:8080/account/otp/issue \
  -H 'X-Forwarded-For: 1.2.3.4' \
  -d 'email=patron@example.com&ip=5.6.7.8&sendmail=false'
# → {"success": "issued"}
```

**4. Compute the expected OTP** (since email is not sent locally):

```bash
docker compose exec web python3 - <<'EOF'
from openlibrary.core.auth import TimedOneTimePassword as OTP
# Use the same service_ip, email, ip as the issue request
print(OTP.generate("1.2.3.4", "patron@example.com", "5.6.7.8"))
EOF
```

**5. Redeem the OTP:**

```bash
curl -s -X POST http://localhost:8080/account/otp/redeem \
  -H 'X-Forwarded-For: 1.2.3.4' \
  -d 'email=patron@example.com&ip=5.6.7.8&otp=<OTP_FROM_STEP_4>'
# → {"success": "redeemed"}
```

## Notes

- `service_ip` (from `X-Forwarded-For`) must match between issue and redeem requests.
- OTPs are valid for `VALID_MINUTES = 10` minutes (checked across rolling 1-minute windows).
- Rate limiting uses memcache: 1 request per TTL per client, max 3 attempts per email/ip globally.
- `verify_service` (challenge URL verification) is intentionally disabled — Open Library cannot make outbound requests to verify endpoints due to WAF/proxy restrictions.
