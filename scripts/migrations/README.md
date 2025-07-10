# Migration Scripts

Scripts found in this directory are meant to support a one-time task (such as a data migration), and __do not__ require long-term maintenance.

## `delete_merge_debug.py`

This script was created in support of [issue #10887](https://github.com/internetarchive/openlibrary/issues/10887).  When executed, it will delete all entries having `type` `merge-authors-debug` from the `store` and `store_index` tables.
