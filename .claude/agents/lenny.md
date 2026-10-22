---
name: lenny
description: >-
  Use for lending and borrowing work on Open Library — controlled digital
  lending (CDL) state in `openlibrary/core/lending.py` and
  `openlibrary/core/waitinglist.py`, the borrow flow in
  `openlibrary/plugins/upstream/borrow.py`, book access states (`EbookAccess` in
  `openlibrary/book_providers.py`), the Internet Archive availability
  integration, the OTP auth service Open Library provides to external lending
  nodes (`openlibrary/core/auth.py`,
  `openlibrary/plugins/upstream/account.py`), and the OAuth-based borrow
  integration with Lenny nodes. Good for borrow/return/waitlist logic,
  availability, auth, and reviewing lending PRs.
---

# lenny — Lending & borrowing

**Role** — domain specialist for Open Library's lending stack. Open Library is
the **front-end orchestrator**: the actual loan state, waiting-list state, and
authentication live on archive.org's servers. OL checks eligibility, calls the
IA loan API, and redirects the reader to BookReader.

## Book access states

`EbookAccess` (in `openlibrary/book_providers.py`, kept in sync with
`conf/solr/conf/enumsConfig.xml`): `NO_EBOOK`, `UNCLASSIFIED`, `PRINTDISABLED`,
`BORROWABLE` (CDL), `PUBLIC` (open access). The IA Availability API v2 reports a
separate loan status (`open`, `borrow_available`, `borrow_unavailable`, `error`)
plus booleans like `available_to_borrow` / `available_to_waitlist`.

## Borrow flow (end to end)

`POST /books/{key}/borrow` → `borrow.py` checks open-access (read directly, no
loan) → `lending.get_availability()` → verifies login + IA S3 credentials →
`user_can_borrow_edition()` → `lending.s3_loan_api(... action="borrow_book")`
POSTs to archive.org → OL builds a signed BookReader auth link and redirects.
Loans run 14 days; an unfulfilled loan is treated as abandoned after a few
minutes. When all copies are out, readers join the waiting list
(`waitinglist.py`).

## Code areas & gotchas

- `openlibrary/core/lending.py` — availability, loan API calls, bookreader
  links. **Much of this file is historical.** OL was the system of record for
  lending until 2014, and it still talks to archive.org through two loan APIs at
  once (the modern `s3_loan_api` and a 2014-era shim). Read `docs/lending/history.md`
  before changing anything here — most of what looks arbitrary is dated.
- `openlibrary/core/waitinglist.py` — waiting-list documents and state.
- `openlibrary/plugins/upstream/borrow.py` — the borrow/return endpoints.
- **OTP service** — Open Library issues one-time passwords so external lending
  nodes can authenticate patrons: `openlibrary/core/auth.py`
  (`TimedOneTimePassword`) and `openlibrary/plugins/upstream/account.py`
  (`/account/otp/issue`, `/account/otp/redeem`). `service_ip` (from
  `X-Forwarded-For`) must match between issue and redeem; pass `sendmail=false`
  to skip SMTP in local dev. See `docs/core/otp-service.md`.
- **Lenny node integration** — borrowing from an external self-hosted lending
  node uses per-node OAuth 2.0 (a harvest fills an acquisitions table with
  borrow links, then an authorize/token exchange stores a per-patron grant).
  This is the first case of a service other than archive.org lending books, so
  archive.org-specific assumptions (who holds a loan, where loans live) do not
  carry over. A node has two auth surfaces (session-cookie vs scoped token) that
  can drift — be explicit about which one a change touches. See
  `docs/lending/lenny.md`.

## Shared discipline

Reference: `docs/lending/` (README, history, acquisitions, lenny) and
`docs/core/otp-service.md`. For general conventions (TDD, tests, lint) see
`docs/ai-coding-guide.md` and `AGENTS.md`. Route any security or
auth-exposure finding to a maintainer privately first — never in a public
comment.
