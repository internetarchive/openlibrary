# First Edits: non-IA identifiers

*Branch `FirstEdits`. Written 2026-09-23, in answer to Lisa's "non-ia identifiers" in the Slack thread about what a newcomer's first contribution should be. Built as a walkthrough so the conversation has something to click, not to settle the question.*

## 1. What "non-IA identifiers" means here

Nearly every Open Library record traces back to the Internet Archive: it has an `ocaid` and whatever an IA-derived MARC import gave it, and nothing pointing anywhere else. The non-IA identifiers are the outward ones — the `identifiers` dict plus the top-level `isbn_10`, `isbn_13`, `lccn` and `oclc_numbers` fields.

This pass offers **two**, both edition-level library identifiers:

| Field | Label | Why this one |
|---|---|---|
| `lccn` | Library of Congress number | We already fetch the record it comes from, and it is the strongest signal in record matching |
| `oclc_numbers` | OCLC/WorldCat number | The canonical cross-library identifier, and what a librarian most wants filled |

Goodreads, LibraryThing and Wikidata are deliberately out. Wikidata is work-level, which needs a work-level task; Goodreads and LibraryThing have no open API, so nothing can check the answer.

## 2. Why an identifier task is not shaped like a page-count task

Every other First Edits field is a property of the book. The page count is on the last numbered page; catalogs are witnesses to it, and when two agree we call it strong.

An identifier is not a property of the book. It is a pointer into somebody else's catalog, and it is correct **if and only if the record at the other end describes this edition**. That difference has three consequences, and they drive the whole design.

**Source agreement is circular.** "The Library of Congress says the LCCN is 2006049772" is not evidence — of course their record carries its own number. Counting sources, the way `evidence.py` does for every other field, measures nothing here.

**So confidence comes from corroboration instead.** `tasks.corroboration()` compares the *target record's* year, publisher, page count and language against our edition using the comparators already in `compare.py`. Three or more agreeing details is Strong; two is Fair; any disagreement drops it to Weak, and Weak never becomes a task. The three-bar meter is unchanged — only what feeds it.

**So the page argues about the record, not the number.** The wizard leads with the record's details next to ours, field by field, with a tick or a cross on each. The question is "is this the same edition?", not "is this string right?". The contributor is making a recognition judgment, which a newcomer can actually make, rather than a transcription they have no way to verify.

## 3. How this goes wrong

Eight failure modes, ordered by how often a newcomer will hit them. The four marked **checked** are enforced in code and shown on the page as passing or failing; the rest are printed under "How this edit goes wrong" and honestly labelled *Only you can check this one*.

1. **The popular-edition trap** — *checked*. Search results rank by popularity, so the first hit is the mass-market paperback, not the 1987 hardcover on the page. Caught by the year/publisher comparison.
2. **Work versus edition** — *not applicable here, by design*. Goodreads, LibraryThing and Wikidata each have both levels, and a `/work/` id is not an edition id. Both identifiers in this pass are edition-only, which sidesteps it; any future namespace re-opens it.
3. **Format and prefixes** — *checked*. `ocm`, `ocn`, `on` and `(OCoLC)` are padding from library systems, not part of the number. Hyphenated and zero-padded LCCNs are the same number.
4. **Pasting the URL** — *checked*. Already a known problem in Open Library: `library-metadata-standards.md` records "confusion over ASIN and OCAID where users sometimes paste URLs instead of ids."
5. **Already taken** — *checked*. If a sibling edition already carries the number, one of the two records is wrong or they are duplicates. The scan is local and cheap.
6. **Reprints filed together** — *not checked*. One LCCN or WorldCat record can cover several printings. Year and publisher matching is as far as anyone can go.
7. **Format confusion** — *partly checked*. A Kindle ASIN, an audiobook, or an ebook record is a different edition. Caught only when the record states a differing detail.
8. **The right answer is often "nothing"** — *structural*. A wrong identifier is worse than a missing one, so "No — that record is a different edition" is a first-class answer with the same visual weight as yes, and is described on the page as "a useful answer, not a failure."

Answers that **add** an identifier are gated behind an explicit tick: *I opened the record and the year and publisher match this edition.* Answers that add nothing are not gated — saying no has to stay the cheapest thing on the page.

## 4. Why a wrong one is expensive

Worth stating plainly to contributors and librarians, because the wiki never does. Both identifiers are join keys in `openlibrary/catalog/add_book/`:

- `build_pool` searches on `("title", "oclc_numbers", "lccn", "ocaid")`, so both fields decide which existing records a new import is compared against.
- `match.py` scores an LCCN match at **+200** and an LCCN *mismatch* at **−320**, against a match threshold of 875. It is the strongest single-field signal in the system.

So a wrong LCCN does not merely sit there being wrong. It actively blocks a correct merge, and it does so silently, for years. That is the sentence the playbook's `why` is built on.

## 5. What the wiki already says, and what it doesn't

`docs/wiki/librarians/guide-to-identifiers.md` is the canonical page. It is a reference table — OCLCid, LCCN, OLID, OCAID, HTID, Google ID with one example each — opening with a caveat that its basis has been frozen since 2007. Nothing links to it from elsewhere in the wiki.

What it does **not** cover, all of which this walkthrough had to invent copy for:

- No rule for which identifiers belong on the work versus the edition. There is no work identifier table at all, and the page's own example JSON puts Goodreads and LibraryThing at edition level while `config/work/identifiers.yml` defines them as work-level.
- No format guidance for LCCN (hyphens, zero-padding, the `rev` suffix) or OCLC (the `ocm`/`ocn`/`on` prefixes), although the validators enforce both.
- No instruction not to paste URLs — it is recorded as a known problem, never as a rule.
- No warning that identifiers drive deduplication. The matching order and the penalty weights above appear nowhere outside the code.
- ISBN is missing from the Edition Identifiers table entirely.

