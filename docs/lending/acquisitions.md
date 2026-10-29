# Trusted Book Providers: acquisition storage

Where a provider's acquisition links are stored, how they reach Solr and the book page, and the contract consumers depend on.

> Part of [Lending](README.md).

> **Status:** partial
> **Sources:** code synthesis (`openlibrary/book_providers.py`, `openlibrary/core/acquisitions.py`, `openlibrary/core/schema.sql`, `openlibrary/solr/updater/edition.py`, `openlibrary/solr/updater/work.py`, `openlibrary/plugins/worksearch/schemes/works.py`, `openlibrary/plugins/upstream/models.py`, `openlibrary/plugins/upstream/addbook.py`, `scripts/bwb_opds_imports.py`)
> **Last ingested:** 2026-07-24
> **Epic:** internetarchive/openlibrary#12844 (Feed Registry & Acquisitions)

Trusted Book Providers (TBP) is the abstraction that turns "this edition has an ebook somewhere" into concrete, OPDS-flavored **acquisitions** (a URL + access level + format + optional price) that render the Read / Borrow / Download buttons and feed Solr's `ebook_access`. This note documents where acquisition data lives **today** (mostly derived on the fly from Infogami edition fields, with a small amount literally stored on the edition object) and the intended migration to the new `acquisitions` Postgres table.

---

## Summary

Mek's claim: *"TBP saves OPDS-style acquisitions ... that [incorrectly] live on the Open Library infogami edition objects, whereas we want this non-editorial ephemera to live exclusively in the acquisitions table."*

**Partially borne out — the nuance matters:**

