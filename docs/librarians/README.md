# Librarians System

> **Status:** partial
> **Sources:** `raw/openlibrary-wiki/Lead:-Community-Librarian.md`, `Anti-Spam-Tools.md`, `Library-Metadata-Standards.md`, `Librarian-Resources/Guide-to-Identifiers.md`
> **Last ingested:** 2026-06-27
> **Source trust:** Medium (wiki; some docs explicitly marked deprecated)

The Librarians System is the **editing experience and tooling** for the people who curate Open Library — the editing UI, merge tools, moderation / anti-spam, metadata standards, and the emerging **micro-edits** surface. It is distinct from [`../tags/`](../tags/): tags is the *data / vocabulary* system, this is the *editing experience* that acts on it (the two cross-reference).

**What belongs here:** the librarian-facing editing UI, merge and moderation tooling, and librarian documentation. The **micro-edits** experience — in-UI contributions and the librarian "what to edit next" surface — is tracked in epic **#13811**; its documentation lands here as it matures.

Open Library has a community of volunteer librarians who curate records, merge duplicates, handle moderation, and maintain metadata quality. Staff roles are defined in the openlibrary-librarians repo; librarians operate through the OL editing interface and a set of staff/admin-only tools.

---

## Community Librarian Role

**Repo:** `github.com/internetarchive/openlibrary-librarians`
**Slack:** `#open-librarians-g`
**Current owner:** @seabelis

Responsibilities:
- Welcome new librarians in `#open-librarians-g`
- Identify broken/missing librarian features on openlibrary.org
- Identify spam from `openlibrary.org/recentchanges` and report to staff
- Maintain and create librarian documentation
- Respond to editing-related user emails
- Collect, vet, and execute **Author merge** and **Works merge** requests
- Create and manage issues on `github.com/internetarchive/openlibrary-librarians`
- Maintain projects list for new librarians
- Identify and promote promising open librarian candidates

---

## Identifier System

### Author / Name Identifiers

| Identifier | Format | Notes |
|-----------|--------|-------|
| `olid` (author) | `OL1234A` | OL's own author record key |
| `lcauth` | URL | Library of Congress authority ID |
| `viaf` | ID | Virtual International Authority File — federated from national authority files |
| `isni` | ISO 27729 | One ISNI per author identity |
| `orcid` | URL | Open Researcher and Contributor ID |
| `wdt` | Wikidata item ID | e.g. `Q6290611` |

For deduplication: prefer ISNI author name (disinverted); list aliases under alternative names. Do NOT store external links for undifferentiated (catchall) author records.

### Edition Identifiers

| Identifier | Format | Notes |
|-----------|--------|-------|
| `olid` (edition) | `OL123M` | OL edition key |
| `oclcid` | number | Use smallest OCLC number when multiple exist |
| `lccn` | LC Control Number | |
| `ocaid` | Archive.org item ID | e.g. `jungleauthoritat00sinc` |
| `htid` | HathiTrust ID | |
| `googleid` | Google Books ID | |
| `isbn_10`, `isbn_13` | digits | Strip non-digits; validate checksum |

### OL ↔ Archive.org Link Fields

OL editions carry `ocaid` (pointing to the Archive.org item). Archive.org items carry:
- **`openlibrary`** — legacy field, stale, should eventually be deprecated
- **`openlibrary_edition`** — current, maps IA item → OL edition key (e.g. `OL3561303M`)
- **`openlibrary_work`** — current, maps IA item → OL work key

⚠️ The IA `derive` pipeline still uses the legacy `openlibrary` metadata field — it was never updated to use `openlibrary_edition` / `openlibrary_work`. Do not drop the `openlibrary` field until that pipeline is updated.

### Identifier Gotchas

- A huge number of bogus ISBNs entered the catalog from bad Amazon records in 2008; strip or downgrade to ASIN if they can't be validated via Worldcat.
- ASIN and OCAID are frequently confused in the UI — users paste full URLs instead of bare IDs.
- For OCLC: an edition can have many OCLC numbers pointing to it; use the **smallest** number as canonical.

---

## Metadata Standards (Open Questions / Standardization Targets)

These are known inconsistencies in OL's metadata — areas where the community has identified standardization work to be done. None of these are fully resolved.

| Area | Issue |
|------|-------|
| Titles | Sentence case preferred (easier to read, auto-convertible to Title Case) — but no enforcement |
| Author names | OL uses "natural order" (First Last); ISNI preferred for authority — but adoption is incomplete |
| Publish dates | Free text; year is the meaningful field for copyright purposes |
| Format names | "Hardcover" / "Softcover" have many synonyms — no controlled vocabulary |
| Subjects | No authority control; case inconsistent; overlap with Tag system (see [[tags]]) |
| ISBN validation | Strip non-digits, run checksum, validate against Worldcat before ingesting |
| Unicode | NFC normalization expected but not enforced; implications for Solr search are undefined |
| VIAF/Wikidata in records | Full URL should be stored for author links, not just bare ID |

**Schemas** (JSON Schema, in openlibrary-client):
- Authors: `olclient/schemata/author.schema.json`
- Editions: `olclient/schemata/edition.schema.json`
- Works: `olclient/schemata/work.schema.json`

---

## Spam & Abuse Handling

Abuse and DDoS response procedures live in the [Disaster Recovery & Immediate Response](https://github.com/internetarchive/openlibrary/wiki/Disaster-Recovery-&-Immediate-Response#handling-abuse--ddos-denial-of-service-attack) guide. The operational detail — host access, log locations, block lists — is staff/prod material and lives with `internal/`/`olsystem`, not here.

---

## Merge Requests

Librarians collect, vet, and execute author and work merge requests. The merge flow goes through OL's admin/editorial interface. This area needs a follow-up ingest — the specific merge endpoints and ILE (inline edit) tool are not covered in available source material.

---

## What's Broken / Fragile

- **Anti-Spam-Tools.md is deprecated** — real runbook lives elsewhere (link above)
- **`openlibrary` metadata field on IA** still in use by derive pipeline — migration to `openlibrary_edition`/`openlibrary_work` is incomplete
- **No controlled vocabulary for subjects/formats** — data quality problems accumulate
- **ISBN bogus data from 2008** — bulk cleanup not completed

---

## Dependencies

**Depends on:**
- [[core-operations]] — editorial UI, admin dashboard, Infogami record editing
- [[tags]] — subject/tag overlap; community tags (Observations) sit in the tag system
- [[infrastructure]] — spam blocking via nginx/olsystem on ol-www0; PostgreSQL for account queries

**Depended on by:**
- [[imports]] — librarians review and correct imported records
- [[core-vitals]] — librarian actions (Book Edit, Author Edit, Work Merge, Author Merge, Cover uploads, Series edits) are Participation events; their ω-value contribution feeds the Participation Score

---

*Sources: `raw/openlibrary-wiki/Lead:-Community-Librarian.md` (role), `Anti-Spam-Tools.md` (deprecated), `Library-Metadata-Standards.md`, `Librarian-Resources/Guide-to-Identifiers.md` · Merge/ILE tool stub — needs follow-up · See [[README]] · [[METHODOLOGY]]*