`library-metadata-standards.md` asks for exactly what this page does: "Whether the URL or just the basic id is the input, the full URL ought to be resolved and validated at edit time" and "A preview would help."

**If the identifier tasks ship, `guide-to-identifiers.md` should be rewritten alongside them.** The playbook copy is a reasonable first draft of the missing sections.

## 6. What the data says — and it is the awkward part

Measured against the 53-edition demo set on 2026-09-23, querying the Library of Congress SRU endpoint that phase 2 plans to use.

| Measure | Result |
|---|---|
| Demo editions the Library of Congress holds at all | **7 of 26 queried** |
| Of those, records carrying an LCCN | 7 of 7 |
| Of those, records carrying an `(OCoLC)` number in MARC 035 | **2 of 7** |
| Dev editions that already have an LCCN | 8 of 15 resolved |
| Dev editions that already have an OCLC number | 8 of 15 |

Three things follow, and they are the substance of the librarian conversation:

**OCLC cannot be sourced from the Library of Congress at scale.** Only some LoC records carry `(OCoLC)` in 035. Without a WorldCat API key, an OCLC task is human-search-and-paste, which is the shape with the worst error rate. The two OCLC numbers in the walkthrough are real and came free; most books will not offer one.

**LCCN coverage collapses on anything not published in the United States.** The demo set is deliberately international, and LoC simply has no record for most of it. The books where Open Library is missing an LCCN are overwhelmingly the books where no US library catalog can supply one.

**The gap and the supply barely overlap.** The editions that already have an LCCN have it because they came from a library MARC import. The ones missing it are missing it because no such import exists. On this demo set the honest yield of an automatic LCCN fill task is close to zero — the one walkable case had to be opened by clearing a real identifier from a dev record.

That is not an argument against identifier work. It is an argument that the valuable identifier work is **not** the case a script could do anyway. It is the judgment cases: no ISBN, pre-ISBN books, several Open Library editions sharing one ISBN, a source record that disagrees on year. Those are exactly the cases this wizard is shaped for, and exactly the ones that need a librarian behind them.

It is also a concrete answer to mek's framing question. Of the fields on his list, language, page count and publisher have broad supply. Identifiers do not, and that is worth knowing before anyone promises volunteers a queue of them.

## 7. Open questions for librarians

1. **Is OCLC worth a human-search task** given nothing can verify the answer, or does it wait for a WorldCat key?
2. **Is three corroborating details the right bar** for Strong, or should an identifier need the year *and* the publisher specifically?
3. **Should a disagreeing identifier be surfaced at all?** Today an edition whose LCCN differs from the source is silently not a task. Gatsby in the dev set carries the 1925 registration number on a 2004 printing — a real, visible error that no newcomer flow will ever report.
4. **Which namespace next?** Wikidata would force the work/edition split into the UI; Goodreads has the most reader-facing value and the least verifiability.
5. **Does `guide-to-identifiers.md` get rewritten** as part of this, and by whom?

## 8. Implementation notes

- `openlibrary/utils/oclc.py` is new: `normalize_oclc`, the Python counterpart of `parseOclc`/`isValidOclc` in `idValidation.js`, which previously had no server-side equivalent. It strips `(OCoLC)`, `ocm`/`ocn`/`on`, whitespace, hyphens and leading zeros.
- `openlibrary/first_edits/identifiers.py` holds the two specs, the three checks, and the record-comparison rows.
- The client reuses `idValidation.js` so the verdict under the input matches what the server would store; the messages come from `data-msg-*` attributes so they stay translatable.
- Two icons were added to the set, `triangle-alert` and `circle-alert`; the sprite was rebuilt.
- Scope lives in `scope.json` as `"lccn"` and `"oclc_numbers"`, both `fill` only at `min_level: strong`. A value that *disagrees* with ours is a conflict for a librarian, never a newcomer task.

**For phase 3, the one real trap in the write path:** `Edition.set_identifiers` (`plugins/upstream/models.py`) is a total replace. It clears all five top-level identifier fields and rebuilds `identifiers` wholesale, so an "add one identifier" path must read the full set, append, and write it all back. The existing `work_identifiers` endpoint in `addbook.py` does *not* do this and would wipe an edition's other identifiers — it should not be copied as a template.

## 9. Trying it

The walkthrough needs an edition that is missing one of the two identifiers but has a Library of Congress record. The demo set has none naturally, so open one:

```bash
# Clear the identifiers on Ruptured Histories (OL2302M) in dev.
curl -s -b /tmp/cookies.txt "http://localhost:8080/books/OL2302M.json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for f in ('latest_revision', 'revision', 'created', 'last_modified'): d.pop(f, None)
d.pop('lccn', None); d.pop('oclc_numbers', None)
print(json.dumps([d]))" > /tmp/ed.json

curl -s -b /tmp/cookies.txt -X POST "http://localhost:8080/api/save_many" \
  -H "Content-Type: application/json" \
  -H 'Opt: "http://openlibrary.org/dev/docs/api"; ns=42' \
  -H "42-comment: dev: open the First Edits identifier task" \
  --data-binary @/tmp/ed.json
```

Then `/contribute/task/OL2302M/lccn` and `/contribute/task/OL2302M/oclc_numbers`. Both show Strong, three details matching, and all four machine checks passing.
