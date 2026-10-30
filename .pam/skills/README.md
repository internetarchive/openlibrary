# `.pam/skills` — atomic agent skills for Open Library

This directory is the **canonical home** for the small, reusable units of
procedure that Open Library's agents run. It is versioned in-repo on purpose:
anything an agent must be able to run should travel to every worktree via
`origin/master`, and should be reviewable and diffable like code.

## Three kinds of unit

| Unit | What it is | Example |
|------|-----------|---------|
| **skill** | Atomic — one job, reads like a man page, and exists mainly to encode one hard-won gotcha. | `gh/pre-commit` |
| **recipe** | A composition of skills into a flow. | `ada/spawn`, `gh/pr-fixup` |
| **action** | A runnable/daemon a skill or recipe invokes, or that runs standalone. | `forge/watch` |

**Single source of truth.** A skill's content lives here and nowhere else. The
phase-oriented `~/Projects/ada/skills/*` become thin glue that `@`-references
these — never restating their content — so a renamed or moved skill breaks
*loudly* at check time instead of silently pointing at nothing. (A dangling
reference that falls back to silence is the exact failure this layout avoids.)

## The bundle

```
.pam/skills/
├── gh/
│   ├── pr-fixup ★ ......... recipe: pr-sync + squash-bot-commits + pre-commit
│   ├── pr-sync ........... fetch the exact pull/N/head ref; diff every file after -X theirs/ours
│   ├── squash-bot-commits  fold pre-commit.ci bot commits
│   ├── pre-commit ........ diff..HEAD | xargs --files; never --all-files
│   ├── issues-sweep ★ .... needs-response / needs-priority / stale; last-human-comment not updatedAt; lift over base rate
│   └── pr-status ......... maintain the <!-- ada-status --> side-car block
├── env/
│   ├── bootstrap-worktree ★  recipe: submodules + npm-install + docker-ol → HTTP 200
│   ├── submodules ........ git submodule update --init vendor/infogami
│   ├── npm-install ....... --engine-strict=false, then restore package-lock.json
│   ├── docker-ol ......... up/down/test, run from inside the worktree
│   └── mock-site-tests ... host-venv MockSite tests when the Lima VM is memory-held
├── ada/
│   ├── spawn ★ ........... recipe: ensure-issue → worktree → bootstrap → draft-PR → provision-home
│   ├── ensure-issue ...... find-or-create the tracking issue (idempotent)
│   └── cleanup ........... post-merge teardown, both safety checks
└── forge/
    └── watch ★ ........... daemon: watch OL PRs by label, 3-state, fire-on-green, spawn a reviewer via ada/spawn
```

`★` marks the five spine units.

## Two ownership notes worth keeping visible

**`ada/spawn` is a co-owned seam.** The coordinator (Ada) owns spawn
*semantics* — the brief, cq-seeding, the one-Ada-per-PR / no-subagent-on-a-PR
rule, draft-PR adoption. PAM owns the mechanical *provisioning* — worktree,
bootstrap-deps, provision-home. The outcome ("a correctly-briefed, provisioned,
live Ada on a PR") is joint, so both owners are named here rather than each
assuming the other is watching the seam.

`ada/spawn` must *assert*, not merely describe, the gotchas that have cost real
time: (a) the full brief is seeded into the target's `cq` and only a short
pointer is passed (the spawn prompt has a ~2000-char cap); (b) the spawned
session's mode line is verified (⏸ manual vs ⏵⏵ auto) or the step fails loudly,
because a spawn left in manual mode sits dead and silent; (c) the new agent is
recorded in `agent-leads.tsv` in the same breath.

**`gh/pr-status` is PAM-adjacent.** PAM owns the machine predicate that reads the
`<!-- ada-status -->` block; this skill owns writing it.

---

*Status: proposed. This README establishes the structure; the individual skill
files follow.*
