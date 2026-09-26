# Coverstore README

## Running cover archival safely, one step at a time

Archival has three stages, and only the last one deletes anything:

1. **Archive**: `archive.archive()` copies covers from `localdisk/` into per-batch zips under `items/`
   and marks them `archived`. It never touches the *open* batch (the one holding the newest cover),
   because covers are still landing in it, and never touches covers below 8,000,000, which are served
   from older layouts.
2. **Upload**: `Batch.process_pending(upload=True)` uploads each complete zip that archive.org lacks, or
   holds a different copy of. **This is the backup.** Covers stay on local disk and keep being served
   from there. A batch that has already been finalized is never uploaded again.
3. **Finalize**: `Batch.process_pending(finalize=True)` points covers at archive.org and deletes the local
   copies. It checks for itself that archive.org's copy of every size is byte-identical (md5) to the
   local zip, that the zips' data passes its checksums, and that each local file matches its zip entry.

Stopping after step 1 or 2 loses nothing, so a batch can wait between steps for as long as you like.
`process_pending` takes `test=True`, which only reports and changes nothing. `archive()` has no test
mode, but it only writes zips and flags; it never deletes.

Every step that writes (`archive()`, and `process_pending` or `finalize` without `test=True`) takes a lock
(`items/.archive.lock`). A second run started while one is going stops with `Another archival run holds
...`, so a manual session and a cron can't overlap. Uploads can hold it for hours; check `ps` and wait.
`test=True` runs don't need it, so you can always look.

