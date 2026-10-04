# Project-management GitHub labels

The real Open Library label scheme, reconstructed from the automation (there is no single prose
catalog; the labels live in GitHub and are applied by workflows under `.github/workflows/` and
`scripts/gh_scripts/`).

## Label families actually in use

| Family      | Labels                                                        | Meaning / who sets it                                               |
| ----------- | ------------------------------------------------------------ | ------------------------------------------------------------------- |
| `Priority:` | `Priority: 0`, `Priority: 1`, `Priority: 2`                  | Triage priority; copied onto a new PR from the issue it closes.     |
| `Lead:`     | `Lead: @<username>`                                          | The owning lead; copied from the closed issue's lead assignee.      |
| `Needs:`    | `Needs: Lead`, `Needs: Review Assignee`, `Needs: Submitter Input` | Workflow gaps: no lead found; stale assigned issue (14d); input needed. |
| `Type:`     | `Type: Epic`, `Type: Question`                               | Epic = a bundle of sub-issues (a PAM Epic). Question = triage.       |
| other       | `agentic-workflows`, `no-automation`                        | Agent-workflow tag; `no-automation` exempts an issue from the bots. |

## The automation that applies them

- `scripts/gh_scripts/new_pr_labeler.mjs` + `scripts/gh_scripts/README.md`: on a new PR, copy the first
  `Priority:` label and the `Lead: @` from the `closes #<issue>`; if no lead, add `Needs: Lead`.
- `.github/workflows/pm_stale_ticket_labeler.yml`: add `Needs: Review Assignee` to stale assigned
  issues after 14 days; exempts `Type: Epic` and `no-automation`; exempts the staff maintainers.
- `.github/labeler.yml`: `Needs: Submitter Input` (path-glob driven).
- `issue_enrichment` and `pr_autoresponder` bots ("Richy"/"Pierre"): discovery labels and first-touch;
  skip authors whose login ends in `[bot]` (dependabot/renovate). See [[pm-automation-bots]] (to port).
- Other label-touching workflows (the automation surface): `new_pr_labeler.yml`, `pr_update_labeler.yml`,
  `pr_changes_requested.yml`, `auto_assign_reviewer.yml`, `pm_on_call_notification.yml`,
  `pm_stale_pr_messenger.yml`, `new_comment_digest.yml`, `weekly_status_report.yml`.
- `scripts/gh_scripts/issue_comment_bot.py`: maps each lead's `githubUsername` to `leadLabel`
  (`Lead: @...`) to `slackId`, the lead-to-label-to-slack binding table.

## Decision flagged for the tool

The pam tool seeded `project.toml` with `[labels.state]` = `State: Icebox/In Progress/Blocked/Done` and
`Type: Subtask`. Those are **tool defaults, not real OL labels**: only `Type: Epic` is confirmed in the
repo. Open Library does not use a `State:` kanban; it uses `Priority:`/`Lead:`/`Needs:` families instead.
Decide whether OL adopts a `State:` kanban or whether the pam tool's label-to-state model should flex to
map families like these. Until then, `project.toml`'s `[labels.state]` does not reflect reality.
