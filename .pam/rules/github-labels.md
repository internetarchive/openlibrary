# Project-management GitHub labels

How Open Library's GitHub labels map to the kanban states PAM reads. This is the first draft from the
tool's `project.toml` label map; it gets reconciled with the authoritative PM labels doc.

## State labels (kanban)

| Label                | Kanban state  |
| -------------------- | ------------- |
| `State: Icebox`      | `icebox`      |
| `State: In Progress` | `in_progress` |
| `State: Blocked`     | `blocked`     |
| `State: Done`        | `done`        |

An issue carries exactly one `State:` label; it is the single source of its kanban column. A Division
Lead keeps the `State:` label accurate as a unit moves (see
[division-lead-epic-updates.md](division-lead-epic-updates.md)).

## Type labels

| Label           | Meaning                                              |
| --------------- | --------------------------------------------------- |
| `Type: Epic`    | An epic issue: a bundle of sub-issues (a PAM Epic). |
| `Type: Subtask` | A sub-issue under an epic; the unit an ADA owns.    |

## Notes

- The label to state map also lives in `project.toml` under `[labels.state]`, which is what PAM reads
  live; this doc is the human-readable explanation.
- To reconcile: port the full OL PM label catalog (priority, area, and any other families) from the
  authoritative project-management labels doc into this file.
