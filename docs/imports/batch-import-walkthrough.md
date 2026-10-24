# Batch-import walkthrough: Arabooks

This walkthrough uses the [Arabooks request](https://github.com/internetarchive/openlibrary/issues/9726) to illustrate the current batch-import flow. Test with a small sample before preparing a large TSV collection.

## 1. Prepare JSONL

Convert each selected TSV row into one JSON object per line. The batch schema requires `title`, `authors`, `publishers`, `publish_date`, and `source_records`. Use a stable source ID in `source_records`; it identifies the record for queue deduplication.

```json
{"title":"Example title","authors":[{"name":"Example Author"}],"publishers":["Example Publisher"],"publish_date":"2020","source_records":["arabooks:example-1"]}
```

Keep the original source ID consistent when regenerating the file. The queue skips an ID already present in any batch, including a failed item; retry an existing failed item from its batch page instead of uploading the same ID again.

## 2. Submit and review

1. Sign in to the local Open Library instance and open `/import/batch/new`.
2. Upload the JSONL file or paste its contents, then submit it. The entire upload is validated before any records are queued; validation errors are shown on the submission page.
3. Open the resulting **View Batch Status** link. Admin submissions are queued as `pending`; other users' submissions wait as `needs_review` until an admin approves them from the batch page.
4. Watch the item status and error columns on the batch page. ImportBot processes pending items and records the outcome as `created`, `modified`, `found`, or `failed`.

The batch page is the place to check outcomes; submitting a batch does not guarantee every record imports successfully.

## 3. Retry failed items

An administrator sees **Retry Failed Imports** on a batch page when it contains failed items with saved import data. Submitting the form sends a POST that requeues only those failed items in that batch, clears their previous error, import time, and Open Library key, and preserves their original data.

Retrying resubmits the same data. Resolve a permanent data or source problem before retrying; the button does not edit records or repair the cause of a failure.

## Local verification

Start the local web stack and ImportBot using the instructions in [Import Pipeline Debugging](debugging.md#running-importbot-locally). Submit only test data to the local instance. The focused automated tests for the retry transition are:

```bash
uv run --with-requirements requirements_test.txt pytest openlibrary/tests/core/test_imports_refresh.py openlibrary/plugins/openlibrary/tests/test_batch_import_retry.py
```

The automated tests verify that retry is limited to failed rows with saved data in the selected batch and that non-admins cannot submit the retry action.
