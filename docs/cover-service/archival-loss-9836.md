# Cover archival: how covers_0014_62 lost covers, and the guards against it

> **Status:** compiled
> **Sources:** investigation for internetarchive/openlibrary#9836, fixed in #13725; archive.org item metadata; public covers API
> **Last ingested:** 2026-09-25

In 2024, cover archival deleted the only copies of up to 5,927 covers. This page records the mechanism,
the evidence, and what #13725 changed, so that "is it safe to run archival?" has a checkable answer.
The procedure itself lives in the repo: `openlibrary/coverstore/README.md`, *Running cover archival safely*.

---

## What was lost

**Up to 5,927 covers: IDs 14,624,073–14,629,999.** **Not all of them are lost** (sample, RAN 2026-09-30 by #13765): of 5
sampled missing IDs, 3 point at the zip that lacks them (lost from archive.org, with no local
file), and 2 (14625555, 14627036) still point local and serve 200. Those 2 were never archived,
not deleted. So the range is a mix of lost and never-archived covers. The split is **unmeasured**
(n=5; sizing it would take ≈5,927 requests). "~10k" is the batch size (`BATCH_SIZE = 10_000`),
not the loss. The figure is "up to" because it counts IDs, and the ID space is dense but not verified
full.

`covers_0014_62.zip` on archive.org holds exactly **4,073** covers (14,620,000–14,624,072, contiguous,
no gaps), identical in all four sizes, uploaded **2024-05-07**. Its neighbours hold 10,000 each;
`_63`–`_68` were uploaded 2024-08-26.

**Not every ID in the range is lost** (sample, 2026-09-30, from a live run of the #13765 checker). Of 5 evenly spaced missing IDs,
3 have `filename` = `covers_0014/covers_0014_62.zip` and redirect into the zip (14624073, 14628517,
14629999). The other 2 (14625555, 14627036) still point at a local date path and serve: HEAD
`-L.jpg?default=false` → 200. So the range mixes covers that are redirected and lost with covers still
on local disk and unarchived. The split is unsized: sizing it takes one public read per ID (5,927).

## The mechanism (archive.py before #13725)

**The chain:** `process_pending` checked completeness (`is_zip_complete`) only before an **upload**.
The **delete** (`finalize`) was gated by nothing but "a file with this name exists on archive.org"
(`ia list | grep`), so it ran at exactly the moment the completeness check would have failed.

- **Run N (2024-05-07):** `archive()` zipped batch 62 while it was still the open batch.
  `is_zip_complete` compared the zip only with rows archived *so far*, so it passed and the zip was
  uploaded.
- **Run N+1 (by 2024-08-26):** `archive()` appended the batch's new covers to the local zip.
  `process_pending` saw all four names on archive.org, never called `is_zip_complete`, and finalized:
  local files deleted, rows marked `uploaded`, local zips (the only other copy) deleted.

Two flaws were necessary: no guard against archiving the open batch, and a name-only check before
deleting. A third, `finalize` not filtering on `archived=True`, is real but **did not fire**.

**Evidence it was this path.** Lost covers 14627720 and 14629990 redirect to `l_covers_0014_62.zip`,
like 14624072, the last one that made it in (`curl -sI https://covers.openlibrary.org/b/id/<id>-L.jpg`,
2026-09-25). The redirect requires `uploaded` (`code.py`), and the only code that sets it,
`update_completed_batch`, touches only archived rows. So they were archived, then finalized.

**Not established:** whether run N was manual or pre-merge code. It predates #9296 by 15 days.

## Other short batches are a different class

A census of all 669 full-size zip-era batches (`covers_0008`–`covers_0014`, 2026-09-24): 638 hold
10,000, 30 are short by 1–15, and `covers_0014_62` is short by 5,927. The small shortfalls have
**scattered internal gaps**; batch 62 **simply stops**. That fits covers marked `failed` for missing
files, but it is inferred from code and not checked in the db.

## What #13725 changed

| Flaw | Guard |
|---|---|
| Open batch archived | `archive()` stops at the batch holding the newest cover; `is_zip_complete` reports `batch_open` for a leftover zip of it |
| Name-only check | "complete" means the zip's names equal the batch's archived covers plus any already uploaded, with data passing `testzip`; `finalize` verifies archive.org's md5 itself, after reading the zip entries |
| Unfiltered delete | `finalize` deletes a local file only if it matches its zip entry (size and CRC); repoints then deletes one cover at a time, only if that row updated |
| "Dry run" uploaded | `test=True` stops uploads and finalize alike |
| Concurrent runs (review) | `archival_lock()`, a flock on `items/.archive.lock`, around every writing step |
| Covers below 8M would stop serving (review) | `MIN_ARCHIVABLE_ID`, shared with `code.py`'s redirect. **A floor, not a guarantee:** covers ≈7.14M–8M have no archive.org copy (the `olcovers` dumps stop at ≈7.14M, per #476; `covers_0007` doesn't exist), so they stay single-copy. Measured in #13769; see [epic #13803](https://github.com/internetarchive/openlibrary/issues/13803). |
| Smaller copy replacing archive.org's (review) | no upload over a larger or unknown-size remote file; `archive()` skips covers that already point at a zip |

**A complete local zip replaces a partial archive.org copy**, even for a finalized batch. If
`covers_0014_62`'s 2024 zips survived on the cover server, following the runbook restores the lost covers.

`openlibrary/coverstore/tests/test_archive_safety.py` has 30 tests against Postgres. On the old code the
2024 sequence loses exactly the late covers. Against the old `archive.py`, 12 tests fail for the behaviour
they test, 14 fail because the code they exercise did not exist, and 4 pass. 29 of 31 single-guard
mutations are caught; the other 2 are a pair that back each other up, caught together.

**Seven adversarial review rounds on #13725** found 6 loss paths, and 3 of those were
introduced by the fix's own drafts: a NULL-`uploaded` row; a re-queued finalized batch after a guard was
removed; and a hand-edited filename after a redundant-looking guard was cut. The last is the lesson worth
keeping: **a guard whose removal no test catches is a missing test, not an unnecessary guard.** The final
verdict on #13725 at its then-head `e9d3e4c72` (unmerged): safe to merge from a data-loss standpoint.

## Open questions

The questions that need host or database access, including whether batch 62's 2024 zips survive, are tracked in [epic #13803](https://github.com/internetarchive/openlibrary/issues/13803) (*Open questions*). Answers belong there first, then here if they change this record.

## Public instrument facts (measured 2026-09-29/30, while building #13765)

Things that make a naive public check lie:
- **`default` defaults to true on the image route.** `/b/id/999999999-L.jpg` answers **200** with a
  43-byte placeholder GIF; with `?default=false` it is a 404. Only a 200 *with* `default=false` means served.
- **archive.org answers a missing item with 200 and `{}`** (`/metadata/covers_0015`). Reading `files`
  from it gives zero zips. Treat it as unknown, never as "holds nothing".
- **`filename` has three shapes:** a zip (`covers_0014/covers_0014_NN.zip`), a local date path
  (`YYYY/MM/DD/OL…M-xxxxx.jpg`), or no record (404). On master the redirect is gated on `uploaded`
  (`code.py`), and its target is computed from the ID, not from `filename`, so `filename` is a proxy.
  It agreed with the live 302 for both controls.
- **The small-short class is two things.** In `covers_0014`, 6 of the 7 short-by-1–6 zips have missing
  IDs that are 404 (no record). The 7th (`_26`, ID 14268717) points local, and HEAD with `default=false`
  is 404: the file is gone locally and was never archived.
- A zip listing names each cover twice (href and text), so count distinct IDs.

## Tools

These live in PR #13725's history (commit `8cf85be17`, unmerged), not in the KB.

Kept at the commit that added them rather than in the repo:
- [`census.py`](https://github.com/internetarchive/openlibrary/blob/8cf85be17/docs/investigations/9836-cover-archival/census.py):
  counts covers per bulk zip from public archive.org listings, with `--only-short --ranges`.
  Positive control: `census.py 0014 --only-short` must show `_62 = 4073`.
- [`ast_diff.py`](https://github.com/internetarchive/openlibrary/blob/8cf85be17/docs/investigations/9836-cover-archival/ast_diff.py):
  reports behaviour-level function changes in a file between two git refs.
- `scripts/monitoring/cover_archival_check.py` (#13765): the W1 checker, with live controls.
- The full investigation write-up at the same commit:
  [`README.md`](https://github.com/internetarchive/openlibrary/blob/8cf85be17/docs/investigations/9836-cover-archival/README.md).
