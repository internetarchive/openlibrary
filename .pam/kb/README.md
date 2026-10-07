# Open Library Knowledge Base

This Project's knowledge base: how each subsystem actually behaves, verified against the source.
Obsidian-style markdown with `[[wikilinks]]`. It is committed with the repo and reads on its own:
you do not need to run pam or cmux to use it.

This KB consolidates what used to live in three places — the in-repo `docs/ai/` guides, the external
`mekarpeles/openlibrary-kb` repo, and `.pam/kb` — into one in-repo source of truth. Staff/fleet-only
operational material (the old `openlibrary-kb/internal/`) is intentionally **not** here; it belongs in
`olsystem`'s private `.pam`. See [`decisions/kb-reconciliation.md`](decisions/kb-reconciliation.md) for
the background.

Start here:

- [`ai-coding-guide.md`](ai-coding-guide.md) — the canonical AI-agent engineering reference (setup,
  build, testing, architecture, code style, key file locations). The root bridge files (`AGENTS.md`,
  `CLAUDE.md`, `.github/copilot-instructions.md`) point here.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — conventions for adding or editing a KB page.

## Sections

| Directory | What's in it |
|---|---|
| [core/](core/) | Infogami, FastAPI, the database, internal APIs, auth, OTP service |
| [imports/](imports/) | How records enter the catalog — BookWorm, feed registry, the import contract, add-book internals, MARC encoding, validation |
| [cover-service/](cover-service/) | Coverstore and cover archival |
| [search/](search/) | Solr indexing, query parsing, text analysis, schema priorities |
| [tags/](tags/) | The Tags data/vocabulary system (genres, subgenres, audiences), dev setup, known issues |
| [librarians/](librarians/) | The Librarians System — editing UI, merge tools, micro-edits |
| [lending/](lending/) | Lending & trusted book providers, including Lenny |
| [i18n/](i18n/) | Translation pipeline and rendering |
| [opds/](opds/) | OPDS feeds |
| [frontend/](frontend/) | Web components, CSS, design, accessibility, BookReader, Library Explorer |
| [client-and-bots/](client-and-bots/) | `openlibrary-client` and bots |
| [analytics/](analytics/) | Analytics, client-side events, Core Vitals |
| [public-apis/](public-apis/) | Public APIs and partials |
| [features/](features/) | Reading log, ratings, activity feed, lists, follows |
| [decisions/](decisions/) | Durable decisions for this KB and the pam Project |

## Rules

- One note per file, named in kebab-case; link related notes with `[[note-name]]`, and link liberally.
- One topic = one directory, each with a `README.md` overview. Keep overviews high-level; deep dives
  live as named sub-documents linked from the `README.md`.
- Keep each note to one idea; put the specifics in the note, not in this index.
- **In-flight effort/issue progress does not live here** — it lives in the corresponding GitHub epic.
  These pages describe how systems *work*, not the status of the work on them.
- This KB is the Project's durable knowledge: decisions, how-tos, gotchas, references.

*This index is only as good as its last update — when you add a page, add it to its directory's
`README.md` in the same commit.*
