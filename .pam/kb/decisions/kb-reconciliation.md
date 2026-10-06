# KB reconciliation (decision needed)

Status: **DECISION NEEDED**. Do not execute the migration until Mek decides how to proceed.
Captured 2026-10-04.

## The problem

Open Library has three overlapping knowledge sources that need reconciling:
- `docs/ai` in the openlibrary repo (AI-agent docs).
- the `openlibrary-kb` repo (a separate knowledge base).
- `.pam/kb` (this new in-repo KB, Obsidian-style).

Some `openlibrary-kb` content is admin/staff-only and must not live in a public repo.

## Direction (Mek's lean, 2026-10-04)

- Move `docs/ai` into `.pam` (likely `.pam/kb`).
- Start moving the public parts of `openlibrary-kb` into `.pam/kb`.
- Move admin/staff-only content to `olsystem`'s `.pam` (private), long-term.
- Obsidian syntax (`[[wikilinks]]`) is the canonical target format for all of it.

## To decide

- The public/private split: what in `openlibrary-kb` is admin/staff-only, and the criteria.
- Target layout: does `docs/ai` become `.pam/kb/...` or a separate `.pam/docs/`? Keep one source of truth.
- Migration order, and how to avoid leaving duplicates or dangling links during the move.
- Whether `olsystem` gets its own `.pam` now or later.

## Notes

- `docs/ai/` already lives IN this repo (this worktree is a clone of openlibrary), so "moving docs/ai
  into .pam" is a local restructure, not a cross-repo copy. The per-domain guides there
  (`docs/ai/{i18n,solr/*,imports/*,tag-system/*,css,design,...}`) are the main public KB content, and
  `docs/ai/README.md` is the canonical engineering-standards entry.
- Relates to the pam tool's KB story: `.pam/kb` is the in-repo default; external and admin KBs need a
  clean story (public `.pam/kb` vs private `olsystem/.pam/kb`). ModSec ([[../rules/modsec|modsec]]) is
  an example of admin/staff-only content that belongs in `olsystem`, not public `.pam`.
- Scope is the KB content reconciliation specifically; the [[division-lead-epic-updates]] rules and the
  `rules/` bucket are separate.
