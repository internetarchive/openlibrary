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

Read the domain reference first — this agent points into it rather than
repeating it: [`docs/lending/README.md`](/docs/lending/README.md) (how lending
works today), [`docs/lending/history.md`](/docs/lending/history.md) (why the code
looks the way it does), [`docs/lending/acquisitions.md`](/docs/lending/acquisitions.md),
and [`docs/lending/lenny.md`](/docs/lending/lenny.md) (the Lenny-node OAuth flow).

## Book access states

`EbookAccess` (in `openlibrary/book_providers.py`, kept in sync with
`conf/solr/conf/enumsConfig.xml`): `NO_EBOOK`, `UNCLASSIFIED`, `PRINTDISABLED`,
`BORROWABLE` (CDL), `PUBLIC`. The IA Availability API v2 reports a separate loan
status. See [Book Access States](/docs/lending/README.md#book-access-states) and
[Availability API](/docs/lending/README.md#availability-api).

## Borrow flow (end to end)

`POST /books/{key}/borrow` checks open-access (read directly, no loan) →
`lending.get_availability()` → verifies login + IA S3 credentials →
`user_can_borrow_edition_async()` (in `borrow.py`) →
`lending.s3_loan_api(... action="borrow_book")` POSTs to archive.org → OL builds
a signed BookReader auth link and redirects. When all copies are out, readers
join the waiting list (`waitinglist.py`). Full walk-through:
[Borrow Flow (End-to-End)](/docs/lending/README.md#borrow-flow-end-to-end) and
[S3 Keys and Authentication](/docs/lending/README.md#s3-keys-and-authentication).

## Code areas & gotchas

- `openlibrary/core/lending.py` — availability, loan API calls, bookreader
  links. **Much of this file is historical.** OL was the system of record for
  lending until 2014 and still talks to archive.org through two loan APIs at
  once. Read [the lending history](/docs/lending/history.md) before changing
  anything here — most of what looks arbitrary is dated — and the live sharp
  edges in [What's Broken / Fragile](/docs/lending/README.md#whats-broken--fragile).
- `openlibrary/core/waitinglist.py` — waiting-list documents and state.
- `openlibrary/plugins/upstream/borrow.py` — the borrow/return endpoints.
- **OTP service** — Open Library issues one-time passwords so external lending
  nodes can authenticate patrons: `openlibrary/core/auth.py`
  (`TimedOneTimePassword`) and `openlibrary/plugins/upstream/account.py`
  (`/account/otp/issue`, `/account/otp/redeem`). `service_ip` (from
  `X-Forwarded-For`) must match between issue and redeem; pass `sendmail=false`
  to skip SMTP in local dev. See [`docs/core/otp-service.md`](/docs/core/otp-service.md)
  and its [Local Docker Testing](/docs/core/otp-service.md#local-docker-testing).
- **Lenny node integration** — borrowing from an external self-hosted lending
  node uses per-node OAuth 2.0: a harvest fills the acquisitions table with
  borrow links, then an authorize/token exchange stores a per-patron grant. This
  is the first case of a service other than archive.org lending books, so
  archive.org-specific assumptions do not carry over, and a node has two auth
  surfaces (session-cookie vs scoped token) that can drift — be explicit about
  which one a change touches. See [`docs/lending/lenny.md`](/docs/lending/lenny.md):
  [How it works](/docs/lending/lenny.md#how-it-works),
  [Design assumptions](/docs/lending/lenny.md#design-assumptions), and
  [What's fragile](/docs/lending/lenny.md#whats-fragile). Where acquisition links
  are stored and how they reach Solr: [`docs/lending/acquisitions.md`](/docs/lending/acquisitions.md).

## Finding work (domain labels)

This agent owns Open Library issues and PRs tagged with these existing GitHub
labels — query them to find open work in the domain:

- `Module: Borrowing / Lending`
- `Module: Lenny (Lending)`
- `Theme: Book Availability`

Combine with `Type: Epic` to surface epic-scale efforts in the domain.

## Docs & discipline

Primary references: [`docs/lending/`](/docs/lending/README.md) (README, history,
acquisitions, lenny) and [`docs/core/otp-service.md`](/docs/core/otp-service.md).
For general conventions (TDD, tests, lint) see
[`docs/ai-coding-guide.md`](/docs/ai-coding-guide.md) and `AGENTS.md`. Route any
security or auth-exposure finding to a maintainer privately first — never in a
public comment.
