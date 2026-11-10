# Contributing to Open Library's agent docs

This directory (`.claude/agents/`) holds the instructions Open Library's AI agents read.
This guide is for **anyone** working on Open Library with an agent — contributor or fleet.
It covers two things: how to write docs that live here, and the operating discipline every
OL agent is expected to follow.

## Writing docs that live here

- **These files are community docs. Keep them impersonal.** Write rules for *the role* — "the
  maintainer," "the approver," "the lead" — not for a named individual, and never encode one
  person's personal preferences or communication style here. Anything specific to a particular
  operator's setup (which bot account acts, who approves, who coordinates, how someone likes to
  be briefed) belongs in *that operator's own layer*, not in this shared tree.
- **Don't restate the repo.** How the app builds, tests, lints, and names things is documented
  in the repo's own `AGENTS.md` and `docs/ai/`. Link to it; don't copy it (copies drift).
- **Contribute what you learn back.** A root cause, a gotcha, a corrected misconception — add it
  here or to `docs/` as a normal reviewed change, held for approval like any other.

## Security issues are embargoed

When the work is a vulnerability, it does not go through the normal public PR/issue flow:

- **Use a private GitHub Security Advisory (GHSA) and its temporary private fork.** Never open a
  public PR or issue that describes an exploitable bug — the public PR *is* the disclosure event.
  Work one vulnerability at a time.
- **Advisory temporary forks do not run CI.** GitHub Actions are disabled on them, so no
  workflow ever reports. The merge-status panel will spin forever waiting on checks that never
  run — don't wait on it. Validate the fix's tests locally before you push.
- **Merge an advisory fix from the advisory page, not the fork's PR URL.** The merge control and
  the advisory backlink live on the advisory page's **"Temporary private fork"** panel; the bare
  fork PR page has neither. Merging from that panel lands the fix on the parent repo's `master`
  as a `Merge commit from fork` commit. (The fork PR URL's *own* merge button is a different
  button and merges only within the throwaway fork — the fix never reaches the parent.)
- **After merging, machine-verify the fix is present on the parent repo's `master` before
  closing the advisory.** Closing tears the fork down; a fix that only reached the fork is then
  silently lost, and a green merge is not proof the commit landed upstream. This one check is
  what stands between you and shipping a security non-fix.
- **A published advisory cannot be closed.** GitHub returns `422 "Cannot close published
  advisory"` — it is a permanent public record. Only *draft* advisories can be closed; a
  published one is resolved by recording the patched version.
- **Every security fix carries a regression test proven to fail first.** Write a test that is
  red against the unfixed source and green against the fix ("watch it go red first"), and have
  it independently verified inside the embargo before the fix is handed up to merge.

## Verify before you report

Never record or relay a terminal status — *merged*, *deployed*, *resolved* — from anyone's word
or a plausible-looking PR. Machine-check it in the same breath:

- `gh pr view <n> --json state,mergedAt`, **and** confirm the fix is actually present on
  `master` (grep the sentinel on the deployed ref).
- **Merged ≠ on master ≠ deployed to prod** — three separate gates. Verify the one you are
  claiming. A status taken from a report instead of a check is how a live bug comes to look
  closed.
- When you can't point to the fixing commit on `master`, it isn't fixed yet — say so.

## Hand off finished, actionable work

How an agent reports is part of the work, not a wrapper around it:

- **Hand people finished work, not drafts.** What you keep iterating on is yours; what reaches a
  reviewer or approver is ready to act on.
- **Make every handoff self-contained and actionable.** Give the exact surface to act on (the
  link that *is* the next step) and the exact action — don't make the reader assemble the next
  step or hunt for where to click. If the answer to "where do I merge?" is a page, give that
  page, not a description of it.
- **Lead with the recommendation.** State your call and what you need, then the evidence — not a
  survey of options for the reader to adjudicate.
- **A reader should be able to act in one pass.** Put the highest-severity item first and label a
  trivial item as trivial, so critical and noise never read at the same volume.
- **Don't repeat a corrected mistake.** A correction is a durable change to how you work; fold it
  back here when it's general.
