**v1 of the Feed Registry & Acquisitions system (#12844).** Companion to the integration-prototype draft #13206 (kept intact); this is the clean, atomic-ish v1 that lands acquisitions in Open Library proper. TDD throughout.

## What v1 does
Register a feed → a **bookworm FastAPI service** (ol-home0/affiliate-server pattern) polls it on a timer → parses OPDS 2.0 into OL import records **carrying `acquisitions[]`** → submits to OL's existing `import_item` queue → **ImportBot loads them and the catalog upserts the acquisitions** → **`search.json` weaves acquisitions in** at query time.

## Pieces (each with tests)
- `openlibrary/bookworm/opds.py` — pydantic OPDS 2.0 parser handling **all 3 real feeds** (BWB ISBN/buy, Gutenberg gutenberg-id/open-access, Lenny self-link-id/open-access), tested against captured samples.
- `import.schema.json` + `add_book.load` — records carry `acquisitions[]`; the catalog upserts them (`provider_name`,`local_id` + created edition/work ids); **public `/api/import` strips acquisitions** (trusted cluster imports keep them).
- `openlibrary/bookworm/registry.py` — `FeedRegistry` (`feed_registry` table, no `tbp_`) with per-feed connector config (id strategy + cursor style).
- `openlibrary/bookworm/harvest.py` — fetch (per-feed cursor: rel=next+client filter for BWB/Lenny; `modified_since` query-param for Gutenberg) → submit to `import_item`.
- `openlibrary/bookworm/server.py` + compose `bookworm` service — FastAPI, 5-min background loop, `/health` `/harvest` `/feeds`.
- `search.json` weave — `Acquisition.get_by_editions` batch + `add_acquisitions`, gated on the `acquisitions` field.

## Not done yet
- End-to-end live run against `compose.near-prod.yaml` (in progress) — the DoD gate.
- Deferred to v2 (per review): separate bookworm db; `openlibrary/bookworm/` consolidation is done, but db routing stays OL for v1; `import_item.ia_id` rename; `manage-imports` dual-source.

Part of #12844.
