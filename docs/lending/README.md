# Lending System

> **Status:** partial
> **Sources:** code synthesis (`openlibrary/core/lending.py`, `openlibrary/core/waitinglist.py`, `openlibrary/plugins/upstream/borrow.py`, `openlibrary/book_providers.py`)
> **Last ingested:** 2026-06-27 · **Corrected:** 2026-08-29 (verified against `aced0c079`, origin/master 2026-08-28)
> **History:** see [[history]] — where this system came from and what each migration left behind

OL's lending system manages controlled digital lending (CDL) of books from the Internet Archive collection. The actual loan state, waiting list state, and S3 authentication all live on archive.org's servers — OL is the front-end orchestrator: it checks eligibility, calls IA's loan API, and redirects users to BookReader.

**This was not always true, and the code shows it.** OL was the system of record for lending from 2010 until November 2014. Much of `lending.py` is machinery from that era, or from the incomplete migrations since. OL currently talks to archive.org through **two different loan APIs simultaneously** — the modern `s3_loan_api` and the 2014-era `openlibrary.php` shim (`IA_Lending_API`). Read [[history]] before changing anything here; most of what looks arbitrary is dated.

---

## Pages in this directory

| Page | What it covers |
|---|---|
| **README** (this page) | How lending works today: access states, the borrow flow, availability, authentication, configuration. |
| [[history]] | Why the code looks the way it does — six eras, what each left behind, and how to tell a live path from a fossil. |
| [[acquisitions]] | Where a provider's acquisition links are stored, how they reach Solr and the book page, and the consumer contract. |
| [[lenny]] | Borrowing from a Lenny node over OAuth 2.0 — the flow, its design assumptions, and a response playbook. |

## Book Access States

`EbookAccess` enum (in `book_providers.py`) — kept in sync with `solr/conf/enumsConfig.xml`:

| Value | Meaning | What the user sees |
|-------|---------|-------------------|
| `NO_EBOOK` (0) | No digital copy exists | No "Read" button |
| `UNCLASSIFIED` (1) | Access type unknown | Depends on further lookup |
| `PRINTDISABLED` (2) | Print-disabled preview only | Sample preview available |
| `BORROWABLE` (3) | In-library borrowable (CDL) | "Borrow" button |
| `PUBLIC` (4) | Public domain / open access | "Read" button, no auth |

`AvailabilityStatus` (from the IA Availability API v2) maps to loan state:

| `status` | Meaning |
|---------|---------|
| `open` | Publicly readable (no loan needed) |
| `borrow_available` | Borrowable, currently available |
| `borrow_unavailable` | Borrowable, all copies checked out |
| `error` | Availability service error |

Additional booleans: `available_to_browse`, `available_to_borrow`, `available_to_waitlist`, `is_printdisabled`, `is_lendable`, `is_restricted`.

---

## Borrow Flow (End-to-End)

When a user clicks "Borrow" on an edition page:

1. **`POST /books/{key}/borrow`** → `borrow.py::borrow.POST()`
2. Checks if it's an open-access book → redirect to archive.org stream directly (no loan needed)
3. Calls `lending.get_availability("identifier", [edition.ocaid])` → checks IA Availability API v2 (Memcached, 5 min TTL)
4. Verifies user is logged in + has IA S3 credentials (from `openlibrary/accounts/model.py`)
5. Checks `user_can_borrow_edition(user, edition)` → returns `"borrow"` or `"browse"` or `False`
6. Calls `lending.s3_loan_api(s3_keys, ocaid=edition.ocaid, action="borrow_book")` → POSTs to `https://archive.org/services/loans/loan/`
7. IA creates the loan record on their side; OL gets confirmation
8. OL calls `make_bookreader_auth_link(loan["_key"], edition.ocaid, bookPath, ia_userid=ia_itemname)` → HMAC tokens + redirect URL
9. **Redirects user** to `https://archive.org/bookreader/BookReaderAuth.php?...` — see [[bookreader]] for token details

