# How to run Covers Archival

```
from openlibrary.coverstore import config
from openlibrary.coverstore.server import load_config
from openlibrary.coverstore import archive
load_config("/olsystem/etc/coverstore.yml")
archive.archive()
```

## Warnings

As of 2022-11 there were 5,692,598 unarchived covers on ol-covers0 -- a sufficiently large amount that `/openlibrary/openlibrary/coverstore/archive.py` `archive()` was hanging after 5 minutes.

# System & Code Architecture

Looks like current cover archival items on archive.org stop at https://archive.org/details/covers_0006

Interim archived covers presumably live at /1/var/lib/openlibrary/coverstore/items/covers_0007

The files in this directory presumably get manually uploaded to an item called covers_0007 (following naming convention) on Archive.org.

I think the 0007 comes from ???

Current id of latest cover uploaded is 13011172

/1/var/lib/openlibrary/coverstore/localdisk/ is where files are uploaded before archival.
