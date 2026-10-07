# Lenny ↔ Open Library: the OAuth borrow flow

## What it is

Lenny is a self-hosted lending server. Many organisations run their own **node**; each node holds its own files and issues its own loans. This page documents how Open Library borrows from one on a patron's behalf.

Open Library is the front door: a reader finds a book, sees that a participating library lends it, and borrows without leaving the site. The node does the lending. Without this integration, a Lenny node's holdings can be *listed* on Open Library but not *borrowed* through it.

Lenny is the first case where a service other than archive.org lends books, so assumptions that resolve to archive.org — who can hold a loan, where a patron's loans live — do not hold here.

## How it works

Each node is its own OAuth 2.0 authorization server; Open Library is a registered client of each.

1. A harvest reads the node's OPDS feed into the `acquisitions` table, so borrow links exist as rows before any patron arrives.
2. The patron clicks Borrow on a book page. Open Library sends them to the node's `/authorize` with PKCE, passing their address as `login_hint`.
3. The node requires its own session before issuing a code, so the patron signs in there — a one-time code to the hinted address — and that sign-in sets the node's first-party cookie.
4. The patron consents. The node redirects back to Open Library's callback with a code.
5. Open Library checks `state` and `iss`, exchanges the code for tokens, stores the grant encrypted, and calls the node's borrow endpoint.
6. The patron returns to the book page, which now offers Read. The node serves the book using the cookie from step 3.

Subsequent borrows skip steps 3–4 until the node session expires.

## Design assumptions

These are decisions, not accidents. Changing any of them changes the security properties.

**OAuth, not shared keys.** An earlier design had Open Library post its archive.org S3 keys to the node and read loans back from a cookie. It was rejected: a node would see credentials that act for every patron, and a single leak would expose everyone's borrowing. The grant is per-patron, scoped, and stored server-side.

**A popup, not an iframe.** The authorize screen opens in a popup because a popup is a top-level browsing context, so the node's session cookie is first-party. In an iframe it would be third-party and Safari would drop it — and the live authorize endpoint sets no frame-ancestor header, so an iframe fails at the cookie rather than at the frame. The cookie is `SameSite=Lax`, which is sufficient for a top-level context and is not sufficient for cross-site XHR.

**No token-to-session exchange.** The node's `/authorize` refuses to issue a code without a node session, so by the time Open Library holds a token the patron's browser already holds the cookie the reader needs. Borrow-then-read works with nothing further built; a token-to-session exchange would be new attack surface for no gain.

**Registration is operator-driven.** There is no HTTP registration endpoint. An operator runs a command on the node, which registers it with Open Library's feed registry and issues that node's client credentials. Deliberate while the set of partners is small.

**The read gate keys on the patron's address, hashed.** The node identifies a reader by `sha256` of their lowercased email, taken from its own session — not from anything a caller supplies.

## Components

| Part | Role |
|---|---|
| Node OAuth server | `/.well-known/oauth-authorization-server`, `/authorize`, `/token`, `/revoke` |
| Node borrow API | creates and lists loans for a bearer token |
| Node patron login | one-time-code sign-in; sets the node session cookie |
| Node reader | serves the book to a session holding a loan |
| Open Library client | borrow route, callback, token storage, loans merge |
| Feed registry + `acquisitions` | which editions a node lends |

## The contract

Discovery is published at the node's origin and is authoritative for endpoint locations. It advertises Authorization Code with PKCE (`S256`), refresh tokens, and `authorization_response_iss_parameter_supported`. Implicit is deliberately absent, and dynamic client registration was deliberately removed.

Three properties of the contract are easy to get wrong:

