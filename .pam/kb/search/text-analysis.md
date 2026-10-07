# Search: Text Analysis and Stopwords

> **Status:** compiled
> **Sources:** `openlibrary/conf/solr/conf/managed-schema.xml`, issues [#5393](https://github.com/internetarchive/openlibrary/issues/5393) / [#3317](https://github.com/internetarchive/openlibrary/issues/3317), PR [#4337](https://github.com/internetarchive/openlibrary/pull/4337), empirical testing against `solr:10.0.0` with OL's configset
> **Last ingested:** 2026-08-10

How Open Library turns text into searchable tokens, why stopword filtering is currently switched **off**, and how to test a change to it. Companion to [[search]].

---

## How It Works

### Two chains, not one

Every Solr text field is analyzed twice, by two separately-configured chains:

- the **index** chain runs when a document is written; whatever it emits is what gets stored
- the **query** chain runs when someone searches; whatever it emits is what gets looked up

They are deliberately configured differently. That is normal — but it means a change to one can silently break matching against the other.

### Positions, and why they decide phrase matching

Each token carries a **position**. A phrase query matches only when every query token is found in the index at the same relative position. So the two chains must agree on positions, not merely on which words survive.

This is the crux of the stopword problem. Removing a word does not renumber the ones after it — it leaves a *hole*. "The Mark of the Crown" with stopwords removed becomes `mark@2 crown@5`, not `mark@1 crown@2`. If one chain preserves those holes and the other collapses them, the terms still match but the phrase does not.

### OL's chain for `text`

The `text` field uses fieldType **`text_en_splitting`** (`managed-schema.xml`). Both chains, in order:

| # | index | query |
|---|---|---|
| 1 | whitespace tokenizer | whitespace tokenizer |
| 2 | — | synonymGraph (expand=true) |
| 3 | ~~stop~~ *(commented out)* | ~~stop~~ *(commented out)* |
| 4 | icuFolding | icuFolding |
| 5 | wordDelimiterGraph **catenateWords=1** | wordDelimiterGraph **catenateWords=0** |
| 6 | lowercase | lowercase |
| 7 | keywordMarker (protwords.txt) | keywordMarker (protwords.txt) |
| 8 | porterStem | porterStem |
| 9 | **flattenGraph** | — *(correctly absent)* |

Two asymmetries are intentional and worth internalising before touching anything:

- **`catenateWords` 1 vs 0.** Indexing "Spider-Man" stores an extra catenated `spiderman` so a query for either form matches. The query side does not produce it. The index legitimately holds *more* tokens than the query — so "the two streams differ" is not by itself a bug.
- **`flattenGraph` index-only.** Filters like wordDelimiterGraph and synonymGraph emit a *graph* (alternative paths). A Lucene index cannot store a graph, so flattenGraph collapses it at index time. The query side must **not** flatten — the query parser needs the graph to build the right alternatives. Adding flattenGraph to a query chain is a known anti-pattern.

### `stopwords.txt` vs `lang/stopwords_en.txt`

Two different files, easily confused:

- `conf/solr/conf/stopwords.txt` — referenced by several fieldTypes, and **contains no words at all**, only a license header. Those `stop` filters are no-ops.
- `conf/solr/conf/lang/stopwords_en.txt` — the real English list (33 words) used by `text_en_splitting`. It begins with two entries, `stopworda` and `stopwordb`, that appear to be leftover test fixtures rather than real stopwords.

### No searchable field filters stopwords today

The schema contains ~36 fieldTypes with a live `stop` filter, which makes it look like filtering is widely enabled. It is not. Every field OL actually searches uses one of two types, and neither filters:

| fieldType | Fields using it | `stop` status |
|---|---|---|
| `text_en_splitting` | `text`, `title`, `subtitle`, `alternative_title`, `subject`, `publisher`, `first_sentence`, … | **commented out** |
| `text_general` | `place`, `person`, `contributor`, `title_suggest`, `lccn`, `_text_` | active, but points at the **empty** `stopwords.txt` |

The other ~30 (`text_en`, `text_en_splitting_tight`, `text_de`, `text_fr`, `text_ja`, …) carry real per-language stopword lists but are **used by no field** — leftovers from Solr's sample schema. Do not read their presence as evidence that stopword filtering is on.

So the two types reach the same end state by different routes: one has the filter disabled, the other has it enabled against an empty list.

## Why It Exists

Stopword filtering drops very common words ("the", "of", "a") so they neither bloat the index nor dominate scoring. It is standard practice, and OL had it on.

It was **disabled** in PR [#4337](https://github.com/internetarchive/openlibrary/pull/4337) during the Solr 8 upgrade, because it broke queries — see [#3317 (comment)](https://github.com/internetarchive/openlibrary/issues/3317#issuecomment-837506502). Issue [#5393](https://github.com/internetarchive/openlibrary/issues/5393) tracks re-enabling it. The schema still carries the commented-out filters and a comment pointing at that history.

**The failure mode, precisely:** with two *consecutive* stopwords, the index chain collapsed the two position holes into one while the query chain kept both. A single stopword between terms was fine; two in a row broke.

## How It Is Used

### Reproducing the bug

`scripts/compare_solr_analysis.py` in the openlibrary repo prints both token streams and reports whether a phrase query can still match:

```bash
# against your local dev Solr
python3 scripts/compare_solr_analysis.py "The Mark of the Crown"

# compare a baseline core against a schema variant you are testing
python3 scripts/compare_solr_analysis.py --core openlibrary --vs mytest "The Mark of the Crown"
```

It exits non-zero when any input cannot phrase-match, so it works in a loop while iterating on the schema. It only compares *tokens that the query needs and the index lacks* — the catenation asymmetry above otherwise produces false alarms.

### Testing a schema change without a full reindex

The Analysis API needs no documents, so a bare Solr with OL's configset is enough for analysis-level work — far faster than reindexing:

```bash
docker run -d --name solr-test -p 8987:8983 -e SOLR_MODULES=analysis-extras \
    -v ~/some/configsets:/configsets:ro solr:10.0.0
docker exec solr-test bin/solr create -c mytest -d /configsets/my-variant
python3 scripts/compare_solr_analysis.py --url http://localhost:8987 --core mytest
```

Note the mount must live under `$HOME` if you use Colima — it does not mount `/tmp` into its VM.

For end-to-end behaviour (ranking, actual search results) this is **not** sufficient; see "Limits" below.

## Findings

Measured against `solr:10.0.0` running OL's configset, comparing three variants of `text_en_splitting`:

| Input | stopwords off *(today)* | naive re-enable | `stop` after `flattenGraph` |
|---|---|---|---|
| The Mark of the Crown | ok | **BROKEN** | ok |
| The Lord of the Rings | ok | **BROKEN** | ok |
| A Tale of Two Cities | ok | ok | ok |
| Spider-Man | ok | ok | ok |

**The naive re-enable reproduces the historical bug**, exactly as described in #5393: index emits `mark@2 crown@4` while query emits `mark@2 crown@5`. "A Tale of Two Cities" survives because it has only one stopword between terms — confirming the defect needs *consecutive* stopwords.

**Moving `stop` to after `flattenGraph`** (on both chains) makes all four cases pass. The mechanism: flattenGraph is what collapses the holes, so removing stopwords *after* it leaves the holes intact and both chains agree.

### The catch, unresolved

Placing `stop` after `porterStem` means stopwords are matched against **stemmed** tokens, while `stopwords_en.txt` is unstemmed. Four of the 33 entries then fail to match their own list and survive filtering:

```
are -> ar      they -> thei      this -> thi      was -> wa
```

So this placement fixes the position bug but silently weakens stopword removal by ~12%. Options not yet evaluated: stem the stopword list to match, place `stop` between `flattenGraph` and `porterStem`, or use `CommonGramsFilter` instead. **This is the open question**, not a solved problem.

## Limits of this analysis

Everything above is **analysis-time only** — it proves tokens and positions line up. It says nothing about:

- whether search *results* improve, or ranking shifts
- relevance scoring (`qf`/`pf` boosts interact with token counts)
- index size and query latency
- the other fieldTypes that reference the empty `stopwords.txt`

Those need the full local stack, a reindex, and a relevance evaluation pass. See [[search]] for local dev commands.

## Key Files

| File | Purpose |
|---|---|
| `conf/solr/conf/managed-schema.xml` | fieldType definitions; `text_en_splitting` is the one that matters |
| `conf/solr/conf/lang/stopwords_en.txt` | the real English stopword list (33 words) |
| `conf/solr/conf/stopwords.txt` | referenced by other fieldTypes; **empty of words** |
| `conf/solr/conf/protwords.txt` | words protected from stemming |
| `conf/solr/conf/synonyms.txt` | query-time synonyms |
| `scripts/compare_solr_analysis.py` | index-vs-query analysis diff harness |

## Common Confusion

- **"The token streams differ, so it's broken."** Not necessarily — the index side deliberately holds extra catenated tokens. Only tokens the *query* needs and the index lacks break a match.
- **"Just add flattenGraph to the query chain so they match."** No. The query parser needs the unflattened graph; flattenGraph is index-only by design.
- **"stopwords.txt is the stopword list."** It is empty. `lang/stopwords_en.txt` is the real one.
- **"Stopwords are removed today."** They are not — both filters are commented out. Searching for "the" currently matches the literal token.

## Related

- [[search]] — indexing flow, schemes, query construction, local dev commands
- [[development]] — local environment setup
