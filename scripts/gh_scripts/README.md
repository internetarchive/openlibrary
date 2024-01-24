# GitHub Project Management Scripts

This directory contains scripts that the Open Library team uses to interact with this GitHub repository.

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