- **True for explicitly-stored acquisitions.** Editions carry a `providers` field (a list of OPDS-style acquisition dicts) directly on the Infogami edition object. `DirectProvider` and the base `AbstractBookProvider.get_acquisitions` read acquisitions straight out of `edition["providers"]`. This is exactly the non-editorial ephemera Mek wants moved. **This part of the claim is correct.**
- **Not literally true for most providers.** The dominant providers (Internet Archive's ~6M ocaids, Project Gutenberg, Standard Ebooks, LibriVox, OpenStax, etc.) do **not** store an acquisition on the edition. They store only a stable **identifier** (`ocaid`, or `identifiers.<key>`) and **synthesize** the acquisition at request/index time from a hardcoded URL template. For these, no acquisition "lives" on the edition — only an identifier does, and the acquisition is computed.

So the accurate statement is: acquisitions are today either (a) **derived implicitly** from edition identifier fields, or (b) **stored explicitly** in the edition's `providers` list. The migration question is really about the boundary between (a) and (b) — see [What's Broken / Open Questions](#whats-broken--open-questions).

---

## How It Works

### The `Acquisition` dataclass

`openlibrary/book_providers.py` (~L70) defines the in-memory `Acquisition` dataclass (distinct from the DB row class of the same name in `core/acquisitions.py`):

```
access:        "sample" | "buy" | "open-access" | "borrow" | "subscribe"
format:        "web" | "pdf" | "epub" | "audio"
price:         str | None
url:           str
provider_name: str | None
```

`Acquisition.from_json` (~L89) dispatches on shape:
- `href` present → `from_opds_json` (~L126): true OPDS link; reads `rel` (last path segment → access), `type`/`indirectAcquisition[0].type` (→ format), `properties.price` (→ price), `href` (→ url).
- `url` present → the "Pressbooks/OL-style" internal shape, mapping `read`/`listen`→`open-access`, `preview`→`sample`, etc.

`EbookAccess` (enum 0–4: `NO_EBOOK`, `UNCLASSIFIED`, `PRINTDISABLED`, `BORROWABLE`, `PUBLIC`; kept in sync with `solr/conf/enumsConfig.xml`) is the bridge between acquisition access literals and Solr. Note the lossy mappings: `sample`→`PRINTDISABLED`, `buy`/`subscribe`→`NO_EBOOK`.

### Implicit vs explicit acquisitions

Every provider subclasses `AbstractBookProvider` and is registered in `PROVIDER_ORDER` (~L676). Two mechanisms coexist:

| Mechanism | How the acquisition is produced | Where the data lives |
|---|---|---|
| **Implicit / derived** | `get_acquisitions()` builds a URL from a template + the edition's identifier | Only the **identifier** lives on the edition (`ocaid` or `identifiers.<key>`); the acquisition is computed each time |
| **Explicit / stored** | Base `get_acquisitions()` reads `ed_or_solr["providers"]` (list of acquisition dicts) | The **acquisition dicts themselves** live on the Infogami edition's `providers` field |

### Provider inventory (`PROVIDER_ORDER`)

| Provider class | `short_name` | `identifier_key` | Edition field read | Acquisition style |
|---|---|---|---|---|
| `DirectProvider` | `direct` | `None` | `providers` (db_selector = `providers.url`) | **Explicit** — reads stored `providers` list, filtering out URLs already produced by other providers to avoid dupes |
| `LibriVoxProvider` | `librivox` | `librivox` | `identifiers.librivox` | Implicit (`librivox.org/{id}`, audio) |
| `ProjectGutenbergProvider` | `gutenberg` | `project_gutenberg` | `identifiers.project_gutenberg` | Implicit (`gutenberg.org/ebooks/{id}`) |
| `ProjectRunebergProvider` | `runeberg` | `project_runeberg` | `identifiers.project_runeberg` | Implicit |
| `StandardEbooksProvider` | `standard_ebooks` | `standard_ebooks` | `identifiers.standard_ebooks` | Implicit (emits both single-page web + epub) |
| `OpenStaxProvider` | `openstax` | `openstax` | `identifiers.openstax` | Implicit |
| `CitaPressProvider` | `cita_press` | `cita_press` | `identifiers.cita_press` | Implicit |
| `WikisourceProvider` | `wikisource` | `wikisource` | `identifiers.wikisource` | Implicit |
| `InternetArchiveProvider` | `ia` | `ocaid` | **`ocaid`** (db_selector = `ocaid`, not `identifiers.*`) | Implicit + IA metadata-driven access; also derives download links |
| `BetterWorldBooksProvider` | `betterworldbooks` | `betterworldbooks` | needs ISBN + lookup in `config.bwb_test_holdings` | Hybrid (see below) |

Notes:
- **Internet Archive is special.** Its identifier is the top-level `ocaid` field, not `identifiers.ocaid`. `get_access()` (~L337) inspects IA item metadata (`collection`, `access_restricted_item`) to decide `BORROWABLE` / `PRINTDISABLED` / `UNCLASSIFIED` / `PUBLIC`. Its `get_acquisitions()` (~L356) reads Solr `ebook_access` back into an access literal and synthesizes an `archive.org/details/...` theater URL plus (for open-access) `{ocaid}.pdf`/`{ocaid}.epub` download links.
- **`is_own_ocaid()` sniffing.** Providers claim ocaids that are actually theirs (Gutenberg: ends with `gut`; Runeberg/LibriVox: substring match). `is_non_ia_ocaid()` uses this so that on aggregated Solr work records (no selected edition) OL can prefer genuine IA copies.
- **BetterWorldBooks is the odd one.** It matches on ISBN and currently looks acquisitions up from Infogami `config.bwb_test_holdings` (test holdings), keyed by edition key — not from the edition object and not from a table. `scripts/bwb_opds_imports.py` polls the BWB OPDS feed and writes **import batches** (`bwb-opds-YYYY-MM-DD`), and its docstring explicitly flags the overlap with the proposed Solr `acquisitions` array (#11264).

### Where acquisition/provider data lives on the edition today

- **`ocaid`** (top-level edition field) → IA.
- **`identifiers.<key>`** (dict on edition) → every non-IA implicit provider. The keys map to `/config/edition` identifier types.
- **`providers`** (list on edition) → explicit OPDS-style acquisition dicts. Written via `Edition.set_providers()` / `set_provider_data()` (`plugins/upstream/models.py` ~L394) and populated on save in `addbook.py` (~L651: `providers = edition_data.pop("providers", []); self.edition.set_providers(providers)`). There's even an edit-form UI (`js/add_provider.js`, fields `edition--providers--{i}--{type}`).

So the "ephemera on Infogami edition objects" is concretely the `providers` list (and, arguably, the identifier fields that drive implicit providers).

---

## How provider/acquisition info flows into Solr

Solr is populated by the updaters, entirely from the **Infogami edition** (not from the acquisitions table):

- `solr/updater/edition.py`:
  - `self._providers = list(bp.get_book_providers(edition))` and `_best_provider` (~L125).
  - Emits `ebook_access` (`self._best_provider.get_access(...)`, ~L334), `ebook_provider` (list of provider names, ~L342), `has_fulltext` (`> UNCLASSIFIED`), `public_scan_b` (`== PUBLIC`), plus `id_<key>` identifier fields and `ia`.
- `solr/updater/work.py`:
  - Work-level `ebook_access` is the **max over its editions' `ebook_access`** (~L507), and `ebook_count_in_solr` counts editions with an ebook.
- `plugins/worksearch/schemes/works.py`:
  - The Solr **`providers`** array field is materialized at fetch time by calling `book_providers.get_acquisitions(solr_doc, ed)` and serializing each `Acquisition.__dict__` (~L645–663). Again sourced from the live edition, not a table.

Bottom line: `ebook_access`, `ebook_provider`, and the Solr `providers` array are all **computed from the Infogami edition** via `book_providers.py` at index/fetch time.

---

## The new home: `acquisitions` table + `core/acquisitions.py`

Added in commit `b74cec763` ("Add acquisitions table and interface for Trusted Book Providers"; docstring references #12844 and PR #12793 — merged as part of the #12851 work).

**Schema** (`openlibrary/core/schema.sql` ~L135):

```sql
CREATE TABLE acquisitions (
    id serial primary key,
    work_id integer not null,
    edition_id integer not null,
    provider_name text not null,
    local_id text not null,
    data jsonb not null,          -- provider metadata blob: prices, formats, urls, etc.
    created timestamp ...,
    updated timestamp ...,
    UNIQUE (local_id, provider_name)
);
-- indexes on work_id, edition_id, updated
```

One row per edition per provider. The **unique key is `(local_id, provider_name)`**, deliberately *not* `(work_id, edition_id)` — so work/edition merges never conflict.

**Interface** (`openlibrary/core/acquisitions.py`): `Acquisition(web.storage, CommonExtras)` with:
- `get_by_edition(edition_id, provider_name=None)`
- `get_by_work(work_id)`
- `upsert(work_id, edition_id, provider_name, local_id, data=None)` — `INSERT ... ON CONFLICT (local_id, provider_name) DO UPDATE` refreshing `work_id`/`edition_id`/`data`/`updated`.
- `update_work_id(...)` inherited from `CommonExtras`, so work merges (`resolve_redirects`) re-point rows robustly.
- `_from_row` handles jsonb-as-dict (Postgres) vs jsonb-as-str (SQLite).

**Who reads/writes it today: nobody in the app.** The only callers are `openlibrary/tests/core/test_acquisitions.py`. No ingestion cron calls `.upsert`, and neither the Solr updaters nor `book_providers.get_acquisitions()` read from it. The module docstring's "ingestion cron upserts rows; Solr later reflects them" is **aspirational** — the table is currently dormant/staged.

---

## `editions.opds_acquisitions` — the consumer contract

> **Reading `properties.openlibrary_source` is mandatory. `provider_name`
> alone is not trustworthy.**

Merged 2026-09-20 (internetarchive/openlibrary#13395, `9d7536c3a`). Opt-in by
name — a caller gets the field only by asking for it, which is also the only
off switch.

### The field name is easy to get wrong, and getting it wrong is silent

```bash
# WORKS — dotted, and `editions` requested so there is a sub-doc to attach to
curl 'https://openlibrary.org/search.json?q=frankenstein&limit=2\
&fields=key,title,editions,editions.key,editions.opds_acquisitions'

# RETURNS NOTHING, NO ERROR — bare name
curl '…&fields=key,title,opds_acquisitions'
```

The field is registered **dotted-only** (`works.py`, in `non_solr_fields`),
deliberately: a bare name is expanded into both `work.X` and `editions.X`, and
a price belongs to a printing, not to a work. The weave gate tests
`if "editions.opds_acquisitions" in prefixed_fields`, so a bare request never
matches — and `code.py` intersects against the raw request set, so it is not
expanded either. The response comes back **200 with the field simply absent**.

This is not hypothetical: the first person to try it in anger used the bare
name and got an empty result, which is why the query shape is recorded here
verbatim rather than described. An absent field also means "could not read"
(see below), so a caller cannot distinguish a typo from an outage from a book
with no acquisitions.

**Open question, not yet ruled on:** whether a bare `opds_acquisitions` should
400 rather than return nothing. That is a change to shared field-expansion
machinery affecting every non-solr field, so it is a follow-up, not a patch.

**Why the marker is not optional.** Both `identifiers.*` and
`Edition.providers` are wiki-editable, so a patron controls the URL *and* the
provider name on any link derived from them. In the collision case — a patron
sets `identifiers.project_gutenberg` **and** adds a `providers` entry naming
`project_gutenberg` with a URL of their choosing — one edition yields two
links that **agree in every published field**, one pointing at gutenberg.org
and one at the patron's host. **The patron's sorts first**, because
`DirectProvider` heads `PROVIDER_ORDER`. A consumer keying on `provider_name`
and taking the first match is handed an arbitrary host.

| `properties.openlibrary_source` | Means | Trust |
|---|---|---|
| `harvested` | Ingested from a registered feed; the import gate checked `provider_name` for exact membership in `FeedRegistry.provider_names()` | The provider's own statement |
| `synthesized` | A `book_providers` class hard-coded the host and appended an `identifiers.*` value | OL constructed the URL — **a claim about the host, not that the provider offers this book** |
| `edition_providers` | Copied out of `Edition.providers` | **Patron-controlled URL and name, both verbatim** |

`harvested` cannot be forged: it is written at exactly one site, from DB rows
only, and applied *after* the feed's property spread so a feed cannot override
it.

**`provider_name` can be `None`, and is on production today.** Verified
2026-09-21 against `openlibrary.org/books/OL59176589M.json`:

```json
"providers": [{"url": "https://github.com/mekarpeles/quintet/blob/master/quintet.org",
               "access": "read", "format": "web"}],
"identifiers": {"lenny": ["59176589"]}
```

The blob carries `url`, `access` and `format` and **no `provider_name` key at
all**, so the `edition_providers` link publishes `provider_name: null`.
Consumers must handle that — the field is not merely untrustworthy, it can be
absent. (Mildly reassuring: a patron omitting the name cannot *impersonate* a
provider through it. The risk is a null, not a forged label.)

**This edition is the whole contract in one response**, and on *testing*
where the field is deployed it returns both links at once:

| `openlibrary_source` | `provider_name` | href |
|---|---|---|
| `harvested` | `lenny` | `lennyforlibraries.org/v1/api/items/59176589/borrow` |
| `edition_providers` | `None` | `github.com/mekarpeles/quintet/blob/master/quintet.org` |

A vetted feed link beside a patron-authored one, identical in shape,
distinguished **only** by the marker. The `edition_providers` path is
therefore not hypothetical wiki abuse — it is how a real production edition is
configured today.

**The invariant this rests on** is that no provider's `get_acquisitions`
delegates to the base implementation — one that did would publish patron text
under a trusted registry name. Pinned by
`test_no_override_delegates_to_the_patron_path`, parametrized over all eight
override-bearing providers. If you add a provider, that test is the thing
that must keep passing.

**Known limit, deliberate:** one provider can still appear under two spellings
*across* the response, because `editions.providers` is woven twelve lines away
in the same method and still publishes `gutenberg` where a harvested row says
`project_gutenberg`. Consistency holds *within* `opds_acquisitions` only.

**Failure is silent by design:** a database error logs
(`works.py` — `logger.exception("failed to read acquisitions...")`) and the
field is omitted rather than failing the search. An absent field therefore
means "could not read" **or** "none exist" — these are indistinguishable to a
caller. There is no metric or alert; that was a considered choice for a new
additive field, not an oversight.

## What's Broken / Open Questions

The concrete gap between today and "acquisitions live exclusively in the `acquisitions` table":

1. **Nothing populates the table.** Need per-provider ingestion (crons/feed consumers) that call `Acquisition.upsert(...)`. `bwb_opds_imports.py` already fetches OPDS but writes import batches, not the table — it's the natural first writer.
2. **Nothing reads the table.** `book_providers.get_acquisitions()` and the Solr updaters must be re-pointed to source acquisitions from the table instead of `edition["providers"]` / derived templates.
3. **Backfill / migration.** The existing `providers` lists on Infogami editions (the `DirectProvider` data) must be migrated into rows and then stopped being written on edit (`addbook.py` / `set_providers`).
4. **Solr shape.** `ebook_access` / `ebook_provider` / `providers[]` derivation would move from "compute from edition" to "join the table" (and eventually the acquisitions array itself may be stored in Solr per #11264).

**Mek's open question — implicit vs explicit for well-defined providers:** For providers whose acquisition is 100% derivable from a stable identifier via a URL template (IA's ~6M ocaids, Gutenberg, Standard Ebooks), should we **materialize** an explicit row per identifier in the `acquisitions` table, or keep deriving them implicitly and only store rows for genuinely ephemeral/non-template acquisitions (prices, direct URLs, BWB buy links)?
- *Materialize everything:* uniform read path, Solr just joins the table, no special-casing — but ~6M+ redundant IA rows that duplicate `ocaid` and must be kept in sync on every edition change.
- *Keep well-defined providers implicit:* the table holds only true ephemera; IA/Gutenberg/etc. stay derived from identifiers (which are legitimately editorial edition data). Smaller table, but the read path stays hybrid (derive + join) — arguably contradicting "exclusively in the table."

This trade-off is the crux of the Feed Registry / Acquisitions epic and is not yet resolved in code.

---

## Common Confusion

- **Two classes named `Acquisition`.** `book_providers.Acquisition` is a transient in-memory dataclass (URL/access/format/price). `core.acquisitions.Acquisition` is a DB row (`web.storage`). They are unrelated types.
- **`identifier_key` vs `provider_name` vs `short_name`.** `identifier_key` names the edition `identifiers.<key>`; `provider_name` defaults to it (IA overrides to `"ia"`); `short_name` is the UI/template name. `get_book_provider_by_name()` accepts either `provider_name` or `short_name`.
- **IA does not use `identifiers.ocaid`.** It uses the top-level `ocaid` field; its `db_selector`/`solr_key` are overridden accordingly.

---

## Key Files

| File | Purpose |
|---|---|
| `openlibrary/book_providers.py` | `Acquisition` dataclass, `EbookAccess`, all `*BookProvider` subclasses, `PROVIDER_ORDER`, `get_acquisitions()` |
| `openlibrary/core/acquisitions.py` | DB interface to the `acquisitions` table (dormant; tests only) |
| `openlibrary/core/schema.sql` (~L135) | `acquisitions` table DDL |
| `openlibrary/solr/updater/edition.py` | Emits `ebook_access`/`ebook_provider`/`providers` from the edition |
| `openlibrary/solr/updater/work.py` | Work-level `ebook_access` = max over editions |
| `openlibrary/plugins/worksearch/schemes/works.py` (~L645) | Materializes Solr `providers[]` via `get_acquisitions` |
| `openlibrary/plugins/upstream/models.py` (~L394) | `Edition.set_providers()` / `set_provider_data()` |
| `openlibrary/plugins/upstream/addbook.py` (~L651) | Writes `providers` onto the edition on save |
| `scripts/bwb_opds_imports.py` | BWB OPDS feed consumer (writes import batches) |
| `openlibrary/tests/core/test_acquisitions.py` | Only current caller of the table interface |

## Dependencies

*Depends on →* [[../lending|Lending]] (shares `EbookAccess`, `book_providers.py`), Infogami edition objects, Solr (`enumsConfig.xml`).
*Depended on by →* [[../features|Features]], Solr search (`ebook_access`, `has_fulltext`), Read/Borrow/Download buttons.

---

*See [[README]] · [[METHODOLOGY]] for ingest rules*
