# Oracle mode (prototype)

**Oracle mode** turns an agent's would-be *stop* into a checklist evaluation.
At every point a Claude Code session would stop, a `Stop` hook evaluates a
per-**role** checklist. The first **unmet, actionable** item is handed back to
the agent as its next prompt (force-continue); when every item is satisfied, the
stop is allowed.

> Not "a stop hook" — *the stop hook evaluates our checklist; not complete → keep
> going.*

This directory is a **rough but working prototype**, scoped to Open Library and
run under by the ada that owns it. Real friction is expected to refine the
checklist before anything graduates to the shared `agents` tool.

## Contract

The hook obeys the Claude Code `Stop` contract:

| Outcome | Exit | Effect |
|---|---|---|
| **force-continue** | `2` | the unmet item's prompt is written to stderr and becomes the next turn |
| **allow stop** | `0` | the session stops normally |

**One invariant: fail open.** Unbound session, unknown role, missing `oracle`
binary, GitHub down, parse error, any exception → **exit 0**. A hook that can
*wedge* a session is strictly worse than one that under-enforces. The only
deliberate non-zero exit in the whole tree is the single `sys.exit(2)` in
`hook.py`.

## State is artifact-native (GitHub only)

Nothing about checklist position is stored. Every predicate re-derives its answer
**live from the artifact on GitHub** each call. The core primitive at every layer
is *"is my summary artifact newer than what's beneath it?"* We trust only
server-authoritative GitHub facts:

- **`headRefOid`** — always populated, server-side, nothing to spoof.
- PR / issue existence and body text (including the oracle body block).

We deliberately do **not** depend on push-time dates. `Commit.pushedDate` is
null in practice (confirmed live against this repo) and the REST PushEvent feed
is 90-day / 300-event capped — unusable on a high-traffic repo. So **plan
currency is anchored on HEAD SHA equality**, not a timestamp (Oliver's schema
call). The plan records the SHA it was last written against; if the agent pushes
and forgets to refresh the plan, the SHAs diverge → force-continue.

The only persisted bit is a runaway-loop counter in the system temp dir (keyed by
repo + branch), never in the repo.

## Files

| File | Role |
|---|---|
| `hook.py` | Stop-hook entry: drain stdin → `agents whoami` → role-gate → route → evaluate → map to exit 2/0. Fails open everywhere. |
| `ada.yml` | the **ada** checklist (one ada, one PR). |
| `lead.yml` | the **lead** checklist (keep the division NOW current). |
| `checks/pr.py` | ada predicates (gh/GraphQL); fail open inside. |
| `checks/now.py` | lead predicates (gh/GraphQL); fail open inside. |
| `checks/_util.py` | shared helpers: gh wrappers, the oracle-block parser, blocker validation, the fail-open net. |

`hook.py` exports `$ORACLE_DIR` to this directory before evaluating, so a
checklist's `check:` lines resolve regardless of the session's cwd. Trivial git
predicates are inline shell (exit code); anything touching gh/GraphQL goes
through a named helper in `checks/` (Oliver resolution #1).

## The oracle block

Per-ada status and the plan's anchor SHA live in an HTML-comment block in the PR
body — artifact-native, and invisible in rendered Markdown. (The prototype keeps
status here rather than minting agent-internal labels on the public `openlibrary`
repo; it still reuses the existing ada-status vocabulary, Oliver resolution #3.)

```
<!-- oracle
status: developing
head: <the HEAD sha the plan was last written against>
blocker: <type>: <specifics>        # only when status: blocked
-->
```

- **status** ∈ `investigating | developing | ready-for-review | needs-decision |
  merged-pending-deploy | blocked`.
- **head** — stamped by the agent after pushing; checked by `plan_current`
  against the live `headRefOid`.
- **blocker** — only a valid clear-to-stop when typed and lead-actionable:
  `<type>` ∈ `decision-needed | missing-info | access | upstream-dependency`,
  with real specifics, and **not** a "haven't-finished-looking" bail.

## ADA checklist (at its stop)

Terminal = (all work items met) **or** (a valid blocked-escape).

1. working tree clean (else: commit) — *skipped when validly blocked; never force a commit*
2. commits ahead are pushed (else: push) — *applies even when blocked, so the lead inherits partial state*
3. a PR exists (else: open a DRAFT PR; its body is the plan)
4. PR body non-empty (else: write the plan)
5. plan current with work — `head:` SHA == live `headRefOid` (else: refresh the plan) — *skipped when validly blocked*
6. status set (else: set one from the vocabulary) — *skipped when validly blocked*

**Blocked-escape** is a distinct, valid clear-to-stop: status `blocked` **and** a
typed, lead-actionable blocker in the body. A "blocker" that reduces to
"haven't-finished-looking" is rejected → force-continue. That rejection is what
stops `blocked` from becoming a lazy bail; conversation with the lead is the only
thing that can legitimately unblock.

## LEAD checklist (at its stop)

The NOW lives in ONE per-division issue titled `[NOW] <division>`.

1. the NOW issue exists (else: create it)
2. NOW current with adas — no owned child issue's `updatedAt` is newer than the
   NOW's `lastEditedAt` (else: reconcile and re-author the NOW)

The float-up is the **lead pulling** at its own stop — never an ada pushing.
Children are compared on `updatedAt` (intentionally sensitive; over-checking is
the safe direction, Oliver resolution #4). Division comes from `$ORACLE_DIVISION`.

## Wiring (done by agents-lead, not here)

Oracle mode is enabled in **user** settings (`~/.claude/settings.json`), so it
self-gates by role via `agents whoami` and never touches shared repo `.claude`
config (Oliver resolution #5). The exact `Stop` hook line:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "sh -c 'D=\"${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}\"; H=\"$D/.claude/oracle/hook.py\"; [ -f \"$H\" ] || exit 0; exec python3 \"$H\"'"
          }
        ]
      }
    ]
  }
}
```

It resolves this repo's checkout, runs `hook.py` if present (any non-OL repo →
`exit 0`), and lets the hook self-gate by role and fail open. **This prototype
does not edit anyone's `settings.json`** — that wire is a separate, careful step.

## Manual evaluation

```bash
ORACLE_DIR=.claude/oracle oracle next --yaml .claude/oracle/ada.yml   # human-readable
ORACLE_DIR=.claude/oracle oracle next --yaml .claude/oracle/ada.yml --text  # raw prompt only
```
