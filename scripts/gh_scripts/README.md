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

## `issue_comment_bot.py`

This script fetches issues that have new comments from contributors within the past number of hours, then posts a message to the team in our Slack channel.

### Usage:
```
positional arguments:
  hours                 Fetch issues that have been updated since this many hours ago

options:
  -h, --help                                       show this help message and exit
  -c CONFIG, --config CONFIG                       Path to configuration file
  -s SLACK_CHANNEL, --slack-channel SLACK_CHANNEL  Issues will be published to this Slack channel
  -t SLACK_TOKEN, --slack-token SLACK_TOKEN        Slack auth token
  --no-labels                                      Prevent the script from labeling the issues
  -v, --verbose                                    Print detailed information about the issues that were found
```

#### Configuration

A configuration file is required for this script to run properly.  The file should contain a JSON string with the following fields:

`leads` : Array of configurations for each lead.

`leads.githubUsername` : The lead's GitHub username.

`leads.leadLabel`: Text of the lead's `Lead: @` label.

`leads.slackId`: The lead's Slack ID in their `mrkdwn` format, which is used to trigger Slack


__Running the script locally:__
```
docker compose exec -e PYTHONPATH=. web bash

# Publish digest of new comments from the past day to #openlibrary-g:
./scripts/gh_scripts/issue_comment_bot.py 24 -s "#openlibrary-g" -t "replace-with-slack-token" -c "path/to/config/file"
```

__Note:__ When adding arguments, be sure to place any hyphenated values within double quotes.

## `weekly_status_report.mjs`

This script prepares a digest of information helpful to leads, and publishes the digest to Slack.

### Usage

<pre><b>node weekly_status_report.mjs</b> config_filepath</pre>
`config_filepath` the location of the script's configuration file

A `SLACK_TOKEN` must be included as an environment variable in order to `POST` to Slack.

Additionally, a `GITHUB_TOKEN` should also be added as an environment variable.  `@octokit/action` adds
this to the `octokit` object during instantiation, allowing `octokit` to make authenticated requests
to GitHub.

#### Configuration

A configuration file is required for this script to run properly.  The file should contain a JSON string with the following fields:

`slackChannel` : The digest will be published here.

`publishFullDigest` : Boolean that flags whether to publish a full or partial digest.  If `false`, the digest will be published without several sections (see **Details**, below).

`leads` : Array of configurations for each lead.

`leads.githubUsername` : The lead's GitHub username.

`leads.leadLabel`: Text of the lead's `Lead: @` label.

`leads.slackId`: The lead's Slack ID in their `mrkdwn` format, which is used to trigger Slack notifications when the message is published.

### Details

The script prepares a digest containing the following sections:

*Recent comments* : A list of links to issues that need comments, broken down by lead.

*Needs: Lead/Assignee* : Lists of pull requests that do not have an assignee, and issues that need a lead.  Only present if `publishFullDigest` is `true`.

*Untriaged issues* : List of issues which have the https://github.com/internetarchive/openlibrary/labels/Needs%3A%20Triage label.  Only present if `publishFullDigest` is `true`.

*Assigned PRs* : List of pull requests that have been assigned, broken down by lead.  Links to higher priority PRs are also included here.

*Staff PRs* : List of all open staff PRs.  Only present if `publishFullDigest` is `true`.

*Submitter Input for PRs* : List of PRs that are labeled https://github.com/internetarchive/openlibrary/labels/Needs%3A%20Submitter%20Input, broken down by leads.
