# BookReader

> **Status:** partial
> **Sources:** `raw/openlibrary-pages/dev_docs_bookreader.json`, `raw/openlibrary-pages/dev_docs_bookurls.json`, code synthesis (`openlibrary/plugins/upstream/borrow.py`)
> **Last ingested:** 2026-06-27
> **GitHub:** GH #10096 (HMAC upgrade — open), GH #12500 (OAuth PKCE migration — open)

BookReader is an Internet Archive–developed book reading UI in a standalone repo (`github.com/internetarchive/bookreader`). Open Library does not host BookReader — it redirects users to archive.org where BookReader runs. OL's role is to generate auth tokens and construct the redirect URL.

---

## How It Works

### For a freely available (public domain) book

OL redirects to:
```
https://archive.org/stream/{ocaid}?ref=ol
```
No auth token required. BookReader streams page images directly from IA's image server.

### For a borrowed (in-library) book

OL generates a signed auth link via `make_bookreader_auth_link()` in `borrow.py` and redirects the user there:

```
https://archive.org/bookreader/BookReaderAuth.php?
  uuid={loan_key}
  &token={10-min HMAC token for book}
  &id={ocaid}
  &bookPath={book_path}
  &iaUserId={ia_userid}
  &iaAuthToken={2-min HMAC token for user}
```

`BookReaderAuth.php` on archive.org validates the token and starts the BookReader session.

---

## HMAC Token Generation

`borrow.py::make_ia_token(item_id, expiry_seconds)`:

```python
timestamp = int(time.time() + expiry_seconds)
token_data = f"{item_id}-{timestamp}"
token = f"{timestamp}-{HMAC-MD5(config.ia_access_secret, token_data)}"
```

| Token type | Expiry | Used for |
|-----------|--------|---------|
| Book token | 10 min (`BOOKREADER_AUTH_SECONDS`) | Access to the book's page images |
| User token | 2 min (`READER_AUTH_SECONDS`) | IA user identity verification |

**BookReader polls OL periodically for fresh tokens** — the session stays alive as long as the user keeps reading.

⚠️ UNVERIFIED — GH #10096 notes the HMAC uses MD5 (`hashlib.md5`) and should be upgraded to a stronger hash. The issue is open and blocked.

`config.ia_access_secret` lives in olsystem (not in the repo). See [[infrastructure]].

---

## Page Image Serving

Page images are served by IA's image server, not OL:

1. During scanning, each page is captured as JPEG2000, stored in `{ocaid}_jp2.zip` on archive.org
2. Page dimensions and display/skip metadata are in `scandata.xml` per book
3. `BookReaderImages.php` on archive.org performs on-the-fly JPEG2000 → JPEG conversion and scaling
4. BookReader maps "page index" → "leaf number" via `scandata.xml` (some pages are marked do-not-display — color cards, blank pages)

⚠️ UNVERIFIED — Exact HTTP request BookReader makes per page turn (endpoint, params) not found within search budget. See `getPageURI()` in `github.com/internetarchive/bookreader`.

---

## URL Format

BookReader URLs use a key-value fragment format. Canonical order: `page` → `mode` → `highlight`:

```
https://archive.org/stream/{ocaid}#page/23/mode/2up/highlight/20,20,30,500
```

User-supplied URLs are remapped to canonical order via redirect. Unknown key-value pairs are ignored (forward-compatible).

Page references: `page/23` (number), `page/iv` (Roman), `page/title` (named). Modes: `1up`, `2up`, `thumb`.

---

## Embedding

```html
<iframe src="https://archive.org/stream/{ocaid}?ui=embed" width="480px" height="480px"></iframe>
<!-- link to specific page in 2-up: -->
<iframe src="https://archive.org/stream/{ocaid}?ui=embed#mode/2up/page/18" ...></iframe>
```

⚠️ UNVERIFIED — How OL's work/edition pages construct the "Read" button was not fully traced within search budget. Entry point: `openlibrary/macros/databarWork.html` → `borrow.py::get_bookreader_stream_url()`.

---

## Key Files

| File | Purpose |
|------|---------|
| `openlibrary/plugins/upstream/borrow.py` | HMAC token generation, auth link, loan lifecycle |
| `openlibrary/macros/databarWork.html` | Work page "Read" button — stream URL construction |
| `openlibrary/core/lending.py` | Loan state, IA availability queries |
| `github.com/internetarchive/bookreader` | Standalone JS reader (not in OL repo) |

---

## What's Broken / Fragile

- **GH #10096 (open):** HMAC uses MD5 — should be upgraded. Currently blocked.
- **GH #12500 (open):** Long-term migration to OAuth PKCE instead of HMAC shared-secret.
- **Token expiry during outage:** If OL goes down while a user reads, the token eventually expires with no graceful degradation.
- **`ia_access_secret` rotation:** If the secret rotates, all active BookReader sessions break immediately.

---

## Common Confusion

- **OL does not host BookReader** — the reader UI and all page images live on archive.org. OL only provides the auth token and redirect.
- **Two tokens, two expiries** — the book token (10 min) and user token (2 min) serve different purposes; BookReader must poll OL before the shorter one expires.

---

## Dependencies

**Depends on:**
- [[lending]] — loan lifecycle, HMAC secret management, availability check
- [[infrastructure]] — `ia_access_secret` in olsystem; archive.org hosts BookReader and image server
- [[auth]] — user identity (`ia_userid`) embedded in the auth link

**Depended on by:**
- [[lending]] — BookReader is the reading UI for all borrowed books
- [[features]] — reading progress, bookmarks within BookReader

---

*Sources: `dev_docs_bookreader.json`, `dev_docs_bookurls.json`, `borrow.py` · GH #10096, #12500 · See [[README]] · [[METHODOLOGY]]*
