# Coverstore README

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

# How to run Covers Archival

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

## Archival Process

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

## 2024 Audit

Cover Service Audit
The following all contain blocks of 1M covers (100 blocks of 10k items)

Legacy WARC backups:
https://archive.org/download/warc_covers_0000 - WARCs
https://archive.org/download/warc_covers_0001 - WARCs
https://archive.org/download/warc_covers_0002- WARCs
https://archive.org/download/warc_covers_0003 - WARCs
https://archive.org/download/warc_covers_0004 - WARCs
https://archive.org/download/warc_covers_0005 - WARCs

Legacy backups (not served from archive.org -- still served off disk
https://archive.org/download/covers_0000 - tar
https://archive.org/download/covers_0001 - tar
https://archive.org/download/covers_0002 - tar
https://archive.org/download/covers_0002 - tar
https://archive.org/download/covers_0003 - tar
https://archive.org/download/covers_0004 - tar
https://archive.org/download/covers_0005 - tar
0006 - L/M/S tar, still served on disk
0007 - O/L/M/S tar, still served on disk

The following covers are served from archive.org:
https://archive.org/download/covers_0008 - tar
https://archive.org/download/covers_0009 - zip
https://archive.org/download/covers_0010 - zip
https://archive.org/download/covers_0011 - zip
https://archive.org/download/covers_0012 - zip
https://archive.org/download/covers_0013 - zip
https://archive.org/download/covers_0014 - zip

You can test where a cover is coming from via...
* < https://covers.openlibrary.org/b/id/07999999-M.jpg -> OL
* > https://covers.openlibrary.org/b/id/08000000-M.jpg -> IA