**Loan duration:** 14 days (`BOOKREADER_LOAN_DAYS = 14`)

**Fulfillment timeout:** 5 minutes (`LOAN_FULFILLMENT_TIMEOUT_SECONDS`) — if loan is created but not fulfilled (no expiry set) within 5 minutes, it's treated as abandoned

---

## Waiting List

When all copies are checked out, users join the waiting list via `POST /books/{key}/borrow?action=join-waitinglist`.

**WaitingLoan document structure** (stored in OL/IA store):
```json
{
  "_key": "waiting-loan-OL123M-anand",
  "type": "waiting-loan",
  "user": "/people/anand",
  "book": "/books/OL123M",
  "status": "waiting",
  "since": "2013-09-16T06:09:16.577942",
  "last-update": "2013-10-01T06:09:16.577942"
}
```

Status flow: `waiting` → `available` (when a slot opens) → deleted (when patron borrows or expires)

**Slot opens → notification: this path is DEAD CODE in Open Library.**

> Corrected 2026-08-29. This page previously described the chain below as live. It is not —
> `on_waitinglist_update()` has **zero callers** anywhere in the repo, which makes
> `sendmail_book_available()` unreachable, since that is its only caller. If patrons receive
> "your book is available" mail, **archive.org sends it**, not OL. Do not reason about OL's
> waitlist notification behaviour from this code. See [[history]] (Era 2 fossils).

The dead chain, for reference when removing it:
1. `waitinglist.on_waitinglist_update(identifier)` — **entry point, never called**
2. → `lending.is_loaned_out(identifier)`
3. → if free and people are waiting, `sendmail_book_available(book)` — **unreachable**
4. `available_email_sent=True` was the once-only guard
5. `expiry` on the WaitingLoan was the borrow window

Also orphaned in the same module: `update_all_ebooks()` (zero callers) and
`WaitingLoan.prune_expired()` (zero callers, and its body is a bare `return`).

**Waiting list operations — split across two APIs:**

| Operation | Transport |
|---|---|
| Join (`action="join_waitlist"`) | `s3_loan_api` — modern |
| Leave (`action="leave_waitlist"`) | `s3_loan_api` — modern |
| `WaitingLoan.query()` (read, sorted by `since`) | `IA_Lending_API` → `openlibrary.php` — 2014-era shim |
| `WaitingLoan.update()` / `.delete()` | `IA_Lending_API` → `openlibrary.php` — 2014-era shim |

Writes go through the new service; reads still go through the old shim.

---

## Availability API

`lending.get_availability(id_type, ids)` — primary availability lookup:
- Calls IA's Availability API v2 (`config_ia_availability_api_v2_url`)
- `id_type`: `"identifier"` (ocaid), `"openlibrary_work"`, or `"openlibrary_edition"`
- Cached in Memcached for 5 minutes
- Returns `dict[str, AvailabilityStatusV2]`

`get_groundtruth_availability(ocaid)` — "ground truth" check, bypasses some caching:
- Hits `https://archive.org/services/loans/loan/?action=availability&identifier={ocaid}`
- Result cached in Memcached for 5 minutes separately

`EBookRecord` — OL's local shadow of loan state:
- Stored in OL store as `"ebooks/{ocaid}"`
- Fields: `borrowed` (string "true"/"false"), `wl_size` (waitlist count), `loan` (loan data)
- Updated by `sync_loan()` after any loan state change
- Used to detect when a loan was completed on IA without OL knowing

---

## Near-realtime Loan Availability in Solr (PR #12689 / issue #7450)

> Added 2026-07-29. Reduces OL's per-request dependency on IA's availability service by pushing loan status into Solr so search/carousels can read it directly. In progress; not yet merged.

