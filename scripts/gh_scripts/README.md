# GitHub Project Management Scripts

This directory contains scripts that the Open Library team uses to interact with this GitHub repository.

## `auto_unassigner.mjs`

This script fetches all open issues that have assignees and automatically removes assignees that meet the following criteria:
- Assignee has been assigned for more than 14 days and has not created and linked a pull request to the issue.
- Assignee's GitHub username does not appear on the exclude list.

This script skips over issues that have the `no-automation` label.

This script takes two options:
- `--daysSince` Integer that defines the number of days until an assignee is stale.  Defaults to `14`.
- `--repoOwner` String that defines the specific `openlibrary` repository.  Defaults to `internetarchive`.

> [!IMPORTANT]
> Include a space between an option and its value when calling this script.

__Correct:__
`node auto_unassigner.mjs --daysSince 21`

__Incorrect:__
`node auto_unassigner.mjs --daysSince=21`

The GitHub action that runs this script automatically sets `--repoOwner` to the owner of the repository that triggered the action.
