# GitHub Project Management Scripts

This directory contains scripts that the Open Library team uses to interact with this GitHub repository.

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
