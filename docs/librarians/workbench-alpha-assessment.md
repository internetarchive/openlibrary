# Librarian workbench: state of the branch and a proposal for a controlled alpha

*Assessed 2026-09-21 on branch `librarian-workbench` (PR #13612, draft), three commits on top of master: `96b8325e7`, `e29eea1af`, `d762dc473`.*

> **Status, 2026-09-21 (same day, later):** everything in section 6 has been implemented on the branch and is uncommitted at the time of writing, with one change of plan, since reversed on 2026-09-22: the workbench is gated by **`/usergroup/workbench`** (see section 6), so only opted-in librarians and admins can open it. Inside it, a librarian can only do what the edit form already lets them request, and nothing applies without a super-librarian. All six must-fixes, the should-fixes (dangling-record warnings, author roles kept, placeholder key dropped, reading-log counts batched, help page, integration and JS tests) and phase A of the action set are in. Sections 2 to 5 describe the branch *before* those changes and are kept as the record of what was found.

This document is written for someone who is not a librarian. The first section explains what the workbench is and how librarians would use it. The rest is the honest state of the code, the bugs and risks found, and a step-by-step plan to put it in front of a handful of librarians safely.

---

## 1. What the workbench is, in plain terms

Open Library's catalog has millions of records that were imported by machines and are wrong in small, repetitive ways: an edition with no language, a work with no author, an author record called "John Smith, editor". Today a librarian fixes these one page at a time: open the record, click Edit, change a field, save, repeat.

The workbench is a single page, `/librarians/workbench`, that turns this into a **find → select → preview → apply → undo** loop:

1. **Find.** A table of records (editions, works or authors) driven by a search. Built-in "worklists" such as *Editions without a language* show how many there are and let you page through them. Each row has small colored "health" chips that flag known problems (author on the edition does not match the work, imported from a low-trust source, publish date in the future, no identifiers).
2. **Select.** Tick boxes, shift-click, or keyboard (`j`/`k`/`x`). Up to 200 records per batch.
3. **Preview.** Choose an action (set a field, add subjects, set the author, move editions to another work, merge duplicate editions, flag, delete). A dialog shows exactly what would change on every record, plus warnings from automatic checks. Some warnings are **blocks**: they must be explicitly ticked "I've checked this" before the batch can go ahead.
4. **Apply or request.** A *super-librarian* (senior volunteer) applies immediately. An ordinary *librarian* files a *request* instead, which appears in the existing merge-request queue at `/merges` for a super-librarian to apply or decline. Nothing is written to the database until this step.
5. **Undo.** Every applied batch is one entry in the site's edit history. It has its own page (`/librarians/batch/<id>`) and can be reverted as a whole or one record at a time. The revert refuses to overwrite a record someone else edited afterwards, unless forced.

There is also a side panel for one record at a time: its findings, editable fields (staged, not saved, until previewed), and shortcuts like "use the work's author" or "move to a new work".

**Where things live.** Nothing new was added to the database schema. An applied batch *is* the changeset it created. A pending request is a small JSON document in the existing site "store". Saved worklists are also store documents, shared by all librarians.

---

## 2. Bottom line

**The core is sound and works.** I verified it three ways:

- The branch's 57 unit tests pass (run inside the web container).
- A full cycle against the real dev database: preview → apply → read back the batch page → list it → revert → confirm the record returned to its previous state. The "batch is a changeset" storage design holds in a real infobase, including finding the changeset by its uid and detecting the revert.
- The live UI in Chrome: worklists load, the grid renders, the merge-editions preview dialog appears with the correct block warning and override checkbox, the record panel loads, and there are no console errors.

**Could it corrupt data?** Not in the structural sense. Every write goes through the same `save_many` path the rest of the site uses, and infobase validates types and references before accepting anything. I confirmed that a bogus language code is rejected at save time. Every change is a normal revision in the edit history and can be reverted.

The real risk is **semantic mistakes at scale**: one click can change up to 200 records, and a few actions do more than a librarian might expect (details in section 4). Those are exactly what a controlled alpha with informed users is for.

**Verdict: yes, deployable to production for a small, informed group, after the four "must-fix" items in section 6 are done.** Two of those are confirmed bugs that alpha users would hit in their first session.

---

## 3. What it does today

| Action | Who | What it changes | Risk level |
|---|---|---|---|
| Set a field (publisher, date, language, format, pages, series…) | librarian requests, super applies | One whitelisted field on each selected edition or work. Title and author links are deliberately excluded. | Low |
| Manage subjects | same | Adds/removes subjects, people, places, times on works. Editions in the selection are folded to their work. | Low |
| Set identifier | same | One identifier (Wikidata, VIAF, ISBN, OCLC…) onto one or more records. Only reachable from code today, no UI button. | Low |
| Set author | same | Add, replace, or set-as-only author on works; optionally keeps edition authors in step (addresses #9863, #13265). | Medium |
| Move editions | same | Re-points editions to another work, or creates a new work (title, authors, first cover copied from the first edition). | Medium |
| Flag for review | everyone requests | Writes nothing. Files a report in the merge queue. | None |
| Merge editions | same as set field | Unions identifiers, covers, publishers etc. onto the surviving edition; turns duplicates into redirects. | High: no equivalent feature exists on the site today (#2114 open since 2019) |
| Delete | super-librarian only | Marks records deleted, optionally a work's editions too. | High |
| Merge works / Merge authors | any | Runs pre-flight checks, then opens the existing merge pages. The workbench does not do the merge itself. | Low |
| Add to list | any | Uses the existing list API. | None |

Built-in worklists: editions without cover / ISBN / language / publisher; works without author / editions / subjects; orphaned editions; authors without works / dates. Librarians can save their own queries as shared worklists.

---

## 4. Bugs and flaws found

Ranked by how much they matter for an alpha. "Confirmed" means reproduced, either live or by reading the code path end to end.

### Confirmed bugs

1. **The Review button on the merge queue 404s for workbench requests.** The queue row template appends `&mrid=N` to every request URL. Merge URLs already contain `?records=`, but a workbench request URL is `/librarians/request/3`, so the link becomes `/librarians/request/3&mrid=5`, which the route does not match. Reproduced live. This breaks the entire librarian → super-librarian review path from `/merges`. (`openlibrary/templates/merge_request_table/table_row.html:9`, `openlibrary/plugins/openlibrary/librarians.py:55`)

2. **Staged field edits are silently lost.** If a librarian edits two fields on one record in the side panel (say publisher and date) and clicks Preview changes, only the first field is previewed. After it is applied, *all* staged edits for that record are dropped, including the one never applied. Reproduced live: two staged fields → one applied → zero remaining. The variable meant to queue the rest (`_pendingQueue`) is set but never read. (`openlibrary/components/lit/OlWorkbench.js:530-545, 575-589`)

3. **Bad input to "Set a field" returns a raw 500.** A non-numeric page count throws an uncaught `ValueError` and the user sees a stack trace. A language code that does not exist passes the preview and only fails at apply with "Saving failed: notfound". Reproduced live. (`openlibrary/core/batch_ops.py:427`)

4. **Flag requests show an Apply button that always fails.** Super-librarians see "Apply" on flag requests in the Batches tab and on the request page; clicking it returns "A flag is a report, not an edit". The only resolution for a flag is Decline, which reads as "rejected" to the person who filed it. Flags need a real outcome ("resolved", or a one-click path to delete/merge). Reproduced live.

### Design flaws that can lose or damage data

5. **A reviewer applies a plan they did not see.** When a super-librarian applies a librarian's request, the plan is rebuilt against the *current* records, which is correct, but the request page and Batches tab show the changes as they were at request time. If the records changed in between, what is applied differs from what was reviewed, with no fresh preview and no revision check (the direct-apply path does have one). (`batch_ops.apply_requested`)

6. **Any batch author can force-revert over other people's later edits.** `force=True` is available to the batch author, not only super-librarians. Given how strongly librarians feel about undo erasing later work (#6371), force should be super-only. (`batch_ops.revert`)

7. **Merge editions across different works can be overridden.** The check is a block, but a super-librarian can tick past it. The duplicate then becomes a redirect and its link to its own work is lost; that work may be left empty. Fields not in the merge's field list (table of contents, classifications, contributors' detail, first sentence…) are dropped from the duplicate. They remain in the redirect's history, so they are recoverable, but not obviously.

8. **Delete has no guard for what points at the record.** Deleting an author with 300 works only warns if the author is on a list. Deleting a work without "include editions" leaves its editions orphaned with no warning. Moving all editions off a work leaves an empty work with no warning. The health panel *knows* these counts; the delete/move checks do not use them.

9. **Set author rewrites every author entry on a work.** In all modes it rebuilds the list as plain author-role entries, so any existing role or `as` information on other authors is dropped. Rare in the data, but silent.

10. **Requests to "move to a new work" store the placeholder key `/works/new`** in the request, which shows up as a record on the request page.

### Smaller issues and limitations

- **Not usable on narrow screens.** Below about 1100px the worklist rail disappears and the sticky action bar covers the grid. This is a desktop tool; say so.
- **Page-scope filters are confusing.** Health filters such as "Edition author ≠ work author" only narrow the 50–100 rows already fetched, so a worklist can show 0 results while thousands exist. The UI labels them "on this page", but a first-time user will read it as a bug.
- **Search box accepts raw Solr syntax.** Convenient for power users; also a way to run very expensive queries. Fine for a small group.
- **Pre-flight checks for delete/flag are slow at scale.** They make three round trips per record (history, lists, reading log). A 200-record delete preview could take tens of seconds on production.
- **No integration tests** against a real infobase, and no JS tests for the workbench components other than the autocomplete. The 57 Python tests use mocks.
- **Saved worklists** are shared globally, cannot be renamed, and any librarian can create up to 200.
- **Two super-librarians can apply the same request concurrently.** Not atomic; the second apply would mostly be a no-op, but the bookkeeping could end up odd.
- **Flag reasons** (spam, not a book, duplicate, delete, review) are not surfaced in the queue title beyond the first line.

---

## 5. What to tell alpha users

- It is a desktop tool. Use a wide window.
- A batch is at most 200 records. Everything is previewed first and can be undone from the Batches tab or the batch page.
- "On this page" filters only look at the rows you fetched. To find all such records, page through a broader worklist.
- Merge editions is new to Open Library. Use it only for true duplicates of the same printing, and read the warnings.
- Flags file a report for a super-librarian. They are not an edit.
- Search may lag a few minutes after an apply. The rows you touched stay tinted green until you reload.
- If something looks wrong, revert first and report second. Every batch has a page you can link to.

---

## 6. Proposal: controlled alpha

### Access

*Decided 2026-09-21: no separate usergroup. Reversed 2026-09-22: opt-in by usergroup.* The workbench, its help page, and the batch and request pages are open only to members of `/usergroup/workbench` who are also librarians, plus admins (`User.can_use_workbench()` in `openlibrary/core/models.py`; `require_workbench` in `openlibrary/fastapi/auth.py`). Anyone else gets the permission-denied page and a 403 from the JSON routes, and the hamburger link is hidden. An admin opts someone in by editing `/usergroup/workbench`. Super-librarians who will review workbench requests need to be in the group too, since the request page is behind the same gate. `ENABLED_ACTIONS` in `batch_ops.py` stays the kill switch for an individual action, and the whole page can be turned off by removing the router if needed.

### Must fix before anyone outside the team uses it

1. Merge-queue Review link (bug 1). One-line template fix: use `?` when the URL has no query string, or make the request route tolerate the suffix.
2. Staged edits (bug 2). Either preview all groups in sequence, or only clear the fields that were actually applied.
3. Input validation in `set_field` (bug 3): validate ints and language codes at preview time and return a 400 with a readable message.
4. Flags (bug 4): hide Apply on flag requests and add a "Resolved" outcome, or route flags to a "Delete…" / "Merge…" shortcut for the reviewer.
5. Fresh preview on apply of a request (flaw 5): the request page should re-run the dry run and show the current plan before the Apply button is enabled, and refuse if the record set changed.
6. Force revert becomes super-librarian only (flaw 6).

### Should fix during the alpha

- Add warnings for: deleting an author with works, deleting a work without its editions, moving the last editions off a work.
- Preserve existing author roles in Set author.
- Drop `/works/new` from stored request items.
- Batch the delete/flag pre-flight queries so a 200-record preview is one or two calls per check, not 600.
- A short help page linked from the masthead ("Help" label already exists but is unused) covering the points in section 5.
- One integration test that runs apply → revert against the dev infobase, and a JS test for the pending-edits flow.

### Phasing the actions

- **Phase A (first two weeks):** Set a field, Manage subjects, Set author, Move editions, Flag, Add to list, plus the merge-works / merge-authors hand-offs. These map onto tasks librarians already do by hand and have equivalents on the site.
- **Phase B (after A settles):** Merge editions and Delete, both super-librarian only. Merge editions has no precedent on the site; watch the first dozen closely.

Phasing is a one-line change to `ENABLED_ACTIONS`.

### Who and how many

Five to eight people: the Lead Community Librarian, two or three super-librarians who review merges regularly, and two or three active librarians who file many requests. Ask each to work one worklist they care about (editions without a language is the safest and largest) and to report in a single GitHub issue.

### Watching it

- Stats already emitted: `ol.librarians.batch.<action>.requested / .applied / .records / .reverted / .override.<code>`. Put them on a Graphite panel.
- `/recentchanges?kind=librarian-batch` and `kind=librarian-batch-revert` give staff a live audit trail without any new tooling.
- Sentry will catch the 500s; fix bug 3 first so the signal is not noise.
- A revert rate above roughly one in ten batches is the signal to pause and look.

### Rolling back

Remove people from the usergroup, or empty `ENABLED_ACTIONS`. Nothing written by the workbench needs special cleanup: every batch is an ordinary changeset and can be reverted from its page.

### Questions to put to librarians during the alpha

- Is "request" the right word, and should requests appear in `/merges` or in their own list?
- Which health chips are noise? Low-trust import is broad.
- Should ordinary librarians be able to Set author at all, given #13648's move to restrict work re-pointing?
- What should happen to a flag once acted on?

---

## Appendix: how this was verified

- `pytest` on the four new test modules inside the `web` container: 57 passed.
- Live HTTP against the dev stack as the seeded super-librarian: config, worklists with counts, edition/work/author queries, record panel, dry runs for set_field, merge_editions, move_editions (new work), delete; apply of a set_field batch (changeset 12299), batch detail, batch listing, revert, record restored; a flag request filed, found on the record's "pending" chip via the store index, its Apply refused, then declined and the chip cleared.
- Chrome via the Claude in Chrome extension against `localhost:8080`: worklists, grid, merge-editions preview dialog with block and override, record panel, staged-edit loss reproduced, console clean.
- Code read in full: `core/batch_ops.py`, `core/librarian_batches.py`, `core/record_context.py`, `core/workbench.py`, `fastapi/librarians.py`, `plugins/openlibrary/librarians.py`, the six Lit components, both Jinja templates, and the infobase client/store/save internals the storage design depends on.