In 2024, finalize trusted "a file with this name exists on archive.org" and deleted covers that were
only in the local zip ([#9836](https://github.com/internetarchive/openlibrary/issues/9836)).
`openlibrary/coverstore/tests/test_archive_safety.py` replays that sequence.

### 0. Open a shell (on `ol-covers0`)

```
ssh -A ol-covers0
cd /opt/openlibrary
CONTAINER=$(docker ps | grep -oP 'openlibrary_covers_run_\S+' | head -1)
if [ -z "$CONTAINER" ]; then
    COMPOSE_FILE="compose.yaml:compose.production.yaml" HOSTNAME=$HOSTNAME docker compose run --rm -d covers bash
    CONTAINER=$(docker ps | grep -oP 'openlibrary_covers_run_\S+' | head -1)
fi
docker exec -it $CONTAINER screen -DR python bash -c 'python && bash'
```

```python
from openlibrary.coverstore.server import load_config
load_config("/olsystem/etc/openlibrary.yml")
load_config("/olsystem/etc/coverstore.yml")
from openlibrary.coverstore import archive
```

### 1. Look (changes nothing)

```python
db = archive.CoverDB().db
list(db.query("SELECT max(id) FROM cover"))            # the open batch is max_id // 10_000
list(db.query("SELECT count(*) FROM cover WHERE id >= 8000000"
              " AND (failed IS NULL OR archived IS NULL OR uploaded IS NULL)"))   # expect 0
archive.Batch.get_pending()                              # zips already on local disk
archive.Batch.process_pending()                          # per batch and size: complete? identical on archive.org?
```

**Check `get_pending()` before doing anything else.** Zips left from earlier runs are processed like new
ones. Anything not `Complete? True` is skipped and reports why (`batch_open`, `archival_incomplete`,
`zip_discrepency`, `zip_corrupt`, `nozip`).

If the NULL count isn't 0, stop and ask. Archival selects on `failed=false` and `uploaded=false`, so
those rows would be skipped silently.

### 2. Archive

```python
archive.archive()   # the lowest batch at or above 8,000,000 with unarchived covers; stops at the open batch
```

It archives one batch per call. Run it again for the next batch.

### 3. Upload

```python
archive.Batch.process_pending(upload=True, test=True)    # prints "Would upload ..."
archive.Batch.process_pending(upload=True, test=False)
```

### 4. Wait, then confirm archive.org has it

archive.org reports a file's md5 once its upload task finishes. Re-run step 1's `process_pending()` until
each size of the batch prints `identical copy on archive.org`. To look independently,
`https://archive.org/download/covers_NNNN/covers_NNNN_NN.zip/` lists the zip's members. A closed batch
holds up to 10,000: IDs marked `failed`, or never used by the id sequence, are absent.

### 5. Finalize

```python
archive.Batch.process_pending(finalize=True, test=True)  # prints "Finalizing N covers ... [test=True]"
archive.Batch.process_pending(finalize=True, test=False)
```

A batch that isn't verified yet shows `Finalize? False` and is skipped. If one prints
`Refusing to finalize`, **stop and read the reason**: finalize's own checks failed, and nothing was
deleted. The reason says which check (archive.org copy, zip checksums, a cover missing from or
differing from the zips, or a zip that changed during finalize).

### 6. Spot-check

```
curl -sI https://covers.openlibrary.org/b/id/<a cover id from the batch>-L.jpg | grep -i location
```

It should redirect into the batch's `l_covers_NNNN_NN.zip`, and that URL should serve the image.

### When a batch doesn't progress

These states are safe: covers stay on local disk and keep being served. Each needs a person to decide.

- **`zip_discrepency` on a batch whose covers are already uploaded.** A cover landed in the batch after
  it was finalized. Its zip holds only the stragglers and is never uploaded over archive.org's copy.
  The straggler stays local.
- **`zip_corrupt`, or `archive()` stopping with `... is not a readable zip`.** A run was killed mid-write.
  The covers it added are marked `archived` but aren't in a readable zip, and `archive()` refuses to
  append to it, so that batch goes no further until someone rebuilds the zip.
- **`zip_discrepency` on a batch with nothing uploaded.** The zip and the db disagree about which covers
  are archived (for example, a zip written before this procedure existed). Nothing is uploaded or
  deleted until they agree.
- **`nozip` for some sizes of a batch whose covers are all uploaded.** Finalize stopped while deleting
  zips. It deletes the full-size zip last, so the batch still shows up in `get_pending()`.
- **One cover's local files remain after an interrupted finalize.** Finalize repoints then deletes one
  cover at a time, so at most one cover's files are left, and that cover already resolves to archive.org.

### All at once

`archive.py`'s `main()` (and the #8278 recipe: `archive.archive()`, then
`Batch.process_pending(upload=True, finalize=True, test=False)`) runs steps 2, 3 and 5 in one go. A batch
uploaded in a run is finalized on a later run, once step 4 would pass. `main(..., dry_run=True)` changes
nothing.

## Where are covers archived?

* Covers 0 - 7,139,999 are stored in `zip` files within items https://archive.org/download/olcovers1 - https://archive.org/download/olcovers713 in the https://archive.org/details/ol_exports collection
* Covers 8,000,000 - 8,819,999 live in `tar` files within the https://archive.org/details/covers_0008 item
* Covers 8,820,000 - 8,829,999 live in a `zip` file also in the https://archive.org/details/covers_0008 item

## Warnings

As of 2022-11 there were 5,692,598 unarchived covers on ol-covers0 and archival hadn't occurred since 2014-11-29. This 5.7M number is sufficiently large that running `/openlibrary/openlibrary/coverstore/archive.py` `archive()` is still hanging after 5 minutes when trying to query for all unarchived covers.

As a result, it is recommended to adjust the cover query for unarchived items within archive.py to batch using some limit e.g. 1000. Also note that an initial `id` is specified (which is the last known successfully archived ID in `2014-11-29`):

```
covers = _db.select('cover', where='archived=$f and id>6708293', order='id', vars={'f': False}, limit=1000)
```

# How to run Covers Archival (2022, historical)

> Superseded by *Running cover archival safely* above. `archive.archive(test=False)` no longer matches
> `archive()`'s signature.

First, `ssh -A ol-covers0` and run `docker exec -it openlibrary_covers_1 bash`. Next, launch a python terminal and run:

```
from openlibrary.coverstore import config
from openlibrary.coverstore.server import load_config
from openlibrary.coverstore import archive
load_config("/olsystem/etc/coverstore.yml")
archive.archive(test=False)
```

# How it works

As of 2022-11, the way coverstore works is that new covers that are uploaded to Open Library go into `/1/var/lib/openlibrary/coverstore/localdisk/` within a directory named `/YYYY/MM/DD/`. A record for each cover (and its size variants) is recorded within the `cover` table of the `coverstore` psql db located on `ol-db1`.

At some (presumably advantageous if) regular interval, as the `localdisk` fills, the files can undergo archival, a process whereby covers are compressed and bundled into tar archives which are moved into the `/1/var/lib/openlibrary/coverstore/items/` directory within folders called "staging items" (e.g. `covers_0007`). The database reference to these covers' filename paths are updated accordingly by the `archive.py` script.

Mek speculates that when coverstore attempts to look up a cover, its entry is looked up in the DB and if the filename is a tar, coverstore first looks on disk for a "staging item" folder within the staging directory `/1/var/lib/openlibrary/coverstore/items/` and if no such "staging item" exists, the staging item is assumed to have been uploaded as an archive.org item having the same name (and thus redirects/resolves its request via archive.org).  

# State of Cover Archival

As of 2022-11 there are 5,692,598 unarchived covers on `ol-covers0` and we're starting to run short on space. Specifically, cover archives haven't been happening since ~2014-11-29, as we can see from the following brutally slow query:

```
coverstore=# select id, olid, filename, last_modified from cover where archived=true order by id desc limit 1;

   id    |    olid     |               filename               |       last_modified  
---------+-------------+--------------------------------------+----------------------------
 7315539 | OL25645665M | covers_0007_31.tar:1849729536:247493 | 2014-11-29 22:34:37.329315
```

In the previous query, we see that the last cover (id #7,315,539) was archived on `2014-11-29` and resides within a tar `covers_0007_31.tar`. Coverstore assumes this tar resolves to an `item` folder called `covers_0007`, either staged on disk within `/1/var/lib/openlibrary/coverstore/items/` or on archive.org/details/covers_0007. In this case, at the time of writing, this item was still staged on disk. As far as Mek can tell, staged items presumably get manually uploaded to archive.org under an item having the same name.

The item name itself (e.g. `coverd_0007`) is a combination of the prefix `covers` and the code `web.numify("%010d.jpg" % cover.id)[:4]` where, in this case, `cover.id` is `7315539`. The `"%010d"` format parameter pads the `cover.id` with leading 0's until it is 10 digits long and then the [:4] takes the first 4 digits of this padded number. Anything lower than `cover.id` 1,000,000 will thus be in `covers_0000` and from there the next 1M will be in `covers_0002` and so on. In total, this scheme allows for just under 10B covers before it breaks, which is a sufficiently unlikely number to hit!

2022-12-03: Anand says: "The cover id is considered to be 10 digits, 4 digits go to items, 2 digits go to tar file and the remaining 4 go to the filename."

**NB**: We identified **unarchived** covers (denoted with `archived=false` within the `covers` table) prior to `2014-11-29` but early tests suggest the archive process may not have been ironed out and standardized before this date, and so we decided to use the latest successful archival date to resume our archival efforts.  

## Archival Process (tar era, historical)

> Superseded by *Running cover archival safely* above. Do not remove local files by hand: finalize
> does it, and only after verifying archive.org's copy.

**Recipe for moving one batch of 10k covers at a time into tars on archive.org.**

1. On ol-covers0 docker container, run archive.py on ~10k items to create a new partial of unarchived covers, starting at stable ID 8M (e.g. `covers_0008_00`)
    ```
    from openlibrary.coverstore import config
    from openlibrary.coverstore.server import load_config
    from openlibrary.coverstore import archive
    load_config("/olsystem/etc/coverstore.yml")
    archive.archive(test=False)
    ```
2. `ia upload` each partial to the 4 respective items:
    * `covers_0008` -> `covers_0008_00.index` and `covers_0008_00.tar`
    * `s_covers_0008` -> `s_covers_0008_00.index` and `s_covers_0008_00.tar`
    * `m_covers_0008` -> `m_covers_0008_00.index` and `m_covers_0008_00.tar`
    * `l_covers_0008` -> `l_covers_0008_00.index` and `l_covers_0008_00.tar`
3. Update the upper bound value in code.py ~L290 by +10k (on `ol-covers0` container 1 & 2 + restart)
  * `if (8100000 > int(value) >= 8000000):` (or whatever is the upper bound)  ...
4. Restart the containers + test to make sure the service is resolving to archive.org for all sizes
5. Remove only the completed partial (e.g. 00 from each folder on /1/var/lib/openlibrary/coverstore/items/
  * `rm /1/var/lib/openlibrary/coverstore/items/cover_0008/covers_0008_00.*`
  * `rm /1/var/lib/openlibrary/coverstore/items/s_cover_0008/s_covers_0008_00.*`
  * `rm /1/var/lib/openlibrary/coverstore/items/m_cover_0008/m_covers_0008_00.*`
  * `rm /1/var/lib/openlibrary/coverstore/items/l_cover_0008/l_covers_0008_00.*`