A standalone poller, `scripts/solr_updater/loan_availability_updater.py`, runs as a **backgrounded process inside the `solr-updater` container** (via `docker/ol-solr-updater-start.sh`, alongside `solr_updater.py` and `trending_updater.py`) — **not** the web app. It polls IA's loan-changes API and writes borrowing status onto Solr **edition** documents within ~30s.

- **Changes API:** `lending.get_loan_changes(after_uid, limit)` → `GET services/loans/loan/?action=changes&after_uid=N&limit=N` (S3-authed). URL resolves as `config_ia_s3_loan_url or (S3_LOAN_URL % config_bookreader_host)`.
- **New Solr fields** (`managed-schema.xml`, on edition docs): `ebook_availability` (pint, 0=unavailable/1=available), `ebook_becomes_available` (plong, epoch), `loan_uid` (plong cursor). All `indexed=false stored=false docValues=true`.
- **Edition-level, not work-level:** editions are **nested child docs** of works (block-join, `_root_` = parent work key). A loan is per-ocaid, so updates target the edition child and leave sibling editions + the parent work untouched.
- **In-place atomic updates:** `Solr.update_in_place()` → `POST /update?update.partial.requireInPlace=true`. Requires numeric fields (string/pdate are rejected HTTP 400); a non-in-place atomic update to a nested child would reindex the whole work + all editions. `requireInPlace` is a query param, not a solrconfig chain.
- **Cold start:** state file → else `max(loan_uid)` in Solr → else binary-search ~14 days back (`LOAN_MAX_AGE_DAYS`, the max loan lifetime). **Eviction safety net** runs each cycle: flips expired-but-still-unavailable editions back to available (Solr rejects `"set": null`, so `ebook_becomes_available` is never cleared — only meaningful when `ebook_availability==0`).

**Dev vs prod config:** dev points `ia_s3_loan_url` at `http://mockservices:8090/...` (`conf/openlibrary.yml`). **`mockservices` is dev-only** and must never appear in prod; olsystem provides its own config and, omitting `ia_s3_loan_url`, falls back to real archive.org. Production run/deploy is olsystem + Jenkins (out of the repo).

### Testing loan availability locally (verified working 2026-07-29)

- **Schema-change gotcha:** the OL Solr startup guard (`ol-local-solr-start`) diffs the mounted schema against the schema baked into the persisted `solr-data` volume and **refuses to start (exit 1) on any drift**. After changing `managed-schema.xml` you must drop the volume: `docker compose down && docker volume rm <project>_solr-data <project>_solr-updater-data && docker compose up -d solr`.
- **Tier A (Solr mechanics):** `docker compose up solr` → `python3 scripts/test_harness_e2e.py` (host-only, hits Solr directly). Proves nested-doc in-place writes, edition isolation, eviction, state recovery. (Harness hardcodes `localhost:8984`; compose defaults host `SOLR_PORT=8983`, so bring up with `SOLR_PORT=8984`.)
- **Tier B (full loop):** seed editions with `ia` ids → `docker compose up mockservices` (it seeds 14d of loan events from **real `ia` ids read out of Solr**; falls back to a static pool that does *not* correspond to real editions on an empty index) → run the updater against it. Confirmed: mockservices → `get_loan_changes` → resolve → in-place → Solr reflects availability, updated within a poll cycle.
- **Confirmed on real Solr:** `indexed=false docValues=true` numeric points fields *are* queryable/sortable (range + exact term via docValues) and returnable in `fl` (useDocValuesAsStored) — no OL precedent, but it works.

### Known sharp edges (as of 2026-07-29, tracked)

- `--reset` is defeated by `query_solr_uid()`: a stale high `loan_uid` in Solr resumes from there instead of binary-searching, contrary to the docstring.
- A live full reindex while the updater runs silently reverts pre-reindex active loans (only restart/`--reset` reconstructs).
- No `_version_` optimistic concurrency → a concurrent work reindex can clobber an in-place loan write.
- Loans for not-yet-indexed editions are dropped, not retried.
- Nothing consumes these fields for display/search yet.

---

