# Migration Scripts

Scripts found in this directory are meant to support a one-time task (such as a data migration), and likely __do not__ require long-term maintenance.

## `anonymous_store_remediation.py`

Created as a follow-up to [issue #11024](https://github.com/internetarchive/openlibrary/pull/11024), this script identifies and removes any remaining `account-email` store entries that are associated with anonymized accounts.

## `delete_merge_debug.py`

This script was created in support of [issue #10887](https://github.com/internetarchive/openlibrary/issues/10887).  When executed, it will delete all entries having `type` `merge-authors-debug` from the `store` and `store_index` tables.

## `write_prefs_to_store.py`

Created as a follow-up to [issue #10920](https://github.com/internetarchive/openlibrary/pull/10920), this script writes
a subset of existing preferences to the store.
