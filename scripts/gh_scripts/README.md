# GitHub Project Management Scripts

This directory contains scripts that the Open Library team uses to interact with this GitHub repository.

## `new_pr_labeler.mjs`
This script is used to automatically prioritize and assign a new PR to a lead.

### Usage:
This script takes three positional arguments, followed by a vararg for the PR's body:

<pre><b>node new_pr_labeler.mjs</b> repository pr_author pr_number pr_body...</pre>
`repository` the repository owner and name (ex. `internetarchive/openlibrary`)
`pr_author`  the GitHub username of the PR's author
`pr_number`  the PR's identification number
`pr_body...` the body of the PR

### Details:
The script does a case-insensitive search for a `closes #` statement in the newly created PR's body.  If one is found, the corresponding issue is fetched.
The first https://github.com/internetarchive/openlibrary/labels/Priority%3A%200, https://github.com/internetarchive/openlibrary/labels/Priority%3A%201, or https://github.com/internetarchive/openlibrary/labels/Priority%3A%202 label that is found on the issue is added to the PR.
If a lead is assigned to the issue, and the lead is not also the PR's author, the lead will be assigned to the PR.  Similar to the priority labels, only one lead can be assigned to a PR.

## `stale_assignee_digest.mjs`

This script fetches all open issues that have assignees and publishes a Slack message listing all that have met the following criteria:
- Assignee has been assigned for more than a given number of days and has not created and linked a pull request to the issue.
- Assignee's GitHub username does not appear on the exclude list.

This script skips over issues that have the https://github.com/internetarchive/openlibrary/labels/no-automation label.

This script takes two options:
- `--daysSince` Integer that defines the number of days until an assignee is stale.  Defaults to `14`.
- `--repoOwner` String that defines the specific `openlibrary` repository.  Defaults to `internetarchive`.

> [!IMPORTANT]
> Include a space between an option and its value when calling this script.

__Correct:__
`node stale_assignee_digest.mjs --daysSince 21`

__Incorrect:__
`node stale_assignee_digest.mjs --daysSince=21`

The GitHub action that runs this script automatically sets `--repoOwner` to the owner of the repository that triggered the action.

To quickly see a script's purpose and arguments, run the script with the `-h` or `--help` flag.

## `issue_comment_bot.py`

This script fetches issues that have new comments from contributors within the past number of hours, then posts a message to the team in our Slack channel.

### Usage:
This script has three positional arguments:
```
  hours        Fetch issues that have been updated since this many hours ago
  channel      Issues will be published to this Slack channel
  slack-token  Slack authentication token
```

__Running the script locally:__
```
docker compose exec -e PYTHONPATH=. web bash

# Publish digest of new comments from the past day to #openlibrary-g:
./scripts/gh_scripts/issue_comment_bot.py 24 "#openlibrary-g" "replace-with-slack-token"
```

__Note:__ When adding arguments, be sure to place any hyphenated values within double quotes.