## S3 Keys and Authentication

Each patron's IA S3 credentials are stored in OL's account model. The `LOW s3access:s3secret` pair authenticates the patron directly against IA's loan API — OL never proxies the actual content, only the auth handshake.

The `ia_ol_metadata_write_s3` config key provides OL's own S3 credentials for API calls that aren't user-attributed (e.g. availability lookups with an authorization header).

Both types of S3 credentials live in olsystem (not in the repo).

---

## Key Files

| File | Purpose |
|------|---------|
| `openlibrary/core/lending.py` | Core: availability API, loan creation, sync, loan state |
| `openlibrary/core/waitinglist.py` | Waiting list — join, leave, notify, expiry |
| `openlibrary/plugins/upstream/borrow.py` | HTTP handlers: `POST /books/{key}/borrow`; HMAC token generation |
| `openlibrary/book_providers.py` | `EbookAccess` enum; `get_book_provider()`; IA vs. non-IA book detection |
| `openlibrary/tests/core/test_lending.py` | Unit tests for lending.py |
| `openlibrary/tests/fastapi/test_account_loans.py` | FastAPI loan endpoint tests |
| `openlibrary/plugins/upstream/models.py` | `Edition.get_available_loans()`, `User.update_loan_status()` — the hot paths |
| `openlibrary/plugins/openlibrary/borrow_home.py` | `loan-created`/`loan-completed` eventer hooks → `core/statsdb.py` |
| `openlibrary/views/loanstats.py` | `/stats/lending` (tombstoned), `/stats/readinglog`, `/trending` |
| `scripts/solr_updater/loan_availability_updater.py` | Near-realtime loan availability poller (in progress) |

---

## Configuration

All config loaded via `lending.setup(config)`:

| Key | Purpose |
|-----|---------|
| `ia_loan_api_url` | IA loan API endpoint |
| `ia_availability_api_v2_url` | IA Availability API v2 URL |
| `ia_access_secret` | HMAC secret for BookReader token generation |
| `ia_ol_shared_key` | OL/IA shared API key |
| `ia_ol_metadata_write_s3` | OL's S3 credentials for availability lookups |
| `bookreader_host` | `archive.org` (or override for dev) |

All secrets live in olsystem. See [[infrastructure]].

---

## What's Broken / Fragile

> Expanded and verified 2026-08-29 against `aced0c079` (origin/master). Each item below was read in the source, and
> callers were counted. Items marked **verified** were confirmed by reading the code path end to end.

### Redundant network calls on the loan-status path

**`get_loan()` calls archive.org twice and throws the first answer away** — *verified*,
`openlibrary/core/lending.py:634-644`:

```python
try:
    _loan = _get_ia_loan(identifier, account and userkey2userid(account.username))
except Exception:
    logger.exception(f"get_loan({identifier}) 1 of 2")
try:
    _loan = _get_ia_loan(identifier, account and account.itemname)   # clobbers the first
except Exception:
    logger.exception(f"get_loan({identifier}) 2 of 2")
return _loan
```

The second assignment unconditionally overwrites the first, so the first POST is pure waste whenever the
second succeeds. Worse: when `user_key is None` (the common case — `is_loaned_out_on_ol()` calls it that
way), `account` is `None`, so **both calls are byte-identical**: the same POST to `openlibrary.php`, twice,
back to back.

**The OL-store read in the same function is also discarded** — *verified*, `lending.py:628-633`. `d` is
fetched from the store and wrapped in a `Loan`, but `loan` is never returned; it only affects control flow
if the loan is expired. Era-1 residue (see [[history]]).

**`is_loaned_out()` costs three round-trips to answer one boolean** — *verified*, `lending.py:589-594`:
`is_loaned_out_on_ol()` (2 identical POSTs, per above) `or` `is_loaned_out_on_ia()` (1 GET to
`services/borrow/{id}?action=status`). None of the three is cached.

