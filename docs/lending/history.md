# Lending: history and archaeology

Why the lending code looks the way it does. Six eras left overlapping mechanisms in place; this page names each one and what it left behind, so that a reader can tell a live path from a fossil.

> Part of [Lending](README.md).

> **Status:** verified
> **Sources:** git history of `internetarchive/openlibrary` (279 commits touching `openlibrary/core/lending.py` alone), read against `aced0c079` (origin/master, 2026-08-28)
> **Last ingested:** 2026-08-29
> **See also:** [[lending]] for the current-state reference

This page exists because the lending code cannot be understood from its current state alone. Open Library
*was* the lending platform in 2010; almost everything since has been migration away from that, and each
migration left something behind. Nearly every oddity in `lending.py`, `borrow.py`, and `waitinglist.py` is
a fossil of a specific era. This page names the eras so the fossils are legible.

**The one-line version:** OL went from *system of record* → *shim over IA's database* → *thin client of IA's
S3 loan service*. The code still contains working machinery from all three, and OL currently talks to
archive.org through **two different loan APIs at once**.

---

## Era 1 — Open Library *is* the lending platform (2010-06 → 2014-10)

Lending shipped in June 2010. `openlibrary/plugins/upstream/borrow.py` is one of the oldest continuously
living files in the repo; its first commits are from **2010-06-17** (`62c6edde4`, "Add handler for e.g.
`/books/OL1M/Title/borrow`").

In this era OL owned everything:

- **Loans lived in OL's own infobase store** as `/type/loan` documents keyed `loan-{ocaid}`.
- **Waiting lists lived in an OL Postgres table**, `waitingloan` (still declared in `openlibrary/core/schema.py`).
- **Fulfillment was Adobe Content Server 4 (ACS4).** OL minted `.acsm` files and handed them to Adobe
  Digital Editions — `acee45727` (2010-06-24), "Support for getting loan status from the status server and
  generating loan offer URLs via ACS4… you must run `git submodule update --init` to pick up the acs4_py
  module." A vendored `acs4_py` submodule lived in the repo.
- **Overdrive was a second provider** alongside ACS (`93ffe3f4a`, "can_borrow and overdrive_id functions").

Two constants still in `lending.py` are from these first two weeks and have never changed:

| Constant | Set in | Commit |
|---|---|---|
| `LOAN_FULFILLMENT_TIMEOUT_SECONDS = 5 min` | 2010-06-27 | `a1479c458` "Decrease length of loan offer timeout to 5 minutes" |
| `BOOKREADER_LOAN_DAYS = 14` | 2010 era | — |

The 5-minute fulfillment timeout exists because ACS4/ADE could issue a loan offer and never have the reader
pick it up. There is no ADE anymore, but the timeout is still enforced.

**Left behind:** the `waitingloan` table in `schema.py`; `/type/loan` store documents; the "unfulfilled loan
= `expiry is None`" convention, which `Loan.from_ia_loan()` still carries a comment about ("For historic
reasons, OL considers expiry == None as un-fulfilled loan").

---

## Era 2 — The database moves to archive.org; `openlibrary.php` is born (2014-10 → 2014-11)

Over about six weeks in autumn 2014, the system of record moved to IA. The commit sequence is unusually
clean:

| Date | Commit | What |
|---|---|---|
| 2014-10-06 | `b27030379` | **Waiting Lists are moved to IA database** |
| 2014-10-08 | `0dec44e4c` | Lending refactor step 1 — consolidate "is it loaned out" into `core/lending.py` |
| 2014-10-21 | `84bea2483` | Lending refactor step 2 — move more lending functions into `core/lending.py` |
| 2014-10-27 | `c0aed2536` | Lending refactor step 3 — first steps towards moving loans to IA |
| 2014-11-06 | `7f78a7841` | **Switched to storing OL loans on archive.org database** |

Follow-ups over the next weeks are all reconciliation problems appearing for the first time: `7cd42eb5e`
"Don't save IA loans to OL", `cf7fadbca` "Delete expired loans that are stored in OL", `ec22285be` "Log
errors in sync_loan instead of crashing", `02749204c` "Disabled updating WL status".

**The shim.** The transport for this era is a PHP endpoint on petabox — `openlibrary.php` — reached by
POSTing an RPC-style `method` parameter (`loan.query`, `loan.create`, `loan.delete`, `waitinglist.join`,
`waitinglist.leave`, `waitinglist.query`, `waitinglist.update`). In the code this is the class
**`IA_Lending_API`** at the bottom of `lending.py`. Its `_post()` still names the endpoint in an error
string:

```python
except JSONDecodeError:
    logger.exception("POST failed to openlibrary.php, no json")
```

Its class docstring says `"""Archive.org waiting list API."""`, which understates it by a decade — it
handles loans too.

**`sync_loan` and `EBookRecord` are artifacts of this era specifically.** Once IA owned the loan records,
OL had no way to learn that a loan had ended. The workaround was to keep a local shadow copy
(`store["ebooks/{ocaid}"]`) and detect deletions by comparing loan ids. `sync_loan()`'s own docstring says
so: *"There is no way for OL to know when a loan is deleted. To handle that situation, the loan info is
stored in the ebook document and the deletion is detected by comparing the current loan id and loan id
stored in the ebook."* That entire mechanism is a 2014 polling workaround for a push problem.

**Left behind:** `IA_Lending_API` (still live — see Era 5); `sync_loan()`; `EBookRecord`; the OL-store loan
lookups that still run alongside the IA calls.

---

## Era 3 — Availability gets its own service (2016-12 → 2017-09)

Reading loan state per-book was too slow for carousels and search results, so a bulk **availability API**
appeared, separate from the loan API. This was a performance migration, not a correctness one.

| Date | Commit | What |
|---|---|---|
| 2016-12-03 | `30207fb9a` | Checking availability of popular books via a staging archive.org availability API |
| 2016-12-06 | `b54f25680` | Point at the production availability service |
| 2016-12-12 | `35afef88c` | "fixing book availability to meet performance requirements" |
| 2017-01-12 | `a07d70554` | REST API + JS frontend for site-wide availability check on pageload |
| 2017-09-09 | `f8c1ae92f` | Replace the slow popular-books carousel with performant staff picks |
| 2017-09-09 | `437f1d49f` | **Migrate carousels to availability v2** |

This is why availability and loan state are two unrelated code paths that answer overlapping questions, and
why `get_availability()` (v2, cached, bulk) and `get_groundtruth_availability()` (single-item, fresher)
both exist. The wiki's current note that ground-truth is a "stopgap" dates from here — it is a nine-year-old
stopgap.

**Left behind:** two availability paths with different cache keys and TTLs; `AvailabilityStatus` vs
`AvailabilityStatusV2` and the `update_availability_schema_to_v2()` adapter that converts between them.

---

## Era 4 — ACS is spun down (2017-12 → 2025-05, in four waves)

The longest tail in the system. Adobe DRM was removed over **seven and a half years**, in distinct waves,
which is why ACS references kept resurfacing long after "we removed ACS":

| Date | Commit | Wave |
|---|---|---|
| 2017-12-01 | `f61941152`, `80e7b0cba` | Remove ACS config logic from OL; add deprecation notes |
| 2020-03-04 | `a761787bc` | Remove the acs4 *dependency* from code |
| 2020-03-05 | `3db440f6e` | Remove the `vendor/acs4_py` *submodule* |
| 2025-05-19 | `202ef43a8` | Remove ACS code and configuration from `lending.py` (#10791) |
| 2025-05-28 | `7287f08b8` | Remove ACS code related to `borrow.py` (#10792) |
| 2026-04-30 | `d3a03e274` | Remove remaining ACS4 dead code from `lending.py`, `models.py`, `borrow.py` |
| 2026-05-01 | `9b6954e14` | Remove ACS4 tests; rename `TestEditionACS4Removal` → `TestEdition` |

**Left behind:** `Loan.new()` still takes a `resource_type` parameter typed `Literal["bookreader"]` and
still has an `else` branch that raises *"No longer supporting ACS borrows directly from Open Library.
Please go to Archive.org"* — a runtime guard for a case the type system already forbids. The concept of a
"resource type" at all is an ACS-era abstraction: there is exactly one resource type now, and
`resource_id` is always the string `"bookreader:" + ocaid`.

---

## Era 5 — S3 loan services (2020-06 → present)

In June 2020 patron-authenticated loan operations moved to a **REST service authenticated by the patron's
own IA S3 keys**, rather than OL acting as a trusted intermediary with a shared token.

| Date | Commit | What |
|---|---|---|
| 2020-06-11 | `b363e7090`, `88dcaf003` | **Enables browse borrowing by s3 keys** |
| 2020-06-17 | `58a09cba5` | Enables returning of 1h ("browse") or 2-week borrowable books |
| 2020-06-17 | `89de25ccb` | Fixing join/leave waitlist |

The new transport is `s3_loan_api()` — `POST https://{bookreader_host}/services/loans/loan/` with
`action=browse_book | borrow_book | return_loan`, carrying `{access, secret}` from the patron's account.
This is where the **1-hour browse** loan comes from; before 2020 there was only the 14-day borrow.

### The critical fact about Era 5: it never finished

`s3_loan_api()` and `IA_Lending_API` (the Era-2 `openlibrary.php` shim) are **both live today**, against the
same underlying loan data, split by operation:

| Operation | Path used | Era |
|---|---|---|
| Create a borrow/browse loan | `s3_loan_api(action="borrow_book"/"browse_book")` | 5 |
| Return a loan | `s3_loan_api(action="return_loan")` | 5 |
| Join / leave waitlist | `s3_loan_api(action="join_waitlist"/"leave_waitlist")` | 5 |
| **Read a loan** (`get_loan`, `find_loans`) | `ia_lending_api` → `openlibrary.php` | 2 |
| **Create/delete loan** (`create_loan`, `delete_loan`) | `ia_lending_api` → `openlibrary.php` | 2 |
| **All waitlist reads/updates** (`WaitingLoan.query`, `.update`, `.delete`) | `ia_lending_api` → `openlibrary.php` | 2 |
| Bulk availability | availability API v2 | 3 |
| Single-item ground truth | `services/loans/loan/?action=availability` | 3/5 |
| "Is it checked out" | `services/borrow/{id}?action=status` | ? (a fourth endpoint) |

So a single question — *is this book on loan, and to whom* — can be answered by four different
archive.org endpoints depending on which function you call. **This is the core of the "duplicative,
half-in-use" problem.**

**You can see both eras in a single HTTP request.** On `/account/loans`, the active-loans table comes from
`get_loans_of_user()` → OL local store + `openlibrary.php` (Era 2), while the loan-history table directly
below it comes from `get_loan_history_data()` → `s3_loan_api(action="user_borrow_history")` (Era 5). The
migration boundary runs straight through one page.

The migration was explicitly acknowledged but not executed: `a7fbdf095` (2026-04-30), *"Document
`IA_Lending_API` migration path to `s3_loan_api`"* — the path was written down, not walked.

**Also from this era:** the `openlibrary.php` name kept leaking to users. `e95331678` (2024-11-01) "fail
calls to `openlibrary.php` gracefully"; `b2d13dc11` (2026-04-30) "Fix misleading `openlibrary.php`
reference in error log."

---

## Era 6 — Cleanup and async (2026)

Three parallel threads in 2026, none complete:

**Legacy removal (2026-04-30):**
- `a07de70ac` / `e161071e2` — Remove legacy OL local-store loan query from `get_loans_of_user`
- `d3a03e274` — Remove remaining ACS4 dead code

**Async migration (2026-08):** availability calls became `async def` with sync wrappers generated by
`async_bridge.wrap()`:

```python
get_available    = async_bridge.wrap(get_available_async)
get_availability = async_bridge.wrap(get_availability_async)
add_availability = async_bridge.wrap(add_availability_async, "add_availability")
```

- `907052679` (2026-08-20) — Add a parallel FastAPI `/borrow` endpoint alongside the legacy web.py one
- `229b90362` (2026-08-20) — Make the `/borrow` helper and its httpx-backed lending calls async
- `49b1e4021` (2026-08-21) — **Fix borrow AsyncBridge deadlock with async lending twins and re-entrancy guard**

That third commit is the warning sign: the sync/async twinning has already produced a production deadlock.
There are now *two* `/borrow` endpoints (web.py and FastAPI) as well.

**Near-realtime availability in Solr (2026-07, in progress):** `scripts/solr_updater/loan_availability_updater.py`
— pushes loan status into Solr so carousels and search can read it without calling IA per request. This is
the first attempt to fix the Era-3 performance problem at its root. Not merged; see [[lending]] for detail.

---

## Fossils: what each era left in the code

Verified against `aced0c079` (origin/master, 2026-08-28). Everything here is present *today*.

| Fossil | Era | Status |
|---|---|---|
| `waitingloan` table in `core/schema.py` | 1 | Table declared; all writes commented out in `waitinglist.py` |
| `/type/loan` store docs, `loan-{ocaid}` | 1 | Still read by `get_loan()` and `borrow.get_loan_key()` |
| `LOAN_FULFILLMENT_TIMEOUT_SECONDS = 5 min` | 1 (ACS/ADE) | Still enforced; the reader it protected is gone |
| `Loan.new()` — the whole method | 1/4 | **Zero callers.** Its ACS `else: raise` branch is doubly dead (param is `Literal["bookreader"]`) |
| `resource_type` / `resource_id` abstraction | 1/4 | One value only: `"bookreader:" + ocaid` |
| `IA_Lending_API` / `openlibrary.php` | 2 | **Live** — all loan reads and all waitlist ops |
| `sync_loan()` + `EBookRecord` shadow | 2 | Live; a polling workaround for a push problem |
| `waitinglist.on_waitinglist_update()` | 2 | **Zero callers** |
| `waitinglist.sendmail_book_available()` | 2 | Only reachable from the above — **unreachable** |
| `waitinglist.update_all_ebooks()` | 2 | **Zero callers** |
| `WaitingLoan.prune_expired()` | 2 | Body is `return` — a stub with zero callers |
| Two availability paths + v1→v2 adapter | 3 | Both live |
| `borrow.is_loaned_out_from_status()` | ? | **Zero callers** |
| `views/loanstats.py::lending_stats` | ? | Route registered; handler body is `raise web.seeother("/")` |
| `scripts/fake_loan_server.py` | ? | **Zero references** anywhere in the repo |
| `static/css/legacy-borrowTable-adminUser.css` | 1 | Name says it |
| `openlibrary.php` string in a user-facing log | 2 | Fixed twice (2024, 2026); the endpoint remains |

**The waiting-list finding deserves emphasis:** the chain
`on_waitinglist_update()` → `is_loaned_out()` → `sendmail_book_available()` is how OL is *documented* to
notify the next patron in a queue, and it is **dead code** — nothing calls the entry point. If patrons are
being emailed when a book becomes available, archive.org is sending those mails, not Open Library. The
[[lending]] page previously described this chain as live; that has been corrected.

---

### Zero-caller symbols, with locations

| Symbol | Location |
|---|---|
| `on_waitinglist_update()` | `core/waitinglist.py:213` |
| `sendmail_book_available()` | `core/waitinglist.py:237` — only reachable from the above |
| `update_all_ebooks()` | `core/waitinglist.py:264` |
| `WaitingLoan.prune_expired()` | `core/waitinglist.py:139` — body is a bare `return` |
| `is_loaned_out_from_status()` | `plugins/upstream/borrow.py:417` |
| `scripts/fake_loan_server.py` | whole file — no references anywhere |
| `lending_stats` route | `views/loanstats.py:144` — handler body is `raise web.seeother("/")` |

## How to read the code with this history in hand

- **If a function talks to `ia_lending_api`, it is Era 2.** It goes through `openlibrary.php` and predates
  the S3 service by six years.
- **If it takes `s3_keys`, it is Era 5** and is the intended path.
- **If it reads `site.get().store`, it is Era 1 residue** — OL has not been the system of record since
  November 2014.
- **If it mentions `resource_type`, `fulfillment`, or `.acsm`, it is ACS-era vocabulary** describing a
  system that no longer exists.

---

## Dependencies

**Related:** [[lending]] (current state) · [[bookreader]] · [[auth]] · [[infrastructure]]

---

*Sources: git archaeology of `internetarchive/openlibrary`, verified against `aced0c079`
(origin/master) on 2026-08-29 · See [[README]] · [[METHODOLOGY]]*

---
