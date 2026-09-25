# #9836 investigation: how cover archival lost covers_0014_62

> **On master before this PR** (`df4a7a7c3`) the mechanism below is live. It is dormant only
> because archival has uploaded nothing since 2024-08-26. **Do not restart archival on that code**,
> as #13287 asks, because doing so re-arms it. This PR fixes it in `openlibrary/coverstore/archive.py`;
> the safe procedure is in `openlibrary/coverstore/README.md`.

## What was lost

**Up to 5,927 covers: IDs 14,624,073–14,629,999.** The figure is "up to" because it counts IDs, and
this investigation has not confirmed that every ID in that range was assigned. The ID space is dense
(#13287 measured 99.99% use in a neighbouring range), so the real figure is probably close to 5,927.

"~10,000" is the batch size (`BATCH_SIZE = 10_000`), not the loss. Mek's 2024-09-16 estimate on
#9836 was "5k or so", which matches.

Evidence, from public archive.org data (run with `census.py`, below):

| zip (all four tiers identical) | covers | id range | uploaded |
|---|---|---|---|
| `covers_0014_61.zip` (control) | 10,000 | 14,610,000–14,619,999 | 2024-05-07 |
| **`covers_0014_62.zip`** | **4,073** | **14,620,000–14,624,072, no internal gaps** | **2024-05-07** |
| `covers_0014_63.zip` … `_68.zip` | 10,000 each | | 2024-08-26 |

The cover from the #9836 report, 14627720, is not in `covers_0014_62.zip`.

**Reading:** on 2024-05-07, batch 62 was the live tail. Covers 14,620,000–14,624,072 existed; later
IDs in its range had not been created yet. The batch was zipped and uploaded as it stood. Covers
created after that were never uploaded, and their local files were later deleted.

## The mechanism

Line numbers are for `openlibrary/coverstore/archive.py` at `df4a7a7c3`. `ast_diff.py` confirms
this logic is unchanged in behaviour since #9296 (merged 2024-05-22, `16681e1d2`): of 40 functions,
3 differ, and each difference is behaviour-preserving (`not len(x)` to `not x`, an unused
variable removed, a no-op `with open(...)` removed).

### The chain, in one sentence

`process_pending` checks completeness (`is_zip_complete`) only before an **upload**. The **delete**
(`finalize`) is gated by nothing but "a file with this name exists on archive.org", so it runs at
exactly the moment the completeness check would fail, and the local and remote copies are never
compared again.

### Run by run

- **Run N (2024-05-07):** `archive()` zips batch 62 while it is still the open batch (4,073 covers).
  `is_zip_complete` compares the zip only with covers archived so far, so it passes, and the zip is
  uploaded. There is no finalize this run, because the names weren't on archive.org when checked.
- **Between runs:** covers 14,624,073–14,629,999 are created.
- **Run N+1 (by 2024-08-26):** `archive()` picks batch 62 again, appends the new covers to the local
  zip and marks them archived. `process_pending` finds all four names on archive.org and skips
  `is_zip_complete`. `finalize` deletes local files for all of them and marks them uploaded. The
  local zips, the only other copy, are deleted.

**Evidence this path fired, not another.** Lost covers 14627720 and 14629990 redirect today to
`l_covers_0014_62.zip`, as 14624072 (the last one that made it in) does. RAN 2026-09-25 with
`curl -sI https://covers.openlibrary.org/b/id/<id>-L.jpg`. The coverstore redirects only rows marked
`uploaded` (`code.py:373`), and the only code anywhere that sets `uploaded=True` is
`update_completed_batch` (`archive.py:287` at `df4a7a7c3`), which touches only rows marked `archived`.
So the lost covers went through `archive()` into the local zip and were then finalized. Batch 63 was
uploaded 2024-08-26, and `archive()` cannot reach it while batch 62 has unarchived covers.

### The flaws

Two were necessary for this incident (1 and 2). The third is real but did not fire here: every lost
cover was archived.

1. **No tail guard.** `archive()` (:351) with no arguments calls `get_batch_unarchived()`, which
   picks the batch of the lowest unarchived cover (`_get_current_batch_start_id`, :250). Nothing
   checks that cover IDs have moved past the batch's end, so the batch still being filled can be
   archived. `is_zip_complete()` (:155) then compares the zip against the rows archived *so far*,
   so a partial tail batch reads as complete and is uploaded (:122-125).

2. **"Uploaded" means "a file with this name exists".** `Uploader.is_uploaded()` (:56-68) runs
   `ia list {item} | grep "{filename}" | wc -l` and checks for 1. It does not compare file count or
   checksum against the local zip. Once a partial zip is on archive.org, every later run treats the
   batch as uploaded, so `process_pending()` never re-uploads it (:116-125) and sets
   `batch_complete` (:109, :119).

3. **`finalize` deletes covers that were never archived.** *(Did not fire in 2024.)* `finalize()` (:180) selects
   `failed=False, uploaded=False` (:184). **It does not filter on `archived=True`.** For every cover
   in the 10,000-ID range that has files on disk, it deletes them (:195, via `delete_files`, :328).
   `update_completed_batch()` (:280) then repoints only rows with `archived=true` (:285) at the zip.
   Rows left out keep pointing at files that no longer exist. `process_pending` then deletes the
   local zips (:132-139), which held the only other copy of covers archived after the upload.

No manual step is required, and the same sequence works on a manual run.

**Not established:** whether the 2024-05-07 upload came from a manual run or from pre-merge code.
It predates #9296's merge by 15 days. The mechanism is the same either way.

## Other short batches are a different class

`census.py` over all 669 full-size zip-era batches (`covers_0008`–`covers_0014`, 2026-09-24):

- 638 hold 10,000 covers.
- 30 are short by 1–15 (e.g. `covers_0011_27.zip`: 9,985).
- 1 is short by 5,927: `covers_0014_62.zip`.

The small shortfalls have **internal gaps** spread through the range (e.g. `covers_0014_29.zip`:
full range 14,290,000–14,299,999, 6 holes). Batch 62 has **no gaps and simply stops**. The likely
explanation for the small ones is that `archive()` marks a cover `failed=True` when its files are
already missing (:365-368) and leaves it out of the zip. **That is inferred from the code and not
verified against the database.**

## Test coverage

`git grep -w` over `openlibrary/coverstore/tests`, `tests` and `scripts` on master: nothing
references `finalize`, `process_pending`, `update_completed_batch` or `delete_files`. Positive
control: the same search finds `get_relpath` in `openlibrary/coverstore/tests/test_archive.py`.

Every non-test call site in `openlibrary/coverstore` that removes files (`os.remove`, `unlink`,
`rmtree`) was enumerated: 5 sites. Only `finalize` → `delete_files` removes images for covers that
already have a database row. The other sites delete local zips after `finalize`
(`archive.py:139`) or clean up after a failed image write in `coverlib.save_image`
(`utils.rm_f`). This covers coverstore Python only, not crons in `olsystem` or manual operations.

## Relation to #8251

#8251 (Drini, draft, 2023-08-31) is a clean-up refactor of this module: a `Cover` dataclass,
`ZipManager` as a context manager, and Python in place of the `ia list | grep` and `unzip | wc`
shell pipelines. It **does not change any of the three flaws above.** `is_uploaded` stays a
name-presence check (now exact-match rather than substring), `finalize`'s query is unchanged, and
there is no tail guard. It is 6,099 commits behind master and `git merge-tree` reports 3 conflicts
(`archive.py`, `code.py`, and `tests/test_archive.py`, which the PR deletes and master modified).

This PR takes from #8251 the parts that bear on safety: the exact-match archive.org lookup through
the `internetarchive` API instead of `ia list | grep`, counting zip members with `zipfile` instead of
`unzip -l | grep | wc`, and `ZipManager` as a context manager. It leaves the rest (the `Cover`
dataclass, the doctest conversion, removing unused `ZipManager` methods) for #8251 to carry on top.

## The fix in this PR

Each flaw gets its own guard, and each guard has a test that fails without it:

| Flaw | Guard | Caught by |
|---|---|---|
| 1. No tail guard | `archive()` stops at the open batch; `is_zip_complete` reports `batch_open` for a leftover zip of it | `test_open_batch_is_not_zipped_or_uploaded`, `test_leftover_zip_of_open_batch_is_not_uploaded` |
| 2. Name-only check | `process_pending` compares md5 with the local zip and re-uploads on mismatch; `finalize` re-checks for itself (`is_verified`) | `test_partial_copy_on_archive_org_is_replaced_not_trusted`, `test_finalize_refuses_by_itself_when_archive_org_differs` |
| 3. Unfiltered delete | `finalize` deletes only `archived` covers, and only ones present in the verified zips | covered by `is_verified` requiring nothing left to archive; no test can reach it separately |
| `test=True` still uploaded | uploads and finalize both honour `test` | `test_dry_run_changes_nothing` |

`test_recipe_keeps_covers_added_after_their_batch_was_first_archived` replays the 2024 sequence
through the recipe itself. On master it loses exactly the covers added after the first upload.

## Reproducing

```bash
# Census (read-only GETs to archive.org; about 10 minutes for all 669 full-size zips)
python docs/investigations/9836-cover-archival/census.py 0008 0009 0010 0011 0012 0013 0014 --only-short --ranges
# Positive control: 0014 must show _62 = 4073 and must not list _61
python docs/investigations/9836-cover-archival/census.py 0014 --only-short

# Behaviour diff of archive.py since #9296
python docs/investigations/9836-cover-archival/ast_diff.py 16681e1d2 origin/master openlibrary/coverstore/archive.py
```
