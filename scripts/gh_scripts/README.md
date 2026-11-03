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
The script looks in the PR body for the issues it references, case-insensitively:
1. Closing keywords first (`Closes #N`, `Fixes #N`, `Resolves #N`, ...), then non-closing references (`Part of #N`, `Refs #N`, `Related to #N`, `Follow-up to #N`, `Works on #N`, `Towards #N`). A same-repo issue URL works in place of `#N`. References inside HTML comments (left-over template text) are ignored, a bare `#N` doesn't count, and only the first 5 references are looked up.
2. The lead comes from the first referenced issue that has a `Lead: @` label, or failing that from its parent issue in this repo (the epic it is a sub-issue of). References that are PRs, Discussions or missing numbers are skipped. The lead is assigned to the PR even when they wrote it, since as the owner they still have to see it through or hand it on.
3. The first https://github.com/internetarchive/openlibrary/labels/Priority%3A%200, https://github.com/internetarchive/openlibrary/labels/Priority%3A%201, or https://github.com/internetarchive/openlibrary/labels/Priority%3A%202 label on the first closing reference that has one is added to the PR. Non-closing references never supply a priority: "Part of #N" usually points at an epic, whose priority says little about one PR.

The decision and its reason (e.g. "#123 (closing keyword) has no Lead label") are written to the job summary. If GitHub silently drops the assignee (e.g. the lead has no repo access), the reason says "could not assign". The shared logic lives in `pr_lead_resolver.mjs` and `new_pr_labeler_core.mjs`.

## `pr_lead_sweep.mjs`
Runs on a schedule (`.github/workflows/pm_pr_lead_sweep.yml`; 14:00 and 02:00 UTC, i.e. 6 AM and 6 PM PST, an hour later during daylight time) and applies the same decision as `new_pr_labeler.mjs` to every open PR that is not a draft, was not opened by a bot, and has never had an assignee. This catches PRs whose issue got its lead after the PR opened, and PRs whose body was edited later. It never re-assigns someone a human removed; any earlier assignment, including a self-assignment, means the PR is left alone. It only adds a priority label to a PR that has none. One failing PR is reported in the summary without stopping the rest, and any failure fails the run.

### Usage:
<pre><b>node pr_lead_sweep.mjs</b> repository</pre>
It writes assignments and labels with the given `GITHUB_TOKEN`, so a local run acts on the real repository. A maintainer can also start it from the Actions tab ("Run workflow").

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