- **Discovery is authoritative for the token endpoint; the configured issuer is used for the loans lookup.** A node whose advertised host differs from the host Open Library is configured with therefore has *working loans and broken refresh* — and a failed refresh deletes the patron's grant, so the symptom is a patron silently needing to reauthorize. Advertise the host the client is configured with.
- **Timestamps are timezone-aware.** The node's loan fields carry an offset. Open Library's expiry parser cannot read one, and a *negative* offset raises `TypeError` rather than `ValueError` — so a guard that catches only `ValueError` still fails for every node west of UTC. Normalise at the boundary.
- **A redirect URI must be `https`, loopback `http`, or a private-use scheme** (RFC 8252). Other hostnames are refused at registration, with a message that does not name the hostname as the cause.

## Configuration

Open Library reads two keys: the set of configured nodes (issuer, client id, client secret, display name) and the callback URI. The callback must match what was registered on the node byte-for-byte.

On the node, the OTP service address is an ordinary environment variable, defaulting to Open Library. Lending must be enabled and the node's Open Library credentials present, or every sign-in is refused as unconfigured.

## Operating a node

- The session cookie is set `secure`, so a plain-HTTP client never sends it back. Local development over HTTP cannot complete a browser sign-in without TLS.
- Credentials are read at import time while the lending mode is re-read per call, so changing them requires **recreating** the container, not restarting it. A restart silently keeps the old values.
- Borrowable items must be stored encrypted; open-access items are refused by the borrow endpoint. The format field is an uppercase enumeration.
- The API container's bundled reverse proxy routes to the reader and admin services, so the API container does not start alone.

## Testing

An end-to-end harness in the Lenny repository walks the whole seam in one command — sign-in, authorize with PKCE, consent, token exchange, borrow, loans, then Open Library's own storage and loans merge — and exits non-zero when any step fails. It stands up a throwaway node and cleans up after itself, and has deliberate failure modes for verifying that it still bites.

A stub for the one-time-code service lets the flow run without a human inbox, by pointing the node's OTP service address at it. This requires no change to node code and is unreachable on a node configured normally.

## What's fragile

- **The token store has no deployed home.** `provider_tokens` is defined in no schema Open Library applies, and Open Library has no DDL-migration mechanism, so a new table reaches fresh installs only. Tracked in internetarchive/openlibrary#13685 and the epic #13270.
- **One node or many.** The book-page button resolves acquisitions under a single provider name, while the feed registry assigns per-node names. A second node's editions therefore select no provider at all, silently. Tracked in internetarchive/openlibrary#13686.
- **Read and Borrow can disagree on which acquisition they act on** when an edition carries both an open-access and a borrow row. Tracked in internetarchive/openlibrary#13686.
- **The OPDS Authentication Document advertises the legacy flow.** This does not affect Open Library, which uses RFC 8414 discovery, but it misdirects other OPDS clients. Tracked in ArchiveLabs/lenny#232.

## Response playbook

**A patron reports that Read does nothing after borrowing.** Check that the node session cookie is present — it is set at sign-in, not at borrow. If the patron borrowed days earlier, the node session has likely expired; re-authorizing restores it without a new consent, because the grant is still in force.

**Loans show but a borrow fails, or the reverse.** These use different endpoint sources — loans from the configured issuer, refresh from discovery. A mismatch between the node's advertised host and its configured issuer produces exactly this split. Compare the two.

**A patron is asked to reauthorize repeatedly.** A refresh failure deletes the grant by design, so a node that intermittently fails refresh presents as repeated reauthorization rather than as an error. Check refresh against the discovered token endpoint.

**A library's books stop offering Borrow.** Confirm an acquisition row exists for the edition and that its provider name is one Open Library is configured for; see *What's fragile* above.

**A node is compromised or must be cut off.** Revoke that node's client credentials on the node and remove it from Open Library's configured nodes. Stored grants for that node become unusable at the next refresh; they are per-patron and scoped, so no other node is affected.

## Dependencies

Depends on the feed registry and the `acquisitions` table for knowing which editions a node lends, on the node being reachable for every borrow and loans lookup, and on Open Library's one-time-code service for node sign-in by default.

Depended on by the book page's borrow affordance and by the patron's loans page, which merges node loans alongside Internet Archive loans. Both degrade rather than fail when a node is unreachable.
