# #9836 investigation: how cover archival lost covers_0014_62

> **This is an investigation, not a fix.** Nothing in this directory changes runtime code.
> The fix belongs in a separate PR, and nobody has authorised one yet.

> **The mechanism is live on current master** (`df4a7a7c3`, 2026-09-25). It is dormant only
> because cover archival has uploaded nothing since 2024-08-26. **Restarting the archival cron,
> as #13287 asks, re-arms it.**

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

Three flaws, each necessary:

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

3. **`finalize` deletes covers that were never archived.** `finalize()` (:180) selects
   `failed=False, uploaded=False` (:184). **It does not filter on `archived=True`.** For every cover
   in the 10,000-ID range that has files on disk, it deletes them (:195, via `delete_files`, :328).
   `update_completed_batch()` (:280) then repoints only rows with `archived=true` (:285) at the zip.
   Rows left out keep pointing at files that no longer exist. `process_pending` then deletes the
   local zips (:132-139), which held the only other copy of covers archived after the upload.

Sequence for batch 62: partial upload on 2024-05-07 (1+2) → later covers archived into the local
zip only, or not at all → next run: `is_uploaded` true for all four tiers → `finalize` deletes
their files (3). No manual step is required, and the same sequence works on a manual run.

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

Recommendation: a small fix PR first, then #8251 refreshed on top as clean-up. A fix needs all three:

- `is_uploaded`, or a new check, compares file count and md5 with the local zip (archive.org
  metadata publishes md5).
- `finalize` selects only `archived=True` rows and refuses to delete anything unless the remote zip
  matches the local one.
- `archive()` skips any batch whose range the highest cover ID has not yet passed.

## Reproducing

```bash
# Census (read-only GETs to archive.org; about 10 minutes for all 669 full-size zips)
python docs/investigations/9836-cover-archival/census.py 0008 0009 0010 0011 0012 0013 0014 --only-short --ranges
# Positive control: 0014 must show _62 = 4073 and must not list _61
python docs/investigations/9836-cover-archival/census.py 0014 --only-short

# Behaviour diff of archive.py since #9296
python docs/investigations/9836-cover-archival/ast_diff.py 16681e1d2 origin/master openlibrary/coverstore/archive.py
```
