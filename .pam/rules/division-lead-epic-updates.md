# Division Lead: how to update epics

A Division Lead manages each Epic as ONE living status unit, not a scatter of posts.

1. **One epic issue per effort.** The epic issue body is a living status page: rewrite it in place as
   state changes. Do not append a wall of dated comments; history lives in the issue's edit log.
2. **Per-unit detail stays in the unit.** Each sub-issue and its PR carry their own detail. The epic
   body links to its sub-issues and summarizes their state; it does not duplicate them.
3. **Current-status + task-list form.** Keep the epic body as: what is done, what is in progress, what
   is blocked, and what is next. A reader should learn the whole state in one read.
4. **Update on state change, not on a timer.** Rewrite the epic whenever a sub-unit opens, starts,
   blocks, or merges. Do not nag or post for the sake of posting.
5. **Keep the State label accurate** on the epic and its sub-issues (see
   [github-labels.md](github-labels.md) for the label to kanban-state mapping).
6. **Your "where are we" is the epic body.** A Division Lead reviews the epic body for the rollup;
   each agent's own state is its PR. If the epic body is current, you can answer "where are we" without
   chasing anyone.

Worked example: an epic rewritten in place from a pile of comments into current-status + task-list
form, so the body alone answers where the effort stands.