**`Edition.get_available_loans()` makes that four** — *verified*,
`openlibrary/plugins/upstream/models.py:177-192`. It calls `lending.is_loaned_out(ocaid)` (3 calls) and
then `_get_available_loans()` → `borrow.is_loaned_out("bookreader:"+ocaid)`, which on a store miss calls
`lending.is_loaned_out_on_ia(identifier)` — **the same GET that was just issued**. Four uncached HTTP
round-trips to archive.org, three of them redundant.

### N+1 on the loans page

> The clearest single illustration of the whole problem: **`/account/loans` calls both eras in one
> request.** The *active loans* table is fetched by `get_loans_of_user()` → OL local store +
> `IA_Lending_API.find_loans()` → `openlibrary.php` (2014). The *loan history* table right beneath it is
> fetched by `get_loan_history_data()` → `s3_loan_api(action="user_borrow_history")` (2020). Same page,
> same request, two generations of transport. Credit to Nilax for spotting this pairing.

**`User.update_loan_status()` is O(N) in network calls and runs before every loan read** — *verified*,
`models.py:887-891` on master:

```python
def update_loan_status(self):
    loans = lending.get_loans_of_user(self.key)   # uncached
    for loan in loans:
        lending.sync_loan(loan["ocaid"])          # <-- has the Loan, passes only the ocaid
```

Three compounding costs, all avoidable:

1. **The Loan object is discarded.** `sync_loan(identifier, loan=NOT_INITIALIZED)` takes an optional
   `loan`; when it isn't passed, `sync_loan` calls `get_loan(identifier)` to re-fetch what the caller
   already had — and `get_loan()` costs **two** POSTs (see above). So each loan costs 2 needless
   round-trips.
2. **Availability is fetched one loan at a time.** `sync_loan()` calls
   `get_availability("identifier", [identifier])` with a single-element list, though the function and the
   underlying API are both batch-capable (`ids: list[str]`).
3. **The whole list is then fetched a second time.** `/account/loans` (`account.py`) calls
   `user.update_loan_status()` and then `docs = get_loans_of_user(user.key)`. `User.get_loans()` does the
   same pairing.

Net: a patron with N active loans costs roughly `2 + N×(2 loan POSTs + 1 availability call)` external
requests to render one page — **per-request work scales with the patron's loan count.**

**The documented 5-minute loan cache is mostly bypassed** — *verified*. `get_cached_loans_of_user` has
exactly **one** caller (`core/models.py:1082`, and only when `use_cache` is true). The uncached
`get_loans_of_user` is called directly from `models.py` (×2), `mybooks.py`, `account.py`, and
`borrow.py:374`.

### Missing timeouts and swallowed errors

**`s3_loan_api()` carries a timeout.** The borrow hot path calls `s3_loan_api_async()`, which posts
through `ia.get_async_session()` with `timeout=config_http_request_timeout`; the synchronous name is
`async_bridge.wrap(s3_loan_api_async)`. Checkouts predating the 2026-08 async migration have an
untimed `requests.post` here instead, so verify against `origin/master` rather than a local tree.

**`sync_loan()` raises on an empty availability response** — *verified*, `lending.py:749-767`.
`num_waiting` is assigned only inside `if response:`, but `kwargs` unconditionally reads both
`response["status"]` and `num_waiting`. When the availability lookup returns empty, `response` is `{}` and
`response["status"]` raises `KeyError` — and this happens *before* the `try` block, which only wraps
`ebook.update()`. So an availability blip propagates an exception out of `sync_loan()` into every caller.

**Broad `except Exception`** in `get_availability_async` — errors swallowed; a bad IA response silently
returns `{}` for all IDs. (Carried over; still true. The `# TODO: Narrow exception scope` comment appears
**7 times** in `lending.py`.)

### Suspected logic inversion

**`borrow.is_loaned_out()` looks inverted** — *unverified, needs a second pair of eyes*,
`openlibrary/plugins/upstream/borrow.py:415`:

