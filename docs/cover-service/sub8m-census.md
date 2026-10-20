# Covers 7.14M–8M: census of the single-copy range

> **Status:** compiled, measured 2026-09-30 (one run, 843 public HTTP requests)
> **Sources:** internetarchive/openlibrary#13769 ([results comment](https://github.com/internetarchive/openlibrary/issues/13769#issuecomment-5901972177)); covers.openlibrary.org; archive.org search and metadata; `coverstore/archive.py` and `code.py` on master
> **Script:** removed from the wiki on 2026-10-06 (code belongs in a repo, not the KB). It survives in the published wiki's history at `mekarpeles/openlibrary-kb@f3fdae1`, `covers/sub8m-census/census.py` (12,475 bytes). The seed reproduces the same 400 IDs.

Covers from 7,140,000 to 7,999,999 have no archive.org copy. The `olcovers` dumps stop below this
range, and the zip tier starts at `MIN_ARCHIVABLE_ID` = 8,000,000. This page gives the measured
size and layout of the range, so that the decision about archiving it rests on numbers.

**RAN** = measured in this run. **READ** = taken from code or documents. Sample: 10 equal strata of
86,000 IDs, 40 random IDs each (n = 400), seed 13769, 95% Wilson intervals. Controls passed first:
`240727` gave 200 and `99999999` gave 404, both on `HEAD -S.jpg?default=false` and on `.json`.

## The numbers

| | Result | Method, n |
|---|---|---|
| Density | **400/400 have a record**; overall 99.0–100%, each stratum 91.2–100% | RAN, `/b/id/N.json`, n = 400 |
| Count | **≥ ~851k** covers (lower bound × 860k IDs) | derived |
| Archive.org edge | `olcovers0`–`olcovers713`, and `olcovers714` returns `{}`, so the copy ends at 7,139,999 | RAN, advancedsearch and `/metadata` |
| Redirect edge | L at 7,129,999 → 302 to `olcovers712`; L at 7,139,999, 7.14M and 7.15M → 200 local. Redirect stops at 7,130,000, i.e. `max_coveritem_index` = 713, inferred from behaviour | RAN, HEAD, Location read and not followed |
| Tar / loose boundary | last tar **7,315,539** (`covers_0007_31.tar`, 2014-11-29); first loose **7,315,540** (2014-11-30) | RAN, bisection in 10 probes; 5+5 monotonicity probes; 0/400 wrong side |
| Tar-held | 7,140,000–7,315,539 = **175,540 IDs** in 18 local tars, `covers_0007_14`–`_31` | RAN; sample 81/400 = 20.3% vs 20.4% expected |
| Loose | 7,315,540–7,999,999 = **684,460 IDs** in local date directories, 2014-11-30 → 2017-06 | RAN |
| Serving | **400/400 serve**: 398 gave 200 on the first pass; 2 gave 502, then 200 on one retry | RAN, `HEAD -S.jpg?default=false`, only 200 counted |
| `failed` flag | **400/400 `failed = true`**; controls outside the range 5/5 `failed = false` | RAN |
| Concentration | **176/400 (44%, CI 39.2–48.9%)** created 2016-10-14, all in one directory, `2016/10/14/` | RAN |

## What it means for archiving

- **The whole range is flagged `failed`, and archival's own selection excludes it.** All four batch
  selectors in `archive.py` filter on `failed = false` (READ). Archiving this range means clearing
  or bypassing that flag deliberately, as well as lowering the 8M floor.
- **Here, `failed` doesn't mean the file is missing:** every sampled cover serves. Current code sets
  `failed` only on missing files, and then skips the cover without archiving it (READ). So the tar
  rows' `archived = true` combined with `failed = true` came from older code or a direct database
  change. Which of the two is not established; that needs database history.
- **One directory holds a large share of the range.** Sampled span 7,455,090–7,836,261; the samples
  on either side are dated 2016-10-07 and 2016-10-16. *Extrapolation:* if the span is contiguous,
  it is roughly 380k covers in one local directory, all single-copy. It is the largest concentration
  this census found, and the strongest argument for archiving the loose part first.
- The 7,130,000–7,139,999 block has an archive.org copy (`olcovers713`) that serving doesn't use.

## Created date against ID

`created` is strictly monotonic in ID (0 inversions in 399 adjacent pairs). Each loose file's
directory date equals its `created` day (319/319). IDs per day, estimated per stratum as the ID
span over the created-day span of its 40 samples:

| Stratum | Created | IDs per day |
|---|---|---|
| 0 | 2012-06 → 2012-08 | ~1,481 |
| 1 | 2012-08 → 2014-10 | ~99 |
| 2 | 2014-11 → 2015-12 | ~187 |
| 3 | 2016-03 → 2016-10 | ~369 |
| 4–7 | 2016-10-14 | the concentration above |
| 8 | 2016-10 → 2017-04 | ~449 |
| 9 | 2017-04 → 2017-06 | ~1,970 |

**This breaks the W6 backlog-sampling design's (#13766) "one ID per ~700 ≈ one day-directory" assumption for this era
only.** That stride was stated for IDs ≥ 8M, which this census did not measure. For W6(b)'s
7.14M–8M stratum, a lost day-directory ranges from a few hundred covers to ~380k, so sampling by ID
stride doesn't give even coverage of directories.

## Not measured

- The density and layout of anything outside 7,140,000–7,999,999. The 3.38M–3.69M redirect break
  found while checking the edges is #13770, not this page.
- Whether the local tars and directories have any backup on the host. Nothing here touched a host.
- Why and when the range was flagged `failed`.
- Whether `2016/10/14/` is contiguous between the samples. It is extrapolated from 176 samples and
  two bracketing dates.

## Reproducing

Run from a temporary directory outside the KB: the outputs hold filenames, which embed edition
and work IDs and are kept out of publication for data minimisation.

```sh
OUT="$(mktemp -d)"   # OUTSIDE any repo: outputs hold filenames, which embed OLIDs
for p in controls edges density flagcontrol boundary serving; do
    CENSUS_OUT="$OUT" python3 census.py "$p" || break
done
```

About 850 requests at ≥1.1 s spacing, roughly 16 minutes. The script refuses to go past 1,000
requests, counted from its own ledger.

**Never write the outputs inside this wiki.** They carry each cover's `filename`, which embeds an
edition or work ID. `publish-wiki.sh` publishes only committed files and refuses to run while `wiki/` has untracked ones, so the risk is committing them by accident.

**Provenance:** every number above came from the 2026-09-30 run. The phases were run as they're
written here, but `flagcontrol` and the serving retry were run as one-off snippets. **This committed
`census.py` has not been run end to end against the network**; it has made 0 requests. Offline, seed
13769 reproduces the same 400 IDs (seed 1, as a control, doesn't). Treat the first full rerun as a
test of the script, not only a measurement.

Related: [[archival-loss-9836]], #13766, and [epic #13803](https://github.com/internetarchive/openlibrary/issues/13803).
