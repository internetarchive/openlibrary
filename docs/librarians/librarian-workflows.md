# How Open Library librarians work

*A living reference for engineers building features that touch cataloguing. Everything here is drawn from GitHub issues and PRs in `internetarchive/openlibrary`, the in-repo wiki clone (`docs/wiki/librarians/`), the public help pages, and the role-gating code. Issue numbers are cited so claims can be checked and updated. Started 2026-09-21.*

**How to use this file:** before designing something librarians will use, read sections 2 to 4. When you learn something new from an issue, a Slack thread or a librarian, add it with a citation. When a workflow changes, edit rather than append.

---

## 1. Vocabulary

| Term | Meaning |
|---|---|
| **Work** | The abstract book: *Moby-Dick*. Has authors, subjects, a description. Key `/works/OL…W`. |
| **Edition** | One published version of a work: the 1992 Penguin paperback. Has publisher, date, ISBN, language, page count. Key `/books/OL…M`. Every edition should point at exactly one work. |
| **Author** | A person or organisation. Key `/authors/OL…A`. Works point at authors; editions carry a shadow copy of the author list that the UI does not show or edit (#2625, #13265). |
| **Orphaned edition** | An edition with no work. Search indexes it as a fake work with an `M` key. |
| **Redirect** | What a record becomes after a merge: it points at the survivor. Anything linking to it follows the redirect. |
| **Merge** | Combining duplicate works or authors into one survivor; the others become redirects. The **oldest OLID is always the survivor** by convention (#10124). |
| **Deconflation / split** | The reverse: separating records that were wrongly combined, e.g. one author record holding two different people. |
| **Promise item / BWB / ISBNdb import** | Bulk imports from booksellers and aggregators. They create most of the records librarians clean up (#7756, #7797, #6555, #3432). |
| **ILE** | The Integrated Librarian Environment: a blue toolbar librarians see on search and author pages for selecting records and dragging them between works and authors. |
| **MR / merge request** | A row in the community edits queue at `/merges`. Despite the name, it is the general "please review this" mechanism. |
| **Changeset** | One entry in the edit history. A merge or bulk edit is one changeset touching many records; "undo" reverts a changeset. |
| **LIT** | Librarian-In-Training. |

---

## 2. Who librarians are

**Four tiers**, all implemented as membership of an Infogami usergroup (`openlibrary/core/models.py`): patron, `/usergroup/librarians`, `/usergroup/super-librarians`, `/usergroup/admin`. Two helpers gate almost everything: `is_librarian_or_higher()` and `is_super_librarian_or_higher()`. Bots have their own group and must apply for accounts (#13191, #12887).

**How someone becomes a librarian.** Anyone with an account can edit any record. To merge or delete, they apply at `/volunteer#librarian`, are reviewed roughly weekly, join the Slack channel `#open-librarians-g` as a LIT, and work through named mentors until promoted. Promotion is done by a staff administrator or the Lead Community Librarian (`/librarians`, `docs/wiki/projects/lead-community-librarian.md`). Staff want to promote conscientious volunteers because merge requests overwhelm the few reviewers (#5721).

**What each tier can do** (from code, not docs):

| Capability | Patron | Librarian | Super-librarian |
|---|---|---|---|
| Edit works, editions, authors; add books and covers | yes | yes | yes |
| Bypass spam-word check and reCAPTCHA | no | yes | yes |
| Full revision history (patrons see a preview) | preview | yes | yes |
| ILE toolbar: select, drag works to authors, editions to works, Bulk Tagger | no | yes | yes |
| `/works/merge`, `/authors/merge` | no | **request only** | **execute** |
| "Move to a new work" in the edition form (#9235) | no | yes | yes |
| Delete records, revert to a revision, undo a merge changeset | no | no | yes |
| Review, approve, decline in `/merges` | no | view | yes |

The 2022 staff audit that produced this split (#6940) deliberately withheld deletion, scan-identifier edits, revert and edition moves from plain librarians. The trend is toward *more* restriction of high-impact fields: #13648 (Sept 2026) asks to limit re-pointing an edition to a different work to super-librarians because the field "is frequently misused in place of duplicate reporting or to repurpose a work record."

**Design implication:** a new tool should offer a *request* path for librarians and an *apply* path for super-librarians, and should never grant plain librarians something the edit form withholds from them.

---

## 3. Recurring tasks and how they are done today

Librarians work **one kind of problem at a time**, in volume. Any feature that saves a click on a repetitive task is worth more than a feature that makes a rare task elegant.

### Merging works
**How:** select works in search results or on an author page with the ILE, choose "Merge Works…", which opens `/works/merge?records=…` (the Vue `MergeUI`). Editions can be mixed into the list, which is how orphans get absorbed (undocumented, #8880, #13390). Librarians request; super-librarians approve.
**Pain:** rate-limit 429s and network errors (#10040, #10875, #11194); merges fail with `expected /type/author, found /type/redirect` when an edition still points at a merged author (#8069, #1445, #5594, open since 2021); errors go to the console not the UI (#5594); site security rules have broken merging for days at a time (#12629, #13428).

### Merging authors
**How:** two flows. From author search results or the author facet, where entries default to unselected because the list mixes duplicates with different people; or from the ILE. Super-librarians approving "have to manually click each entry… the majority of author merge submissions require no changes" (#11852).
**Wants:** show names and descriptions on the merge page (#9429, #10292); warn when Wikidata says the records are two different people (#10501); stop importing bad author records in the first place (#7756, #7797).

### Moving editions and splitting works
**How:** edit the edition, change "What work is this an edition of?", paste a work ID, or type `--` for "Move to a new work", save with a note. Drag-and-drop onto another work exists in the ILE, but not "move a selection to a *new* work."
**Pain:** "My biggest pet peeve as a librarian is how tedious it is to move editions to a new work… when you need to do it 50 times in a row" (#11346).
**Decision on record:** a new work does **not** inherit the old work's authors, because "usually if you have to move to a new work, the author is incorrect" (#8637). A veteran asked for at least a warning after "inadvertently creating a bunch of unauthored work records."

### Fixing author attribution
**How:** drag a work onto another author page in the ILE, or edit the work's author field. Splitting a conflated author is a multi-step recipe from the FAQ: add disambiguating dates to the author, then re-point each work.
**Known rot:** edition-level authors silently diverge from work authors; 336k editions were found fully disjoint from their work's authors and 124k editions reference deleted or redirected authors (#13265, #13322, #9863).

### Subjects
**How:** the Bulk Tagger in the ILE (`/tags/bulk_tag_works`) adds and removes subjects, people, places and times across selected works; subject chips on the book page are editable inline for librarians (#11719).
**Wants:** dry-run mode (#8657), exact-match ranking in autocomplete (#8584), selecting works in carousels (#8714). Merging or renaming subjects has been open since 2011 (#65).

### Deleting spam and non-books
**How:** super-librarians only, one edition at a time via the edit form. Requests arrive in Slack: "Fairly often, in the librarian Slack channel people request entries to be deleted (calendars, etc)" (#10033). The FAQ's "what is not a book" list (calendars, notebooks, toys, dump bins) is the standard.
**Wants:** a deletion request type in the queue worded as "this is not a book" (#10033); "delete work and all editions" (#7973); a FLAG request type (#7627); list-spam scoring (#11905).

### Cleaning bad imports
The dominant complaint of 2020 to 2026. Bookseller imports create authors with roles baked into the name ("editor", "trans.", "illus.", about 9,900 "editor" authors in #7797), multi-author strings, lowercase names, duplicates with no dates or identifiers, placeholder covers (40k, #9737), future publish dates (#4568), mangled MARC diacritics (`docs/wiki/librarians/mangled-marc.md`). Veteran view, repeated often: "The solution to this isn't to make merging better, but to stop importing crappy bookseller metadata in the first place."

### Identifiers
Author identifiers (VIAF, ISNI, Wikidata, LC, ORCID) are documented in `docs/wiki/librarians/guide-to-identifiers.md`. Problems: OCLC numbers misclassified as LCCN (#12409), identifiers added to redirects (#3431), wanting to paste a URL (#866), wanting a manual "sync from Wikidata" (#11505, #10904).

### Covers
Detailed etiquette in the FAQ ("be respectful of others' efforts"). Removed covers should not auto-reimport (#7504); the "Add IA cover" button is flaky (#9589).

### Orphaned editions
Absorbed via `/works/merge` with mixed records or the edition form. They disappeared from search (#9710), crashed the merge UI (#11702), and librarians want the old "Orphaned Editions" indicator back (#4874).

---

## 4. The review queue at `/merges`

Backed by the `community_edits_queue` table (`openlibrary/core/edits.py`): submitter, reviewer, url, status (0 declined, 1 pending, 2 merged), comment, `mr_type` (1 work merge, 2 author merge, 3 librarian batch on the workbench branch). Any librarian can file; only super-librarians see the merge button and can approve or decline. Clicking a row **claims** it (sets the reviewer). Super-librarians may also merge directly without a request.

**Known problems:** requests do not close when the reviewer changes the record set (#7207); "there's no way to preview a merge without claiming it" and "it's difficult to know whether a merge request is for an edition or an author" (#8880); a 400 shown as success (#8724); librarians could not find the queue in navigation until 2025 (#10293); closed rows lacked a link to the survivor (#10714).

**Wanted extensions:** deletion requests (#10033), web-book submissions (#9624), suggested edits to protected fields routed through the queue (#9751, #11338), per-submitter and per-reviewer stats (#6968).

**Design implication:** the queue is the accepted place for "someone senior should look at this." Reuse it rather than inventing a parallel inbox, but give each request type its own review page and make the row say what kind of thing it is.

---

## 5. What librarians worry about

1. **Bad merges are the cardinal sin and hard to undo.** Undo exists for author and work merges (#6885, #6774) but reverts *every* touched record to its pre-merge revision: "This could be months or even years of edits" (#6371). Undo fails when a later merge redirected an author (#5664). Librarians want to cherry-pick one record out of a bulk undo (#11337).
2. **Cascading edits need review.** Changing a work title or author name affects every edition at once; "incorrect changes have resulted in bad merges" (#11338). A proposed stop-gap is making those fields read-only below super-librarian.
3. **"Is not" relations (#9500).** Some records look identical but must never be merged (manga volumes with the same title). A structured `is_not` field was proposed so merges can be blocked programmatically. Admins have a free-text version.
4. **Provenance matters more than a checkmark.** Librarians want to see where metadata came from and who touched it (#7038, #9075, #7659). A veteran's position: knowing which external identifier agrees beats a "verified" badge.
5. **Concurrency.** A merge should refuse if the records changed in the meantime (#6675).
6. **Bots and imports** are seen as the source of the mess librarians clean up.

**Design implications:** preview before write; per-record undo, not only whole-batch; refuse or warn on stale revisions; show provenance in the UI; treat any check that says "these are different people or works" as a hard stop.

---

## 6. Requests for bulk tooling (the backlog this work draws on)

- **Epic #11505** (Nov 2025): draft saving, bulk apply of title/publisher/cover/language across editions, duplicate-an-edition, manual Wikidata sync, MARC import preview, paste-a-list author matcher, and a delete queue with bulk flagging of non-books.
- **Bulk edition editing**: #11845 (2026) atop a librarian's prototype; #7486 / #7649 "ILE Bulk Edit UI" (2023).
- **Batch author set and edition-author sync**: #9863, #13265, #13322.
- **Bulk move editions to a new work**: #11346 (mockup: select editions, one button).
- **Delete work plus all editions**: #7973 (super-librarian only, batches of 1000).
- **Dashboards and worklists**: #7630 maintenance dashboard for collaborative data-quality tasks; #7661 `/librarians/dashboard` built from Solr queries for invalid dates and missing covers, sorted by reading-log popularity; a `/merges`-style dashboard listing "link Wikidata IDs, propose merges, fix these bad ISBNs, bulk tag books."
- **Flag for review request type**: #7627.
- **Selection ergonomics**: shift-click (#8212), selection visibility (#8659), carousel selection (#8714), preselected authors (#11852), drop the "primary" radio because oldest always wins (#10124).
- **Edition merge**: #2114, open since 2019: "Edition merging should be the core feature of Open Library if it is even a goal to make a usable catalogue."
- **Current staff direction**: inline quick edits on the book page to lower the ramp for new volunteers (#13391), and the librarian workbench (PR #13612).

---

## 7. Where librarians talk and read

- **Slack** (invite via `/volunteer`): `#open-librarians-g` for librarians, `#openlibrary-g` general, `#openlibrary-imports-g`, `#openlibrary-design-g` (`docs/wiki/everyone/slack.md`). Many issues cite a Slack thread as the decision record. Decisions also get made on the **weekly community call**, Tuesdays 9am Pacific.
- **Help pages on the site** (editable wiki pages): `/librarians`, `/librarians-in-training`, `/help/faq/editing` (the de facto cataloguing standard: what is a book, derivative works vs editions, author name order, cover rules), `/trusted-book-providers`.
- **GitHub wiki clone** in this repo: `docs/wiki/librarians/` (identifiers, metadata standards, mangled MARC, web books, trusted providers, community lists) and `docs/wiki/projects/lead-community-librarian.md`.
- **`internetarchive/openlibrary-librarians` repo**: batches of records needing human cleanup, labelled `not a book`, `to purge`, `bad author import`, `conflation`. Low traffic since 2023; coordination moved to Slack.
- **GitHub labels** to search: `Affects: Librarians`, `Module: Merging`, `Module: Merge Queue`, `Module: Integrated Librarian Environment (ILE Bar)`, `Theme: Record Merging`, `Theme: Subjects`, `Lead: @seabelis`. There is no "Team: Librarian" label.
- **Voices worth reading**: the Lead Community Librarian (sets policy), two veteran data-quality critics who comment on most merge and import threads, a librarian who also ships code (undo-merge, bulk edit prototype, redirect cleanup), and the handful of high-volume mergers active 2022 to 2026.

---

## 8. Principles for building librarian features

Distilled from the above. Each is traceable to a cited complaint.

1. **Optimise for the fiftieth repetition, not the first.** Librarians do the same fix hundreds of times (#11346, #11852).
2. **Preview everything, write nothing until confirmed.** Bulk tools without a dry run get asked for one (#8657).
3. **Undo per record as well as per batch, and never overwrite later edits silently** (#6371, #11337).
4. **Refuse stale writes.** Check the revision the user saw (#6675).
5. **Respect the tier split.** Librarians request, super-librarians apply. Do not hand plain librarians delete, revert or edition re-pointing (#6940, #13648).
6. **Hard-stop on "these are different."** Different Wikidata items, an `is_not` link, disjoint authors (#10501, #9500).
7. **Show provenance.** Source records, human vs bot edits, external identifiers (#7038, #7659).
8. **Reuse the queue** for review, but make the row say what kind of request it is and give it its own review page (#8880).
9. **Oldest OLID survives a merge.** Do not ask the user to pick (#10124).
10. **Errors go in the UI, not the console** (#5594, #8724).
11. **Do not create unauthored works by accident.** Warn, or copy authors deliberately (#8637).
12. **Keep edition authors in step with work authors** whenever a tool changes either (#9863, #13265).