```python
return bool(loan and datetime_from_isoformat(loan["expiry"]) < datetime.utcnow())
```

This returns `True` when the loan's expiry is **in the past** — i.e. reports "loaned out" precisely when
the loan has *expired*. Read plainly that is backwards. The line predates 2016-10-15 (`2de55db1d`) and has
only been touched by formatting since, so if it is a bug it is a long-lived one, and something may depend
on the current behaviour. **Do not flip it without tracing callers.**

### Dead code

An inventory of zero-caller symbols, with the era each belongs to, is in [[history]].

### Structural

- **Two loan APIs are live at once** — `s3_loan_api` (2020) for writes, `IA_Lending_API`/`openlibrary.php`
  (2014) for all loan reads and all waitlist reads. See [[history]] Era 5.
- **Sync/async twins** — `get_available`, `get_availability`, `add_availability` each exist as an
  `async def` plus an `async_bridge.wrap()` alias. This has already caused a production deadlock
  (`49b1e4021`, 2026-08-21). Two `/borrow` endpoints (web.py + FastAPI) also coexist.
- **`is_loaned_out_on_ol`** — checks OL's local store, which can drift from IA's state. `sync_loan()` is
  the reconciliation mechanism, but it's called opportunistically (not scheduled).
- **Legacy ACS** — `Loan.new()` is typed `Literal["bookreader"]` yet still carries an `else: raise` branch
  for ACS, which the type forbids. The whole `resource_type`/`resource_id` abstraction has one value.
- **Waiting list expiry not enforced** — `prune_expired()` is a stub. Expired waiting loans must be
  cleaned up on the IA side or they pile up.
- **`waitingloan` table** still declared in `core/schema.py`; all writes to it are commented out in
  `waitinglist.py`. Moved to IA in 2014.

---

## Common Confusion

- **OL does not store loans** — all canonical loan records are on archive.org. OL's `store["loan-{ocaid}"]` entries are OL-originated loans only; IA-originated loans come back via `ia_lending_api.get_loan()`.
- **`borrow_book` vs `browse_book`** — "borrow" = 14-day checkout; "browse" = 1-hour browse (same endpoint, different `action` param to IA's loan API). `user_can_borrow_edition()` determines which the user gets.
- **Availability v2 vs ground-truth** — `get_availability()` hits the v2 API (cached, fast). `get_groundtruth_availability()` hits a different endpoint with fresher data but slightly higher latency. Both exist; ground-truth is a "stopgap" — one dating from 2016, see [[history]] Era 3.
- **`s3_loan_api` vs `ia_lending_api`** — these are two *different transports to archive.org*, not two layers. `s3_loan_api` (2020) is a REST service authenticated with the patron's own S3 keys; `ia_lending_api` (2014) is an RPC-style POST to `openlibrary.php` authenticated with OL's shared token. Both are live. If you are adding a call, use `s3_loan_api`.
- **Four endpoints answer "is this on loan?"** — `openlibrary.php` (`loan.query`), `services/loans/loan/?action=availability`, `services/borrow/{id}?action=status`, and the bulk availability v2 API. They have different freshness, caching, and failure modes.

---

## Dependencies

**Depends on:**
- [[infrastructure]] — IA loan API, IA S3, `ia_access_secret` in olsystem; Memcached for availability cache
- [[auth]] — user S3 keys come from OL account model; `ia_itemname` identifies patron to IA
- [[bookreader]] — lending hands off to BookReader via HMAC auth link after loan is created

**Depended on by:**
- [[bookreader]] — BookReader needs a valid loan + HMAC token to start a session
- [[features]] — reading log, reading goals reference loan state

**See also:**
- [[history]] — the migration history; why this code looks the way it does, and what each era left behind

---

*Sources: `lending.py`, `waitinglist.py`, `borrow.py`, `book_providers.py` (code synthesis) · See [[README]] · [[METHODOLOGY]]*

---
