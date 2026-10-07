# Contributing to the Open Library KB

A few conventions keep this knowledge base usable.

## What this KB is for

These docs describe **how Open Library's systems actually work**:

- how each system works, and the **assumptions that went into its design**;
- **how to use** it, **how things connect**, and **how to extend** it;
- a **playbook for response** when something goes wrong;
- documentation of our **processes, architecture, and components**.

A page is **reference**: how a system works, or — for a finished system — what it is.

## What does *not* belong here

- **Planning, status, and in-flight progress.** Plans, oversight, "what's done
  vs pending," PR-by-PR state — these live in the corresponding **GitHub issue or
  epic**, not the KB. A page documents how a system works, not the state of the
  work on it. If a piece of a page is really status, move it to the tracker.
- **Scratch work and investigation diaries.** Distil findings into reference;
  don't paste the working notes or the path you took to them.
- **Armchair security.** Threat speculation and exploit walkthroughs are not
  documentation. A response **playbook** describes *how to respond*, not *how to
  exploit*.
- **Non-public detail — hard rule.** Never write content that must not be public:
  unpublished security advisories or exploit mechanics, a map of a missing or
  deliberately-disabled control, production infrastructure topology (hostnames,
  log paths, config paths), or SHAs of unreleased/unmerged security work. **If a
  fact cannot be public, it does not go in a doc** — there is no "publish all of
  this page except one section."
- **Code.** Scripts and harnesses belong in a repository, not the KB.
- **Out-of-scope projects.** This KB is for Open Library.
- **Staff/prod-only operational material** belongs under `internal/` (ultimately
  `olsystem`'s), not the product docs.

## Voice

Write **impersonal reference.** No first person, no author/agent/session byline,
no "we found" or process narration. Cite evidence as **GitHub issues, PRs, or
commit SHAs** — never session names, scratch directories, or who-did-what.

## Structure

- **One topic = one directory**, each with a `README.md` as its high-level overview.
- **No two files cover the same topic.** Extend the topic's `README.md` or add a
  genuinely-distinct sub-document inside its directory — don't create a second
  top-level file for the same subject.
- **Keep overviews high-level.** A `README.md` is a map, not the territory. Deep,
  self-contained technical dives live as named sub-documents (e.g.
  `search/text-analysis.md`), linked from the `README.md`. If an overview has
  grown to tens of kilobytes, that is the signal to split the deep material out —
  not to keep appending.
- When you add a page, add it to its directory's `README.md` in the same change.

## Page shape

A page covers, as relevant — omit what doesn't apply, don't pad:

- **What it is / why it exists** — one or two sentences, and what would break without it.
- **How it works** — the mechanism, step by step.
- **How to use it** — commands, invocation examples, walkthroughs.
- **Components & architecture** — the named parts and how they relate.
- **Key files** — entry points and config, with paths.
- **Configuration** — knobs, env vars, feature flags, where defaults live.
- **Testing** — where the tests are, how to run them, what's covered and what isn't.
- **Related jobs** — crons, daemons, workers that touch this system.
- **What's fragile / unimplemented** — known issues; link the GitHub issue.
- **Dependencies** — what this depends on, and what depends on it.

## Evidence standard

Cite commit SHAs and confirm they are ancestors of `master`; separate what you
verified by running from what you reasoned; and correct mistakes visibly rather
than silently.

## Publishing

This KB now lives in-repo under `.pam/kb/`; there is no separate publish step.
Edits land with the commit that makes them, reviewed like any other change.

> **Historical note (flag for human review):** this KB was consolidated from the
> external `mekarpeles/openlibrary-kb` repo, which is being spun down. The old
> flow mirrored a `wiki/` source to that published repo via `publish-wiki.sh`.
> That mechanism no longer applies here.
